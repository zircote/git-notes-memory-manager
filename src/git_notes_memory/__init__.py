"""Git-native, semantically-searchable memory storage for Claude Code.

This package provides a memory capture and recall system that stores memories
as git notes with semantic search capabilities via sqlite-vec embeddings.

Example usage::

    from git_notes_memory import get_capture_service, get_recall_service

    # Capture a memory
    capture = get_capture_service()
    result = capture.capture(
        namespace="decisions",
        summary="Chose PostgreSQL for persistence",
        content="Evaluated SQLite vs PostgreSQL. PostgreSQL wins for concurrency.",
    )

    # Recall memories
    recall = get_recall_service()
    memories = recall.search("database choice", namespace="decisions", limit=5)
"""

from __future__ import annotations

__version__ = "0.12.0"

# Lazy imports to avoid loading embedding model at import time
__all__ = [
    "__version__",
    # Factory functions (lazy-loaded)
    "get_capture_service",
    "get_recall_service",
    "get_sync_service",
    "get_secrets_filtering_service",
    "is_auto_capture_enabled",
    # Models (always available)
    "Memory",
    "MemoryResult",
    "HydrationLevel",
    "HydratedMemory",
    "SpecContext",
    "IndexStats",
    "VerificationResult",
    "CaptureResult",
    "CaptureAccumulator",
    "Pattern",
    "PatternType",
    "PatternStatus",
    "CommitInfo",
    "NoteRecord",
    # Exceptions (always available)
    "MemoryError",
    "StorageError",
    "MemoryIndexError",
    "EmbeddingError",
    "ParseError",
    "CaptureError",
    "ValidationError",
]


def __getattr__(name: str) -> object:
    """Lazy loading of service factories and models.

    This prevents the embedding model from being loaded at import time,
    which would be slow and memory-intensive.
    """
    # Factory functions - load services lazily
    # Note: Internal modules use "get_default_service"; we expose cleaner names
    if name == "get_capture_service":
        from git_notes_memory.capture import get_default_service as get_capture_service

        return get_capture_service
    if name == "get_recall_service":
        from git_notes_memory.recall import get_default_service as get_recall_service

        return get_recall_service
    if name == "get_sync_service":
        from git_notes_memory.sync import get_sync_service

        return get_sync_service
    if name == "is_auto_capture_enabled":
        from git_notes_memory.config import is_auto_capture_enabled

        return is_auto_capture_enabled
    if name == "get_secrets_filtering_service":
        from git_notes_memory.security.service import (
            get_default_service as get_secrets_filtering_service,
        )

        return get_secrets_filtering_service

    # Models - these are lightweight, import directly
    if name in {
        "Memory",
        "MemoryResult",
        "HydrationLevel",
        "HydratedMemory",
        "SpecContext",
        "IndexStats",
        "VerificationResult",
        "CaptureResult",
        "CaptureAccumulator",
        "Pattern",
        "PatternType",
        "PatternStatus",
        "CommitInfo",
        "NoteRecord",
    }:
        from git_notes_memory import models

        return getattr(models, name)

    # Exceptions
    if name in {
        "MemoryError",
        "StorageError",
        "MemoryIndexError",
        "EmbeddingError",
        "ParseError",
        "CaptureError",
        "ValidationError",
    }:
        from git_notes_memory import exceptions

        return getattr(exceptions, name)

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
