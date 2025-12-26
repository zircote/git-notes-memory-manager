"""Integration tests for secrets filtering with CaptureService."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from git_notes_memory.capture import CaptureService
from git_notes_memory.git_ops import GitOps
from git_notes_memory.security.config import SecretsConfig
from git_notes_memory.security.exceptions import BlockedContentError
from git_notes_memory.security.models import FilterStrategy
from git_notes_memory.security.service import SecretsFilteringService


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    # Create initial commit
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    subprocess.run(
        ["git", "add", "."],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    return tmp_path


@pytest.fixture
def capture_service_with_filtering(git_repo: Path, tmp_path: Path) -> CaptureService:
    """Create a CaptureService with SecretsFilteringService configured."""
    # Use PII-only detection to avoid entropy false positives
    config = SecretsConfig(enabled=True, entropy_enabled=False)
    secrets_service = SecretsFilteringService(config=config, data_dir=tmp_path)

    git_ops = GitOps(repo_path=git_repo)
    service = CaptureService(
        git_ops=git_ops,
        secrets_service=secrets_service,
    )
    return service


@pytest.fixture
def capture_service_blocking(git_repo: Path, tmp_path: Path) -> CaptureService:
    """Create a CaptureService with BLOCK strategy."""
    config = SecretsConfig(
        enabled=True,
        entropy_enabled=False,
        default_strategy=FilterStrategy.BLOCK,
    )
    secrets_service = SecretsFilteringService(config=config, data_dir=tmp_path)

    git_ops = GitOps(repo_path=git_repo)
    service = CaptureService(
        git_ops=git_ops,
        secrets_service=secrets_service,
    )
    return service


class TestCaptureWithFiltering:
    """Tests for capture with secrets filtering enabled."""

    def test_capture_clean_content(
        self, capture_service_with_filtering: CaptureService
    ):
        """Test that clean content passes through unchanged."""
        summary = "Clean summary without secrets"
        content = "This is clean content with no sensitive data."

        result = capture_service_with_filtering.capture(
            namespace="decisions",
            summary=summary,
            content=content,
        )

        assert result.success
        assert result.memory is not None
        assert result.memory.summary == summary
        assert result.memory.content == content

    def test_capture_redacts_ssn_in_content(
        self, capture_service_with_filtering: CaptureService
    ):
        """Test that SSN in content is redacted."""
        summary = "Summary about a person"
        content = "The user's SSN is 123-45-6789 and their info."

        result = capture_service_with_filtering.capture(
            namespace="decisions",
            summary=summary,
            content=content,
        )

        assert result.success
        assert result.memory is not None
        assert "123-45-6789" not in result.memory.content
        assert "[REDACTED:pii_ssn]" in result.memory.content
        assert result.warning is not None
        assert "secret" in result.warning.lower()

    def test_capture_redacts_ssn_in_summary(
        self, capture_service_with_filtering: CaptureService
    ):
        """Test that SSN in summary is redacted."""
        summary = "User 123-45-6789 issue"
        content = "Some clean content."

        result = capture_service_with_filtering.capture(
            namespace="learnings",
            summary=summary,
            content=content,
        )

        assert result.success
        assert result.memory is not None
        assert "123-45-6789" not in result.memory.summary
        assert "[REDACTED:pii_ssn]" in result.memory.summary
        assert result.warning is not None

    def test_capture_redacts_credit_card(
        self, capture_service_with_filtering: CaptureService
    ):
        """Test that credit card numbers are redacted."""
        summary = "Payment issue"
        content = "Customer card: 4111111111111111"

        result = capture_service_with_filtering.capture(
            namespace="progress",
            summary=summary,
            content=content,
        )

        assert result.success
        assert result.memory is not None
        assert "4111111111111111" not in result.memory.content
        assert "[REDACTED:pii_credit_card]" in result.memory.content

    def test_capture_redacts_phone(
        self, capture_service_with_filtering: CaptureService
    ):
        """Test that phone numbers are redacted."""
        summary = "Contact info"
        content = "Call user at (555) 123-4567"

        result = capture_service_with_filtering.capture(
            namespace="blockers",
            summary=summary,
            content=content,
        )

        assert result.success
        assert result.memory is not None
        assert "(555) 123-4567" not in result.memory.content
        assert "[REDACTED:pii_phone]" in result.memory.content

    def test_capture_redacts_multiple_secrets(
        self, capture_service_with_filtering: CaptureService
    ):
        """Test that multiple secrets are all redacted."""
        summary = "User 123-45-6789 payment"
        # Note: Use valid SSN area code (not 900-999 which are reserved)
        content = """User details:
SSN: 234-56-7890
Card: 4111111111111111
Phone: (555) 987-6543"""

        result = capture_service_with_filtering.capture(
            namespace="decisions",
            summary=summary,
            content=content,
        )

        assert result.success
        assert result.memory is not None
        # Summary SSN redacted
        assert "123-45-6789" not in result.memory.summary
        # Content SSN redacted (using valid area code)
        assert "234-56-7890" not in result.memory.content
        # Credit card redacted
        assert "4111111111111111" not in result.memory.content
        # Phone redacted
        assert "(555) 987-6543" not in result.memory.content


class TestCaptureWithBlockStrategy:
    """Tests for capture with BLOCK strategy configured."""

    def test_capture_blocks_on_secret(self, capture_service_blocking: CaptureService):
        """Test that capture raises BlockedContentError when secrets found."""
        summary = "Normal summary"
        content = "SSN: 123-45-6789"

        with pytest.raises(BlockedContentError) as exc_info:
            capture_service_blocking.capture(
                namespace="decisions",
                summary=summary,
                content=content,
            )

        # BlockedContentError should contain detection info
        assert len(exc_info.value.detections) >= 1

    def test_capture_clean_content_allowed(
        self, capture_service_blocking: CaptureService
    ):
        """Test that clean content passes even with BLOCK strategy."""
        summary = "Clean summary"
        content = "No secrets here."

        result = capture_service_blocking.capture(
            namespace="learnings",
            summary=summary,
            content=content,
        )

        assert result.success
        assert result.memory is not None


class TestCaptureWithoutFiltering:
    """Tests to verify capture works without filtering service."""

    def test_capture_no_secrets_service(self, git_repo: Path):
        """Test that capture works when no secrets service is configured."""
        git_ops = GitOps(repo_path=git_repo)
        service = CaptureService(git_ops=git_ops)

        # Content with what would be a secret
        summary = "User 123-45-6789"
        content = "SSN: 123-45-6789"

        result = service.capture(
            namespace="decisions",
            summary=summary,
            content=content,
        )

        # Should pass through unchanged
        assert result.success
        assert result.memory is not None
        assert result.memory.summary == summary
        assert result.memory.content == content


class TestCaptureWithDisabledFiltering:
    """Tests for capture with disabled secrets service."""

    def test_capture_disabled_service(self, git_repo: Path, tmp_path: Path):
        """Test that disabled service passes content through."""
        config = SecretsConfig(enabled=False)
        secrets_service = SecretsFilteringService(config=config, data_dir=tmp_path)

        git_ops = GitOps(repo_path=git_repo)
        service = CaptureService(
            git_ops=git_ops,
            secrets_service=secrets_service,
        )

        summary = "User 123-45-6789"
        content = "SSN: 123-45-6789"

        result = service.capture(
            namespace="decisions",
            summary=summary,
            content=content,
        )

        # Should pass through unchanged
        assert result.success
        assert result.memory is not None
        assert result.memory.summary == summary
        assert result.memory.content == content


class TestCaptureWithAllowlist:
    """Tests for capture with allowlisted secrets."""

    def test_allowlisted_secret_passes(self, git_repo: Path, tmp_path: Path):
        """Test that allowlisted secrets are not filtered."""
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        secrets_service = SecretsFilteringService(config=config, data_dir=tmp_path)

        # Add to allowlist
        secrets_service.allowlist.add(value="123-45-6789", reason="Test SSN")

        git_ops = GitOps(repo_path=git_repo)
        service = CaptureService(
            git_ops=git_ops,
            secrets_service=secrets_service,
        )

        content = "SSN: 123-45-6789"

        result = service.capture(
            namespace="decisions",
            summary="Allowlisted test",
            content=content,
        )

        assert result.success
        assert result.memory is not None
        # SSN should be present (not redacted)
        assert "123-45-6789" in result.memory.content


class TestCaptureSetSecretsService:
    """Tests for the set_secrets_service method."""

    def test_set_secrets_service_after_init(self, git_repo: Path, tmp_path: Path):
        """Test setting secrets service after initialization."""
        git_ops = GitOps(repo_path=git_repo)
        service = CaptureService(git_ops=git_ops)

        # Initially no filtering
        result = service.capture(
            namespace="decisions",
            summary="Test",
            content="SSN: 123-45-6789",
        )
        assert "123-45-6789" in result.memory.content  # type: ignore[union-attr]

        # Now add secrets service
        config = SecretsConfig(enabled=True, entropy_enabled=False)
        secrets_service = SecretsFilteringService(config=config, data_dir=tmp_path)
        service.set_secrets_service(secrets_service)

        # Now should filter (use valid SSN area code, not 900-999)
        result = service.capture(
            namespace="learnings",
            summary="Test2",
            content="SSN: 234-56-7890",
        )
        assert "234-56-7890" not in result.memory.content  # type: ignore[union-attr]
        assert "[REDACTED:pii_ssn]" in result.memory.content  # type: ignore[union-attr]

    def test_secrets_service_property(self, git_repo: Path, tmp_path: Path):
        """Test the secrets_service property."""
        config = SecretsConfig(enabled=True)
        secrets_service = SecretsFilteringService(config=config, data_dir=tmp_path)

        git_ops = GitOps(repo_path=git_repo)
        service = CaptureService(
            git_ops=git_ops,
            secrets_service=secrets_service,
        )

        assert service.secrets_service is secrets_service


class TestConvenienceMethodsWithFiltering:
    """Tests for convenience methods with filtering enabled."""

    def test_capture_decision_filters(
        self, capture_service_with_filtering: CaptureService
    ):
        """Test capture_decision applies filtering."""
        result = capture_service_with_filtering.capture_decision(
            spec="test-project",
            summary="Decision about user 123-45-6789",
            context="User SSN context",
            rationale="Rationale with card 4111111111111111",
        )

        assert result.success
        assert result.memory is not None
        assert "123-45-6789" not in result.memory.summary
        assert "4111111111111111" not in result.memory.content

    def test_capture_learning_filters(
        self, capture_service_with_filtering: CaptureService
    ):
        """Test capture_learning applies filtering."""
        result = capture_service_with_filtering.capture_learning(
            summary="Learned about phone (555) 123-4567",
            insight="The phone was important",
        )

        assert result.success
        assert result.memory is not None
        assert "(555) 123-4567" not in result.memory.summary

    def test_capture_progress_filters(
        self, capture_service_with_filtering: CaptureService
    ):
        """Test capture_progress applies filtering."""
        result = capture_service_with_filtering.capture_progress(
            spec="test-project",
            summary="Progress update",
            milestone="Handled SSN 123-45-6789 case",
        )

        assert result.success
        assert result.memory is not None
        assert "123-45-6789" not in result.memory.content
