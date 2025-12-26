"""Exception hierarchy for the secrets filtering system.

All exceptions include recovery suggestions following the project pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_notes_memory.exceptions import ErrorCategory, MemoryPluginError

if TYPE_CHECKING:
    from git_notes_memory.security.models import SecretDetection

__all__ = [
    # Exception Classes
    "SecretsFilteringError",
    "BlockedContentError",
    "AllowlistError",
    "AuditLogError",
    # Error Category
    "SECURITY",
]

# Add a new error category for security operations
SECURITY = ErrorCategory.VALIDATION  # Reuse validation for security errors


class SecretsFilteringError(MemoryPluginError):
    """Base exception for secrets filtering operations.

    Common causes:
    - Detection failed
    - Configuration error
    - Service initialization failed
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize a SecretsFilteringError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(SECURITY, message, recovery_action)


class BlockedContentError(SecretsFilteringError):
    """Content was blocked due to detected secrets.

    Raised when FilterStrategy.BLOCK is configured and secrets are found.
    Includes the list of detections for logging and user feedback.

    Attributes:
        detections: The secrets that caused the block.
    """

    def __init__(
        self,
        detections: tuple[SecretDetection, ...],
        message: str | None = None,
        recovery_action: str | None = None,
    ) -> None:
        """Initialize a BlockedContentError.

        Args:
            detections: The secrets that caused the content to be blocked.
            message: Optional custom message.
            recovery_action: Optional custom recovery action.
        """
        self.detections = detections

        # Build message from detections if not provided
        if message is None:
            types = {d.secret_type.value for d in detections}
            message = f"Content blocked: {len(detections)} secret(s) detected ({', '.join(sorted(types))})"

        if recovery_action is None:
            recovery_action = (
                "Remove the sensitive data or add values to the allowlist with "
                "/memory:secrets-allowlist add"
            )

        super().__init__(message, recovery_action)

    def __str__(self) -> str:
        """Format the error with detection details."""
        base = super().__str__()
        if self.detections:
            details: list[str] = []
            for d in self.detections:
                details.append(
                    f"  - {d.secret_type.value} at position {d.start}-{d.end}"
                )
            return f"{base}\nDetections:\n" + "\n".join(details)
        return base


class AllowlistError(SecretsFilteringError):
    """Allowlist operation failed.

    Common causes:
    - Invalid hash format
    - Entry not found
    - File permission error
    - Corrupt allowlist file
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize an AllowlistError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(message, recovery_action)


class AuditLogError(SecretsFilteringError):
    """Audit logging operation failed.

    Common causes:
    - Log file not writable
    - Disk full
    - Log rotation failed
    """

    def __init__(self, message: str, recovery_action: str) -> None:
        """Initialize an AuditLogError.

        Args:
            message: Human-readable error description.
            recovery_action: Suggested action to resolve the error.
        """
        super().__init__(message, recovery_action)
