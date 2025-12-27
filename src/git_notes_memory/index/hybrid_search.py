"""Hybrid Search Engine for combining vector and BM25 search with RRF.

RET-H-002: Orchestrates multiple search strategies and combines results
using Reciprocal Rank Fusion for improved retrieval accuracy.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from git_notes_memory.index.rrf_fusion import RankedItem, RRFConfig, RRFFusionEngine
from git_notes_memory.observability.decorators import measure_duration
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.tracing import trace_operation
from git_notes_memory.retrieval.config import HybridSearchConfig, SearchMode

if TYPE_CHECKING:
    from git_notes_memory.index.search_engine import SearchEngine
    from git_notes_memory.models import Memory

logger = logging.getLogger(__name__)

__all__ = ["HybridSearchEngine", "HybridSearchResult"]


@dataclass(frozen=True)
class HybridSearchResult:
    """Result from hybrid search with RRF scoring.

    Attributes:
        memory: The memory object.
        rrf_score: Combined RRF score from all sources.
        sources: Dict mapping source names to their ranks for this result.
        rank: Final rank in the combined results (1-indexed).
    """

    memory: Memory
    rrf_score: float
    sources: dict[str, int] = field(default_factory=dict)
    rank: int = 0


class HybridSearchEngine:
    """Engine for combining multiple search strategies using RRF.

    RET-H-002: This engine orchestrates vector similarity search and BM25
    full-text search, then combines results using Reciprocal Rank Fusion
    to leverage the strengths of both approaches.

    The hybrid approach helps because:
    - Vector search captures semantic similarity (synonyms, concepts)
    - BM25 captures exact term matches (names, technical terms)
    - RRF combines rankings without requiring score normalization

    Example:
        >>> engine = HybridSearchEngine(search_engine, embedding_fn, config)
        >>> results = engine.search("PostgreSQL connection pooling", limit=10)
        >>> for result in results:
        ...     print(f"[{result.rank}] {result.memory.summary} (RRF: {result.rrf_score:.4f})")

    Attributes:
        config: Configuration for hybrid search behavior.
    """

    def __init__(
        self,
        search_engine: SearchEngine,
        embed_fn: Callable[[str], Sequence[float]],
        config: HybridSearchConfig | None = None,
    ) -> None:
        """Initialize the hybrid search engine.

        Args:
            search_engine: The underlying SearchEngine for vector/text search.
            embed_fn: Function to generate embeddings from text.
            config: Optional configuration. Uses defaults if not provided.
        """
        self._search_engine = search_engine
        self._embed_fn = embed_fn
        self._config = config or HybridSearchConfig()
        self._rrf_engine = RRFFusionEngine(
            RRFConfig(k=self._config.rrf_k, weights=self._config.get_rrf_weights())
        )
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    @property
    def config(self) -> HybridSearchConfig:
        """Get the current configuration."""
        return self._config

    @measure_duration("hybrid_search")
    def search(
        self,
        query: str,
        limit: int = 10,
        mode: SearchMode | None = None,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[HybridSearchResult]:
        """Search memories using hybrid vector + BM25 strategy.

        Args:
            query: The search query text.
            limit: Maximum number of results to return.
            mode: Search mode override. If None, uses config default.
                - "hybrid": Combine vector and BM25 with RRF
                - "vector": Vector search only
                - "bm25": BM25 text search only
            namespace: Optional namespace filter.
            spec: Optional specification filter.
            domain: Optional domain filter.

        Returns:
            List of HybridSearchResult objects sorted by RRF score descending.
        """
        metrics = get_metrics()
        effective_mode = mode or self._config.mode

        with trace_operation(
            "hybrid_search.search",
            labels={"mode": effective_mode, "limit": str(limit)},
        ):
            metrics.increment(
                "hybrid_search_total",
                labels={"mode": effective_mode},
            )

            if effective_mode == "vector":
                return self._search_vector_only(query, limit, namespace, spec, domain)
            elif effective_mode == "bm25":
                return self._search_bm25_only(query, limit, namespace, spec, domain)
            else:
                return self._search_hybrid(query, limit, namespace, spec, domain)

    def _search_hybrid(
        self,
        query: str,
        limit: int,
        namespace: str | None,
        spec: str | None,
        domain: str | None,
    ) -> list[HybridSearchResult]:
        """Perform hybrid search with RRF fusion."""
        metrics = get_metrics()
        max_per_source = self._config.max_results_per_source

        # Get embedding for vector search
        with trace_operation("hybrid_search.embed"):
            query_embedding = self._embed_fn(query)

        if self._config.parallel_search:
            # Run searches in parallel using ThreadPoolExecutor
            with trace_operation("hybrid_search.parallel"):
                vector_future = self._executor.submit(
                    self._search_engine.search_vector_ranked,
                    query_embedding,
                    k=max_per_source,
                    namespace=namespace,
                    spec=spec,
                    domain=domain,
                )
                bm25_future = self._executor.submit(
                    self._search_engine.search_text_ranked,
                    query,
                    limit=max_per_source,
                    namespace=namespace,
                    spec=spec,
                    domain=domain,
                )

                vector_results = vector_future.result()
                bm25_results = bm25_future.result()
        else:
            # Sequential search
            vector_results = self._search_engine.search_vector_ranked(
                query_embedding,
                k=max_per_source,
                namespace=namespace,
                spec=spec,
                domain=domain,
            )
            bm25_results = self._search_engine.search_text_ranked(
                query,
                limit=max_per_source,
                namespace=namespace,
                spec=spec,
                domain=domain,
            )

        # Record per-source metrics
        metrics.observe("hybrid_search_vector_results", len(vector_results))
        metrics.observe("hybrid_search_bm25_results", len(bm25_results))

        # Convert to RankedItems for RRF fusion
        vector_ranked = [
            RankedItem(
                item_id=memory.id,
                rank=rank,
                score=score,
                source="vector",
                item=memory,
            )
            for memory, rank, score in vector_results
        ]

        bm25_ranked = [
            RankedItem(
                item_id=memory.id,
                rank=rank,
                score=score,
                source="bm25",
                item=memory,
            )
            for memory, rank, score in bm25_results
        ]

        # Fuse with RRF
        with trace_operation("hybrid_search.rrf_fusion"):
            fused = self._rrf_engine.fuse(
                [("vector", vector_ranked), ("bm25", bm25_ranked)],
                limit=limit,
            )

        # Convert to HybridSearchResult
        results: list[HybridSearchResult] = []
        for idx, fused_result in enumerate(fused):
            if fused_result.item is not None:
                results.append(
                    HybridSearchResult(
                        memory=fused_result.item,
                        rrf_score=fused_result.rrf_score,
                        sources=fused_result.sources,
                        rank=idx + 1,
                    )
                )

        return results

    def _search_vector_only(
        self,
        query: str,
        limit: int,
        namespace: str | None,
        spec: str | None,
        domain: str | None,
    ) -> list[HybridSearchResult]:
        """Perform vector-only search."""
        with trace_operation("hybrid_search.embed"):
            query_embedding = self._embed_fn(query)

        results = self._search_engine.search_vector_ranked(
            query_embedding,
            k=limit,
            namespace=namespace,
            spec=spec,
            domain=domain,
        )

        return [
            HybridSearchResult(
                memory=memory,
                rrf_score=1.0 / (self._config.rrf_k + rank),
                sources={"vector": rank},
                rank=rank,
            )
            for memory, rank, _score in results
        ]

    def _search_bm25_only(
        self,
        query: str,
        limit: int,
        namespace: str | None,
        spec: str | None,
        domain: str | None,
    ) -> list[HybridSearchResult]:
        """Perform BM25-only text search."""
        results = self._search_engine.search_text_ranked(
            query,
            limit=limit,
            namespace=namespace,
            spec=spec,
            domain=domain,
        )

        return [
            HybridSearchResult(
                memory=memory,
                rrf_score=1.0 / (self._config.rrf_k + rank),
                sources={"bm25": rank},
                rank=rank,
            )
            for memory, rank, _score in results
        ]

    async def search_async(
        self,
        query: str,
        limit: int = 10,
        mode: SearchMode | None = None,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[HybridSearchResult]:
        """Async version of search for use in async contexts.

        Args:
            query: The search query text.
            limit: Maximum number of results to return.
            mode: Search mode override.
            namespace: Optional namespace filter.
            spec: Optional specification filter.
            domain: Optional domain filter.

        Returns:
            List of HybridSearchResult objects.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.search(query, limit, mode, namespace, spec, domain),
        )

    def close(self) -> None:
        """Shutdown the thread pool executor."""
        self._executor.shutdown(wait=False)

    def __enter__(self) -> HybridSearchEngine:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()
