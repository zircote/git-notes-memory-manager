"""Tests for the AllowlistManager."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from git_notes_memory.security.allowlist import (
    AllowlistManager,
    reset_allowlist_manager,
)
from git_notes_memory.security.exceptions import AllowlistError


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton manager before each test."""
    reset_allowlist_manager()
    yield
    reset_allowlist_manager()


@pytest.fixture
def manager(tmp_path: Path) -> AllowlistManager:
    """Create a fresh AllowlistManager with temp directory."""
    return AllowlistManager(data_dir=tmp_path)


class TestHashValue:
    """Tests for hash_value method."""

    def test_hash_consistent(self, manager: AllowlistManager):
        """Test that hashing is consistent."""
        value = "test-secret-value"
        hash1 = manager.hash_value(value)
        hash2 = manager.hash_value(value)

        assert hash1 == hash2

    def test_hash_is_sha256(self, manager: AllowlistManager):
        """Test that hash is SHA-256 (64 hex chars)."""
        value = "test"
        hash_val = manager.hash_value(value)

        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)

    def test_different_values_different_hashes(self, manager: AllowlistManager):
        """Test that different values produce different hashes."""
        hash1 = manager.hash_value("secret1")
        hash2 = manager.hash_value("secret2")

        assert hash1 != hash2


class TestAddAndIsAllowed:
    """Tests for add and is_allowed methods."""

    def test_add_by_value(self, manager: AllowlistManager):
        """Test adding by value."""
        entry = manager.add(value="test-secret", reason="Test entry")

        assert entry.secret_hash == manager.hash_value("test-secret")
        assert entry.reason == "Test entry"
        assert entry.added_by == "user"

    def test_add_by_hash(self, manager: AllowlistManager):
        """Test adding by pre-computed hash."""
        hash_val = manager.hash_value("test-secret")
        entry = manager.add(secret_hash=hash_val, reason="Test entry")

        assert entry.secret_hash == hash_val

    def test_add_requires_value_or_hash(self, manager: AllowlistManager):
        """Test that add requires either value or hash."""
        with pytest.raises(AllowlistError):
            manager.add(reason="No value or hash")

    def test_is_allowed_after_add(self, manager: AllowlistManager):
        """Test that is_allowed returns True after add."""
        entry = manager.add(value="allowed-secret")

        assert manager.is_allowed(entry.secret_hash)

    def test_is_allowed_not_in_list(self, manager: AllowlistManager):
        """Test that is_allowed returns False for unknown hash."""
        assert not manager.is_allowed("unknown-hash-value")

    def test_is_allowed_with_namespace(self, manager: AllowlistManager):
        """Test namespace-scoped allowlist."""
        entry = manager.add(value="secret", namespace="decisions")

        # Should be allowed in the namespace
        assert manager.is_allowed(entry.secret_hash, namespace="decisions")

        # Should NOT be allowed globally or in other namespace
        assert not manager.is_allowed(entry.secret_hash, namespace=None)
        assert not manager.is_allowed(entry.secret_hash, namespace="progress")

    def test_global_applies_to_namespace(self, manager: AllowlistManager):
        """Test that global allowlist applies to all namespaces."""
        entry = manager.add(value="global-secret", namespace=None)

        # Should be allowed in any namespace check
        assert manager.is_allowed(entry.secret_hash, namespace=None)
        assert manager.is_allowed(entry.secret_hash, namespace="decisions")
        assert manager.is_allowed(entry.secret_hash, namespace="progress")


class TestRemove:
    """Tests for remove method."""

    def test_remove_existing(self, manager: AllowlistManager):
        """Test removing an existing entry."""
        entry = manager.add(value="to-remove")

        result = manager.remove(entry.secret_hash)

        assert result is True
        assert not manager.is_allowed(entry.secret_hash)

    def test_remove_nonexistent(self, manager: AllowlistManager):
        """Test removing a non-existent entry."""
        result = manager.remove("nonexistent-hash")

        assert result is False

    def test_remove_from_namespace(self, manager: AllowlistManager):
        """Test removing from specific namespace."""
        entry = manager.add(value="ns-secret", namespace="decisions")

        result = manager.remove(entry.secret_hash, namespace="decisions")

        assert result is True
        assert not manager.is_allowed(entry.secret_hash, namespace="decisions")


class TestListEntries:
    """Tests for list_entries method."""

    def test_list_empty(self, manager: AllowlistManager):
        """Test listing empty allowlist."""
        entries = manager.list_entries()

        assert entries == ()

    def test_list_global(self, manager: AllowlistManager):
        """Test listing global entries."""
        manager.add(value="secret1", reason="First")
        manager.add(value="secret2", reason="Second")

        entries = manager.list_entries()

        assert len(entries) == 2

    def test_list_namespace(self, manager: AllowlistManager):
        """Test listing namespace-specific entries."""
        manager.add(value="ns-secret", namespace="decisions")
        manager.add(value="global-secret", namespace=None)

        # With include_global=True (default)
        entries = manager.list_entries(namespace="decisions")
        assert len(entries) == 2

        # With include_global=False
        entries = manager.list_entries(namespace="decisions", include_global=False)
        assert len(entries) == 1

    def test_list_sorted_newest_first(self, manager: AllowlistManager):
        """Test that entries are sorted newest first."""
        manager.add(value="first")
        manager.add(value="second")
        manager.add(value="third")

        entries = manager.list_entries()

        # Most recent should be first
        assert entries[0].secret_hash == manager.hash_value("third")
        assert entries[2].secret_hash == manager.hash_value("first")


class TestExpiration:
    """Tests for expiration handling."""

    def test_expired_entry_not_allowed(self, manager: AllowlistManager):
        """Test that expired entries are not allowed."""
        past = datetime.now(UTC) - timedelta(days=1)
        entry = manager.add(
            value="expired-secret",
            expires_at=past,
        )

        assert not manager.is_allowed(entry.secret_hash)

    def test_future_expiration_allowed(self, manager: AllowlistManager):
        """Test that future expiration is still allowed."""
        future = datetime.now(UTC) + timedelta(days=1)
        entry = manager.add(
            value="valid-secret",
            expires_at=future,
        )

        assert manager.is_allowed(entry.secret_hash)

    def test_expired_not_in_list(self, manager: AllowlistManager):
        """Test that expired entries are filtered from list."""
        past = datetime.now(UTC) - timedelta(days=1)
        manager.add(value="expired", expires_at=past)
        manager.add(value="valid")

        entries = manager.list_entries()

        assert len(entries) == 1


class TestPersistence:
    """Tests for YAML file persistence."""

    def test_persists_to_file(self, tmp_path: Path):
        """Test that entries are persisted to file."""
        manager = AllowlistManager(data_dir=tmp_path)
        manager.add(value="persistent-secret", reason="Test")

        # File should exist
        file_path = tmp_path / "allowlist.yaml"
        assert file_path.exists()

        # Content should be valid YAML
        import yaml

        with file_path.open() as f:
            data = yaml.safe_load(f)

        assert data["version"] == "1.0"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["reason"] == "Test"

    def test_namespace_separate_file(self, tmp_path: Path):
        """Test that namespace uses separate file."""
        manager = AllowlistManager(data_dir=tmp_path)
        manager.add(value="ns-secret", namespace="decisions")

        ns_file = tmp_path / "allowlist.decisions.yaml"
        assert ns_file.exists()

        global_file = tmp_path / "allowlist.yaml"
        assert not global_file.exists()

    def test_loads_on_new_instance(self, tmp_path: Path):
        """Test that entries are loaded from file on new instance."""
        manager1 = AllowlistManager(data_dir=tmp_path)
        entry = manager1.add(value="persistent", reason="Survive reload")

        # Create new instance
        manager2 = AllowlistManager(data_dir=tmp_path)

        assert manager2.is_allowed(entry.secret_hash)

    def test_handles_missing_file(self, tmp_path: Path):
        """Test graceful handling of missing file."""
        manager = AllowlistManager(data_dir=tmp_path)

        # Should not raise
        assert manager.list_entries() == ()
        assert not manager.is_allowed("any-hash")


class TestGetEntry:
    """Tests for get_entry method."""

    def test_get_existing(self, manager: AllowlistManager):
        """Test getting an existing entry."""
        added = manager.add(value="secret", reason="Test")

        entry = manager.get_entry(added.secret_hash)

        assert entry is not None
        assert entry.reason == "Test"

    def test_get_nonexistent(self, manager: AllowlistManager):
        """Test getting a non-existent entry."""
        entry = manager.get_entry("nonexistent-hash")

        assert entry is None

    def test_get_from_namespace(self, manager: AllowlistManager):
        """Test getting entry with namespace fallback."""
        ns_entry = manager.add(value="ns-secret", namespace="decisions")
        global_entry = manager.add(value="global-secret", namespace=None)

        # Both should be found when checking namespace
        assert (
            manager.get_entry(ns_entry.secret_hash, namespace="decisions") is not None
        )
        assert (
            manager.get_entry(global_entry.secret_hash, namespace="decisions")
            is not None
        )


class TestClearCache:
    """Tests for cache management."""

    def test_clear_cache_forces_reload(self, tmp_path: Path):
        """Test that clear_cache forces reload from disk."""
        manager = AllowlistManager(data_dir=tmp_path)
        entry = manager.add(value="cached")

        # Verify in cache
        assert manager.is_allowed(entry.secret_hash)

        # Clear cache
        manager.clear_cache()

        # Should still work (reloads from disk)
        assert manager.is_allowed(entry.secret_hash)
