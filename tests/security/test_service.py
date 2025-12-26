"""Tests for the SecretsFilteringService."""

from __future__ import annotations

from pathlib import Path

import pytest

from git_notes_memory.security.config import SecretsConfig
from git_notes_memory.security.exceptions import BlockedContentError
from git_notes_memory.security.models import FilterAction, FilterStrategy, SecretType
from git_notes_memory.security.service import (
    SecretsFilteringService,
    reset_service,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton service before each test."""
    reset_service()
    yield
    reset_service()


@pytest.fixture
def service(tmp_path: Path) -> SecretsFilteringService:
    """Create a fresh SecretsFilteringService with temp directory."""
    config = SecretsConfig(enabled=True)
    return SecretsFilteringService(config=config, data_dir=tmp_path)


@pytest.fixture
def disabled_service(tmp_path: Path) -> SecretsFilteringService:
    """Create a disabled SecretsFilteringService."""
    config = SecretsConfig(enabled=False)
    return SecretsFilteringService(config=config, data_dir=tmp_path)


class TestFilterBasic:
    """Basic filtering tests."""

    def test_filter_no_secrets(self, tmp_path: Path):
        """Test filtering content with no secrets."""
        # Use PII-only detection to avoid entropy false positives
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = "this is just normal text without any secrets"

        result = service.filter(content)

        assert result.content == content
        assert result.action == FilterAction.ALLOWED
        assert not result.had_secrets

    def test_filter_empty_content(self, service: SecretsFilteringService):
        """Test filtering empty content."""
        result = service.filter("")

        assert result.content == ""
        assert result.action == FilterAction.ALLOWED

    def test_filter_whitespace_only(self, service: SecretsFilteringService):
        """Test filtering whitespace-only content."""
        result = service.filter("   \n\n   ")

        assert result.action == FilterAction.ALLOWED

    def test_filter_disabled(self, disabled_service: SecretsFilteringService):
        """Test that disabled service passes content through."""
        content = "aws_key = AKIAIOSFODNN7EXAMPLE"

        result = disabled_service.filter(content)

        assert result.content == content
        assert result.action == FilterAction.ALLOWED


class TestFilterSecrets:
    """Tests for detecting and filtering secrets."""

    def test_filter_aws_key(self, service: SecretsFilteringService):
        """Test filtering AWS access key."""
        content = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"

        result = service.filter(content)

        assert "[REDACTED:" in result.content
        assert "AKIAIOSFODNN7EXAMPLE" not in result.content
        assert result.action == FilterAction.REDACTED
        assert result.had_secrets

    def test_filter_ssn(self, service: SecretsFilteringService):
        """Test filtering SSN."""
        content = "SSN: 123-45-6789"

        result = service.filter(content)

        assert "[REDACTED:pii_ssn]" in result.content
        assert "123-45-6789" not in result.content
        assert result.action == FilterAction.REDACTED

    def test_filter_credit_card(self, service: SecretsFilteringService):
        """Test filtering credit card number."""
        content = "Card: 4111111111111111"

        result = service.filter(content)

        assert "[REDACTED:pii_credit_card]" in result.content
        assert "4111111111111111" not in result.content

    def test_filter_phone(self, service: SecretsFilteringService):
        """Test filtering phone number."""
        content = "Phone: (555) 123-4567"

        result = service.filter(content)

        assert "[REDACTED:pii_phone]" in result.content

    def test_filter_multiple_secrets(self, service: SecretsFilteringService):
        """Test filtering multiple secrets in one content."""
        content = """AWS: AKIAIOSFODNN7EXAMPLE
SSN: 123-45-6789
Card: 4111111111111111"""

        result = service.filter(content)

        assert "AKIAIOSFODNN7EXAMPLE" not in result.content
        assert "123-45-6789" not in result.content
        assert "4111111111111111" not in result.content
        assert result.detection_count >= 3


class TestFilterStrategies:
    """Tests for different filtering strategies."""

    def test_redact_strategy(self, tmp_path: Path):
        """Test REDACT strategy."""
        config = SecretsConfig(
            enabled=True,
            default_strategy=FilterStrategy.REDACT,
        )
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        result = service.filter("SSN: 123-45-6789")

        assert "[REDACTED:pii_ssn]" in result.content

    def test_mask_strategy(self, tmp_path: Path):
        """Test MASK strategy."""
        config = SecretsConfig(
            enabled=True,
            default_strategy=FilterStrategy.MASK,
        )
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        result = service.filter("Card: 4111111111111111")

        # Masked should show partial info
        assert "*" in result.content
        assert result.action == FilterAction.MASKED

    def test_block_strategy(self, tmp_path: Path):
        """Test BLOCK strategy raises error."""
        config = SecretsConfig(
            enabled=True,
            default_strategy=FilterStrategy.BLOCK,
        )
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        with pytest.raises(BlockedContentError) as exc_info:
            service.filter("SSN: 123-45-6789")

        assert len(exc_info.value.detections) >= 1

    def test_warn_strategy(self, tmp_path: Path):
        """Test WARN strategy passes content through."""
        config = SecretsConfig(
            enabled=True,
            default_strategy=FilterStrategy.WARN,
        )
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = "SSN: 123-45-6789"
        result = service.filter(content)

        assert result.content == content
        assert result.action == FilterAction.WARNED


class TestAllowlist:
    """Tests for allowlist integration."""

    def test_allowlisted_secret_passes(self, tmp_path: Path):
        """Test that allowlisted secrets are not filtered."""
        # Use a service that only has PII detection to avoid entropy false positives
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = "my ssn is 123-45-6789"

        # Add to allowlist
        service.allowlist.add(value="123-45-6789", reason="Test allowlist")

        result = service.filter(content)

        # Content should be unchanged
        assert "123-45-6789" in result.content
        assert result.action == FilterAction.ALLOWED

    def test_allowlisted_shows_warning(self, tmp_path: Path):
        """Test that allowlisted secrets generate warnings."""
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = "my ssn is 123-45-6789"
        service.allowlist.add(value="123-45-6789", reason="Test")

        result = service.filter(content)

        # Should have warning about allowlisted secrets
        assert len(result.warnings) > 0

    def test_namespace_allowlist(self, tmp_path: Path):
        """Test namespace-scoped allowlist."""
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        content = "my ssn is 123-45-6789"

        # Add to decisions namespace only
        service.allowlist.add(
            value="123-45-6789",
            reason="Test",
            namespace="decisions",
        )

        # Should be filtered in other namespace
        result = service.filter(content, namespace="progress")
        assert "123-45-6789" not in result.content

        # Should pass in decisions namespace
        result = service.filter(content, namespace="decisions")
        assert "123-45-6789" in result.content


class TestScan:
    """Tests for scan method (detection without modification)."""

    def test_scan_detects_secrets(self, service: SecretsFilteringService):
        """Test that scan detects secrets."""
        content = "SSN: 123-45-6789"

        result = service.scan(content)

        assert result.had_secrets
        assert result.detection_count >= 1

    def test_scan_does_not_modify(self, service: SecretsFilteringService):
        """Test that scan does not modify content."""
        content = "SSN: 123-45-6789"

        result = service.scan(content)

        assert result.content == content
        assert "123-45-6789" in result.content

    def test_scan_provides_warnings(self, service: SecretsFilteringService):
        """Test that scan provides warnings about what would happen."""
        content = "SSN: 123-45-6789"

        result = service.scan(content)

        assert len(result.warnings) > 0
        assert "Would redact" in result.warnings[0]

    def test_scan_empty_content(self, service: SecretsFilteringService):
        """Test scan with empty content."""
        result = service.scan("")

        assert result.action == FilterAction.ALLOWED
        assert not result.had_secrets


class TestDeduplication:
    """Tests for deduplication of overlapping detections."""

    def test_prefers_specific_over_entropy(self, service: SecretsFilteringService):
        """Test that specific detections are preferred over entropy."""
        # AWS key should be detected as AWS_ACCESS_KEY, not HIGH_ENTROPY
        content = "AKIAIOSFODNN7EXAMPLE"

        result = service.filter(content)

        # Check detection type if any detections
        if result.had_secrets:
            types = [d.secret_type for d in result.detections]
            # Should prefer specific AWS detection if both detected
            if SecretType.AWS_ACCESS_KEY in types:
                assert SecretType.HIGH_ENTROPY_BASE64 not in types or len(types) == 1


class TestConfiguration:
    """Tests for configuration options."""

    def test_disable_pii_detection(self, tmp_path: Path):
        """Test disabling PII detection."""
        config = SecretsConfig(
            enabled=True,
            pii_enabled=False,
        )
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        result = service.filter("SSN: 123-45-6789")

        # PII should not be detected
        pii_types = {
            SecretType.PII_SSN,
            SecretType.PII_CREDIT_CARD,
            SecretType.PII_PHONE,
        }
        detected_types = {d.secret_type for d in result.detections}
        assert not detected_types.intersection(pii_types)

    def test_disable_entropy_detection(self, tmp_path: Path):
        """Test disabling entropy detection."""
        config = SecretsConfig(
            enabled=True,
            entropy_enabled=False,
        )
        service = SecretsFilteringService(config=config, data_dir=tmp_path)

        # Only PII should work
        result = service.filter("SSN: 123-45-6789")

        # SSN should still be detected
        assert result.had_secrets


class TestProperties:
    """Tests for service properties."""

    def test_enabled_property(self, service: SecretsFilteringService):
        """Test enabled property."""
        assert service.enabled is True

    def test_config_property(self, service: SecretsFilteringService):
        """Test config property."""
        assert service.config is not None
        assert service.config.enabled is True

    def test_allowlist_property(self, service: SecretsFilteringService):
        """Test allowlist property."""
        assert service.allowlist is not None

    def test_redactor_property(self, service: SecretsFilteringService):
        """Test redactor property."""
        assert service.redactor is not None


class TestFilterResult:
    """Tests for FilterResult properties."""

    def test_original_and_filtered_length(self, service: SecretsFilteringService):
        """Test that lengths are correctly tracked."""
        content = "SSN: 123-45-6789"

        result = service.filter(content)

        assert result.original_length == len(content)
        assert result.filtered_length == len(result.content)
        # Redacted version should have different length
        assert result.original_length != result.filtered_length

    def test_by_type_property(self, service: SecretsFilteringService):
        """Test by_type property groups detections."""
        content = """SSN: 123-45-6789
Card: 4111111111111111"""

        result = service.filter(content)

        by_type = result.by_type
        # Should have entries for detected types
        assert len(by_type) > 0
