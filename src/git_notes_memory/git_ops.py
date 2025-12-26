"""Git operations wrapper for memory capture plugin.

Provides a clean interface to Git notes commands with proper error handling.
All operations use subprocess and parse Git output appropriately.

Security:
- All refs are validated via validate_git_ref() before use
- All paths are validated to prevent injection and traversal
- Never uses shell=True in subprocess calls

Git Notes Architecture:
- Notes are stored under refs/notes/mem/{namespace} per namespace
- Each commit can have one note per namespace
- append_note is preferred for concurrent safety (atomically appends)
- Sync configuration enables push/fetch of notes to remotes
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from git_notes_memory.config import NAMESPACES, get_git_namespace
from git_notes_memory.exceptions import (
    INVALID_NAMESPACE_ERROR,
    StorageError,
    ValidationError,
)
from git_notes_memory.models import CommitInfo
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.tracing import trace_operation

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass

__all__ = [
    "GitOps",
    "CommitInfo",
    "validate_path",
]


# =============================================================================
# Constants
# =============================================================================

# Core sync config keys that must be True for git notes sync to work
SYNC_CORE_KEYS: tuple[str, ...] = ("push", "fetch", "rewrite", "merge")


# =============================================================================
# Git Version Detection
# =============================================================================

# Cached git version tuple (major, minor, patch)
_git_version: tuple[int, int, int] | None = None


def get_git_version() -> tuple[int, int, int]:
    """Get the installed git version as a tuple.

    Returns:
        Tuple of (major, minor, patch) version numbers.

    Note:
        Result is cached after first call.
    """
    global _git_version
    if _git_version is not None:
        return _git_version

    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
        # Parse "git version 2.43.0" or similar
        match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout)
        if match:
            _git_version = (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
        else:
            warnings.warn(
                "Could not parse git version from output; "
                "using regex fallback for config operations",
                UserWarning,
                stacklevel=2,
            )
            _git_version = (0, 0, 0)
    except Exception:
        warnings.warn(
            "Git version detection failed; using regex fallback for config operations",
            UserWarning,
            stacklevel=2,
        )
        _git_version = (0, 0, 0)

    return _git_version


def git_supports_fixed_value() -> bool:
    """Check if git version supports --fixed-value flag.

    The --fixed-value flag was added in git 2.37.0 to allow matching
    literal values (not regex) in git config operations.

    Returns:
        True if git >= 2.37.0, False otherwise.
    """
    major, minor, _ = get_git_version()
    return (major, minor) >= (2, 37)


# =============================================================================
# Path Validation
# =============================================================================


def validate_path(path: str) -> None:
    """Validate a file path to prevent command injection and path traversal.

    Args:
        path: File path relative to repo root.

    Raises:
        ValidationError: If path is invalid or potentially dangerous.

    Examples:
        >>> validate_path("src/main.py")  # OK
        >>> validate_path("../etc/passwd")  # Raises ValidationError
    """
    if not path:
        raise ValidationError(
            "Path cannot be empty",
            "Provide a valid file path",
        )
    if path.startswith("-"):
        raise ValidationError(
            "Invalid path: cannot start with dash",
            "Check path format - file paths should not begin with '-'",
        )
    # Prevent absolute paths and null bytes
    if path.startswith("/") or "\x00" in path:
        raise ValidationError(
            "Invalid path: absolute paths and null bytes not allowed",
            "Use relative paths from repository root",
        )
    # Check for path traversal
    if ".." in path:
        raise ValidationError(
            "Invalid path: path traversal not allowed",
            "Use direct paths without '..' components",
        )
    # Allow common path characters but prevent shell metacharacters
    if not re.match(r"^[a-zA-Z0-9_./@-][a-zA-Z0-9_./@ -]*$", path):
        raise ValidationError(
            "Invalid path format: contains illegal characters",
            "Use alphanumeric characters, dots, underscores, slashes, spaces, and dashes only",
        )


# =============================================================================
# GitOps Class
# =============================================================================


class GitOps:
    """Wrapper for Git notes operations.

    Handles add, append, show, list, and configuration of Git notes
    for the memory-capture namespaces.

    Attributes:
        repo_path: Path to the git repository root.

    Example:
        >>> git = GitOps("/path/to/repo")
        >>> git.append_note("decisions", "## Decision\\nChose PostgreSQL", "HEAD")
        >>> note = git.show_note("decisions", "HEAD")
    """

    def __init__(self, repo_path: Path | str | None = None) -> None:
        """Initialize GitOps for a repository.

        Args:
            repo_path: Path to git repository root. If None, uses cwd.
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()

    def _run_git(
        self,
        args: list[str],
        *,
        check: bool = True,
        capture_output: bool = True,
        timeout: float = 30.0,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command in the repository.

        Args:
            args: Git command arguments (without 'git' prefix).
            check: Raise on non-zero exit.
            capture_output: Capture stdout/stderr.
            timeout: Maximum time to wait for command (seconds). Default 30.0.
                HIGH-001: Prevents indefinite hangs on slow/unresponsive systems.

        Returns:
            CompletedProcess result.

        Raises:
            StorageError: If command fails and check=True, or if timeout is exceeded.
        """
        cmd = ["git", "-C", str(self.repo_path), *args]
        metrics = get_metrics()

        # Determine git subcommand for tracing
        git_subcommand = args[0] if args else "unknown"

        start_time = time.perf_counter()
        try:
            with trace_operation("git.subprocess", labels={"command": git_subcommand}):
                result = subprocess.run(
                    cmd,
                    check=check,
                    capture_output=capture_output,
                    text=True,
                    timeout=timeout,
                )

            # Record git command execution time
            duration_ms = (time.perf_counter() - start_time) * 1000
            metrics.observe(
                "git_command_duration_ms",
                duration_ms,
                labels={"command": git_subcommand},
            )
            metrics.increment(
                "git_commands_total",
                labels={"command": git_subcommand, "status": "success"},
            )

            return result
        except subprocess.CalledProcessError as e:
            metrics.increment(
                "git_commands_total",
                labels={"command": git_subcommand, "status": "error"},
            )
            # Parse common git errors for better messages
            # SEC-002: Sanitize paths in error messages to prevent info leakage
            stderr = e.stderr or ""
            if "not a git repository" in stderr.lower():
                raise StorageError(
                    "Not in a Git repository",
                    "Initialize a git repository: cd <repo_path> && git init",
                ) from e
            if "permission denied" in stderr.lower():
                raise StorageError(
                    "Permission denied for Git operation",
                    "Check repository permissions and ownership",
                ) from e
            if "does not have any commits" in stderr.lower():
                raise StorageError(
                    "Repository has no commits",
                    "Create at least one commit: git commit --allow-empty -m 'initial'",
                ) from e

            # SEC-002: Sanitize arguments to avoid leaking filesystem paths.
            # Handles POSIX/Windows absolute paths, home-relative, and traversals.
            def _looks_like_path(arg: str) -> bool:
                if not arg:
                    return False
                # POSIX absolute paths
                if arg.startswith("/"):
                    return True
                # Windows absolute paths (e.g., C:\path or D:/path)
                if len(arg) >= 3 and arg[1] == ":" and arg[2] in ("/", "\\"):
                    return True
                # Home-relative paths
                if arg.startswith("~"):
                    return True
                # Relative traversal paths
                return bool(arg.startswith(".."))

            repo_path_str = str(self.repo_path)
            sanitized_args: list[str] = []
            for arg in args:
                if arg == repo_path_str:
                    sanitized_args.append("<repo_path>")
                elif _looks_like_path(arg):
                    sanitized_args.append("<path>")
                else:
                    sanitized_args.append(arg)
            raise StorageError(
                f"Git command failed: {' '.join(sanitized_args)}\n{stderr}",
                "Check git status and try again",
            ) from e
        except subprocess.TimeoutExpired as e:
            metrics.increment(
                "git_commands_total",
                labels={"command": git_subcommand, "status": "timeout"},
            )
            # HIGH-001: Handle timeout to provide clear error message
            raise StorageError(
                f"Git command timed out after {timeout}s",
                "Git operation is taking too long; check for network issues or large repository",
            ) from e

    def _note_ref(self, namespace: str) -> str:
        """Get the full ref name for a namespace.

        Uses the configured git namespace prefix (default: refs/notes/mem)
        with the namespace appended.

        Args:
            namespace: Memory namespace (e.g., "decisions").

        Returns:
            Full ref path (e.g., "refs/notes/mem/decisions").
        """
        base = get_git_namespace()
        return f"{base}/{namespace}"

    def _validate_namespace(self, namespace: str) -> None:
        """Validate namespace against allowed values.

        Args:
            namespace: Memory namespace to validate.

        Raises:
            ValidationError: If namespace is invalid.
        """
        if namespace not in NAMESPACES:
            raise ValidationError(
                f"Invalid namespace: {namespace}",
                f"Use one of: {', '.join(sorted(NAMESPACES))}",
            )

    def _validate_git_ref(self, ref: str) -> None:
        """Validate a Git reference to prevent command injection.

        Args:
            ref: Git reference (commit SHA, branch, tag).

        Raises:
            ValidationError: If ref is invalid or potentially dangerous.
        """
        if not ref:
            raise ValidationError(
                "Git ref cannot be empty",
                "Provide a valid reference (commit SHA, branch, or tag)",
            )
        if ref.startswith("-"):
            raise ValidationError(
                "Invalid ref: cannot start with dash",
                "Check ref format - refs should not begin with '-'",
            )
        # Allow alphanumeric, dots, underscores, slashes, dashes, and tilde/caret for relative refs
        if not re.match(r"^[a-zA-Z0-9_./@^~-]+$", ref):
            raise ValidationError(
                "Invalid ref format: contains illegal characters",
                "Use alphanumeric characters, dots, underscores, slashes, and dashes only",
            )

    # =========================================================================
    # Note Operations
    # =========================================================================

    def add_note(
        self,
        namespace: str,
        content: str,
        commit: str = "HEAD",
        *,
        force: bool = False,
    ) -> None:
        """Add a note to a commit.

        WARNING: This overwrites any existing note. Use append_note() for safe
        concurrent operations.

        Args:
            namespace: Memory namespace (e.g., "decisions").
            content: Note content.
            commit: Commit to attach note to (default: HEAD).
            force: Overwrite existing note if present.

        Raises:
            ValidationError: If namespace or commit is invalid.
            StorageError: If git operation fails.
        """
        self._validate_namespace(namespace)
        self._validate_git_ref(commit)

        args = ["notes", f"--ref={self._note_ref(namespace)}", "add"]
        if force:
            args.append("-f")
        args.extend(["-m", content, commit])

        self._run_git(args)

    def append_note(
        self,
        namespace: str,
        content: str,
        commit: str = "HEAD",
    ) -> None:
        """Append content to a note (creates if not exists).

        This is the preferred method for capture operations,
        as it safely handles concurrent operations without data loss.

        Args:
            namespace: Memory namespace.
            content: Content to append.
            commit: Commit to attach to (default: HEAD).

        Raises:
            ValidationError: If namespace or commit is invalid.
            StorageError: If git operation fails.
        """
        self._validate_namespace(namespace)
        self._validate_git_ref(commit)

        args = [
            "notes",
            f"--ref={self._note_ref(namespace)}",
            "append",
            "-m",
            content,
            commit,
        ]

        self._run_git(args)

    def show_note(
        self,
        namespace: str,
        commit: str = "HEAD",
    ) -> str | None:
        """Show the note content for a commit.

        Args:
            namespace: Memory namespace.
            commit: Commit to get note from.

        Returns:
            Note content, or None if no note exists.

        Raises:
            ValidationError: If namespace or commit is invalid.
        """
        self._validate_namespace(namespace)
        self._validate_git_ref(commit)

        result = self._run_git(
            ["notes", f"--ref={self._note_ref(namespace)}", "show", commit],
            check=False,
        )

        if result.returncode != 0:
            return None

        return result.stdout

    def show_notes_batch(
        self,
        namespace: str,
        commit_shas: list[str],
    ) -> dict[str, str | None]:
        """Show multiple notes in a single subprocess call.

        Uses `git cat-file --batch` for efficient bulk retrieval.
        This is significantly faster than calling show_note() in a loop
        when fetching many notes.

        Args:
            namespace: Memory namespace.
            commit_shas: List of commit SHAs to get notes for.

        Returns:
            Dict mapping commit_sha -> note content (or None if no note).

        Raises:
            ValidationError: If namespace is invalid.
        """
        if not commit_shas:
            return {}

        self._validate_namespace(namespace)
        for sha in commit_shas:
            self._validate_git_ref(sha)

        # Build object references: notes ref points to the note object for each commit
        # Format: refs/notes/mem/namespace:commit_sha
        ref = self._note_ref(namespace)
        objects_input = "\n".join(f"{ref}:{sha}" for sha in commit_shas)

        # Run cat-file --batch to get all notes at once
        cmd = ["git", "-C", str(self.repo_path), "cat-file", "--batch"]

        try:
            result = subprocess.run(
                cmd,
                input=objects_input,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            # Fallback to sequential if batch fails
            return {sha: self.show_note(namespace, sha) for sha in commit_shas}

        # Parse batch output
        # Format per object:
        #   <sha> <type> <size>\n
        #   <content>\n
        # Or for missing:
        #   <ref> missing\n
        results: dict[str, str | None] = {}
        lines: list[str] = result.stdout.split("\n")
        i = 0
        sha_index = 0

        while i < len(lines) and sha_index < len(commit_shas):
            line = lines[i]
            current_sha = commit_shas[sha_index]

            # Check for missing object (format: "<ref> missing")
            header_parts = line.split()
            if len(header_parts) == 2 and header_parts[1] == "missing":
                results[current_sha] = None
                i += 1
                sha_index += 1
            elif line and not line.startswith(" "):
                # Header line: <object_sha> <type> <size>
                parts = header_parts
                if len(parts) >= 3:
                    try:
                        size = int(parts[2])
                        # Content follows on next lines until size bytes consumed
                        # Note: git cat-file --batch output format has content
                        # followed by a newline separator. We track bytes consumed
                        # including newlines between lines (but not trailing).
                        content_lines: list[str] = []
                        bytes_read = 0
                        i += 1
                        while bytes_read < size and i < len(lines):
                            content_line = lines[i]
                            line_bytes = len(content_line.encode("utf-8"))
                            # Account for newline except after last content line
                            if bytes_read + line_bytes >= size:
                                # Last line of content
                                content_lines.append(content_line)
                                bytes_read += line_bytes
                            else:
                                # More content follows; add newline byte
                                content_lines.append(content_line)
                                bytes_read += line_bytes + 1
                            i += 1
                        results[current_sha] = "\n".join(content_lines)
                        sha_index += 1
                    except (ValueError, IndexError):
                        results[current_sha] = None
                        sha_index += 1
                        i += 1
                else:
                    # Malformed header; treat as missing for current SHA
                    results[current_sha] = None
                    sha_index += 1
                    i += 1
            else:
                i += 1

        # Fill in any remaining SHAs as None
        for remaining_sha in commit_shas[sha_index:]:
            results[remaining_sha] = None

        return results

    def list_notes(
        self,
        namespace: str,
    ) -> list[tuple[str, str]]:
        """List all notes in a namespace.

        Args:
            namespace: Memory namespace.

        Returns:
            List of (note_object_sha, commit_sha) tuples.

        Raises:
            ValidationError: If namespace is invalid.
        """
        self._validate_namespace(namespace)

        result = self._run_git(
            ["notes", f"--ref={self._note_ref(namespace)}", "list"],
            check=False,
        )

        if result.returncode != 0 or not result.stdout.strip():
            return []

        notes = []
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2:
                note_sha, commit_sha = parts[0], parts[1]
                notes.append((note_sha, commit_sha))

        return notes

    def remove_note(
        self,
        namespace: str,
        commit: str = "HEAD",
    ) -> bool:
        """Remove a note from a commit.

        Args:
            namespace: Memory namespace.
            commit: Commit to remove note from.

        Returns:
            True if note was removed, False if no note existed.

        Raises:
            ValidationError: If namespace or commit is invalid.
        """
        self._validate_namespace(namespace)
        self._validate_git_ref(commit)

        result = self._run_git(
            ["notes", f"--ref={self._note_ref(namespace)}", "remove", commit],
            check=False,
        )
        return result.returncode == 0

    # =========================================================================
    # Commit Operations
    # =========================================================================

    def get_commit_sha(self, ref: str = "HEAD") -> str:
        """Get the full SHA for a commit reference.

        Args:
            ref: Git ref (branch, tag, HEAD, etc.).

        Returns:
            Full commit SHA (40 characters).

        Raises:
            ValidationError: If ref format is invalid.
            StorageError: If ref cannot be resolved.
        """
        self._validate_git_ref(ref)
        result = self._run_git(["rev-parse", ref])
        return result.stdout.strip()

    def get_commit_info(self, commit: str = "HEAD") -> CommitInfo:
        """Get metadata about a commit.

        Args:
            commit: Commit ref.

        Returns:
            CommitInfo dataclass with author, date, message.

        Raises:
            ValidationError: If commit format is invalid.
            StorageError: If commit cannot be found.
        """
        self._validate_git_ref(commit)

        # Get commit metadata in one call
        result = self._run_git(
            [
                "log",
                "-1",
                "--format=%H%n%an%n%ae%n%aI%n%s",
                commit,
            ]
        )

        lines = result.stdout.strip().split("\n")
        if len(lines) < 5:
            raise StorageError(
                f"Could not parse commit info for {commit}",
                "Verify the commit exists in the repository",
            )

        return CommitInfo(
            sha=lines[0],
            author_name=lines[1],
            author_email=lines[2],
            date=lines[3],
            message=lines[4],
        )

    def get_file_at_commit(
        self,
        path: str,
        commit: str = "HEAD",
    ) -> str | None:
        """Get file content at a specific commit.

        Args:
            path: File path relative to repo root.
            commit: Commit ref.

        Returns:
            File content, or None if file doesn't exist at commit.

        Raises:
            ValidationError: If path or commit format is invalid.
        """
        validate_path(path)
        self._validate_git_ref(commit)

        result = self._run_git(
            ["show", f"{commit}:{path}"],
            check=False,
        )

        if result.returncode != 0:
            return None

        return result.stdout

    def get_changed_files(self, commit: str = "HEAD") -> list[str]:
        """Get list of files changed in a commit.

        Args:
            commit: Commit ref.

        Returns:
            List of file paths that were modified in the commit.

        Raises:
            ValidationError: If commit format is invalid.
            StorageError: If commit cannot be found.
        """
        self._validate_git_ref(commit)
        result = self._run_git(["show", "--name-only", "--format=", commit])

        return [f for f in result.stdout.strip().split("\n") if f]

    # =========================================================================
    # Sync Configuration
    # =========================================================================

    def is_sync_configured(self) -> dict[str, bool]:
        """Check if Git notes sync is already configured.

        Checks for push/fetch refspecs, rewriteRef for rebases,
        and merge strategy configuration.

        Returns:
            Dict with configuration status:
            - push: True if push refspec is configured
            - fetch: True if fetch refspec is configured
            - rewrite: True if rewriteRef is configured
            - merge: True if merge strategy is configured
        """
        base = get_git_namespace()
        status = {"push": False, "fetch": False, "rewrite": False, "merge": False}

        # Check push refspec
        result = self._run_git(
            ["config", "--get-all", "remote.origin.push"],
            check=False,
        )
        if result.returncode == 0 and base in result.stdout:
            status["push"] = True

        # Check fetch refspec - detect both old and new patterns
        # Old pattern: refs/notes/mem/*:refs/notes/mem/* (problematic, direct to local)
        # New pattern: +refs/notes/mem/*:refs/notes/origin/mem/* (correct, tracking refs)
        result = self._run_git(
            ["config", "--get-all", "remote.origin.fetch"],
            check=False,
        )
        if result.returncode == 0:
            fetch_configs = result.stdout.strip()
            old_pattern = f"{base}/*:{base}/*"
            new_pattern = f"+{base}/*:refs/notes/origin/mem/*"
            # Consider configured if either pattern is present
            # Migration will handle converting old to new
            if old_pattern in fetch_configs or new_pattern in fetch_configs:
                status["fetch"] = True
            # Track which pattern for migration detection
            status["fetch_old"] = old_pattern in fetch_configs
            status["fetch_new"] = new_pattern in fetch_configs

        # Check rewriteRef
        result = self._run_git(
            ["config", "--get-all", "notes.rewriteRef"],
            check=False,
        )
        if result.returncode == 0 and base in result.stdout:
            status["rewrite"] = True

        # Check merge strategy
        result = self._run_git(
            ["config", "--get", "notes.mergeStrategy"],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            status["merge"] = True

        return status

    def configure_sync(self, *, force: bool = False) -> dict[str, bool]:
        """Configure Git to sync notes with remote (idempotent).

        Sets up push/fetch refspecs, rewriteRef for rebases, and merge strategy.
        Safe to call multiple times - only adds missing configuration.

        Args:
            force: If True, reconfigure even if already set.

        Returns:
            Dict indicating which components were configured (True = newly configured).
        """
        base = get_git_namespace()
        configured = {"push": False, "fetch": False, "rewrite": False, "merge": False}

        # Check existing configuration
        current = self.is_sync_configured()

        # Configure push for all mem/* refs
        if force or not current["push"]:
            result = self._run_git(
                [
                    "config",
                    "--add",
                    "remote.origin.push",
                    f"{base}/*:{base}/*",
                ],
                check=False,
            )
            configured["push"] = result.returncode == 0

        # Configure fetch for all mem/* refs using remote tracking refs pattern
        # This fetches to refs/notes/origin/mem/* (tracking refs) instead of
        # directly to refs/notes/mem/* (local refs) to avoid non-fast-forward
        # rejection when notes diverge between local and remote.
        # The + prefix forces updates to tracking refs (standard for tracking refs).
        if force or not current["fetch"]:
            result = self._run_git(
                [
                    "config",
                    "--add",
                    "remote.origin.fetch",
                    f"+{base}/*:refs/notes/origin/mem/*",
                ],
                check=False,
            )
            configured["fetch"] = result.returncode == 0

        # Configure rewriteRef for rebase support (preserves notes during rebase)
        if force or not current["rewrite"]:
            result = self._run_git(
                [
                    "config",
                    "--add",
                    "notes.rewriteRef",
                    f"{base}/*",
                ],
                check=False,
            )
            configured["rewrite"] = result.returncode == 0

        # Set merge strategy for notes
        if force or not current["merge"]:
            result = self._run_git(
                ["config", "notes.mergeStrategy", "cat_sort_uniq"],
                check=False,
            )
            configured["merge"] = result.returncode == 0

        return configured

    def _unset_fetch_config(self, pattern: str) -> bool:
        """Remove a fetch refspec pattern from git config.

        Uses --fixed-value on git 2.37+ for literal matching, falls back
        to iterating through values on older versions.

        Args:
            pattern: The exact fetch refspec pattern to remove.

        Returns:
            True if successfully removed or not found, False on error.
        """
        if git_supports_fixed_value():
            # Git 2.37+: Use --fixed-value for exact literal matching
            result = self._run_git(
                ["config", "--unset", "--fixed-value", "remote.origin.fetch", pattern],
                check=False,
            )
            # Return code 5 means pattern not found, which is fine
            return result.returncode in (0, 5)
        else:
            # Git < 2.37: Use regex to match the exact pattern
            # Escape special regex characters in the pattern for git config --unset
            escaped = re.escape(pattern)
            result = self._run_git(
                ["config", "--unset", "remote.origin.fetch", f"^{escaped}$"],
                check=False,
            )
            # Return code 5 means pattern not found, which is fine
            return result.returncode in (0, 5)

    def migrate_fetch_config(self) -> bool:
        """Migrate from direct fetch to tracking refs pattern.

        This method detects the old fetch refspec pattern that writes directly
        to local refs (which fails on divergence) and migrates to the new
        remote tracking refs pattern.

        Returns:
            True if migration occurred, False if already migrated or no config.

        Note:
            This method is idempotent - safe to call multiple times.
            Works with git 2.37+ (uses --fixed-value) and older versions
            (falls back to iterative removal).
        """
        base = get_git_namespace()
        old_pattern = f"{base}/*:{base}/*"
        new_pattern = f"+{base}/*:refs/notes/origin/mem/*"

        # Check current fetch configs
        result = self._run_git(
            ["config", "--get-all", "remote.origin.fetch"],
            check=False,
        )

        if result.returncode != 0:
            # No fetch config at all
            return False

        configs = result.stdout.strip().split("\n")

        # Check if old pattern exists
        has_old = any(old_pattern in c for c in configs)
        has_new = any(new_pattern in c for c in configs)

        if not has_old:
            # Already migrated or never had old config
            return False

        if has_new:
            # New config already exists, just remove old
            self._unset_fetch_config(old_pattern)
            return True

        # Remove old, add new
        self._unset_fetch_config(old_pattern)
        self._run_git(
            ["config", "--add", "remote.origin.fetch", new_pattern],
            check=False,
        )
        return True

    # =========================================================================
    # Remote Sync Operations
    # =========================================================================

    def fetch_notes_from_remote(
        self,
        namespaces: list[str] | None = None,
    ) -> dict[str, bool]:
        """Fetch notes from origin to tracking refs.

        Fetches notes from the remote to refs/notes/origin/mem/* tracking refs.
        This allows local notes to remain unchanged while remote state is captured.

        Args:
            namespaces: Specific namespaces to fetch, or None for all.

        Returns:
            Dict mapping namespace to fetch success.
        """
        base = get_git_namespace()
        ns_list = namespaces if namespaces is not None else list(NAMESPACES)
        results: dict[str, bool] = {}
        metrics = get_metrics()

        for ns in ns_list:
            try:
                local_ref = f"{base}/{ns}"
                tracking_ref = f"refs/notes/origin/mem/{ns}"
                result = self._run_git(
                    ["fetch", "origin", f"+{local_ref}:{tracking_ref}"],
                    check=False,
                )
                results[ns] = result.returncode == 0
            except Exception as e:
                logger.warning(
                    "Failed to fetch notes for namespace %s: %s",
                    ns,
                    e,
                )
                metrics.increment(
                    "silent_failures_total",
                    labels={"location": "git_ops.fetch_notes"},
                )
                results[ns] = False

        return results

    def merge_notes_from_tracking(
        self,
        namespace: str,
    ) -> bool:
        """Merge tracking refs into local notes.

        Uses Git's cat_sort_uniq merge strategy to combine notes from the
        tracking ref (remote state) into the local notes ref.

        Args:
            namespace: Namespace to merge.

        Returns:
            True if merge succeeded or no tracking ref exists, False on error.
        """
        if namespace not in NAMESPACES:
            raise INVALID_NAMESPACE_ERROR

        tracking_ref = f"refs/notes/origin/mem/{namespace}"

        # Check if tracking ref exists
        result = self._run_git(
            ["rev-parse", tracking_ref],
            check=False,
        )
        if result.returncode != 0:
            # No tracking ref to merge - not an error
            return True

        # Merge using configured cat_sort_uniq strategy
        result = self._run_git(
            [
                "notes",
                f"--ref=mem/{namespace}",
                "merge",
                "-s",
                "cat_sort_uniq",
                tracking_ref,
            ],
            check=False,
        )
        return result.returncode == 0

    def push_notes_to_remote(self) -> bool:
        """Push all notes to origin.

        Pushes local notes to the remote repository. Uses the configured
        push refspec (refs/notes/mem/*:refs/notes/mem/*).

        Returns:
            True if push succeeded, False otherwise.
        """
        base = get_git_namespace()
        result = self._run_git(
            ["push", "origin", f"{base}/*:{base}/*"],
            check=False,
        )
        return result.returncode == 0

    def sync_notes_with_remote(
        self,
        namespaces: list[str] | None = None,
        *,
        push: bool = True,
    ) -> dict[str, bool]:
        """Sync notes with remote using fetch → merge → push workflow.

        This is the primary method for synchronizing notes between local
        and remote repositories. It:
        1. Fetches remote notes to tracking refs
        2. Merges tracking refs into local notes using cat_sort_uniq
        3. Pushes merged notes back to remote (optional)

        Args:
            namespaces: Specific namespaces to sync, or None for all.
            push: Whether to push after merging.

        Returns:
            Dict mapping namespace to sync success.
        """
        ns_list = namespaces if namespaces is not None else list(NAMESPACES)
        results: dict[str, bool] = {}

        # Step 1: Fetch notes to tracking refs
        fetch_results = self.fetch_notes_from_remote(ns_list)

        # Step 2: Merge each namespace
        for ns in ns_list:
            if fetch_results.get(ns, False):
                results[ns] = self.merge_notes_from_tracking(ns)
            else:
                # Fetch failed - mark as failed but continue with other namespaces
                results[ns] = False

        # Step 3: Push (if requested and any merges succeeded)
        if push and any(results.values()):
            push_success = self.push_notes_to_remote()
            if not push_success:
                # Push failed - note that merges still succeeded locally
                # The notes are safe locally, just not pushed
                pass

        return results

    def ensure_sync_configured(self) -> bool:
        """Ensure git notes sync is configured for this repository.

        This is the primary entry point for auto-configuration. Call this
        at service initialization or session start to ensure notes will
        sync with push/pull operations.

        Returns:
            True if sync is fully configured (either already was or just configured).

        Note:
            This method is idempotent and safe to call repeatedly.
            It will only configure what's missing.
        """
        # Check if we're in a git repository with a remote
        if not self.is_git_repository():
            return False

        # Check for origin remote
        result = self._run_git(
            ["remote", "get-url", "origin"],
            check=False,
        )
        if result.returncode != 0:
            # No origin remote - can't configure sync
            return False

        # Check current configuration
        status = self.is_sync_configured()

        # If already fully configured, nothing to do
        if all(status.get(k, False) for k in SYNC_CORE_KEYS):
            return True

        # Configure missing parts
        self.configure_sync()

        # Verify configuration
        final_status = self.is_sync_configured()
        return all(final_status.get(k, False) for k in SYNC_CORE_KEYS)

    # =========================================================================
    # Repository Information
    # =========================================================================

    def is_git_repository(self) -> bool:
        """Check if the path is inside a git repository.

        Returns:
            True if path is in a git repository, False otherwise.
        """
        result = self._run_git(
            ["rev-parse", "--git-dir"],
            check=False,
        )
        return result.returncode == 0

    def get_repository_root(self) -> Path | None:
        """Get the root directory of the git repository.

        Returns:
            Path to repository root, or None if not in a repository.
        """
        result = self._run_git(
            ["rev-parse", "--show-toplevel"],
            check=False,
        )
        if result.returncode != 0:
            return None
        return Path(result.stdout.strip())

    def has_commits(self) -> bool:
        """Check if the repository has any commits.

        Returns:
            True if repository has at least one commit.
        """
        result = self._run_git(
            ["rev-parse", "HEAD"],
            check=False,
        )
        return result.returncode == 0
