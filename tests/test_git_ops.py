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
        """Test is_sync_configured when all configured."""
        git = GitOps(tmp_path)

        def mock_run(args, **kwargs):
            # Convert args to string for easier substring matching
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)
            if (
                "--get-all" in args_str
                and "remote.origin.push" in args_str
                or "--get-all" in args_str
                and "remote.origin.fetch" in args_str
            ):
                result.stdout = "refs/notes/mem/*:refs/notes/mem/*"
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
            elif "remote.origin.push" in args_str or "remote.origin.fetch" in args_str:
                result.stdout = "refs/notes/mem/*:refs/notes/mem/*"
            elif "notes.rewriteRef" in args_str:
                result.stdout = "refs/notes/mem/*"
            elif "notes.mergeStrategy" in args_str:
                result.stdout = "cat_sort_uniq"
            return result

        with patch("subprocess.run", side_effect=mock_run):
            assert git.ensure_sync_configured() is True

    def test_ensure_sync_configured_configures_missing(self, tmp_path: Path) -> None:
        """Test ensure_sync_configured configures missing settings."""
        git = GitOps(tmp_path)
        config_calls = []

        def mock_run(args, **kwargs):
            args_str = " ".join(str(a) for a in args)
            result = MagicMock(returncode=0)

            if "rev-parse" in args_str and "--git-dir" in args_str:
                result.stdout = ".git"
            elif "remote" in args_str and "get-url" in args_str:
                result.stdout = "git@github.com:user/repo.git"
            elif "config" in args_str and "--add" in args_str:
                # Track config calls
                config_calls.append(args)
                result.returncode = 0
            elif "config" in args_str and "--get" in args_str:
                # First is_sync_configured call returns not configured
                if len(config_calls) == 0:
                    result.returncode = 1
                    result.stdout = ""
                else:
                    # After configure, return configured
                    result.stdout = "refs/notes/mem/*"
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
