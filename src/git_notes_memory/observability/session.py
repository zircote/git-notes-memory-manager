"""Session identification for multi-tenant distinguishability.

Provides unique session identifiers that allow correlating observability
data across multiple concurrent sessions without exposing sensitive
information like full paths or usernames.

Usage:
    from git_notes_memory.observability import (
        get_session_info,
        generate_session_id,
        SessionInfo,
    )

    # Get current session info (singleton)
    session = get_session_info()
    print(f"Session: {session.session_id}")

    # Generate a new unique session ID
    new_id = generate_session_id()
"""

from __future__ import annotations

import hashlib
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any


def _get_hostname() -> str:
    """Get the hostname, falling back to 'unknown' if unavailable."""
    try:
        return socket.gethostname()[:16]  # Truncate for readability
    except Exception:
        return "unknown"


def _hash_value(value: str) -> str:
    """Create a privacy-preserving hash of a value.

    Uses first 8 characters of SHA256 for brevity while
    maintaining sufficient uniqueness.
    """
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def _get_repo_hash() -> str:
    """Get a hash of the current repository path.

    Uses the current working directory as proxy for repo identity.
    Falls back to a random value if CWD is unavailable.
    """
    try:
        cwd = os.getcwd()
        return _hash_value(cwd)
    except Exception:
        return _hash_value(str(uuid.uuid4()))


def _get_user_hash() -> str:
    """Get a hash of the current username.

    Falls back to a random value if username is unavailable.
    """
    try:
        username = os.environ.get("USER") or os.environ.get("USERNAME") or ""
        if username:
            return _hash_value(username)
        return _hash_value(str(uuid.uuid4()))
    except Exception:
        return _hash_value(str(uuid.uuid4()))


@dataclass(frozen=True)
class SessionInfo:
    """Immutable session identification information.

    Contains privacy-preserving identifiers for correlating
    observability data without exposing sensitive paths or usernames.

    Attributes:
        hostname: Truncated hostname (max 16 chars).
        repo_hash: SHA256 hash of repository path (8 chars).
        user_hash: SHA256 hash of username (8 chars).
        timestamp: Session start time as Unix timestamp.
        uuid_suffix: Random UUID suffix for uniqueness (8 chars).
        start_time: Session start as datetime.
    """

    hostname: str
    repo_hash: str
    user_hash: str
    timestamp: float = field(default_factory=time.time)
    uuid_suffix: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    @property
    def start_time(self) -> datetime:
        """Session start time as datetime."""
        return datetime.fromtimestamp(self.timestamp, tz=UTC)

    @property
    def session_id(self) -> str:
        """Generate the full session ID string.

        Format: {hostname}:{repo_hash}:{timestamp_hex}:{uuid_suffix}

        This format is designed to be:
        - Human-readable (hostname first)
        - Sortable by time (timestamp in hex)
        - Unique (uuid suffix)
        - Privacy-preserving (hashes instead of raw values)
        """
        # Use hex timestamp for compactness
        ts_hex = format(int(self.timestamp), "x")
        return f"{self.hostname}:{self.repo_hash}:{ts_hex}:{self.uuid_suffix}"

    @property
    def short_id(self) -> str:
        """Short version of session ID for logging.

        Format: {repo_hash}:{uuid_suffix}
        """
        return f"{self.repo_hash}:{self.uuid_suffix}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "short_id": self.short_id,
            "hostname": self.hostname,
            "repo_hash": self.repo_hash,
            "user_hash": self.user_hash,
            "timestamp": self.timestamp,
            "start_time": self.start_time.isoformat(),
            "uuid_suffix": self.uuid_suffix,
        }


def generate_session_id() -> str:
    """Generate a new unique session ID.

    Creates a fresh SessionInfo and returns its ID string.
    Use this when you need a one-off ID without storing session state.

    Returns:
        Session ID string in format {hostname}:{repo_hash}:{timestamp}:{uuid}
    """
    info = SessionInfo(
        hostname=_get_hostname(),
        repo_hash=_get_repo_hash(),
        user_hash=_get_user_hash(),
    )
    return info.session_id


# Singleton instance
_session_info: SessionInfo | None = None


@lru_cache(maxsize=1)
def get_session_info() -> SessionInfo:
    """Get the global SessionInfo singleton.

    The session is created once per process and cached.
    This provides a consistent session identity throughout
    the lifetime of the application.

    Returns:
        SessionInfo: The global session info instance.
    """
    global _session_info
    if _session_info is None:
        _session_info = SessionInfo(
            hostname=_get_hostname(),
            repo_hash=_get_repo_hash(),
            user_hash=_get_user_hash(),
        )
    return _session_info


def reset_session() -> None:
    """Reset the session singleton.

    Primarily for testing. Clears the cached session so
    a new one will be created on next access.
    """
    global _session_info
    _session_info = None
    get_session_info.cache_clear()
