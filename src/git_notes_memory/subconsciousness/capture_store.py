"""SQLite storage for implicit captures awaiting review.

This module provides persistent storage for captures identified by the
LLM during transcript analysis. Captures are stored until reviewed by
the user, at which point they are either promoted to permanent memories
or discarded.

The store uses its own SQLite database separate from the main memory index,
keeping the subconsciousness layer cleanly isolated.

Architecture:
    - implicit_captures table: Stores capture metadata and content
    - Indexes for efficient pending/expired queries
    - JSON serialization for nested objects
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from .models import (
    CaptureConfidence,
    ImplicitCapture,
    ImplicitMemory,
    ReviewStatus,
    ThreatDetection,
    ThreatLevel,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "CaptureStore",
    "CaptureStoreError",
    "get_default_capture_store",
]


# =============================================================================
# Exceptions
# =============================================================================


class CaptureStoreError(Exception):
    """Error in capture storage operations."""

    def __init__(self, message: str, recovery_hint: str = "") -> None:
        """Initialize error with message and optional recovery hint."""
        super().__init__(message)
        self.recovery_hint = recovery_hint


# =============================================================================
# Constants
# =============================================================================

# Schema version for this store
CAPTURE_SCHEMA_VERSION = 1

# Default review expiration (7 days)
DEFAULT_EXPIRATION_DAYS = 7

# SQL for table creation
_CREATE_CAPTURES_TABLE = """
CREATE TABLE IF NOT EXISTS implicit_captures (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence_json TEXT NOT NULL,
    confidence_overall REAL NOT NULL DEFAULT 0.0,
    source_hash TEXT NOT NULL,
    source_range_json TEXT,
    rationale TEXT,
    tags_json TEXT,
    threat_detection_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    session_id TEXT,
    reviewed_at TEXT
)
"""

_CREATE_INDICES = [
    "CREATE INDEX IF NOT EXISTS idx_captures_status ON implicit_captures(status)",
    "CREATE INDEX IF NOT EXISTS idx_captures_expires_at ON implicit_captures(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_captures_source_hash ON implicit_captures(source_hash)",
    "CREATE INDEX IF NOT EXISTS idx_captures_namespace ON implicit_captures(namespace)",
    "CREATE INDEX IF NOT EXISTS idx_captures_session ON implicit_captures(session_id)",
    # DB-M-004: Composite index for pending query optimization
    "CREATE INDEX IF NOT EXISTS idx_captures_pending_query ON implicit_captures(status, expires_at)",
    # DB-M-002: Index on denormalized confidence for efficient ORDER BY
    "CREATE INDEX IF NOT EXISTS idx_captures_confidence ON implicit_captures(confidence_overall DESC)",
]

_CREATE_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
"""


# =============================================================================
# CaptureStore
# =============================================================================


class CaptureStore:
    """SQLite storage for implicit captures awaiting review.

    Manages a SQLite database for storing captures identified by LLM
    analysis. Captures remain in the store until reviewed by the user.

    Attributes:
        db_path: Path to the SQLite database file.

    Example:
        >>> store = CaptureStore()
        >>> store.initialize()
        >>> capture_id = store.save(implicit_capture)
        >>> pending = store.get_pending()
        >>> store.approve(capture_id)
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Initialize the CaptureStore.

        Args:
            db_path: Path to the SQLite database. If None, uses a default
                path alongside the main memory index.
        """
        if db_path is None:
            from ..config import get_data_path

            db_path = get_data_path() / "implicit_captures.db"
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._initialized = False
        self._lock = threading.Lock()

    @property
    def is_initialized(self) -> bool:
        """Check if the store has been initialized."""
        return self._initialized and self._conn is not None

    def initialize(self) -> None:
        """Initialize the database and create schema.

        Creates the database file and directory if needed,
        connects to the database, and creates tables.

        Raises:
            CaptureStoreError: If initialization fails.
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

            # Create schema
            self._create_schema()

            self._initialized = True

        except Exception as e:
            # DB-M-003: Close connection before setting to None to prevent leaks
            if self._conn is not None:
                with contextlib.suppress(Exception):
                    self._conn.close()
            self._conn = None
            self._initialized = False
            if isinstance(e, CaptureStoreError):
                raise
            raise CaptureStoreError(
                f"Failed to initialize capture store: {e}",
                "Check disk space and permissions",
            ) from e

    def _create_schema(self) -> None:
        """Create database tables and indices."""
        if self._conn is None:
            raise CaptureStoreError(
                "Database connection not established",
                "Call initialize() first",
            )

        cursor = self._conn.cursor()
        try:
            # Create captures table
            cursor.execute(_CREATE_CAPTURES_TABLE)

            # DB-M-002: Migration - add confidence_overall column if missing
            self._migrate_add_confidence_column(cursor)

            # Create indices
            for index_sql in _CREATE_INDICES:
                with contextlib.suppress(sqlite3.OperationalError):
                    cursor.execute(index_sql)

            # Create metadata table
            cursor.execute(_CREATE_METADATA_TABLE)

            # Set schema version
            cursor.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                ("schema_version", str(CAPTURE_SCHEMA_VERSION)),
            )

            self._conn.commit()
        except Exception as e:
            self._conn.rollback()
            raise CaptureStoreError(
                f"Failed to create schema: {e}",
                "Delete the implicit_captures.db file and retry",
            ) from e

    def _migrate_add_confidence_column(self, cursor: sqlite3.Cursor) -> None:
        """Add confidence_overall column if missing (DB-M-002 migration).

        Also backfills existing rows by extracting from JSON.
        """
        # Check if column exists
        cursor.execute("PRAGMA table_info(implicit_captures)")
        columns = {row[1] for row in cursor.fetchall()}

        if "confidence_overall" not in columns:
            # Add the column
            cursor.execute(
                "ALTER TABLE implicit_captures ADD COLUMN confidence_overall REAL NOT NULL DEFAULT 0.0"
            )
            # Backfill from JSON
            cursor.execute(
                """
                UPDATE implicit_captures
                SET confidence_overall = COALESCE(
                    json_extract(confidence_json, '$.overall'),
                    0.0
                )
                """
            )

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        """Context manager for database cursor with locking.

        Yields:
            A database cursor.

        Raises:
            CaptureStoreError: If the store is not initialized.
        """
        if self._conn is None:
            raise CaptureStoreError(
                "Store not initialized",
                "Call initialize() before performing operations",
            )
        with self._lock:
            cursor = self._conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def save(
        self,
        capture: ImplicitCapture,
    ) -> str:
        """Save an implicit capture to the store.

        Args:
            capture: The capture to save.

        Returns:
            The capture ID.

        Raises:
            CaptureStoreError: If save fails.
        """
        with self._cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO implicit_captures (
                        id, namespace, summary, content, confidence_json,
                        confidence_overall, source_hash, source_range_json,
                        rationale, tags_json, threat_detection_json, status,
                        created_at, expires_at, session_id, reviewed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        capture.id,
                        capture.memory.namespace,
                        capture.memory.summary,
                        capture.memory.content,
                        self._serialize_confidence(capture.memory.confidence),
                        capture.memory.confidence.overall,  # DB-M-002: Denormalized
                        capture.memory.source_hash,
                        (
                            json.dumps(list(capture.memory.source_range))
                            if capture.memory.source_range
                            else None
                        ),
                        capture.memory.rationale,
                        json.dumps(list(capture.memory.tags)),
                        self._serialize_threat_detection(capture.threat_detection),
                        capture.status.value,
                        capture.created_at.isoformat(),
                        capture.expires_at.isoformat(),
                        capture.session_id,
                        (
                            capture.reviewed_at.isoformat()
                            if capture.reviewed_at
                            else None
                        ),
                    ),
                )
                if self._conn:
                    self._conn.commit()
                return capture.id
            except sqlite3.IntegrityError as e:
                if self._conn:
                    self._conn.rollback()
                raise CaptureStoreError(
                    f"Duplicate capture ID: {capture.id}",
                    "Use a unique ID for each capture",
                ) from e
            except Exception as e:
                if self._conn:
                    self._conn.rollback()
                raise CaptureStoreError(f"Failed to save capture: {e}") from e

    def get(self, capture_id: str) -> ImplicitCapture | None:
        """Get a capture by ID.

        Args:
            capture_id: The capture ID.

        Returns:
            The capture, or None if not found.
        """
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM implicit_captures WHERE id = ?",
                (capture_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_capture(row)

    def get_pending(
        self,
        *,
        limit: int = 50,
        include_expired: bool = False,
    ) -> list[ImplicitCapture]:
        """Get pending captures awaiting review.

        Args:
            limit: Maximum captures to return.
            include_expired: If True, includes expired captures.

        Returns:
            List of pending captures, ordered by confidence (desc).
        """
        with self._cursor() as cursor:
            if include_expired:
                # DB-M-002: Use denormalized confidence_overall column for efficient ORDER BY
                cursor.execute(
                    """
                    SELECT * FROM implicit_captures
                    WHERE status = 'pending'
                    ORDER BY confidence_overall DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            else:
                # DB-M-004: Uses composite index (status, expires_at)
                now = datetime.now(UTC).isoformat()
                cursor.execute(
                    """
                    SELECT * FROM implicit_captures
                    WHERE status = 'pending' AND expires_at > ?
                    ORDER BY confidence_overall DESC
                    LIMIT ?
                    """,
                    (now, limit),
                )
            return [self._row_to_capture(row) for row in cursor.fetchall()]

    def get_by_source_hash(self, source_hash: str) -> list[ImplicitCapture]:
        """Get captures by source hash for deduplication.

        Args:
            source_hash: The source hash to search for.

        Returns:
            List of captures with matching source hash.
        """
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM implicit_captures WHERE source_hash = ?",
                (source_hash,),
            )
            return [self._row_to_capture(row) for row in cursor.fetchall()]

    def update_status(
        self,
        capture_id: str,
        status: ReviewStatus,
    ) -> bool:
        """Update the review status of a capture.

        Args:
            capture_id: The capture ID.
            status: The new status.

        Returns:
            True if updated, False if not found.
        """
        reviewed_at = (
            datetime.now(UTC).isoformat() if status != ReviewStatus.PENDING else None
        )
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE implicit_captures
                SET status = ?, reviewed_at = ?
                WHERE id = ?
                """,
                (status.value, reviewed_at, capture_id),
            )
            if self._conn:
                self._conn.commit()
            return cursor.rowcount > 0

    def delete(self, capture_id: str) -> bool:
        """Delete a capture by ID.

        Args:
            capture_id: The capture ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM implicit_captures WHERE id = ?",
                (capture_id,),
            )
            if self._conn:
                self._conn.commit()
            return cursor.rowcount > 0

    def expire_old_captures(self) -> int:
        """Mark expired captures with EXPIRED status.

        Returns:
            Number of captures expired.
        """
        now = datetime.now(UTC).isoformat()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE implicit_captures
                SET status = 'expired', reviewed_at = ?
                WHERE status = 'pending' AND expires_at <= ?
                """,
                (now, now),
            )
            if self._conn:
                self._conn.commit()
            return cursor.rowcount

    def cleanup_reviewed(self, older_than_days: int = 30) -> int:
        """Delete reviewed captures older than threshold.

        Args:
            older_than_days: Delete captures reviewed this many days ago.

        Returns:
            Number of captures deleted.
        """
        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM implicit_captures
                WHERE status IN ('approved', 'rejected', 'expired')
                AND reviewed_at < ?
                """,
                (cutoff,),
            )
            if self._conn:
                self._conn.commit()
            return cursor.rowcount

    def count_by_status(self) -> dict[str, int]:
        """Get count of captures by status.

        Returns:
            Dict mapping status to count.
        """
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT status, COUNT(*) as count
                FROM implicit_captures
                GROUP BY status
                """
            )
            return {row["status"]: row["count"] for row in cursor.fetchall()}

    # =========================================================================
    # Helpers
    # =========================================================================

    def _serialize_confidence(self, conf: CaptureConfidence) -> str:
        """Serialize CaptureConfidence to JSON."""
        return json.dumps(
            {
                "overall": conf.overall,
                "relevance": conf.relevance,
                "actionability": conf.actionability,
                "novelty": conf.novelty,
                "specificity": conf.specificity,
                "coherence": conf.coherence,
            }
        )

    def _deserialize_confidence(self, json_str: str) -> CaptureConfidence:
        """Deserialize CaptureConfidence from JSON."""
        data = json.loads(json_str)
        return CaptureConfidence(
            overall=data["overall"],
            relevance=data.get("relevance", 0.0),
            actionability=data.get("actionability", 0.0),
            novelty=data.get("novelty", 0.0),
            specificity=data.get("specificity", 0.0),
            coherence=data.get("coherence", 0.0),
        )

    def _serialize_threat_detection(self, td: ThreatDetection) -> str:
        """Serialize ThreatDetection to JSON."""
        return json.dumps(
            {
                "level": td.level.value,
                "patterns_found": list(td.patterns_found),
                "explanation": td.explanation,
                "should_block": td.should_block,
            }
        )

    def _deserialize_threat_detection(self, json_str: str) -> ThreatDetection:
        """Deserialize ThreatDetection from JSON."""
        data = json.loads(json_str)
        return ThreatDetection(
            level=ThreatLevel(data["level"]),
            patterns_found=tuple(data.get("patterns_found", [])),
            explanation=data.get("explanation", ""),
            should_block=data.get("should_block", False),
        )

    def _row_to_capture(self, row: sqlite3.Row) -> ImplicitCapture:
        """Convert a database row to an ImplicitCapture."""
        # Parse source_range
        source_range = None
        if row["source_range_json"]:
            sr = json.loads(row["source_range_json"])
            source_range = (sr[0], sr[1])

        # Parse tags
        tags = tuple(json.loads(row["tags_json"])) if row["tags_json"] else ()

        # Build memory
        memory = ImplicitMemory(
            namespace=row["namespace"],
            summary=row["summary"],
            content=row["content"],
            confidence=self._deserialize_confidence(row["confidence_json"]),
            source_hash=row["source_hash"],
            source_range=source_range,
            rationale=row["rationale"] or "",
            tags=tags,
        )

        # Parse reviewed_at
        reviewed_at = None
        if row["reviewed_at"]:
            reviewed_at = datetime.fromisoformat(row["reviewed_at"])

        return ImplicitCapture(
            id=row["id"],
            memory=memory,
            status=ReviewStatus(row["status"]),
            threat_detection=self._deserialize_threat_detection(
                row["threat_detection_json"]
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            session_id=row["session_id"],
            reviewed_at=reviewed_at,
        )


# =============================================================================
# Factory Function
# =============================================================================

_default_store: CaptureStore | None = None


def get_default_capture_store() -> CaptureStore:
    """Get the default CaptureStore singleton.

    Returns a lazily-initialized store using the default database path.

    Returns:
        CaptureStore instance.
    """
    global _default_store

    if _default_store is not None and _default_store.is_initialized:
        return _default_store

    _default_store = CaptureStore()
    _default_store.initialize()
    return _default_store


def reset_default_capture_store() -> None:
    """Reset the default store singleton.

    Useful for testing or reconfiguration.
    """
    global _default_store
    if _default_store is not None:
        _default_store.close()
    _default_store = None


# =============================================================================
# Convenience Functions
# =============================================================================


def create_capture(
    memory: ImplicitMemory,
    threat_detection: ThreatDetection | None = None,
    session_id: str | None = None,
    expiration_days: int = DEFAULT_EXPIRATION_DAYS,
) -> ImplicitCapture:
    """Create a new ImplicitCapture with generated ID and timestamps.

    Args:
        memory: The extracted memory content.
        threat_detection: Optional threat screening result.
        session_id: Optional Claude session ID.
        expiration_days: Days until capture expires.

    Returns:
        New ImplicitCapture ready to save.
    """
    now = datetime.now(UTC)
    return ImplicitCapture(
        id=f"cap-{uuid4().hex[:12]}",
        memory=memory,
        status=ReviewStatus.PENDING,
        threat_detection=threat_detection or ThreatDetection.safe(),
        created_at=now,
        expires_at=now + timedelta(days=expiration_days),
        session_id=session_id,
    )
