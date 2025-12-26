"""Exception hierarchy for the memory capture system.

All exceptions include recovery suggestions per the design specification.
Each exception has:
- category: Error classification (ErrorCategory enum)
- message: Human-readable error description
- recovery_action: Suggested action to resolve the error
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    # Error Categories
    "ErrorCategory",
    # Exception Classes
    "MemoryPluginError",
    # Backward compatibility alias (deprecated - avoid using in new code)
    "MemoryError",
    "StorageError",
    "MemoryIndexError",
    "EmbeddingError",
    "ParseError",
    "CaptureError",
    "RecallError",
    "ValidationError",
    # Pre-defined Errors
    "NO_COMMITS_ERROR",
    "PERMISSION_DENIED_ERROR",
    "INDEX_LOCKED_ERROR",
    "SQLITE_VEC_MISSING_ERROR",
    "MODEL_OOM_ERROR",
    "MODEL_CORRUPTED_ERROR",
    "INVALID_YAML_ERROR",
    "MISSING_FIELD_ERROR",
    "LOCK_TIMEOUT_ERROR",
    "INVALID_NAMESPACE_ERROR",
    "CONTENT_TOO_LARGE_ERROR",
    "INVALID_GIT_REF_ERROR",
    "PATH_TRAVERSAL_ERROR",
]


# =============================================================================
# Error Categories
# =============================================================================


class ErrorCategory(Enum):
    """Categories of errors that can occur in the memory system.

    Used to group related errors and provide consistent error handling.
    """

    STORAGE = "storage"  # Git notes operations
    INDEX = "index"  # SQLite/sqlite-vec operations
    EMBEDDING = "embedding"  # Embedding generation
    PARSE = "parse"  # Note content parsing
    CAPTURE = "capture"  # Memory capture orchestration
    RECALL = "recall"  # Memory recall/retrieval
    VALIDATION = "validation"  # Input validation


# =============================================================================
# Base Exception
# =============================================================================


class MemoryPluginError(Exception):
    """Base exception for memory plugin errors.

    All exceptions include a category, message, and recovery action
    to help users understand and resolve issues.

    Note:
        Renamed from 'MemoryError' to avoid confusion with Python's builtin
        MemoryError (raised on OOM). The old name is kept as a deprecated alias.

    Attributes:
        category: Error category for grouping related errors.
        message: Human-readable error description.
        recovery_action: Suggested action to resolve the error.
    """

    def __init__(
        self,
        category: ErrorCategory,
        message: str,
        recovery_action: str,
    ) -> None:
        """Initialize a MemoryPluginError.

        Args:
            category: The error category.
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(message)
        self.category = category
        self.message = message
        self.recovery_action = recovery_action

    def __str__(self) -> str:
        """Format the error for display."""
        return f"[{self.category.value}] {self.message}\n-> {self.recovery_action}"


# Backward compatibility alias (deprecated - use MemoryPluginError in new code)
MemoryError = MemoryPluginError


# =============================================================================
# Specific Exception Classes
# =============================================================================


class StorageError(MemoryPluginError):
    """Git notes operation failed.

    Common causes:
    - No commits in repository
    - Permission denied
    - Invalid ref name
    - Merge conflicts
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize a StorageError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(ErrorCategory.STORAGE, message, recovery_action)


class MemoryIndexError(MemoryPluginError):
    """SQLite or sqlite-vec operation failed.

    Common causes:
    - Database locked by another process
    - Corrupted index file
    - sqlite-vec extension not found
    - Schema migration needed

    Note: Named MemoryIndexError to avoid shadowing Python's built-in IndexError.
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize a MemoryIndexError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(ErrorCategory.INDEX, message, recovery_action)


class EmbeddingError(MemoryPluginError):
    """Embedding generation failed.

    Common causes:
    - Insufficient memory for model
    - Corrupted model cache
    - Model download failed
    - CUDA/MPS device error
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize an EmbeddingError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(ErrorCategory.EMBEDDING, message, recovery_action)


class ParseError(MemoryPluginError):
    """Note content parsing failed.

    Common causes:
    - Invalid YAML front matter
    - Missing required fields
    - Invalid timestamp format
    - Malformed Markdown
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize a ParseError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(ErrorCategory.PARSE, message, recovery_action)


class CaptureError(MemoryPluginError):
    """Memory capture operation failed.

    Common causes:
    - Lock acquisition timeout
    - Concurrent capture in progress
    - Validation failure
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize a CaptureError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(ErrorCategory.CAPTURE, message, recovery_action)


class RecallError(MemoryPluginError):
    """Memory recall/retrieval operation failed.

    Common causes:
    - Search query failed
    - Hydration failed
    - Memory not found
    - Index unavailable
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize a RecallError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(ErrorCategory.RECALL, message, recovery_action)


class ValidationError(MemoryPluginError):
    """Input validation failed.

    Common causes:
    - Invalid namespace
    - Content exceeds size limit
    - Invalid git ref format
    - Path traversal attempt
    - Invalid timestamp format
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize a ValidationError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(ErrorCategory.VALIDATION, message, recovery_action)


# =============================================================================
# Pre-defined Common Errors
# =============================================================================

# Storage errors
NO_COMMITS_ERROR = StorageError(
    "Cannot capture memory: no commits exist in this repository",
    "Create at least one commit first: git commit --allow-empty -m 'initial'",
)

PERMISSION_DENIED_ERROR = StorageError(
    "Cannot write to Git notes: permission denied",
    "Check repository permissions and ensure you have write access",
)

# Index errors
INDEX_LOCKED_ERROR = MemoryIndexError(
    "Index database is locked by another process",
    "Wait for the other process to complete, or check for stuck processes",
)

SQLITE_VEC_MISSING_ERROR = MemoryIndexError(
    "sqlite-vec extension not found",
    "Install sqlite-vec: pip install sqlite-vec",
)

# Embedding errors
MODEL_OOM_ERROR = EmbeddingError(
    "Insufficient memory to load embedding model",
    "Close other applications or use a smaller model",
)

MODEL_CORRUPTED_ERROR = EmbeddingError(
    "Embedding model cache corrupted",
    "Delete the models/ directory and retry to re-download the model",
)

# Parse errors
INVALID_YAML_ERROR = ParseError(
    "Note contains invalid YAML front matter",
    "Check note format - YAML must be valid and enclosed in --- markers",
)

MISSING_FIELD_ERROR = ParseError(
    "Note missing required field",
    "Ensure note has: type, spec, timestamp, summary",
)

# Capture errors
LOCK_TIMEOUT_ERROR = CaptureError(
    "Another capture operation is in progress",
    "Wait and retry, or check for stuck processes",
)

# Validation errors
INVALID_NAMESPACE_ERROR = ValidationError(
    "Invalid memory namespace",
    "Use one of: inception, elicitation, research, decisions, progress, "
    "blockers, reviews, learnings, retrospective, patterns",
)

CONTENT_TOO_LARGE_ERROR = ValidationError(
    "Content exceeds maximum size limit (100KB)",
    "Reduce content size or split into multiple memories",
)

INVALID_GIT_REF_ERROR = ValidationError(
    "Invalid git reference format",
    "Git refs must not contain shell metacharacters or path traversal sequences",
)

PATH_TRAVERSAL_ERROR = ValidationError(
    "Path contains traversal sequences",
    "Paths must not contain '..' or other traversal patterns",
)
