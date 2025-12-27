"""Tests for the Hybrid Search Engine.

Tests cover:
- Basic hybrid search functionality
- Mode selection (hybrid, vector, bm25)
- RRF fusion integration
- Parallel vs sequential search
- Configuration options
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from git_notes_memory.index.hybrid_search import HybridSearchEngine, HybridSearchResult
from git_notes_memory.models import Memory
from git_notes_memory.retrieval.config import HybridSearchConfig

# =============================================================================
# Fixtures
# =============================================================================


@dataclass
class MockSearchEngine:
    """Mock search engine for testing."""

    vector_results: list[tuple[Memory, int, float]]
    text_results: list[tuple[Memory, int, float]]

    def search_vector_ranked(
        self,
        query_embedding: list[float],
        k: int = 100,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[tuple[Memory, int, float]]:
        """Return mock vector results."""
        return self.vector_results[:k]

    def search_text_ranked(
        self,
        query: str,
        limit: int = 100,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[tuple[Memory, int, float]]:
        """Return mock text results."""
        return self.text_results[:limit]


def make_memory(memory_id: str, summary: str = "Test") -> Memory:
    """Create a test memory."""
    return Memory(
        id=memory_id,
        commit_sha="abc1234",
        namespace="test",
        summary=summary,
        content="Test content",
        timestamp=datetime.now(UTC),
        tags=(),
    )


@pytest.fixture
def memories() -> dict[str, Memory]:
    """Create a set of test memories."""
    return {
        "mem1": make_memory("mem1", "PostgreSQL connection pooling"),
        "mem2": make_memory("mem2", "Database optimization strategies"),
        "mem3": make_memory("mem3", "Redis caching implementation"),
        "mem4": make_memory("mem4", "API rate limiting design"),
    }


@pytest.fixture
def mock_embed_fn() -> callable:
    """Create a mock embedding function."""
    return lambda _text: [0.1] * 384


@pytest.fixture
def mock_search_engine(memories: dict[str, Memory]) -> MockSearchEngine:
    """Create a mock search engine with preset results."""
    # Vector search: mem1 first, mem2 second
    vector_results = [
        (memories["mem1"], 1, 0.1),
        (memories["mem2"], 2, 0.2),
        (memories["mem3"], 3, 0.3),
    ]
    # BM25 search: mem2 first, mem1 second (different order)
    text_results = [
        (memories["mem2"], 1, -10.0),
        (memories["mem1"], 2, -8.0),
        (memories["mem4"], 3, -6.0),
    ]
    return MockSearchEngine(vector_results, text_results)


@pytest.fixture
def hybrid_engine(
    mock_search_engine: MockSearchEngine, mock_embed_fn: callable
) -> HybridSearchEngine:
    """Create a hybrid search engine with mocks."""
    return HybridSearchEngine(mock_search_engine, mock_embed_fn)


# =============================================================================
# Test: Basic Hybrid Search
# =============================================================================


class TestBasicHybridSearch:
    """Test basic hybrid search functionality."""

    def test_hybrid_search_returns_results(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test that hybrid search returns results."""
        results = hybrid_engine.search("PostgreSQL", limit=10)
        assert len(results) > 0
        assert all(isinstance(r, HybridSearchResult) for r in results)

    def test_hybrid_search_result_structure(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test HybridSearchResult structure."""
        results = hybrid_engine.search("PostgreSQL", limit=10)
        result = results[0]

        assert result.memory is not None
        assert result.rrf_score > 0
        assert result.rank >= 1
        assert isinstance(result.sources, dict)

    def test_hybrid_fuses_vector_and_bm25(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test that hybrid mode combines both search strategies."""
        results = hybrid_engine.search("PostgreSQL", limit=10)

        # Check that results come from both sources
        all_sources: set[str] = set()
        for r in results:
            all_sources.update(r.sources.keys())

        assert "vector" in all_sources
        assert "bm25" in all_sources

    def test_items_in_both_sources_rank_higher(
        self, hybrid_engine: HybridSearchEngine, memories: dict[str, Memory]
    ) -> None:
        """Test that items appearing in both sources get higher RRF scores."""
        results = hybrid_engine.search("PostgreSQL", limit=10)

        # mem1 and mem2 appear in both sources, should be ranked higher
        top_ids = {r.memory.id for r in results[:2]}
        assert "mem1" in top_ids or "mem2" in top_ids


# =============================================================================
# Test: Mode Selection
# =============================================================================


class TestModeSelection:
    """Test search mode selection."""

    def test_vector_only_mode(
        self, mock_search_engine: MockSearchEngine, mock_embed_fn: callable
    ) -> None:
        """Test vector-only search mode."""
        config = HybridSearchConfig(mode="vector")
        engine = HybridSearchEngine(mock_search_engine, mock_embed_fn, config)

        results = engine.search("test")

        # Should only have vector sources
        for r in results:
            assert "vector" in r.sources
            assert "bm25" not in r.sources

    def test_bm25_only_mode(
        self, mock_search_engine: MockSearchEngine, mock_embed_fn: callable
    ) -> None:
        """Test BM25-only search mode."""
        config = HybridSearchConfig(mode="bm25")
        engine = HybridSearchEngine(mock_search_engine, mock_embed_fn, config)

        results = engine.search("test")

        # Should only have bm25 sources
        for r in results:
            assert "bm25" in r.sources
            assert "vector" not in r.sources

    def test_mode_override_in_search(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test that mode can be overridden per search call."""
        # Default is hybrid
        hybrid_results = hybrid_engine.search("test")
        assert len({s for r in hybrid_results for s in r.sources}) >= 1

        # Override to vector only
        vector_results = hybrid_engine.search("test", mode="vector")
        for r in vector_results:
            assert "bm25" not in r.sources


# =============================================================================
# Test: RRF Score Calculations
# =============================================================================


class TestRRFScores:
    """Test RRF score calculations in hybrid search."""

    def test_rrf_scores_are_positive(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test that RRF scores are positive."""
        results = hybrid_engine.search("test")
        for r in results:
            assert r.rrf_score > 0

    def test_results_sorted_by_rrf_score(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test that results are sorted by RRF score descending."""
        results = hybrid_engine.search("test")

        for i in range(len(results) - 1):
            assert results[i].rrf_score >= results[i + 1].rrf_score

    def test_rank_matches_position(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test that ranks match 1-indexed positions."""
        results = hybrid_engine.search("test")

        for i, r in enumerate(results):
            assert r.rank == i + 1


# =============================================================================
# Test: Configuration Options
# =============================================================================


class TestConfiguration:
    """Test configuration options."""

    def test_custom_rrf_k(
        self, mock_search_engine: MockSearchEngine, mock_embed_fn: callable
    ) -> None:
        """Test custom RRF k parameter."""
        config = HybridSearchConfig(rrf_k=100)
        engine = HybridSearchEngine(mock_search_engine, mock_embed_fn, config)

        results = engine.search("test")

        # With k=100, score for rank 1 = 1/(100+1) = 0.0099...
        # Check that scores reflect the higher k
        assert results[0].rrf_score < 0.02  # Lower than k=60

    def test_parallel_search_disabled(
        self, mock_search_engine: MockSearchEngine, mock_embed_fn: callable
    ) -> None:
        """Test sequential search when parallel is disabled."""
        config = HybridSearchConfig(parallel_search=False)
        engine = HybridSearchEngine(mock_search_engine, mock_embed_fn, config)

        results = engine.search("test")

        # Should still return results
        assert len(results) > 0

    def test_max_results_per_source(
        self, mock_search_engine: MockSearchEngine, mock_embed_fn: callable
    ) -> None:
        """Test max_results_per_source limits."""
        config = HybridSearchConfig(max_results_per_source=2)
        engine = HybridSearchEngine(mock_search_engine, mock_embed_fn, config)

        # Even with high limit, should only get max 2 from each source
        results = engine.search("test", limit=100)

        # Max 4 unique results (2 from vector + 2 from bm25, some may overlap)
        assert len(results) <= 4


# =============================================================================
# Test: Limit Handling
# =============================================================================


class TestLimitHandling:
    """Test result limit handling."""

    def test_respects_limit(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test that limit is respected."""
        results = hybrid_engine.search("test", limit=2)
        assert len(results) <= 2

    def test_limit_one(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test limit of 1."""
        results = hybrid_engine.search("test", limit=1)
        assert len(results) == 1


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_results(self, mock_embed_fn: callable) -> None:
        """Test search with no results."""
        empty_engine = MockSearchEngine([], [])
        engine = HybridSearchEngine(empty_engine, mock_embed_fn)

        results = engine.search("test")
        assert results == []

    def test_only_vector_results(
        self, mock_embed_fn: callable, memories: dict[str, Memory]
    ) -> None:
        """Test when only vector search returns results."""
        vector_only = MockSearchEngine(
            [(memories["mem1"], 1, 0.1)],
            [],
        )
        engine = HybridSearchEngine(vector_only, mock_embed_fn)

        results = engine.search("test")
        assert len(results) == 1
        assert results[0].memory.id == "mem1"

    def test_only_bm25_results(
        self, mock_embed_fn: callable, memories: dict[str, Memory]
    ) -> None:
        """Test when only BM25 search returns results."""
        bm25_only = MockSearchEngine(
            [],
            [(memories["mem2"], 1, -10.0)],
        )
        engine = HybridSearchEngine(bm25_only, mock_embed_fn)

        results = engine.search("test")
        assert len(results) == 1
        assert results[0].memory.id == "mem2"


# =============================================================================
# Test: Context Manager
# =============================================================================


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager_usage(
        self, mock_search_engine: MockSearchEngine, mock_embed_fn: callable
    ) -> None:
        """Test using HybridSearchEngine as context manager."""
        with HybridSearchEngine(mock_search_engine, mock_embed_fn) as engine:
            results = engine.search("test")
            assert len(results) > 0


# =============================================================================
# Test: Async Search
# =============================================================================


class TestAsyncSearch:
    """Test async search functionality."""

    @pytest.mark.asyncio
    async def test_async_search(
        self, hybrid_engine: HybridSearchEngine
    ) -> None:
        """Test async search method."""
        results = await hybrid_engine.search_async("test", limit=5)
        assert len(results) > 0
        assert all(isinstance(r, HybridSearchResult) for r in results)


# =============================================================================
# Test: Filter Passthrough
# =============================================================================


class TestFilterPassthrough:
    """Test that filters are passed to underlying search methods."""

    def test_namespace_filter(
        self, mock_embed_fn: callable, memories: dict[str, Memory]
    ) -> None:
        """Test namespace filter is passed through."""
        search_engine = MagicMock()
        search_engine.search_vector_ranked.return_value = [
            (memories["mem1"], 1, 0.1)
        ]
        search_engine.search_text_ranked.return_value = []

        engine = HybridSearchEngine(search_engine, mock_embed_fn)
        engine.search("test", namespace="decisions")

        # Check that namespace was passed
        search_engine.search_vector_ranked.assert_called_once()
        call_args = search_engine.search_vector_ranked.call_args
        assert call_args.kwargs.get("namespace") == "decisions"

    def test_spec_filter(
        self, mock_embed_fn: callable, memories: dict[str, Memory]
    ) -> None:
        """Test spec filter is passed through."""
        search_engine = MagicMock()
        search_engine.search_vector_ranked.return_value = [
            (memories["mem1"], 1, 0.1)
        ]
        search_engine.search_text_ranked.return_value = []

        engine = HybridSearchEngine(search_engine, mock_embed_fn)
        engine.search("test", spec="my-project")

        call_args = search_engine.search_vector_ranked.call_args
        assert call_args.kwargs.get("spec") == "my-project"

    def test_domain_filter(
        self, mock_embed_fn: callable, memories: dict[str, Memory]
    ) -> None:
        """Test domain filter is passed through."""
        search_engine = MagicMock()
        search_engine.search_vector_ranked.return_value = [
            (memories["mem1"], 1, 0.1)
        ]
        search_engine.search_text_ranked.return_value = []

        engine = HybridSearchEngine(search_engine, mock_embed_fn)
        engine.search("test", domain="user")

        call_args = search_engine.search_vector_ranked.call_args
        assert call_args.kwargs.get("domain") == "user"
