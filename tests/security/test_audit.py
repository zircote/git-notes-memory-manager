"""Tests for the AuditLogger."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from git_notes_memory.security.audit import (
    AuditEntry,
    AuditLogger,
    reset_audit_logger,
)
from git_notes_memory.security.models import (
    FilterAction,
    FilterResult,
    SecretDetection,
    SecretType,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton logger before each test."""
    reset_audit_logger()
    yield
    reset_audit_logger()


@pytest.fixture
def logger(tmp_path: Path) -> AuditLogger:
    """Create a fresh AuditLogger with temp directory."""
    return AuditLogger(log_dir=tmp_path)


@pytest.fixture
def sample_detection() -> SecretDetection:
    """Create a sample SecretDetection for testing."""
    return SecretDetection(
        secret_type=SecretType.PII_SSN,
        start=5,
        end=16,
        confidence=0.9,
        detector="SSN",
        line_number=1,
        secret_hash="abc123def456",
    )


@pytest.fixture
def sample_result(sample_detection: SecretDetection) -> FilterResult:
    """Create a sample FilterResult for testing."""
    return FilterResult(
        content="SSN: [REDACTED:pii_ssn]",
        action=FilterAction.REDACTED,
        detections=(sample_detection,),
        original_length=20,
        filtered_length=25,
    )


class TestAuditEntry:
    """Tests for AuditEntry dataclass."""

    def test_to_dict(self):
        """Test converting entry to dictionary."""
        entry = AuditEntry(
            timestamp="2024-01-15T10:30:00+00:00",
            event_type="detection",
            namespace="decisions",
            secret_types=("pii_ssn", "aws_access_key"),
            action="redacted",
            detection_count=2,
            source="capture",
            session_id="sess123",
            details={"key": "value"},
        )

        d = entry.to_dict()

        assert d["timestamp"] == "2024-01-15T10:30:00+00:00"
        assert d["event_type"] == "detection"
        assert d["namespace"] == "decisions"
        assert d["secret_types"] == ["pii_ssn", "aws_access_key"]
        assert d["action"] == "redacted"
        assert d["detection_count"] == 2
        assert d["source"] == "capture"
        assert d["session_id"] == "sess123"
        assert d["details"] == {"key": "value"}

    def test_from_dict(self):
        """Test creating entry from dictionary."""
        data = {
            "timestamp": "2024-01-15T10:30:00+00:00",
            "event_type": "filter",
            "namespace": "learnings",
            "secret_types": ["pii_ssn"],
            "action": "blocked",
            "detection_count": 1,
            "source": "memory",
            "session_id": "sess456",
            "details": {"foo": "bar"},
        }

        entry = AuditEntry.from_dict(data)

        assert entry.timestamp == "2024-01-15T10:30:00+00:00"
        assert entry.event_type == "filter"
        assert entry.namespace == "learnings"
        assert entry.secret_types == ("pii_ssn",)
        assert entry.action == "blocked"
        assert entry.detection_count == 1
        assert entry.source == "memory"
        assert entry.session_id == "sess456"
        assert entry.details == {"foo": "bar"}

    def test_from_dict_missing_fields(self):
        """Test from_dict handles missing fields gracefully."""
        data = {
            "timestamp": "2024-01-15T10:30:00+00:00",
            "event_type": "scan",
        }

        entry = AuditEntry.from_dict(data)

        assert entry.timestamp == "2024-01-15T10:30:00+00:00"
        assert entry.event_type == "scan"
        assert entry.namespace == ""
        assert entry.secret_types == ()
        assert entry.detection_count == 0


class TestAuditLoggerBasic:
    """Basic logging tests."""

    def test_log_detection(
        self, logger: AuditLogger, sample_detection: SecretDetection, tmp_path: Path
    ):
        """Test logging a detection."""
        logger.log_detection(
            sample_detection,
            source="test",
            namespace="decisions",
        )

        # Verify log file exists
        assert logger.log_file.exists()

        # Read and parse entry
        with logger.log_file.open() as f:
            line = f.readline()
            entry = json.loads(line)

        assert entry["event_type"] == "detection"
        assert entry["namespace"] == "decisions"
        assert entry["secret_types"] == ["pii_ssn"]
        assert entry["action"] == "detected"
        assert entry["detection_count"] == 1

    def test_log_filter_result(
        self, logger: AuditLogger, sample_result: FilterResult, tmp_path: Path
    ):
        """Test logging a filter result."""
        logger.log_filter_result(
            sample_result,
            source="capture",
            namespace="progress",
        )

        with logger.log_file.open() as f:
            line = f.readline()
            entry = json.loads(line)

        assert entry["event_type"] == "filter"
        assert entry["namespace"] == "progress"
        assert entry["action"] == "redacted"
        assert entry["detection_count"] == 1
        assert entry["details"]["original_length"] == 20
        assert entry["details"]["filtered_length"] == 25

    def test_log_filter_result_no_secrets(self, logger: AuditLogger, tmp_path: Path):
        """Test that clean content isn't logged."""
        clean_result = FilterResult(
            content="clean",
            action=FilterAction.ALLOWED,
            original_length=5,
            filtered_length=5,
        )

        logger.log_filter_result(clean_result, source="test")

        # Log file should not exist (nothing logged)
        assert not logger.log_file.exists()

    def test_log_scan(
        self, logger: AuditLogger, sample_result: FilterResult, tmp_path: Path
    ):
        """Test logging a scan operation."""
        logger.log_scan(
            sample_result,
            source="retrospective",
            namespace="decisions",
        )

        with logger.log_file.open() as f:
            line = f.readline()
            entry = json.loads(line)

        assert entry["event_type"] == "scan"
        assert entry["action"] == "scanned"
        assert entry["details"]["had_secrets"] is True

    def test_log_allowlist_change(self, logger: AuditLogger, tmp_path: Path):
        """Test logging allowlist modifications."""
        logger.log_allowlist_change(
            action="add",
            secret_hash="abc123def456789",
            reason="Test allowlist",
            namespace="decisions",
            added_by="test_user",
        )

        with logger.log_file.open() as f:
            line = f.readline()
            entry = json.loads(line)

        assert entry["event_type"] == "allowlist"
        assert entry["action"] == "add"
        assert entry["namespace"] == "decisions"
        # Hash should be truncated for privacy (first 16 chars)
        assert entry["details"]["secret_hash"] == "abc123def456789..."
        assert entry["details"]["reason"] == "Test allowlist"
        assert entry["details"]["added_by"] == "test_user"


class TestSessionId:
    """Tests for session ID correlation."""

    def test_set_session_id(
        self, logger: AuditLogger, sample_detection: SecretDetection
    ):
        """Test that session ID is included in logs."""
        logger.set_session_id("session-abc-123")
        logger.log_detection(sample_detection)

        with logger.log_file.open() as f:
            entry = json.loads(f.readline())

        assert entry["session_id"] == "session-abc-123"

    def test_session_id_property(self, logger: AuditLogger):
        """Test the session_id property."""
        assert logger.session_id == ""
        logger.set_session_id("test-session")
        assert logger.session_id == "test-session"


class TestLogRotation:
    """Tests for log file rotation."""

    def test_rotation_on_size(self, tmp_path: Path):
        """Test that logs rotate when size limit is reached."""
        # Create logger with small max size
        logger = AuditLogger(
            log_dir=tmp_path,
            max_file_size=500,  # 500 bytes
            max_files=3,
        )

        detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=10,
            confidence=1.0,
            detector="test",
            line_number=1,
            secret_hash="hash123",
        )

        # Write enough entries to trigger rotation
        for _ in range(20):
            logger.log_detection(detection, source="test")

        # Check that rotation occurred
        rotated_1 = tmp_path / "secrets-audit.1.jsonl"
        assert rotated_1.exists()

    def test_max_files_limit(self, tmp_path: Path):
        """Test that old rotated files are deleted."""
        logger = AuditLogger(
            log_dir=tmp_path,
            max_file_size=200,
            max_files=2,
        )

        detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=10,
            confidence=1.0,
            detector="test",
            line_number=1,
            secret_hash="hash123",
        )

        # Write many entries
        for _ in range(50):
            logger.log_detection(detection, source="test")

        # Should not have more than max_files rotated files
        rotated_files = list(tmp_path.glob("secrets-audit.*.jsonl"))
        assert len(rotated_files) <= 2


class TestQuery:
    """Tests for querying audit logs."""

    def test_query_all(self, logger: AuditLogger, sample_detection: SecretDetection):
        """Test querying all entries."""
        logger.log_detection(sample_detection, namespace="decisions")
        logger.log_detection(sample_detection, namespace="learnings")
        logger.log_detection(sample_detection, namespace="progress")

        entries = list(logger.query())

        assert len(entries) == 3

    def test_query_by_event_type(
        self,
        logger: AuditLogger,
        sample_detection: SecretDetection,
        sample_result: FilterResult,
    ):
        """Test filtering by event type."""
        logger.log_detection(sample_detection)
        logger.log_filter_result(sample_result)
        logger.log_scan(sample_result)

        detections = list(logger.query(event_type="detection"))
        filters = list(logger.query(event_type="filter"))
        scans = list(logger.query(event_type="scan"))

        assert len(detections) == 1
        assert len(filters) == 1
        assert len(scans) == 1

    def test_query_by_namespace(
        self, logger: AuditLogger, sample_detection: SecretDetection
    ):
        """Test filtering by namespace."""
        logger.log_detection(sample_detection, namespace="decisions")
        logger.log_detection(sample_detection, namespace="decisions")
        logger.log_detection(sample_detection, namespace="learnings")

        entries = list(logger.query(namespace="decisions"))

        assert len(entries) == 2

    def test_query_by_time_range(
        self, logger: AuditLogger, sample_detection: SecretDetection
    ):
        """Test filtering by time range."""
        # Log some entries
        logger.log_detection(sample_detection)
        logger.log_detection(sample_detection)

        # Query with since=now should return nothing
        future = datetime.now(UTC) + timedelta(hours=1)
        entries = list(logger.query(since=future))

        assert len(entries) == 0

        # Query with until=future should return all
        entries = list(logger.query(until=future))
        assert len(entries) == 2

    def test_query_limit(self, logger: AuditLogger, sample_detection: SecretDetection):
        """Test limit parameter."""
        for _ in range(10):
            logger.log_detection(sample_detection)

        entries = list(logger.query(limit=5))

        assert len(entries) == 5

    def test_query_by_secret_type(self, logger: AuditLogger):
        """Test filtering by secret type."""
        ssn = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=10,
            confidence=1.0,
            detector="test",
            line_number=1,
            secret_hash="h1",
        )
        cc = SecretDetection(
            secret_type=SecretType.PII_CREDIT_CARD,
            start=0,
            end=16,
            confidence=1.0,
            detector="test",
            line_number=1,
            secret_hash="h2",
        )

        logger.log_detection(ssn)
        logger.log_detection(cc)

        entries = list(logger.query(secret_type=SecretType.PII_SSN))

        assert len(entries) == 1
        assert entries[0].secret_types == ("pii_ssn",)


class TestGetStats:
    """Tests for getting statistics."""

    def test_get_stats(self, logger: AuditLogger, sample_detection: SecretDetection):
        """Test getting statistics from the log."""
        logger.log_detection(sample_detection, namespace="decisions")
        logger.log_detection(sample_detection, namespace="decisions")
        logger.log_detection(sample_detection, namespace="learnings")

        stats = logger.get_stats()

        assert stats["total_events"] == 3
        assert stats["detections"] == 3
        assert stats["by_namespace"]["decisions"] == 2
        assert stats["by_namespace"]["learnings"] == 1


class TestThreadSafety:
    """Tests for thread-safe operation."""

    def test_concurrent_writes(
        self, logger: AuditLogger, sample_detection: SecretDetection
    ):
        """Test that concurrent writes don't corrupt the log."""
        num_threads = 10
        writes_per_thread = 20

        def write_entries():
            for _ in range(writes_per_thread):
                logger.log_detection(sample_detection)
                time.sleep(0.001)  # Small delay to encourage interleaving

        threads = [threading.Thread(target=write_entries) for _ in range(num_threads)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All entries should be written
        entries = list(logger.query(limit=1000))
        assert len(entries) == num_threads * writes_per_thread

        # Each line should be valid JSON
        with logger.log_file.open() as f:
            for line in f:
                json.loads(line)  # Should not raise
