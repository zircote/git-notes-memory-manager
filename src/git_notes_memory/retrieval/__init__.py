"""Memory Retrieval module for hybrid search, entity extraction, and query expansion.

This module provides advanced retrieval capabilities beyond basic vector search:

- **Hybrid Search**: Combines BM25 and vector search using Reciprocal Rank Fusion
- **Entity Extraction**: Extracts named entities (PERSON, PROJECT, TECHNOLOGY, FILE)
- **Temporal Extraction**: Parses dates for time-based queries
- **Query Expansion**: LLM-powered query enhancement

Usage:
    from git_notes_memory.retrieval import (
        get_hybrid_search_config,
        HybridSearchConfig,
    )

    config = get_hybrid_search_config()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from git_notes_memory.retrieval.config import HybridSearchConfig

logger = logging.getLogger(__name__)

__all__ = [
    "HybridSearchConfig",
    "get_hybrid_search_config",
]

# Lazy-loaded singleton
_config: HybridSearchConfig | None = None


def get_hybrid_search_config() -> HybridSearchConfig:
    """Get the hybrid search configuration singleton.

    Returns:
        HybridSearchConfig: Configuration loaded from environment variables.
    """
    global _config
    if _config is None:
        from git_notes_memory.retrieval.config import HybridSearchConfig

        _config = HybridSearchConfig.from_env()
    return _config


def __getattr__(name: str) -> object:
    """Lazy import for heavy modules."""
    if name == "HybridSearchConfig":
        from git_notes_memory.retrieval.config import HybridSearchConfig

        return HybridSearchConfig

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
