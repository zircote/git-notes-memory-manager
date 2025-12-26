"""Audit logging for secrets filtering operations.

Provides JSON Lines formatted audit logs for compliance with SOC2/GDPR
requirements. All detections and filtering operations are logged with
timestamps and metadata for auditability.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from git_notes_memory.registry import ServiceRegistry
from git_notes_memory.security.models import FilterAction, SecretType

if TYPE_CHECKING:
    from collections.abc import Iterator

    from git_notes_memory.security.models import FilterResult, SecretDetection

__all__ = [
    "AuditEntry",
    "AuditLogger",
    "get_default_audit_logger",
    "reset_audit_logger",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditEntry:
    """A single audit log entry.

    Represents a recorded event in the audit log.

    Attributes:
        timestamp: When the event occurred (ISO format).
        event_type: Type of event (detection, scan, filter, allowlist).
        namespace: Memory namespace where event occurred.
        secret_types: Types of secrets involved.
        action: Action taken (allowed, redacted, blocked, etc.).
        detection_count: Number of secrets detected.
        source: Source of the content (e.g., capture_summary).
        session_id: Unique session identifier for correlation.
        details: Additional event-specific details.
    """

    timestamp: str
    event_type: str
    namespace: str = ""
    secret_types: tuple[str, ...] = field(default_factory=tuple)
    action: str = ""
    detection_count: int = 0
    source: str = ""
    session_id: str = ""
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "namespace": self.namespace,
            "secret_types": list(self.secret_types),
            "action": self.action,
            "detection_count": self.detection_count,
            "source": self.source,
            "session_id": self.session_id,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> AuditEntry:
        """Create from dictionary."""
        # Extract and validate types
        secret_types_raw = data.get("secret_types", [])
        secret_types = (
            tuple(str(s) for s in secret_types_raw)
            if isinstance(secret_types_raw, (list, tuple))
            else ()
        )

        detection_count_raw = data.get("detection_count", 0)
        detection_count = (
            int(detection_count_raw)
            if isinstance(detection_count_raw, (int, float, str))
            else 0
        )

        details_raw = data.get("details", {})
        details = dict(details_raw) if isinstance(details_raw, dict) else {}

        return cls(
            timestamp=str(data.get("timestamp", "")),
            event_type=str(data.get("event_type", "")),
            namespace=str(data.get("namespace", "")),
            secret_types=secret_types,
            action=str(data.get("action", "")),
            detection_count=detection_count,
            source=str(data.get("source", "")),
            session_id=str(data.get("session_id", "")),
            details=details,
        )


class AuditLogger:
    """Thread-safe audit logger for secrets filtering operations.

    Logs all detection and filtering operations to JSON Lines files
    for compliance and debugging purposes.

    Example usage::

        logger = AuditLogger(log_dir=Path("/var/log/memory-plugin"))
        logger.log_filter_result(result, source="capture", namespace="decisions")

        # Query recent entries
        for entry in logger.query(since=yesterday, event_type="detection"):
            print(entry)
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        max_files: int = 5,
    ) -> None:
        """Initialize the audit logger.

        Args:
            log_dir: Directory for log files. Uses default if not provided.
            max_file_size: Maximum size per log file before rotation (bytes).
            max_files: Maximum number of rotated log files to keep.
        """
        if log_dir is None:
            from git_notes_memory.config import get_data_path

            log_dir = get_data_path() / "audit"

        self._log_dir = log_dir
        self._max_file_size = max_file_size
        self._max_files = max_files
        self._write_lock = threading.Lock()
        self._session_id = ""

        # Ensure log directory exists
        self._log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def log_file(self) -> Path:
        """Get the current log file path."""
        return self._log_dir / "secrets-audit.jsonl"

    @property
    def session_id(self) -> str:
        """Get the current session ID."""
        return self._session_id

    def set_session_id(self, session_id: str) -> None:
        """Set the session ID for correlation."""
        self._session_id = session_id

    def log_detection(
        self,
        detection: SecretDetection,
        source: str = "",
        namespace: str = "",
    ) -> None:
        """Log a single secret detection.

        Args:
            detection: The secret detection to log.
            source: Source of the content.
            namespace: Memory namespace.
        """
        entry = AuditEntry(
            timestamp=datetime.now(UTC).isoformat(),
            event_type="detection",
            namespace=namespace,
            secret_types=(detection.secret_type.value,),
            action="detected",
            detection_count=1,
            source=source,
            session_id=self._session_id,
            details={
                "detector": detection.detector,
                "confidence": detection.confidence,
                "line_number": detection.line_number,
            },
        )
        self._write_entry(entry)

    def log_filter_result(
        self,
        result: FilterResult,
        source: str = "",
        namespace: str = "",
    ) -> None:
        """Log a complete filter result.

        Args:
            result: The filter result to log.
            source: Source of the content.
            namespace: Memory namespace.
        """
        if not result.had_secrets:
            return  # Don't log clean content

        secret_types = tuple(d.secret_type.value for d in result.detections)
        entry = AuditEntry(
            timestamp=datetime.now(UTC).isoformat(),
            event_type="filter",
            namespace=namespace,
            secret_types=secret_types,
            action=result.action.value,
            detection_count=result.detection_count,
            source=source,
            session_id=self._session_id,
            details={
                "original_length": result.original_length,
                "filtered_length": result.filtered_length,
            },
        )
        self._write_entry(entry)

    def log_scan(
        self,
        result: FilterResult,
        source: str = "",
        namespace: str = "",
    ) -> None:
        """Log a scan operation (detection without modification).

        Args:
            result: The scan result to log.
            source: Source of the content.
            namespace: Memory namespace.
        """
        secret_types = tuple(d.secret_type.value for d in result.detections)
        entry = AuditEntry(
            timestamp=datetime.now(UTC).isoformat(),
            event_type="scan",
            namespace=namespace,
            secret_types=secret_types,
            action="scanned",
            detection_count=result.detection_count,
            source=source,
            session_id=self._session_id,
            details={
                "had_secrets": result.had_secrets,
            },
        )
        self._write_entry(entry)

    def log_allowlist_change(
        self,
        action: str,
        secret_hash: str,
        reason: str = "",
        namespace: str = "",
        added_by: str = "",
    ) -> None:
        """Log an allowlist modification.

        Args:
            action: The action (add, remove).
            secret_hash: Hash of the secret (never log raw secrets!).
            reason: Reason for the change.
            namespace: Namespace scope (if any).
            added_by: Who made the change.
        """
        entry = AuditEntry(
            timestamp=datetime.now(UTC).isoformat(),
            event_type="allowlist",
            namespace=namespace,
            action=action,
            session_id=self._session_id,
            details={
                "secret_hash": secret_hash[:16] + "...",  # Truncate for privacy
                "reason": reason,
                "added_by": added_by,
            },
        )
        self._write_entry(entry)

    def _write_entry(self, entry: AuditEntry) -> None:
        """Write an entry to the log file (thread-safe).

        Args:
            entry: The audit entry to write.
        """
        with self._write_lock:
            # Check for rotation
            if self._should_rotate():
                self._rotate_logs()

            # Append to log file
            try:
                with self.log_file.open("a") as f:
                    json.dump(entry.to_dict(), f, default=str)
                    f.write("\n")
            except OSError as e:
                # Audit log failures are serious for compliance - log at ERROR
                logger.error(
                    "AUDIT LOG FAILURE: Failed to write entry to %s: %s. "
                    "Event type=%s, namespace=%s. This may indicate disk issues.",
                    self.log_file,
                    e,
                    entry.event_type,
                    entry.namespace,
                )

    def _should_rotate(self) -> bool:
        """Check if log rotation is needed."""
        if not self.log_file.exists():
            return False
        return self.log_file.stat().st_size >= self._max_file_size

    def _rotate_logs(self) -> None:
        """Rotate log files."""
        try:
            # Remove oldest if at limit
            for i in range(self._max_files - 1, 0, -1):
                old_file = self._log_dir / f"secrets-audit.{i}.jsonl"
                new_file = self._log_dir / f"secrets-audit.{i + 1}.jsonl"
                if old_file.exists():
                    if i + 1 >= self._max_files:
                        old_file.unlink()
                    else:
                        old_file.rename(new_file)

            # Rotate current to .1
            if self.log_file.exists():
                self.log_file.rename(self._log_dir / "secrets-audit.1.jsonl")

            logger.debug("Rotated audit logs")
        except OSError as e:
            # Rotation failure could lead to unbounded log growth
            logger.error(
                "AUDIT LOG ROTATION FAILURE: %s. "
                "Log file may grow unbounded. Check disk space and permissions.",
                e,
            )

    def query(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        event_type: str | None = None,
        namespace: str | None = None,
        secret_type: SecretType | None = None,
        action: FilterAction | None = None,
        limit: int = 100,
    ) -> Iterator[AuditEntry]:
        """Query audit log entries.

        Args:
            since: Only entries after this time.
            until: Only entries before this time.
            event_type: Filter by event type.
            namespace: Filter by namespace.
            secret_type: Filter by secret type.
            action: Filter by action taken.
            limit: Maximum entries to return.

        Yields:
            Matching AuditEntry objects.
        """
        count = 0

        # Read from all log files (current + rotated)
        log_files = [self.log_file]
        for i in range(1, self._max_files + 1):
            rotated = self._log_dir / f"secrets-audit.{i}.jsonl"
            if rotated.exists():
                log_files.append(rotated)

        for log_file in log_files:
            if not log_file.exists():
                continue

            try:
                with log_file.open() as f:
                    for line in f:
                        if count >= limit:
                            return

                        line = line.strip()
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                            entry = AuditEntry.from_dict(data)
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.debug(
                                "Skipping malformed audit entry in %s: %s", log_file, e
                            )
                            continue

                        # Apply filters
                        if not self._matches_filters(
                            entry,
                            since,
                            until,
                            event_type,
                            namespace,
                            secret_type,
                            action,
                        ):
                            continue

                        yield entry
                        count += 1

            except OSError as e:
                logger.warning("Failed to read audit log %s: %s", log_file, e)

    def _matches_filters(
        self,
        entry: AuditEntry,
        since: datetime | None,
        until: datetime | None,
        event_type: str | None,
        namespace: str | None,
        secret_type: SecretType | None,
        action: FilterAction | None,
    ) -> bool:
        """Check if an entry matches the query filters."""
        # Parse timestamp
        try:
            ts_str = entry.timestamp
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            entry_time = datetime.fromisoformat(ts_str)
        except ValueError:
            return False

        if since and entry_time < since:
            return False
        if until and entry_time > until:
            return False
        if event_type and entry.event_type != event_type:
            return False
        if namespace and entry.namespace != namespace:
            return False
        if secret_type and secret_type.value not in entry.secret_types:
            return False
        return not (action and entry.action != action.value)

    def get_stats(
        self,
        since: datetime | None = None,
    ) -> dict[str, object]:
        """Get summary statistics from the audit log.

        Args:
            since: Only count entries after this time.

        Returns:
            Dictionary with counts by type, namespace, action.
        """
        stats: dict[str, int] = {
            "total_events": 0,
            "detections": 0,
            "filters": 0,
            "scans": 0,
            "allowlist_changes": 0,
        }
        by_namespace: dict[str, int] = {}
        by_action: dict[str, int] = {}
        by_type: dict[str, int] = {}

        for entry in self.query(since=since, limit=10000):
            stats["total_events"] += 1
            stats[entry.event_type + "s"] = stats.get(entry.event_type + "s", 0) + 1

            if entry.namespace:
                by_namespace[entry.namespace] = by_namespace.get(entry.namespace, 0) + 1
            if entry.action:
                by_action[entry.action] = by_action.get(entry.action, 0) + 1
            for st in entry.secret_types:
                by_type[st] = by_type.get(st, 0) + 1

        return {
            **stats,
            "by_namespace": by_namespace,
            "by_action": by_action,
            "by_type": by_type,
        }


def get_default_audit_logger(
    log_dir: Path | None = None,
) -> AuditLogger:
    """Get the default audit logger instance.

    Returns a singleton instance via ServiceRegistry with thread-safe
    double-checked locking.

    Args:
        log_dir: Optional log directory override (only used on first call).

    Returns:
        The shared AuditLogger instance.
    """
    if log_dir is not None:
        return ServiceRegistry.get(AuditLogger, log_dir=log_dir)
    return ServiceRegistry.get(AuditLogger)


def reset_audit_logger() -> None:
    """Reset the singleton audit logger instance.

    Used for testing to ensure fresh instances.
    Note: Prefer ServiceRegistry.reset() to reset all services at once.
    """
    # ServiceRegistry.reset() handles this globally
    # This function is kept for backward compatibility
    pass
