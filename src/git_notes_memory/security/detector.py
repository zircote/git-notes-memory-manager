"""Adapter for the detect-secrets library.

Wraps Yelp's detect-secrets library to provide a consistent interface for
secret detection within the memory capture system.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from detect_secrets.core.scan import scan_line
from detect_secrets.settings import transient_settings

from git_notes_memory.registry import ServiceRegistry
from git_notes_memory.security.models import SecretDetection, SecretType

if TYPE_CHECKING:
    from detect_secrets.core.potential_secret import PotentialSecret

__all__ = [
    "DetectSecretsAdapter",
    "get_default_adapter",
]

# Mapping from detect-secrets plugin types to our SecretType enum
_TYPE_MAPPING: dict[str, SecretType] = {
    # AWS
    "AWS Access Key": SecretType.AWS_ACCESS_KEY,
    "AWS Secret Key": SecretType.AWS_SECRET_KEY,  # noqa: S105
    # GitHub
    "GitHub Token": SecretType.GITHUB_TOKEN,  # noqa: S105
    # Slack
    "Slack Token": SecretType.SLACK_TOKEN,  # noqa: S105
    # Stripe
    "Stripe Access Key": SecretType.STRIPE_KEY,
    # Twilio
    "Twilio API Key": SecretType.TWILIO_KEY,
    # Mailchimp
    "Mailchimp Access Key": SecretType.MAILCHIMP_KEY,
    # SendGrid
    "SendGrid API Key": SecretType.SENDGRID_KEY,
    # Cloudant
    "Cloudant Password": SecretType.CLOUDANT_KEY,  # noqa: S105
    # Discord
    "Discord Bot Token": SecretType.DISCORD_TOKEN,  # noqa: S105
    # Azure
    "Azure Storage Key": SecretType.AZURE_KEY,
    # Auth
    "Basic Auth Credentials": SecretType.BASIC_AUTH,
    "JSON Web Token": SecretType.JWT_TOKEN,  # noqa: S105
    # Private keys
    "Private Key": SecretType.PRIVATE_KEY,
    # High entropy
    "Base64 High Entropy String": SecretType.HIGH_ENTROPY_BASE64,
    "Hex High Entropy String": SecretType.HIGH_ENTROPY_HEX,
    # Generic
    "Secret Keyword": SecretType.PASSWORD,  # noqa: S105
    "Artifactory Credentials": SecretType.GENERIC_API_KEY,
    "IBM Cloud IAM Key": SecretType.GENERIC_API_KEY,
    "IBM COS HMAC Credentials": SecretType.GENERIC_API_KEY,
    "NPM Token": SecretType.GENERIC_API_KEY,  # noqa: S105
    "Softlayer Credentials": SecretType.GENERIC_API_KEY,
    "Square OAuth Secret": SecretType.GENERIC_API_KEY,  # noqa: S105
}


def _map_secret_type(detect_secrets_type: str) -> SecretType:
    """Map a detect-secrets type string to our SecretType enum.

    Args:
        detect_secrets_type: The type string from detect-secrets.

    Returns:
        The corresponding SecretType enum value.
    """
    return _TYPE_MAPPING.get(detect_secrets_type, SecretType.UNKNOWN)


def _hash_secret(secret_value: str) -> str:
    """Create a SHA-256 hash of a secret value.

    Used for allowlist matching without storing the actual secret.

    Args:
        secret_value: The raw secret value.

    Returns:
        Hexadecimal SHA-256 hash.
    """
    return hashlib.sha256(secret_value.encode()).hexdigest()


class DetectSecretsAdapter:
    """Adapter wrapping the detect-secrets library.

    Provides a consistent interface for detecting secrets in text content,
    mapping detect-secrets results to our SecretDetection model.

    Example usage::

        adapter = DetectSecretsAdapter()
        detections = adapter.detect("aws_key = AKIAIOSFODNN7EXAMPLE")
        for d in detections:
            print(f"Found {d.secret_type} at {d.start}-{d.end}")
    """

    def __init__(
        self,
        disabled_plugins: tuple[str, ...] = (),
        entropy_limit: float = 4.5,
    ) -> None:
        """Initialize the adapter.

        Args:
            disabled_plugins: Plugin class names to disable.
            entropy_limit: Minimum entropy threshold for high-entropy detection.
                          Default 4.5 is a balance between catching real secrets
                          and avoiding false positives on normal words.
        """
        self._disabled_plugins = disabled_plugins
        self._entropy_limit = entropy_limit

    def detect(self, content: str) -> tuple[SecretDetection, ...]:
        """Detect secrets in content.

        Scans the content line by line using detect-secrets plugins.

        Args:
            content: The text content to scan.

        Returns:
            Tuple of SecretDetection objects for found secrets.
        """
        if not content:
            return ()

        detections: list[SecretDetection] = []
        lines = content.splitlines(keepends=True)
        line_offset = 0

        # Configure settings for this scan
        settings = self._build_settings()

        for line_num, line in enumerate(lines, start=1):
            if not line.strip():
                line_offset += len(line)
                continue

            # Scan the line
            secrets = self._scan_line(line, settings)

            for secret in secrets:
                # Get position within the line
                secret_value = secret.secret_value or ""
                start_in_line = line.find(secret_value)
                if start_in_line == -1:
                    # Fallback: use 0 if we can't find the exact position
                    start_in_line = 0

                detection = SecretDetection(
                    secret_type=_map_secret_type(secret.type),
                    start=line_offset + start_in_line,
                    end=line_offset + start_in_line + len(secret_value),
                    confidence=1.0,  # detect-secrets doesn't provide confidence
                    detector=secret.type,
                    line_number=line_num,
                    secret_hash=_hash_secret(secret_value) if secret_value else "",
                )
                detections.append(detection)

            line_offset += len(line)

        # Deduplicate overlapping detections (same position, different types)
        return self._deduplicate(tuple(detections))

    def _build_settings(self) -> dict[str, object]:
        """Build settings dict for detect-secrets.

        Returns:
            Settings dictionary for configure_settings_from_baseline.
        """
        # Build plugins list with our configuration
        plugins: list[dict[str, object]] = []

        # Standard plugins
        plugin_names = [
            "AWSKeyDetector",
            "ArtifactoryDetector",
            "AzureStorageKeyDetector",
            "BasicAuthDetector",
            "CloudantDetector",
            "DiscordBotTokenDetector",
            "GitHubTokenDetector",
            "IbmCloudIamDetector",
            "IbmCosHmacDetector",
            "JwtTokenDetector",
            "MailchimpDetector",
            "NpmDetector",
            "PrivateKeyDetector",
            "SendGridDetector",
            "SlackDetector",
            "SoftlayerDetector",
            "SquareOAuthDetector",
            "StripeDetector",
            "TwilioKeyDetector",
        ]

        for name in plugin_names:
            if name not in self._disabled_plugins:
                plugins.append({"name": name})

        # High entropy plugins with configurable limit
        if "Base64HighEntropyString" not in self._disabled_plugins:
            plugins.append(
                {"name": "Base64HighEntropyString", "limit": self._entropy_limit}
            )
        if "HexHighEntropyString" not in self._disabled_plugins:
            plugins.append(
                {"name": "HexHighEntropyString", "limit": self._entropy_limit}
            )

        # Keyword detector for passwords
        if "KeywordDetector" not in self._disabled_plugins:
            plugins.append({"name": "KeywordDetector"})

        return {
            "plugins_used": plugins,
            "filters_used": [],
        }

    def _scan_line(
        self,
        line: str,
        settings: dict[str, object],
    ) -> list[PotentialSecret]:
        """Scan a single line for secrets.

        Args:
            line: The line to scan.
            settings: detect-secrets settings.

        Returns:
            List of PotentialSecret objects found.
        """
        # Use transient_settings to apply our custom plugin configuration
        with transient_settings(settings):
            return list(scan_line(line))

    def _deduplicate(
        self,
        detections: tuple[SecretDetection, ...],
    ) -> tuple[SecretDetection, ...]:
        """Remove duplicate detections at the same position.

        When multiple detectors find the same string (e.g., AWS key triggers
        both AWS detector and entropy detector), keep the more specific one.

        Args:
            detections: All detections found.

        Returns:
            Deduplicated detections.
        """
        if len(detections) <= 1:
            return detections

        # Group by position
        by_position: dict[tuple[int, int], list[SecretDetection]] = {}
        for d in detections:
            key = (d.start, d.end)
            if key not in by_position:
                by_position[key] = []
            by_position[key].append(d)

        # For each position, prefer specific types over entropy
        result: list[SecretDetection] = []
        for position_detections in by_position.values():
            if len(position_detections) == 1:
                result.append(position_detections[0])
            else:
                # Prefer non-entropy types
                non_entropy = [
                    d
                    for d in position_detections
                    if d.secret_type
                    not in (SecretType.HIGH_ENTROPY_BASE64, SecretType.HIGH_ENTROPY_HEX)
                ]
                if non_entropy:
                    result.append(non_entropy[0])
                else:
                    result.append(position_detections[0])

        # Sort by position for consistent output
        result.sort(key=lambda d: (d.start, d.end))
        return tuple(result)


def get_default_adapter(
    disabled_plugins: tuple[str, ...] = (),
) -> DetectSecretsAdapter:
    """Get the default DetectSecretsAdapter instance.

    Returns a singleton instance via ServiceRegistry with thread-safe
    double-checked locking.

    Args:
        disabled_plugins: Plugin class names to disable (only used on first call).

    Returns:
        The shared DetectSecretsAdapter instance.
    """
    if disabled_plugins:
        return ServiceRegistry.get(
            DetectSecretsAdapter, disabled_plugins=disabled_plugins
        )
    return ServiceRegistry.get(DetectSecretsAdapter)


def reset_adapter() -> None:
    """Reset the singleton adapter instance.

    Used for testing to ensure fresh instances.
    Note: Prefer ServiceRegistry.reset() to reset all services at once.
    """
    # ServiceRegistry.reset() handles this globally
    # This function is kept for backward compatibility
    pass
