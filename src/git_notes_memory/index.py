"""SQLite + sqlite-vec index service for semantic memory search.

This module provides the IndexService class for managing a SQLite database
with vector search capabilities using the sqlite-vec extension. It handles:

- Database initialization and schema management
- Memory CRUD operations (insert, get, update, delete)
- Vector similarity search (KNN queries)
- Batch operations for efficiency
- Statistics and health monitoring

The index stores memory metadata and embeddings, enabling fast semantic search
across all captured memories. The actual memory content is stored in git notes,
with the index providing a queryable view.

Architecture:
    - memories table: Stores memory metadata (id, commit_sha, namespace, etc.)
    - vec_memories virtual table: Stores embeddings for KNN search
    - Both tables are kept in sync via insert/update/delete operations
"""

from __future__ import annotations

import logging
import sqlite3
import struct
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import sqlite_vec

from git_notes_memory.config import EMBEDDING_DIMENSIONS, get_index_path
from git_notes_memory.exceptions import MemoryIndexError
from git_notes_memory.observability.decorators import measure_duration
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.tracing import trace_operation

logger = logging.getLogger(__name__)


# PERF-007: Cache compiled struct format for embedding serialization
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


if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from git_notes_memory.models import IndexStats, Memory

__all__ = [
    "IndexService",
]


# =============================================================================
# Constants
# =============================================================================

# Schema version for migrations
SCHEMA_VERSION = 2

# SQL statements for schema creation
_CREATE_MEMORIES_TABLE = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    namespace TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    repo_path TEXT,
    spec TEXT,
    phase TEXT,
    tags TEXT,
    status TEXT DEFAULT 'active',
    relates_to TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

_CREATE_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace)",
    "CREATE INDEX IF NOT EXISTS idx_memories_spec ON memories(spec)",
    "CREATE INDEX IF NOT EXISTS idx_memories_commit ON memories(commit_sha)",
    "CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status)",
    "CREATE INDEX IF NOT EXISTS idx_memories_repo_path ON memories(repo_path)",
    # HIGH-004: Composite index for efficient range queries within namespace
    "CREATE INDEX IF NOT EXISTS idx_memories_namespace_timestamp ON memories(namespace, timestamp DESC)",
]

# Migration SQL for schema version upgrades
_MIGRATIONS = {
    2: [
        # Add repo_path column for per-repository memory isolation
        "ALTER TABLE memories ADD COLUMN repo_path TEXT",
        "CREATE INDEX IF NOT EXISTS idx_memories_repo_path ON memories(repo_path)",
    ],
}

_CREATE_VEC_TABLE = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0(
    id TEXT PRIMARY KEY,
    embedding FLOAT[{EMBEDDING_DIMENSIONS}]
)
"""

_CREATE_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


# =============================================================================
# IndexService
# =============================================================================


class IndexService:
    """SQLite + sqlite-vec database management for memory search.

    Manages a SQLite database with vector search capabilities for semantic
    memory retrieval. The service handles:

    - Database initialization and schema management
    - Memory CRUD operations
    - Vector similarity search (KNN queries)
    - Batch operations for efficiency
    - Statistics and health monitoring

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
        # HIGH-011: Thread lock for concurrent access safety
        self._lock = threading.Lock()

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

            # MED-005: Enable WAL mode for better concurrent access
            # WAL allows readers and writers to operate concurrently
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")

            # Load sqlite-vec extension
            self._load_vec_extension()

            # Create schema
            self._create_schema()

            self._initialized = True

        except Exception as e:
            self._conn = None
            self._initialized = False
            if isinstance(e, MemoryIndexError):
                raise
            raise MemoryIndexError(
                f"Failed to initialize index database: {e}",
                "Check disk space and permissions, then retry",
            ) from e

    def _load_vec_extension(self) -> None:
        """Load the sqlite-vec extension.

        Raises:
            MemoryIndexError: If the extension cannot be loaded.
        """
        if self._conn is None:
            raise MemoryIndexError(
                "Database connection not established",
                "Call initialize() first",
            )

        try:
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
        except Exception as e:
            raise MemoryIndexError(
                f"Failed to load sqlite-vec extension: {e}",
                "Install sqlite-vec: pip install sqlite-vec",
            ) from e

    def _get_current_schema_version(self) -> int:
        """Get the current schema version from the database.

        Returns:
            Current schema version, or 0 if metadata table doesn't exist.
        """
        if self._conn is None:
            return 0

        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
            row = cursor.fetchone()
            return int(row[0]) if row else 1  # Default to v1 for existing DBs
        except sqlite3.OperationalError:
            # Metadata table doesn't exist - new database
            return 0

    def _run_migrations(self, from_version: int, to_version: int) -> None:
        """Run schema migrations from one version to another.

        Args:
            from_version: Current schema version.
            to_version: Target schema version.
        """
        if self._conn is None:
            return

        cursor = self._conn.cursor()
        for version in range(from_version + 1, to_version + 1):
            if version in _MIGRATIONS:
                for sql in _MIGRATIONS[version]:
                    try:
                        cursor.execute(sql)
                    except sqlite3.OperationalError as e:
                        # Column may already exist from a partial migration
                        if "duplicate column" not in str(e).lower():
                            raise
        self._conn.commit()

    def _create_schema(self) -> None:
        """Create database tables and indices, running migrations if needed."""
        if self._conn is None:
            raise MemoryIndexError(
                "Database connection not established",
                "Call initialize() first",
            )

        cursor = self._conn.cursor()
        try:
            # Check current schema version before creating tables
            current_version = self._get_current_schema_version()

            # Create memories table
            cursor.execute(_CREATE_MEMORIES_TABLE)

            # Create indices (ignore if they already exist)
            for index_sql in _CREATE_INDICES:
                try:
                    cursor.execute(index_sql)
                except sqlite3.OperationalError as e:
                    # Index likely already exists - this is expected on subsequent inits
                    logger.debug("Index creation skipped (already exists): %s", e)
                    metrics = get_metrics()
                    metrics.increment(
                        "silent_failures_total",
                        labels={"location": "index.create_index_skipped"},
                    )

            # Create vector table
            cursor.execute(_CREATE_VEC_TABLE)

            # Create metadata table
            cursor.execute(_CREATE_METADATA_TABLE)

            # Run migrations if needed
            if 0 < current_version < SCHEMA_VERSION:
                self._run_migrations(current_version, SCHEMA_VERSION)

            # Set schema version
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

            # Set last sync to now (only if not already set)
            cursor.execute(
                "INSERT OR IGNORE INTO metadata (key, value) VALUES (?, ?)",
                ("last_sync", datetime.now(UTC).isoformat()),
            )

            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise MemoryIndexError(
                f"Failed to create database schema: {e}",
                "Delete the index.db file and retry to recreate",
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
                # Insert into memories table
                cursor.execute(
                    """
                    INSERT INTO memories (
                        id, commit_sha, namespace, summary, content,
                        timestamp, repo_path, spec, phase, tags, status,
                        relates_to, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        memory.id,
                        memory.commit_sha,
                        memory.namespace,
                        memory.summary,
                        memory.content,
                        memory.timestamp.isoformat(),
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

                # Insert embedding if provided
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
                        # CRIT-002: Include repo_path for per-repository isolation
                        cursor.execute(
                            """
                            INSERT INTO memories (
                                id, commit_sha, namespace, summary, content,
                                timestamp, repo_path, spec, phase, tags, status,
                                relates_to, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                memory.id,
                                memory.commit_sha,
                                memory.namespace,
                                memory.summary,
                                memory.content,
                                memory.timestamp.isoformat(),
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
        """Insert an embedding into the vector table.

        Args:
            cursor: Active database cursor.
            memory_id: ID of the memory this embedding belongs to.
            embedding: The embedding vector.
        """
        # PERF-007: Use cached struct format for embedding packing
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
                f"SELECT * FROM memories WHERE id IN ({placeholders})",  # nosec B608
                memory_ids,
            )
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_spec(
        self,
        spec: str,
        namespace: str | None = None,
        limit: int | None = None,
    ) -> list[Memory]:
        """Get all memories for a specification.

        Args:
            spec: The specification slug to filter by.
            namespace: Optional namespace to filter by.
            limit: Optional maximum number of results.

        Returns:
            List of Memory objects matching the criteria.
        """
        query = "SELECT * FROM memories WHERE spec = ?"
        params: list[object] = [spec]

        if namespace is not None:
            query += " AND namespace = ?"
            params.append(namespace)

        query += " ORDER BY timestamp DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_by_commit(self, commit_sha: str) -> list[Memory]:
        """Get all memories attached to a commit.

        Args:
            commit_sha: The commit SHA to filter by.

        Returns:
            List of Memory objects attached to the commit.
        """
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
    ) -> list[Memory]:
        """Get all memories in a namespace.

        Args:
            namespace: The namespace to filter by.
            spec: Optional specification to filter by.
            limit: Optional maximum number of results.

        Returns:
            List of Memory objects matching the criteria.
        """
        query = "SELECT * FROM memories WHERE namespace = ?"
        params: list[object] = [namespace]

        if spec is not None:
            query += " AND spec = ?"
            params.append(spec)

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
    ) -> list[Memory]:
        """Get the most recent memories.

        Args:
            limit: Maximum number of results.
            namespace: Optional namespace filter.
            spec: Optional specification filter.

        Returns:
            List of Memory objects ordered by timestamp descending.
        """
        query = "SELECT * FROM memories WHERE 1=1"
        params: list[object] = []

        if namespace is not None:
            query += " AND namespace = ?"
            params.append(namespace)

        if spec is not None:
            query += " AND spec = ?"
            params.append(spec)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._cursor() as cursor:
            cursor.execute(query, params)
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    def get_all_ids(self) -> list[str]:
        """Get all memory IDs in the index.

        Returns:
            List of all memory IDs.
        """
        with self._cursor() as cursor:
            cursor.execute("SELECT id FROM memories")
            return [row[0] for row in cursor.fetchall()]

    def get_all_memories(
        self,
        namespace: str | None = None,
    ) -> list[Memory]:
        """Get all memories in the index.

        Args:
            namespace: Optional namespace filter.

        Returns:
            List of all Memory objects.
        """
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
        """Check if a memory exists in the index.

        Args:
            memory_id: The memory ID to check.

        Returns:
            True if the memory exists.
        """
        with self._cursor() as cursor:
            cursor.execute("SELECT 1 FROM memories WHERE id = ?", (memory_id,))
            return cursor.fetchone() is not None

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        """Convert a database row to a Memory object.

        Args:
            row: A sqlite3.Row from the memories table.

        Returns:
            A Memory object.
        """
        from git_notes_memory.models import Memory

        # Parse tags
        tags_str = row["tags"]
        tags = tuple(tags_str.split(",")) if tags_str else ()

        # Parse relates_to
        relates_str = row["relates_to"]
        relates_to = tuple(relates_str.split(",")) if relates_str else ()

        # Parse timestamp
        timestamp = datetime.fromisoformat(row["timestamp"])

        return Memory(
            id=row["id"],
            commit_sha=row["commit_sha"],
            namespace=row["namespace"],
            summary=row["summary"],
            content=row["content"],
            timestamp=timestamp,
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
        """Update an existing memory.

        Args:
            memory: The Memory object with updated fields.
            embedding: Optional new embedding vector.

        Returns:
            True if the update was successful, False if memory not found.

        Raises:
            MemoryIndexError: If the update fails.
        """
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

                # Update embedding if provided
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
        """Update an embedding in the vector table.

        Args:
            cursor: Active database cursor.
            memory_id: ID of the memory this embedding belongs to.
            embedding: The new embedding vector.
        """
        # PERF-007: Use cached struct format for embedding packing
        blob = _get_struct_format(len(embedding)).pack(*embedding)

        # Delete existing and insert new (sqlite-vec doesn't support UPDATE well)
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
        """Update only the embedding for a memory.

        Args:
            memory_id: ID of the memory to update.
            embedding: The new embedding vector.

        Returns:
            True if successful, False if memory not found.
        """
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
        """Delete a memory from the index.

        Args:
            memory_id: ID of the memory to delete.

        Returns:
            True if deleted, False if not found.
        """
        with self._cursor() as cursor:
            try:
                # Delete from memories table
                cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                deleted = cursor.rowcount > 0

                # Delete from vec_memories table
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
        """Delete multiple memories.

        Args:
            memory_ids: List of memory IDs to delete.

        Returns:
            Number of memories deleted.
        """
        if not memory_ids:
            return 0

        placeholders = ",".join("?" * len(memory_ids))

        with self._cursor() as cursor:
            try:
                # Delete from memories table
                # placeholders is only "?" chars - safe parameterized query
                cursor.execute(
                    f"DELETE FROM memories WHERE id IN ({placeholders})",  # nosec B608
                    memory_ids,
                )
                deleted = cursor.rowcount

                # Delete from vec_memories table
                # placeholders is only "?" chars - safe parameterized query
                cursor.execute(
                    f"DELETE FROM vec_memories WHERE id IN ({placeholders})",  # nosec B608
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
        """Delete all memories from the index.

        Returns:
            Number of memories deleted.
        """
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
    # Search Operations
    # =========================================================================

    @measure_duration("index_search_vector")
    def search_vector(
        self,
        query_embedding: Sequence[float],
        k: int = 10,
        namespace: str | None = None,
        spec: str | None = None,
    ) -> list[tuple[Memory, float]]:
        """Search for similar memories using vector similarity.

        Uses KNN search via sqlite-vec to find the k nearest neighbors
        to the query embedding.

        Args:
            query_embedding: The query embedding vector.
            k: Number of nearest neighbors to return.
            namespace: Optional namespace filter.
            spec: Optional specification filter.

        Returns:
            List of (Memory, distance) tuples sorted by distance ascending.
            Lower distance means more similar.
        """
        metrics = get_metrics()

        with trace_operation("index.search_vector", labels={"k": str(k)}):
            # PERF-007: Use cached struct format for embedding packing
            blob = _get_struct_format(len(query_embedding)).pack(*query_embedding)

            with self._cursor() as cursor:
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

    def search_text(
        self,
        query: str,
        limit: int = 10,
        namespace: str | None = None,
        spec: str | None = None,
    ) -> list[Memory]:
        """Search memories by text in summary and content.

        Performs a simple LIKE-based text search. For semantic search,
        use search_vector() with an embedding.

        Args:
            query: Text to search for.
            limit: Maximum number of results.
            namespace: Optional namespace filter.
            spec: Optional specification filter.

        Returns:
            List of matching Memory objects.
        """
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

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._cursor() as cursor:
            cursor.execute(sql, params)
            return [self._row_to_memory(row) for row in cursor.fetchall()]

    # =========================================================================
    # Statistics Operations
    # =========================================================================

    def get_stats(self) -> IndexStats:
        """Get statistics about the index.

        Returns:
            IndexStats with counts and metadata.
        """
        from git_notes_memory.models import IndexStats

        with self._cursor() as cursor:
            # Total count
            cursor.execute("SELECT COUNT(*) FROM memories")
            total = cursor.fetchone()[0]

            # Count by namespace
            cursor.execute(
                """
                SELECT namespace, COUNT(*) as count
                FROM memories
                GROUP BY namespace
                ORDER BY count DESC
                """
            )
            by_namespace = tuple((row[0], row[1]) for row in cursor.fetchall())

            # Count by spec
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

            # Last sync time
            cursor.execute("SELECT value FROM metadata WHERE key = 'last_sync'")
            row = cursor.fetchone()
            last_sync = datetime.fromisoformat(row[0]) if row else None

            # Database size
            index_size = self.db_path.stat().st_size if self.db_path.exists() else 0

            return IndexStats(
                total_memories=total,
                by_namespace=by_namespace,
                by_spec=by_spec,
                last_sync=last_sync,
                index_size_bytes=index_size,
            )

    def count(
        self,
        namespace: str | None = None,
        spec: str | None = None,
    ) -> int:
        """Count memories matching criteria.

        Args:
            namespace: Optional namespace filter.
            spec: Optional specification filter.

        Returns:
            Number of matching memories.
        """
        sql = "SELECT COUNT(*) FROM memories WHERE 1=1"
        params: list[object] = []

        if namespace is not None:
            sql += " AND namespace = ?"
            params.append(namespace)

        if spec is not None:
            sql += " AND spec = ?"
            params.append(spec)

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
        """Optimize the database by vacuuming."""
        if self._conn is None:
            raise MemoryIndexError(
                "Database not initialized",
                "Call initialize() before performing operations",
            )
        self._conn.execute("VACUUM")

    def has_embedding(self, memory_id: str) -> bool:
        """Check if a memory has an embedding.

        Args:
            memory_id: The memory ID to check.

        Returns:
            True if the memory has an embedding in vec_memories.
        """
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM vec_memories WHERE id = ?",
                (memory_id,),
            )
            return cursor.fetchone() is not None

    def get_memories_without_embeddings(self, limit: int | None = None) -> list[str]:
        """Get IDs of memories that don't have embeddings.

        Args:
            limit: Optional maximum number to return.

        Returns:
            List of memory IDs without embeddings.
        """
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
