"""Secrets filtering service - main orchestrator.

This module provides the SecretsFilteringService that coordinates detection,
allowlist checking, and redaction of sensitive content.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from git_notes_memory.registry import ServiceRegistry
from git_notes_memory.security.allowlist import AllowlistManager
from git_notes_memory.security.config import SecretsConfig, get_secrets_config
from git_notes_memory.security.detector import DetectSecretsAdapter
from git_notes_memory.security.models import (
    FilterAction,
    FilterResult,
    SecretDetection,
    SecretType,
)
from git_notes_memory.security.pii import PIIDetector
from git_notes_memory.security.redactor import Redactor

if TYPE_CHECKING:
    pass

__all__ = [
    "SecretsFilteringService",
    "get_default_service",
]

_logger = logging.getLogger(__name__)


class SecretsFilteringService:
    """Main service for secrets detection and filtering.

    Orchestrates:
    - Detection via DetectSecretsAdapter and PIIDetector
    - Allowlist checking via AllowlistManager
    - Content redaction via Redactor

    The filtering pipeline:
    1. Detect secrets using both detect-secrets and custom PII patterns
    2. Deduplicate overlapping detections
    3. Filter out allowlisted hashes
    4. Apply redaction strategy (REDACT/MASK/BLOCK/WARN)

    Example usage::

        service = get_default_service()
        result = service.filter(content, source="memory", namespace="decisions")
        if result.had_secrets:
            print(f"Filtered {result.detection_count} secrets")
        filtered_content = result.content
    """

    def __init__(
        self,
        config: SecretsConfig | None = None,
        data_dir: Path | None = None,
    ) -> None:
        """Initialize the secrets filtering service.

        Args:
            config: Configuration for filtering. Uses defaults if not provided.
            data_dir: Directory for allowlist files. Uses default if not provided.
        """
        self._config = config or get_secrets_config()

        # Initialize detectors
        self._secrets_detector = DetectSecretsAdapter(
            disabled_plugins=self._config.detectors_disabled,
        )
        self._pii_detector = PIIDetector()

        # Initialize allowlist manager
        self._allowlist = AllowlistManager(data_dir=data_dir)

        # Initialize redactor with strategy from config
        # Convert namespace_strategies (namespace -> strategy) to type overrides
        # Note: The config has namespace strategies, but the redactor uses type strategies
        # For now, use default strategy only - per-type overrides can be added later
        self._redactor = Redactor(
            default_strategy=self._config.default_strategy,
        )

    @property
    def config(self) -> SecretsConfig:
        """Get the current configuration."""
        return self._config

    @property
    def enabled(self) -> bool:
        """Check if secrets filtering is enabled."""
        return self._config.enabled

    @property
    def allowlist(self) -> AllowlistManager:
        """Get the allowlist manager."""
        return self._allowlist

    @property
    def redactor(self) -> Redactor:
        """Get the redactor."""
        return self._redactor

    def filter(
        self,
        content: str,
        source: str = "",
        namespace: str = "",
    ) -> FilterResult:
        """Filter content for secrets, applying configured strategy.

        This is the main entry point for content filtering. It:
        1. Detects all secrets in the content
        2. Filters out allowlisted hashes
        3. Applies the configured redaction strategy
        4. Returns the filtered content with metadata

        Args:
            content: The content to filter.
            source: Source of the content (for audit logging).
            namespace: Memory namespace (for strategy selection and allowlist).

        Returns:
            FilterResult with filtered content and detection metadata.

        Raises:
            BlockedContentError: If BLOCK strategy is configured and secrets found.
        """
        _ = source  # Reserved for future audit logging

        if not self._config.enabled:
            return FilterResult(
                content=content,
                action=FilterAction.ALLOWED,
                original_length=len(content),
                filtered_length=len(content),
            )

        if not content or not content.strip():
            return FilterResult(
                content=content,
                action=FilterAction.ALLOWED,
                original_length=len(content),
                filtered_length=len(content),
            )

        # Step 1: Detect all secrets
        detections = self._detect(content)

        if not detections:
            return FilterResult(
                content=content,
                action=FilterAction.ALLOWED,
                original_length=len(content),
                filtered_length=len(content),
            )

        # Step 2: Filter out allowlisted
        active_detections = self._filter_allowlisted(detections, namespace)

        if not active_detections:
            return FilterResult(
                content=content,
                action=FilterAction.ALLOWED,
                detections=detections,  # Keep original detections for reference
                original_length=len(content),
                filtered_length=len(content),
                warnings=("All detected secrets were in allowlist",),
            )

        # Step 3: Apply redaction (may raise BlockedContentError)
        filtered_content = self._redactor.apply(content, active_detections)
        action = self._determine_action(active_detections)

        return FilterResult(
            content=filtered_content,
            action=action,
            detections=active_detections,
            original_length=len(content),
            filtered_length=len(filtered_content),
        )

    def scan(
        self,
        content: str,
        namespace: str = "",
    ) -> FilterResult:
        """Scan content for secrets without modifying it.

        Useful for dry-run mode or reporting purposes.

        Args:
            content: The content to scan.
            namespace: Memory namespace (for allowlist checking).

        Returns:
            FilterResult with detections but original content unchanged.
        """
        if not self._config.enabled or not content or not content.strip():
            return FilterResult(
                content=content,
                action=FilterAction.ALLOWED,
                original_length=len(content),
                filtered_length=len(content),
            )

        # Detect all secrets
        detections = self._detect(content)

        if not detections:
            return FilterResult(
                content=content,
                action=FilterAction.ALLOWED,
                original_length=len(content),
                filtered_length=len(content),
            )

        # Check which would be filtered (not allowlisted)
        active_detections = self._filter_allowlisted(detections, namespace)

        # Build warnings about what would happen
        warnings: list[str] = []
        for detection in active_detections:
            strategy = self._redactor.get_strategy(detection.secret_type)
            warnings.append(
                f"Would {strategy.value}: {detection.secret_type.value} "
                f"at {detection.start}-{detection.end}"
            )

        return FilterResult(
            content=content,  # Unchanged
            action=FilterAction.WARNED if active_detections else FilterAction.ALLOWED,
            detections=detections,
            original_length=len(content),
            filtered_length=len(content),
            warnings=tuple(warnings),
        )

    def _detect(self, content: str) -> tuple[SecretDetection, ...]:
        """Run all detectors and deduplicate results.

        Args:
            content: The content to scan.

        Returns:
            Tuple of deduplicated SecretDetection objects.
        """
        all_detections: list[SecretDetection] = []

        # Run detect-secrets adapter (entropy_enabled controls this)
        if self._config.entropy_enabled:
            secrets_detections = self._secrets_detector.detect(content)
            all_detections.extend(secrets_detections)

        # Run PII detector
        if self._config.pii_enabled:
            pii_detections = self._pii_detector.detect(content)
            all_detections.extend(pii_detections)

        # Deduplicate overlapping detections
        return self._deduplicate(tuple(all_detections))

    def _deduplicate(
        self,
        detections: tuple[SecretDetection, ...],
    ) -> tuple[SecretDetection, ...]:
        """Deduplicate overlapping detections.

        When multiple detectors find overlapping regions:
        1. Prefer specific types over entropy-based detection
        2. Prefer higher confidence scores
        3. Keep the longest match

        Args:
            detections: All detections from all detectors.

        Returns:
            Deduplicated detections.
        """
        if len(detections) <= 1:
            return detections

        # Sort by start position, then by specificity, then by length
        def sort_key(d: SecretDetection) -> tuple[int, int, int, float]:
            # Lower score = higher priority
            specificity = (
                0
                if d.secret_type
                not in (
                    SecretType.HIGH_ENTROPY_BASE64,
                    SecretType.HIGH_ENTROPY_HEX,
                    SecretType.UNKNOWN,
                )
                else 1
            )
            return (d.start, specificity, -(d.end - d.start), -d.confidence)

        sorted_detections = sorted(detections, key=sort_key)

        result: list[SecretDetection] = []
        for detection in sorted_detections:
            # Check if this overlaps with any already-accepted detection
            overlaps = False
            for accepted in result:
                if self._ranges_overlap(
                    detection.start,
                    detection.end,
                    accepted.start,
                    accepted.end,
                ):
                    overlaps = True
                    break

            if not overlaps:
                result.append(detection)

        return tuple(result)

    def _ranges_overlap(
        self,
        start1: int,
        end1: int,
        start2: int,
        end2: int,
    ) -> bool:
        """Check if two ranges overlap."""
        return start1 < end2 and start2 < end1

    def _filter_allowlisted(
        self,
        detections: tuple[SecretDetection, ...],
        namespace: str,
    ) -> tuple[SecretDetection, ...]:
        """Filter out detections that are in the allowlist.

        Args:
            detections: All detected secrets.
            namespace: Namespace for allowlist checking.

        Returns:
            Detections that are NOT in the allowlist.
        """
        result: list[SecretDetection] = []

        for detection in detections:
            if not self._allowlist.is_allowed(
                detection.secret_hash,
                namespace=namespace or None,
            ):
                result.append(detection)
            else:
                _logger.debug(
                    "Skipping allowlisted secret: %s at %d-%d",
                    detection.secret_type.value,
                    detection.start,
                    detection.end,
                )

        return tuple(result)

    def _determine_action(
        self,
        detections: tuple[SecretDetection, ...],
    ) -> FilterAction:
        """Determine the overall action taken based on detections.

        Returns the "most severe" action applied to any detection:
        BLOCKED > REDACTED > MASKED > WARNED > ALLOWED

        Args:
            detections: Active (non-allowlisted) detections.

        Returns:
            The most severe FilterAction applied.
        """
        if not detections:
            return FilterAction.ALLOWED

        actions: set[FilterAction] = set()

        for detection in detections:
            strategy = self._redactor.get_strategy(detection.secret_type)
            action = self._redactor.get_action_for_strategy(strategy)
            actions.add(action)

        # Return most severe
        if FilterAction.BLOCKED in actions:
            return FilterAction.BLOCKED
        if FilterAction.REDACTED in actions:
            return FilterAction.REDACTED
        if FilterAction.MASKED in actions:
            return FilterAction.MASKED
        if FilterAction.WARNED in actions:
            return FilterAction.WARNED
        return FilterAction.ALLOWED


def get_default_service(
    config: SecretsConfig | None = None,
    data_dir: Path | None = None,
) -> SecretsFilteringService:
    """Get the default secrets filtering service instance.

    Returns a singleton instance via ServiceRegistry with thread-safe
    double-checked locking.

    Args:
        config: Optional configuration override (only used on first call).
        data_dir: Optional data directory override (only used on first call).

    Returns:
        The shared SecretsFilteringService instance.
    """
    kwargs: dict[str, SecretsConfig | Path] = {}
    if config is not None:
        kwargs["config"] = config
    if data_dir is not None:
        kwargs["data_dir"] = data_dir
    if kwargs:
        return ServiceRegistry.get(SecretsFilteringService, **kwargs)
    return ServiceRegistry.get(SecretsFilteringService)


def reset_service() -> None:
    """Reset the singleton service instance.

    Used for testing to ensure fresh instances.
    Note: Prefer ServiceRegistry.reset() to reset all services at once.
    """
    # ServiceRegistry.reset() handles this globally
    # This function is kept for backward compatibility
    pass
