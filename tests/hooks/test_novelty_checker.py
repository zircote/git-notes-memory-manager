"""Tests for novelty checking functionality.

TEST-H-003: Tests for novelty_checker.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from git_notes_memory.hooks.models import CaptureSignal, NoveltyResult, SignalType
from git_notes_memory.hooks.novelty_checker import NoveltyChecker

if TYPE_CHECKING:
    pass


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_recall_service() -> MagicMock:
    """Create a mock recall service."""
    mock = MagicMock()
    mock.search.return_value = []
    return mock


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create a mock embedding service."""
    mock = MagicMock()
    mock.is_loaded = True
    return mock


@pytest.fixture
def checker(
    mock_recall_service: MagicMock, mock_embedding_service: MagicMock
) -> NoveltyChecker:
    """Create a NoveltyChecker with mocked services."""
    return NoveltyChecker(
        recall_service=mock_recall_service,
        embedding_service=mock_embedding_service,
    )


@pytest.fixture
def sample_signal() -> CaptureSignal:
    """Create a sample capture signal."""
    return CaptureSignal(
        type=SignalType.DECISION,
        match="I decided to use SQLite",
        context="After evaluating options, I decided to use SQLite for storage.",
        suggested_namespace="decisions",
        confidence=0.9,
    )


# =============================================================================
# NoveltyChecker Initialization Tests
# =============================================================================


class TestNoveltyCheckerInit:
    """Tests for NoveltyChecker initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default values."""
        checker = NoveltyChecker()
        assert checker.novelty_threshold == 0.3
        assert checker.similarity_threshold == 0.7
        assert checker.k == 5
        assert checker._recall_service is None
        assert checker._embedding_service is None

    def test_init_with_custom_values(self) -> None:
        """Test initialization with custom values."""
        checker = NoveltyChecker(
            novelty_threshold=0.5,
            similarity_threshold=0.8,
            k=10,
        )
        assert checker.novelty_threshold == 0.5
        assert checker.similarity_threshold == 0.8
        assert checker.k == 10

    def test_init_with_services(
        self, mock_recall_service: MagicMock, mock_embedding_service: MagicMock
    ) -> None:
        """Test initialization with pre-configured services."""
        checker = NoveltyChecker(
            recall_service=mock_recall_service,
            embedding_service=mock_embedding_service,
        )
        assert checker._recall_service is mock_recall_service
        assert checker._embedding_service is mock_embedding_service


# =============================================================================
# Service Lazy Loading Tests
# =============================================================================


class TestServiceLazyLoading:
    """Tests for lazy loading of services."""

    def test_get_recall_service_creates_if_none(self) -> None:
        """Test that recall service is created lazily."""
        checker = NoveltyChecker()
        # Initially None
        assert checker._recall_service is None
        # After calling _get_recall_service, it should be set
        with patch("git_notes_memory.recall.get_default_service") as mock_get:
            mock_service = MagicMock()
            mock_get.return_value = mock_service
            result = checker._get_recall_service()
            assert result is mock_service
            mock_get.assert_called_once()

    def test_get_recall_service_uses_existing(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that existing recall service is reused."""
        checker = NoveltyChecker(recall_service=mock_recall_service)
        result = checker._get_recall_service()
        assert result is mock_recall_service

    def test_get_embedding_service_uses_existing(
        self, mock_embedding_service: MagicMock
    ) -> None:
        """Test that existing embedding service is reused."""
        checker = NoveltyChecker(embedding_service=mock_embedding_service)
        result = checker._get_embedding_service()
        assert result is mock_embedding_service


# =============================================================================
# check_novelty Tests
# =============================================================================


class TestCheckNovelty:
    """Tests for the check_novelty method."""

    def test_empty_text_is_novel(self, checker: NoveltyChecker) -> None:
        """Test that empty text returns fully novel."""
        result = checker.check_novelty("")
        assert result.novelty_score == 1.0
        assert result.is_novel is True
        assert result.similar_memory_ids == []
        assert result.highest_similarity == 0.0

    def test_whitespace_only_is_novel(self, checker: NoveltyChecker) -> None:
        """Test that whitespace-only text returns fully novel."""
        result = checker.check_novelty("   \n\t  ")
        assert result.novelty_score == 1.0
        assert result.is_novel is True

    def test_no_similar_memories_is_novel(
        self,
        mock_recall_service: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that text with no similar memories is novel."""
        mock_recall_service.search.return_value = []
        checker = NoveltyChecker(
            recall_service=mock_recall_service,
            embedding_service=mock_embedding_service,
        )

        result = checker.check_novelty("Completely new content")

        assert result.novelty_score == 1.0
        assert result.is_novel is True
        assert result.similar_memory_ids == []

    def test_high_similarity_not_novel(
        self,
        mock_recall_service: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that high similarity results in not novel."""
        # Mock a memory result with low distance (high similarity)
        mock_memory = MagicMock()
        mock_memory.id = "decisions:abc1234:0"

        mock_result = MagicMock()
        mock_result.memory = mock_memory
        mock_result.distance = 0.1  # Low distance = high similarity

        mock_recall_service.search.return_value = [mock_result]

        checker = NoveltyChecker(
            novelty_threshold=0.3,
            similarity_threshold=0.7,
            recall_service=mock_recall_service,
            embedding_service=mock_embedding_service,
        )

        result = checker.check_novelty("Almost duplicate content")

        # Similarity = 1 / (1 + 0.1) ≈ 0.909
        # Novelty = 1 - 0.909 ≈ 0.091
        assert result.novelty_score < 0.3
        assert result.is_novel is False
        assert result.highest_similarity > 0.7
        assert "decisions:abc1234:0" in result.similar_memory_ids

    def test_medium_similarity_is_novel(
        self,
        mock_recall_service: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that medium similarity can be novel."""
        mock_memory = MagicMock()
        mock_memory.id = "learnings:def5678:0"

        mock_result = MagicMock()
        mock_result.memory = mock_memory
        mock_result.distance = 2.0  # Medium distance

        mock_recall_service.search.return_value = [mock_result]

        checker = NoveltyChecker(
            novelty_threshold=0.3,
            similarity_threshold=0.7,
            recall_service=mock_recall_service,
            embedding_service=mock_embedding_service,
        )

        result = checker.check_novelty("Somewhat similar content")

        # Similarity = 1 / (1 + 2.0) ≈ 0.333
        # Novelty = 1 - 0.333 ≈ 0.667
        assert result.novelty_score >= 0.3
        assert result.is_novel is True

    def test_embedding_not_loaded_assumes_novel(
        self,
        mock_recall_service: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that unloaded embedding model assumes novel."""
        mock_embedding_service.is_loaded = False

        checker = NoveltyChecker(
            recall_service=mock_recall_service,
            embedding_service=mock_embedding_service,
        )

        result = checker.check_novelty("Some text")

        assert result.novelty_score == 1.0
        assert result.is_novel is True
        # Search should not be called if embedding not loaded
        mock_recall_service.search.assert_not_called()

    def test_exception_handling_assumes_novel(
        self,
        mock_recall_service: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that exceptions result in novel assumption."""
        mock_recall_service.search.side_effect = Exception("Database error")

        checker = NoveltyChecker(
            recall_service=mock_recall_service,
            embedding_service=mock_embedding_service,
        )

        result = checker.check_novelty("Text that causes error")

        assert result.novelty_score == 1.0
        assert result.is_novel is True

    def test_namespace_filtering(
        self,
        mock_recall_service: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that namespace is passed to search."""
        mock_recall_service.search.return_value = []

        checker = NoveltyChecker(
            recall_service=mock_recall_service,
            embedding_service=mock_embedding_service,
        )

        checker.check_novelty("Test content", namespace="decisions")

        mock_recall_service.search.assert_called_once()
        _, kwargs = mock_recall_service.search.call_args
        assert kwargs["namespace"] == "decisions"


# =============================================================================
# check_signal_novelty Tests
# =============================================================================


class TestCheckSignalNovelty:
    """Tests for the check_signal_novelty method."""

    def test_uses_context_over_match(
        self,
        checker: NoveltyChecker,
        sample_signal: CaptureSignal,
        mock_recall_service: MagicMock,
    ) -> None:
        """Test that context is used if available."""
        checker.check_signal_novelty(sample_signal)

        mock_recall_service.search.assert_called_once()
        args, _ = mock_recall_service.search.call_args
        assert "After evaluating options" in args[0]

    def test_falls_back_to_match(
        self,
        checker: NoveltyChecker,
        mock_recall_service: MagicMock,
    ) -> None:
        """Test that match is used when no context."""
        signal = CaptureSignal(
            type=SignalType.LEARNING,
            match="I learned that SQLite is fast",
            context="",
            suggested_namespace="learnings",
            confidence=0.8,
        )

        checker.check_signal_novelty(signal)

        mock_recall_service.search.assert_called_once()
        args, _ = mock_recall_service.search.call_args
        assert "I learned that SQLite is fast" in args[0]

    def test_uses_suggested_namespace(
        self,
        checker: NoveltyChecker,
        sample_signal: CaptureSignal,
        mock_recall_service: MagicMock,
    ) -> None:
        """Test that suggested namespace is used for search."""
        checker.check_signal_novelty(sample_signal)

        _, kwargs = mock_recall_service.search.call_args
        assert kwargs["namespace"] == "decisions"


# =============================================================================
# batch_check_novelty Tests
# =============================================================================


class TestBatchCheckNovelty:
    """Tests for the batch_check_novelty method."""

    def test_empty_list(self, checker: NoveltyChecker) -> None:
        """Test that empty list returns empty results."""
        results = checker.batch_check_novelty([])
        assert results == []

    def test_processes_all_signals(
        self,
        checker: NoveltyChecker,
        mock_recall_service: MagicMock,
    ) -> None:
        """Test that all signals are processed."""
        signals = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="Decision 1",
                context="",
                suggested_namespace="decisions",
                confidence=0.9,
            ),
            CaptureSignal(
                type=SignalType.LEARNING,
                match="Learning 1",
                context="",
                suggested_namespace="learnings",
                confidence=0.8,
            ),
        ]

        results = checker.batch_check_novelty(signals)

        assert len(results) == 2
        assert mock_recall_service.search.call_count == 2

    def test_preserves_order(
        self,
        mock_recall_service: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test that results are in same order as inputs."""
        # Configure mock to return different results based on call count
        call_count = [0]

        def mock_search(*args: object, **kwargs: object) -> list[MagicMock]:
            call_count[0] += 1
            if call_count[0] == 1:
                # First call - return similar memory
                mock_memory = MagicMock()
                mock_memory.id = "first:abc:0"
                mock_result = MagicMock()
                mock_result.memory = mock_memory
                mock_result.distance = 0.1  # High similarity
                return [mock_result]
            # Second call - no similar memories
            return []

        mock_recall_service.search.side_effect = mock_search

        checker = NoveltyChecker(
            recall_service=mock_recall_service,
            embedding_service=mock_embedding_service,
        )

        signals = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="Similar content",
                context="",
                suggested_namespace="decisions",
                confidence=0.9,
            ),
            CaptureSignal(
                type=SignalType.LEARNING,
                match="Unique content",
                context="",
                suggested_namespace="learnings",
                confidence=0.8,
            ),
        ]

        results = checker.batch_check_novelty(signals)

        assert len(results) == 2
        assert results[0].is_novel is False  # First had similar
        assert results[1].is_novel is True  # Second was unique


# =============================================================================
# NoveltyResult Tests
# =============================================================================


class TestNoveltyResult:
    """Tests for the NoveltyResult dataclass."""

    def test_create_result(self) -> None:
        """Test creating a NoveltyResult."""
        result = NoveltyResult(
            novelty_score=0.8,
            is_novel=True,
            similar_memory_ids=["mem:abc:0"],
            highest_similarity=0.2,
        )
        assert result.novelty_score == 0.8
        assert result.is_novel is True
        assert result.similar_memory_ids == ["mem:abc:0"]
        assert result.highest_similarity == 0.2

    def test_result_is_immutable(self) -> None:
        """Test that NoveltyResult is frozen."""
        result = NoveltyResult(
            novelty_score=0.5,
            is_novel=True,
            similar_memory_ids=[],
            highest_similarity=0.5,
        )
        with pytest.raises(AttributeError):
            result.novelty_score = 0.9  # type: ignore[misc]
