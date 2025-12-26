"""Data models for the secrets filtering system.

These dataclasses define the core domain objects for secrets detection and filtering.
All models are immutable (frozen) to ensure thread-safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

__all__ = [
    # Enums
    "SecretType",
    "FilterStrategy",
    "FilterAction",
    # Models
    "SecretDetection",
    "FilterResult",
    "AllowlistEntry",
    "AuditEntry",
]


# =============================================================================
# Enums
# =============================================================================


class SecretType(Enum):
    """Types of secrets that can be detected.

    Maps to detect-secrets plugin types and custom PII patterns.
    """

    # API Keys & Tokens (detect-secrets)
    AWS_ACCESS_KEY = "aws_access_key"
    AWS_SECRET_KEY = "aws_secret_key"  # noqa: S105
    GITHUB_TOKEN = "github_token"  # noqa: S105
    SLACK_TOKEN = "slack_token"  # noqa: S105
    STRIPE_KEY = "stripe_key"
    TWILIO_KEY = "twilio_key"
    MAILCHIMP_KEY = "mailchimp_key"
    SENDGRID_KEY = "sendgrid_key"
    CLOUDANT_KEY = "cloudant_key"
    DISCORD_TOKEN = "discord_token"  # noqa: S105
    AZURE_KEY = "azure_key"
    BASIC_AUTH = "basic_auth"
    JWT_TOKEN = "jwt_token"  # noqa: S105
    GENERIC_API_KEY = "generic_api_key"

    # Private Keys (detect-secrets)
    PRIVATE_KEY = "private_key"

    # High Entropy (detect-secrets)
    HIGH_ENTROPY_BASE64 = "high_entropy_base64"
    HIGH_ENTROPY_HEX = "high_entropy_hex"

    # PII (custom patterns)
    PII_SSN = "pii_ssn"
    PII_CREDIT_CARD = "pii_credit_card"
    PII_PHONE = "pii_phone"

    # Password patterns
    PASSWORD = "password"  # noqa: S105

    # Connection strings
    CONNECTION_STRING = "connection_string"

    # Generic/Unknown
    UNKNOWN = "unknown"


class FilterStrategy(Enum):
    """Strategies for handling detected secrets.

    Each strategy defines how to handle content when a secret is detected:
    - REDACT: Replace secret with [REDACTED:{type}] placeholder
    - MASK: Show first/last 4 characters, mask the middle
    - BLOCK: Reject the content entirely, raise BlockedContentError
    - WARN: Log a warning but allow content through unchanged
    """

    REDACT = "redact"
    MASK = "mask"
    BLOCK = "block"
    WARN = "warn"


class FilterAction(Enum):
    """Actions taken on content by the filtering system.

    Records what action was actually performed:
    - REDACTED: Secret was replaced with placeholder
    - MASKED: Secret was partially obscured
    - BLOCKED: Content was rejected
    - WARNED: Warning was logged, content passed through
    - ALLOWED: No secrets detected or content was in allowlist
    """

    REDACTED = "redacted"
    MASKED = "masked"
    BLOCKED = "blocked"
    WARNED = "warned"
    ALLOWED = "allowed"


# =============================================================================
# Detection Models
# =============================================================================


@dataclass(frozen=True)
class SecretDetection:
    """A detected secret in content.

    Represents a single secret found by the detection layer.

    Attributes:
        secret_type: Type of secret detected
        start: Start position in the content (character index)
        end: End position in the content (character index)
        confidence: Detection confidence (0.0 - 1.0)
        detector: Name of the detector that found this (e.g., "AWSKeyDetector")
        line_number: Line number where secret was found (1-indexed, if available)
        secret_hash: SHA-256 hash of the secret value (for allowlist matching)
    """

    secret_type: SecretType
    start: int
    end: int
    confidence: float = 1.0
    detector: str = ""
    line_number: int | None = None
    secret_hash: str = ""

    @property
    def length(self) -> int:
        """Get the length of the detected secret."""
        return self.end - self.start


@dataclass(frozen=True)
class FilterResult:
    """Result of filtering content for secrets.

    Contains the processed content and metadata about the filtering operation.

    Attributes:
        content: The filtered content (may be modified if secrets were redacted/masked)
        action: The action that was taken
        detections: All secrets detected in the original content
        original_length: Length of the original content
        filtered_length: Length of the filtered content
        warnings: Any warnings generated during filtering
    """

    content: str
    action: FilterAction
    detections: tuple[SecretDetection, ...] = field(default_factory=tuple)
    original_length: int = 0
    filtered_length: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def had_secrets(self) -> bool:
        """Check if any secrets were detected."""
        return len(self.detections) > 0

    @property
    def detection_count(self) -> int:
        """Get the number of secrets detected."""
        return len(self.detections)

    @property
    def by_type(self) -> dict[SecretType, list[SecretDetection]]:
        """Group detections by secret type."""
        result: dict[SecretType, list[SecretDetection]] = {}
        for detection in self.detections:
            if detection.secret_type not in result:
                result[detection.secret_type] = []
            result[detection.secret_type].append(detection)
        return result


# =============================================================================
# Allowlist Models
# =============================================================================


@dataclass(frozen=True)
class AllowlistEntry:
    """An allowlisted secret value.

    Stores the hash of a known-safe value to prevent false positives.

    Attributes:
        secret_hash: SHA-256 hash of the allowlisted value
        reason: Human-readable reason for allowlisting
        added_by: Who added this entry
        added_at: When the entry was added
        namespace: Optional namespace scope (None = global)
        expires_at: Optional expiration date
    """

    secret_hash: str
    reason: str
    added_by: str = "unknown"
    added_at: datetime | None = None
    namespace: str | None = None
    expires_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        if self.expires_at is None:
            return False
        from datetime import UTC

        return datetime.now(UTC) > self.expires_at


# =============================================================================
# Audit Models
# =============================================================================


@dataclass(frozen=True)
class AuditEntry:
    """Audit log entry for secrets filtering operations.

    Records all filtering events for compliance and debugging.

    Attributes:
        timestamp: When the event occurred
        event_type: Type of event (detection, allowlist_add, scan, etc.)
        namespace: Memory namespace being processed
        action: Action taken (FilterAction)
        detection_count: Number of secrets detected
        secret_types: Types of secrets found
        source: Source of the content (e.g., "capture", "scan")
        details: Additional details as key-value pairs
    """

    timestamp: datetime
    event_type: str
    namespace: str
    action: FilterAction
    detection_count: int = 0
    secret_types: tuple[SecretType, ...] = field(default_factory=tuple)
    source: str = ""
    details: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def details_dict(self) -> dict[str, str]:
        """Get details as a dictionary."""
        return dict(self.details)
