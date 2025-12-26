"""PII (Personally Identifiable Information) detector.

Detects SSN, credit card numbers, and phone numbers using regex patterns.
Credit card detection includes Luhn algorithm validation to reduce false positives.
"""

from __future__ import annotations

import bisect
import hashlib
import re
from dataclasses import dataclass

from git_notes_memory.registry import ServiceRegistry
from git_notes_memory.security.models import SecretDetection, SecretType

__all__ = [
    "PIIDetector",
    "get_default_pii_detector",
    "luhn_check",
]


# =============================================================================
# Pattern Definitions
# =============================================================================


@dataclass(frozen=True)
class PIIPattern:
    """A PII detection pattern.

    Attributes:
        name: Human-readable name for this pattern.
        secret_type: The SecretType to assign to matches.
        regex: Compiled regex pattern.
        validator: Optional validation function (e.g., Luhn check).
    """

    name: str
    secret_type: SecretType
    regex: re.Pattern[str]
    validator: str | None = None  # Name of validation function to use


# SSN Pattern: XXX-XX-XXXX (with or without dashes)
# Avoid matching dates like 123-45-6789 that look like SSN
_SSN_PATTERN = re.compile(
    r"\b"
    r"(?!000|666|9\d{2})"  # SSN can't start with 000, 666, or 9XX
    r"([0-8]\d{2})"  # Area number (001-899, excluding 666)
    r"[- ]?"
    r"(?!00)(\d{2})"  # Group number (01-99)
    r"[- ]?"
    r"(?!0000)(\d{4})"  # Serial number (0001-9999)
    r"\b"
)

# Credit Card Patterns (major card types)
# Visa: starts with 4, 13-16 digits
# MasterCard: starts with 51-55 or 2221-2720, 16 digits
# Amex: starts with 34 or 37, 15 digits
# Discover: starts with 6011 or 65, 16 digits
_CREDIT_CARD_PATTERN = re.compile(
    r"\b"
    r"(?:"
    r"4[0-9]{12}(?:[0-9]{3})?"  # Visa
    r"|"
    r"(?:5[1-5][0-9]{2}|222[1-9]|22[3-9][0-9]|2[3-6][0-9]{2}|27[01][0-9]|2720)[0-9]{12}"  # MC
    r"|"
    r"3[47][0-9]{13}"  # Amex
    r"|"
    r"(?:6011|65[0-9]{2})[0-9]{12}"  # Discover
    r")"
    r"\b"
)

# Also match with spaces/dashes
_CREDIT_CARD_FORMATTED_PATTERN = re.compile(
    r"\b"
    r"(?:"
    r"4[0-9]{3}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{1,4}"  # Visa
    r"|"
    r"(?:5[1-5][0-9]{2})[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}"  # MC
    r"|"
    r"3[47][0-9]{2}[- ]?[0-9]{6}[- ]?[0-9]{5}"  # Amex
    r"|"
    r"(?:6011|65[0-9]{2})[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}"  # Discover
    r")"
    r"\b"
)

# Phone Number Patterns (US formats)
# (XXX) XXX-XXXX, XXX-XXX-XXXX, XXX.XXX.XXXX
# More lenient to catch potential phone numbers for redaction
_PHONE_PATTERN = re.compile(
    r"(?:"
    r"\+?1[- .]?"  # Optional +1 country code
    r")?"
    r"(?:"
    r"\(\d{3}\)[- .]?"  # (XXX) format
    r"|"
    r"\d{3}[- .]"  # XXX- or XXX. format
    r")"
    r"\d{3}[- .]?"  # Exchange
    r"\d{4}"  # Subscriber
    r"(?!\d)"  # Not followed by more digits
)

# All patterns
_PII_PATTERNS = (
    PIIPattern("SSN", SecretType.PII_SSN, _SSN_PATTERN),
    PIIPattern("Credit Card", SecretType.PII_CREDIT_CARD, _CREDIT_CARD_PATTERN, "luhn"),
    PIIPattern(
        "Credit Card (formatted)",
        SecretType.PII_CREDIT_CARD,
        _CREDIT_CARD_FORMATTED_PATTERN,
        "luhn",
    ),
    PIIPattern("Phone", SecretType.PII_PHONE, _PHONE_PATTERN),
)


# =============================================================================
# Validation Functions
# =============================================================================


def luhn_check(card_number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm.

    The Luhn algorithm is a checksum formula used to validate credit card numbers.

    Args:
        card_number: The credit card number (digits only, or with separators).

    Returns:
        True if the number passes the Luhn check, False otherwise.
    """
    # Remove non-digits
    digits = re.sub(r"\D", "", card_number)

    if not digits or len(digits) < 13:
        return False

    # Luhn algorithm
    total = 0
    is_second = False

    # Process from right to left
    for char in reversed(digits):
        digit = int(char)

        if is_second:
            digit *= 2
            if digit > 9:
                digit -= 9

        total += digit
        is_second = not is_second

    return total % 10 == 0


def _hash_value(value: str) -> str:
    """Create a SHA-256 hash of a value.

    Args:
        value: The raw value to hash.

    Returns:
        Hexadecimal SHA-256 hash.
    """
    return hashlib.sha256(value.encode()).hexdigest()


# =============================================================================
# PII Detector
# =============================================================================


class PIIDetector:
    """Detector for Personally Identifiable Information.

    Detects SSN, credit card numbers, and phone numbers using regex patterns.
    Credit card detection includes Luhn validation to reduce false positives.

    Example usage::

        detector = PIIDetector()
        detections = detector.detect("SSN: 123-45-6789")
        for d in detections:
            print(f"Found {d.secret_type} at {d.start}-{d.end}")
    """

    def __init__(self, patterns: tuple[PIIPattern, ...] | None = None) -> None:
        """Initialize the detector.

        Args:
            patterns: PII patterns to use. Defaults to all standard patterns.
        """
        self._patterns = patterns or _PII_PATTERNS

    def detect(self, content: str) -> tuple[SecretDetection, ...]:
        """Detect PII in content.

        Args:
            content: The text content to scan.

        Returns:
            Tuple of SecretDetection objects for found PII.
        """
        if not content:
            return ()

        # HIGH-004: Pre-compute line positions for O(n) instead of O(n*m)
        # Build array of line start positions for binary search
        line_starts = [0]
        for i, char in enumerate(content):
            if char == "\n":
                line_starts.append(i + 1)

        def get_line_number(position: int) -> int:
            """Get line number for position using binary search."""
            return bisect.bisect_right(line_starts, position)

        detections: list[SecretDetection] = []

        for pattern in self._patterns:
            for match in pattern.regex.finditer(content):
                matched_text = match.group()

                # Run validator if specified
                if pattern.validator == "luhn" and not luhn_check(matched_text):
                    continue

                # Calculate line number using pre-computed positions
                line_number = get_line_number(match.start())

                detection = SecretDetection(
                    secret_type=pattern.secret_type,
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9 if pattern.validator else 0.7,  # Higher if validated
                    detector=pattern.name,
                    line_number=line_number,
                    secret_hash=_hash_value(matched_text),
                )
                detections.append(detection)

        # Deduplicate overlapping detections (same position, different patterns)
        return self._deduplicate(tuple(detections))

    def _deduplicate(
        self,
        detections: tuple[SecretDetection, ...],
    ) -> tuple[SecretDetection, ...]:
        """Remove duplicate detections at the same position.

        When multiple patterns match the same text (e.g., formatted and unformatted
        credit card patterns), keep only one.

        Args:
            detections: All detections found.

        Returns:
            Deduplicated and sorted detections.
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

        # For each position, keep the one with highest confidence
        result: list[SecretDetection] = []
        for position_detections in by_position.values():
            if len(position_detections) == 1:
                result.append(position_detections[0])
            else:
                # Keep highest confidence
                best = max(position_detections, key=lambda d: d.confidence)
                result.append(best)

        # Sort by position for consistent output
        result.sort(key=lambda d: (d.start, d.end))
        return tuple(result)


def get_default_pii_detector() -> PIIDetector:
    """Get the default PIIDetector instance.

    Returns a singleton instance via ServiceRegistry with thread-safe
    double-checked locking.

    Returns:
        The shared PIIDetector instance.
    """
    return ServiceRegistry.get(PIIDetector)


def reset_pii_detector() -> None:
    """Reset the singleton detector instance.

    Used for testing to ensure fresh instances.
    Note: Prefer ServiceRegistry.reset() to reset all services at once.
    """
    # ServiceRegistry.reset() handles this globally
    # This function is kept for backward compatibility
    pass
