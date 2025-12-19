"""End-to-end functional tests for plugin commands.

These tests validate the command execution paths used by the skill files
to ensure API contracts are maintained and prevent regressions.

Each command corresponds to a skill file in commands/:
- /memory:capture -> commands/capture.md
- /memory:recall -> commands/recall.md
- /memory:search -> commands/search.md
- /memory:status -> commands/status.md
- /memory:sync -> commands/sync.md
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


class TestStatusCommandE2E:
    """E2E tests for /memory:status command.

    Tests the exact Python code executed by commands/status.md.
    """

    def test_basic_status_api_exists(self) -> None:
        """Test that all APIs used by basic status command exist."""
        # These imports must succeed for the command to work
        from git_notes_memory import get_sync_service
        from git_notes_memory.config import (
            get_data_path,
            get_embedding_model,
            get_index_path,
        )
        from git_notes_memory.index import IndexService

        # Functions must be callable
        assert callable(get_sync_service)
        assert callable(get_index_path)
        assert callable(get_data_path)
        assert callable(get_embedding_model)

        # Classes must be instantiable
        index_path = get_index_path()
        index = IndexService(index_path)
        assert index is not None

    def test_basic_status_execution(self) -> None:
        """Test basic status command executes without error."""
        code = """
from git_notes_memory import get_sync_service
from git_notes_memory.index import IndexService
from git_notes_memory.config import get_embedding_model, get_index_path, get_data_path

sync = get_sync_service()
index_path = get_index_path()

if index_path.exists():
    index = IndexService(index_path)
    index.initialize()
    stats = index.get_stats()
    assert stats.total_memories >= 0
    assert stats.index_size_bytes >= 0
    index.close()

assert get_embedding_model() == "all-MiniLM-L6-v2"
assert get_data_path() is not None
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Status command failed: {result.stderr}"

    def test_verbose_status_api_exists(self) -> None:
        """Test that all APIs used by verbose status command exist."""
        from git_notes_memory import get_sync_service
        from git_notes_memory.config import (
            NAMESPACES,
            get_index_path,
        )
        from git_notes_memory.index import IndexService

        # NAMESPACES must be iterable (frozenset)
        assert isinstance(NAMESPACES, frozenset)
        assert len(NAMESPACES) == 10

        # Sync service must have verify_consistency
        sync = get_sync_service()
        assert hasattr(sync, "verify_consistency")

        # IndexService.get_stats must return proper structure
        index_path = get_index_path()
        if index_path.exists():
            index = IndexService(index_path)
            index.initialize()
            stats = index.get_stats()
            # Stats must have required attributes
            assert hasattr(stats, "total_memories")
            assert hasattr(stats, "by_namespace")
            assert hasattr(stats, "by_spec")
            assert hasattr(stats, "last_sync")
            assert hasattr(stats, "index_size_bytes")
            index.close()


class TestCaptureCommandE2E:
    """E2E tests for /memory:capture command."""

    def test_capture_api_exists(self) -> None:
        """Test that capture API exists and is callable."""
        from git_notes_memory import get_capture_service

        capture = get_capture_service()
        assert hasattr(capture, "capture")
        assert callable(capture.capture)

    def test_capture_result_structure(self, tmp_path: Path) -> None:
        """Test that capture result has expected structure."""
        from git_notes_memory.capture import CaptureService
        from git_notes_memory.index import IndexService

        # Set up isolated test environment
        index_path = tmp_path / "index.db"
        index = IndexService(index_path)
        index.initialize()

        capture = CaptureService(
            repo_path=tmp_path,
            index_service=index,
        )

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        # Create initial commit
        (tmp_path / "README.md").write_text("test")
        subprocess.run(
            ["git", "add", "."],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=tmp_path,
            capture_output=True,
            check=True,
        )

        result = capture.capture(
            namespace="learnings",
            summary="Test E2E capture",
            content="This is a test capture for E2E validation.",
        )

        # Result must have expected attributes for command script
        assert hasattr(result, "success")
        assert hasattr(result, "memory")
        assert hasattr(result, "warning")

        if result.success:
            assert result.memory is not None
            assert hasattr(result.memory, "namespace")
            assert hasattr(result.memory, "id")
            assert hasattr(result.memory, "summary")

        index.close()


class TestRecallCommandE2E:
    """E2E tests for /memory:recall command."""

    def test_recall_api_exists(self) -> None:
        """Test that recall API exists and is callable."""
        from git_notes_memory import get_recall_service

        recall = get_recall_service()
        assert hasattr(recall, "search")
        assert callable(recall.search)

    def test_recall_result_structure(self) -> None:
        """Test that recall results have expected structure."""
        from git_notes_memory import get_recall_service

        recall = get_recall_service()
        results = recall.search(query="test", k=5)

        # Results is a list
        assert isinstance(results, list)

        # Each result must have expected attributes
        for r in results:
            assert hasattr(r, "namespace")
            assert hasattr(r, "summary")
            assert hasattr(r, "score")
            assert hasattr(r, "timestamp")
            assert hasattr(r, "content")


class TestSearchCommandE2E:
    """E2E tests for /memory:search command."""

    def test_search_api_exists(self) -> None:
        """Test that search API exists."""
        from git_notes_memory import get_recall_service

        recall = get_recall_service()
        # Semantic search
        assert hasattr(recall, "search")
        # Text search
        assert hasattr(recall, "search_text")

    def test_search_text_result_structure(self) -> None:
        """Test that text search results have expected structure."""
        from git_notes_memory import get_recall_service

        recall = get_recall_service()
        results = recall.search_text(query="test", limit=5)

        assert isinstance(results, list)
        for m in results:
            # Must have attributes used in command script
            assert hasattr(m, "namespace")
            assert hasattr(m, "summary")
            assert hasattr(m, "timestamp")


class TestSyncCommandE2E:
    """E2E tests for /memory:sync command."""

    def test_sync_api_exists(self) -> None:
        """Test that sync API exists."""
        from git_notes_memory import get_sync_service

        sync = get_sync_service()

        # Must have methods used by command scripts
        assert hasattr(sync, "reindex")
        assert hasattr(sync, "verify_consistency")
        assert hasattr(sync, "repair")

    def test_reindex_returns_count(self) -> None:
        """Test that reindex returns a count."""
        from git_notes_memory import get_sync_service

        sync = get_sync_service()
        count = sync.reindex(full=False)

        assert isinstance(count, int)
        assert count >= 0

    def test_verify_consistency_result_structure(self) -> None:
        """Test that verify_consistency returns proper structure."""
        from git_notes_memory import get_sync_service

        sync = get_sync_service()
        result = sync.verify_consistency()

        # Must have attributes used by command script
        assert hasattr(result, "is_consistent")
        assert hasattr(result, "missing_in_index")
        assert hasattr(result, "orphaned_in_index")
        assert hasattr(result, "mismatched")

        assert isinstance(result.is_consistent, bool)
        assert isinstance(result.missing_in_index, (list, tuple))
        assert isinstance(result.orphaned_in_index, (list, tuple))


class TestConfigAPIExports:
    """Tests to ensure config module exports required APIs for commands."""

    def test_get_embedding_model_exported(self) -> None:
        """Test get_embedding_model is exported and callable."""
        from git_notes_memory.config import get_embedding_model

        result = get_embedding_model()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_index_path_exported(self) -> None:
        """Test get_index_path is exported and callable."""
        from git_notes_memory.config import get_index_path

        result = get_index_path()
        assert isinstance(result, Path)

    def test_get_data_path_exported(self) -> None:
        """Test get_data_path is exported and callable."""
        from git_notes_memory.config import get_data_path

        result = get_data_path()
        assert isinstance(result, Path)

    def test_namespaces_exported(self) -> None:
        """Test NAMESPACES is exported and is a frozenset."""
        from git_notes_memory.config import NAMESPACES

        assert isinstance(NAMESPACES, frozenset)
        assert "learnings" in NAMESPACES
        assert "decisions" in NAMESPACES


class TestIndexServiceAPI:
    """Tests to ensure IndexService has required methods for commands."""

    def test_index_service_get_stats(self, tmp_path: Path) -> None:
        """Test IndexService.get_stats returns proper structure."""
        from git_notes_memory.index import IndexService

        index = IndexService(tmp_path / "test.db")
        index.initialize()
        stats = index.get_stats()

        # Verify all attributes used by commands
        assert hasattr(stats, "total_memories")
        assert hasattr(stats, "by_namespace")
        assert hasattr(stats, "by_spec")
        assert hasattr(stats, "last_sync")
        assert hasattr(stats, "index_size_bytes")

        index.close()

    def test_index_service_initialize_required(self, tmp_path: Path) -> None:
        """Test that initialize() must be called before operations."""
        from git_notes_memory.exceptions import MemoryIndexError
        from git_notes_memory.index import IndexService

        index = IndexService(tmp_path / "test.db")

        # Should raise without initialize
        with pytest.raises(MemoryIndexError):
            index.get_stats()

        index.close()
