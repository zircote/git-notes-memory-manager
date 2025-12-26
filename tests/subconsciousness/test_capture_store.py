"""Tests for the implicit capture store."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from git_notes_memory.subconsciousness.capture_store import (
    CaptureStore,
    CaptureStoreError,
    create_capture,
)
from git_notes_memory.subconsciousness.models import (
    CaptureConfidence,
    ImplicitMemory,
    ReviewStatus,
    ThreatDetection,
    ThreatLevel,
)


@pytest.fixture
def capture_store(tmp_path: Path) -> Generator[CaptureStore, None, None]:
    """Create a temporary capture store for testing."""
    db_path = tmp_path / "test_captures.db"
    store = CaptureStore(db_path=db_path)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def sample_memory() -> ImplicitMemory:
    """Create a sample implicit memory for testing."""
    return ImplicitMemory(
        namespace="decisions",
        summary="Use PostgreSQL for persistence",
        content="## Context\nWe decided to use PostgreSQL for the database.",
        confidence=CaptureConfidence(
            overall=0.85,
            relevance=0.9,
            actionability=0.8,
            novelty=0.7,
            specificity=0.85,
            coherence=0.95,
        ),
        source_hash="abc123def456",
        source_range=(10, 25),
        rationale="Contains clear decision with context",
        tags=("database", "architecture"),
    )


class TestCaptureStoreInitialization:
    """Tests for CaptureStore initialization."""

    def test_initialize_creates_db(self, tmp_path: Path) -> None:
        """Test that initialize creates the database file."""
        db_path = tmp_path / "test.db"
        store = CaptureStore(db_path=db_path)
        store.initialize()

        assert db_path.exists()
        assert store.is_initialized
        store.close()

    def test_initialize_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test that initialize creates parent directories."""
        db_path = tmp_path / "nested" / "dirs" / "test.db"
        store = CaptureStore(db_path=db_path)
        store.initialize()

        assert db_path.exists()
        store.close()

    def test_initialize_idempotent(self, capture_store: CaptureStore) -> None:
        """Test that initialize can be called multiple times."""
        # Already initialized by fixture
        capture_store.initialize()  # Should not raise
        assert capture_store.is_initialized

    def test_close_resets_state(self, tmp_path: Path) -> None:
        """Test that close resets initialization state."""
        db_path = tmp_path / "test.db"
        store = CaptureStore(db_path=db_path)
        store.initialize()
        assert store.is_initialized

        store.close()
        assert not store.is_initialized


class TestCaptureStoreSave:
    """Tests for saving captures."""

    def test_save_basic(
        self,
        capture_store: CaptureStore,
        sample_memory: ImplicitMemory,
    ) -> None:
        """Test saving a basic capture."""
        capture = create_capture(sample_memory, session_id="session-123")
        saved_id = capture_store.save(capture)

        assert saved_id == capture.id
        assert saved_id.startswith("cap-")

    def test_save_duplicate_raises(
        self,
        capture_store: CaptureStore,
        sample_memory: ImplicitMemory,
    ) -> None:
        """Test that saving duplicate ID raises error."""
        capture = create_capture(sample_memory)
        capture_store.save(capture)

        with pytest.raises(CaptureStoreError, match="Duplicate"):
            capture_store.save(capture)

    def test_save_without_optional_fields(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test saving capture without optional fields."""
        memory = ImplicitMemory(
            namespace="learnings",
            summary="Learned something",
            content="Content here",
            confidence=CaptureConfidence(overall=0.5),
            source_hash="hash123",
        )
        capture = create_capture(memory)
        saved_id = capture_store.save(capture)

        # Should be retrievable
        retrieved = capture_store.get(saved_id)
        assert retrieved is not None
        assert retrieved.memory.source_range is None
        assert retrieved.memory.rationale == ""
        assert retrieved.memory.tags == ()


class TestCaptureStoreGet:
    """Tests for retrieving captures."""

    def test_get_existing(
        self,
        capture_store: CaptureStore,
        sample_memory: ImplicitMemory,
    ) -> None:
        """Test retrieving an existing capture."""
        capture = create_capture(sample_memory, session_id="sess-001")
        capture_store.save(capture)

        retrieved = capture_store.get(capture.id)

        assert retrieved is not None
        assert retrieved.id == capture.id
        assert retrieved.memory.namespace == "decisions"
        assert retrieved.memory.summary == "Use PostgreSQL for persistence"
        assert retrieved.memory.confidence.overall == 0.85
        assert retrieved.memory.source_range == (10, 25)
        assert retrieved.memory.tags == ("database", "architecture")
        assert retrieved.session_id == "sess-001"

    def test_get_nonexistent(self, capture_store: CaptureStore) -> None:
        """Test retrieving a non-existent capture."""
        result = capture_store.get("nonexistent-id")
        assert result is None

    def test_get_preserves_threat_detection(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test that threat detection is preserved on round-trip."""
        memory = ImplicitMemory(
            namespace="test",
            summary="Test",
            content="Content",
            confidence=CaptureConfidence(overall=0.5),
            source_hash="hash",
        )
        threat = ThreatDetection.blocked(
            level=ThreatLevel.HIGH,
            patterns=["injection", "exfil"],
            explanation="Detected suspicious patterns",
        )
        capture = create_capture(memory, threat_detection=threat)
        capture_store.save(capture)

        retrieved = capture_store.get(capture.id)

        assert retrieved is not None
        assert retrieved.threat_detection.level == ThreatLevel.HIGH
        assert retrieved.threat_detection.should_block is True
        assert "injection" in retrieved.threat_detection.patterns_found


class TestCaptureStoreGetPending:
    """Tests for retrieving pending captures."""

    def test_get_pending_empty(self, capture_store: CaptureStore) -> None:
        """Test getting pending from empty store."""
        pending = capture_store.get_pending()
        assert pending == []

    def test_get_pending_basic(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test getting pending captures."""
        # Create captures with different confidence
        for i, conf in enumerate([0.9, 0.5, 0.7]):
            memory = ImplicitMemory(
                namespace="test",
                summary=f"Test {i}",
                content="Content",
                confidence=CaptureConfidence(overall=conf),
                source_hash=f"hash{i}",
            )
            capture = create_capture(memory)
            capture_store.save(capture)

        pending = capture_store.get_pending()

        # Should be ordered by confidence descending
        assert len(pending) == 3
        assert pending[0].memory.confidence.overall == 0.9
        assert pending[1].memory.confidence.overall == 0.7
        assert pending[2].memory.confidence.overall == 0.5

    def test_get_pending_excludes_expired(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test that expired captures are excluded by default."""
        memory = ImplicitMemory(
            namespace="test",
            summary="Test",
            content="Content",
            confidence=CaptureConfidence(overall=0.8),
            source_hash="hash",
        )
        # Create already-expired capture manually
        from git_notes_memory.subconsciousness.models import ImplicitCapture

        capture = ImplicitCapture(
            id="cap-expired",
            memory=memory,
            status=ReviewStatus.PENDING,
            threat_detection=ThreatDetection.safe(),
            created_at=datetime.now(UTC) - timedelta(days=10),
            expires_at=datetime.now(UTC) - timedelta(days=1),  # Expired
        )
        capture_store.save(capture)

        # Should not appear in pending (default excludes expired)
        pending = capture_store.get_pending()
        assert len(pending) == 0

        # But should appear with include_expired=True
        pending_with_expired = capture_store.get_pending(include_expired=True)
        assert len(pending_with_expired) == 1

    def test_get_pending_excludes_reviewed(
        self,
        capture_store: CaptureStore,
        sample_memory: ImplicitMemory,
    ) -> None:
        """Test that reviewed captures are excluded."""
        capture = create_capture(sample_memory)
        capture_store.save(capture)

        # Approve it
        capture_store.update_status(capture.id, ReviewStatus.APPROVED)

        pending = capture_store.get_pending()
        assert len(pending) == 0

    def test_get_pending_limit(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test limit on pending captures."""
        # Create 5 captures
        for i in range(5):
            memory = ImplicitMemory(
                namespace="test",
                summary=f"Test {i}",
                content="Content",
                confidence=CaptureConfidence(overall=0.5),
                source_hash=f"hash{i}",
            )
            capture_store.save(create_capture(memory))

        pending = capture_store.get_pending(limit=3)
        assert len(pending) == 3


class TestCaptureStoreUpdateStatus:
    """Tests for updating capture status."""

    def test_update_to_approved(
        self,
        capture_store: CaptureStore,
        sample_memory: ImplicitMemory,
    ) -> None:
        """Test approving a capture."""
        capture = create_capture(sample_memory)
        capture_store.save(capture)

        result = capture_store.update_status(capture.id, ReviewStatus.APPROVED)

        assert result is True
        retrieved = capture_store.get(capture.id)
        assert retrieved is not None
        assert retrieved.status == ReviewStatus.APPROVED
        assert retrieved.reviewed_at is not None

    def test_update_to_rejected(
        self,
        capture_store: CaptureStore,
        sample_memory: ImplicitMemory,
    ) -> None:
        """Test rejecting a capture."""
        capture = create_capture(sample_memory)
        capture_store.save(capture)

        result = capture_store.update_status(capture.id, ReviewStatus.REJECTED)

        assert result is True
        retrieved = capture_store.get(capture.id)
        assert retrieved is not None
        assert retrieved.status == ReviewStatus.REJECTED

    def test_update_nonexistent(self, capture_store: CaptureStore) -> None:
        """Test updating non-existent capture returns False."""
        result = capture_store.update_status("nonexistent", ReviewStatus.APPROVED)
        assert result is False


class TestCaptureStoreDelete:
    """Tests for deleting captures."""

    def test_delete_existing(
        self,
        capture_store: CaptureStore,
        sample_memory: ImplicitMemory,
    ) -> None:
        """Test deleting an existing capture."""
        capture = create_capture(sample_memory)
        capture_store.save(capture)

        result = capture_store.delete(capture.id)

        assert result is True
        assert capture_store.get(capture.id) is None

    def test_delete_nonexistent(self, capture_store: CaptureStore) -> None:
        """Test deleting non-existent capture returns False."""
        result = capture_store.delete("nonexistent")
        assert result is False


class TestCaptureStoreExpiration:
    """Tests for capture expiration."""

    def test_expire_old_captures(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test marking expired captures."""
        from git_notes_memory.subconsciousness.models import ImplicitCapture

        # Create an already-expired capture
        memory = ImplicitMemory(
            namespace="test",
            summary="Test",
            content="Content",
            confidence=CaptureConfidence(overall=0.5),
            source_hash="hash",
        )
        expired = ImplicitCapture(
            id="cap-old",
            memory=memory,
            status=ReviewStatus.PENDING,
            threat_detection=ThreatDetection.safe(),
            created_at=datetime.now(UTC) - timedelta(days=10),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        capture_store.save(expired)

        # Create a non-expired capture
        valid = create_capture(memory)
        capture_store.save(valid)

        # Run expiration
        count = capture_store.expire_old_captures()

        assert count == 1
        retrieved = capture_store.get("cap-old")
        assert retrieved is not None
        assert retrieved.status == ReviewStatus.EXPIRED


class TestCaptureStoreSourceHash:
    """Tests for source hash deduplication."""

    def test_get_by_source_hash(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test finding captures by source hash."""
        hash1 = "abc123"
        hash2 = "def456"

        for i, h in enumerate([hash1, hash1, hash2]):
            memory = ImplicitMemory(
                namespace="test",
                summary=f"Test {i}",
                content="Content",
                confidence=CaptureConfidence(overall=0.5),
                source_hash=h,
            )
            capture_store.save(create_capture(memory))

        # Should find 2 with hash1
        matches = capture_store.get_by_source_hash(hash1)
        assert len(matches) == 2

        # Should find 1 with hash2
        matches = capture_store.get_by_source_hash(hash2)
        assert len(matches) == 1

        # Should find 0 with unknown hash
        matches = capture_store.get_by_source_hash("unknown")
        assert len(matches) == 0


class TestCaptureStoreStats:
    """Tests for store statistics."""

    def test_count_by_status(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test counting captures by status."""
        # Create captures with different statuses
        for _ in range(3):
            memory = ImplicitMemory(
                namespace="test",
                summary="Test",
                content="Content",
                confidence=CaptureConfidence(overall=0.5),
                source_hash=f"hash{_}",
            )
            capture_store.save(create_capture(memory))

        # Approve one
        pending = capture_store.get_pending()
        capture_store.update_status(pending[0].id, ReviewStatus.APPROVED)

        counts = capture_store.count_by_status()

        assert counts["pending"] == 2
        assert counts["approved"] == 1


class TestCreateCapture:
    """Tests for the create_capture helper function."""

    def test_creates_unique_id(self, sample_memory: ImplicitMemory) -> None:
        """Test that each capture gets a unique ID."""
        capture1 = create_capture(sample_memory)
        capture2 = create_capture(sample_memory)

        assert capture1.id != capture2.id
        assert capture1.id.startswith("cap-")
        assert capture2.id.startswith("cap-")

    def test_sets_timestamps(self, sample_memory: ImplicitMemory) -> None:
        """Test that timestamps are set correctly."""
        before = datetime.now(UTC)
        capture = create_capture(sample_memory, expiration_days=7)
        after = datetime.now(UTC)

        assert before <= capture.created_at <= after
        assert capture.expires_at > capture.created_at
        # Should expire in approximately 7 days
        expected_expiry = capture.created_at + timedelta(days=7)
        assert abs((capture.expires_at - expected_expiry).total_seconds()) < 1

    def test_sets_default_threat_detection(
        self,
        sample_memory: ImplicitMemory,
    ) -> None:
        """Test that default threat detection is safe."""
        capture = create_capture(sample_memory)

        assert capture.threat_detection.level == ThreatLevel.NONE
        assert capture.threat_detection.should_block is False

    def test_sets_pending_status(self, sample_memory: ImplicitMemory) -> None:
        """Test that status starts as pending."""
        capture = create_capture(sample_memory)

        assert capture.status == ReviewStatus.PENDING


class TestCaptureStoreCleanup:
    """Tests for cleanup of old reviewed captures."""

    def test_cleanup_reviewed_removes_old_approved(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test that old approved captures are cleaned up."""
        from git_notes_memory.subconsciousness.models import ImplicitCapture

        # Create an approved capture with old reviewed_at
        memory = ImplicitMemory(
            namespace="test",
            summary="Old approved",
            content="Content",
            confidence=CaptureConfidence(overall=0.8),
            source_hash="hash-old",
        )
        old_capture = ImplicitCapture(
            id="cap-old-approved",
            memory=memory,
            status=ReviewStatus.APPROVED,
            threat_detection=ThreatDetection.safe(),
            created_at=datetime.now(UTC) - timedelta(days=60),
            expires_at=datetime.now(UTC) - timedelta(days=53),
            reviewed_at=datetime.now(UTC) - timedelta(days=45),  # 45 days ago
        )
        capture_store.save(old_capture)

        # Create a recent approved capture
        recent_capture = ImplicitCapture(
            id="cap-recent-approved",
            memory=ImplicitMemory(
                namespace="test",
                summary="Recent approved",
                content="Content",
                confidence=CaptureConfidence(overall=0.8),
                source_hash="hash-recent",
            ),
            status=ReviewStatus.APPROVED,
            threat_detection=ThreatDetection.safe(),
            created_at=datetime.now(UTC) - timedelta(days=5),
            expires_at=datetime.now(UTC) + timedelta(days=2),
            reviewed_at=datetime.now(UTC) - timedelta(days=3),  # 3 days ago
        )
        capture_store.save(recent_capture)

        # Cleanup captures older than 30 days
        deleted = capture_store.cleanup_reviewed(older_than_days=30)

        assert deleted == 1
        assert capture_store.get("cap-old-approved") is None
        assert capture_store.get("cap-recent-approved") is not None

    def test_cleanup_reviewed_removes_rejected(
        self,
        capture_store: CaptureStore,
    ) -> None:
        """Test that old rejected captures are cleaned up."""
        from git_notes_memory.subconsciousness.models import ImplicitCapture

        memory = ImplicitMemory(
            namespace="test",
            summary="Old rejected",
            content="Content",
            confidence=CaptureConfidence(overall=0.8),
            source_hash="hash-rejected",
        )
        old_rejected = ImplicitCapture(
            id="cap-old-rejected",
            memory=memory,
            status=ReviewStatus.REJECTED,
            threat_detection=ThreatDetection.safe(),
            created_at=datetime.now(UTC) - timedelta(days=40),
            expires_at=datetime.now(UTC) - timedelta(days=33),
            reviewed_at=datetime.now(UTC) - timedelta(days=35),
        )
        capture_store.save(old_rejected)

        deleted = capture_store.cleanup_reviewed(older_than_days=30)

        assert deleted == 1
        assert capture_store.get("cap-old-rejected") is None

    def test_cleanup_reviewed_preserves_pending(
        self,
        capture_store: CaptureStore,
        sample_memory: ImplicitMemory,
    ) -> None:
        """Test that pending captures are not cleaned up."""
        capture = create_capture(sample_memory)
        capture_store.save(capture)

        # Should not delete pending captures regardless of age
        deleted = capture_store.cleanup_reviewed(older_than_days=0)

        assert deleted == 0
        assert capture_store.get(capture.id) is not None


class TestCaptureStoreDefaultFactory:
    """Tests for the default store factory functions."""

    def test_get_default_capture_store(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test getting the default store singleton."""
        from git_notes_memory.subconsciousness.capture_store import (
            get_default_capture_store,
            reset_default_capture_store,
        )

        # Reset first to ensure clean state
        reset_default_capture_store()

        # Set a temp data path
        monkeypatch.setenv("MEMORY_PLUGIN_DATA_DIR", str(tmp_path))

        # Get store - should create new
        store1 = get_default_capture_store()
        assert store1.is_initialized

        # Get again - should return same instance
        store2 = get_default_capture_store()
        assert store1 is store2

        # Clean up
        reset_default_capture_store()

    def test_reset_default_capture_store(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test resetting the default store singleton."""
        from git_notes_memory.subconsciousness.capture_store import (
            get_default_capture_store,
            reset_default_capture_store,
        )

        # Reset first
        reset_default_capture_store()

        # Set temp path
        monkeypatch.setenv("MEMORY_PLUGIN_DATA_DIR", str(tmp_path))

        store1 = get_default_capture_store()

        # Reset should close the store
        reset_default_capture_store()

        # Getting again should create a new instance
        store2 = get_default_capture_store()
        assert store1 is not store2

        # Clean up
        reset_default_capture_store()
