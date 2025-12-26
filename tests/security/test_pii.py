"""Tests for the PIIDetector."""

from __future__ import annotations

import pytest

from git_notes_memory.security.models import SecretType
from git_notes_memory.security.pii import (
    PIIDetector,
    luhn_check,
    reset_pii_detector,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton detector before each test."""
    reset_pii_detector()
    yield
    reset_pii_detector()


class TestLuhnCheck:
    """Tests for the Luhn algorithm validation."""

    def test_valid_visa(self):
        """Test valid Visa card numbers."""
        assert luhn_check("4111111111111111") is True
        assert luhn_check("4012888888881881") is True

    def test_valid_mastercard(self):
        """Test valid MasterCard numbers."""
        assert luhn_check("5500000000000004") is True
        assert luhn_check("5105105105105100") is True

    def test_valid_amex(self):
        """Test valid American Express numbers."""
        assert luhn_check("378282246310005") is True
        assert luhn_check("371449635398431") is True

    def test_valid_discover(self):
        """Test valid Discover card numbers."""
        assert luhn_check("6011111111111117") is True

    def test_invalid_cards(self):
        """Test invalid card numbers."""
        assert luhn_check("4111111111111112") is False  # Wrong check digit
        assert luhn_check("1234567890123456") is False
        # Note: 0000000000000000 actually passes Luhn (0 mod 10 = 0)
        # but won't be detected as a credit card due to pattern constraints
        assert luhn_check("1111111111111111") is False

    def test_cards_with_separators(self):
        """Test cards with spaces and dashes."""
        assert luhn_check("4111-1111-1111-1111") is True
        assert luhn_check("4111 1111 1111 1111") is True
        assert luhn_check("4111-1111-1111-1112") is False

    def test_too_short(self):
        """Test numbers that are too short."""
        assert luhn_check("12345") is False
        assert luhn_check("") is False
        assert luhn_check("411111111111") is False  # 12 digits

    def test_non_numeric(self):
        """Test handling of non-numeric input."""
        assert luhn_check("abcd-efgh-ijkl-mnop") is False


class TestPIIDetector:
    """Tests for the PIIDetector."""

    def test_detect_ssn_with_dashes(self):
        """Test detection of SSN with dashes."""
        detector = PIIDetector()
        content = "My SSN is 123-45-6789."

        detections = detector.detect(content)

        ssn_detections = [d for d in detections if d.secret_type == SecretType.PII_SSN]
        assert len(ssn_detections) == 1

        ssn = ssn_detections[0]
        assert ssn.line_number == 1
        assert ssn.confidence == 0.7  # No validator

    def test_detect_ssn_without_dashes(self):
        """Test detection of SSN without dashes."""
        detector = PIIDetector()
        content = "SSN: 123 45 6789"

        detections = detector.detect(content)

        ssn_detections = [d for d in detections if d.secret_type == SecretType.PII_SSN]
        assert len(ssn_detections) == 1

    def test_reject_invalid_ssn_patterns(self):
        """Test that invalid SSN patterns are not detected."""
        detector = PIIDetector()
        # 000-XX-XXXX and 666-XX-XXXX are not valid SSNs
        content = "000-12-3456 and 666-12-3456"

        detections = detector.detect(content)
        ssn_detections = [d for d in detections if d.secret_type == SecretType.PII_SSN]

        # These should not be detected as SSNs
        assert len(ssn_detections) == 0

    def test_detect_visa(self):
        """Test detection of Visa card numbers."""
        detector = PIIDetector()
        content = "Card: 4111111111111111"

        detections = detector.detect(content)

        cc_detections = [
            d for d in detections if d.secret_type == SecretType.PII_CREDIT_CARD
        ]
        assert len(cc_detections) == 1
        assert cc_detections[0].confidence == 0.9  # Luhn validated

    def test_detect_mastercard(self):
        """Test detection of MasterCard numbers."""
        detector = PIIDetector()
        content = "MC: 5500000000000004"

        detections = detector.detect(content)

        cc_detections = [
            d for d in detections if d.secret_type == SecretType.PII_CREDIT_CARD
        ]
        assert len(cc_detections) == 1

    def test_detect_amex(self):
        """Test detection of American Express numbers."""
        detector = PIIDetector()
        content = "Amex: 378282246310005"

        detections = detector.detect(content)

        cc_detections = [
            d for d in detections if d.secret_type == SecretType.PII_CREDIT_CARD
        ]
        assert len(cc_detections) == 1

    def test_reject_invalid_credit_card(self):
        """Test that invalid credit card numbers are not detected."""
        detector = PIIDetector()
        content = "Invalid: 4111111111111112"  # Fails Luhn check

        detections = detector.detect(content)

        cc_detections = [
            d for d in detections if d.secret_type == SecretType.PII_CREDIT_CARD
        ]
        assert len(cc_detections) == 0

    def test_detect_phone_with_parens(self):
        """Test detection of phone numbers with parentheses."""
        detector = PIIDetector()
        content = "Call me at (555) 123-4567"

        detections = detector.detect(content)

        phone_detections = [
            d for d in detections if d.secret_type == SecretType.PII_PHONE
        ]
        assert len(phone_detections) == 1

    def test_detect_phone_with_dashes(self):
        """Test detection of phone numbers with dashes."""
        detector = PIIDetector()
        content = "Phone: 555-234-5678"

        detections = detector.detect(content)

        phone_detections = [
            d for d in detections if d.secret_type == SecretType.PII_PHONE
        ]
        assert len(phone_detections) == 1

    def test_detect_phone_with_dots(self):
        """Test detection of phone numbers with dots."""
        detector = PIIDetector()
        content = "Contact: 555.234.5678"

        detections = detector.detect(content)

        phone_detections = [
            d for d in detections if d.secret_type == SecretType.PII_PHONE
        ]
        assert len(phone_detections) == 1

    def test_detect_phone_with_country_code(self):
        """Test detection of phone numbers with +1 country code."""
        detector = PIIDetector()
        content = "International: +1-555-234-5678"

        detections = detector.detect(content)

        phone_detections = [
            d for d in detections if d.secret_type == SecretType.PII_PHONE
        ]
        assert len(phone_detections) == 1

    def test_empty_content(self):
        """Test handling of empty content."""
        detector = PIIDetector()

        assert detector.detect("") == ()
        assert detector.detect("   \n\n   ") == ()

    def test_no_pii(self):
        """Test content with no PII."""
        detector = PIIDetector()
        content = "This is just normal text with no sensitive information."

        detections = detector.detect(content)
        assert detections == ()

    def test_multiline_content(self):
        """Test detection across multiple lines."""
        detector = PIIDetector()
        content = """Line 1: SSN 123-45-6789
Line 2: Card 4111111111111111
Line 3: Phone (555) 234-5678
"""

        detections = detector.detect(content)

        # Should find all three
        ssn = [d for d in detections if d.secret_type == SecretType.PII_SSN]
        cc = [d for d in detections if d.secret_type == SecretType.PII_CREDIT_CARD]
        phone = [d for d in detections if d.secret_type == SecretType.PII_PHONE]

        assert len(ssn) == 1
        assert len(cc) == 1
        assert len(phone) == 1

        assert ssn[0].line_number == 1
        assert cc[0].line_number == 2
        assert phone[0].line_number == 3

    def test_deduplication(self):
        """Test that duplicate detections are removed."""
        detector = PIIDetector()
        # A single credit card number shouldn't be detected twice
        content = "4111111111111111"

        detections = detector.detect(content)

        positions = [(d.start, d.end) for d in detections]
        # No duplicate positions
        assert len(positions) == len(set(positions))

    def test_secret_hash_generated(self):
        """Test that secret hashes are generated."""
        detector = PIIDetector()
        content = "SSN: 123-45-6789"

        detections = detector.detect(content)
        assert len(detections) >= 1

        for detection in detections:
            assert detection.secret_hash != ""
            assert len(detection.secret_hash) == 64  # SHA-256 hex
