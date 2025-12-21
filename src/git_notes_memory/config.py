"""Configuration system for the memory capture plugin.

This module provides all configuration constants, path resolution helpers,
and environment variable overrides for the memory system.

Environment Variables:
    MEMORY_PLUGIN_DATA_DIR: Override the XDG data directory
    MEMORY_PLUGIN_GIT_NAMESPACE: Override the git notes namespace
    MEMORY_PLUGIN_EMBEDDING_MODEL: Override the embedding model name
    MEMORY_PLUGIN_AUTO_CAPTURE: Enable/disable auto-capture (1/true/yes/on)

XDG Compliance:
    By default, data is stored in $XDG_DATA_HOME/memory-plugin/ which
    defaults to ~/.local/share/memory-plugin/ if XDG_DATA_HOME is not set.

.env File Support:
    Place a .env file in the project root or working directory to set
    environment variables. See .env.example for available options.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file early, before any environment variable access
# This looks for .env in the current directory and parent directories
load_dotenv()

__all__ = [
    # Namespaces
    "NAMESPACES",
    # Git Configuration
    "DEFAULT_GIT_NAMESPACE",
    "get_git_namespace",
    # Storage Paths
    "INDEX_DB_NAME",
    "MODELS_DIR_NAME",
    "LOCK_FILE_NAME",
    "MEMORY_DIR_NAME",
    "find_git_root",
    "NotInGitRepositoryError",
    "get_data_path",
    "get_index_path",
    "get_project_index_path",
    "get_project_identifier",
    "get_project_memory_dir",
    "get_models_path",
    "get_lock_path",
    # Embedding Configuration
    "DEFAULT_EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "get_embedding_model",
    # Limits and Thresholds
    "MAX_CONTENT_BYTES",
    "MAX_SUMMARY_CHARS",
    "MAX_HYDRATION_FILES",
    "MAX_FILE_SIZE",
    # Performance Timeouts
    "SEARCH_TIMEOUT_MS",
    "CAPTURE_TIMEOUT_MS",
    "REINDEX_TIMEOUT_MS",
    "LOCK_TIMEOUT_SECONDS",
    # Cache Settings
    "CACHE_TTL_SECONDS",
    "CACHE_MAX_ENTRIES",
    # Lifecycle Settings
    "DECAY_HALF_LIFE_DAYS",
    "SECONDS_PER_DAY",
    # Search Defaults
    "DEFAULT_RECALL_LIMIT",
    "DEFAULT_SEARCH_LIMIT",
    "MAX_RECALL_LIMIT",
    "MAX_PROACTIVE_SUGGESTIONS",
    # Note Schema
    "NOTE_REQUIRED_FIELDS",
    "NOTE_OPTIONAL_FIELDS",
    # Auto-capture
    "is_auto_capture_enabled",
    "AUTO_CAPTURE_NAMESPACES",
    # Review Categories
    "REVIEW_CATEGORIES",
    "REVIEW_SEVERITIES",
    # Retrospective
    "RETROSPECTIVE_OUTCOMES",
    # Hook Configuration
    "HOOK_DEFAULT_TIMEOUT",
    "HOOK_SESSION_START_TIMEOUT",
    "HOOK_USER_PROMPT_TIMEOUT",
    "HOOK_STOP_TIMEOUT",
    "HOOK_BUDGET_SIMPLE",
    "HOOK_BUDGET_MEDIUM",
    "HOOK_BUDGET_COMPLEX",
    "HOOK_BUDGET_FULL",
    "HOOK_MIN_CONFIDENCE",
    "HOOK_AUTO_THRESHOLD",
    "HOOK_NOVELTY_THRESHOLD",
    "HOOK_SIGNAL_NAMESPACES",
]


# =============================================================================
# Memory Namespaces
# =============================================================================

NAMESPACES: frozenset[str] = frozenset(
    {
        "inception",  # Problem statements, scope, success criteria
        "elicitation",  # Requirements clarifications, constraints
        "research",  # External findings, technology evaluations
        "decisions",  # Architecture Decision Records
        "progress",  # Task completions, milestones
        "blockers",  # Obstacles and resolutions
        "reviews",  # Code review findings
        "learnings",  # Technical insights, patterns
        "retrospective",  # Post-mortems
        "patterns",  # Cross-spec generalizations
    }
)

# Namespaces that support auto-capture
AUTO_CAPTURE_NAMESPACES: frozenset[str] = frozenset(
    {
        "inception",
        "elicitation",
        "research",
        "decisions",
        "progress",
        "blockers",
        "learnings",
        "retrospective",
        "patterns",
    }
)


# =============================================================================
# Git Configuration
# =============================================================================

DEFAULT_GIT_NAMESPACE = "refs/notes/mem"


def get_git_namespace() -> str:
    """Get the git notes namespace, with environment override.

    Returns:
        The git notes namespace (e.g., 'refs/notes/mem').
    """
    return os.environ.get("MEMORY_PLUGIN_GIT_NAMESPACE", DEFAULT_GIT_NAMESPACE)


# =============================================================================
# Storage Paths
# =============================================================================

INDEX_DB_NAME = "index.db"
MODELS_DIR_NAME = "models"
LOCK_FILE_NAME = ".capture.lock"


def get_data_path() -> Path:
    """Get the XDG-compliant data directory.

    Environment override: MEMORY_PLUGIN_DATA_DIR

    Returns:
        Path to data directory (default: ~/.local/share/memory-plugin/).
    """
    override = os.environ.get("MEMORY_PLUGIN_DATA_DIR")
    if override:
        return Path(override).expanduser()

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        base = Path(xdg_data_home)
    else:
        base = Path.home() / ".local" / "share"

    return base / "memory-plugin"


def get_index_path() -> Path:
    """Get the path to the global SQLite index database.

    Note: For per-project isolation, use get_project_index_path() instead.

    Returns:
        Path to index.db file.
    """
    return get_data_path() / INDEX_DB_NAME


MEMORY_DIR_NAME = ".memory"


class NotInGitRepositoryError(Exception):
    """Raised when an operation requires a git repository but none is found."""

    pass


def find_git_root(start_path: Path | str | None = None) -> Path:
    """Find the git repository root from a starting path.

    Walks up the directory tree looking for a .git directory. The .memory
    folder MUST always be at the git root, parallel to .git.

    Args:
        start_path: Starting path to search from. Defaults to current directory.

    Returns:
        Path to the git repository root.

    Raises:
        NotInGitRepositoryError: If not inside a git repository.

    Example::

        git_root = find_git_root()
        # Returns /path/to/repo even if cwd is /path/to/repo/src/deep/subdir
    """
    if start_path is None:
        current = Path.cwd()
    else:
        current = Path(start_path).resolve()

    # Walk up looking for .git directory
    for _ in range(100):  # Safety limit on depth
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            # Reached filesystem root without finding .git
            break
        current = parent

    raise NotInGitRepositoryError(
        f"Not inside a git repository: {start_path or Path.cwd()}. "
        "The .memory folder must be at the git root parallel to .git."
    )


# Cache for project identifiers to avoid repeated file I/O
_project_id_cache: dict[str, str] = {}


def get_project_identifier(repo_path: Path | str | None = None) -> str:
    """Get a unique identifier for a repository.

    Uses the repository's git remote URL if available, otherwise falls back
    to the canonical git root path. The identifier is a short hash for
    filesystem safety.

    This function always resolves to the git root before computing the
    identifier, ensuring consistent IDs regardless of subdirectory.

    Results are cached to avoid repeated file I/O on hot paths.

    Args:
        repo_path: Path within the repository. If None, uses current directory.
                   The actual git root is discovered by walking up the tree.

    Returns:
        A short identifier string (e.g., "a1b2c3d4") unique to this repository.

    Raises:
        NotInGitRepositoryError: If not inside a git repository.
    """
    import hashlib
    import re

    # Always resolve to git root for consistent identification
    git_root = find_git_root(repo_path)

    # Check cache first for performance (use git root as cache key)
    cache_key = str(git_root)
    if cache_key in _project_id_cache:
        return _project_id_cache[cache_key]

    # Try to read remote URL from .git/config directly (no subprocess)
    identifier_source: str | None = None
    git_config = git_root / ".git" / "config"

    if git_config.exists():
        try:
            content = git_config.read_text(encoding="utf-8")
            # Match url = <value> under [remote "origin"] section
            match = re.search(
                r'\[remote\s+"origin"\][^\[]*url\s*=\s*(.+?)$',
                content,
                re.MULTILINE | re.IGNORECASE,
            )
            if match:
                identifier_source = match.group(1).strip()
        except OSError:
            # Git config file may not exist; fall back to path-based ID
            pass

    # Fall back to canonical git root path if git config not available
    if not identifier_source:
        identifier_source = str(git_root)

    # Create a short hash for filesystem-safe naming
    hash_digest = hashlib.sha256(identifier_source.encode()).hexdigest()[:12]

    # Cache the result
    _project_id_cache[cache_key] = hash_digest
    return hash_digest


def get_project_memory_dir(repo_path: Path | str | None = None) -> Path:
    """Get the path to the project's .memory directory.

    The .memory directory stores project-specific memory data including
    the SQLite index. This directory is ALWAYS placed at the git repository
    root, parallel to the .git folder, regardless of the current working
    directory.

    ARCHITECTURAL INVARIANT: .memory MUST be at git root parallel to .git.
    This ensures consistent memory storage even when working from subdirectories.

    Args:
        repo_path: Path within the repository. If None, uses current directory.
                   The actual git root is discovered by walking up the tree.

    Returns:
        Path to .memory/ directory at the git repository root.

    Raises:
        NotInGitRepositoryError: If not inside a git repository.

    Example::

        # From /path/to/repo/src/deep/subdir
        get_project_memory_dir()  # Returns /path/to/repo/.memory
    """
    git_root = find_git_root(repo_path)
    return git_root / MEMORY_DIR_NAME


def get_project_index_path(repo_path: Path | str | None = None) -> Path:
    """Get the path to a project-specific SQLite index database.

    Each repository gets its own index database stored in <git-root>/.memory/index.db.
    This ensures sync/reindex operations only affect the current project.
    The .memory directory should be added to .gitignore.

    ARCHITECTURAL INVARIANT: The database is ALWAYS at the git root, parallel
    to .git, regardless of the current working directory.

    Args:
        repo_path: Path within the repository. If None, uses current directory.
                   The actual git root is discovered by walking up the tree.

    Returns:
        Path to project-specific index.db file (e.g., <git-root>/.memory/index.db).

    Raises:
        NotInGitRepositoryError: If not inside a git repository.
    """
    return get_project_memory_dir(repo_path) / INDEX_DB_NAME


def get_models_path() -> Path:
    """Get the path to the embedding models directory.

    Returns:
        Path to models/ directory.
    """
    return get_data_path() / MODELS_DIR_NAME


def get_lock_path() -> Path:
    """Get the path to the capture lock file.

    Returns:
        Path to .capture.lock file.
    """
    return get_data_path() / LOCK_FILE_NAME


# =============================================================================
# Embedding Configuration
# =============================================================================

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384


def get_embedding_model() -> str:
    """Get the embedding model name, with environment override.

    Environment override: MEMORY_PLUGIN_EMBEDDING_MODEL

    Returns:
        The embedding model name.
    """
    return os.environ.get("MEMORY_PLUGIN_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


# =============================================================================
# Limits and Thresholds
# =============================================================================

# Content length limits (SEC-005 security requirement)
MAX_CONTENT_BYTES = 102400  # 100KB max content for capture
MAX_SUMMARY_CHARS = 100  # Max summary length

# Hydration limits (PERF-003 performance requirement)
MAX_HYDRATION_FILES = 20  # Max files to hydrate per memory
MAX_FILE_SIZE = 102400  # 100KB max per file


# =============================================================================
# Performance Timeouts
# =============================================================================

SEARCH_TIMEOUT_MS = 500  # 500ms target for search operations
CAPTURE_TIMEOUT_MS = 2000  # 2s target for capture operations
REINDEX_TIMEOUT_MS = 60000  # 60s target for full reindex
LOCK_TIMEOUT_SECONDS = 5  # Lock acquisition timeout


# =============================================================================
# Cache Settings
# =============================================================================

CACHE_TTL_SECONDS = 300.0  # 5 minutes cache lifetime
CACHE_MAX_ENTRIES = 100  # Maximum cached search results


# =============================================================================
# Lifecycle Settings
# =============================================================================

DECAY_HALF_LIFE_DAYS = 30  # Half-life for memory relevance decay
SECONDS_PER_DAY = 86400  # Constant for time calculations


# =============================================================================
# Search Defaults
# =============================================================================

DEFAULT_RECALL_LIMIT = 10  # Default number of results to return
DEFAULT_SEARCH_LIMIT = 10  # Default search limit
MAX_RECALL_LIMIT = 100  # Maximum allowed recall limit
MAX_PROACTIVE_SUGGESTIONS = 3  # Max proactive recall suggestions

# Token estimation for context size (rough average: ~4 chars per token)
TOKENS_PER_CHAR = 0.25  # Conservative estimate for token counting


# =============================================================================
# Note Schema
# =============================================================================

NOTE_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {"type", "spec", "timestamp", "summary"}
)
NOTE_OPTIONAL_FIELDS: frozenset[str] = frozenset(
    {"phase", "tags", "relates_to", "status"}
)


# =============================================================================
# Auto-capture Configuration
# =============================================================================


def is_auto_capture_enabled() -> bool:
    """Check if auto-capture is enabled via environment variable.

    Environment variable: MEMORY_PLUGIN_AUTO_CAPTURE
    Accepts: 1, true, yes, on (case-insensitive)

    Returns:
        True if auto-capture is enabled.
    """
    value = os.environ.get("MEMORY_PLUGIN_AUTO_CAPTURE", "").lower()
    return value in {"1", "true", "yes", "on"}


# =============================================================================
# Review Finding Categories
# =============================================================================

REVIEW_CATEGORIES: frozenset[str] = frozenset(
    {
        "security",
        "performance",
        "architecture",
        "quality",
        "tests",
        "documentation",
    }
)

REVIEW_SEVERITIES: frozenset[str] = frozenset(
    {
        "critical",
        "high",
        "medium",
        "low",
    }
)


# =============================================================================
# Retrospective Configuration
# =============================================================================

RETROSPECTIVE_OUTCOMES: frozenset[str] = frozenset(
    {
        "success",
        "partial",
        "failed",
        "abandoned",
    }
)


# =============================================================================
# Hook Configuration
# =============================================================================

# Default token budgets for context injection (PERF-004 requirement)
HOOK_DEFAULT_TIMEOUT = 30  # Default hook timeout in seconds
HOOK_SESSION_START_TIMEOUT = 5  # SessionStart hook timeout
HOOK_USER_PROMPT_TIMEOUT = 2  # UserPromptSubmit hook timeout
HOOK_STOP_TIMEOUT = 5  # Stop hook timeout

# Token budget tiers (from architecture spec)
HOOK_BUDGET_SIMPLE = 500  # Simple projects
HOOK_BUDGET_MEDIUM = 1000  # Medium complexity projects
HOOK_BUDGET_COMPLEX = 2000  # Complex projects
HOOK_BUDGET_FULL = 3000  # Full/unlimited budget

# Capture detection thresholds
HOOK_MIN_CONFIDENCE = 0.7  # Minimum confidence for SUGGEST action
HOOK_AUTO_THRESHOLD = 0.95  # Threshold for AUTO action
HOOK_NOVELTY_THRESHOLD = 0.3  # Minimum novelty score

# Hook namespaces for captured signals
HOOK_SIGNAL_NAMESPACES: frozenset[str] = frozenset(
    {
        "decisions",
        "learnings",
        "blockers",
        "solutions",  # Resolution signals map here
        "preferences",
        "notes",  # Explicit signals map here
    }
)
