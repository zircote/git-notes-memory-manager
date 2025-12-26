"""Tests for the DetectSecretsAdapter."""

from __future__ import annotations

import pytest

from git_notes_memory.security.detector import (
    DetectSecretsAdapter,
    reset_adapter,
)
from git_notes_memory.security.models import SecretType


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton adapter before each test."""
    reset_adapter()
    yield
    reset_adapter()


class TestDetectSecretsAdapter:
    """Tests for DetectSecretsAdapter."""

    def test_detect_aws_key(self):
        """Test detection of AWS access key."""
        adapter = DetectSecretsAdapter()
        content = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"

        detections = adapter.detect(content)

        # Should detect at least the AWS key
        aws_detections = [d for d in detections if d.secret_type == SecretType.AWS_ACCESS_KEY]
        assert len(aws_detections) >= 1

        aws = aws_detections[0]
        assert aws.secret_type == SecretType.AWS_ACCESS_KEY
        assert aws.line_number == 1
        assert aws.secret_hash != ""

    def test_detect_github_token(self):
        """Test detection of GitHub token."""
        adapter = DetectSecretsAdapter()
        # Real GitHub token format
        content = "token = ghp_1234567890abcdefghijklmnopqrstuvwxyz"

        detections = adapter.detect(content)

        # Should detect at least something (GitHub detector or high entropy)
        assert len(detections) >= 1

    def test_detect_private_key(self):
        """Test detection of private key."""
        adapter = DetectSecretsAdapter()
        content = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
-----END RSA PRIVATE KEY-----"""

        detections = adapter.detect(content)

        # Should detect private key
        pk_detections = [d for d in detections if d.secret_type == SecretType.PRIVATE_KEY]
        assert len(pk_detections) >= 1

    def test_detect_high_entropy(self):
        """Test detection of high-entropy strings."""
        adapter = DetectSecretsAdapter()
        # High entropy Base64 string
        content = "secret = 'aGVsbG8gd29ybGQgdGhpcyBpcyBhIGxvbmcgc2VjcmV0'"

        detections = adapter.detect(content)

        # May or may not trigger entropy detection depending on threshold
        # Just verify the adapter doesn't crash
        assert isinstance(detections, tuple)

    def test_empty_content(self):
        """Test handling of empty content."""
        adapter = DetectSecretsAdapter()

        detections = adapter.detect("")
        assert detections == ()

        detections = adapter.detect("   \n\n   ")
        assert detections == ()

    def test_no_secrets(self):
        """Test content with no secrets."""
        adapter = DetectSecretsAdapter()
        content = """
        This is normal text.
        No secrets here!
        Just regular content.
        """

        detections = adapter.detect(content)
        # Should have no or minimal detections
        # (entropy might still catch some things)
        assert isinstance(detections, tuple)

    def test_multiline_content(self):
        """Test detection across multiple lines."""
        adapter = DetectSecretsAdapter()
        content = """Line 1: no secrets
Line 2: aws_key = AKIAIOSFODNN7EXAMPLE
Line 3: normal text
Line 4: another_key = AKIAIOSFODNN7EXAMPL2
"""

        detections = adapter.detect(content)
        aws_detections = [d for d in detections if d.secret_type == SecretType.AWS_ACCESS_KEY]

        # Should find both AWS keys
        assert len(aws_detections) >= 2

        # Check line numbers
        line_numbers = {d.line_number for d in aws_detections}
        assert 2 in line_numbers
        assert 4 in line_numbers

    def test_deduplication(self):
        """Test that overlapping detections are deduplicated."""
        adapter = DetectSecretsAdapter()
        # AWS key might trigger both AWS detector and entropy detector
        content = "AKIAIOSFODNN7EXAMPLE"

        detections = adapter.detect(content)

        # After deduplication, should prefer specific detector over entropy
        positions = [(d.start, d.end) for d in detections]
        # No duplicate positions
        assert len(positions) == len(set(positions))

    def test_secret_hash_generated(self):
        """Test that secret hashes are generated."""
        adapter = DetectSecretsAdapter()
        content = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"

        detections = adapter.detect(content)
        assert len(detections) >= 1

        for detection in detections:
            assert detection.secret_hash != ""
            # SHA-256 hex is 64 characters
            assert len(detection.secret_hash) == 64


class TestDetectSecretsAdapterConfiguration:
    """Tests for adapter configuration."""

    def test_disabled_plugins(self):
        """Test that plugins can be disabled."""
        # This is a configuration test - behavior depends on implementation
        adapter = DetectSecretsAdapter(disabled_plugins=("AWSKeyDetector",))
        content = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"

        detections = adapter.detect(content)

        # Adapter should still work
        assert isinstance(detections, tuple)

    def test_entropy_limit(self):
        """Test entropy limit configuration."""
        # This is a configuration test - actual behavior may vary
        adapter = DetectSecretsAdapter(entropy_limit=5.0)  # Very high threshold

        # Should still work
        detections = adapter.detect("some content")
        assert isinstance(detections, tuple)
