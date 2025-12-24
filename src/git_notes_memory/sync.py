"""Synchronization service for index and git notes consistency.

This module provides the SyncService that keeps the SQLite index
synchronized with the authoritative git notes storage.

Key Operations:
    - sync_note_to_index: Index a single note by commit
    - reindex: Rebuild entire index from git notes
    - verify_consistency: Check index vs notes for drift
    - collect_notes: Gather all notes across namespaces
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from git_notes_memory.config import NAMESPACES, get_project_index_path
from git_notes_memory.exceptions import RecallError
from git_notes_memory.models import Memory, NoteRecord, VerificationResult

if TYPE_CHECKING:
    from git_notes_memory.embedding import EmbeddingService
    from git_notes_memory.git_ops import GitOps
    from git_notes_memory.index import IndexService
    from git_notes_memory.note_parser import NoteParser

__all__ = ["SyncService", "get_sync_service"]

logger = logging.getLogger(__name__)


class SyncService:
    """Service for synchronizing index with git notes.

    This service maintains consistency between the authoritative
    git notes storage and the SQLite vector index. It supports:

    - Indexing individual notes (for incremental updates)
    - Full reindexing (for recovery or initial setup)
    - Consistency verification (for detecting drift)

    The service uses lazy dependency injection to avoid circular
    imports and allow flexible testing.

    Attributes:
        repo_path: Path to the git repository.
    """

    def __init__(
        self,
        repo_path: Path | None = None,
        *,
        index: IndexService | None = None,
        git_ops: GitOps | None = None,
        embedding_service: EmbeddingService | None = None,
        note_parser: NoteParser | None = None,
    ) -> None:
        """Initialize the sync service.

        Args:
            repo_path: Path to git repository. Defaults to cwd.
            index: IndexService instance (optional, for testing).
            git_ops: GitOps instance (optional, for testing).
            embedding_service: EmbeddingService instance (optional, for testing).
            note_parser: NoteParser instance (optional, for testing).
        """
        self.repo_path = repo_path or Path.cwd()
        self._index = index
        self._git_ops = git_ops
        self._embedding_service = embedding_service
        self._note_parser = note_parser

    def _get_index(self) -> IndexService:
        """Get or create IndexService instance using project-specific database."""
        if self._index is None:
            from git_notes_memory.index import IndexService

            # Use project-specific index for per-repository isolation
            self._index = IndexService(get_project_index_path(self.repo_path))
            self._index.initialize()
        return self._index

    def _get_git_ops(self) -> GitOps:
        """Get or create GitOps instance."""
        if self._git_ops is None:
            from git_notes_memory.git_ops import GitOps

            self._git_ops = GitOps(self.repo_path)
        return self._git_ops

    def _get_embedding_service(self) -> EmbeddingService:
        """Get or create EmbeddingService instance."""
        if self._embedding_service is None:
            from git_notes_memory.embedding import EmbeddingService

            self._embedding_service = EmbeddingService()
        return self._embedding_service

    def _get_note_parser(self) -> NoteParser:
        """Get or create NoteParser instance."""
        if self._note_parser is None:
            from git_notes_memory.note_parser import NoteParser

            self._note_parser = NoteParser()
        return self._note_parser

    def sync_note_to_index(
        self,
        commit: str,
        namespace: str,
    ) -> int:
        """Parse and index a single note.

        Reads the note content from git notes, parses it to extract
        memory records, generates embeddings, and inserts into the index.

        Args:
            commit: Commit SHA to index note from.
            namespace: Memory namespace.

        Returns:
            Number of memories indexed from the note.

        Raises:
            StorageError: If note cannot be read.
            RecallError: If indexing fails.
        """
        git_ops = self._get_git_ops()
        parser = self._get_note_parser()
        index = self._get_index()
        embedding = self._get_embedding_service()

        # Get note content
        content = git_ops.show_note(namespace, commit)
        if content is None:
            logger.debug("No note at %s for namespace %s", commit, namespace)
            return 0

        # Parse note content to records
        try:
            records = parser.parse_many(content)
        except Exception as e:
            logger.warning("Failed to parse note at %s: %s", commit, e)
            return 0

        # Convert to memories and index
        indexed = 0
        for i, record in enumerate(records):
            memory = self._record_to_memory(record, commit, namespace, i)

            # Generate embedding
            embed_vector = None
            try:
                text_for_embedding = f"{memory.summary}\n{memory.content}"
                embed_vector = embedding.embed(text_for_embedding)
            except Exception as e:
                logger.warning("Embedding failed for %s: %s", memory.id, e)

            # Insert into index
            try:
                if index.exists(memory.id):
                    index.update(memory, embedding=embed_vector)
                else:
                    index.insert(memory, embedding=embed_vector)
                indexed += 1
            except Exception as e:
                logger.warning("Failed to index memory %s: %s", memory.id, e)

        return indexed

    def _record_to_memory(
        self,
        record: NoteRecord,
        commit: str,
        namespace: str,
        index: int,
    ) -> Memory:
        """Convert a NoteRecord to a Memory with generated ID.

        Args:
            record: The parsed note record.
            commit: Commit SHA the note is attached to.
            namespace: Memory namespace.
            index: Index of this record within the note.

        Returns:
            Memory instance with deterministic ID.
        """
        from datetime import UTC, datetime

        # Generate deterministic ID
        memory_id = f"{namespace}:{commit[:7]}:{index}"

        # Parse timestamp or use current time
        timestamp = record.timestamp
        if timestamp is None:
            timestamp = datetime.now(UTC)

        return Memory(
            id=memory_id,
            commit_sha=commit,
            namespace=namespace,
            timestamp=timestamp,
            summary=record.summary or "",
            content=record.body or "",
            spec=record.spec,
            tags=tuple(record.tags) if record.tags else (),
            phase=record.phase,
            status=record.status or "active",
            relates_to=tuple(record.relates_to) if record.relates_to else (),
        )

    def collect_notes(self) -> list[NoteRecord]:
        """Collect all notes across all namespaces.

        Iterates through all namespaces, lists notes, and parses
        their content into NoteRecord objects.

        Uses batch git operations (PERF-001) for efficient retrieval.

        Returns:
            List of all NoteRecord objects from git notes.
        """
        git_ops = self._get_git_ops()
        parser = self._get_note_parser()
        all_records: list[NoteRecord] = []

        for namespace in NAMESPACES:
            try:
                notes_list = git_ops.list_notes(namespace)
            except Exception as e:
                logger.debug("No notes in namespace %s: %s", namespace, e)
                continue

            if not notes_list:
                continue

            # PERF-001: Batch fetch all notes for this namespace
            commit_shas = [commit_sha for _note_sha, commit_sha in notes_list]
            contents = git_ops.show_notes_batch(namespace, commit_shas)

            for _note_sha, commit_sha in notes_list:
                try:
                    content = contents.get(commit_sha)
                    if content:
                        # Pass commit_sha and namespace so NoteRecord has them
                        records = parser.parse_many(
                            content,
                            commit_sha=commit_sha,
                            namespace=namespace,
                        )
                        all_records.extend(records)
                except Exception as e:
                    logger.warning(
                        "Failed to read note at %s/%s: %s",
                        namespace,
                        commit_sha,
                        e,
                    )

        return all_records

    def reindex(self, *, full: bool = False) -> int:
        """Rebuild the index from git notes.

        Uses batch git operations (PERF-001) and batch embedding (PERF-002)
        for efficient retrieval and vectorization.

        Args:
            full: If True, clears index first. Otherwise incremental.

        Returns:
            Number of memories indexed.

        Raises:
            StorageError: If git operations fail.
            RecallError: If indexing fails.
        """
        git_ops = self._get_git_ops()
        index = self._get_index()
        embedding_service = self._get_embedding_service()
        parser = self._get_note_parser()

        if full:
            logger.info("Starting full reindex - clearing existing index")
            index.clear()

        indexed = 0
        for namespace in NAMESPACES:
            try:
                notes_list = git_ops.list_notes(namespace)
            except Exception as e:
                logger.debug("No notes in namespace %s: %s", namespace, e)
                continue

            if not notes_list:
                continue

            # PERF-001: Batch fetch all notes for this namespace
            commit_shas = [commit_sha for _note_sha, commit_sha in notes_list]
            contents = git_ops.show_notes_batch(namespace, commit_shas)

            # First pass: collect all memories and texts for batch embedding
            memories_to_index: list[Memory] = []
            texts_to_embed: list[str] = []

            for _note_sha, commit_sha in notes_list:
                try:
                    content = contents.get(commit_sha)
                    if not content:
                        continue

                    records = parser.parse_many(content)
                    for i, record in enumerate(records):
                        memory = self._record_to_memory(
                            record, commit_sha, namespace, i
                        )

                        # Skip if already exists and not full reindex
                        if not full and index.exists(memory.id):
                            continue

                        memories_to_index.append(memory)
                        texts_to_embed.append(f"{memory.summary}\n{memory.content}")

                except Exception as e:
                    logger.warning(
                        "Failed to process note %s/%s: %s",
                        namespace,
                        commit_sha,
                        e,
                    )

            if not memories_to_index:
                continue

            # PERF-002: Batch generate all embeddings at once
            embeddings: list[list[float]] | list[None] = []
            try:
                embeddings = embedding_service.embed_batch(texts_to_embed)
            except Exception as e:
                logger.warning(
                    "Batch embedding failed for namespace %s: %s",
                    namespace,
                    e,
                )
                # Fall back to None embeddings for all
                embeddings = [None] * len(memories_to_index)

            # Second pass: insert memories with their embeddings
            for memory, embed_vector in zip(memories_to_index, embeddings, strict=True):
                try:
                    index.insert(memory, embedding=embed_vector)
                    indexed += 1
                except Exception as e:
                    logger.warning(
                        "Failed to index memory %s: %s",
                        memory.id,
                        e,
                    )

        logger.info("Reindex complete: %d memories indexed", indexed)
        return indexed

    def verify_consistency(self) -> VerificationResult:
        """Check index consistency against git notes.

        Compares the set of memory IDs in the index with those
        that should exist based on git notes content.

        Uses batch git operations (PERF-001) for efficient retrieval.

        Returns:
            VerificationResult with details of any inconsistencies.
        """
        git_ops = self._get_git_ops()
        index = self._get_index()
        parser = self._get_note_parser()

        # Collect all memory IDs that should exist from git notes
        expected_ids: set[str] = set()
        memory_hashes: dict[str, str] = {}  # id -> content hash

        for namespace in NAMESPACES:
            try:
                notes_list = git_ops.list_notes(namespace)
            except Exception:
                continue

            if not notes_list:
                continue

            # PERF-001: Batch fetch all notes for this namespace
            commit_shas = [commit_sha for _note_sha, commit_sha in notes_list]
            contents = git_ops.show_notes_batch(namespace, commit_shas)

            for _note_sha, commit_sha in notes_list:
                try:
                    content = contents.get(commit_sha)
                    if not content:
                        continue

                    records = parser.parse_many(content)
                    for i, record in enumerate(records):
                        memory_id = f"{namespace}:{commit_sha[:7]}:{i}"
                        expected_ids.add(memory_id)
                        # Store hash of content for mismatch detection
                        content_str = f"{record.summary}|{record.body}"
                        memory_hashes[memory_id] = hashlib.md5(
                            content_str.encode(), usedforsecurity=False
                        ).hexdigest()
                except Exception as e:
                    logger.debug("Error processing note: %s", e)

        # Get all memory IDs from index
        try:
            indexed_ids = set(index.get_all_ids())
        except Exception as e:
            raise RecallError(
                f"Failed to read index: {e}",
                "Run '/memory reindex --full' to rebuild the index",
            ) from e

        # Find discrepancies
        missing_in_index = expected_ids - indexed_ids
        orphaned_in_index = indexed_ids - expected_ids

        # Check for content mismatches (simplified - just check if exists)
        mismatched: list[str] = []
        for memory_id in expected_ids & indexed_ids:
            try:
                memory = index.get(memory_id)
                if memory:
                    current_hash = hashlib.md5(
                        f"{memory.summary}|{memory.content}".encode(),
                        usedforsecurity=False,
                    ).hexdigest()
                    expected_hash = memory_hashes.get(memory_id, "")
                    if current_hash != expected_hash:
                        mismatched.append(memory_id)
            except Exception:
                pass

        is_consistent = (
            len(missing_in_index) == 0
            and len(orphaned_in_index) == 0
            and len(mismatched) == 0
        )

        return VerificationResult(
            is_consistent=is_consistent,
            missing_in_index=tuple(sorted(missing_in_index)),
            orphaned_in_index=tuple(sorted(orphaned_in_index)),
            mismatched=tuple(sorted(mismatched)),
        )

    def repair(self, verification: VerificationResult | None = None) -> int:
        """Repair inconsistencies found by verify_consistency.

        Args:
            verification: Previous verification result, or None to verify first.

        Returns:
            Number of repairs made.
        """
        if verification is None:
            verification = self.verify_consistency()

        if verification.is_consistent:
            logger.info("Index is consistent, no repairs needed")
            return 0

        index = self._get_index()
        repairs = 0

        # Remove orphaned entries
        for memory_id in verification.orphaned_in_index:
            try:
                index.delete(memory_id)
                repairs += 1
                logger.debug("Removed orphaned entry: %s", memory_id)
            except Exception as e:
                logger.warning("Failed to remove %s: %s", memory_id, e)

        # Re-index missing and mismatched entries
        to_reindex = set(verification.missing_in_index) | set(verification.mismatched)
        for memory_id in to_reindex:
            # Parse memory_id to get namespace and commit
            parts = memory_id.split(":")
            if len(parts) >= 2:
                namespace = parts[0]
                commit_prefix = parts[1]
                # We need to find the full commit SHA
                # For now, sync the note which will re-add this memory
                try:
                    git_ops = self._get_git_ops()
                    notes_list = git_ops.list_notes(namespace)
                    for _note_sha, commit_sha in notes_list:
                        if commit_sha.startswith(commit_prefix):
                            self.sync_note_to_index(commit_sha, namespace)
                            repairs += 1
                            break
                except Exception as e:
                    logger.warning("Failed to repair %s: %s", memory_id, e)

        logger.info("Repair complete: %d changes made", repairs)
        return repairs


# =============================================================================
# Singleton Access (using ServiceRegistry)
# =============================================================================


def get_sync_service(repo_path: Path | None = None) -> SyncService:
    """Get or create the singleton SyncService instance.

    Args:
        repo_path: Optional repo path for first initialization.

    Returns:
        The SyncService singleton.
    """
    from git_notes_memory.registry import ServiceRegistry

    # If repo_path is provided, pass it to get() for initialization
    if repo_path is not None:
        return ServiceRegistry.get(SyncService, repo_path=repo_path)

    return ServiceRegistry.get(SyncService)
