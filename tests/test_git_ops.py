"""Tests for git_notes_memory.git_ops module.

Tests git operations wrapper with mocked subprocess calls.
Also includes integration tests that work with real git repositories.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from git_notes_memory import config
from git_notes_memory.exceptions import StorageError, ValidationError
from git_notes_memory.git_ops import CommitInfo, GitOps, validate_path

if TYPE_CHECKING:
    pass


# =============================================================================
# Path Validation Tests
# =============================================================================


class TestValidatePath:
    """Tests for validate_path function."""

    def test_valid_simple_path(self) -> None:
        """Test validation of simple file path."""
        validate_path("src/main.py")  # Should not raise

    def test_valid_nested_path(self) -> None:
        """Test validation of deeply nested path."""
        validate_path("src/git_notes_memory/git_ops.py")  # Should not raise

    def test_valid_path_with_spaces(self) -> None:
        """Test path with spaces is allowed."""
        validate_path("docs/my file.md")  # Should not raise

    def test_valid_path_with_dot(self) -> None:
        """Test path with dots is allowed."""
        validate_path(".gitignore")  # Should not raise
        validate_path("src/.hidden/file.txt")  # Should not raise

    def test_empty_path_raises(self) -> None:
        """Test empty path raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_path("")
        assert "cannot be empty" in exc_info.value.message

    def test_path_starting_with_dash_raises(self) -> None:
        """Test path starting with dash raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_path("-rf")
        assert "cannot start with dash" in exc_info.value.message

    def test_absolute_path_raises(self) -> None:
        """Test absolute path raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_path("/etc/passwd")
        assert "absolute paths" in exc_info.value.message.lower()

    def test_null_byte_raises(self) -> None:
        """Test path with null byte raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_path("file\x00name")
        assert "null bytes" in exc_info.value.message.lower()

    def test_path_traversal_raises(self) -> None:
        """Test path traversal raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_path("../etc/passwd")
        assert "traversal" in exc_info.value.message.lower()

    def test_path_with_shell_metachar_raises(self) -> None:
        """Test path with shell metacharacters raises."""
        invalid_paths = [
            "file;rm -rf",
            "file`id`",
            "file$(whoami)",
            "file|cat",
            "file&bg",
        ]
        for path in invalid_paths:
            with pytest.raises(ValidationError):
                validate_path(path)


# =============================================================================
# CommitInfo Tests
# =============================================================================


class TestCommitInfo:
    """Tests for CommitInfo dataclass."""

    def test_create_commit_info(self) -> None:
        """Test creating a CommitInfo instance."""
        info = CommitInfo(
            sha="abc123def456",
            author_name="Test User",
            author_email="test@example.com",
            date="2024-01-15T10:30:00+00:00",
            message="Test commit",
        )
        assert info.sha == "abc123def456"
        assert info.author_name == "Test User"
        assert info.author_email == "test@example.com"
        assert info.date == "2024-01-15T10:30:00+00:00"
        assert info.message == "Test commit"

    def test_commit_info_is_frozen(self) -> None:
        """Test that CommitInfo is immutable."""
        info = CommitInfo(
            sha="abc123",
            author_name="Test",
            author_email="test@test.com",
            date="2024-01-15",
            message="Test",
        )
        with pytest.raises(AttributeError):
            info.sha = "new_sha"  # type: ignore[misc]


# =============================================================================
# GitOps Initialization Tests
# =============================================================================


class TestGitOpsInit:
    """Tests for GitOps initialization."""

    def test_init_with_path(self, tmp_path: Path) -> None:
        """Test initialization with explicit path."""
        git = GitOps(tmp_path)
        assert git.repo_path == tmp_path

    def test_init_with_string_path(self, tmp_path: Path) -> None:
        """Test initialization with string path."""
        git = GitOps(str(tmp_path))
        assert git.repo_path == tmp_path

    def test_init_without_path_uses_cwd(self) -> None:
        """Test initialization without path uses current directory."""
        git = GitOps()
        assert git.repo_path == Path.cwd()


# =============================================================================
# GitOps Validation Tests
# =============================================================================


class TestGitOpsValidation:
    """Tests for GitOps internal validation methods."""

    def test_validate_namespace_valid(self, tmp_path: Path) -> None:
        """Test validation of valid namespaces."""
        git = GitOps(tmp_path)
        for namespace in config.NAMESPACES:
            git._validate_namespace(namespace)  # Should not raise

    def test_validate_namespace_invalid(self, tmp_path: Path) -> None:
        """Test validation of invalid namespace raises."""
        git = GitOps(tmp_path)
        with pytest.raises(ValidationError) as exc_info:
            git._validate_namespace("invalid_namespace")
        assert "Invalid namespace" in exc_info.value.message

    def test_validate_git_ref_valid(self, tmp_path: Path) -> None:
        """Test validation of valid git refs."""
        git = GitOps(tmp_path)
        valid_refs = [
            "HEAD",
            "main",
            "feature/test",
            "v1.0.0",
            "abc123def",
            "HEAD~1",
            "HEAD^2",
            "origin/main",
        ]
        for ref in valid_refs:
            git._validate_git_ref(ref)  # Should not raise

    def test_validate_git_ref_empty_raises(self, tmp_path: Path) -> None:
        """Test empty ref raises ValidationError."""
        git = GitOps(tmp_path)
        with pytest.raises(ValidationError) as exc_info:
            git._validate_git_ref("")
        assert "cannot be empty" in exc_info.value.message

    def test_validate_git_ref_dash_prefix_raises(self, tmp_path: Path) -> None:
        """Test ref starting with dash raises ValidationError."""
        git = GitOps(tmp_path)
        with pytest.raises(ValidationError) as exc_info:
            git._validate_git_ref("-n")
        assert "cannot start with dash" in exc_info.value.message

    def test_validate_git_ref_invalid_chars_raises(self, tmp_path: Path) -> None:
        """Test ref with invalid characters raises ValidationError."""
        git = GitOps(tmp_path)
        invalid_refs = [
            "ref;rm -rf",
            "ref`id`",
            "ref$(cmd)",
            "ref with space",
        ]
        for ref in invalid_refs:
            with pytest.raises(ValidationError):
                git._validate_git_ref(ref)


# =============================================================================
# GitOps Note Ref Tests
# =============================================================================


class TestGitOpsNoteRef:
    """Tests for note ref generation."""

    def test_note_ref_default_namespace(self, tmp_path: Path) -> None:
        """Test note ref uses default git namespace."""
        git = GitOps(tmp_path)
        ref = git._note_ref("decisions")
        assert ref == "refs/notes/mem/decisions"

    def test_note_ref_with_env_override(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test note ref uses environment override."""
        monkeypatch.setenv("MEMORY_PLUGIN_GIT_NAMESPACE", "refs/notes/custom")
        git = GitOps(tmp_path)
        ref = git._note_ref("decisions")
        assert ref == "refs/notes/custom/decisions"


# =============================================================================
# GitOps _run_git Tests (Mocked)
# =============================================================================


class TestGitOpsRunGit:
    """Tests for _run_git method with mocked subprocess."""

    def test_run_git_success(self, tmp_path: Path) -> None:
        """Test successful git command execution."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="output", stderr="")

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = git._run_git(["status"])

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[:2] == ["git", "-C"]
            assert call_args[3] == "status"
            assert result.returncode == 0

    def test_run_git_not_a_repo_error(self, tmp_path: Path) -> None:
        """Test error handling for non-repository."""
        git = GitOps(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                128, "git", stderr="fatal: not a git repository"
            )
            with pytest.raises(StorageError) as exc_info:
                git._run_git(["status"])

            assert "Not in a Git repository" in exc_info.value.message

    def test_run_git_permission_denied_error(self, tmp_path: Path) -> None:
        """Test error handling for permission denied."""
        git = GitOps(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "git", stderr="permission denied"
            )
            with pytest.raises(StorageError) as exc_info:
                git._run_git(["status"])

            assert "Permission denied" in exc_info.value.message

    def test_run_git_no_commits_error(self, tmp_path: Path) -> None:
        """Test error handling for repository without commits."""
        git = GitOps(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                128, "git", stderr="does not have any commits yet"
            )
            with pytest.raises(StorageError) as exc_info:
                git._run_git(["log"])

            assert "no commits" in exc_info.value.message.lower()

    def test_run_git_generic_error(self, tmp_path: Path) -> None:
        """Test generic error handling."""
        git = GitOps(tmp_path)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, "git", stderr="some random error"
            )
            with pytest.raises(StorageError) as exc_info:
                git._run_git(["status"])

            assert "Git command failed" in exc_info.value.message


# =============================================================================
# GitOps Note Operations Tests (Mocked)
# =============================================================================


class TestGitOpsNoteOperationsMocked:
    """Tests for note operations with mocked subprocess."""

    def test_add_note_calls_git_correctly(self, tmp_path: Path) -> None:
        """Test add_note constructs correct git command."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0)

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            git.add_note("decisions", "Test content", "HEAD")

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "notes" in args
            assert "--ref=refs/notes/mem/decisions" in args
            assert "add" in args
            assert "-m" in args
            assert "Test content" in args

    def test_add_note_with_force(self, tmp_path: Path) -> None:
        """Test add_note with force flag."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0)

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            git.add_note("decisions", "Test content", "HEAD", force=True)

            args = mock_run.call_args[0][0]
            assert "-f" in args

    def test_add_note_invalid_namespace_raises(self, tmp_path: Path) -> None:
        """Test add_note with invalid namespace raises immediately."""
        git = GitOps(tmp_path)

        with pytest.raises(ValidationError) as exc_info:
            git.add_note("invalid", "content", "HEAD")

        assert "Invalid namespace" in exc_info.value.message

    def test_append_note_calls_git_correctly(self, tmp_path: Path) -> None:
        """Test append_note constructs correct git command."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0)

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            git.append_note("learnings", "New learning", "abc123")

            args = mock_run.call_args[0][0]
            assert "notes" in args
            assert "--ref=refs/notes/mem/learnings" in args
            assert "append" in args
            assert "-m" in args
            assert "New learning" in args

    def test_show_note_returns_content(self, tmp_path: Path) -> None:
        """Test show_note returns note content."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="Note content")

        with patch("subprocess.run", return_value=mock_result):
            result = git.show_note("decisions", "HEAD")

            assert result == "Note content"

    def test_show_note_returns_none_when_missing(self, tmp_path: Path) -> None:
        """Test show_note returns None when note doesn't exist."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=1, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            result = git.show_note("decisions", "HEAD")

            assert result is None

    def test_list_notes_parses_output(self, tmp_path: Path) -> None:
        """Test list_notes parses git output correctly."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(
            returncode=0,
            stdout="abc123 def456\n789xyz 012abc\n",
        )

        with patch("subprocess.run", return_value=mock_result):
            result = git.list_notes("decisions")

            assert result == [("abc123", "def456"), ("789xyz", "012abc")]

    def test_list_notes_empty_when_no_notes(self, tmp_path: Path) -> None:
        """Test list_notes returns empty list when no notes."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=1, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            result = git.list_notes("decisions")

            assert result == []

    def test_remove_note_returns_true_on_success(self, tmp_path: Path) -> None:
        """Test remove_note returns True on success."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = git.remove_note("decisions", "HEAD")

            assert result is True

    def test_remove_note_returns_false_when_missing(self, tmp_path: Path) -> None:
        """Test remove_note returns False when note doesn't exist."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=1)

        with patch("subprocess.run", return_value=mock_result):
            result = git.remove_note("decisions", "HEAD")

            assert result is False


# =============================================================================
# GitOps Commit Operations Tests (Mocked)
# =============================================================================


class TestGitOpsCommitOperationsMocked:
    """Tests for commit operations with mocked subprocess."""

    def test_get_commit_sha(self, tmp_path: Path) -> None:
        """Test get_commit_sha returns SHA."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(
            returncode=0,
            stdout="abc123def456789\n",
        )

        with patch("subprocess.run", return_value=mock_result):
            result = git.get_commit_sha("HEAD")

            assert result == "abc123def456789"

    def test_get_commit_info_parses_output(self, tmp_path: Path) -> None:
        """Test get_commit_info parses git log output."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(
            returncode=0,
            stdout="abc123def456\nTest Author\ntest@example.com\n2024-01-15T10:30:00+00:00\nTest commit message\n",
        )

        with patch("subprocess.run", return_value=mock_result):
            result = git.get_commit_info("HEAD")

            assert isinstance(result, CommitInfo)
            assert result.sha == "abc123def456"
            assert result.author_name == "Test Author"
            assert result.author_email == "test@example.com"
            assert result.date == "2024-01-15T10:30:00+00:00"
            assert result.message == "Test commit message"

    def test_get_file_at_commit_returns_content(self, tmp_path: Path) -> None:
        """Test get_file_at_commit returns file content."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(
            returncode=0,
            stdout="file content here",
        )

        with patch("subprocess.run", return_value=mock_result):
            result = git.get_file_at_commit("src/main.py", "HEAD")

            assert result == "file content here"

    def test_get_file_at_commit_returns_none_when_missing(self, tmp_path: Path) -> None:
        """Test get_file_at_commit returns None when file doesn't exist."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=1, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            result = git.get_file_at_commit("nonexistent.py", "HEAD")

            assert result is None

    def test_get_changed_files(self, tmp_path: Path) -> None:
        """Test get_changed_files parses output."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(
            returncode=0,
            stdout="src/main.py\nsrc/utils.py\nREADME.md\n",
        )

        with patch("subprocess.run", return_value=mock_result):
            result = git.get_changed_files("HEAD")

            assert result == ["src/main.py", "src/utils.py", "README.md"]


# =============================================================================
# GitOps Sync Configuration Tests (Mocked)
# =============================================================================


class TestGitOpsSyncConfigMocked:
    """Tests for sync configuration with mocked subprocess."""

    def test_is_sync_configured_all_false(self, tmp_path: Path) -> None:
        """Test is_sync_configured when nothing configured."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=1, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            result = git.is_sync_configured()

            assert result == {
                "push": False,
                "fetch": False,
                "rewrite": False,
                "merge": False,
            }

    def test_is_sync_configured_all_true(self, tmp_path: Path) -> None:
        """Test is_sync_configured when all configured with new pattern."""
        git = GitOps(tmp_path)

        def mock_run(args, **kwargs):
            # Convert args to string for easier substring matching
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)
            if "--get-all" in args_str and "remote.origin.push" in args_str:
                result.stdout = "refs/notes/mem/*:refs/notes/mem/*"
            elif "--get-all" in args_str and "remote.origin.fetch" in args_str:
                # New pattern with tracking refs
                result.stdout = "+refs/notes/mem/*:refs/notes/origin/mem/*"
            elif "notes.rewriteRef" in args_str:
                result.stdout = "refs/notes/mem/*"
            elif "notes.mergeStrategy" in args_str:
                result.stdout = "cat_sort_uniq"
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.is_sync_configured()

            assert result == {
                "push": True,
                "fetch": True,
                "rewrite": True,
                "merge": True,
                "fetch_old": False,
                "fetch_new": True,
            }

    def test_configure_sync_sets_all(self, tmp_path: Path) -> None:
        """Test configure_sync sets all configurations."""
        git = GitOps(tmp_path)

        # First call returns not configured, subsequent calls succeed
        call_count = 0

        def mock_run(args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock(returncode=0 if call_count > 4 else 1, stdout="")
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.configure_sync()

            # All should be newly configured
            assert result["push"] is True
            assert result["fetch"] is True
            assert result["rewrite"] is True
            assert result["merge"] is True

    def test_ensure_sync_configured_when_not_git_repo(self, tmp_path: Path) -> None:
        """Test ensure_sync_configured returns False for non-git repos."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=128, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            assert git.ensure_sync_configured() is False

    def test_ensure_sync_configured_when_no_remote(self, tmp_path: Path) -> None:
        """Test ensure_sync_configured returns False when no origin remote."""
        git = GitOps(tmp_path)

        def mock_run(args, **kwargs):
            args_str = " ".join(str(a) for a in args)
            if "rev-parse" in args_str and "--git-dir" in args_str:
                return MagicMock(returncode=0, stdout=".git")
            if "remote" in args_str and "get-url" in args_str:
                return MagicMock(returncode=1, stdout="")
            return MagicMock(returncode=0, stdout="")

        with patch("subprocess.run", side_effect=mock_run):
            assert git.ensure_sync_configured() is False

    def test_ensure_sync_configured_already_configured(self, tmp_path: Path) -> None:
        """Test ensure_sync_configured returns True when already configured."""
        git = GitOps(tmp_path)

        def mock_run(args, **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)
            if "rev-parse" in args_str and "--git-dir" in args_str:
                result.stdout = ".git"
            elif "remote" in args_str and "get-url" in args_str:
                result.stdout = "git@github.com:user/repo.git"
            elif "--get-all" in args_str and "remote.origin.push" in args_str:
                result.stdout = "refs/notes/mem/*:refs/notes/mem/*"
            elif "--get-all" in args_str and "remote.origin.fetch" in args_str:
                # New pattern uses tracking refs
                result.stdout = "+refs/notes/mem/*:refs/notes/origin/mem/*"
            elif "--get" in args_str and "notes.rewriteRef" in args_str:
                result.stdout = "refs/notes/mem/*"
            elif "--get" in args_str and "notes.mergeStrategy" in args_str:
                result.stdout = "cat_sort_uniq"
            return result

        with patch("subprocess.run", side_effect=mock_run):
            assert git.ensure_sync_configured() is True

    def test_ensure_sync_configured_configures_missing(self, tmp_path: Path) -> None:
        """Test ensure_sync_configured configures missing settings."""
        git = GitOps(tmp_path)
        config_calls: list[list[str]] = []
        configured = False

        def mock_run(args, **kwargs):
            nonlocal configured
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)

            if "rev-parse" in args_str and "--git-dir" in args_str:
                result.stdout = ".git"
            elif "remote" in args_str and "get-url" in args_str:
                result.stdout = "git@github.com:user/repo.git"
            elif "config" in args_str and "--add" in args_str:
                # Track config calls and mark as configured
                config_calls.append(list(args))
                configured = True
                result.returncode = 0
            elif "--get-all" in args_str and "remote.origin.push" in args_str:
                if configured:
                    result.stdout = "refs/notes/mem/*:refs/notes/mem/*"
                else:
                    result.returncode = 1
                    result.stdout = ""
            elif "--get-all" in args_str and "remote.origin.fetch" in args_str:
                if configured:
                    result.stdout = "+refs/notes/mem/*:refs/notes/origin/mem/*"
                else:
                    result.returncode = 1
                    result.stdout = ""
            elif "--get" in args_str and "notes.rewriteRef" in args_str:
                if configured:
                    result.stdout = "refs/notes/mem/*"
                else:
                    result.returncode = 1
                    result.stdout = ""
            elif "--get" in args_str and "notes.mergeStrategy" in args_str:
                if configured:
                    result.stdout = "cat_sort_uniq"
                else:
                    result.returncode = 1
                    result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.ensure_sync_configured()
            # Should have made config calls
            assert len(config_calls) > 0
            assert result is True


# =============================================================================
# GitOps Repository Info Tests (Mocked)
# =============================================================================


class TestGitOpsRepoInfoMocked:
    """Tests for repository info methods with mocked subprocess."""

    def test_is_git_repository_true(self, tmp_path: Path) -> None:
        """Test is_git_repository returns True for repo."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0, stdout=".git")

        with patch("subprocess.run", return_value=mock_result):
            assert git.is_git_repository() is True

    def test_is_git_repository_false(self, tmp_path: Path) -> None:
        """Test is_git_repository returns False for non-repo."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=128, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            assert git.is_git_repository() is False

    def test_get_repository_root(self, tmp_path: Path) -> None:
        """Test get_repository_root returns path."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="/path/to/repo\n")

        with patch("subprocess.run", return_value=mock_result):
            result = git.get_repository_root()

            assert result == Path("/path/to/repo")

    def test_get_repository_root_returns_none(self, tmp_path: Path) -> None:
        """Test get_repository_root returns None for non-repo."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=128, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            result = git.get_repository_root()

            assert result is None

    def test_has_commits_true(self, tmp_path: Path) -> None:
        """Test has_commits returns True when commits exist."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0, stdout="abc123")

        with patch("subprocess.run", return_value=mock_result):
            assert git.has_commits() is True

    def test_has_commits_false(self, tmp_path: Path) -> None:
        """Test has_commits returns False for empty repo."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=128, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            assert git.has_commits() is False


# =============================================================================
# Integration Tests (Real Git)
# =============================================================================


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a real git repository for integration tests."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)

    # Configure git user for commits
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    (repo_path / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return repo_path


class TestGitOpsIntegration:
    """Integration tests with real git repositories."""

    def test_is_git_repository_real(self, git_repo: Path) -> None:
        """Test is_git_repository with real repo."""
        git = GitOps(git_repo)
        assert git.is_git_repository() is True

    def test_is_git_repository_non_repo(self, tmp_path: Path) -> None:
        """Test is_git_repository with non-repo directory."""
        git = GitOps(tmp_path)
        assert git.is_git_repository() is False

    def test_has_commits_real(self, git_repo: Path) -> None:
        """Test has_commits with real repo."""
        git = GitOps(git_repo)
        assert git.has_commits() is True

    def test_get_commit_sha_real(self, git_repo: Path) -> None:
        """Test get_commit_sha with real repo."""
        git = GitOps(git_repo)
        sha = git.get_commit_sha("HEAD")
        # SHA should be 40 hex characters
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_get_commit_info_real(self, git_repo: Path) -> None:
        """Test get_commit_info with real repo."""
        git = GitOps(git_repo)
        info = git.get_commit_info("HEAD")

        assert isinstance(info, CommitInfo)
        assert info.author_name == "Test User"
        assert info.author_email == "test@example.com"
        assert info.message == "Initial commit"

    def test_get_changed_files_real(self, git_repo: Path) -> None:
        """Test get_changed_files with real repo."""
        git = GitOps(git_repo)
        files = git.get_changed_files("HEAD")

        assert "README.md" in files

    def test_get_file_at_commit_real(self, git_repo: Path) -> None:
        """Test get_file_at_commit with real repo."""
        git = GitOps(git_repo)
        content = git.get_file_at_commit("README.md", "HEAD")

        assert content is not None
        assert "# Test Repo" in content

    def test_note_lifecycle_real(self, git_repo: Path) -> None:
        """Test full note lifecycle with real repo."""
        git = GitOps(git_repo)

        # Initially no note
        assert git.show_note("decisions", "HEAD") is None
        assert git.list_notes("decisions") == []

        # Add note
        git.add_note("decisions", "Test decision", "HEAD")
        note = git.show_note("decisions", "HEAD")
        assert note is not None
        assert "Test decision" in note

        # List notes
        notes = git.list_notes("decisions")
        assert len(notes) == 1

        # Append to note
        git.append_note("decisions", "Additional info", "HEAD")
        note = git.show_note("decisions", "HEAD")
        assert "Test decision" in note
        assert "Additional info" in note

        # Remove note
        result = git.remove_note("decisions", "HEAD")
        assert result is True
        assert git.show_note("decisions", "HEAD") is None

    def test_note_in_different_namespaces(self, git_repo: Path) -> None:
        """Test notes in different namespaces are independent."""
        git = GitOps(git_repo)

        # Add notes to different namespaces
        git.add_note("decisions", "A decision", "HEAD")
        git.add_note("learnings", "A learning", "HEAD")

        # Each namespace has its own note
        assert "decision" in (git.show_note("decisions", "HEAD") or "")
        assert "learning" in (git.show_note("learnings", "HEAD") or "")

        # Removing from one doesn't affect other
        git.remove_note("decisions", "HEAD")
        assert git.show_note("decisions", "HEAD") is None
        assert "learning" in (git.show_note("learnings", "HEAD") or "")

    def test_repository_root_real(self, git_repo: Path) -> None:
        """Test get_repository_root with real repo."""
        git = GitOps(git_repo)
        root = git.get_repository_root()

        assert root is not None
        assert root.exists()
        assert (root / ".git").exists()


# =============================================================================
# GitOps Migration Tests (Mocked)
# =============================================================================


class TestGitOpsMigrationMocked:
    """Tests for migrate_fetch_config with mocked subprocess."""

    def test_migrate_no_config(self, tmp_path: Path) -> None:
        """Test migration when no fetch config exists."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=1, stdout="")

        with patch("subprocess.run", return_value=mock_result):
            result = git.migrate_fetch_config()
            assert result is False

    def test_migrate_old_pattern_to_new(self, tmp_path: Path) -> None:
        """Test migration from old pattern to new tracking refs."""
        git = GitOps(tmp_path)
        config_calls: list[list[str]] = []

        def mock_run(args: list[str], **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)

            if "--get-all" in args_str and "remote.origin.fetch" in args_str:
                # Return old pattern
                result.stdout = "refs/notes/mem/*:refs/notes/mem/*"
            elif "--unset" in args_str or "--add" in args_str:
                config_calls.append(list(args))
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.migrate_fetch_config()

            assert result is True
            # Should have unset old and added new
            assert len(config_calls) == 2

    def test_migrate_already_new_pattern(self, tmp_path: Path) -> None:
        """Test migration when already using new pattern."""
        git = GitOps(tmp_path)

        def mock_run(args: list[str], **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)

            if "--get-all" in args_str and "remote.origin.fetch" in args_str:
                # Return new pattern (no old pattern)
                result.stdout = "+refs/notes/mem/*:refs/notes/origin/mem/*"
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.migrate_fetch_config()
            # No migration needed - no old pattern
            assert result is False

    def test_migrate_both_patterns_removes_old(self, tmp_path: Path) -> None:
        """Test migration when both patterns exist removes old."""
        git = GitOps(tmp_path)
        unset_called = []

        def mock_run(args: list[str], **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)

            if "--get-all" in args_str and "remote.origin.fetch" in args_str:
                # Return both patterns
                result.stdout = (
                    "refs/notes/mem/*:refs/notes/mem/*\n"
                    "+refs/notes/mem/*:refs/notes/origin/mem/*"
                )
            elif "--unset" in args_str:
                unset_called.append(list(args))
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.migrate_fetch_config()

            assert result is True
            # Should have only unset old, not added new (already exists)
            assert len(unset_called) == 1


# =============================================================================
# GitOps Remote Sync Tests (Mocked)
# =============================================================================


class TestGitOpsRemoteSyncMocked:
    """Tests for remote sync methods with mocked subprocess."""

    def test_fetch_notes_from_remote_success(self, tmp_path: Path) -> None:
        """Test fetch_notes_from_remote with successful fetch."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = git.fetch_notes_from_remote(["decisions", "learnings"])

            assert result["decisions"] is True
            assert result["learnings"] is True

    def test_fetch_notes_from_remote_partial_failure(self, tmp_path: Path) -> None:
        """Test fetch_notes_from_remote with some failures."""
        git = GitOps(tmp_path)
        call_count = 0

        def mock_run(args: list[str], **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            # First call succeeds, second fails
            result.returncode = 0 if call_count == 1 else 1
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.fetch_notes_from_remote(["decisions", "learnings"])

            # First succeeds, second fails
            assert result["decisions"] is True
            assert result["learnings"] is False

    def test_merge_notes_from_tracking_success(self, tmp_path: Path) -> None:
        """Test merge_notes_from_tracking with successful merge."""
        git = GitOps(tmp_path)

        def mock_run(args: list[str], **kwargs):
            result = MagicMock(returncode=0)
            if "rev-parse" in " ".join(str(a) for a in args):
                result.stdout = "abc123"  # Tracking ref exists
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.merge_notes_from_tracking("decisions")
            assert result is True

    def test_merge_notes_from_tracking_no_tracking_ref(self, tmp_path: Path) -> None:
        """Test merge_notes_from_tracking when no tracking ref."""
        git = GitOps(tmp_path)

        def mock_run(args: list[str], **kwargs):
            result = MagicMock()
            if "rev-parse" in " ".join(str(a) for a in args):
                result.returncode = 1  # Tracking ref doesn't exist
            else:
                result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.merge_notes_from_tracking("decisions")
            # Should return True (no-op when no tracking ref)
            assert result is True

    def test_merge_notes_invalid_namespace_raises(self, tmp_path: Path) -> None:
        """Test merge_notes_from_tracking with invalid namespace."""
        git = GitOps(tmp_path)

        with pytest.raises(ValidationError):
            git.merge_notes_from_tracking("invalid_namespace")

    def test_push_notes_to_remote_success(self, tmp_path: Path) -> None:
        """Test push_notes_to_remote with successful push."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=0)

        with patch("subprocess.run", return_value=mock_result):
            result = git.push_notes_to_remote()
            assert result is True

    def test_push_notes_to_remote_failure(self, tmp_path: Path) -> None:
        """Test push_notes_to_remote with failed push."""
        git = GitOps(tmp_path)
        mock_result = MagicMock(returncode=1)

        with patch("subprocess.run", return_value=mock_result):
            result = git.push_notes_to_remote()
            assert result is False

    def test_sync_notes_with_remote_full_workflow(self, tmp_path: Path) -> None:
        """Test sync_notes_with_remote orchestrates fetch→merge→push."""
        git = GitOps(tmp_path)
        call_sequence: list[str] = []

        def mock_run(args: list[str], **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)

            if "fetch" in args_str:
                call_sequence.append("fetch")
            elif "rev-parse" in args_str:
                result.stdout = "abc123"
                call_sequence.append("rev-parse")
            elif "notes" in args_str and "merge" in args_str:
                call_sequence.append("merge")
            elif "push" in args_str:
                call_sequence.append("push")
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.sync_notes_with_remote(["decisions"])

            assert result["decisions"] is True
            # Verify workflow order: fetch → rev-parse → merge → push
            assert "fetch" in call_sequence
            assert "push" in call_sequence

    def test_sync_notes_with_remote_no_push(self, tmp_path: Path) -> None:
        """Test sync_notes_with_remote with push=False."""
        git = GitOps(tmp_path)
        push_called = []

        def mock_run(args: list[str], **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)
            if "push" in args_str:
                push_called.append(True)
            elif "rev-parse" in args_str:
                result.stdout = "abc123"
            return result

        with patch("subprocess.run", side_effect=mock_run):
            git.sync_notes_with_remote(["decisions"], push=False)

            # Push should not have been called
            assert len(push_called) == 0


# =============================================================================
# GitOps is_sync_configured Pattern Detection Tests
# =============================================================================


class TestGitOpsSyncPatternDetection:
    """Tests for detecting old vs new fetch patterns in is_sync_configured."""

    def test_detects_old_pattern(self, tmp_path: Path) -> None:
        """Test is_sync_configured detects old fetch pattern."""
        git = GitOps(tmp_path)

        def mock_run(args: list[str], **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)
            if "remote.origin.fetch" in args_str or "remote.origin.push" in args_str:
                result.stdout = "refs/notes/mem/*:refs/notes/mem/*"
            else:
                result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.is_sync_configured()

            assert result["fetch"] is True
            assert result.get("fetch_old") is True
            assert result.get("fetch_new") is False

    def test_detects_new_pattern(self, tmp_path: Path) -> None:
        """Test is_sync_configured detects new tracking refs pattern."""
        git = GitOps(tmp_path)

        def mock_run(args: list[str], **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)
            if "remote.origin.fetch" in args_str:
                result.stdout = "+refs/notes/mem/*:refs/notes/origin/mem/*"
            elif "remote.origin.push" in args_str:
                result.stdout = "refs/notes/mem/*:refs/notes/mem/*"
            else:
                result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.is_sync_configured()

            assert result["fetch"] is True
            assert result.get("fetch_old") is False
            assert result.get("fetch_new") is True

    def test_detects_both_patterns(self, tmp_path: Path) -> None:
        """Test is_sync_configured detects when both patterns exist."""
        git = GitOps(tmp_path)

        def mock_run(args: list[str], **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)
            if "remote.origin.fetch" in args_str:
                result.stdout = (
                    "refs/notes/mem/*:refs/notes/mem/*\n"
                    "+refs/notes/mem/*:refs/notes/origin/mem/*"
                )
            elif "remote.origin.push" in args_str:
                result.stdout = "refs/notes/mem/*:refs/notes/mem/*"
            else:
                result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=mock_run):
            result = git.is_sync_configured()

            assert result["fetch"] is True
            assert result.get("fetch_old") is True
            assert result.get("fetch_new") is True


# =============================================================================
# Integration Tests - Diverged Notes Scenario
# =============================================================================


@pytest.fixture
def git_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Create a local git repo with a bare remote for sync testing.

    Returns:
        Tuple of (local_repo_path, remote_repo_path).
    """
    # Create bare remote repository
    remote_path = tmp_path / "remote.git"
    remote_path.mkdir()
    subprocess.run(
        ["git", "init", "--bare"],
        cwd=remote_path,
        check=True,
        capture_output=True,
    )
    # Configure git user in bare repo (needed for tests that append notes directly)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=remote_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=remote_path,
        check=True,
        capture_output=True,
    )

    # Create local repository
    local_path = tmp_path / "local"
    local_path.mkdir()
    subprocess.run(["git", "init"], cwd=local_path, check=True, capture_output=True)

    # Configure git user
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=local_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=local_path,
        check=True,
        capture_output=True,
    )

    # Add remote
    subprocess.run(
        ["git", "remote", "add", "origin", str(remote_path)],
        cwd=local_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit and push
    (local_path / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=local_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=local_path,
        check=True,
        capture_output=True,
    )

    # Get current branch name (main or master depending on git version)
    branch_result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=local_path,
        capture_output=True,
        text=True,
        check=True,
    )
    branch_name = branch_result.stdout.strip() or "main"

    subprocess.run(
        ["git", "push", "-u", "origin", branch_name],
        cwd=local_path,
        check=True,
        capture_output=True,
    )

    return local_path, remote_path


class TestGitOpsDivergedNotesIntegration:
    """Integration tests for diverged notes merge scenario."""

    def test_configure_sync_uses_new_refspec(self, git_repo_with_remote: tuple) -> None:
        """Test configure_sync sets up tracking refs pattern."""
        local_path, _ = git_repo_with_remote
        git = GitOps(local_path)

        # Configure sync
        git.configure_sync()

        # Check fetch refspec uses new tracking refs pattern
        result = subprocess.run(
            ["git", "config", "--get-all", "remote.origin.fetch"],
            cwd=local_path,
            capture_output=True,
            text=True,
        )
        fetch_lines = result.stdout.strip().split("\n")

        # Should contain the new pattern
        assert any(
            "+refs/notes/mem/*:refs/notes/origin/mem/*" in line for line in fetch_lines
        )

    def test_add_and_push_notes(self, git_repo_with_remote: tuple) -> None:
        """Test adding notes locally and pushing to remote."""
        local_path, remote_path = git_repo_with_remote
        git = GitOps(local_path)

        # Configure sync first
        git.configure_sync()

        # Add a note
        git.add_note("decisions", "Local decision 1", "HEAD")

        # Push notes
        result = git.push_notes_to_remote()
        assert result is True

        # Verify note exists in remote
        # Remote won't have HEAD context, but notes should be in refs
        # Check via for-each-ref
        result = subprocess.run(
            ["git", "for-each-ref", "refs/notes/mem/decisions"],
            cwd=remote_path,
            capture_output=True,
            text=True,
        )
        assert "refs/notes/mem/decisions" in result.stdout

    def test_fetch_notes_creates_tracking_ref(
        self, git_repo_with_remote: tuple
    ) -> None:
        """Test fetch creates refs/notes/origin/mem/* tracking refs."""
        local_path, _ = git_repo_with_remote
        git = GitOps(local_path)
        git.configure_sync()

        # Add and push a note
        git.add_note("decisions", "Decision to fetch", "HEAD")
        git.push_notes_to_remote()

        # Delete local ref to simulate fresh fetch
        subprocess.run(
            ["git", "update-ref", "-d", f"{config.DEFAULT_GIT_NAMESPACE}/decisions"],
            cwd=local_path,
            check=True,
            capture_output=True,
        )

        # Fetch notes
        results = git.fetch_notes_from_remote(["decisions"])
        assert results["decisions"] is True

        # Verify tracking ref was created
        result = subprocess.run(
            ["git", "for-each-ref", "refs/notes/origin/mem/decisions"],
            cwd=local_path,
            capture_output=True,
            text=True,
        )
        assert "refs/notes/origin/mem/decisions" in result.stdout

    def test_merge_notes_with_cat_sort_uniq(self, git_repo_with_remote: tuple) -> None:
        """Test merging diverged notes uses cat_sort_uniq strategy."""
        local_path, remote_path = git_repo_with_remote
        git = GitOps(local_path)
        git.configure_sync()

        # Add initial note and push
        git.add_note("decisions", "Shared decision", "HEAD")
        git.push_notes_to_remote()

        # Simulate remote having additional content by directly modifying remote
        # First, get the commit SHA
        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=local_path,
            capture_output=True,
            text=True,
        )
        commit_sha = sha_result.stdout.strip()

        # Add to remote's note directly
        subprocess.run(
            [
                "git",
                "notes",
                f"--ref={config.DEFAULT_GIT_NAMESPACE}/decisions",
                "append",
                "-m",
                "Remote addition",
                commit_sha,
            ],
            cwd=remote_path,
            check=True,
            capture_output=True,
        )

        # Add local content
        git.append_note("decisions", "Local addition", "HEAD")

        # Fetch (creates tracking ref with remote's version)
        git.fetch_notes_from_remote(["decisions"])

        # Merge using tracking ref
        result = git.merge_notes_from_tracking("decisions")
        assert result is True

        # Verify merged content contains both additions
        note = git.show_note("decisions", "HEAD")
        assert note is not None
        assert "Shared decision" in note
        # The merge strategy should combine content
        # (exact behavior depends on cat_sort_uniq implementation)

    def test_full_sync_workflow(self, git_repo_with_remote: tuple) -> None:
        """Test complete sync_notes_with_remote workflow."""
        local_path, remote_path = git_repo_with_remote
        git = GitOps(local_path)
        git.configure_sync()

        # Add local note and push first to establish remote notes
        git.add_note("learnings", "Initial learning", "HEAD")
        git.push_notes_to_remote()

        # Simulate remote having additional content
        sha_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=local_path,
            capture_output=True,
            text=True,
        )
        commit_sha = sha_result.stdout.strip()

        subprocess.run(
            [
                "git",
                "notes",
                f"--ref={config.DEFAULT_GIT_NAMESPACE}/learnings",
                "append",
                "-m",
                "Remote learning",
                commit_sha,
            ],
            cwd=remote_path,
            check=True,
            capture_output=True,
        )

        # Add local content after remote addition
        git.append_note("learnings", "Local learning", "HEAD")

        # Full sync: fetch → merge → push
        results = git.sync_notes_with_remote(["learnings"])

        assert results["learnings"] is True

        # Note should contain all content
        note = git.show_note("learnings", "HEAD")
        assert note is not None
        assert "Initial learning" in note

    def test_migration_from_old_to_new_pattern(
        self, git_repo_with_remote: tuple
    ) -> None:
        """Test migration from old refspec to new tracking refs."""
        local_path, _ = git_repo_with_remote
        git = GitOps(local_path)

        # Manually configure OLD pattern (simulating pre-migration state)
        subprocess.run(
            [
                "git",
                "config",
                "--add",
                "remote.origin.fetch",
                "refs/notes/mem/*:refs/notes/mem/*",
            ],
            cwd=local_path,
            check=True,
            capture_output=True,
        )

        # Verify old pattern exists
        status = git.is_sync_configured()
        assert status.get("fetch_old") is True

        # Run migration
        migrated = git.migrate_fetch_config()
        assert migrated is True

        # Verify new pattern exists and old is gone
        status = git.is_sync_configured()
        assert status.get("fetch_new") is True
        assert status.get("fetch_old") is False
