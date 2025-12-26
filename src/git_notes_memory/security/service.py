"""Secrets filtering service - main orchestrator.

This module provides the SecretsFilteringService that coordinates detection,
allowlist checking, and redaction of sensitive content.

Note: Full implementation is in Phase 3. This is a minimal stub for Phase 1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_notes_memory.security.config import SecretsConfig, get_secrets_config
from git_notes_memory.security.models import (
    FilterAction,
    FilterResult,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "SecretsFilteringService",
    "get_default_service",
]

# Singleton instance
_service: SecretsFilteringService | None = None


class SecretsFilteringService:
    """Main service for secrets detection and filtering.

    Orchestrates:
    - Detection via DetectSecretsAdapter and PIIDetector
    - Allowlist checking via AllowlistManager
    - Content redaction via Redactor
    - Audit logging via AuditLogger

    Example usage::

        service = get_default_service()
        result = service.filter(content, source="memory", namespace="decisions")
        if result.had_secrets:
            print(f"Filtered {result.detection_count} secrets")
        filtered_content = result.content
    """

    def __init__(self, config: SecretsConfig | None = None) -> None:
        """Initialize the secrets filtering service.

        Args:
            config: Configuration for filtering. Uses defaults if not provided.
        """
        self._config = config or get_secrets_config()

    @property
    def config(self) -> SecretsConfig:
        """Get the current configuration."""
        return self._config

    @property
    def enabled(self) -> bool:
        """Check if secrets filtering is enabled."""
        return self._config.enabled

    def filter(
        self,
        content: str,
        source: str = "",
        namespace: str = "",
    ) -> FilterResult:
        """Filter content for secrets, applying configured strategy.

        Args:
            content: The content to filter.
            source: Source of the content (for audit logging).
            namespace: Memory namespace (for strategy selection).

        Returns:
            FilterResult with filtered content and detection metadata.

        Note:
            Full implementation in Phase 3. This stub returns content unchanged.
        """
        # Stub implementation - returns content unchanged
        # Full implementation will be added in Phase 3 (Task 3.5)
        _ = source, namespace  # Will be used in full implementation
        return FilterResult(
            content=content,
            action=FilterAction.ALLOWED,
            original_length=len(content),
            filtered_length=len(content),
        )

    def scan(
        self,
        content: str,
    ) -> FilterResult:
        """Scan content for secrets without modifying it.

        Args:
            content: The content to scan.

        Returns:
            FilterResult with detections but original content.

        Note:
            Full implementation in Phase 3. This stub returns no detections.
        """
        # Stub implementation - returns no detections
        # Full implementation will be added in Phase 3 (Task 3.5)
        return FilterResult(
            content=content,
            action=FilterAction.ALLOWED,
            original_length=len(content),
            filtered_length=len(content),
        )


def get_default_service(config: SecretsConfig | None = None) -> SecretsFilteringService:
    """Get the default secrets filtering service instance.

    Returns a singleton instance. Thread-safe for typical usage patterns.

    Args:
        config: Optional configuration override for first initialization.

    Returns:
        The shared SecretsFilteringService instance.
    """
    global _service
    if _service is None:
        _service = SecretsFilteringService(config=config)
    return _service


def reset_service() -> None:
    """Reset the singleton service instance.

    Used for testing to ensure fresh instances.
    """
    global _service
    _service = None
