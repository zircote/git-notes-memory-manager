"""Allowlist manager for known-safe secrets.

Manages a hash-based allowlist to prevent false positives on known-safe values.
Secrets are never stored - only their SHA-256 hashes.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from git_notes_memory.registry import ServiceRegistry
from git_notes_memory.security.exceptions import AllowlistError
from git_notes_memory.security.models import AllowlistEntry

__all__ = [
    "AllowlistManager",
    "get_default_allowlist_manager",
]

_logger = logging.getLogger(__name__)


# =============================================================================
# AllowlistManager
# =============================================================================


class AllowlistManager:
    """Manages a hash-based allowlist for known-safe secrets.

    Stores SHA-256 hashes of allowlisted values to prevent false positives.
    Supports global and per-namespace allowlists.

    Example usage::

        manager = AllowlistManager(data_dir=Path("/data"))

        # Add a known-safe value
        manager.add(
            value="known-safe-api-key",
            reason="Test API key for development",
            namespace="decisions",
        )

        # Check if a hash is allowed
        if manager.is_allowed("abc123hash...", namespace="decisions"):
            # Skip this detection
            pass

    File structure::

        data_dir/
          allowlist.yaml          # Global allowlist
          allowlist.decisions.yaml  # Namespace-specific
          allowlist.progress.yaml
    """

    def __init__(
        self,
        data_dir: Path | None = None,
    ) -> None:
        """Initialize the AllowlistManager.

        Args:
            data_dir: Directory for storing allowlist files.
                      Defaults to ~/.local/share/memory-plugin/security/
        """
        if data_dir is None:
            data_dir = Path.home() / ".local" / "share" / "memory-plugin" / "security"

        self._data_dir = data_dir
        self._cache: dict[str | None, dict[str, AllowlistEntry]] = {}
        self._dirty: set[str | None] = set()

    @property
    def data_dir(self) -> Path:
        """Get the data directory path."""
        return self._data_dir

    def _get_file_path(self, namespace: str | None = None) -> Path:
        """Get the file path for a namespace's allowlist."""
        if namespace:
            return self._data_dir / f"allowlist.{namespace}.yaml"
        return self._data_dir / "allowlist.yaml"

    def _ensure_data_dir(self) -> None:
        """Ensure the data directory exists."""
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _load_namespace(
        self, namespace: str | None = None
    ) -> dict[str, AllowlistEntry]:
        """Load allowlist entries for a namespace.

        Args:
            namespace: The namespace to load (None for global).

        Returns:
            Dictionary mapping secret hash to AllowlistEntry.
        """
        if namespace in self._cache:
            return self._cache[namespace]

        file_path = self._get_file_path(namespace)
        entries: dict[str, AllowlistEntry] = {}

        if file_path.exists():
            try:
                with file_path.open() as f:
                    data = yaml.safe_load(f)

                if data and isinstance(data, dict) and "entries" in data:
                    for entry_data in data["entries"]:
                        entry = self._parse_entry(entry_data, namespace)
                        if entry and not entry.is_expired:
                            entries[entry.secret_hash] = entry
            except yaml.YAMLError as e:
                # YAML syntax error - file is corrupted, raise to alert user
                _logger.error(
                    "Allowlist file %s has invalid YAML syntax: %s", file_path, e
                )
                raise AllowlistError(
                    f"Allowlist file corrupted: {file_path}",
                    "Check YAML syntax or delete the file to reset",
                ) from e
            except OSError as e:
                # I/O error - log but continue with empty (may be permission issue)
                _logger.error(
                    "Failed to read allowlist %s: %s. "
                    "Secrets filtering will operate without allowlist for namespace '%s'",
                    file_path,
                    e,
                    namespace or "global",
                )
                # Don't cache empty - allow retry on next call
                return entries

        self._cache[namespace] = entries
        return entries

    def _parse_entry(
        self,
        data: dict[str, Any],
        namespace: str | None,
    ) -> AllowlistEntry | None:
        """Parse an allowlist entry from YAML data."""
        try:
            added_at = data.get("added_at")
            if isinstance(added_at, str):
                added_at = datetime.fromisoformat(added_at)

            expires_at = data.get("expires_at")
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)

            return AllowlistEntry(
                secret_hash=data["secret_hash"],
                reason=data.get("reason", ""),
                added_by=data.get("added_by", "unknown"),
                added_at=added_at,
                namespace=namespace,
                expires_at=expires_at,
            )
        except KeyError as e:
            _logger.error(
                "Invalid allowlist entry - missing required field %s: %s", e, data
            )
            return None
        except ValueError as e:
            _logger.error(
                "Invalid allowlist entry - malformed value: %s in %s", e, data
            )
            return None

    def _save_namespace(self, namespace: str | None = None) -> None:
        """Save allowlist entries for a namespace.

        Args:
            namespace: The namespace to save (None for global).
        """
        if namespace not in self._dirty:
            return

        self._ensure_data_dir()
        file_path = self._get_file_path(namespace)

        entries = self._cache.get(namespace, {})

        # Convert entries to YAML-serializable format
        yaml_entries: list[dict[str, Any]] = []
        for entry in entries.values():
            entry_data: dict[str, Any] = {
                "secret_hash": entry.secret_hash,
                "reason": entry.reason,
                "added_by": entry.added_by,
            }
            if entry.added_at:
                entry_data["added_at"] = entry.added_at.isoformat()
            if entry.expires_at:
                entry_data["expires_at"] = entry.expires_at.isoformat()
            yaml_entries.append(entry_data)

        data = {
            "version": "1.0",
            "namespace": namespace,
            "entries": yaml_entries,
        }

        try:
            with file_path.open("w") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            self._dirty.discard(namespace)
        except OSError as e:
            raise AllowlistError(
                f"Failed to save allowlist to {file_path}: {e}",
                "Check file permissions and disk space",
            ) from e

    def hash_value(self, value: str) -> str:
        """Compute the SHA-256 hash of a value.

        Args:
            value: The secret value to hash.

        Returns:
            Hexadecimal SHA-256 hash.
        """
        return hashlib.sha256(value.encode()).hexdigest()

    def is_allowed(
        self,
        secret_hash: str,
        namespace: str | None = None,
    ) -> bool:
        """Check if a secret hash is in the allowlist.

        Checks namespace-specific list first, then falls back to global.

        Args:
            secret_hash: The SHA-256 hash of the secret.
            namespace: Optional namespace to check.

        Returns:
            True if the hash is allowlisted, False otherwise.
        """
        # Check namespace-specific first
        if namespace:
            ns_entries = self._load_namespace(namespace)
            if secret_hash in ns_entries:
                entry = ns_entries[secret_hash]
                return not entry.is_expired

        # Check global
        global_entries = self._load_namespace(None)
        if secret_hash in global_entries:
            entry = global_entries[secret_hash]
            return not entry.is_expired

        return False

    def add(
        self,
        value: str | None = None,
        secret_hash: str | None = None,
        reason: str = "",
        added_by: str = "user",
        namespace: str | None = None,
        expires_at: datetime | None = None,
    ) -> AllowlistEntry:
        """Add a value or hash to the allowlist.

        Args:
            value: The raw secret value to hash and add.
            secret_hash: Pre-computed hash (alternative to value).
            reason: Human-readable reason for allowlisting.
            added_by: Who added this entry.
            namespace: Namespace scope (None for global).
            expires_at: Optional expiration date.

        Returns:
            The created AllowlistEntry.

        Raises:
            AllowlistError: If neither value nor secret_hash is provided.
        """
        if value is None and secret_hash is None:
            raise AllowlistError(
                "Must provide either value or secret_hash",
                "Provide the secret value or its SHA-256 hash",
            )

        if secret_hash is None:
            secret_hash = self.hash_value(value)  # type: ignore[arg-type]

        entry = AllowlistEntry(
            secret_hash=secret_hash,
            reason=reason,
            added_by=added_by,
            added_at=datetime.now(UTC),
            namespace=namespace,
            expires_at=expires_at,
        )

        # Load existing entries and add
        entries = self._load_namespace(namespace)
        entries[secret_hash] = entry
        self._dirty.add(namespace)
        self._save_namespace(namespace)

        _logger.info(
            "Added allowlist entry: hash=%s... namespace=%s",
            secret_hash[:8],
            namespace or "global",
        )

        return entry

    def remove(
        self,
        secret_hash: str,
        namespace: str | None = None,
    ) -> bool:
        """Remove a hash from the allowlist.

        Args:
            secret_hash: The SHA-256 hash to remove.
            namespace: Namespace to remove from (None for global).

        Returns:
            True if the entry was removed, False if not found.
        """
        entries = self._load_namespace(namespace)

        if secret_hash not in entries:
            return False

        del entries[secret_hash]
        self._dirty.add(namespace)
        self._save_namespace(namespace)

        _logger.info(
            "Removed allowlist entry: hash=%s... namespace=%s",
            secret_hash[:8],
            namespace or "global",
        )

        return True

    def list_entries(
        self,
        namespace: str | None = None,
        include_global: bool = True,
    ) -> tuple[AllowlistEntry, ...]:
        """List all allowlist entries.

        Args:
            namespace: Namespace to list (None for global only).
            include_global: If True, include global entries when listing namespace.

        Returns:
            Tuple of AllowlistEntry objects.
        """
        entries: list[AllowlistEntry] = []

        if namespace:
            ns_entries = self._load_namespace(namespace)
            entries.extend(ns_entries.values())

            if include_global:
                global_entries = self._load_namespace(None)
                # Add global entries that aren't overridden by namespace
                for hash_val, entry in global_entries.items():
                    if hash_val not in ns_entries:
                        entries.append(entry)
        else:
            global_entries = self._load_namespace(None)
            entries.extend(global_entries.values())

        # Filter expired entries
        entries = [e for e in entries if not e.is_expired]

        # Sort by added_at descending (newest first)
        entries.sort(
            key=lambda e: e.added_at or datetime.min.replace(tzinfo=UTC), reverse=True
        )

        return tuple(entries)

    def get_entry(
        self,
        secret_hash: str,
        namespace: str | None = None,
    ) -> AllowlistEntry | None:
        """Get a specific allowlist entry.

        Args:
            secret_hash: The SHA-256 hash to look up.
            namespace: Namespace to check (also checks global).

        Returns:
            The AllowlistEntry if found, None otherwise.
        """
        # Check namespace first
        if namespace:
            entries = self._load_namespace(namespace)
            if secret_hash in entries:
                entry = entries[secret_hash]
                if not entry.is_expired:
                    return entry

        # Check global
        entries = self._load_namespace(None)
        if secret_hash in entries:
            entry = entries[secret_hash]
            if not entry.is_expired:
                return entry

        return None

    def clear_cache(self) -> None:
        """Clear the in-memory cache.

        Forces a reload from disk on next access.
        """
        self._cache.clear()
        self._dirty.clear()


# =============================================================================
# Factory
# =============================================================================


def get_default_allowlist_manager(data_dir: Path | None = None) -> AllowlistManager:
    """Get the default AllowlistManager instance.

    Returns a singleton instance via ServiceRegistry with thread-safe
    double-checked locking.

    Args:
        data_dir: Optional override for data directory (only used on first call).

    Returns:
        The shared AllowlistManager instance.
    """
    if data_dir is not None:
        return ServiceRegistry.get(AllowlistManager, data_dir=data_dir)
    return ServiceRegistry.get(AllowlistManager)


def reset_allowlist_manager() -> None:
    """Reset the singleton manager instance.

    Used for testing to ensure fresh instances.
    Note: Prefer ServiceRegistry.reset() to reset all services at once.
    """
    # ServiceRegistry.reset() handles this globally
    # This function is kept for backward compatibility
    pass
