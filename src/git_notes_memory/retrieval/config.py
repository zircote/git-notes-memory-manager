"""Configuration for hybrid search and retrieval features.

RET-H-003: Configuration dataclass for all retrieval settings,
loaded from environment variables with sensible defaults.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

__all__ = ["HybridSearchConfig", "SearchMode"]


SearchMode = Literal["hybrid", "vector", "bm25", "entity"]


@dataclass(frozen=True)
class HybridSearchConfig:
    """Configuration for hybrid search and retrieval features.

    Attributes:
        mode: Default search mode. Options: hybrid, vector, bm25, entity.
        rrf_k: RRF smoothing parameter (default 60).
        vector_weight: Weight for vector search in RRF (default 1.0).
        bm25_weight: Weight for BM25 search in RRF (default 1.0).
        entity_weight: Weight for entity matching in RRF (default 0.8).
        entity_boost_enabled: Whether to boost results matching query entities.
        temporal_enabled: Whether to extract and index temporal references.
        query_expansion_enabled: Whether to use LLM query expansion (opt-in).
        expand_query_default: Default value for expand_query parameter.
        parallel_search: Whether to run vector and BM25 searches in parallel.
        max_results_per_source: Max results from each source before fusion.
        spacy_model: spaCy model for NER (default: en_core_web_sm).
    """

    mode: SearchMode = "hybrid"
    rrf_k: int = 60
    vector_weight: float = 1.0
    bm25_weight: float = 1.0
    entity_weight: float = 0.8
    entity_boost_enabled: bool = True
    temporal_enabled: bool = True
    query_expansion_enabled: bool = True
    expand_query_default: bool = False  # Opt-in per ADR-007
    parallel_search: bool = True
    max_results_per_source: int = 100
    spacy_model: str = "en_core_web_sm"

    # Environment variable prefix for config
    _env_prefix: str = field(default="HYBRID_SEARCH_", repr=False, compare=False)

    @classmethod
    def from_env(cls, prefix: str = "HYBRID_SEARCH_") -> HybridSearchConfig:
        """Load configuration from environment variables.

        Args:
            prefix: Environment variable prefix (default: HYBRID_SEARCH_).

        Returns:
            HybridSearchConfig loaded from environment.

        Environment Variables:
            HYBRID_SEARCH_MODE: Search mode (hybrid, vector, bm25, entity).
            HYBRID_SEARCH_RRF_K: RRF k parameter.
            HYBRID_SEARCH_VECTOR_WEIGHT: Vector search weight.
            HYBRID_SEARCH_BM25_WEIGHT: BM25 search weight.
            HYBRID_SEARCH_ENTITY_WEIGHT: Entity matching weight.
            HYBRID_SEARCH_ENTITY_BOOST_ENABLED: Enable entity boosting.
            HYBRID_SEARCH_TEMPORAL_ENABLED: Enable temporal extraction.
            HYBRID_SEARCH_QUERY_EXPANSION_ENABLED: Enable LLM query expansion.
            HYBRID_SEARCH_EXPAND_QUERY_DEFAULT: Default for expand_query param.
            HYBRID_SEARCH_PARALLEL: Run searches in parallel.
            HYBRID_SEARCH_MAX_RESULTS_PER_SOURCE: Max results per source.
            HYBRID_SEARCH_SPACY_MODEL: spaCy model name.
        """

        def get_str(key: str, default: str) -> str:
            return os.environ.get(f"{prefix}{key}", default)

        def get_int(key: str, default: int) -> int:
            value = os.environ.get(f"{prefix}{key}")
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                logger.warning(
                    "Invalid int value for %s%s: %s, using default %d",
                    prefix,
                    key,
                    value,
                    default,
                )
                return default

        def get_float(key: str, default: float) -> float:
            value = os.environ.get(f"{prefix}{key}")
            if value is None:
                return default
            try:
                return float(value)
            except ValueError:
                logger.warning(
                    "Invalid float value for %s%s: %s, using default %f",
                    prefix,
                    key,
                    value,
                    default,
                )
                return default

        def get_bool(key: str, default: bool) -> bool:
            value = os.environ.get(f"{prefix}{key}")
            if value is None:
                return default
            return value.lower() in ("true", "1", "yes", "on")

        # Validate mode
        mode_value = get_str("MODE", "hybrid")
        if mode_value not in ("hybrid", "vector", "bm25", "entity"):
            logger.warning(
                "Invalid search mode: %s, using 'hybrid'",
                mode_value,
            )
            mode_value = "hybrid"

        return cls(
            mode=mode_value,
            rrf_k=get_int("RRF_K", 60),
            vector_weight=get_float("VECTOR_WEIGHT", 1.0),
            bm25_weight=get_float("BM25_WEIGHT", 1.0),
            entity_weight=get_float("ENTITY_WEIGHT", 0.8),
            entity_boost_enabled=get_bool("ENTITY_BOOST_ENABLED", True),
            temporal_enabled=get_bool("TEMPORAL_ENABLED", True),
            query_expansion_enabled=get_bool("QUERY_EXPANSION_ENABLED", True),
            expand_query_default=get_bool("EXPAND_QUERY_DEFAULT", False),
            parallel_search=get_bool("PARALLEL", True),
            max_results_per_source=get_int("MAX_RESULTS_PER_SOURCE", 100),
            spacy_model=get_str("SPACY_MODEL", "en_core_web_sm"),
        )

    def get_rrf_weights(self) -> tuple[tuple[str, float], ...]:
        """Get weights as tuples for RRFConfig.

        Returns:
            Tuple of (source_name, weight) tuples.
        """
        return (
            ("vector", self.vector_weight),
            ("bm25", self.bm25_weight),
            ("entity", self.entity_weight),
        )
