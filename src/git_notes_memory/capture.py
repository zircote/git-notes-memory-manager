"""Capture service for storing memories in git notes.

Orchestrates memory capture operations with concurrency safety, validation,
and graceful degradation when embedding fails. The capture flow:

1. Validate input (namespace, content length)
2. Acquire file lock for concurrency
3. Create YAML front matter metadata
4. Write to git notes (append for concurrency safety)
5. Generate embedding (graceful degradation on failure)
6. Insert into index
7. Release lock
"""

from __future__ import annotations

import fcntl
import logging
import os
import random
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from git_notes_memory.config import (
    MAX_CONTENT_BYTES,
    MAX_SUMMARY_CHARS,
    NAMESPACES,
    get_lock_path,
)
from git_notes_memory.exceptions import (
    CaptureError,
    ValidationError,
)
from git_notes_memory.git_ops import GitOps
from git_notes_memory.models import CaptureResult, Memory
from git_notes_memory.note_parser import serialize_note
from git_notes_memory.observability.decorators import measure_duration
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.tracing import trace_operation

if TYPE_CHECKING:
    from git_notes_memory.embedding import EmbeddingService
    from git_notes_memory.index import IndexService
    from git_notes_memory.security.service import SecretsFilteringService

__all__ = [
    "CaptureService",
    "get_default_service",
]

logger = logging.getLogger(__name__)


# =============================================================================
# File Locking
# =============================================================================


@contextmanager
def _acquire_lock(lock_path: Path, timeout: float = 10.0) -> Iterator[None]:
    """Acquire an exclusive file lock for capture operations.

    Uses fcntl advisory locking to prevent concurrent corruption. The lock
    is automatically released when the context manager exits.

    Uses non-blocking lock with retry loop to implement timeout, preventing
    indefinite blocking if another process holds the lock.

    Args:
        lock_path: Path to the lock file.
        timeout: Maximum time to wait for lock (seconds). Default 10.0.

    Yields:
        None when lock is acquired.

    Raises:
        CaptureError: If the lock cannot be acquired within the timeout.
    """
    # Ensure parent directory exists
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = None
    try:
        # Open or create lock file with restrictive permissions (MED-001)
        # O_NOFOLLOW prevents symlink attacks (HIGH-005: TOCTOU mitigation)
        fd = os.open(
            str(lock_path),
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600,
        )

        # Acquire exclusive lock with timeout using non-blocking retry loop
        # CRIT-001: Prevents indefinite blocking if lock is held
        # Uses exponential backoff with jitter to reduce contention under high concurrency
        deadline = time.monotonic() + timeout
        base_interval = 0.05  # Start with 50ms
        max_interval = 2.0  # Cap at 2 seconds
        attempt = 0

        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                logger.debug("Acquired capture lock: %s", lock_path)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise CaptureError(
                        f"Lock acquisition timed out after {timeout}s",
                        "Another capture may be in progress, wait and retry",
                    ) from None
                # Exponential backoff: 50ms, 100ms, 200ms, ... up to max_interval
                # Add jitter (0-10% of interval) to prevent thundering herd
                interval = min(base_interval * (2**attempt), max_interval)
                jitter = random.uniform(0, interval * 0.1)  # noqa: S311
                time.sleep(interval + jitter)
                attempt += 1
            except OSError as e:
                raise CaptureError(
                    f"Failed to acquire capture lock: {e}",
                    "Another capture may be in progress, wait and retry",
                ) from e

        yield

    finally:
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
                logger.debug("Released capture lock: %s", lock_path)
            except OSError as e:
                # Log warning rather than silently ignoring - helps debug lock issues
                logger.warning("Failed to release capture lock %s: %s", lock_path, e)
                metrics = get_metrics()
                metrics.increment(
                    "silent_failures_total",
                    labels={"location": "capture.lock_release"},
                )


# =============================================================================
# Validation
# =============================================================================


def _validate_namespace(namespace: str) -> None:
    """Validate that a namespace is valid.

    Args:
        namespace: The namespace to validate.

    Raises:
        ValidationError: If the namespace is invalid.
    """
    if not namespace:
        raise ValidationError(
            "Namespace cannot be empty",
            f"Use one of: {', '.join(sorted(NAMESPACES))}",
        )

    if namespace not in NAMESPACES:
        raise ValidationError(
            f"Invalid namespace: '{namespace}'",
            f"Use one of: {', '.join(sorted(NAMESPACES))}",
        )


def _validate_summary(summary: str) -> None:
    """Validate that a summary is valid.

    Args:
        summary: The summary to validate.

    Raises:
        ValidationError: If the summary is invalid.
    """
    if not summary or not summary.strip():
        raise ValidationError(
            "Summary cannot be empty",
            "Provide a one-line summary of the memory",
        )

    if len(summary) > MAX_SUMMARY_CHARS:
        raise ValidationError(
            f"Summary too long: {len(summary)} characters (max {MAX_SUMMARY_CHARS})",
            f"Shorten the summary to {MAX_SUMMARY_CHARS} characters or less",
        )


def _validate_content(content: str) -> None:
    """Validate that content is within size limits.

    Args:
        content: The content to validate.

    Raises:
        ValidationError: If the content is too large.
    """
    content_bytes = len(content.encode("utf-8"))
    if content_bytes > MAX_CONTENT_BYTES:
        raise ValidationError(
            f"Content too large: {content_bytes} bytes (max {MAX_CONTENT_BYTES})",
            "Reduce content size or split into multiple memories",
        )


# =============================================================================
# CaptureService
# =============================================================================


class CaptureService:
    """Service for capturing memories to git notes with indexing.

    Orchestrates memory capture with concurrency safety, validation,
    and graceful degradation. Memories are stored in git notes and
    optionally indexed for semantic search.

    Attributes:
        git_ops: GitOps instance for git note operations.
        index_service: IndexService for search indexing (optional).
        embedding_service: EmbeddingService for embeddings (optional).

    Examples:
        >>> service = CaptureService()
        >>> result = service.capture(
        ...     namespace="decisions",
        ...     summary="Use PostgreSQL for data storage",
        ...     content="## Context\\n\\nWe need a database...",
        ...     spec="my-project",
        ... )
        >>> result.success
        True
    """

    def __init__(
        self,
        git_ops: GitOps | None = None,
        index_service: IndexService | None = None,
        embedding_service: EmbeddingService | None = None,
        secrets_service: SecretsFilteringService | None = None,
        repo_path: Path | None = None,
    ) -> None:
        """Initialize the capture service.

        Args:
            git_ops: GitOps instance for git operations. If None, creates
                one for the given repo_path or current directory.
            index_service: IndexService for indexing. If None, memories
                are captured but not indexed.
            embedding_service: EmbeddingService for embeddings. If None,
                memories are indexed without embeddings.
            secrets_service: SecretsFilteringService for filtering sensitive
                data. If None, content is captured without filtering.
            repo_path: Path to the git repository. Only used if git_ops
                is None.
        """
        self._git_ops = git_ops
        self._index_service = index_service
        self._embedding_service = embedding_service
        self._secrets_service: SecretsFilteringService | None = secrets_service
        self._repo_path = repo_path
        self._lock_path = get_lock_path()

    @property
    def git_ops(self) -> GitOps:
        """Get the GitOps instance, creating one if needed."""
        if self._git_ops is None:
            self._git_ops = GitOps(repo_path=self._repo_path)
        return self._git_ops

    @property
    def index_service(self) -> IndexService | None:
        """Get the IndexService instance."""
        return self._index_service

    @property
    def embedding_service(self) -> EmbeddingService | None:
        """Get the EmbeddingService instance."""
        return self._embedding_service

    def set_index_service(self, service: IndexService) -> None:
        """Set the index service after initialization.

        Useful for lazy initialization or dependency injection.
        """
        self._index_service = service

    def set_embedding_service(self, service: EmbeddingService) -> None:
        """Set the embedding service after initialization.

        Useful for lazy initialization or dependency injection.
        """
        self._embedding_service = service

    @property
    def secrets_service(self) -> SecretsFilteringService | None:
        """Get the SecretsFilteringService instance."""
        return self._secrets_service

    def set_secrets_service(self, service: SecretsFilteringService) -> None:
        """Set the secrets filtering service after initialization.

        Useful for lazy initialization or dependency injection.
        """
        self._secrets_service = service

    # =========================================================================
    # Input Validation (extracted for ARCH-007)
    # =========================================================================

    def _validate_capture_input(
        self,
        namespace: str,
        summary: str,
        content: str,
    ) -> None:
        """Validate all capture input parameters.

        Args:
            namespace: Memory type to validate.
            summary: One-line summary to validate.
            content: Full content to validate.

        Raises:
            ValidationError: If any validation fails.
        """
        _validate_namespace(namespace)
        _validate_summary(summary)
        _validate_content(content)

    def _filter_content(
        self,
        summary: str,
        content: str,
        namespace: str,
    ) -> tuple[str, str, list[str]]:
        """Filter secrets from summary and content.

        Applies secrets filtering if a SecretsFilteringService is configured.
        Raises BlockedContentError if content contains blocked secrets.

        Args:
            summary: The one-line summary to filter.
            content: The full content to filter.
            namespace: Memory namespace for allowlist scoping.

        Returns:
            Tuple of (filtered_summary, filtered_content, warnings).

        Raises:
            BlockedContentError: If BLOCK strategy is configured and secrets found.
        """
        if self._secrets_service is None or not self._secrets_service.enabled:
            return summary, content, []

        warnings: list[str] = []

        # Filter summary
        summary_result = self._secrets_service.filter(
            summary,
            source="capture_summary",
            namespace=namespace,
        )
        filtered_summary = summary_result.content
        if summary_result.warnings:
            warnings.extend(summary_result.warnings)
        if summary_result.had_secrets:
            warnings.append(
                f"Summary contained {summary_result.detection_count} secret(s), redacted"
            )

        # Filter content
        content_result = self._secrets_service.filter(
            content,
            source="capture_content",
            namespace=namespace,
        )
        filtered_content = content_result.content
        if content_result.warnings:
            warnings.extend(content_result.warnings)
        if content_result.had_secrets:
            warnings.append(
                f"Content contained {content_result.detection_count} secret(s), redacted"
            )

        return filtered_summary, filtered_content, warnings

    def _build_front_matter(
        self,
        namespace: str,
        summary: str,
        timestamp: datetime,
        spec: str | None,
        phase: str | None,
        tags: tuple[str, ...],
        status: str,
        relates_to: tuple[str, ...],
    ) -> dict[str, object]:
        """Build the YAML front matter dictionary.

        Args:
            namespace: Memory type.
            summary: One-line summary.
            timestamp: Capture timestamp.
            spec: Optional specification slug.
            phase: Optional lifecycle phase.
            tags: Categorization tags.
            status: Memory status.
            relates_to: Related memory IDs.

        Returns:
            Dictionary ready for YAML serialization.
        """
        front_matter: dict[str, object] = {
            "type": namespace,
            "timestamp": timestamp.isoformat(),
            "summary": summary,
        }

        if spec:
            front_matter["spec"] = spec
        if phase:
            front_matter["phase"] = phase
        if tags:
            front_matter["tags"] = list(tags)
        if status != "active":
            front_matter["status"] = status
        if relates_to:
            front_matter["relates_to"] = list(relates_to)

        return front_matter

    # =========================================================================
    # Core Capture Method
    # =========================================================================

    @measure_duration("memory_capture")
    def capture(
        self,
        namespace: str,
        summary: str,
        content: str,
        *,
        spec: str | None = None,
        tags: list[str] | tuple[str, ...] | None = None,
        phase: str | None = None,
        status: str = "active",
        relates_to: list[str] | tuple[str, ...] | None = None,
        commit: str = "HEAD",
        skip_lock: bool = False,
    ) -> CaptureResult:
        """Capture a memory to git notes with optional indexing.

        The core capture method that validates input, writes to git notes,
        and optionally indexes the memory for semantic search.

        Args:
            namespace: Memory type (decisions, learnings, blockers, etc.)
            summary: One-line summary (max 100 characters)
            content: Full markdown content
            spec: Specification slug this memory belongs to
            tags: Categorization tags
            phase: Lifecycle phase (planning, implementation, review, etc.)
            status: Memory status (active, resolved, archived)
            relates_to: IDs of related memories
            commit: Git commit to attach the note to (default HEAD)
            skip_lock: Skip file locking (use with caution)

        Returns:
            CaptureResult with success status and captured memory.

        Raises:
            ValidationError: If input validation fails.
            CaptureError: If the capture operation fails.
            GitError: If git operations fail.

        Examples:
            >>> result = service.capture(
            ...     namespace="decisions",
            ...     summary="Use REST over GraphQL",
            ...     content="## Context\\n\\nSimplicity wins.",
            ...     spec="my-api",
            ...     tags=["api", "architecture"],
            ... )
            >>> result.success
            True
        """
        # Validate input (extracted method for ARCH-007)
        self._validate_capture_input(namespace, summary, content)

        # Filter secrets from summary and content
        # This may raise BlockedContentError if BLOCK strategy is configured
        filtered_summary, filtered_content, filter_warnings = self._filter_content(
            summary, content, namespace
        )

        # Normalize tags
        tags_tuple = tuple(tags) if tags else ()
        relates_tuple = tuple(relates_to) if relates_to else ()

        # Get current timestamp
        timestamp = datetime.now(UTC)

        # Build front matter (extracted method for ARCH-007)
        # Use filtered_summary in front matter
        front_matter = self._build_front_matter(
            namespace=namespace,
            summary=filtered_summary,
            timestamp=timestamp,
            spec=spec,
            phase=phase,
            tags=tags_tuple,
            status=status,
            relates_to=relates_tuple,
        )

        # Serialize to YAML front matter format
        # Use filtered_content in note body
        note_content = serialize_note(front_matter, filtered_content)

        # Capture with or without locking
        if skip_lock:
            return self._do_capture(
                namespace=namespace,
                summary=filtered_summary,
                content=filtered_content,
                note_content=note_content,
                timestamp=timestamp,
                spec=spec,
                phase=phase,
                tags=tags_tuple,
                status=status,
                relates_to=relates_tuple,
                commit=commit,
                filter_warnings=filter_warnings,
            )

        with _acquire_lock(self._lock_path):
            return self._do_capture(
                namespace=namespace,
                summary=filtered_summary,
                content=filtered_content,
                note_content=note_content,
                timestamp=timestamp,
                spec=spec,
                phase=phase,
                tags=tags_tuple,
                status=status,
                relates_to=relates_tuple,
                commit=commit,
                filter_warnings=filter_warnings,
            )

    def _do_capture(
        self,
        *,
        namespace: str,
        summary: str,
        content: str,
        note_content: str,
        timestamp: datetime,
        spec: str | None,
        phase: str | None,
        tags: tuple[str, ...],
        status: str,
        relates_to: tuple[str, ...],
        commit: str,
        filter_warnings: list[str] | None = None,
    ) -> CaptureResult:
        """Execute the capture operation (called within lock).

        Internal method that performs the actual capture work.

        Args:
            filter_warnings: Optional list of warnings from secrets filtering.
        """
        metrics = get_metrics()

        with trace_operation("capture", labels={"namespace": namespace}):
            # Resolve commit SHA
            with trace_operation("capture.resolve_commit"):
                try:
                    commit_info = self.git_ops.get_commit_info(commit)
                    commit_sha = commit_info.sha
                except Exception as e:
                    raise CaptureError(
                        f"Failed to resolve commit '{commit}': {e}",
                        "Ensure you're in a git repository with valid commits",
                    ) from e

            # Determine note index (count existing notes by "---" pairs)
            with trace_operation("capture.count_existing"):
                try:
                    existing_note = self.git_ops.show_note(namespace, commit_sha)
                    index = (
                        existing_note.count("\n---\n") // 2 + 1 if existing_note else 0
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to count existing notes for %s:%s: %s",
                        namespace,
                        commit_sha[:8],
                        e,
                    )
                    metrics.increment(
                        "silent_failures_total",
                        labels={"location": "capture.count_existing"},
                    )
                    index = 0

            # Build memory ID
            memory_id = f"{namespace}:{commit_sha}:{index}"

            # Write to git notes (append for safety)
            with trace_operation("capture.git_append"):
                try:
                    self.git_ops.append_note(namespace, note_content, commit_sha)
                    logger.info("Captured memory: %s", memory_id)
                except Exception as e:
                    raise CaptureError(
                        f"Failed to write git note: {e}",
                        "Check git repository status and permissions",
                    ) from e

            # Create Memory object
            memory = Memory(
                id=memory_id,
                commit_sha=commit_sha,
                namespace=namespace,
                summary=summary,
                content=content,
                timestamp=timestamp,
                spec=spec,
                phase=phase,
                tags=tags,
                status=status,
                relates_to=relates_to,
            )

            # Try to index (graceful degradation)
            # Initialize warnings list with any filter warnings from secrets filtering
            indexed = False
            warnings: list[str] = list(filter_warnings) if filter_warnings else []

            if self._index_service is not None:
                with trace_operation("capture.index"):
                    try:
                        # Generate embedding if service available
                        embedding: list[float] | None = None
                        if self._embedding_service is not None:
                            with trace_operation("capture.embed"):
                                try:
                                    # Combine summary and content for embedding
                                    embed_text = f"{summary}\n\n{content}"
                                    embedding = self._embedding_service.embed(
                                        embed_text
                                    )
                                except Exception as e:
                                    warnings.append(f"Embedding failed: {e}")
                                    logger.warning("Embedding generation failed: %s", e)

                        # Insert into index
                        self._index_service.insert(memory, embedding)
                        indexed = True
                        logger.debug("Indexed memory: %s", memory_id)

                    except Exception as e:
                        warnings.append(f"Indexing failed: {e}")
                        logger.warning("Indexing failed for %s: %s", memory_id, e)

            # Increment counter on successful capture
            metrics.increment(
                "memories_captured_total",
                labels={"namespace": namespace},
            )

            # Combine all warnings into a single string (or None if no warnings)
            combined_warning = "; ".join(warnings) if warnings else None

            return CaptureResult(
                success=True,
                memory=memory,
                indexed=indexed,
                warning=combined_warning,
            )

    # =========================================================================
    # Convenience Capture Methods
    # =========================================================================

    def capture_decision(
        self,
        spec: str,
        summary: str,
        context: str,
        rationale: str,
        alternatives: list[str] | None = None,
        *,
        tags: list[str] | None = None,
        phase: str | None = None,
        commit: str = "HEAD",
    ) -> CaptureResult:
        """Capture a decision memory.

        Structured capture for architectural and design decisions.

        Args:
            spec: Specification this decision belongs to.
            summary: One-line summary of the decision.
            context: Background context for the decision.
            rationale: Why this decision was made.
            alternatives: Alternatives that were considered.
            tags: Categorization tags.
            phase: Lifecycle phase.
            commit: Git commit to attach to.

        Returns:
            CaptureResult with the captured decision.

        Examples:
            >>> result = service.capture_decision(
            ...     spec="my-project",
            ...     summary="Use PostgreSQL for data storage",
            ...     context="We need a reliable database for production.",
            ...     rationale="Strong ACID compliance and JSON support.",
            ...     alternatives=["MySQL", "MongoDB"],
            ... )
        """
        # Build structured content
        content_parts = [
            "## Context",
            "",
            context,
            "",
            "## Decision",
            "",
            summary,
            "",
            "## Rationale",
            "",
            rationale,
        ]

        if alternatives:
            content_parts.extend(
                [
                    "",
                    "## Alternatives Considered",
                    "",
                ]
            )
            for alt in alternatives:
                content_parts.append(f"- {alt}")

        content = "\n".join(content_parts)

        return self.capture(
            namespace="decisions",
            summary=summary,
            content=content,
            spec=spec,
            tags=tags,
            phase=phase,
            commit=commit,
        )

    def capture_blocker(
        self,
        spec: str,
        summary: str,
        description: str,
        impact: str | None = None,
        *,
        tags: list[str] | None = None,
        phase: str | None = None,
        commit: str = "HEAD",
    ) -> CaptureResult:
        """Capture a blocker memory.

        Records an impediment that is blocking progress.

        Args:
            spec: Specification this blocker affects.
            summary: One-line summary of the blocker.
            description: Detailed description of the blocker.
            impact: How this blocker impacts progress.
            tags: Categorization tags.
            phase: Lifecycle phase.
            commit: Git commit to attach to.

        Returns:
            CaptureResult with the captured blocker.
        """
        content_parts = [
            "## Description",
            "",
            description,
        ]

        if impact:
            content_parts.extend(
                [
                    "",
                    "## Impact",
                    "",
                    impact,
                ]
            )

        content = "\n".join(content_parts)

        return self.capture(
            namespace="blockers",
            summary=summary,
            content=content,
            spec=spec,
            tags=tags,
            phase=phase,
            status="active",
            commit=commit,
        )

    def resolve_blocker(
        self,
        memory_id: str,
        resolution: str,
        *,
        tags: list[str] | None = None,
        commit: str = "HEAD",
    ) -> CaptureResult:
        """Resolve an existing blocker.

        Creates a new memory documenting the resolution and linking
        to the original blocker.

        Args:
            memory_id: ID of the blocker to resolve.
            resolution: How the blocker was resolved.
            tags: Additional tags for the resolution.
            commit: Git commit to attach to.

        Returns:
            CaptureResult with the resolution memory.
        """
        # Parse the memory ID to extract namespace and spec
        parts = memory_id.split(":")
        if len(parts) < 3 or parts[0] != "blockers":
            raise ValidationError(
                f"Invalid blocker memory ID: '{memory_id}'",
                "Memory ID must be in format blockers:<commit>:<index>",
            )

        content = f"## Resolution\n\n{resolution}"

        return self.capture(
            namespace="blockers",
            summary=f"Resolved: {memory_id}",
            content=content,
            tags=tags,
            status="resolved",
            relates_to=[memory_id],
            commit=commit,
        )

    def capture_learning(
        self,
        summary: str,
        insight: str,
        context: str | None = None,
        *,
        spec: str | None = None,
        tags: list[str] | None = None,
        commit: str = "HEAD",
    ) -> CaptureResult:
        """Capture a learning memory.

        Records insights and lessons learned.

        Args:
            summary: One-line summary of the learning.
            insight: The key insight or lesson.
            context: Background context for the learning.
            spec: Optional specification this relates to.
            tags: Categorization tags.
            commit: Git commit to attach to.

        Returns:
            CaptureResult with the captured learning.
        """
        content_parts = [
            "## Insight",
            "",
            insight,
        ]

        if context:
            content_parts.extend(
                [
                    "",
                    "## Context",
                    "",
                    context,
                ]
            )

        content = "\n".join(content_parts)

        return self.capture(
            namespace="learnings",
            summary=summary,
            content=content,
            spec=spec,
            tags=tags,
            commit=commit,
        )

    def capture_progress(
        self,
        spec: str,
        summary: str,
        milestone: str,
        *,
        details: str | None = None,
        tags: list[str] | None = None,
        phase: str | None = None,
        commit: str = "HEAD",
    ) -> CaptureResult:
        """Capture a progress memory.

        Records project milestones and progress updates.

        Args:
            spec: Specification this progress belongs to.
            summary: One-line summary of the progress.
            milestone: Description of the milestone reached.
            details: Additional details about the progress.
            tags: Categorization tags.
            phase: Lifecycle phase.
            commit: Git commit to attach to.

        Returns:
            CaptureResult with the captured progress.
        """
        content_parts = [
            "## Milestone",
            "",
            milestone,
        ]

        if details:
            content_parts.extend(
                [
                    "",
                    "## Details",
                    "",
                    details,
                ]
            )

        content = "\n".join(content_parts)

        return self.capture(
            namespace="progress",
            summary=summary,
            content=content,
            spec=spec,
            tags=tags,
            phase=phase,
            commit=commit,
        )

    def capture_retrospective(
        self,
        spec: str,
        summary: str,
        content: str,
        outcome: str | None = None,
        *,
        tags: list[str] | None = None,
        commit: str = "HEAD",
    ) -> CaptureResult:
        """Capture a retrospective memory.

        Records project retrospectives and post-mortems.

        Args:
            spec: Specification this retrospective is for.
            summary: One-line summary.
            content: Full retrospective content.
            outcome: Outcome summary (success, partial, failed).
            tags: Categorization tags.
            commit: Git commit to attach to.

        Returns:
            CaptureResult with the captured retrospective.
        """
        full_tags = list(tags) if tags else []
        if outcome and outcome not in full_tags:
            full_tags.append(f"outcome:{outcome}")

        return self.capture(
            namespace="retrospective",
            summary=summary,
            content=content,
            spec=spec,
            tags=full_tags,
            phase="completed",
            commit=commit,
        )

    def capture_pattern(
        self,
        summary: str,
        pattern_type: str,
        evidence: str,
        confidence: float = 0.5,
        *,
        tags: list[str] | None = None,
        commit: str = "HEAD",
    ) -> CaptureResult:
        """Capture a pattern memory.

        Records recurring patterns observed across the codebase.

        Args:
            summary: One-line summary of the pattern.
            pattern_type: Type of pattern (success, anti-pattern, workflow, etc.)
            evidence: Evidence supporting this pattern.
            confidence: Confidence score (0.0 to 1.0).
            tags: Categorization tags.
            commit: Git commit to attach to.

        Returns:
            CaptureResult with the captured pattern.
        """
        if not 0.0 <= confidence <= 1.0:
            raise ValidationError(
                f"Confidence must be between 0.0 and 1.0, got {confidence}",
                "Provide a confidence value between 0.0 and 1.0",
            )

        content = f"## Pattern Type\n\n{pattern_type}\n\n## Evidence\n\n{evidence}\n\n## Confidence\n\n{confidence:.2f}"

        full_tags = list(tags) if tags else []
        full_tags.append(f"pattern:{pattern_type}")

        return self.capture(
            namespace="patterns",
            summary=summary,
            content=content,
            tags=full_tags,
            status="candidate",
            commit=commit,
        )

    def capture_review(
        self,
        spec: str,
        summary: str,
        findings: str,
        *,
        verdict: str | None = None,
        tags: list[str] | None = None,
        commit: str = "HEAD",
    ) -> CaptureResult:
        """Capture a review memory.

        Records code review or design review findings.

        Args:
            spec: Specification being reviewed.
            summary: One-line summary of the review.
            findings: Review findings and feedback.
            verdict: Overall verdict (approved, needs-work, rejected).
            tags: Categorization tags.
            commit: Git commit to attach to.

        Returns:
            CaptureResult with the captured review.
        """
        content_parts = [
            "## Findings",
            "",
            findings,
        ]

        if verdict:
            content_parts.extend(
                [
                    "",
                    "## Verdict",
                    "",
                    verdict,
                ]
            )

        content = "\n".join(content_parts)

        full_tags = list(tags) if tags else []
        if verdict and verdict not in full_tags:
            full_tags.append(f"verdict:{verdict}")

        return self.capture(
            namespace="reviews",
            summary=summary,
            content=content,
            spec=spec,
            tags=full_tags,
            commit=commit,
        )


# =============================================================================
# Singleton Access (using ServiceRegistry)
# =============================================================================


def get_default_service() -> CaptureService:
    """Get the default capture service singleton.

    Returns:
        The default CaptureService instance.

    Note:
        The default service is created without index or embedding services.
        Use set_index_service() and set_embedding_service() to enable
        these features after getting the default service.
    """
    from git_notes_memory.registry import ServiceRegistry

    service = ServiceRegistry.get(CaptureService)

    # Ensure git notes sync is configured on first use (best effort)
    try:
        service.git_ops.ensure_sync_configured()
    except Exception as e:
        logger.debug("Git notes sync auto-configuration skipped: %s", e)

    return service
