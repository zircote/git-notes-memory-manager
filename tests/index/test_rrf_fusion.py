"""Tests for the RRF Fusion Engine.

Tests cover:
- Basic RRF fusion algorithm
- Weighted sources
- Edge cases (empty lists, single source, ties)
- Configuration options
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from git_notes_memory.index.rrf_fusion import (
    FusedResult,
    RankedItem,
    RRFConfig,
    RRFFusionEngine,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def engine() -> RRFFusionEngine:
    """Create a default RRF fusion engine."""
    return RRFFusionEngine()


@pytest.fixture
def weighted_engine() -> RRFFusionEngine:
    """Create an RRF engine with custom weights."""
    config = RRFConfig(
        k=60,
        weights=(("vector", 1.5), ("bm25", 1.0)),
    )
    return RRFFusionEngine(config)


@dataclass
class MockItem:
    """Mock item for testing."""

    id: str
    name: str


# =============================================================================
# Test: RRFConfig
# =============================================================================


class TestRRFConfig:
    """Test RRFConfig dataclass."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = RRFConfig()
        assert config.k == 60
        assert config.weights == ()

    def test_custom_k(self) -> None:
        """Test custom k parameter."""
        config = RRFConfig(k=100)
        assert config.k == 100

    def test_custom_weights(self) -> None:
        """Test custom weights."""
        config = RRFConfig(weights=(("vector", 1.5), ("bm25", 0.8)))
        assert config.get_weight("vector") == 1.5
        assert config.get_weight("bm25") == 0.8

    def test_default_weight_for_unknown_source(self) -> None:
        """Test default weight of 1.0 for unknown sources."""
        config = RRFConfig(weights=(("vector", 1.5),))
        assert config.get_weight("unknown") == 1.0


# =============================================================================
# Test: RankedItem
# =============================================================================


class TestRankedItem:
    """Test RankedItem dataclass."""

    def test_basic_item(self) -> None:
        """Test basic RankedItem creation."""
        item = RankedItem(item_id="doc1", rank=1)
        assert item.item_id == "doc1"
        assert item.rank == 1
        assert item.score is None
        assert item.source == ""
        assert item.item is None

    def test_full_item(self) -> None:
        """Test RankedItem with all fields."""
        mock = MockItem(id="doc1", name="Test")
        item = RankedItem(
            item_id="doc1",
            rank=1,
            score=0.95,
            source="vector",
            item=mock,
        )
        assert item.score == 0.95
        assert item.source == "vector"
        assert item.item == mock


# =============================================================================
# Test: Basic Fusion
# =============================================================================


class TestBasicFusion:
    """Test basic RRF fusion operations."""

    def test_empty_input(self, engine: RRFFusionEngine) -> None:
        """Test fusion with empty input."""
        result = engine.fuse([])
        assert result == []

    def test_single_source(self, engine: RRFFusionEngine) -> None:
        """Test fusion with a single source."""
        items = [
            RankedItem("doc1", rank=1),
            RankedItem("doc2", rank=2),
            RankedItem("doc3", rank=3),
        ]
        result = engine.fuse([("vector", items)])

        assert len(result) == 3
        # First item should have highest score
        assert result[0].item_id == "doc1"
        assert result[1].item_id == "doc2"
        assert result[2].item_id == "doc3"

    def test_two_sources_same_order(self, engine: RRFFusionEngine) -> None:
        """Test fusion with two sources agreeing on order."""
        vector_items = [
            RankedItem("doc1", rank=1),
            RankedItem("doc2", rank=2),
        ]
        bm25_items = [
            RankedItem("doc1", rank=1),
            RankedItem("doc2", rank=2),
        ]
        result = engine.fuse([("vector", vector_items), ("bm25", bm25_items)])

        assert len(result) == 2
        # doc1 ranked first by both, should be first
        assert result[0].item_id == "doc1"
        assert result[1].item_id == "doc2"

    def test_two_sources_different_order(self, engine: RRFFusionEngine) -> None:
        """Test fusion with two sources with different orders."""
        vector_items = [
            RankedItem("doc1", rank=1),
            RankedItem("doc2", rank=2),
        ]
        bm25_items = [
            RankedItem("doc2", rank=1),
            RankedItem("doc1", rank=2),
        ]
        result = engine.fuse([("vector", vector_items), ("bm25", bm25_items)])

        assert len(result) == 2
        # Both docs have same cumulative score (1/61 + 1/62)
        # They should both appear, order may vary due to dict ordering
        item_ids = {r.item_id for r in result}
        assert item_ids == {"doc1", "doc2"}

    def test_item_only_in_one_source(self, engine: RRFFusionEngine) -> None:
        """Test fusion when an item appears in only one source."""
        vector_items = [
            RankedItem("doc1", rank=1),
            RankedItem("doc2", rank=2),
        ]
        bm25_items = [
            RankedItem("doc3", rank=1),  # Only in BM25
            RankedItem("doc1", rank=2),
        ]
        result = engine.fuse([("vector", vector_items), ("bm25", bm25_items)])

        assert len(result) == 3
        item_ids = {r.item_id for r in result}
        assert item_ids == {"doc1", "doc2", "doc3"}

        # doc1 appears in both, should have higher score than doc2 or doc3 alone
        doc1_result = next(r for r in result if r.item_id == "doc1")
        doc2_result = next(r for r in result if r.item_id == "doc2")
        doc3_result = next(r for r in result if r.item_id == "doc3")

        # doc1: 1/61 + 1/62 > doc3: 1/61 (alone) or doc2: 1/62 (alone)
        assert doc1_result.rrf_score > doc2_result.rrf_score
        assert doc1_result.rrf_score > doc3_result.rrf_score


class TestFusionWithLimit:
    """Test RRF fusion with result limits."""

    def test_limit_results(self, engine: RRFFusionEngine) -> None:
        """Test limiting number of results."""
        items = [
            RankedItem("doc1", rank=1),
            RankedItem("doc2", rank=2),
            RankedItem("doc3", rank=3),
        ]
        result = engine.fuse([("vector", items)], limit=2)

        assert len(result) == 2
        assert result[0].item_id == "doc1"
        assert result[1].item_id == "doc2"

    def test_limit_greater_than_results(self, engine: RRFFusionEngine) -> None:
        """Test limit greater than available results."""
        items = [
            RankedItem("doc1", rank=1),
            RankedItem("doc2", rank=2),
        ]
        result = engine.fuse([("vector", items)], limit=10)

        assert len(result) == 2


# =============================================================================
# Test: Weighted Fusion
# =============================================================================


class TestWeightedFusion:
    """Test RRF fusion with weighted sources."""

    def test_weighted_sources(self, weighted_engine: RRFFusionEngine) -> None:
        """Test that weights affect ranking."""
        # Vector ranked first, BM25 ranked second
        vector_items = [
            RankedItem("doc1", rank=1),
            RankedItem("doc2", rank=2),
        ]
        bm25_items = [
            RankedItem("doc2", rank=1),
            RankedItem("doc1", rank=2),
        ]
        result = weighted_engine.fuse([("vector", vector_items), ("bm25", bm25_items)])

        # doc1: vector weight 1.5/61 + bm25 weight 1.0/62
        # doc2: vector weight 1.5/62 + bm25 weight 1.0/61
        # 1.5/61 + 1.0/62 > 1.5/62 + 1.0/61
        # doc1 should be ranked higher due to higher weight on vector
        assert result[0].item_id == "doc1"


# =============================================================================
# Test: Score Calculations
# =============================================================================


class TestScoreCalculations:
    """Test RRF score calculations."""

    def test_score_formula(self) -> None:
        """Test RRF score formula correctness."""
        # k=60, weight=1.0, rank=1 -> 1/(60+1) = 1/61
        config = RRFConfig(k=60)
        engine = RRFFusionEngine(config)

        items = [RankedItem("doc1", rank=1)]
        result = engine.fuse([("test", items)])

        expected_score = 1.0 / (60 + 1)
        assert abs(result[0].rrf_score - expected_score) < 0.0001

    def test_score_accumulation(self) -> None:
        """Test that scores accumulate across sources."""
        engine = RRFFusionEngine(RRFConfig(k=60))

        vector_items = [RankedItem("doc1", rank=1)]
        bm25_items = [RankedItem("doc1", rank=1)]

        result = engine.fuse([("vector", vector_items), ("bm25", bm25_items)])

        # doc1: 1/61 + 1/61 = 2/61
        expected_score = 2.0 / 61
        assert abs(result[0].rrf_score - expected_score) < 0.0001

    def test_custom_k_affects_score(self) -> None:
        """Test that k parameter affects scores."""
        engine_k60 = RRFFusionEngine(RRFConfig(k=60))
        engine_k100 = RRFFusionEngine(RRFConfig(k=100))

        items = [RankedItem("doc1", rank=1)]

        result_k60 = engine_k60.fuse([("test", items)])
        result_k100 = engine_k100.fuse([("test", items)])

        # Higher k means lower score for same rank
        assert result_k60[0].rrf_score > result_k100[0].rrf_score


# =============================================================================
# Test: Source Tracking
# =============================================================================


class TestSourceTracking:
    """Test that sources are properly tracked in results."""

    def test_sources_tracked(self, engine: RRFFusionEngine) -> None:
        """Test that source contributions are recorded."""
        vector_items = [RankedItem("doc1", rank=1)]
        bm25_items = [RankedItem("doc1", rank=3)]

        result = engine.fuse([("vector", vector_items), ("bm25", bm25_items)])

        assert result[0].sources == {"vector": 1, "bm25": 3}

    def test_single_source_tracked(self, engine: RRFFusionEngine) -> None:
        """Test source tracking for item in single source."""
        vector_items = [RankedItem("doc1", rank=1)]
        bm25_items = [RankedItem("doc2", rank=1)]

        result = engine.fuse([("vector", vector_items), ("bm25", bm25_items)])

        doc1_result = next(r for r in result if r.item_id == "doc1")
        doc2_result = next(r for r in result if r.item_id == "doc2")

        assert doc1_result.sources == {"vector": 1}
        assert doc2_result.sources == {"bm25": 1}


# =============================================================================
# Test: Item Preservation
# =============================================================================


class TestItemPreservation:
    """Test that item objects are preserved through fusion."""

    def test_item_preserved(self, engine: RRFFusionEngine) -> None:
        """Test that item objects are included in results."""
        mock = MockItem(id="doc1", name="Test Document")
        items = [RankedItem("doc1", rank=1, item=mock)]

        result = engine.fuse([("test", items)])

        assert result[0].item == mock
        assert result[0].item.name == "Test Document"

    def test_item_from_any_source(self, engine: RRFFusionEngine) -> None:
        """Test that item is taken from whichever source has it."""
        mock = MockItem(id="doc1", name="From Vector")
        vector_items = [RankedItem("doc1", rank=1, item=mock)]
        bm25_items = [RankedItem("doc1", rank=2)]  # No item

        result = engine.fuse([("vector", vector_items), ("bm25", bm25_items)])

        assert result[0].item == mock


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_rank_zero(self, engine: RRFFusionEngine) -> None:
        """Test that rank 0 raises ValueError."""
        items = [RankedItem("doc1", rank=0)]

        with pytest.raises(ValueError, match="Rank must be > 0"):
            engine.fuse([("test", items)])

    def test_invalid_rank_negative(self, engine: RRFFusionEngine) -> None:
        """Test that negative rank raises ValueError."""
        items = [RankedItem("doc1", rank=-1)]

        with pytest.raises(ValueError, match="Rank must be > 0"):
            engine.fuse([("test", items)])

    def test_many_sources(self, engine: RRFFusionEngine) -> None:
        """Test fusion with many sources."""
        sources = []
        for i in range(10):
            sources.append((f"source{i}", [RankedItem("doc1", rank=1)]))

        result = engine.fuse(sources)

        # Should have 10x the single-source score
        expected_score = 10.0 / 61
        assert abs(result[0].rrf_score - expected_score) < 0.0001

    def test_empty_source_list(self, engine: RRFFusionEngine) -> None:
        """Test fusion when a source has no items."""
        vector_items = [RankedItem("doc1", rank=1)]
        bm25_items: list[RankedItem] = []  # Empty

        result = engine.fuse([("vector", vector_items), ("bm25", bm25_items)])

        assert len(result) == 1
        assert result[0].item_id == "doc1"

    def test_large_ranks(self, engine: RRFFusionEngine) -> None:
        """Test with large rank values."""
        items = [RankedItem("doc1", rank=1000)]

        result = engine.fuse([("test", items)])

        # Score should be 1/(60+1000) = 1/1060
        expected_score = 1.0 / 1060
        assert abs(result[0].rrf_score - expected_score) < 0.0001


# =============================================================================
# Test: Convenience Method
# =============================================================================


class TestFuseWithItems:
    """Test the fuse_with_items convenience method."""

    def test_basic_usage(self, engine: RRFFusionEngine) -> None:
        """Test basic fuse_with_items usage."""
        item1 = MockItem(id="doc1", name="Doc 1")
        item2 = MockItem(id="doc2", name="Doc 2")

        vector_list = [(item1, 1, 0.9), (item2, 2, 0.8)]
        bm25_list = [(item2, 1, 10.0), (item1, 2, 8.0)]

        result = engine.fuse_with_items(
            [("vector", vector_list), ("bm25", bm25_list)],
        )

        assert len(result) == 2
        # Each result is (item, rrf_score, sources)
        assert all(isinstance(r[0], MockItem) for r in result)
        assert all(isinstance(r[1], float) for r in result)
        assert all(isinstance(r[2], dict) for r in result)

    def test_custom_id_extractor(self, engine: RRFFusionEngine) -> None:
        """Test with custom ID extractor."""

        @dataclass
        class CustomItem:
            custom_id: str
            value: int

        item1 = CustomItem(custom_id="x1", value=100)
        item2 = CustomItem(custom_id="x2", value=200)

        vector_list = [(item1, 1, 0.9), (item2, 2, 0.8)]

        def custom_extractor(item: CustomItem) -> str:
            return item.custom_id

        result = engine.fuse_with_items(
            [("vector", vector_list)],
            id_extractor=custom_extractor,
        )

        assert len(result) == 2
        assert result[0][0].custom_id == "x1"
