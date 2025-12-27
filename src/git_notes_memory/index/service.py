"""IndexService - main facade for memory index operations.

ARCH-H-001: Refactored from monolithic God Object to composed service using:
- SchemaManager: Database schema and migrations
- SearchEngine: Vector and text search operations

The public API remains backward compatible.
"""

from __future__ import annotations

import logging
import sqlite3
import struct
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from git_notes_memory.config import get_index_path
from git_notes_memory.exceptions import MemoryIndexError
from git_notes_memory.observability.decorators import measure_duration
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.tracing import trace_operation

from .schema_manager import SchemaManager
from .search_engine import SearchEngine

if TYPE_CHECKING:
    from collections.abc import Sequence

    from git_notes_memory.models import IndexStats, Memory

logger = logging.getLogger(__name__)

__all__ = ["IndexService"]


# =============================================================================
# Helpers
# =============================================================================


@lru_cache(maxsize=1)
def _get_struct_format(dimensions: int) -> struct.Struct:
    """Get a cached struct.Struct for packing embeddings."""
    return struct.Struct(f"{dimensions}f")


# =============================================================================
# IndexService
# =============================================================================


class IndexService:
    """SQLite + sqlite-vec database management for memory search.

    ARCH-H-001: Refactored to use composition with extracted components:
    - SchemaManager: Handles schema creation and migrations
    - SearchEngine: Handles vector and text search operations

    The public API remains unchanged for backward compatibility.

    Attributes:
        db_path: Path to the SQLite database file.

    Example:
        >>> index = IndexService()
        >>> index.initialize()
        >>> index.insert(memory, embedding)
        >>> results = index.search_vector(query_embedding, k=10)
        >>> index.close()
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the IndexService.

        Args:
            db_path: Path to the SQLite database. If None, uses the default
                path from config.get_index_path().
        """
        self.db_path = db_path or get_index_path()
        self._conn: sqlite3.Connection | None = None
        self._initialized = False
        self._schema_manager: SchemaManager | None = None
        self._search_engine: SearchEngine | None = None

    @property
    def is_initialized(self) -> bool:
        """Check if the database has been initialized."""
        return self._initialized and self._conn is not None

    def initialize(self) -> None:
        """Initialize the database and load sqlite-vec extension.

        Creates the data directory if needed, connects to the database,
        loads the sqlite-vec extension, and creates the schema.

        Raises:
            MemoryIndexError: If the database cannot be initialized or
                the sqlite-vec extension cannot be loaded.
        """
        if self._initialized:
            return

        try:
            # Ensure data directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Connect to database
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row

            # Enable WAL mode for better concurrent access
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            # RES-M-004: Set busy_timeout to prevent "database is locked" errors
            self._conn.execute("PRAGMA busy_timeout=5000")

            # Initialize components
            self._schema_manager = SchemaManager(self._conn)
            self._schema_manager.load_vec_extension()
            self._schema_manager.create_schema()

            # Initialize search engine with row converter callback
            self._search_engine = SearchEngine(self._conn, self._row_to_memory)

            self._initialized = True

        except Exception as e:
            if self._conn is not None:
                with suppress(Exception):
                    self._conn.close()
            self._conn = None
            self._schema_manager = None
            self._search_engine = None
            self._initialized = False
            if isinstance(e, MemoryIndexError):
                raise
            raise MemoryIndexError(
                f"Failed to initialize index database: {e}",
                "Check disk space and permissions, then retry",
            ) from e

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        """Context manager for database cursor with error handling.

        Yields:
            A database cursor.

        Raises:
            MemoryIndexError: If the database is not initialized.
        """
        if self._conn is None:
            raise MemoryIndexError(
                "Database not initialized",
                "Call initialize() before performing operations",
            )
        cursor = self._conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._schema_manager = None
        self._search_engine = None
        self._initialized = False

    # =========================================================================
    # Insert Operations
    # =========================================================================

    @measure_duration("index_insert")
    def insert(
        self,
        memory: Memory,
        embedding: Sequence[float] | None = None,
    ) -> bool:
        """Insert a memory into the index.

        Args:
            memory: The Memory object to insert.
            embedding: Optional embedding vector. If provided, also inserts
                into the vector table for similarity search.

        Returns:
            True if the insert was successful.

        Raises:
            MemoryIndexError: If the insert fails.
        """
        from git_notes_memory.models import Memory

        if not isinstance(memory, Memory):
            raise MemoryIndexError(
                "Invalid memory object",
                "Provide a valid Memory instance",
            )

        now = datetime.now(UTC).isoformat()
        metrics = get_metrics()

        with (
            trace_operation("index.insert", labels={"namespace": memory.namespace}),
            self._cursor() as cursor,
        ):
            try:
                cursor.execute(
                    """
                    INSERT INTO memories (
                        id, commit_sha, namespace, summary, content,
                        timestamp, domain, repo_path, spec, phase, tags, status,
                        relates_to, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory.id,
                        memory.commit_sha,
                        memory.namespace,
                        memory.summary,
                        memory.content,
                        memory.timestamp.isoformat(),
                        memory.domain,
                        memory.repo_path,
                        memory.spec,
                        memory.phase,
                        ",".join(memory.tags) if memory.tags else None,
                        memory.status,
                        ",".join(memory.relates_to) if memory.relates_to else None,
                        now,
                        now,
                    ),
                )

                if embedding is not None:
                    self._insert_embedding(cursor, memory.id, embedding)

                self._conn.commit()  # type: ignore[union-attr]

                metrics.increment(
                    "index_inserts_total",
                    labels={"namespace": memory.namespace},
                )

                return True

            except sqlite3.IntegrityError as e:
                self._conn.rollback()  # type: ignore[union-attr]
                raise MemoryIndexError(
                    f"Memory with id '{memory.id}' already exists",
                    "Use update() to modify existing memories",
                ) from e
            except Exception as e:
                self._conn.rollback()  # type: ignore[union-attr]
                raise MemoryIndexError(
                    f"Failed to insert memory: {e}",
                    "Check memory data and retry",
                ) from e

    def insert_batch(
        self,
        memories: Sequence[Memory],
        embeddings: Sequence[Sequence[float]] | None = None,
    ) -> int:
        """Insert multiple memories in a single transaction.

        More efficient than individual inserts for bulk operations.

        Args:
            memories: List of Memory objects to insert.
            embeddings: Optional list of embedding vectors (must match
                memories length if provided).

        Returns:
            Number of successfully inserted memories.

        Raises:
            MemoryIndexError: If the batch insert fails.
        """
        if not memories:
            return 0

        if embeddings is not None and len(embeddings) != len(memories):
            raise MemoryIndexError(
                "Embeddings count must match memories count",
                "Provide matching lists or None for embeddings",
            )

        now = datetime.now(UTC).isoformat()
        inserted = 0

        with self._cursor() as cursor:
            try:
                for i, memory in enumerate(memories):
                    try:
                        cursor.execute(
                            """
                            INSERT INTO memories (
                                id, commit_sha, namespace, summary, content,
                                timestamp, domain, repo_path, spec, phase, tags, status,
                                relates_to, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                memory.id,
                                memory.commit_sha,
                                memory.namespace,
                                memory.summary,
                                memory.content,
                                memory.timestamp.isoformat(),
                                memory.domain,
                                memory.repo_path,
                                memory.spec,
                                memory.phase,
                                ",".join(memory.tags) if memory.tags else None,
                                memory.status,
                                (
                                    ",".join(memory.relates_to)
                                    if memory.relates_to
                                    else None
                                ),
                                now,
                                now,
                            ),
                        )

                        if embeddings is not None:
                            self._insert_embedding(cursor, memory.id, embeddings[i])

                        inserted += 1

                    except sqlite3.IntegrityError:
                        # Skip duplicates in batch mode
                        continue

                self._conn.commit()  # type: ignore[union-attr]
                return inserted

            except Exception as e:
                self._conn.rollback()  # type: ignore[union-attr]
                raise MemoryIndexError(
                    f"Failed to insert batch: {e}",
                    "Check memory data and retry",
                ) from e

    def _insert_embedding(
        self,
        cursor: sqlite3.Cursor,
        memory_id: str,
        embedding: Sequence[float],
    ) -> None:
        """Insert an embedding into the vector table."""
        blob = _get_struct_format(len(embedding)).pack(*embedding)
        cursor.execute(
            "INSERT INTO vec_memories (id, embedding) VALUES (?, ?)",
            (memory_id, blob),
        )

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get(self, memory_id: str) -> Memory | None:
        """Get a memory by ID.

        Args:
            memory_id: The memory ID to retrieve.

        Returns:
            The Memory object if found, None otherwise.
        """
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_memory(row)

    def get_batch(self, memory_ids: Sequence[str]) -> list[Memory]:
        """Get multiple memories by IDs.

        Args:
            memory_ids: List of memory IDs to retrieve.

        Returns:
            List of Memory objects (may be shorter than input if some not found).
        """
        if not memory_ids:
            return []

        placeholders = ",".join("?" * len(memory_ids))
        with self._cursor() as cursor:
            # placeholders is only "?" chars - safe parameterized query
            cursor.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})",  # noqa: S608 # nosec B608
                memory_ids,
            )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_spec(
        self,
        spec: str,
        namespace: str | None = None,
        limit: int | None = None,
        domain: str | None = None,
    ) -> list[Memory]:
        """Get all memories for a specification."""
        query = "SELECT * FROM memories WHERE spec = ?"
        params: list[object] = [spec]

        if namespace is not None:
            query += " AND namespace = ?"
            params.append(namespace)

        if domain is not None:
            query += " AND domain = ?"
            params.append(domain)

        query += " ORDER BY timestamp DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_commit(self, commit_sha: str) -> list[Memory]:
        """Get all memories attached to a commit."""
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM memories WHERE commit_sha = ? ORDER BY timestamp",
                (commit_sha,),
            )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_namespace(
        self,
        namespace: str,
        spec: str | None = None,
        limit: int | None = None,
        domain: str | None = None,
    ) -> list[Memory]:
        """Get all memories in a namespace."""
        query = "SELECT * FROM memories WHERE namespace = ?"
        params: list[object] = [namespace]

        if spec is not None:
            query += " AND spec = ?"
            params.append(spec)

        if domain is not None:
            query += " AND domain = ?"
            params.append(domain)

        query += " ORDER BY timestamp DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def list_recent(
        self,
        limit: int = 10,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[Memory]:
        """Get the most recent memories."""
        query = "SELECT * FROM memories WHERE 1=1"
        params: list[object] = []

        if namespace is not None:
            query += " AND namespace = ?"
            params.append(namespace)

        if spec is not None:
            query += " AND spec = ?"
            params.append(spec)

        if domain is not None:
            query += " AND domain = ?"
            params.append(domain)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_all_ids(
        self,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[str]:
        """Get memory IDs in the index with optional pagination."""
        if limit is not None:
            query = "SELECT id FROM memories LIMIT ? OFFSET ?"
            params: tuple[int, ...] = (limit, offset)
        else:
            query = "SELECT id FROM memories"
            params = ()

        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [row[0] for row in cursor.fetchall()]

    def iter_all_ids(self, batch_size: int = 1000) -> Iterator[str]:
        """Iterate over all memory IDs in batches."""
        offset = 0
        while True:
            batch = self.get_all_ids(limit=batch_size, offset=offset)
            if not batch:
                break
            yield from batch
            offset += len(batch)
            if len(batch) < batch_size:
                break

    def get_all_memories(
        self,
        namespace: str | None = None,
    ) -> list[Memory]:
        """Get all memories in the index."""
        query = "SELECT * FROM memories WHERE 1=1"
        params: list[object] = []

        if namespace is not None:
            query += " AND namespace = ?"
            params.append(namespace)

        query += " ORDER BY timestamp DESC"

        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def exists(self, memory_id: str) -> bool:
        """Check if a memory exists in the index."""
        with self._cursor() as cursor:
            cursor.execute("SELECT 1 FROM memories WHERE id = ?", (memory_id,))
            return cursor.fetchone() is not None

    def get_existing_ids(self, memory_ids: list[str]) -> set[str]:
        """Check which memory IDs exist in the index (batch operation)."""
        if not memory_ids:
            return set()

        batch_size = 500
        existing: set[str] = set()

        for i in range(0, len(memory_ids), batch_size):
            batch = memory_ids[i : i + batch_size]
            placeholders = ",".join("?" * len(batch))
            query = f"SELECT id FROM memories WHERE id IN ({placeholders})"  # noqa: S608 # nosec B608

            with self._cursor() as cursor:
                cursor.execute(query, batch)
                existing.update(row[0] for row in cursor.fetchall())

        return existing

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        """Convert a database row to a Memory object."""
        from git_notes_memory.models import Memory

        tags_str = row["tags"]
        tags = tuple(tags_str.split(",")) if tags_str else ()

        relates_str = row["relates_to"]
        relates_to = tuple(relates_str.split(",")) if relates_str else ()

        timestamp = datetime.fromisoformat(row["timestamp"])
        domain = row["domain"] if row["domain"] else "project"

        return Memory(
            id=row["id"],
            commit_sha=row["commit_sha"],
            namespace=row["namespace"],
            summary=row["summary"],
            content=row["content"],
            timestamp=timestamp,
            domain=domain,
            spec=row["spec"],
            phase=row["phase"],
            tags=tags,
            status=row["status"] or "active",
            relates_to=relates_to,
        )

    # =========================================================================
    # Update Operations
    # =========================================================================

    def update(
        self,
        memory: Memory,
        embedding: Sequence[float] | None = None,
    ) -> bool:
        """Update an existing memory."""
        now = datetime.now(UTC).isoformat()

        with self._cursor() as cursor:
            try:
                cursor.execute(
                    """
                    UPDATE memories SET
                        commit_sha = ?,
                        namespace = ?,
                        summary = ?,
                        content = ?,
                        timestamp = ?,
                        domain = ?,
                        spec = ?,
                        phase = ?,
                        tags = ?,
                        status = ?,
                        relates_to = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        memory.commit_sha,
                        memory.namespace,
                        memory.summary,
                        memory.content,
                        memory.timestamp.isoformat(),
                        memory.domain,
                        memory.spec,
                        memory.phase,
                        ",".join(memory.tags) if memory.tags else None,
                        memory.status,
                        ",".join(memory.relates_to) if memory.relates_to else None,
                        now,
                        memory.id,
                    ),
                )

                if cursor.rowcount == 0:
                    return False

                if embedding is not None:
                    self._update_embedding(cursor, memory.id, embedding)

                self._conn.commit()  # type: ignore[union-attr]
                return True

            except Exception as e:
                self._conn.rollback()  # type: ignore[union-attr]
                raise MemoryIndexError(
                    f"Failed to update memory: {e}",
                    "Check memory data and retry",
                ) from e

    def _update_embedding(
        self,
        cursor: sqlite3.Cursor,
        memory_id: str,
        embedding: Sequence[float],
    ) -> None:
        """Update an embedding in the vector table."""
        blob = _get_struct_format(len(embedding)).pack(*embedding)
        cursor.execute("DELETE FROM vec_memories WHERE id = ?", (memory_id,))
        cursor.execute(
            "INSERT INTO vec_memories (id, embedding) VALUES (?, ?)",
            (memory_id, blob),
        )

    def update_embedding(
        self,
        memory_id: str,
        embedding: Sequence[float],
    ) -> bool:
        """Update only the embedding for a memory."""
        if not self.exists(memory_id):
            return False

        with self._cursor() as cursor:
            try:
                self._update_embedding(cursor, memory_id, embedding)
                self._conn.commit()  # type: ignore[union-attr]
                return True
            except Exception as e:
                self._conn.rollback()  # type: ignore[union-attr]
                raise MemoryIndexError(
                    f"Failed to update embedding: {e}",
                    "Check embedding data and retry",
                ) from e

    # =========================================================================
    # Delete Operations
    # =========================================================================

    def delete(self, memory_id: str) -> bool:
        """Delete a memory from the index."""
        with self._cursor() as cursor:
            try:
                cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                deleted = cursor.rowcount > 0
                cursor.execute("DELETE FROM vec_memories WHERE id = ?", (memory_id,))
                self._conn.commit()  # type: ignore[union-attr]
                return deleted
            except Exception as e:
                self._conn.rollback()  # type: ignore[union-attr]
                raise MemoryIndexError(
                    f"Failed to delete memory: {e}",
                    "Retry the operation",
                ) from e

    def delete_batch(self, memory_ids: Sequence[str]) -> int:
        """Delete multiple memories."""
        if not memory_ids:
            return 0

        placeholders = ",".join("?" * len(memory_ids))

        with self._cursor() as cursor:
            try:
                # placeholders is only "?" chars - safe parameterized query
                cursor.execute(
                    f"DELETE FROM memories WHERE id IN ({placeholders})",  # noqa: S608 # nosec B608
                    memory_ids,
                )
                deleted = cursor.rowcount
                # placeholders is only "?" chars - safe parameterized query
                cursor.execute(
                    f"DELETE FROM vec_memories WHERE id IN ({placeholders})",  # noqa: S608 # nosec B608
                    memory_ids,
                )
                self._conn.commit()  # type: ignore[union-attr]
                return deleted
            except Exception as e:
                self._conn.rollback()  # type: ignore[union-attr]
                raise MemoryIndexError(
                    f"Failed to delete batch: {e}",
                    "Retry the operation",
                ) from e

    def clear(self) -> int:
        """Delete all memories from the index."""
        with self._cursor() as cursor:
            try:
                cursor.execute("SELECT COUNT(*) FROM memories")
                row = cursor.fetchone()
                count: int = int(row[0]) if row else 0

                cursor.execute("DELETE FROM memories")
                cursor.execute("DELETE FROM vec_memories")

                self._conn.commit()  # type: ignore[union-attr]
                return count
            except Exception as e:
                self._conn.rollback()  # type: ignore[union-attr]
                raise MemoryIndexError(
                    f"Failed to clear index: {e}",
                    "Retry the operation",
                ) from e

    # =========================================================================
    # Search Operations (delegated to SearchEngine)
    # =========================================================================

    def search_vector(
        self,
        query_embedding: Sequence[float],
        k: int = 10,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[tuple[Memory, float]]:
        """Search for similar memories using vector similarity.

        Delegates to SearchEngine component.
        """
        if self._search_engine is None:
            raise MemoryIndexError(
                "Database not initialized",
                "Call initialize() before performing operations",
            )
        return self._search_engine.search_vector(
            query_embedding, k, namespace, spec, domain
        )

    def search_text(
        self,
        query: str,
        limit: int = 10,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> list[Memory]:
        """Search memories by text using FTS5.

        Delegates to SearchEngine component.
        """
        if self._search_engine is None:
            raise MemoryIndexError(
                "Database not initialized",
                "Call initialize() before performing operations",
            )
        return self._search_engine.search_text(query, limit, namespace, spec, domain)

    # =========================================================================
    # Statistics Operations
    # =========================================================================

    def get_stats(self) -> IndexStats:
        """Get statistics about the index."""
        from git_notes_memory.models import IndexStats

        with self._cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM memories")
            total = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT namespace, COUNT(*) as count
                FROM memories
                GROUP BY namespace
                ORDER BY count DESC
                """
            )
            by_namespace = tuple((row[0], row[1]) for row in cursor.fetchall())

            cursor.execute(
                """
                SELECT spec, COUNT(*) as count
                FROM memories
                WHERE spec IS NOT NULL
                GROUP BY spec
                ORDER BY count DESC
                """
            )
            by_spec = tuple((row[0], row[1]) for row in cursor.fetchall())

            cursor.execute(
                """
                SELECT domain, COUNT(*) as count
                FROM memories
                GROUP BY domain
                ORDER BY count DESC
                """
            )
            by_domain = tuple((row[0], row[1]) for row in cursor.fetchall())

            cursor.execute("SELECT value FROM metadata WHERE key = 'last_sync'")
            row = cursor.fetchone()
            last_sync = datetime.fromisoformat(row[0]) if row else None

            index_size = self.db_path.stat().st_size if self.db_path.exists() else 0

            return IndexStats(
                total_memories=total,
                by_namespace=by_namespace,
                by_spec=by_spec,
                by_domain=by_domain,
                last_sync=last_sync,
                index_size_bytes=index_size,
            )

    def count(
        self,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
    ) -> int:
        """Count memories matching criteria."""
        sql = "SELECT COUNT(*) FROM memories WHERE 1=1"
        params: list[object] = []

        if namespace is not None:
            sql += " AND namespace = ?"
            params.append(namespace)

        if spec is not None:
            sql += " AND spec = ?"
            params.append(spec)

        if domain is not None:
            sql += " AND domain = ?"
            params.append(domain)

        with self._cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def update_last_sync(self) -> None:
        """Update the last sync timestamp to now."""
        with self._cursor() as cursor:
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("last_sync", datetime.now(UTC).isoformat()),
            )
            self._conn.commit()  # type: ignore[union-attr]

    # =========================================================================
    # Utility Operations
    # =========================================================================

    def vacuum(self) -> None:
        """Optimize the database by vacuuming and updating statistics."""
        if self._conn is None:
            raise MemoryIndexError(
                "Database not initialized",
                "Call initialize() before performing operations",
            )
        self._conn.execute("VACUUM")
        self._conn.execute("ANALYZE")

    def has_embedding(self, memory_id: str) -> bool:
        """Check if a memory has an embedding."""
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM vec_memories WHERE id = ?",
                (memory_id,),
            )
            return cursor.fetchone() is not None

    def get_memories_without_embeddings(self, limit: int | None = None) -> list[str]:
        """Get IDs of memories that don't have embeddings."""
        sql = """
            SELECT m.id FROM memories m
            LEFT JOIN vec_memories v ON m.id = v.id
            WHERE v.id IS NULL
        """
        params: list[object] = []

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        with self._cursor() as cursor:
            cursor.execute(sql, params)
            return [row[0] for row in cursor.fetchall()]
