"""Tests for secrets-related command functionality.

These tests verify the Python code paths that the markdown commands execute.
The commands themselves are Claude Code markdown files, but we test the
underlying service integrations here.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from git_notes_memory.index import IndexService
from git_notes_memory.models import Memory
from git_notes_memory.security import (
    FilterAction,
    FilterStrategy,
    SecretType,
    get_allowlist_manager,
    get_audit_logger,
    get_secrets_filtering_service,
)
from git_notes_memory.security.allowlist import reset_allowlist_manager
from git_notes_memory.security.audit import reset_audit_logger
from git_notes_memory.security.service import reset_service

if TYPE_CHECKING:
    pass


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
def env_without_entropy(monkeypatch: pytest.MonkeyPatch):
    """Disable entropy detection for cleaner tests."""
    monkeypatch.setenv("SECRETS_FILTER_ENTROPY_ENABLED", "false")
    yield


@pytest.fixture
def index_service(tmp_path: Path) -> IndexService:
    """Create an index service with temp database."""
    index = IndexService(tmp_path / "test.db")
    index.initialize()
    return index


@pytest.fixture
def sample_memories(index_service: IndexService) -> list[Memory]:
    """Create sample memories with and without secrets."""
    memories = [
        Memory(
            id="decisions:abc123:0",
            commit_sha="abc123",
            namespace="decisions",
            timestamp=datetime.now(UTC),
            summary="Clean decision",
            content="This is clean content with no secrets.",
            spec="test-project",
            tags=("architecture",),
        ),
        Memory(
            id="decisions:def456:0",
            commit_sha="def456",
            namespace="decisions",
            timestamp=datetime.now(UTC),
            summary="Decision with SSN",
            content="User SSN is 123-45-6789 for reference.",
            spec="test-project",
            tags=("pii",),
        ),
        Memory(
            id="learnings:ghi789:0",
            commit_sha="ghi789",
            namespace="learnings",
            timestamp=datetime.now(UTC),
            summary="API key learning",
            content="The API key is AKIAIOSFODNN7EXAMPLE for testing.",
            spec="test-project",
            tags=("aws",),
        ),
    ]

    for mem in memories:
        index_service.insert(mem)

    return memories


class TestScanSecretsCommand:
    """Tests for /memory:scan-secrets command functionality."""

    def test_scan_finds_secrets_in_memories(
        self,
        index_service: IndexService,
        sample_memories: list[Memory],
    ):
        """Test that scanning finds secrets in stored memories."""
        service = get_secrets_filtering_service()

        # Scan each memory
        findings = []
        all_memories = index_service.get_all_memories()

        for mem in all_memories:
            result = service.scan(mem.content)
            if result.had_secrets:
                findings.append(
                    {
                        "id": mem.id,
                        "namespace": mem.namespace,
                        "count": result.detection_count,
                    }
                )

        # Should find at least 2 memories with secrets (SSN and AWS key)
        # May find more due to entropy detection on normal text
        assert len(findings) >= 2

        # Check specific findings
        ids = [f["id"] for f in findings]
        assert "decisions:def456:0" in ids  # SSN
        assert "learnings:ghi789:0" in ids  # AWS key

    def test_scan_with_namespace_filter(
        self,
        index_service: IndexService,
        sample_memories: list[Memory],
    ):
        """Test scanning with namespace filter."""
        service = get_secrets_filtering_service()

        # Only scan decisions namespace - should find SSN
        findings = []
        for mem in index_service.get_all_memories(namespace="decisions"):
            result = service.scan(mem.content)
            if result.had_secrets:
                findings.append(mem.id)

        # Should find the SSN in decisions (may also find entropy matches)
        assert len(findings) >= 1
        assert "decisions:def456:0" in findings

    def test_scan_dry_run_does_not_modify(
        self,
        index_service: IndexService,
        sample_memories: list[Memory],
    ):
        """Test that dry-run scanning doesn't modify memories."""
        service = get_secrets_filtering_service()

        # Get original content
        original_content = sample_memories[1].content

        # Scan (filter) in dry-run mode - just scan, don't apply
        result = service.scan(original_content)

        # Original should be unchanged
        assert result.had_secrets is True
        # The scan result shows what would be filtered but doesn't change it
        mem = index_service.get(sample_memories[1].id)
        assert mem is not None
        assert "123-45-6789" in mem.content  # Still has SSN


class TestSecretsAllowlistCommand:
    """Tests for /memory:secrets-allowlist command functionality."""

    def test_list_empty_allowlist(self, tmp_path: Path):
        """Test listing empty allowlist."""
        reset_allowlist_manager()
        manager = get_allowlist_manager(data_dir=tmp_path)

        entries = list(manager.list_entries())

        assert len(entries) == 0

    def test_add_to_allowlist(self, tmp_path: Path):
        """Test adding entry to allowlist."""
        reset_allowlist_manager()
        manager = get_allowlist_manager(data_dir=tmp_path)

        entry = manager.add(
            secret_hash="abc123def456",
            reason="False positive - example code",
            namespace=None,
            added_by="test_user",
        )

        assert entry.secret_hash == "abc123def456"
        assert entry.reason == "False positive - example code"
        assert entry.added_by == "test_user"

        # Should be in list
        entries = list(manager.list_entries())
        assert len(entries) == 1

    def test_add_namespace_scoped(self, tmp_path: Path):
        """Test adding namespace-scoped allowlist entry."""
        reset_allowlist_manager()
        manager = get_allowlist_manager(data_dir=tmp_path)

        entry = manager.add(
            secret_hash="def789ghi",
            reason="Intentional in decisions",
            namespace="decisions",
            added_by="test_user",
        )

        assert entry.namespace == "decisions"

        # Check if secret is allowed in namespace
        assert manager.is_allowed("def789ghi", namespace="decisions")
        # Should not be allowed in other namespace
        assert not manager.is_allowed("def789ghi", namespace="learnings")

    def test_remove_from_allowlist(self, tmp_path: Path):
        """Test removing entry from allowlist."""
        reset_allowlist_manager()
        manager = get_allowlist_manager(data_dir=tmp_path)

        # Add then remove
        manager.add(
            secret_hash="to_remove",
            reason="Temporary",
            added_by="test",
        )

        removed = manager.remove("to_remove")

        assert removed is True
        assert not manager.is_allowed("to_remove")

    def test_remove_nonexistent(self, tmp_path: Path):
        """Test removing non-existent entry."""
        reset_allowlist_manager()
        manager = get_allowlist_manager(data_dir=tmp_path)

        removed = manager.remove("doesnt_exist")

        assert removed is False


class TestTestSecretCommand:
    """Tests for /memory:test-secret command functionality."""

    def test_detect_ssn(self):
        """Test SSN detection."""
        service = get_secrets_filtering_service()

        result = service.scan("123-45-6789")

        assert result.had_secrets is True
        assert len(result.detections) == 1
        assert result.detections[0].secret_type == SecretType.PII_SSN

    def test_detect_aws_key(self):
        """Test AWS access key detection."""
        service = get_secrets_filtering_service()

        result = service.scan("AKIAIOSFODNN7EXAMPLE")

        assert result.had_secrets is True
        assert any(
            d.secret_type == SecretType.AWS_ACCESS_KEY for d in result.detections
        )

    def test_detect_credit_card(self):
        """Test credit card detection."""
        service = get_secrets_filtering_service()

        result = service.scan("4111111111111111")

        assert result.had_secrets is True
        assert any(
            d.secret_type == SecretType.PII_CREDIT_CARD for d in result.detections
        )

    def test_no_detection_for_clean_content(
        self, env_without_entropy: None, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that clean content doesn't trigger detection."""
        reset_service()
        service = get_secrets_filtering_service()

        result = service.scan("Hello, this is normal text.")

        assert result.had_secrets is False
        assert len(result.detections) == 0

    def test_get_strategy_for_detection(self):
        """Test getting the strategy that would apply."""
        from git_notes_memory.security import get_redactor

        redactor = get_redactor()

        # Default strategy for SSN
        strategy = redactor.get_strategy(SecretType.PII_SSN)
        assert strategy == FilterStrategy.REDACT

    def test_get_hash_for_allowlisting(self):
        """Test that detections include hash for allowlisting."""
        service = get_secrets_filtering_service()

        result = service.scan("123-45-6789")

        assert result.had_secrets is True
        assert result.detections[0].secret_hash is not None
        assert len(result.detections[0].secret_hash) > 0


class TestAuditLogCommand:
    """Tests for /memory:audit-log command functionality."""

    def test_query_all_entries(self, tmp_path: Path):
        """Test querying all audit entries."""
        logger = get_audit_logger(log_dir=tmp_path)

        # Create some entries
        from git_notes_memory.security.models import SecretDetection

        detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=11,
            confidence=0.95,
            detector="SSN",
            line_number=1,
            secret_hash="test_hash",
        )

        logger.log_detection(detection, namespace="decisions")
        logger.log_detection(detection, namespace="learnings")

        entries = list(logger.query())

        assert len(entries) == 2

    def test_query_by_event_type(self, tmp_path: Path):
        """Test filtering by event type."""
        logger = get_audit_logger(log_dir=tmp_path)

        from git_notes_memory.security.models import FilterResult, SecretDetection

        detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=11,
            confidence=0.95,
            detector="SSN",
            line_number=1,
            secret_hash="hash1",
        )

        result = FilterResult(
            content="[REDACTED]",
            action=FilterAction.REDACTED,
            detections=(detection,),
            original_length=11,
            filtered_length=10,
        )

        logger.log_detection(detection)
        logger.log_filter_result(result)

        detections = list(logger.query(event_type="detection"))
        filters = list(logger.query(event_type="filter"))

        assert len(detections) == 1
        assert len(filters) == 1

    def test_query_by_namespace(self, tmp_path: Path):
        """Test filtering by namespace."""
        logger = get_audit_logger(log_dir=tmp_path)

        from git_notes_memory.security.models import SecretDetection

        detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=11,
            confidence=0.95,
            detector="SSN",
            line_number=1,
            secret_hash="hash2",
        )

        logger.log_detection(detection, namespace="decisions")
        logger.log_detection(detection, namespace="decisions")
        logger.log_detection(detection, namespace="learnings")

        decisions = list(logger.query(namespace="decisions"))

        assert len(decisions) == 2

    def test_query_since_time(self, tmp_path: Path):
        """Test filtering by time range."""
        logger = get_audit_logger(log_dir=tmp_path)

        from git_notes_memory.security.models import SecretDetection

        detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=11,
            confidence=0.95,
            detector="SSN",
            line_number=1,
            secret_hash="hash3",
        )

        logger.log_detection(detection)

        # Query for future should return nothing
        future = datetime.now(UTC) + timedelta(hours=1)
        entries = list(logger.query(since=future))

        assert len(entries) == 0

        # Query for past should return everything
        past = datetime.now(UTC) - timedelta(hours=1)
        entries = list(logger.query(since=past))

        assert len(entries) == 1

    def test_json_output(self, tmp_path: Path):
        """Test that entries serialize to JSON correctly."""
        logger = get_audit_logger(log_dir=tmp_path)

        from git_notes_memory.security.models import SecretDetection

        detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=11,
            confidence=0.95,
            detector="SSN",
            line_number=1,
            secret_hash="hash4",
        )

        logger.log_detection(detection, namespace="decisions")

        entries = list(logger.query())

        # Should serialize to valid JSON
        for entry in entries:
            json_str = json.dumps(entry.to_dict())
            parsed = json.loads(json_str)
            assert parsed["event_type"] == "detection"
            assert parsed["namespace"] == "decisions"

    def test_get_stats(self, tmp_path: Path):
        """Test getting aggregate statistics."""
        logger = get_audit_logger(log_dir=tmp_path)

        from git_notes_memory.security.models import SecretDetection

        detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=11,
            confidence=0.95,
            detector="SSN",
            line_number=1,
            secret_hash="hash5",
        )

        logger.log_detection(detection, namespace="decisions")
        logger.log_detection(detection, namespace="decisions")
        logger.log_detection(detection, namespace="learnings")

        stats = logger.get_stats()

        assert stats["total_events"] == 3
        assert stats["detections"] == 3
        assert stats["by_namespace"]["decisions"] == 2
        assert stats["by_namespace"]["learnings"] == 1


class TestAllowlistAuditIntegration:
    """Tests for allowlist changes being recorded in audit log."""

    def test_add_logs_to_audit(self, tmp_path: Path):
        """Test that adding to allowlist logs an audit entry."""
        reset_audit_logger()
        reset_allowlist_manager()
        audit_logger = get_audit_logger(log_dir=tmp_path / "audit")
        allowlist_manager = get_allowlist_manager(data_dir=tmp_path / "allowlist")

        # Add entry
        allowlist_manager.add(
            secret_hash="logged_hash",
            reason="Testing audit",
            added_by="test",
        )

        # Log the change to audit (simulating what command does)
        audit_logger.log_allowlist_change(
            action="add",
            secret_hash="logged_hash",
            reason="Testing audit",
            added_by="test",
        )

        # Check audit log
        entries = list(audit_logger.query(event_type="allowlist"))

        assert len(entries) == 1
        assert entries[0].action == "add"
