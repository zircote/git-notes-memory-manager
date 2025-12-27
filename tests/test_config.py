"""Tests for git_notes_memory.config module.

Tests all configuration constants, path resolution, and environment variable overrides.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from git_notes_memory import config

if TYPE_CHECKING:
    from collections.abc import Iterator


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def clean_env() -> Iterator[None]:
    """Clean up environment variables before and after test."""
    env_vars = [
        "MEMORY_PLUGIN_DATA_DIR",
        "MEMORY_PLUGIN_GIT_NAMESPACE",
        "MEMORY_PLUGIN_EMBEDDING_MODEL",
        "MEMORY_PLUGIN_AUTO_CAPTURE",
        "XDG_DATA_HOME",
    ]
    old_values = {var: os.environ.get(var) for var in env_vars}

    # Remove all env vars before test
    for var in env_vars:
        os.environ.pop(var, None)

    yield

    # Restore original values after test
    for var, value in old_values.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value


# =============================================================================
# Domain Configuration Tests
# =============================================================================


class TestDomainEnum:
    """Tests for Domain enum."""

    def test_domain_values(self) -> None:
        """Test Domain enum has USER and PROJECT values."""
        assert config.Domain.USER.value == "user"
        assert config.Domain.PROJECT.value == "project"

    def test_domain_membership(self) -> None:
        """Test Domain enum has exactly two members."""
        assert len(config.Domain) == 2

    def test_domain_is_enum(self) -> None:
        """Test Domain is an Enum class."""
        from enum import Enum

        assert issubclass(config.Domain, Enum)

    def test_domain_user_is_distinct(self) -> None:
        """Test USER and PROJECT are distinct enum values."""
        assert config.Domain.USER != config.Domain.PROJECT

    def test_domain_str_representation(self) -> None:
        """Test Domain string representation."""
        assert str(config.Domain.USER) == "Domain.USER"
        assert str(config.Domain.PROJECT) == "Domain.PROJECT"


class TestUserMemoriesPath:
    """Tests for get_user_memories_path() function."""

    def test_returns_path(self, clean_env: None) -> None:
        """Test get_user_memories_path returns a Path."""
        result = config.get_user_memories_path()
        assert isinstance(result, Path)

    def test_default_path(self, clean_env: None) -> None:
        """Test default path is in XDG data directory."""
        result = config.get_user_memories_path()
        expected = Path.home() / ".local" / "share" / "memory-plugin" / "user-memories"
        assert result == expected

    def test_respects_data_dir_override(self, clean_env: None) -> None:
        """Test path respects MEMORY_PLUGIN_DATA_DIR override."""
        os.environ["MEMORY_PLUGIN_DATA_DIR"] = "/custom/data"
        result = config.get_user_memories_path()
        assert result == Path("/custom/data/user-memories")

    def test_respects_xdg_data_home(self, clean_env: None) -> None:
        """Test path respects XDG_DATA_HOME."""
        os.environ["XDG_DATA_HOME"] = "/custom/xdg"
        result = config.get_user_memories_path()
        assert result == Path("/custom/xdg/memory-plugin/user-memories")

    def test_does_not_create_directory_by_default(
        self, tmp_path: Path, clean_env: None
    ) -> None:
        """Test get_user_memories_path does not create directory by default."""
        os.environ["MEMORY_PLUGIN_DATA_DIR"] = str(tmp_path)
        result = config.get_user_memories_path()
        # Path is returned but directory is not created
        assert result == tmp_path / "user-memories"
        assert not result.exists()

    def test_creates_directory_with_ensure_exists(
        self, tmp_path: Path, clean_env: None
    ) -> None:
        """Test get_user_memories_path creates directory when ensure_exists=True."""
        os.environ["MEMORY_PLUGIN_DATA_DIR"] = str(tmp_path)
        result = config.get_user_memories_path(ensure_exists=True)
        assert result.exists()
        assert result.is_dir()


class TestUserIndexPath:
    """Tests for get_user_index_path() function."""

    def test_returns_path(self, clean_env: None) -> None:
        """Test get_user_index_path returns a Path."""
        result = config.get_user_index_path()
        assert isinstance(result, Path)

    def test_default_path(self, clean_env: None) -> None:
        """Test default path is in XDG data directory."""
        result = config.get_user_index_path()
        expected = (
            Path.home() / ".local" / "share" / "memory-plugin" / "user" / "index.db"
        )
        assert result == expected

    def test_respects_data_dir_override(self, clean_env: None) -> None:
        """Test path respects MEMORY_PLUGIN_DATA_DIR override."""
        os.environ["MEMORY_PLUGIN_DATA_DIR"] = "/custom/data"
        result = config.get_user_index_path()
        assert result == Path("/custom/data/user/index.db")

    def test_does_not_create_directory_by_default(
        self, tmp_path: Path, clean_env: None
    ) -> None:
        """Test get_user_index_path does not create directory by default."""
        os.environ["MEMORY_PLUGIN_DATA_DIR"] = str(tmp_path)
        result = config.get_user_index_path()
        # Path is returned but parent directory is not created
        assert result == tmp_path / "user" / "index.db"
        assert not result.parent.exists()

    def test_creates_parent_directory_with_ensure_exists(
        self, tmp_path: Path, clean_env: None
    ) -> None:
        """Test get_user_index_path creates parent directory when ensure_exists=True."""
        os.environ["MEMORY_PLUGIN_DATA_DIR"] = str(tmp_path)
        result = config.get_user_index_path(ensure_exists=True)
        assert result.parent.exists()
        assert result.parent.is_dir()
        # The file itself should NOT be created, just the directory
        assert not result.exists()

    def test_filename_is_index_db(self, clean_env: None) -> None:
        """Test the filename is index.db."""
        result = config.get_user_index_path()
        assert result.name == "index.db"


# =============================================================================
# Namespace Tests
# =============================================================================


class TestNamespaces:
    """Tests for namespace configuration."""

    def test_namespaces_count(self) -> None:
        """Test that exactly 10 namespaces are defined."""
        assert len(config.NAMESPACES) == 10

    def test_namespaces_membership(self) -> None:
        """Test all expected namespaces exist."""
        expected = {
            "inception",
            "elicitation",
            "research",
            "decisions",
            "progress",
            "blockers",
            "reviews",
            "learnings",
            "retrospective",
            "patterns",
        }
        assert expected == config.NAMESPACES

    def test_namespaces_is_frozenset(self) -> None:
        """Test that NAMESPACES is immutable."""
        assert isinstance(config.NAMESPACES, frozenset)

    def test_auto_capture_namespaces_is_subset(self) -> None:
        """Test that AUTO_CAPTURE_NAMESPACES is subset of NAMESPACES."""
        assert config.AUTO_CAPTURE_NAMESPACES <= config.NAMESPACES

    def test_auto_capture_excludes_reviews(self) -> None:
        """Test that auto-capture excludes 'reviews' namespace."""
        assert "reviews" not in config.AUTO_CAPTURE_NAMESPACES


# =============================================================================
# Git Configuration Tests
# =============================================================================


class TestGitConfiguration:
    """Tests for git namespace configuration."""

    def test_default_git_namespace(self) -> None:
        """Test default git namespace value."""
        assert config.DEFAULT_GIT_NAMESPACE == "refs/notes/mem"

    def test_get_git_namespace_default(self, clean_env: None) -> None:
        """Test get_git_namespace returns default when no env var."""
        assert config.get_git_namespace() == "refs/notes/mem"

    def test_get_git_namespace_override(self, clean_env: None) -> None:
        """Test get_git_namespace respects environment override."""
        os.environ["MEMORY_PLUGIN_GIT_NAMESPACE"] = "refs/notes/custom"
        assert config.get_git_namespace() == "refs/notes/custom"


# =============================================================================
# Path Configuration Tests
# =============================================================================


class TestPathConfiguration:
    """Tests for path configuration and resolution."""

    def test_index_db_name(self) -> None:
        """Test index database filename."""
        assert config.INDEX_DB_NAME == "index.db"

    def test_models_dir_name(self) -> None:
        """Test models directory name."""
        assert config.MODELS_DIR_NAME == "models"

    def test_lock_file_name(self) -> None:
        """Test lock file name."""
        assert config.LOCK_FILE_NAME == ".capture.lock"

    def test_get_data_path_default(self, clean_env: None) -> None:
        """Test get_data_path returns XDG-compliant default."""
        path = config.get_data_path()
        expected = Path.home() / ".local" / "share" / "memory-plugin"
        assert path == expected

    def test_get_data_path_xdg_override(self, clean_env: None) -> None:
        """Test get_data_path respects XDG_DATA_HOME."""
        os.environ["XDG_DATA_HOME"] = "/custom/xdg/data"
        path = config.get_data_path()
        assert path == Path("/custom/xdg/data/memory-plugin")

    def test_get_data_path_env_override(self, clean_env: None) -> None:
        """Test get_data_path respects MEMORY_PLUGIN_DATA_DIR."""
        os.environ["MEMORY_PLUGIN_DATA_DIR"] = "/custom/memory/data"
        path = config.get_data_path()
        assert path == Path("/custom/memory/data")

    def test_get_data_path_env_override_priority(self, clean_env: None) -> None:
        """Test MEMORY_PLUGIN_DATA_DIR takes priority over XDG_DATA_HOME."""
        os.environ["XDG_DATA_HOME"] = "/xdg/data"
        os.environ["MEMORY_PLUGIN_DATA_DIR"] = "/custom/memory"
        path = config.get_data_path()
        assert path == Path("/custom/memory")

    def test_get_data_path_expands_tilde(self, clean_env: None) -> None:
        """Test get_data_path expands ~ in paths."""
        os.environ["MEMORY_PLUGIN_DATA_DIR"] = "~/memory-plugin"
        path = config.get_data_path()
        assert path == Path.home() / "memory-plugin"

    def test_get_index_path(self, clean_env: None) -> None:
        """Test get_index_path returns correct path."""
        path = config.get_index_path()
        expected = config.get_data_path() / "index.db"
        assert path == expected

    def test_get_models_path(self, clean_env: None) -> None:
        """Test get_models_path returns correct path."""
        path = config.get_models_path()
        expected = config.get_data_path() / "models"
        assert path == expected

    def test_get_lock_path(self, clean_env: None) -> None:
        """Test get_lock_path returns correct path."""
        path = config.get_lock_path()
        expected = config.get_data_path() / ".capture.lock"
        assert path == expected


# =============================================================================
# Git Root Detection Tests
# =============================================================================


class TestFindGitRoot:
    """Tests for find_git_root() function."""

    def test_finds_git_root_from_root(self, tmp_path: Path) -> None:
        """Test finding git root when at the repo root."""
        (tmp_path / ".git").mkdir()
        result = config.find_git_root(tmp_path)
        assert result == tmp_path

    def test_finds_git_root_from_subdir(self, tmp_path: Path) -> None:
        """Test finding git root from a subdirectory."""
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "src" / "deep" / "nested"
        subdir.mkdir(parents=True)
        result = config.find_git_root(subdir)
        assert result == tmp_path

    def test_uses_cwd_when_no_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test using current directory when no path provided."""
        (tmp_path / ".git").mkdir()
        monkeypatch.chdir(tmp_path)
        result = config.find_git_root()
        assert result == tmp_path

    def test_raises_when_not_in_git_repo(self, tmp_path: Path) -> None:
        """Test raising NotInGitRepositoryError when not in a git repo."""
        # tmp_path has no .git directory
        with pytest.raises(config.NotInGitRepositoryError) as exc_info:
            config.find_git_root(tmp_path)
        assert "Not inside a git repository" in str(exc_info.value)
        assert ".memory folder must be at the git root" in str(exc_info.value)

    def test_error_includes_path(self, tmp_path: Path) -> None:
        """Test that error message includes the path that was searched."""
        with pytest.raises(config.NotInGitRepositoryError) as exc_info:
            config.find_git_root(tmp_path)
        assert str(tmp_path) in str(exc_info.value)


class TestProjectMemoryDirGitRoot:
    """Tests for get_project_memory_dir() git root enforcement."""

    def test_returns_memory_dir_at_git_root(self, tmp_path: Path) -> None:
        """Test .memory is placed at git root."""
        (tmp_path / ".git").mkdir()
        result = config.get_project_memory_dir(tmp_path)
        assert result == tmp_path / ".memory"

    def test_finds_git_root_from_subdir(self, tmp_path: Path) -> None:
        """Test .memory is placed at git root even when called from subdir."""
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "src" / "nested"
        subdir.mkdir(parents=True)
        result = config.get_project_memory_dir(subdir)
        # Should be at git root, not in subdir
        assert result == tmp_path / ".memory"
        assert result != subdir / ".memory"

    def test_raises_when_not_in_git_repo(self, tmp_path: Path) -> None:
        """Test raising error when not in a git repository."""
        with pytest.raises(config.NotInGitRepositoryError):
            config.get_project_memory_dir(tmp_path)

    def test_index_path_at_git_root(self, tmp_path: Path) -> None:
        """Test index.db is placed at git root/.memory/."""
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "src"
        subdir.mkdir()
        result = config.get_project_index_path(subdir)
        assert result == tmp_path / ".memory" / "index.db"


class TestProjectIdentifierGitRoot:
    """Tests for get_project_identifier() git root resolution."""

    def test_consistent_id_from_any_subdir(self, tmp_path: Path) -> None:
        """Test same ID returned from any subdirectory."""
        (tmp_path / ".git").mkdir()
        subdir1 = tmp_path / "src"
        subdir2 = tmp_path / "tests" / "deep"
        subdir1.mkdir()
        subdir2.mkdir(parents=True)

        id_root = config.get_project_identifier(tmp_path)
        id_subdir1 = config.get_project_identifier(subdir1)
        id_subdir2 = config.get_project_identifier(subdir2)

        assert id_root == id_subdir1 == id_subdir2

    def test_raises_when_not_in_git_repo(self, tmp_path: Path) -> None:
        """Test raising error when not in a git repository."""
        with pytest.raises(config.NotInGitRepositoryError):
            config.get_project_identifier(tmp_path)


# =============================================================================
# Embedding Configuration Tests
# =============================================================================


class TestEmbeddingConfiguration:
    """Tests for embedding model configuration."""

    def test_default_embedding_model(self) -> None:
        """Test default embedding model name."""
        assert config.DEFAULT_EMBEDDING_MODEL == "all-MiniLM-L6-v2"

    def test_embedding_dimensions(self) -> None:
        """Test embedding dimensions for default model."""
        assert config.EMBEDDING_DIMENSIONS == 384

    def test_get_embedding_model_default(self, clean_env: None) -> None:
        """Test get_embedding_model returns default when no env var."""
        assert config.get_embedding_model() == "all-MiniLM-L6-v2"

    def test_get_embedding_model_override(self, clean_env: None) -> None:
        """Test get_embedding_model respects environment override."""
        os.environ["MEMORY_PLUGIN_EMBEDDING_MODEL"] = "custom-model"
        assert config.get_embedding_model() == "custom-model"


# =============================================================================
# Limits and Thresholds Tests
# =============================================================================


class TestLimitsAndThresholds:
    """Tests for limits and threshold constants."""

    def test_max_content_bytes(self) -> None:
        """Test MAX_CONTENT_BYTES is 100KB."""
        assert config.MAX_CONTENT_BYTES == 102400

    def test_max_summary_chars(self) -> None:
        """Test MAX_SUMMARY_CHARS is 100."""
        assert config.MAX_SUMMARY_CHARS == 100

    def test_max_hydration_files(self) -> None:
        """Test MAX_HYDRATION_FILES is 20."""
        assert config.MAX_HYDRATION_FILES == 20

    def test_max_file_size(self) -> None:
        """Test MAX_FILE_SIZE is 100KB."""
        assert config.MAX_FILE_SIZE == 102400


# =============================================================================
# Performance Timeout Tests
# =============================================================================


class TestPerformanceTimeouts:
    """Tests for performance timeout constants."""

    def test_search_timeout_ms(self) -> None:
        """Test SEARCH_TIMEOUT_MS is 500ms."""
        assert config.SEARCH_TIMEOUT_MS == 500

    def test_capture_timeout_ms(self) -> None:
        """Test CAPTURE_TIMEOUT_MS is 2000ms."""
        assert config.CAPTURE_TIMEOUT_MS == 2000

    def test_reindex_timeout_ms(self) -> None:
        """Test REINDEX_TIMEOUT_MS is 60000ms."""
        assert config.REINDEX_TIMEOUT_MS == 60000

    def test_lock_timeout_seconds(self) -> None:
        """Test LOCK_TIMEOUT_SECONDS is 5s."""
        assert config.LOCK_TIMEOUT_SECONDS == 5


# =============================================================================
# Cache Settings Tests
# =============================================================================


class TestCacheSettings:
    """Tests for cache configuration constants."""

    def test_cache_ttl_seconds(self) -> None:
        """Test CACHE_TTL_SECONDS is 300 (5 minutes)."""
        assert config.CACHE_TTL_SECONDS == 300.0

    def test_cache_max_entries(self) -> None:
        """Test CACHE_MAX_ENTRIES is 100."""
        assert config.CACHE_MAX_ENTRIES == 100


# =============================================================================
# Lifecycle Settings Tests
# =============================================================================


class TestLifecycleSettings:
    """Tests for lifecycle configuration constants."""

    def test_decay_half_life_days(self) -> None:
        """Test DECAY_HALF_LIFE_DAYS is 30."""
        assert config.DECAY_HALF_LIFE_DAYS == 30

    def test_seconds_per_day(self) -> None:
        """Test SECONDS_PER_DAY is correct."""
        assert config.SECONDS_PER_DAY == 86400
        assert config.SECONDS_PER_DAY == 60 * 60 * 24


# =============================================================================
# Search Defaults Tests
# =============================================================================


class TestSearchDefaults:
    """Tests for search default constants."""

    def test_default_recall_limit(self) -> None:
        """Test DEFAULT_RECALL_LIMIT is 10."""
        assert config.DEFAULT_RECALL_LIMIT == 10

    def test_default_search_limit(self) -> None:
        """Test DEFAULT_SEARCH_LIMIT is 10."""
        assert config.DEFAULT_SEARCH_LIMIT == 10

    def test_max_recall_limit(self) -> None:
        """Test MAX_RECALL_LIMIT is 100."""
        assert config.MAX_RECALL_LIMIT == 100

    def test_max_proactive_suggestions(self) -> None:
        """Test MAX_PROACTIVE_SUGGESTIONS is 3."""
        assert config.MAX_PROACTIVE_SUGGESTIONS == 3


# =============================================================================
# Note Schema Tests
# =============================================================================


class TestNoteSchema:
    """Tests for note schema configuration."""

    def test_note_required_fields(self) -> None:
        """Test NOTE_REQUIRED_FIELDS contains expected fields."""
        expected = {"type", "spec", "timestamp", "summary"}
        assert expected == config.NOTE_REQUIRED_FIELDS

    def test_note_optional_fields(self) -> None:
        """Test NOTE_OPTIONAL_FIELDS contains expected fields."""
        expected = {"phase", "tags", "relates_to", "status"}
        assert expected == config.NOTE_OPTIONAL_FIELDS

    def test_note_fields_are_frozenset(self) -> None:
        """Test note field sets are immutable."""
        assert isinstance(config.NOTE_REQUIRED_FIELDS, frozenset)
        assert isinstance(config.NOTE_OPTIONAL_FIELDS, frozenset)


# =============================================================================
# Auto-capture Tests
# =============================================================================


class TestAutoCaptureConfiguration:
    """Tests for auto-capture configuration."""

    def test_is_auto_capture_disabled_by_default(self, clean_env: None) -> None:
        """Test auto-capture is disabled by default."""
        assert config.is_auto_capture_enabled() is False

    def test_is_auto_capture_enabled_with_1(self, clean_env: None) -> None:
        """Test auto-capture enabled with '1'."""
        os.environ["MEMORY_PLUGIN_AUTO_CAPTURE"] = "1"
        assert config.is_auto_capture_enabled() is True

    def test_is_auto_capture_enabled_with_true(self, clean_env: None) -> None:
        """Test auto-capture enabled with 'true'."""
        os.environ["MEMORY_PLUGIN_AUTO_CAPTURE"] = "true"
        assert config.is_auto_capture_enabled() is True

    def test_is_auto_capture_enabled_with_TRUE(self, clean_env: None) -> None:
        """Test auto-capture enabled with 'TRUE' (case-insensitive)."""
        os.environ["MEMORY_PLUGIN_AUTO_CAPTURE"] = "TRUE"
        assert config.is_auto_capture_enabled() is True

    def test_is_auto_capture_enabled_with_yes(self, clean_env: None) -> None:
        """Test auto-capture enabled with 'yes'."""
        os.environ["MEMORY_PLUGIN_AUTO_CAPTURE"] = "yes"
        assert config.is_auto_capture_enabled() is True

    def test_is_auto_capture_enabled_with_on(self, clean_env: None) -> None:
        """Test auto-capture enabled with 'on'."""
        os.environ["MEMORY_PLUGIN_AUTO_CAPTURE"] = "on"
        assert config.is_auto_capture_enabled() is True

    def test_is_auto_capture_disabled_with_0(self, clean_env: None) -> None:
        """Test auto-capture disabled with '0'."""
        os.environ["MEMORY_PLUGIN_AUTO_CAPTURE"] = "0"
        assert config.is_auto_capture_enabled() is False

    def test_is_auto_capture_disabled_with_false(self, clean_env: None) -> None:
        """Test auto-capture disabled with 'false'."""
        os.environ["MEMORY_PLUGIN_AUTO_CAPTURE"] = "false"
        assert config.is_auto_capture_enabled() is False

    def test_is_auto_capture_disabled_with_invalid(self, clean_env: None) -> None:
        """Test auto-capture disabled with invalid value."""
        os.environ["MEMORY_PLUGIN_AUTO_CAPTURE"] = "invalid"
        assert config.is_auto_capture_enabled() is False


# =============================================================================
# Review Categories Tests
# =============================================================================


class TestReviewCategories:
    """Tests for review category configuration."""

    def test_review_categories(self) -> None:
        """Test REVIEW_CATEGORIES contains expected values."""
        expected = {
            "security",
            "performance",
            "architecture",
            "quality",
            "tests",
            "documentation",
        }
        assert expected == config.REVIEW_CATEGORIES

    def test_review_severities(self) -> None:
        """Test REVIEW_SEVERITIES contains expected values."""
        expected = {"critical", "high", "medium", "low"}
        assert expected == config.REVIEW_SEVERITIES

    def test_review_sets_are_frozenset(self) -> None:
        """Test review sets are immutable."""
        assert isinstance(config.REVIEW_CATEGORIES, frozenset)
        assert isinstance(config.REVIEW_SEVERITIES, frozenset)


# =============================================================================
# Retrospective Configuration Tests
# =============================================================================


class TestRetrospectiveConfiguration:
    """Tests for retrospective configuration."""

    def test_retrospective_outcomes(self) -> None:
        """Test RETROSPECTIVE_OUTCOMES contains expected values."""
        expected = {"success", "partial", "failed", "abandoned"}
        assert expected == config.RETROSPECTIVE_OUTCOMES

    def test_retrospective_outcomes_is_frozenset(self) -> None:
        """Test RETROSPECTIVE_OUTCOMES is immutable."""
        assert isinstance(config.RETROSPECTIVE_OUTCOMES, frozenset)


# =============================================================================
# Module Export Tests
# =============================================================================


class TestModuleExports:
    """Tests for module __all__ exports."""

    def test_all_exports_exist(self) -> None:
        """Test all items in __all__ are actually defined."""
        for name in config.__all__:
            assert hasattr(config, name), f"'{name}' in __all__ but not defined"

    def test_important_exports_in_all(self) -> None:
        """Test important items are exported in __all__."""
        important = [
            "Domain",
            "get_user_memories_path",
            "get_user_index_path",
            "NAMESPACES",
            "DEFAULT_GIT_NAMESPACE",
            "DEFAULT_EMBEDDING_MODEL",
            "get_data_path",
            "get_index_path",
            "get_models_path",
            "is_auto_capture_enabled",
        ]
        for name in important:
            assert name in config.__all__, f"'{name}' should be in __all__"
