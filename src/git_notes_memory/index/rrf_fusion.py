"""Reciprocal Rank Fusion (RRF) engine for combining search rankings.

RET-H-001: RRF provides a robust method for fusing ranked lists from multiple
search strategies (vector, BM25, entity matching) without requiring score
normalization.

The RRF formula is:
    RRF_score(d) = Σ (weight_i / (k + rank_i(d)))

Where:
- k is a smoothing constant (default 60)
- weight_i is the weight for ranking source i
- rank_i(d) is the rank of document d in source i (1-indexed)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

__all__ = ["RRFFusionEngine", "RRFConfig", "RankedItem"]


T = TypeVar("T")


@dataclass(frozen=True)
class RRFConfig:
    """Configuration for RRF fusion.

    Attributes:
        k: Smoothing constant. Higher values reduce impact of high ranks.
            Default 60 is standard in literature.
        weights: Optional weights per source. Keys are source names,
            values are weight multipliers (default 1.0).
    """

    k: int = 60
    weights: tuple[tuple[str, float], ...] = ()

    def get_weight(self, source: str) -> float:
        """Get weight for a source, defaulting to 1.0."""
        for name, weight in self.weights:
            if name == source:
                return weight
        return 1.0


@dataclass(frozen=True)
class RankedItem:
    """A ranked item from a search source.

    Attributes:
        item_id: Unique identifier for the item.
        rank: 1-indexed rank in the source's results.
        score: Optional original score from the source.
        source: Name of the ranking source.
        item: The actual item object (e.g., Memory).
    """

    item_id: str
    rank: int
    score: float | None = None
    source: str = ""
    item: Any = None


@dataclass
class FusedResult:
    """Result of RRF fusion for a single item.

    Attributes:
        item_id: Unique identifier for the item.
        rrf_score: Combined RRF score.
        sources: Sources that contributed to this result with their ranks.
        item: The actual item object (if available from any source).
    """

    item_id: str
    rrf_score: float
    sources: dict[str, int] = field(default_factory=lambda: {})
    item: Any = None


class RRFFusionEngine:
    """Engine for combining ranked lists using Reciprocal Rank Fusion.

    RRF is parameter-light (just k and optional weights) and works well
    when combining sources with different score distributions.

    Example:
        >>> engine = RRFFusionEngine()
        >>> vector_results = [
        ...     RankedItem("doc1", rank=1),
        ...     RankedItem("doc2", rank=2),
        ... ]
        >>> bm25_results = [
        ...     RankedItem("doc2", rank=1),
        ...     RankedItem("doc1", rank=2),
        ... ]
        >>> fused = engine.fuse(
        ...     [
        ...         ("vector", vector_results),
        ...         ("bm25", bm25_results),
        ...     ]
        ... )
        >>> print(fused[0].item_id)  # doc1 or doc2, depending on weights
    """

    def __init__(self, config: RRFConfig | None = None) -> None:
        """Initialize the RRF fusion engine.

        Args:
            config: Optional RRF configuration. Uses defaults if not provided.
        """
        self._config = config or RRFConfig()

    @property
    def config(self) -> RRFConfig:
        """Get the current RRF configuration."""
        return self._config

    def fuse(
        self,
        ranked_lists: list[tuple[str, list[RankedItem]]],
        limit: int | None = None,
    ) -> list[FusedResult]:
        """Fuse multiple ranked lists using RRF.

        Args:
            ranked_lists: List of (source_name, ranked_items) tuples.
                Each ranked_items list should be ordered by rank (1-indexed).
            limit: Maximum number of results to return. If None, returns all.

        Returns:
            List of FusedResult objects, sorted by RRF score descending.

        Raises:
            ValueError: If any ranks are <= 0.
        """
        if not ranked_lists:
            return []

        # Validate inputs
        for _source_name, items in ranked_lists:
            for item in items:
                if item.rank <= 0:
                    msg = f"Rank must be > 0, got {item.rank} for {item.item_id}"
                    raise ValueError(msg)

        # Build score accumulator per item
        scores: dict[str, float] = {}
        sources: dict[str, dict[str, int]] = {}  # item_id -> {source -> rank}
        items_by_id: dict[str, Any] = {}  # Store items for later

        k = self._config.k

        for source_name, ranked_items in ranked_lists:
            weight = self._config.get_weight(source_name)

            for item in ranked_items:
                item_id = item.item_id

                # Calculate RRF contribution: weight / (k + rank)
                rrf_contribution = weight / (k + item.rank)

                # Accumulate scores
                if item_id not in scores:
                    scores[item_id] = 0.0
                    sources[item_id] = {}
                scores[item_id] += rrf_contribution
                sources[item_id][source_name] = item.rank

                # Store item if available
                if item.item is not None:
                    items_by_id[item_id] = item.item

        # Build result list
        results: list[FusedResult] = []
        for item_id, rrf_score in scores.items():
            results.append(
                FusedResult(
                    item_id=item_id,
                    rrf_score=rrf_score,
                    sources=sources[item_id],
                    item=items_by_id.get(item_id),
                )
            )

        # Sort by RRF score descending
        results.sort(key=lambda r: r.rrf_score, reverse=True)

        # Apply limit
        if limit is not None and limit > 0:
            results = results[:limit]

        return results

    def fuse_with_items(
        self,
        ranked_lists: list[tuple[str, list[tuple[T, int, float | None]]]],
        limit: int | None = None,
        id_extractor: Any = None,
    ) -> list[tuple[T, float, dict[str, int]]]:
        """Fuse ranked lists and return items directly.

        Convenience method when you have items with ranks.

        Args:
            ranked_lists: List of (source_name, [(item, rank, score), ...]) tuples.
            limit: Maximum results to return.
            id_extractor: Function to extract ID from item. Defaults to item.id.

        Returns:
            List of (item, rrf_score, sources) tuples.
        """

        def default_id_extractor(x: Any) -> str:
            return str(x.id) if hasattr(x, "id") else str(x)

        get_id = id_extractor if id_extractor is not None else default_id_extractor

        # Convert to RankedItems
        converted: list[tuple[str, list[RankedItem]]] = []
        for source_name, items in ranked_lists:
            ranked_items: list[RankedItem] = []
            for item, rank, score in items:
                item_id = get_id(item)
                ranked_items.append(
                    RankedItem(
                        item_id=item_id,
                        rank=rank,
                        score=score,
                        source=source_name,
                        item=item,
                    )
                )
            converted.append((source_name, ranked_items))

        # Fuse
        fused = self.fuse(converted, limit=limit)

        # Convert back to tuple format
        return [(r.item, r.rrf_score, r.sources) for r in fused if r.item is not None]
