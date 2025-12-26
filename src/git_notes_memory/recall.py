"""Memory recall and retrieval service.

Provides semantic search, memory retrieval, and hydration capabilities.
The service supports three hydration levels:
- SUMMARY: Only metadata and one-line summary (fastest)
- FULL: Complete note content
- FILES: Full content plus file snapshots at commit time

Memories can be searched semantically using vector similarity or filtered
by namespace and spec. The service also supports grouping memories by
spec into SpecContext objects for comprehensive context retrieval.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from git_notes_memory.config import TOKENS_PER_CHAR, get_project_index_path
from git_notes_memory.exceptions import RecallError
from git_notes_memory.models import (
    CommitInfo,
    HydratedMemory,
    HydrationLevel,
    Memory,
    MemoryResult,
    SpecContext,
)
from git_notes_memory.observability.decorators import measure_duration
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.tracing import trace_operation

if TYPE_CHECKING:
    from pathlib import Path

    from git_notes_memory.embedding import EmbeddingService
    from git_notes_memory.git_ops import GitOps
    from git_notes_memory.index import IndexService

__all__ = [
    "RecallService",
    "get_default_service",
]

logger = logging.getLogger(__name__)


# =============================================================================
# RecallService
# =============================================================================


class RecallService:
    """Service for retrieving and hydrating memories.

    Provides semantic search, direct retrieval, and hydration of memories
    at different levels of detail. Supports filtering by namespace and spec,
    and can aggregate memories into SpecContext objects for comprehensive
    context retrieval.

    Attributes:
        index_path: Path to the SQLite index database.

    Examples:
        >>> service = RecallService()
        >>> results = service.search("how to handle authentication")
        >>> for r in results:
        ...     print(f"{r.id}: {r.summary} (distance: {r.distance:.4f})")

        >>> hydrated = service.hydrate(results[0], HydrationLevel.FULL)
        >>> print(hydrated.full_content)
    """

    def __init__(
        self,
        index_path: Path | None = None,
        *,
        index_service: IndexService | None = None,
        embedding_service: EmbeddingService | None = None,
        git_ops: GitOps | None = None,
    ) -> None:
        """Initialize the recall service.

        Args:
            index_path: Path to the SQLite index database.
                Defaults to the XDG data directory's index.db.
            index_service: Optional pre-configured IndexService instance.
                If not provided, one will be created lazily.
            embedding_service: Optional pre-configured EmbeddingService instance.
                If not provided, one will be created lazily.
            git_ops: Optional pre-configured GitOps instance.
                If not provided, one will be created lazily.
        """
        # Use project-specific index for per-repository isolation
        self._index_path = index_path or get_project_index_path()
        self._index_service = index_service
        self._embedding_service = embedding_service
        self._git_ops = git_ops

    @property
    def index_path(self) -> Path:
        """Get the index database path."""
        return self._index_path

    # -------------------------------------------------------------------------
    # Lazy-loaded Dependencies
    # -------------------------------------------------------------------------

    def _get_index(self) -> IndexService:
        """Get or create the IndexService instance."""
        if self._index_service is None:
            from git_notes_memory.index import IndexService

            self._index_service = IndexService(self._index_path)
            self._index_service.initialize()
        return self._index_service

    def _get_embedding(self) -> EmbeddingService:
        """Get or create the EmbeddingService instance."""
        if self._embedding_service is None:
            from git_notes_memory.embedding import get_default_service

            self._embedding_service = get_default_service()
        return self._embedding_service

    def _get_git_ops(self) -> GitOps:
        """Get or create the GitOps instance."""
        if self._git_ops is None:
            from git_notes_memory.git_ops import GitOps

            self._git_ops = GitOps()
        return self._git_ops

    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------

    @measure_duration("memory_search")
    def search(
        self,
        query: str,
        k: int = 10,
        *,
        namespace: str | None = None,
        spec: str | None = None,
        min_similarity: float | None = None,
    ) -> list[MemoryResult]:
        """Search for memories semantically similar to the query.

        Uses vector similarity search to find memories with content
        similar to the query text.

        Args:
            query: The search query text.
            k: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            spec: Optional spec identifier to filter results.
            min_similarity: Minimum similarity threshold (0-1).
                Results with similarity below this are filtered out.

        Returns:
            List of MemoryResult objects sorted by relevance (most similar first).

        Raises:
            RecallError: If the search operation fails.

        Examples:
            >>> results = service.search("authentication flow")
            >>> results = service.search("error handling", namespace="decisions")
            >>> results = service.search("api design", k=5, min_similarity=0.5)
        """
        if not query or not query.strip():
            return []

        metrics = get_metrics()

        with trace_operation("search", labels={"search_type": "semantic"}):
            try:
                # Generate embedding for the query
                with trace_operation("search.embed_query"):
                    embedding_service = self._get_embedding()
                    query_embedding = embedding_service.embed(query)

                # Search the index
                with trace_operation("search.vector_search"):
                    index = self._get_index()
                    raw_results = index.search_vector(
                        query_embedding,
                        k=k,
                        namespace=namespace,
                        spec=spec,
                    )

                # Convert to MemoryResult and apply similarity filter
                results: list[MemoryResult] = []
                for memory, distance in raw_results:
                    # Convert distance to similarity (assuming L2 distance)
                    # For normalized vectors, similarity = 1 - (distance^2 / 2)
                    # But sqlite-vec returns distance directly, use 1 / (1 + distance)
                    similarity = 1.0 / (1.0 + distance) if distance >= 0 else 0.0

                    if min_similarity is not None and similarity < min_similarity:
                        continue

                    results.append(MemoryResult(memory=memory, distance=distance))

                # Track retrieval count
                metrics.increment(
                    "memories_retrieved_total",
                    amount=float(len(results)),
                    labels={"search_type": "semantic"},
                )

                logger.debug(
                    "Search for '%s' returned %d results (k=%d, namespace=%s, spec=%s)",
                    query[:50],
                    len(results),
                    k,
                    namespace,
                    spec,
                )

                return results

            except Exception as e:
                raise RecallError(
                    f"Search failed: {e}",
                    "Check query text and try again",
                ) from e

    @measure_duration("memory_search_text")
    def search_text(
        self,
        query: str,
        limit: int = 10,
        *,
        namespace: str | None = None,
        spec: str | None = None,
    ) -> list[Memory]:
        """Search for memories using text matching (FTS5).

        Uses SQLite full-text search for exact or partial text matches.
        This is faster than semantic search but less flexible.

        Args:
            query: The search query text.
            limit: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            spec: Optional spec identifier to filter results.

        Returns:
            List of Memory objects matching the query.

        Raises:
            RecallError: If the search operation fails.

        Examples:
            >>> memories = service.search_text("API endpoint")
            >>> memories = service.search_text("bug fix", namespace="decisions")
        """
        if not query or not query.strip():
            return []

        metrics = get_metrics()

        with trace_operation("search", labels={"search_type": "text"}):
            try:
                index = self._get_index()
                results = index.search_text(
                    query,
                    limit=limit,
                    namespace=namespace,
                    spec=spec,
                )

                # Track retrieval count
                metrics.increment(
                    "memories_retrieved_total",
                    amount=float(len(results)),
                    labels={"search_type": "text"},
                )

                logger.debug(
                    "Text search for '%s' returned %d results",
                    query[:50],
                    len(results),
                )

                return results

            except Exception as e:
                raise RecallError(
                    f"Text search failed: {e}",
                    "Check query text and try again",
                ) from e

    # -------------------------------------------------------------------------
    # Direct Retrieval
    # -------------------------------------------------------------------------

    def get(self, memory_id: str) -> Memory | None:
        """Retrieve a memory by its ID.

        Args:
            memory_id: The memory ID in format "namespace:commit_sha:index".

        Returns:
            The Memory object if found, None otherwise.

        Examples:
            >>> memory = service.get("decisions:abc123:0")
            >>> if memory:
            ...     print(memory.summary)
        """
        try:
            index = self._get_index()
            return index.get(memory_id)
        except Exception as e:
            logger.warning("Failed to get memory %s: %s", memory_id, e)
            return None

    def get_batch(self, memory_ids: Sequence[str]) -> list[Memory]:
        """Retrieve multiple memories by their IDs.

        Args:
            memory_ids: Sequence of memory IDs.

        Returns:
            List of found Memory objects. Missing memories are omitted.

        Examples:
            >>> memories = service.get_batch(
            ...     ["decisions:abc123:0", "learnings:def456:1"]
            ... )
        """
        if not memory_ids:
            return []

        try:
            index = self._get_index()
            return index.get_batch(memory_ids)
        except Exception as e:
            logger.warning("Failed to get batch memories: %s", e)
            return []

    def get_by_namespace(
        self,
        namespace: str,
        *,
        spec: str | None = None,
        limit: int | None = None,
    ) -> list[Memory]:
        """Retrieve all memories in a namespace.

        Args:
            namespace: The namespace to retrieve from.
            spec: Optional spec identifier to filter results.
            limit: Maximum number of results to return.

        Returns:
            List of Memory objects in the namespace.

        Examples:
            >>> decisions = service.get_by_namespace("decisions")
            >>> spec_learnings = service.get_by_namespace("learnings", spec="SPEC-001")
        """
        try:
            index = self._get_index()
            return index.get_by_namespace(namespace, spec=spec, limit=limit)
        except Exception as e:
            logger.warning("Failed to get memories for namespace %s: %s", namespace, e)
            return []

    def get_by_spec(
        self,
        spec: str,
        *,
        namespace: str | None = None,
        limit: int | None = None,
    ) -> list[Memory]:
        """Retrieve all memories for a spec.

        Args:
            spec: The spec identifier (e.g., "SPEC-2025-12-18-001").
            namespace: Optional namespace to filter results.
            limit: Maximum number of results to return.

        Returns:
            List of Memory objects for the spec.

        Examples:
            >>> all_spec_memories = service.get_by_spec("SPEC-2025-12-18-001")
            >>> spec_decisions = service.get_by_spec("SPEC-001", namespace="decisions")
        """
        try:
            index = self._get_index()
            return index.get_by_spec(spec, namespace=namespace, limit=limit)
        except Exception as e:
            logger.warning("Failed to get memories for spec %s: %s", spec, e)
            return []

    def list_recent(
        self,
        limit: int = 10,
        *,
        namespace: str | None = None,
        spec: str | None = None,
    ) -> list[MemoryResult]:
        """List the most recent memories.

        Args:
            limit: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            spec: Optional spec identifier to filter results.

        Returns:
            List of MemoryResult objects sorted by creation time (newest first).
            Distance is set to 0.0 for recency-based results.

        Examples:
            >>> recent = service.list_recent(5)
            >>> recent_decisions = service.list_recent(10, namespace="decisions")
        """
        try:
            index = self._get_index()
            memories = index.list_recent(limit=limit, namespace=namespace, spec=spec)

            # Wrap in MemoryResult with zero distance (not a similarity search)
            return [MemoryResult(memory=m, distance=0.0) for m in memories]

        except Exception as e:
            logger.warning("Failed to list recent memories: %s", e)
            return []

    # -------------------------------------------------------------------------
    # Hydration
    # -------------------------------------------------------------------------

    def hydrate(
        self,
        memory_or_result: Memory | MemoryResult,
        level: HydrationLevel = HydrationLevel.SUMMARY,
    ) -> HydratedMemory:
        """Hydrate a memory to the specified level of detail.

        Hydration levels:
        - SUMMARY: Only the memory metadata (no additional loading)
        - FULL: Loads the complete note content from git
        - FILES: Loads content plus file snapshots at commit time

        Args:
            memory_or_result: The memory to hydrate. Can be a Memory or MemoryResult.
            level: The level of detail to hydrate to.

        Returns:
            A HydratedMemory object with the requested level of detail.

        Raises:
            RecallError: If hydration fails.

        Examples:
            >>> result = service.search("auth")[0]
            >>> hydrated = service.hydrate(result, HydrationLevel.FULL)
            >>> print(hydrated.full_content)

            >>> hydrated = service.hydrate(result, HydrationLevel.FILES)
            >>> for path, content in hydrated.files:
            ...     print(f"{path}: {len(content)} bytes")
        """
        # Normalize to MemoryResult
        if isinstance(memory_or_result, Memory):
            result = MemoryResult(memory=memory_or_result, distance=0.0)
        else:
            result = memory_or_result

        memory = result.memory

        # SUMMARY level - no additional loading needed
        if level == HydrationLevel.SUMMARY:
            return HydratedMemory(result=result)

        try:
            git_ops = self._get_git_ops()

            # FULL level - load note content
            full_content: str | None = None
            commit_info: CommitInfo | None = None

            if level.value >= HydrationLevel.FULL.value:
                # Get the full note content
                full_content = git_ops.show_note(
                    namespace=memory.namespace,
                    commit=memory.commit_sha,
                )

                # Get commit info
                try:
                    commit_info = git_ops.get_commit_info(memory.commit_sha)
                except Exception as e:
                    logger.debug(
                        "Failed to get commit info for %s: %s", memory.commit_sha, e
                    )

            # FILES level - also load file snapshots
            files: tuple[tuple[str, str], ...] = ()

            if level == HydrationLevel.FILES:
                files = self._load_files_at_commit(memory.commit_sha)

            return HydratedMemory(
                result=result,
                full_content=full_content,
                files=files,
                commit_info=commit_info,
            )

        except Exception as e:
            raise RecallError(
                f"Failed to hydrate memory {memory.id}: {e}",
                "Check that the git repository is accessible",
            ) from e

    def hydrate_batch(
        self,
        memories: Sequence[Memory | MemoryResult],
        level: HydrationLevel = HydrationLevel.SUMMARY,
    ) -> list[HydratedMemory]:
        """Hydrate multiple memories to the specified level.

        Uses batch git operations (PERF-003) for efficient retrieval when
        hydrating FULL or FILES level.

        Args:
            memories: Sequence of memories to hydrate.
            level: The level of detail to hydrate to.

        Returns:
            List of HydratedMemory objects.

        Examples:
            >>> results = service.search("auth")
            >>> hydrated = service.hydrate_batch(results, HydrationLevel.FULL)
        """
        if not memories:
            return []

        # SUMMARY level doesn't need git ops
        if level == HydrationLevel.SUMMARY:
            return [
                HydratedMemory(
                    result=(
                        MemoryResult(memory=m, distance=0.0)
                        if isinstance(m, Memory)
                        else m
                    )
                )
                for m in memories
            ]

        # Normalize to MemoryResult
        results: list[MemoryResult] = []
        for m in memories:
            if isinstance(m, Memory):
                results.append(MemoryResult(memory=m, distance=0.0))
            else:
                results.append(m)

        # PERF-003: Group memories by namespace for batch git operations
        git_ops = self._get_git_ops()

        # Collect unique (namespace, commit_sha) pairs
        namespace_commits: dict[str, list[str]] = {}
        for r in results:
            ns = r.memory.namespace
            if ns not in namespace_commits:
                namespace_commits[ns] = []
            if r.memory.commit_sha not in namespace_commits[ns]:
                namespace_commits[ns].append(r.memory.commit_sha)

        # Batch fetch note contents by namespace
        note_contents: dict[str, dict[str, str | None]] = {}
        for ns, commit_shas in namespace_commits.items():
            note_contents[ns] = git_ops.show_notes_batch(ns, commit_shas)

        # Build hydrated memories using cached contents
        hydrated: list[HydratedMemory] = []
        for r in results:
            memory = r.memory
            full_content: str | None = None
            commit_info: CommitInfo | None = None
            files: tuple[tuple[str, str], ...] = ()

            if level.value >= HydrationLevel.FULL.value:
                # Get from batch-fetched contents
                ns_contents = note_contents.get(memory.namespace, {})
                full_content = ns_contents.get(memory.commit_sha)

                # Get commit info (not batched - less critical for perf)
                try:
                    commit_info = git_ops.get_commit_info(memory.commit_sha)
                except Exception as e:
                    logger.debug(
                        "Failed to get commit info for %s: %s", memory.commit_sha, e
                    )

            if level == HydrationLevel.FILES:
                files = self._load_files_at_commit(memory.commit_sha)

            hydrated.append(
                HydratedMemory(
                    result=r,
                    full_content=full_content,
                    files=files,
                    commit_info=commit_info,
                )
            )

        return hydrated

    def _load_files_at_commit(self, commit_sha: str) -> tuple[tuple[str, str], ...]:
        """Load file snapshots at a specific commit.

        Args:
            commit_sha: The commit SHA to load files from.

        Returns:
            Tuple of (path, content) pairs for changed files.
        """
        try:
            git_ops = self._get_git_ops()

            # Get list of changed files in the commit
            changed_files = git_ops.get_changed_files(commit_sha)

            # Load content for each file
            files: list[tuple[str, str]] = []
            for path in changed_files:
                try:
                    content = git_ops.get_file_at_commit(path, commit_sha)
                    if content is not None:
                        files.append((path, content))
                except Exception as e:
                    logger.debug(
                        "Failed to load file %s at %s: %s", path, commit_sha, e
                    )

            return tuple(files)

        except Exception as e:
            logger.debug("Failed to load files at commit %s: %s", commit_sha, e)
            return ()

    # -------------------------------------------------------------------------
    # Context Aggregation
    # -------------------------------------------------------------------------

    def get_spec_context(
        self,
        spec: str,
        *,
        hydration_level: HydrationLevel = HydrationLevel.SUMMARY,
    ) -> SpecContext:
        """Get aggregated context for a spec.

        Retrieves all memories for a spec and organizes them by namespace.
        Includes token estimation for LLM context window management.

        Args:
            spec: The spec identifier (e.g., "SPEC-2025-12-18-001").
            hydration_level: Level of detail for memory content.
                Only affects token estimation accuracy.

        Returns:
            A SpecContext object with all memories organized by namespace.

        Examples:
            >>> ctx = service.get_spec_context("SPEC-2025-12-18-001")
            >>> print(f"Total memories: {ctx.total_count}")
            >>> print(f"Token estimate: {ctx.token_estimate}")
            >>> for ns, memories in ctx.by_namespace.items():
            ...     print(f"{ns}: {len(memories)} memories")
        """
        try:
            # Get all memories for the spec
            memories = self.get_by_spec(spec)

            # Calculate token estimate
            token_estimate = self._estimate_tokens(memories, hydration_level)

            return SpecContext(
                spec=spec,
                memories=tuple(memories),
                total_count=len(memories),
                token_estimate=token_estimate,
            )

        except Exception as e:
            logger.warning("Failed to get spec context for %s: %s", spec, e)
            return SpecContext(spec=spec)

    def _estimate_tokens(
        self,
        memories: Sequence[Memory],
        level: HydrationLevel,
    ) -> int:
        """Estimate the number of tokens for a set of memories.

        Uses a simple character-based estimation: ~4 characters per token.
        PERF-006: Uses generator expression for single-pass calculation.

        Args:
            memories: Sequence of memories to estimate.
            level: The hydration level (affects what content is counted).

        Returns:
            Estimated token count.
        """
        include_content = level.value >= HydrationLevel.FULL.value

        # PERF-006: Single-pass generator avoids loop variable overhead
        total_chars = sum(
            len(m.summary)
            + (len(m.content) if include_content else 0)
            + 50  # Metadata overhead
            for m in memories
        )

        return int(total_chars * TOKENS_PER_CHAR)

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def recall_context(
        self,
        query: str,
        k: int = 5,
        *,
        namespace: str | None = None,
        hydration_level: HydrationLevel = HydrationLevel.SUMMARY,
    ) -> list[HydratedMemory]:
        """Search and hydrate memories in one operation.

        Convenience method that combines search and hydration.

        Args:
            query: The search query text.
            k: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            hydration_level: Level of detail for hydration.

        Returns:
            List of HydratedMemory objects sorted by relevance.

        Examples:
            >>> context = service.recall_context(
            ...     "how do we handle errors",
            ...     k=3,
            ...     hydration_level=HydrationLevel.FULL,
            ... )
            >>> for h in context:
            ...     print(h.result.summary)
        """
        results = self.search(query, k=k, namespace=namespace)
        return self.hydrate_batch(results, hydration_level)

    def recall_similar(
        self,
        memory: Memory,
        k: int = 5,
        *,
        exclude_self: bool = True,
    ) -> list[MemoryResult]:
        """Find memories similar to an existing memory.

        Args:
            memory: The reference memory to find similar items for.
            k: Maximum number of results to return.
            exclude_self: Whether to exclude the reference memory from results.

        Returns:
            List of similar MemoryResult objects.

        Examples:
            >>> memory = service.get("decisions:abc123:0")
            >>> similar = service.recall_similar(memory, k=3)
        """
        if not memory.content:
            return []

        # Search using the memory's content
        results = self.search(memory.content, k=k + 1 if exclude_self else k)

        # Optionally filter out the reference memory
        if exclude_self:
            results = [r for r in results if r.memory.id != memory.id][:k]

        return results


# =============================================================================
# Singleton Access (using ServiceRegistry)
# =============================================================================


def get_default_service() -> RecallService:
    """Get the default recall service singleton.

    Returns:
        The default RecallService instance.

    Examples:
        >>> service = get_default_service()
        >>> results = service.search("authentication")
    """
    from git_notes_memory.registry import ServiceRegistry

    return ServiceRegistry.get(RecallService)
