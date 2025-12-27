"""Search engine for the memory index database.

ARCH-H-001: Extracted from IndexService to follow Single Responsibility Principle.
This module handles vector similarity search and full-text search operations.
"""

from __future__ import annotations

import sqlite3
import struct
from collections.abc import Callable
from functools import lru_cache
from typing import TYPE_CHECKING

from git_notes_memory.exceptions import MemoryIndexError
from git_notes_memory.observability.decorators import measure_duration
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.tracing import trace_operation

if TYPE_CHECKING:
    from collections.abc import Sequence

    from git_notes_memory.models import Memory

__all__ = ["SearchEngine"]


# =============================================================================
# Helpers
# =============================================================================


@lru_cache(maxsize=1)
def _get_struct_format(dimensions: int) -> struct.Struct:
    """Get a cached struct.Struct for packing embeddings.

    The embedding dimensions are typically constant (384 for all-MiniLM-L6-v2),
    so caching the compiled Struct avoids repeated format string parsing.

    Args:
        dimensions: Number of float values in the embedding.

    Returns:
        A compiled struct.Struct instance for packing.
    """
    return struct.Struct(f"{dimensions}f")


# =============================================================================
# SearchEngine
# =============================================================================


class SearchEngine:
    """Handles vector similarity and full-text search operations.

    ARCH-H-001: Extracted from IndexService to separate search concerns from
    CRUD and schema operations.

    Attributes:
        conn: The SQLite database connection.
        row_to_memory: Callback to convert SQLite rows to Memory objects.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        row_to_memory: Callable[[sqlite3.Row], Memory],
    ) -> None:
        """Initialize SearchEngine with a database connection.

        Args:
            conn: An open SQLite database connection.
            row_to_memory: Callback function to convert rows to Memory objects.
        """
        self._conn = conn
        self._row_to_memory = row_to_memory

    @measure_duration("index_search_vector")
    def search_vector(
        self,
        query_embedding: Sequence[float],
        k: int = 10,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[tuple[Memory, float]]:
        """Search for similar memories using vector similarity.

        Uses KNN search via sqlite-vec to find the k nearest neighbors
        to the query embedding.

        Args:
            query_embedding: The query embedding vector.
            k: Number of nearest neighbors to return.
            namespace: Optional namespace filter.
            spec: Optional specification filter.
            domain: Optional domain filter ('user' or 'project').
                None searches all domains (default, backward compatible).

        Returns:
            List of (Memory, distance) tuples sorted by distance ascending.
            Lower distance means more similar.

        Raises:
            MemoryIndexError: If the search fails.
        """
        metrics = get_metrics()

        with trace_operation("index.search_vector", labels={"k": str(k)}):
            blob = _get_struct_format(len(query_embedding)).pack(*query_embedding)

            cursor = self._conn.cursor()
            try:
                # Build parameterized query with optional filters
                # Use single JOIN to eliminate N+1 query pattern
                params: list[object] = [blob, k * 3]

                sql = """
                    SELECT m.*, v.distance
                    FROM vec_memories v
                    JOIN memories m ON v.id = m.id
                    WHERE v.embedding MATCH ?
                      AND k = ?
                """

                if namespace is not None:
                    sql += " AND m.namespace = ?"
                    params.append(namespace)
                if spec is not None:
                    sql += " AND m.spec = ?"
                    params.append(spec)
                if domain is not None:
                    sql += " AND m.domain = ?"
                    params.append(domain)

                sql += " ORDER BY v.distance LIMIT ?"
                params.append(k)

                cursor.execute(sql, params)

                results: list[tuple[Memory, float]] = []
                for row in cursor.fetchall():
                    memory = self._row_to_memory(row)
                    distance = row["distance"]
                    results.append((memory, distance))

                metrics.increment(
                    "index_searches_total",
                    labels={"search_type": "vector"},
                )

                return results

            except Exception as e:
                raise MemoryIndexError(
                    f"Vector search failed: {e}",
                    "Check embedding dimensions and retry",
                ) from e
            finally:
                cursor.close()

    def search_text(
        self,
        query: str,
        limit: int = 10,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[Memory]:
        """Search memories by text in summary and content using FTS5.

        PERF-H-005: Uses FTS5 full-text search for O(log n) performance
        instead of O(n) LIKE queries. Falls back to LIKE if FTS5 unavailable.

        Args:
            query: Text to search for. Supports FTS5 query syntax
                (AND, OR, NOT, phrases in quotes, prefix matching with *).
            limit: Maximum number of results.
            namespace: Optional namespace filter.
            spec: Optional specification filter.
            domain: Optional domain filter ('user' or 'project').
                None searches all domains (default, backward compatible).

        Returns:
            List of matching Memory objects, ranked by relevance.
        """
        # Try FTS5 first, fall back to LIKE if unavailable
        try:
            return self._search_text_fts5(query, limit, namespace, spec, domain)
        except sqlite3.OperationalError:
            # FTS5 table doesn't exist (pre-migration) - fall back to LIKE
            return self._search_text_like(query, limit, namespace, spec, domain)

    def _search_text_fts5(
        self,
        query: str,
        limit: int,
        namespace: str | None,
        spec: str | None,
        domain: str | None,
    ) -> list[Memory]:
        """FTS5-based text search with BM25 ranking."""
        # Escape special FTS5 characters and prepare query
        # Use double quotes to treat query as phrase for exact matching
        fts_query = f'"{query}"'

        sql = """
            SELECT m.*
            FROM memories m
            INNER JOIN memories_fts fts ON m.id = fts.id
            WHERE memories_fts MATCH ?
        """
        params: list[object] = [fts_query]

        if namespace is not None:
            sql += " AND m.namespace = ?"
            params.append(namespace)

        if spec is not None:
            sql += " AND m.spec = ?"
            params.append(spec)

        if domain is not None:
            sql += " AND m.domain = ?"
            params.append(domain)

        # BM25 ranking: lower = more relevant
        sql += " ORDER BY bm25(memories_fts) LIMIT ?"
        params.append(limit)

        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, params)
            return [self._row_to_memory(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def _search_text_like(
        self,
        query: str,
        limit: int,
        namespace: str | None,
        spec: str | None,
        domain: str | None,
    ) -> list[Memory]:
        """Fallback LIKE-based text search for pre-FTS5 databases."""
        search_term = f"%{query}%"

        sql = """
            SELECT * FROM memories
            WHERE (summary LIKE ? OR content LIKE ?)
        """
        params: list[object] = [search_term, search_term]

        if namespace is not None:
            sql += " AND namespace = ?"
            params.append(namespace)

        if spec is not None:
            sql += " AND spec = ?"
            params.append(spec)

        if domain is not None:
            sql += " AND domain = ?"
            params.append(domain)

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, params)
            return [self._row_to_memory(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    # =========================================================================
    # Ranked Search Methods (for RRF fusion)
    # =========================================================================

    @measure_duration("index_search_vector_ranked")
    def search_vector_ranked(
        self,
        query_embedding: Sequence[float],
        k: int = 100,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[tuple[Memory, int, float]]:
        """Search for similar memories and return with ranks.

        RET-H-002: Returns ranked results suitable for RRF fusion.
        Ranks are 1-indexed (first result has rank 1).

        Args:
            query_embedding: The query embedding vector.
            k: Maximum number of results.
            namespace: Optional namespace filter.
            spec: Optional specification filter.
            domain: Optional domain filter.

        Returns:
            List of (Memory, rank, distance) tuples sorted by distance ascending.
            Rank is 1-indexed. Lower distance means more similar.
        """
        results = self.search_vector(
            query_embedding, k=k, namespace=namespace, spec=spec, domain=domain
        )
        # Add 1-indexed ranks
        return [(memory, idx + 1, distance) for idx, (memory, distance) in enumerate(results)]

    @measure_duration("index_search_text_ranked")
    def search_text_ranked(
        self,
        query: str,
        limit: int = 100,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[tuple[Memory, int, float]]:
        """Search memories by text and return with BM25 ranks.

        RET-H-002: Returns ranked results suitable for RRF fusion.
        Ranks are 1-indexed (first result has rank 1).

        Args:
            query: Text to search for.
            limit: Maximum number of results.
            namespace: Optional namespace filter.
            spec: Optional specification filter.
            domain: Optional domain filter.

        Returns:
            List of (Memory, rank, bm25_score) tuples sorted by relevance.
            Rank is 1-indexed. Lower BM25 score means more relevant.
        """
        try:
            return self._search_text_fts5_ranked(query, limit, namespace, spec, domain)
        except sqlite3.OperationalError:
            # FTS5 table doesn't exist - fall back to LIKE (no real scores)
            memories = self._search_text_like(query, limit, namespace, spec, domain)
            # Assign synthetic scores based on position
            return [(memory, idx + 1, float(idx + 1)) for idx, memory in enumerate(memories)]

    def _search_text_fts5_ranked(
        self,
        query: str,
        limit: int,
        namespace: str | None,
        spec: str | None,
        domain: str | None,
    ) -> list[tuple[Memory, int, float]]:
        """FTS5-based text search returning ranks and BM25 scores."""
        fts_query = f'"{query}"'

        sql = """
            SELECT m.*, bm25(memories_fts) as bm25_score
            FROM memories m
            INNER JOIN memories_fts fts ON m.id = fts.id
            WHERE memories_fts MATCH ?
        """
        params: list[object] = [fts_query]

        if namespace is not None:
            sql += " AND m.namespace = ?"
            params.append(namespace)

        if spec is not None:
            sql += " AND m.spec = ?"
            params.append(spec)

        if domain is not None:
            sql += " AND m.domain = ?"
            params.append(domain)

        sql += " ORDER BY bm25(memories_fts) LIMIT ?"
        params.append(limit)

        cursor = self._conn.cursor()
        try:
            cursor.execute(sql, params)
            results: list[tuple[Memory, int, float]] = []
            for idx, row in enumerate(cursor.fetchall()):
                memory = self._row_to_memory(row)
                bm25_score = row["bm25_score"]
                results.append((memory, idx + 1, bm25_score))
            return results
        finally:
            cursor.close()
