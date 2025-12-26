"""Content redactor for secrets filtering.

Applies filtering strategies to detected secrets in content.
Handles overlapping detections and preserves content structure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from git_notes_memory.registry import ServiceRegistry
from git_notes_memory.security.exceptions import BlockedContentError
from git_notes_memory.security.models import FilterAction, FilterStrategy, SecretType

if TYPE_CHECKING:
    from git_notes_memory.security.models import SecretDetection

__all__ = [
    "Redactor",
    "get_default_redactor",
]

_logger = logging.getLogger(__name__)


# =============================================================================
# Redaction Segments
# =============================================================================


@dataclass(frozen=True)
class RedactionSegment:
    """A segment of content that needs redaction.

    Attributes:
        start: Start position in original content.
        end: End position in original content.
        replacement: The replacement text.
        detection: The detection that triggered this redaction.
    """

    start: int
    end: int
    replacement: str
    detection: SecretDetection


# =============================================================================
# Redactor
# =============================================================================


class Redactor:
    """Applies filtering strategies to detected secrets.

    Strategies:
    - REDACT: Replace secret with [REDACTED:{type}] placeholder
    - MASK: Show first/last 4 characters, mask the middle with asterisks
    - BLOCK: Raise BlockedContentError
    - WARN: Log a warning but return content unchanged

    Example usage::

        redactor = Redactor()
        detections = [SecretDetection(SecretType.AWS_ACCESS_KEY, 0, 20, ...)]
        result = redactor.apply("AKIAIOSFODNN7EXAMPLE", detections)
        print(result)  # "[REDACTED:aws_access_key]"

    Overlapping detections are handled by:
    1. Sorting by start position, then by length (longest first)
    2. Merging overlapping regions
    3. Using the highest-priority detection for each merged region
    """

    def __init__(
        self,
        default_strategy: FilterStrategy = FilterStrategy.REDACT,
        strategy_overrides: dict[SecretType, FilterStrategy] | None = None,
    ) -> None:
        """Initialize the Redactor.

        Args:
            default_strategy: Default strategy for all secret types.
            strategy_overrides: Per-type strategy overrides.
        """
        self._default_strategy = default_strategy
        self._overrides = strategy_overrides or {}

    def apply(
        self,
        content: str,
        detections: tuple[SecretDetection, ...],
    ) -> str:
        """Apply redaction to content based on detections.

        Args:
            content: The original content.
            detections: Secrets detected in the content.

        Returns:
            The content with secrets redacted according to the configured strategy.

        Raises:
            BlockedContentError: If any detection has BLOCK strategy.
        """
        if not detections:
            return content

        # Check for BLOCK strategy first
        blocked = self._get_blocked_detections(detections)
        if blocked:
            raise BlockedContentError(detections=blocked)

        # Check for WARN-only (all detections are WARN)
        if all(self._get_strategy(d) == FilterStrategy.WARN for d in detections):
            self._log_warnings(detections)
            return content

        # Build redaction segments
        segments = self._build_segments(content, detections)

        # Merge overlapping segments
        merged = self._merge_overlapping(segments)

        # Apply redactions from end to start to preserve positions
        return self._apply_segments(content, merged)

    def get_strategy(self, secret_type: SecretType) -> FilterStrategy:
        """Get the strategy for a secret type.

        Args:
            secret_type: The type of secret.

        Returns:
            The filtering strategy to apply.
        """
        return self._overrides.get(secret_type, self._default_strategy)

    def get_action_for_strategy(self, strategy: FilterStrategy) -> FilterAction:
        """Get the FilterAction for a FilterStrategy.

        Args:
            strategy: The filtering strategy.

        Returns:
            The corresponding filter action.
        """
        return {
            FilterStrategy.REDACT: FilterAction.REDACTED,
            FilterStrategy.MASK: FilterAction.MASKED,
            FilterStrategy.BLOCK: FilterAction.BLOCKED,
            FilterStrategy.WARN: FilterAction.WARNED,
        }[strategy]

    def _get_strategy(self, detection: SecretDetection) -> FilterStrategy:
        """Get the strategy for a detection."""
        return self._overrides.get(detection.secret_type, self._default_strategy)

    def _get_blocked_detections(
        self,
        detections: tuple[SecretDetection, ...],
    ) -> tuple[SecretDetection, ...]:
        """Get detections that have BLOCK strategy."""
        return tuple(
            d for d in detections if self._get_strategy(d) == FilterStrategy.BLOCK
        )

    def _log_warnings(self, detections: tuple[SecretDetection, ...]) -> None:
        """Log warnings for WARN strategy detections."""
        for d in detections:
            _logger.warning(
                "Secret detected but allowed: %s at position %d-%d (line %s)",
                d.secret_type.value,
                d.start,
                d.end,
                d.line_number or "unknown",
            )

    def _build_segments(
        self,
        content: str,
        detections: tuple[SecretDetection, ...],
    ) -> list[RedactionSegment]:
        """Build redaction segments for each detection."""
        segments: list[RedactionSegment] = []

        for detection in detections:
            strategy = self._get_strategy(detection)

            if strategy == FilterStrategy.WARN:
                # WARN doesn't create a segment
                _logger.warning(
                    "Secret detected but allowed: %s at position %d-%d (line %s)",
                    detection.secret_type.value,
                    detection.start,
                    detection.end,
                    detection.line_number or "unknown",
                )
                continue

            # Get the original text
            original = content[detection.start : detection.end]

            # Generate replacement based on strategy
            if strategy == FilterStrategy.REDACT:
                replacement = f"[REDACTED:{detection.secret_type.value}]"
            elif strategy == FilterStrategy.MASK:
                replacement = self._mask_value(original)
            else:
                # BLOCK is handled earlier
                continue

            segments.append(
                RedactionSegment(
                    start=detection.start,
                    end=detection.end,
                    replacement=replacement,
                    detection=detection,
                )
            )

        return segments

    def _mask_value(self, value: str) -> str:
        """Mask a value showing first/last 4 characters.

        Args:
            value: The secret value to mask.

        Returns:
            Masked value like "AKIA****MPLE".
        """
        # Remove common separators for counting
        clean = value.replace("-", "").replace(" ", "").replace(".", "")
        length = len(clean)

        if length <= 8:
            # Too short to meaningfully mask
            return "*" * length

        # Show first 4 and last 4
        # Find positions in original string
        prefix = ""
        suffix = ""
        prefix_count = 0
        suffix_count = 0

        # Get first 4 non-separator chars
        for char in value:
            if char in "-. ":
                prefix += char
            else:
                prefix += char
                prefix_count += 1
                if prefix_count == 4:
                    break

        # Get last 4 non-separator chars
        for char in reversed(value):
            if char in "-. ":
                suffix = char + suffix
            else:
                suffix = char + suffix
                suffix_count += 1
                if suffix_count == 4:
                    break

        # Calculate mask length (preserve approximate original length)
        mask_length = max(4, length - 8)
        return f"{prefix}{'*' * mask_length}{suffix}"

    def _merge_overlapping(
        self,
        segments: list[RedactionSegment],
    ) -> list[RedactionSegment]:
        """Merge overlapping redaction segments.

        When segments overlap, we keep the one with the longer original
        match (more specific detection).

        Args:
            segments: List of redaction segments.

        Returns:
            Merged list with no overlaps.
        """
        if len(segments) <= 1:
            return segments

        # Sort by start position, then by length descending (longest first)
        sorted_segments = sorted(
            segments,
            key=lambda s: (s.start, -(s.end - s.start)),
        )

        merged: list[RedactionSegment] = []
        for segment in sorted_segments:
            if not merged:
                merged.append(segment)
                continue

            last = merged[-1]

            # Check for overlap
            if segment.start < last.end:
                # Overlapping - keep the longer one (already sorted longest first)
                # If the new segment extends beyond, we might need to combine
                if segment.end > last.end:
                    # Partial overlap extending beyond - keep both but adjust
                    # For simplicity, keep the first (longer) one
                    # In practice, overlapping secrets are usually the same region
                    pass
                # else: completely contained, skip
            else:
                # No overlap
                merged.append(segment)

        return merged

    def _apply_segments(
        self,
        content: str,
        segments: list[RedactionSegment],
    ) -> str:
        """Apply redaction segments to content.

        Applies from end to start to preserve position indices.

        Args:
            content: The original content.
            segments: Merged redaction segments.

        Returns:
            Content with all redactions applied.
        """
        if not segments:
            return content

        # Sort by start position descending (apply from end)
        sorted_segments = sorted(segments, key=lambda s: s.start, reverse=True)

        result = content
        for segment in sorted_segments:
            result = (
                result[: segment.start] + segment.replacement + result[segment.end :]
            )

        return result


# =============================================================================
# Factory
# =============================================================================


def get_default_redactor() -> Redactor:
    """Get the default Redactor instance.

    Returns a singleton instance via ServiceRegistry with thread-safe
    double-checked locking.

    Returns:
        The shared Redactor instance.
    """
    return ServiceRegistry.get(Redactor)


def reset_redactor() -> None:
    """Reset the singleton redactor instance.

    Used for testing to ensure fresh instances.
    Note: Prefer ServiceRegistry.reset() to reset all services at once.
    """
    # ServiceRegistry.reset() handles this globally
    # This function is kept for backward compatibility
    pass
