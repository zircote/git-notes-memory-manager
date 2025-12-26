"""Integration tests for the complete secrets filtering workflow.

These tests verify end-to-end scenarios including:
- Capture with secrets → filtering → audit logging
- Retrospective scanning of existing memories
- Allowlist workflow with audit trail
- Configuration changes affecting behavior
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from git_notes_memory.capture import CaptureService
from git_notes_memory.git_ops import GitOps
from git_notes_memory.index import IndexService
from git_notes_memory.models import Memory
from git_notes_memory.security import (
    get_audit_logger,
    get_secrets_filtering_service,
)
from git_notes_memory.security.allowlist import reset_allowlist_manager
from git_notes_memory.security.audit import reset_audit_logger
from git_notes_memory.security.config import SecretsConfig
from git_notes_memory.security.models import FilterAction, FilterStrategy
from git_notes_memory.security.service import SecretsFilteringService, reset_service


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singleton services before each test."""
    reset_service()
    reset_allowlist_manager()
    reset_audit_logger()
    yield
    reset_service()
    reset_allowlist_manager()
    reset_audit_logger()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
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
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    return tmp_path


class TestCaptureToAuditWorkflow:
    """Test the capture → filter → audit logging workflow."""

    def test_capture_with_secrets_logs_to_audit(self, git_repo: Path, tmp_path: Path):
        """Test that capturing content with secrets logs detections and filters."""
        # Setup services
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        secrets_service = SecretsFilteringService(config=config, data_dir=data_dir)
        audit_logger = get_audit_logger(log_dir=data_dir / "audit")

        git_ops = GitOps(repo_path=git_repo)
        capture = CaptureService(git_ops=git_ops, secrets_service=secrets_service)

        # Capture content with SSN
        result = capture.capture(
            namespace="decisions",
            summary="User decision",
            content="User SSN is 123-45-6789",
        )

        # Verify capture succeeded with redaction
        assert result.success
        assert result.memory is not None
        assert "123-45-6789" not in result.memory.content
        assert "[REDACTED:pii_ssn]" in result.memory.content
        assert result.warning is not None

    def test_clean_content_no_audit_detections(self, git_repo: Path, tmp_path: Path):
        """Test that clean content doesn't log detections."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        secrets_service = SecretsFilteringService(config=config, data_dir=data_dir)
        audit_logger = get_audit_logger(log_dir=data_dir / "audit")

        git_ops = GitOps(repo_path=git_repo)
        capture = CaptureService(git_ops=git_ops, secrets_service=secrets_service)

        # Capture clean content
        result = capture.capture(
            namespace="decisions",
            summary="Clean decision",
            content="This is clean content",
        )

        assert result.success
        assert result.warning is None

        # No detection events in audit log
        detections = list(audit_logger.query(event_type="detection"))
        assert len(detections) == 0


class TestRetrospectiveScanWorkflow:
    """Test retrospective scanning of existing memories."""

    def test_scan_finds_secrets_in_stored_memories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that scanning finds secrets in previously stored memories."""
        # Disable entropy to avoid false positives on normal text
        monkeypatch.setenv("SECRETS_FILTER_ENTROPY_ENABLED", "false")
        reset_service()

        # Create index with memories containing secrets
        index = IndexService(tmp_path / "test.db")
        index.initialize()

        # Store memories directly (bypassing filter)
        memories = [
            Memory(
                id="decisions:abc123:0",
                commit_sha="abc123",
                namespace="decisions",
                timestamp=datetime.now(UTC),
                summary="Clean memory",
                content="No secrets here",
                spec="test",
                tags=(),
            ),
            Memory(
                id="decisions:def456:0",
                commit_sha="def456",
                namespace="decisions",
                timestamp=datetime.now(UTC),
                summary="Memory with SSN",
                content="User SSN: 123-45-6789",
                spec="test",
                tags=(),
            ),
            Memory(
                id="learnings:ghi789:0",
                commit_sha="ghi789",
                namespace="learnings",
                timestamp=datetime.now(UTC),
                summary="Memory with CC",
                content="Card: 4111111111111111",
                spec="test",
                tags=(),
            ),
        ]

        for mem in memories:
            index.insert(mem)

        # Scan for secrets
        service = get_secrets_filtering_service()
        findings = []

        for mem in index.get_all_memories():
            result = service.scan(mem.content)
            if result.had_secrets:
                findings.append(mem.id)

        # Should find 2 memories with secrets
        assert "decisions:def456:0" in findings  # SSN
        assert "learnings:ghi789:0" in findings  # CC
        assert "decisions:abc123:0" not in findings  # Clean

    def test_scan_with_namespace_filter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Test scanning a specific namespace only."""
        monkeypatch.setenv("SECRETS_FILTER_ENTROPY_ENABLED", "false")
        reset_service()

        index = IndexService(tmp_path / "test.db")
        index.initialize()

        # Store memories in different namespaces
        mem1 = Memory(
            id="decisions:abc:0",
            commit_sha="abc",
            namespace="decisions",
            timestamp=datetime.now(UTC),
            summary="Decision SSN",
            content="SSN: 123-45-6789",
            spec="test",
            tags=(),
        )
        mem2 = Memory(
            id="learnings:def:0",
            commit_sha="def",
            namespace="learnings",
            timestamp=datetime.now(UTC),
            summary="Learning SSN",
            content="SSN: 234-56-7890",
            spec="test",
            tags=(),
        )

        index.insert(mem1)
        index.insert(mem2)

        # Scan only decisions namespace
        service = get_secrets_filtering_service()
        findings = []

        for mem in index.get_all_memories(namespace="decisions"):
            result = service.scan(mem.content)
            if result.had_secrets:
                findings.append(mem.id)

        # Should only find the decisions memory
        assert len(findings) == 1
        assert "decisions:abc:0" in findings


class TestAllowlistWorkflow:
    """Test the complete allowlist workflow."""

    def test_add_to_allowlist_bypasses_filter(self, tmp_path: Path):
        """Test that allowlisted secrets pass through filtering."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        # First, verify secret is detected
        result = service.filter("SSN: 123-45-6789", source="test")
        assert result.action == FilterAction.REDACTED
        assert "123-45-6789" not in result.content

        # Add to allowlist
        service.allowlist.add(value="123-45-6789", reason="Test exemption")

        # Now should pass through
        reset_service()
        service2 = SecretsFilteringService(config=config, data_dir=data_dir)
        result2 = service2.filter("SSN: 123-45-6789", source="test")
        assert result2.action == FilterAction.ALLOWED
        assert "123-45-6789" in result2.content

    def test_allowlist_namespace_scoping(self, tmp_path: Path):
        """Test namespace-scoped allowlist entries."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        # Add namespace-scoped entry
        service.allowlist.add(
            value="123-45-6789",
            reason="Allowed in decisions only",
            namespace="decisions",
        )

        # Should be allowed in decisions namespace
        result1 = service.filter(
            "SSN: 123-45-6789", source="test", namespace="decisions"
        )
        assert "123-45-6789" in result1.content

        # Should be filtered in other namespaces
        result2 = service.filter(
            "SSN: 123-45-6789", source="test", namespace="learnings"
        )
        assert "123-45-6789" not in result2.content

    def test_remove_from_allowlist_re_enables_filter(self, tmp_path: Path):
        """Test that removing from allowlist re-enables filtering."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        # Add then remove
        entry = service.allowlist.add(value="123-45-6789", reason="Temporary")
        service.allowlist.remove(entry.secret_hash)

        # Should be filtered again
        result = service.filter("SSN: 123-45-6789", source="test")
        assert "123-45-6789" not in result.content

    def test_allowlist_persists_across_service_instances(self, tmp_path: Path):
        """Test that allowlist persists across service restarts."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service1 = SecretsFilteringService(config=config, data_dir=data_dir)
        service1.allowlist.add(value="123-45-6789", reason="Persistent")

        # Create new service instance
        reset_service()
        reset_allowlist_manager()
        service2 = SecretsFilteringService(config=config, data_dir=data_dir)

        # Should still be allowed
        result = service2.filter("SSN: 123-45-6789", source="test")
        assert "123-45-6789" in result.content


class TestAuditLogWorkflow:
    """Test audit logging across the workflow."""

    def test_audit_logs_detections_with_metadata(self, tmp_path: Path):
        """Test that audit log captures detection metadata."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        logger = get_audit_logger(log_dir=audit_dir)

        # Create a detection to log
        from git_notes_memory.security.models import SecretDetection, SecretType

        detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=5,
            end=16,
            confidence=0.95,
            detector="SSNDetector",
            line_number=1,
            secret_hash="abc123def456",
        )

        logger.log_detection(detection, namespace="decisions")

        # Query and verify
        entries = list(logger.query(event_type="detection"))
        assert len(entries) == 1
        assert entries[0].namespace == "decisions"
        assert SecretType.PII_SSN.value in entries[0].secret_types

    def test_audit_logs_filter_results(self, tmp_path: Path):
        """Test that filtering operations are logged."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        logger = get_audit_logger(log_dir=audit_dir)

        from git_notes_memory.security.models import (
            FilterResult,
            SecretDetection,
            SecretType,
        )

        detection = SecretDetection(
            secret_type=SecretType.PII_CREDIT_CARD,
            start=0,
            end=16,
            confidence=0.99,
            detector="CardDetector",
            line_number=1,
            secret_hash="card123",
        )

        result = FilterResult(
            content="[REDACTED:pii_credit_card]",
            action=FilterAction.REDACTED,
            detections=(detection,),
            original_length=16,
            filtered_length=25,
        )

        logger.log_filter_result(result, namespace="progress")

        # Query and verify
        entries = list(logger.query(event_type="filter"))
        assert len(entries) == 1
        assert entries[0].action == "redacted"

    def test_audit_logs_allowlist_changes(self, tmp_path: Path):
        """Test that allowlist changes are logged."""
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        logger = get_audit_logger(log_dir=audit_dir)

        # Log an add operation
        logger.log_allowlist_change(
            action="add",
            secret_hash="abc123",
            reason="False positive",
            added_by="test_user",
        )

        # Log a remove operation
        logger.log_allowlist_change(
            action="remove",
            secret_hash="abc123",
            reason="No longer needed",
            added_by="test_user",
        )

        # Query allowlist events
        entries = list(logger.query(event_type="allowlist"))
        assert len(entries) == 2
        assert entries[0].action in ("add", "remove")
        assert entries[1].action in ("add", "remove")

    def test_audit_query_with_time_filter(self, tmp_path: Path):
        """Test querying audit log with time filters."""
        from datetime import timedelta

        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        logger = get_audit_logger(log_dir=audit_dir)

        from git_notes_memory.security.models import SecretDetection, SecretType

        detection = SecretDetection(
            secret_type=SecretType.AWS_ACCESS_KEY,
            start=0,
            end=20,
            confidence=0.9,
            detector="AWSDetector",
            line_number=1,
            secret_hash="aws123",
        )

        logger.log_detection(detection)

        # Query for future - should return nothing
        future = datetime.now(UTC) + timedelta(hours=1)
        entries = list(logger.query(since=future))
        assert len(entries) == 0

        # Query for past - should return the entry
        past = datetime.now(UTC) - timedelta(hours=1)
        entries = list(logger.query(since=past))
        assert len(entries) == 1


class TestConfigurationChanges:
    """Test behavior changes with configuration updates."""

    def test_disable_pii_allows_ssn(self, tmp_path: Path):
        """Test that disabling PII detection allows SSN through."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(
            enabled=True,
            entropy_enabled=False,
            pii_enabled=False,  # Disable PII
        )
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        result = service.filter("SSN: 123-45-6789", source="test")

        # SSN should pass through since PII is disabled
        assert "123-45-6789" in result.content

    def test_warn_strategy_passes_content(self, tmp_path: Path):
        """Test that WARN strategy passes content unchanged."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(
            enabled=True,
            entropy_enabled=False,
            default_strategy=FilterStrategy.WARN,
        )
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        result = service.filter("SSN: 123-45-6789", source="test")

        # Content should be unchanged
        assert "123-45-6789" in result.content
        assert result.action == FilterAction.WARNED

    def test_mask_strategy_shows_partial(self, tmp_path: Path):
        """Test that MASK strategy shows partial content."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(
            enabled=True,
            entropy_enabled=False,
            default_strategy=FilterStrategy.MASK,
        )
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        result = service.filter("SSN: 123-45-6789", source="test")

        # Should be masked, not fully redacted
        assert "123-45-6789" not in result.content
        assert result.action == FilterAction.MASKED
        # Masked format shows partial
        assert "***" in result.content or "..." in result.content


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_content_passes(self, tmp_path: Path):
        """Test that empty content passes through."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True)
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        result = service.filter("", source="test")
        assert result.content == ""
        assert result.action == FilterAction.ALLOWED

    def test_very_long_content(self, tmp_path: Path):
        """Test filtering of very long content."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        # Create long content with SSN in the middle
        long_content = "A" * 10000 + " 123-45-6789 " + "B" * 10000

        result = service.filter(long_content, source="test")

        assert "123-45-6789" not in result.content
        assert "[REDACTED:pii_ssn]" in result.content

    def test_multiple_secrets_same_line(self, tmp_path: Path):
        """Test multiple secrets on the same line."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        content = "SSN: 123-45-6789, Card: 4111111111111111"

        result = service.filter(content, source="test")

        assert "123-45-6789" not in result.content
        assert "4111111111111111" not in result.content
        assert len(result.detections) >= 2

    def test_unicode_content_preserved(self, tmp_path: Path):
        """Test that unicode content is preserved."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        config = SecretsConfig(enabled=True, entropy_enabled=False)
        service = SecretsFilteringService(config=config, data_dir=data_dir)

        content = "User: 田中太郎, SSN: 123-45-6789, Note: 日本語テスト"

        result = service.filter(content, source="test")

        assert "123-45-6789" not in result.content
        assert "田中太郎" in result.content
        assert "日本語テスト" in result.content
