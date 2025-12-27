"""Index module for SQLite + sqlite-vec memory search.

ARCH-H-001: This module has been refactored from a single God Object (IndexService)
into composed components following the Single Responsibility Principle:

- SchemaManager: Database schema creation, migrations, and version management
- SearchEngine: Vector similarity search and full-text search operations
- IndexService: Main facade providing the public API (backward compatible)

Usage:
    >>> from git_notes_memory.index import IndexService
    >>> index = IndexService()
    >>> index.initialize()
    >>> index.insert(memory, embedding)
    >>> results = index.search_vector(query_embedding)
"""

from .hybrid_search import HybridSearchEngine, HybridSearchResult
from .rrf_fusion import RankedItem, RRFConfig, RRFFusionEngine
from .schema_manager import SCHEMA_VERSION, SchemaManager
from .search_engine import SearchEngine
from .service import IndexService

__all__ = [
    "HybridSearchEngine",
    "HybridSearchResult",
    "IndexService",
    "RankedItem",
    "RRFConfig",
    "RRFFusionEngine",
    "SchemaManager",
    "SearchEngine",
    "SCHEMA_VERSION",
]
