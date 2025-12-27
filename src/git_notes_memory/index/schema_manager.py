"""Schema management for the memory index database.

ARCH-H-001: Extracted from IndexService to follow Single Responsibility Principle.
This module handles database schema creation, migrations, and version management.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import sqlite_vec

from git_notes_memory.config import EMBEDDING_DIMENSIONS
from git_notes_memory.exceptions import MemoryIndexError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = ["SchemaManager", "SCHEMA_VERSION"]


# =============================================================================
# Constants
# =============================================================================

# Schema version for migrations
SCHEMA_VERSION = 5

# SQL statements for schema creation
_CREATE_MEMORIES_TABLE = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    commit_sha TEXT NOT NULL,
    namespace TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    domain TEXT DEFAULT 'project',
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
    # Single-column indexes for simple lookups
    "CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace)",
    "CREATE INDEX IF NOT EXISTS idx_memories_spec ON memories(spec)",
    "CREATE INDEX IF NOT EXISTS idx_memories_commit ON memories(commit_sha)",
    "CREATE INDEX IF NOT EXISTS idx_memories_timestamp ON memories(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status)",
    "CREATE INDEX IF NOT EXISTS idx_memories_repo_path ON memories(repo_path)",
    "CREATE INDEX IF NOT EXISTS idx_memories_domain ON memories(domain)",
    # Composite indexes for common multi-column queries
    "CREATE INDEX IF NOT EXISTS idx_memories_domain_namespace ON memories(domain, namespace)",
    "CREATE INDEX IF NOT EXISTS idx_memories_spec_namespace ON memories(spec, namespace)",
    "CREATE INDEX IF NOT EXISTS idx_memories_spec_domain ON memories(spec, domain)",
    "CREATE INDEX IF NOT EXISTS idx_memories_namespace_domain ON memories(namespace, domain)",
    "CREATE INDEX IF NOT EXISTS idx_memories_namespace_timestamp ON memories(namespace, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_memories_status_timestamp ON memories(status, timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_memories_ns_spec_ts ON memories(namespace, spec, timestamp DESC)",
]

# Migration SQL for schema version upgrades
_MIGRATIONS = {
    2: [
        # Add repo_path column for per-repository memory isolation
        "ALTER TABLE memories ADD COLUMN repo_path TEXT",
        "CREATE INDEX IF NOT EXISTS idx_memories_repo_path ON memories(repo_path)",
    ],
    3: [
        # Add domain column for multi-domain memory storage (user vs project)
        "ALTER TABLE memories ADD COLUMN domain TEXT DEFAULT 'project'",
        "CREATE INDEX IF NOT EXISTS idx_memories_domain ON memories(domain)",
    ],
    4: [
        # PERF-H-005: Add FTS5 virtual table for fast full-text search
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            id UNINDEXED,
            summary,
            content,
            content='memories',
            content_rowid='rowid'
        )
        """,
        # Populate FTS table with existing data
        """
        INSERT INTO memories_fts(rowid, id, summary, content)
        SELECT rowid, id, summary, content FROM memories
        """,
        # Trigger to keep FTS in sync on INSERT
        """
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, id, summary, content)
            VALUES (new.rowid, new.id, new.summary, new.content);
        END
        """,
        # Trigger to keep FTS in sync on DELETE
        """
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, id, summary, content)
            VALUES ('delete', old.rowid, old.id, old.summary, old.content);
        END
        """,
        # Trigger to keep FTS in sync on UPDATE
        """
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, id, summary, content)
            VALUES ('delete', old.rowid, old.id, old.summary, old.content);
            INSERT INTO memories_fts(rowid, id, summary, content)
            VALUES (new.rowid, new.id, new.summary, new.content);
        END
        """,
    ],
    5: [
        # RET-H-001: Entity extraction and indexing for hybrid search
        # Entities table - stores unique entity references
        """
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            type TEXT NOT NULL,
            canonical_form TEXT,
            first_seen TEXT NOT NULL,
            mention_count INTEGER DEFAULT 1,
            UNIQUE(text, type)
        )
        """,
        # Index for entity lookups
        "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type)",
        "CREATE INDEX IF NOT EXISTS idx_entities_text ON entities(text)",
        "CREATE INDEX IF NOT EXISTS idx_entities_canonical ON entities(canonical_form)",
        # Memory-entity mapping table
        """
        CREATE TABLE IF NOT EXISTS memory_entities (
            memory_id TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            span_start INTEGER,
            span_end INTEGER,
            confidence REAL DEFAULT 1.0,
            PRIMARY KEY (memory_id, entity_id),
            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE,
            FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_memory_entities_memory ON memory_entities(memory_id)",
        "CREATE INDEX IF NOT EXISTS idx_memory_entities_entity ON memory_entities(entity_id)",
        # RET-H-002: Temporal reference extraction and indexing
        """
        CREATE TABLE IF NOT EXISTS temporal_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id TEXT NOT NULL,
            text TEXT NOT NULL,
            start_date TEXT,
            end_date TEXT,
            granularity TEXT,
            span_start INTEGER,
            span_end INTEGER,
            confidence REAL DEFAULT 1.0,
            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_temporal_refs_memory ON temporal_refs(memory_id)",
        "CREATE INDEX IF NOT EXISTS idx_temporal_refs_start ON temporal_refs(start_date)",
        "CREATE INDEX IF NOT EXISTS idx_temporal_refs_end ON temporal_refs(end_date)",
        "CREATE INDEX IF NOT EXISTS idx_temporal_refs_dates ON temporal_refs(start_date, end_date)",
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
# SchemaManager
# =============================================================================


class SchemaManager:
    """Manages database schema creation, migrations, and sqlite-vec extension.

    ARCH-H-001: Extracted from IndexService to separate schema concerns from
    CRUD and search operations.

    Attributes:
        conn: The SQLite database connection.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize SchemaManager with a database connection.

        Args:
            conn: An open SQLite database connection.
        """
        self._conn = conn

    def load_vec_extension(self) -> None:
        """Load the sqlite-vec extension.

        Raises:
            MemoryIndexError: If the extension cannot be loaded.
        """
        try:
            self._conn.enable_load_extension(True)
            sqlite_vec.load(self._conn)
            self._conn.enable_load_extension(False)
        except Exception as e:
            raise MemoryIndexError(
                f"Failed to load sqlite-vec extension: {e}",
                "Install sqlite-vec: pip install sqlite-vec",
            ) from e

    def get_current_version(self) -> int:
        """Get the current schema version from the database.

        Returns:
            Current schema version, or 0 if metadata table doesn't exist.
        """
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
            row = cursor.fetchone()
            return int(row[0]) if row else 1  # Default to v1 for existing DBs
        except sqlite3.OperationalError:
            # Metadata table doesn't exist - new database
            return 0

    def run_migrations(self, from_version: int, to_version: int) -> None:
        """Run schema migrations from one version to another.

        Args:
            from_version: Current schema version.
            to_version: Target schema version.
        """
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

    def create_schema(self) -> None:
        """Create database tables and indices, running migrations if needed.

        Raises:
            MemoryIndexError: If schema creation fails.
        """
        from git_notes_memory.observability.metrics import get_metrics

        cursor = self._conn.cursor()
        try:
            # Check current schema version before creating tables
            current_version = self.get_current_version()

            # Create memories table
            cursor.execute(_CREATE_MEMORIES_TABLE)

            # Create indices (ignore if they already exist)
            for index_sql in _CREATE_INDICES:
                try:
                    cursor.execute(index_sql)
                except sqlite3.OperationalError as e:
                    # Index likely already exists - expected on subsequent inits
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
            # For existing databases (version > 0): migrate from current version
            # For new databases (version 0): run all migrations to create optional tables
            if current_version < SCHEMA_VERSION:
                self.run_migrations(current_version, SCHEMA_VERSION)

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
