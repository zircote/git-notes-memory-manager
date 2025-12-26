"""Tests for git_notes_memory.capture module.

Tests for CaptureService including validation, locking, graceful degradation,
and convenience methods. Uses mocked git operations and both mocked and real
index/embedding services.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from git_notes_memory.capture import (
    CaptureService,
    _acquire_lock,
    _validate_content,
    _validate_namespace,
    _validate_summary,
    get_default_service,
)
from git_notes_memory.config import MAX_CONTENT_BYTES, MAX_SUMMARY_CHARS, NAMESPACES
from git_notes_memory.exceptions import CaptureError, ValidationError

if TYPE_CHECKING:
    pass


# =============================================================================
# Validation Tests
# =============================================================================


class TestValidateNamespace:
    """Tests for _validate_namespace function."""

    def test_valid_namespaces(self) -> None:
        """Test all valid namespaces pass validation."""
        for namespace in NAMESPACES:
            _validate_namespace(namespace)  # Should not raise

    def test_empty_namespace_raises(self) -> None:
        """Test empty namespace raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            _validate_namespace("")
        assert "cannot be empty" in exc_info.value.message

    def test_invalid_namespace_raises(self) -> None:
        """Test invalid namespace raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            _validate_namespace("invalid")
        assert "Invalid namespace" in exc_info.value.message
        # Should suggest valid namespaces
        for valid in sorted(NAMESPACES):
            assert valid in exc_info.value.recovery_action

    def test_case_sensitive(self) -> None:
        """Test namespace validation is case-sensitive."""
        with pytest.raises(ValidationError):
            _validate_namespace("DECISIONS")


class TestValidateSummary:
    """Tests for _validate_summary function."""

    def test_valid_summary(self) -> None:
        """Test valid summary passes validation."""
        _validate_summary("This is a valid summary")  # Should not raise

    def test_empty_summary_raises(self) -> None:
        """Test empty summary raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            _validate_summary("")
        assert "cannot be empty" in exc_info.value.message

    def test_whitespace_only_summary_raises(self) -> None:
        """Test whitespace-only summary raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            _validate_summary("   ")
        assert "cannot be empty" in exc_info.value.message

    def test_max_length_summary(self) -> None:
        """Test summary at max length passes."""
        summary = "x" * MAX_SUMMARY_CHARS
        _validate_summary(summary)  # Should not raise

    def test_too_long_summary_raises(self) -> None:
        """Test summary exceeding max length raises."""
        summary = "x" * (MAX_SUMMARY_CHARS + 1)
        with pytest.raises(ValidationError) as exc_info:
            _validate_summary(summary)
        assert "too long" in exc_info.value.message
        assert str(MAX_SUMMARY_CHARS) in exc_info.value.recovery_action


class TestValidateContent:
    """Tests for _validate_content function."""

    def test_valid_content(self) -> None:
        """Test valid content passes validation."""
        _validate_content("This is valid content")  # Should not raise

    def test_empty_content(self) -> None:
        """Test empty content passes (only size is validated)."""
        _validate_content("")  # Should not raise

    def test_max_size_content(self) -> None:
        """Test content at max size passes."""
        content = "x" * MAX_CONTENT_BYTES
        _validate_content(content)  # Should not raise

    def test_too_large_content_raises(self) -> None:
        """Test content exceeding max size raises."""
        content = "x" * (MAX_CONTENT_BYTES + 1)
        with pytest.raises(ValidationError) as exc_info:
            _validate_content(content)
        assert "too large" in exc_info.value.message

    def test_unicode_content_byte_count(self) -> None:
        """Test content with unicode is measured in bytes, not characters."""
        # 🔥 is 4 bytes in UTF-8
        # MAX_CONTENT_BYTES / 4 emojis would be exactly at the limit
        num_emojis = MAX_CONTENT_BYTES // 4
        content = "🔥" * num_emojis
        _validate_content(content)  # Should not raise


# =============================================================================
# File Locking Tests
# =============================================================================


class TestAcquireLock:
    """Tests for _acquire_lock context manager."""

    def test_lock_acquired_and_released(self, tmp_path: Path) -> None:
        """Test lock file is created and can be acquired/released."""
        lock_path = tmp_path / "test.lock"

        with _acquire_lock(lock_path):
            assert lock_path.exists()

        # Lock should be released after context exits
        # Can acquire again immediately
        with _acquire_lock(lock_path):
            pass

    def test_lock_creates_parent_directory(self, tmp_path: Path) -> None:
        """Test lock creates parent directories if needed."""
        lock_path = tmp_path / "subdir" / "deep" / "test.lock"

        with _acquire_lock(lock_path):
            assert lock_path.parent.exists()

    def test_concurrent_locks_block(self, tmp_path: Path) -> None:
        """Test that concurrent lock attempts block."""
        lock_path = tmp_path / "test.lock"
        results: list[str] = []

        def worker(name: str, delay: float) -> None:
            with _acquire_lock(lock_path):
                results.append(f"{name}_start")
                time.sleep(delay)
                results.append(f"{name}_end")

        # Start two threads that try to acquire the same lock
        t1 = threading.Thread(target=worker, args=("A", 0.1))
        t2 = threading.Thread(target=worker, args=("B", 0.1))

        t1.start()
        time.sleep(0.02)  # Give A time to acquire lock
        t2.start()

        t1.join()
        t2.join()

        # A should complete before B starts
        assert results == ["A_start", "A_end", "B_start", "B_end"]

    def test_lock_acquisition_timeout(self, tmp_path: Path) -> None:
        """Test that lock acquisition times out when held by another thread.

        CRIT-002: Verifies the timeout mechanism prevents indefinite blocking.
        """
        import fcntl
        import os

        lock_path = tmp_path / "timeout.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Acquire the lock in the main thread and hold it
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)

        try:
            # Try to acquire with a short timeout - should raise CaptureError
            with pytest.raises(CaptureError) as exc_info:
                with _acquire_lock(lock_path, timeout=0.3):
                    pass  # Should never reach here

            assert "timed out" in exc_info.value.message.lower()
            assert "0.3s" in exc_info.value.message
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def test_lock_acquisition_oserror(self, tmp_path: Path) -> None:
        """Test that OSError during lock acquisition is handled properly.

        CRIT-003: Verifies proper error handling for OS-level failures.
        """
        import fcntl

        lock_path = tmp_path / "oserror.lock"

        # Mock fcntl.flock to raise OSError (simulates I/O error, invalid fd, etc.)
        original_flock = fcntl.flock

        def mock_flock(fd: int, operation: int) -> None:
            if operation == (fcntl.LOCK_EX | fcntl.LOCK_NB):
                raise OSError(5, "I/O error during lock")
            return original_flock(fd, operation)

        with patch("fcntl.flock", side_effect=mock_flock):
            with pytest.raises(CaptureError) as exc_info:
                with _acquire_lock(lock_path, timeout=1.0):
                    pass

            assert "Failed to acquire" in exc_info.value.message
            assert "I/O error" in exc_info.value.message

    def test_lock_cleanup_on_exception(self, tmp_path: Path) -> None:
        """Test that lock is released even when exception occurs in block.

        Verifies the finally block properly cleans up resources.
        """
        lock_path = tmp_path / "exception.lock"

        with pytest.raises(ValueError):
            with _acquire_lock(lock_path):
                raise ValueError("Test exception")

        # Lock should be released - we can acquire it again immediately
        with _acquire_lock(lock_path, timeout=0.5):
            pass  # Should succeed without timeout


# =============================================================================
# CaptureService Tests
# =============================================================================


class TestCaptureServiceInit:
    """Tests for CaptureService initialization."""

    def test_default_init(self) -> None:
        """Test default initialization."""
        service = CaptureService()
        assert service._git_ops is None
        assert service._index_service is None
        assert service._embedding_service is None

    def test_init_with_repo_path(self, tmp_path: Path) -> None:
        """Test initialization with repo_path."""
        service = CaptureService(repo_path=tmp_path)
        assert service._repo_path == tmp_path

    def test_lazy_git_ops_creation(self) -> None:
        """Test GitOps is created lazily on first access."""
        with patch("git_notes_memory.capture.GitOps") as mock_git_ops:
            mock_instance = MagicMock()
            mock_git_ops.return_value = mock_instance

            service = CaptureService()
            assert service._git_ops is None

            # Access git_ops property
            _ = service.git_ops
            mock_git_ops.assert_called_once()

    def test_set_index_service(self) -> None:
        """Test setting index service after init."""
        service = CaptureService()
        mock_index = MagicMock()

        service.set_index_service(mock_index)
        assert service.index_service is mock_index

    def test_set_embedding_service(self) -> None:
        """Test setting embedding service after init."""
        service = CaptureService()
        mock_embedding = MagicMock()

        service.set_embedding_service(mock_embedding)
        assert service.embedding_service is mock_embedding


class TestCaptureServiceCapture:
    """Tests for CaptureService.capture method."""

    @pytest.fixture
    def mock_git_ops(self) -> MagicMock:
        """Create a mock GitOps instance."""
        mock = MagicMock()
        mock.get_commit_info.return_value = MagicMock(sha="abc123def456")
        mock.show_note.return_value = None  # No existing notes
        mock.append_note.return_value = None
        return mock

    @pytest.fixture
    def capture_service(
        self, mock_git_ops: MagicMock, tmp_path: Path
    ) -> CaptureService:
        """Create a CaptureService with mocked GitOps."""
        service = CaptureService(git_ops=mock_git_ops, repo_path=tmp_path)
        return service

    def test_basic_capture(
        self, capture_service: CaptureService, mock_git_ops: MagicMock
    ) -> None:
        """Test basic capture operation."""
        result = capture_service.capture(
            namespace="decisions",
            summary="Use PostgreSQL",
            content="We chose PostgreSQL for its reliability.",
            skip_lock=True,
        )

        assert result.success is True
        assert result.memory is not None
        assert result.memory.namespace == "decisions"
        assert result.memory.summary == "Use PostgreSQL"
        assert result.indexed is False  # No index service

        # Verify git operations
        mock_git_ops.append_note.assert_called_once()

    def test_capture_with_all_options(
        self, capture_service: CaptureService, mock_git_ops: MagicMock
    ) -> None:
        """Test capture with all optional parameters."""
        result = capture_service.capture(
            namespace="learnings",
            summary="Test summary",
            content="Test content",
            spec="my-project",
            tags=["tag1", "tag2"],
            phase="implementation",
            status="active",
            relates_to=["memory-1", "memory-2"],
            commit="HEAD",
            skip_lock=True,
        )

        assert result.success is True
        memory = result.memory
        assert memory is not None
        assert memory.spec == "my-project"
        assert memory.tags == ("tag1", "tag2")
        assert memory.phase == "implementation"
        assert memory.status == "active"
        assert memory.relates_to == ("memory-1", "memory-2")

    def test_capture_memory_id_format(
        self, capture_service: CaptureService, mock_git_ops: MagicMock
    ) -> None:
        """Test memory ID follows expected format."""
        result = capture_service.capture(
            namespace="decisions",
            summary="Test",
            content="Content",
            skip_lock=True,
        )

        memory = result.memory
        assert memory is not None
        # Format: <namespace>:<commit_sha>:<index>
        assert memory.id == "decisions:abc123def456:0"

    def test_capture_increments_index(
        self, capture_service: CaptureService, mock_git_ops: MagicMock
    ) -> None:
        """Test index increments for existing notes."""
        # Simulate existing note with one entry (has one pair of "---")
        mock_git_ops.show_note.return_value = "---\nfirst note\n---\ncontent"

        result = capture_service.capture(
            namespace="decisions",
            summary="Second note",
            content="Content",
            skip_lock=True,
        )

        memory = result.memory
        assert memory is not None
        assert memory.id.endswith(":1")  # Second note has index 1

    def test_capture_validates_namespace(self, capture_service: CaptureService) -> None:
        """Test capture validates namespace."""
        with pytest.raises(ValidationError) as exc_info:
            capture_service.capture(
                namespace="invalid",
                summary="Test",
                content="Content",
                skip_lock=True,
            )
        assert "Invalid namespace" in exc_info.value.message

    def test_capture_validates_summary(self, capture_service: CaptureService) -> None:
        """Test capture validates summary."""
        with pytest.raises(ValidationError) as exc_info:
            capture_service.capture(
                namespace="decisions",
                summary="",
                content="Content",
                skip_lock=True,
            )
        assert "cannot be empty" in exc_info.value.message

    def test_capture_validates_content(self, capture_service: CaptureService) -> None:
        """Test capture validates content size."""
        with pytest.raises(ValidationError):
            capture_service.capture(
                namespace="decisions",
                summary="Test",
                content="x" * (MAX_CONTENT_BYTES + 1),
                skip_lock=True,
            )

    def test_capture_git_error_handling(
        self, capture_service: CaptureService, mock_git_ops: MagicMock
    ) -> None:
        """Test capture handles git errors."""
        mock_git_ops.get_commit_info.side_effect = Exception("Git error")

        with pytest.raises(CaptureError) as exc_info:
            capture_service.capture(
                namespace="decisions",
                summary="Test",
                content="Content",
                skip_lock=True,
            )
        assert "Failed to resolve commit" in exc_info.value.message


class TestCaptureWithIndexing:
    """Tests for CaptureService with indexing enabled."""

    @pytest.fixture
    def mock_git_ops(self) -> MagicMock:
        """Create a mock GitOps instance."""
        mock = MagicMock()
        mock.get_commit_info.return_value = MagicMock(sha="abc123def456")
        mock.show_note.return_value = None
        return mock

    @pytest.fixture
    def mock_index(self) -> MagicMock:
        """Create a mock IndexService."""
        mock = MagicMock()
        mock.insert.return_value = True
        return mock

    @pytest.fixture
    def mock_embedding(self) -> MagicMock:
        """Create a mock EmbeddingService."""
        mock = MagicMock()
        mock.embed.return_value = [0.1] * 384
        return mock

    def test_capture_with_index_and_embedding(
        self,
        mock_git_ops: MagicMock,
        mock_index: MagicMock,
        mock_embedding: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test capture indexes memory with embedding."""
        service = CaptureService(
            git_ops=mock_git_ops,
            index_service=mock_index,
            embedding_service=mock_embedding,
            repo_path=tmp_path,
        )

        result = service.capture(
            namespace="decisions",
            summary="Test",
            content="Content",
            skip_lock=True,
        )

        assert result.success is True
        assert result.indexed is True
        assert result.warning is None

        mock_embedding.embed.assert_called_once()
        mock_index.insert.assert_called_once()

    def test_capture_graceful_embedding_failure(
        self,
        mock_git_ops: MagicMock,
        mock_index: MagicMock,
        mock_embedding: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test capture continues when embedding fails."""
        mock_embedding.embed.side_effect = Exception("Embedding error")

        service = CaptureService(
            git_ops=mock_git_ops,
            index_service=mock_index,
            embedding_service=mock_embedding,
            repo_path=tmp_path,
        )

        result = service.capture(
            namespace="decisions",
            summary="Test",
            content="Content",
            skip_lock=True,
        )

        # Capture succeeds but with warning
        assert result.success is True
        assert result.indexed is True  # Index still works without embedding
        assert result.warning is not None
        assert "Embedding failed" in result.warning

    def test_capture_graceful_index_failure(
        self,
        mock_git_ops: MagicMock,
        mock_index: MagicMock,
        mock_embedding: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test capture continues when indexing fails."""
        mock_index.insert.side_effect = Exception("Index error")

        service = CaptureService(
            git_ops=mock_git_ops,
            index_service=mock_index,
            embedding_service=mock_embedding,
            repo_path=tmp_path,
        )

        result = service.capture(
            namespace="decisions",
            summary="Test",
            content="Content",
            skip_lock=True,
        )

        # Capture succeeds but not indexed
        assert result.success is True
        assert result.indexed is False
        assert result.warning is not None
        assert "Indexing failed" in result.warning


# =============================================================================
# Convenience Method Tests
# =============================================================================


class TestCaptureDecision:
    """Tests for capture_decision convenience method."""

    @pytest.fixture
    def capture_service(self, tmp_path: Path) -> CaptureService:
        """Create a CaptureService with mocked GitOps."""
        mock_git_ops = MagicMock()
        mock_git_ops.get_commit_info.return_value = MagicMock(sha="abc123")
        mock_git_ops.show_note.return_value = None
        return CaptureService(git_ops=mock_git_ops, repo_path=tmp_path)

    def test_capture_decision_basic(self, capture_service: CaptureService) -> None:
        """Test basic decision capture."""
        result = capture_service.capture_decision(
            spec="my-project",
            summary="Use PostgreSQL",
            context="We need a database.",
            rationale="ACID compliance.",
        )

        assert result.success is True
        memory = result.memory
        assert memory is not None
        assert memory.namespace == "decisions"
        assert memory.spec == "my-project"
        assert "## Context" in memory.content
        assert "## Rationale" in memory.content

    def test_capture_decision_with_alternatives(
        self, capture_service: CaptureService
    ) -> None:
        """Test decision capture with alternatives."""
        result = capture_service.capture_decision(
            spec="my-project",
            summary="Use PostgreSQL",
            context="Context",
            rationale="Rationale",
            alternatives=["MySQL", "MongoDB", "Redis"],
        )

        memory = result.memory
        assert memory is not None
        assert "## Alternatives Considered" in memory.content
        assert "- MySQL" in memory.content
        assert "- MongoDB" in memory.content
        assert "- Redis" in memory.content


class TestCaptureBlocker:
    """Tests for capture_blocker and resolve_blocker methods."""

    @pytest.fixture
    def capture_service(self, tmp_path: Path) -> CaptureService:
        """Create a CaptureService with mocked GitOps."""
        mock_git_ops = MagicMock()
        mock_git_ops.get_commit_info.return_value = MagicMock(sha="abc123")
        mock_git_ops.show_note.return_value = None
        return CaptureService(git_ops=mock_git_ops, repo_path=tmp_path)

    def test_capture_blocker(self, capture_service: CaptureService) -> None:
        """Test basic blocker capture."""
        result = capture_service.capture_blocker(
            spec="my-project",
            summary="API rate limit",
            description="Third-party API has rate limits.",
            impact="Cannot sync more than 100 items/min.",
        )

        assert result.success is True
        memory = result.memory
        assert memory is not None
        assert memory.namespace == "blockers"
        assert memory.status == "active"
        assert "## Description" in memory.content
        assert "## Impact" in memory.content

    def test_resolve_blocker(self, capture_service: CaptureService) -> None:
        """Test resolving a blocker."""
        result = capture_service.resolve_blocker(
            memory_id="blockers:abc123:0",
            resolution="Implemented exponential backoff.",
        )

        assert result.success is True
        memory = result.memory
        assert memory is not None
        assert memory.namespace == "blockers"
        assert memory.status == "resolved"
        assert memory.relates_to == ("blockers:abc123:0",)
        assert "## Resolution" in memory.content

    def test_resolve_blocker_invalid_id(self, capture_service: CaptureService) -> None:
        """Test resolve_blocker with invalid memory ID."""
        with pytest.raises(ValidationError) as exc_info:
            capture_service.resolve_blocker(
                memory_id="decisions:abc123:0",  # Wrong namespace
                resolution="Fix",
            )
        assert "Invalid blocker memory ID" in exc_info.value.message


class TestCaptureLearning:
    """Tests for capture_learning convenience method."""

    @pytest.fixture
    def capture_service(self, tmp_path: Path) -> CaptureService:
        """Create a CaptureService with mocked GitOps."""
        mock_git_ops = MagicMock()
        mock_git_ops.get_commit_info.return_value = MagicMock(sha="abc123")
        mock_git_ops.show_note.return_value = None
        return CaptureService(git_ops=mock_git_ops, repo_path=tmp_path)

    def test_capture_learning_basic(self, capture_service: CaptureService) -> None:
        """Test basic learning capture."""
        result = capture_service.capture_learning(
            summary="Always use type hints",
            insight="Type hints catch bugs early and improve IDE support.",
        )

        assert result.success is True
        memory = result.memory
        assert memory is not None
        assert memory.namespace == "learnings"
        assert "## Insight" in memory.content

    def test_capture_learning_with_context(
        self, capture_service: CaptureService
    ) -> None:
        """Test learning capture with context."""
        result = capture_service.capture_learning(
            summary="Test summary",
            insight="The key insight",
            context="Background context",
        )

        memory = result.memory
        assert memory is not None
        assert "## Insight" in memory.content
        assert "## Context" in memory.content


class TestCaptureProgress:
    """Tests for capture_progress convenience method."""

    @pytest.fixture
    def capture_service(self, tmp_path: Path) -> CaptureService:
        """Create a CaptureService with mocked GitOps."""
        mock_git_ops = MagicMock()
        mock_git_ops.get_commit_info.return_value = MagicMock(sha="abc123")
        mock_git_ops.show_note.return_value = None
        return CaptureService(git_ops=mock_git_ops, repo_path=tmp_path)

    def test_capture_progress(self, capture_service: CaptureService) -> None:
        """Test basic progress capture."""
        result = capture_service.capture_progress(
            spec="my-project",
            summary="Phase 1 complete",
            milestone="All foundation tasks done",
            details="Tests passing at 91% coverage.",
        )

        assert result.success is True
        memory = result.memory
        assert memory is not None
        assert memory.namespace == "progress"
        assert "## Milestone" in memory.content
        assert "## Details" in memory.content


class TestCaptureRetrospective:
    """Tests for capture_retrospective convenience method."""

    @pytest.fixture
    def capture_service(self, tmp_path: Path) -> CaptureService:
        """Create a CaptureService with mocked GitOps."""
        mock_git_ops = MagicMock()
        mock_git_ops.get_commit_info.return_value = MagicMock(sha="abc123")
        mock_git_ops.show_note.return_value = None
        return CaptureService(git_ops=mock_git_ops, repo_path=tmp_path)

    def test_capture_retrospective(self, capture_service: CaptureService) -> None:
        """Test retrospective capture."""
        result = capture_service.capture_retrospective(
            spec="my-project",
            summary="Project retrospective",
            content="## What went well\n\nEverything!",
            outcome="success",
        )

        assert result.success is True
        memory = result.memory
        assert memory is not None
        assert memory.namespace == "retrospective"
        assert memory.phase == "completed"
        assert "outcome:success" in memory.tags


class TestCapturePattern:
    """Tests for capture_pattern convenience method."""

    @pytest.fixture
    def capture_service(self, tmp_path: Path) -> CaptureService:
        """Create a CaptureService with mocked GitOps."""
        mock_git_ops = MagicMock()
        mock_git_ops.get_commit_info.return_value = MagicMock(sha="abc123")
        mock_git_ops.show_note.return_value = None
        return CaptureService(git_ops=mock_git_ops, repo_path=tmp_path)

    def test_capture_pattern(self, capture_service: CaptureService) -> None:
        """Test pattern capture."""
        result = capture_service.capture_pattern(
            summary="Repository pattern for data access",
            pattern_type="success",
            evidence="Used in 5 projects successfully.",
            confidence=0.8,
        )

        assert result.success is True
        memory = result.memory
        assert memory is not None
        assert memory.namespace == "patterns"
        assert memory.status == "candidate"
        assert "pattern:success" in memory.tags
        assert "## Pattern Type" in memory.content
        assert "## Evidence" in memory.content
        assert "## Confidence" in memory.content
        assert "0.80" in memory.content

    def test_capture_pattern_invalid_confidence(
        self, capture_service: CaptureService
    ) -> None:
        """Test pattern capture with invalid confidence."""
        with pytest.raises(ValidationError) as exc_info:
            capture_service.capture_pattern(
                summary="Test",
                pattern_type="success",
                evidence="Evidence",
                confidence=1.5,  # Invalid
            )
        assert "between 0.0 and 1.0" in exc_info.value.message


class TestCaptureReview:
    """Tests for capture_review convenience method."""

    @pytest.fixture
    def capture_service(self, tmp_path: Path) -> CaptureService:
        """Create a CaptureService with mocked GitOps."""
        mock_git_ops = MagicMock()
        mock_git_ops.get_commit_info.return_value = MagicMock(sha="abc123")
        mock_git_ops.show_note.return_value = None
        return CaptureService(git_ops=mock_git_ops, repo_path=tmp_path)

    def test_capture_review(self, capture_service: CaptureService) -> None:
        """Test review capture."""
        result = capture_service.capture_review(
            spec="my-project",
            summary="Code review for PR #42",
            findings="Good code quality overall.",
            verdict="approved",
        )

        assert result.success is True
        memory = result.memory
        assert memory is not None
        assert memory.namespace == "reviews"
        assert "verdict:approved" in memory.tags
        assert "## Findings" in memory.content
        assert "## Verdict" in memory.content


# =============================================================================
# Singleton Tests
# =============================================================================


class TestGetDefaultService:
    """Tests for get_default_service singleton."""

    def test_returns_capture_service(self) -> None:
        """Test get_default_service returns a CaptureService."""
        # Reset singleton for test
        import git_notes_memory.capture as capture_module

        capture_module._default_service = None

        service = get_default_service()
        assert isinstance(service, CaptureService)

    def test_returns_same_instance(self) -> None:
        """Test get_default_service returns the same instance."""
        import git_notes_memory.capture as capture_module

        capture_module._default_service = None

        service1 = get_default_service()
        service2 = get_default_service()
        assert service1 is service2


# =============================================================================
# Integration Tests (with real git repo)
# =============================================================================


@pytest.mark.integration
class TestCaptureServiceIntegration:
    """Integration tests with real git repositories."""

    @pytest.fixture
    def git_repo(self, tmp_path: Path) -> Path:
        """Create a temporary git repository."""
        import subprocess

        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create initial commit
        readme = repo_path / "README.md"
        readme.write_text("# Test")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        return repo_path

    def test_capture_to_real_git_repo(self, git_repo: Path) -> None:
        """Test capture writes to a real git repository."""
        service = CaptureService(repo_path=git_repo)

        result = service.capture(
            namespace="decisions",
            summary="Use Python",
            content="Python is the best choice.",
            skip_lock=True,
        )

        assert result.success is True
        assert result.memory is not None

        # Verify note was written (note: git notes are stored under refs/notes/mem/)
        import subprocess

        from git_notes_memory.config import get_git_namespace

        note_ref = f"{get_git_namespace()}/decisions"
        show_result = subprocess.run(
            ["git", "notes", f"--ref={note_ref}", "show", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert show_result.returncode == 0
        assert "Use Python" in show_result.stdout

    def test_capture_multiple_to_same_commit(self, git_repo: Path) -> None:
        """Test multiple captures append to same commit."""
        service = CaptureService(repo_path=git_repo)

        result1 = service.capture(
            namespace="decisions",
            summary="First decision",
            content="First content",
            skip_lock=True,
        )

        result2 = service.capture(
            namespace="decisions",
            summary="Second decision",
            content="Second content",
            skip_lock=True,
        )

        assert result1.success is True
        assert result2.success is True

        # Verify IDs have different indices
        assert result1.memory is not None
        assert result2.memory is not None
        assert result1.memory.id.endswith(":0")
        assert result2.memory.id.endswith(":1")

        # Verify both are in the note (note: git notes are stored under refs/notes/mem/)
        import subprocess

        from git_notes_memory.config import get_git_namespace

        note_ref = f"{get_git_namespace()}/decisions"
        show_result = subprocess.run(
            ["git", "notes", f"--ref={note_ref}", "show", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
        )
        assert "First decision" in show_result.stdout
        assert "Second decision" in show_result.stdout
