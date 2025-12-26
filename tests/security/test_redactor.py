"""Tests for the Redactor."""

from __future__ import annotations

import pytest

from git_notes_memory.security.exceptions import BlockedContentError
from git_notes_memory.security.models import FilterStrategy, SecretDetection, SecretType
from git_notes_memory.security.redactor import Redactor, reset_redactor


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton redactor before each test."""
    reset_redactor()
    yield
    reset_redactor()


def make_detection(
    secret_type: SecretType = SecretType.GENERIC_API_KEY,
    start: int = 0,
    end: int = 10,
    confidence: float = 1.0,
    detector: str = "test",
    line_number: int = 1,
    secret_hash: str = "abc123",  # noqa: S107 - test fixture, not a real secret
) -> SecretDetection:
    """Helper to create a SecretDetection."""
    return SecretDetection(
        secret_type=secret_type,
        start=start,
        end=end,
        confidence=confidence,
        detector=detector,
        line_number=line_number,
        secret_hash=secret_hash,
    )


class TestRedactStrategy:
    """Tests for REDACT strategy."""

    def test_redact_single_secret(self):
        """Test redacting a single secret."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "my_api_key = SECRET123"
        detection = make_detection(
            secret_type=SecretType.GENERIC_API_KEY,
            start=13,
            end=22,
        )

        result = redactor.apply(content, (detection,))

        assert result == "my_api_key = [REDACTED:generic_api_key]"

    def test_redact_aws_key(self):
        """Test redacting AWS access key."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "aws_key = AKIAIOSFODNN7EXAMPLE"
        detection = make_detection(
            secret_type=SecretType.AWS_ACCESS_KEY,
            start=10,
            end=30,
        )

        result = redactor.apply(content, (detection,))

        assert result == "aws_key = [REDACTED:aws_access_key]"

    def test_redact_multiple_secrets(self):
        """Test redacting multiple secrets in order."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "key1=SECRET1 key2=SECRET2"
        detections = (
            make_detection(SecretType.GENERIC_API_KEY, start=5, end=12),
            make_detection(SecretType.GENERIC_API_KEY, start=18, end=25),
        )

        result = redactor.apply(content, detections)

        assert (
            result == "key1=[REDACTED:generic_api_key] key2=[REDACTED:generic_api_key]"
        )

    def test_redact_preserves_surrounding_text(self):
        """Test that text around secrets is preserved."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "prefix SECRET suffix"
        detection = make_detection(start=7, end=13)

        result = redactor.apply(content, (detection,))

        assert result == "prefix [REDACTED:generic_api_key] suffix"

    def test_redact_ssn(self):
        """Test redacting SSN with appropriate type."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "SSN: 123-45-6789"
        detection = make_detection(
            secret_type=SecretType.PII_SSN,
            start=5,
            end=16,
        )

        result = redactor.apply(content, (detection,))

        assert result == "SSN: [REDACTED:pii_ssn]"


class TestMaskStrategy:
    """Tests for MASK strategy."""

    def test_mask_long_secret(self):
        """Test masking a long secret shows first/last 4 chars."""
        redactor = Redactor(default_strategy=FilterStrategy.MASK)
        content = "key=AKIAIOSFODNN7EXAMPLE"  # 20 chars
        detection = make_detection(start=4, end=24)

        result = redactor.apply(content, (detection,))

        # Should show AKIA****MPLE (first 4, mask, last 4)
        assert "AKIA" in result
        assert "MPLE" in result
        assert "****" in result

    def test_mask_short_secret(self):
        """Test masking a short secret (<=8 chars) uses all asterisks."""
        redactor = Redactor(default_strategy=FilterStrategy.MASK)
        content = "key=SHORT123"  # 8 chars
        detection = make_detection(start=4, end=12)

        result = redactor.apply(content, (detection,))

        # Should be all asterisks
        assert result == "key=********"

    def test_mask_with_separators(self):
        """Test masking preserves separators in prefix/suffix."""
        redactor = Redactor(default_strategy=FilterStrategy.MASK)
        content = "card=4111-1111-1111-1111"
        detection = make_detection(start=5, end=24)

        result = redactor.apply(content, (detection,))

        # Should have some masking
        assert "*" in result
        # First 4 should include the 4111- pattern
        assert "4111" in result


class TestBlockStrategy:
    """Tests for BLOCK strategy."""

    def test_block_raises_error(self):
        """Test that BLOCK strategy raises BlockedContentError."""
        redactor = Redactor(default_strategy=FilterStrategy.BLOCK)
        content = "password=supersecret"
        detection = make_detection(
            secret_type=SecretType.PASSWORD,
            start=9,
            end=20,
        )

        with pytest.raises(BlockedContentError) as exc_info:
            redactor.apply(content, (detection,))

        assert len(exc_info.value.detections) == 1
        assert exc_info.value.detections[0].secret_type == SecretType.PASSWORD

    def test_block_with_multiple_detections(self):
        """Test BLOCK with multiple secrets includes all in error."""
        redactor = Redactor(default_strategy=FilterStrategy.BLOCK)
        content = "key1=SECRET1 key2=SECRET2"
        detections = (
            make_detection(SecretType.GENERIC_API_KEY, start=5, end=12),
            make_detection(SecretType.AWS_ACCESS_KEY, start=18, end=25),
        )

        with pytest.raises(BlockedContentError) as exc_info:
            redactor.apply(content, detections)

        assert len(exc_info.value.detections) == 2

    def test_block_error_message(self):
        """Test that BlockedContentError has informative message."""
        redactor = Redactor(default_strategy=FilterStrategy.BLOCK)
        content = "secret=VALUE"
        detection = make_detection(secret_type=SecretType.PRIVATE_KEY, start=7, end=12)

        with pytest.raises(BlockedContentError) as exc_info:
            redactor.apply(content, (detection,))

        error_str = str(exc_info.value)
        assert "private_key" in error_str
        assert "position 7-12" in error_str


class TestWarnStrategy:
    """Tests for WARN strategy."""

    def test_warn_returns_unchanged_content(self):
        """Test that WARN strategy returns content unchanged."""
        redactor = Redactor(default_strategy=FilterStrategy.WARN)
        content = "password=supersecret"
        detection = make_detection(start=9, end=20)

        result = redactor.apply(content, (detection,))

        assert result == content

    def test_warn_with_multiple_detections(self):
        """Test WARN with multiple detections returns unchanged."""
        redactor = Redactor(default_strategy=FilterStrategy.WARN)
        content = "key1=SECRET1 key2=SECRET2"
        detections = (
            make_detection(start=5, end=12),
            make_detection(start=18, end=25),
        )

        result = redactor.apply(content, detections)

        assert result == content


class TestStrategyOverrides:
    """Tests for per-type strategy overrides."""

    def test_override_single_type(self):
        """Test overriding strategy for a single type."""
        redactor = Redactor(
            default_strategy=FilterStrategy.REDACT,
            strategy_overrides={SecretType.PII_CREDIT_CARD: FilterStrategy.MASK},
        )
        content = "card=4111111111111111 key=SECRET"
        detections = (
            make_detection(SecretType.PII_CREDIT_CARD, start=5, end=21),
            make_detection(SecretType.GENERIC_API_KEY, start=26, end=32),
        )

        result = redactor.apply(content, detections)

        # Credit card should be masked, API key should be redacted
        assert "[REDACTED:generic_api_key]" in result
        assert "4111" in result  # First 4 of credit card

    def test_override_to_block(self):
        """Test overriding a specific type to BLOCK."""
        redactor = Redactor(
            default_strategy=FilterStrategy.REDACT,
            strategy_overrides={SecretType.PRIVATE_KEY: FilterStrategy.BLOCK},
        )
        content = "key=-----BEGIN RSA PRIVATE KEY-----"
        detection = make_detection(SecretType.PRIVATE_KEY, start=4, end=35)

        with pytest.raises(BlockedContentError):
            redactor.apply(content, (detection,))

    def test_mixed_strategies(self):
        """Test content with mixed strategies applied correctly."""
        redactor = Redactor(
            default_strategy=FilterStrategy.REDACT,
            strategy_overrides={
                SecretType.PII_SSN: FilterStrategy.WARN,
            },
        )
        content = "ssn=123-45-6789 key=SECRET"
        detections = (
            make_detection(SecretType.PII_SSN, start=4, end=15),
            make_detection(SecretType.GENERIC_API_KEY, start=20, end=26),
        )

        result = redactor.apply(content, detections)

        # SSN should be unchanged (WARN), API key should be redacted
        assert "123-45-6789" in result
        assert "[REDACTED:generic_api_key]" in result


class TestOverlappingDetections:
    """Tests for handling overlapping detections."""

    def test_identical_overlap(self):
        """Test two detections at the same position."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "secret=AKIAIOSFODNN7EXAMPLE"
        # Same position, different types (e.g., AWS key and high entropy)
        detections = (
            make_detection(SecretType.AWS_ACCESS_KEY, start=7, end=27),
            make_detection(SecretType.HIGH_ENTROPY_BASE64, start=7, end=27),
        )

        result = redactor.apply(content, detections)

        # Should only have one redaction (not two)
        assert result.count("[REDACTED:") == 1

    def test_nested_overlap(self):
        """Test one detection contained within another."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "data = longer_secret_value_here"
        # Outer detection contains inner one
        detections = (
            make_detection(SecretType.GENERIC_API_KEY, start=7, end=31),  # Longer
            make_detection(SecretType.HIGH_ENTROPY_HEX, start=14, end=20),  # Contained
        )

        result = redactor.apply(content, detections)

        # Should use the longer detection
        assert result.count("[REDACTED:") == 1
        assert "[REDACTED:generic_api_key]" in result

    def test_partial_overlap(self):
        """Test partially overlapping detections."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "data = abcdefghijklmnop"
        # Overlapping but not identical
        detections = (
            make_detection(SecretType.GENERIC_API_KEY, start=7, end=15),  # abcdefgh
            make_detection(SecretType.HIGH_ENTROPY_HEX, start=12, end=20),  # fghijklm
        )

        result = redactor.apply(content, detections)

        # First one should be used (they overlap, first is kept)
        assert "[REDACTED:generic_api_key]" in result


class TestEmptyAndEdgeCases:
    """Tests for empty content and edge cases."""

    def test_empty_detections(self):
        """Test with no detections returns original content."""
        redactor = Redactor()
        content = "no secrets here"

        result = redactor.apply(content, ())

        assert result == content

    def test_empty_content(self):
        """Test with empty content."""
        redactor = Redactor()

        result = redactor.apply("", ())

        assert result == ""

    def test_detection_at_start(self):
        """Test detection at the very start of content."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "SECRET rest of content"
        detection = make_detection(start=0, end=6)

        result = redactor.apply(content, (detection,))

        assert result == "[REDACTED:generic_api_key] rest of content"

    def test_detection_at_end(self):
        """Test detection at the very end of content."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "content ends with SECRET"
        detection = make_detection(start=18, end=24)

        result = redactor.apply(content, (detection,))

        assert result == "content ends with [REDACTED:generic_api_key]"

    def test_detection_entire_content(self):
        """Test detection covers entire content."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "ENTIRESECRET"
        detection = make_detection(start=0, end=12)

        result = redactor.apply(content, (detection,))

        assert result == "[REDACTED:generic_api_key]"


class TestGetStrategy:
    """Tests for get_strategy method."""

    def test_get_default_strategy(self):
        """Test getting the default strategy."""
        redactor = Redactor(default_strategy=FilterStrategy.MASK)

        assert redactor.get_strategy(SecretType.GENERIC_API_KEY) == FilterStrategy.MASK

    def test_get_overridden_strategy(self):
        """Test getting an overridden strategy."""
        redactor = Redactor(
            default_strategy=FilterStrategy.REDACT,
            strategy_overrides={SecretType.PII_SSN: FilterStrategy.MASK},
        )

        assert redactor.get_strategy(SecretType.PII_SSN) == FilterStrategy.MASK
        assert (
            redactor.get_strategy(SecretType.GENERIC_API_KEY) == FilterStrategy.REDACT
        )


class TestMultilineContent:
    """Tests for multiline content."""

    def test_redact_across_lines(self):
        """Test redacting secrets across multiple lines."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = """Line 1: SECRET1
Line 2: normal text
Line 3: SECRET2"""
        detections = (
            make_detection(start=8, end=15, line_number=1),
            make_detection(start=47, end=54, line_number=3),
        )

        result = redactor.apply(content, detections)

        assert "[REDACTED:generic_api_key]" in result
        assert "normal text" in result
        assert result.count("[REDACTED:") == 2

    def test_preserves_newlines(self):
        """Test that newlines are preserved."""
        redactor = Redactor(default_strategy=FilterStrategy.REDACT)
        content = "line1\nSECRET\nline3"
        detection = make_detection(start=6, end=12)

        result = redactor.apply(content, (detection,))

        assert "line1\n" in result
        assert "\nline3" in result
