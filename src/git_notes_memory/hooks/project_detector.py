"""Project detection for hook context.

This module provides utilities for detecting the current project and spec
from the working directory. It examines:
- Directory name and path
- CLAUDE.md for spec references
- Git repository name
- Package configuration files (pyproject.toml, package.json, etc.)

The detected project identifier is used for:
- Filtering relevant memories
- Semantic search queries
- Context scoping
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["detect_project", "ProjectInfo"]

logger = logging.getLogger(__name__)

# Cache for project detection results to avoid repeated file I/O
_project_cache: dict[str, ProjectInfo] = {}


@dataclass(frozen=True)
class ProjectInfo:
    """Information about the detected project.

    Attributes:
        name: Project name (usually directory or repo name).
        path: Absolute path to the project root.
        spec_id: Optional spec identifier if found.
        git_repo: Optional git repository name.
    """

    name: str
    path: str
    spec_id: str | None = None
    git_repo: str | None = None


def detect_project(cwd: str | Path) -> ProjectInfo:
    """Detect project information from the working directory.

    Examines the working directory to determine project identity:
    1. Looks for git repository root and name
    2. Scans CLAUDE.md for spec references
    3. Falls back to directory name

    Results are cached to avoid repeated file I/O on hot paths.

    Args:
        cwd: Current working directory path.

    Returns:
        ProjectInfo with detected name, path, and optional spec_id.

    Example::

        info = detect_project("/path/to/my-project")
        print(info.name)  # "my-project"
        print(info.spec_id)  # "SPEC-2025-12-19-001" or None
    """
    path = Path(cwd).resolve()

    # Check cache first for performance
    cache_key = str(path)
    if cache_key in _project_cache:
        return _project_cache[cache_key]

    logger.debug("Detecting project from: %s", path)

    # Find git repository root if present
    git_root = _find_git_root(path)
    git_repo = _get_git_repo_name(git_root) if git_root else None

    # Use git root as project root if found, otherwise use cwd
    project_root = git_root or path

    # Get project name from directory
    project_name = _detect_project_name(project_root)

    # Try to extract spec_id from CLAUDE.md or related files
    spec_id = _extract_spec_id(project_root)

    info = ProjectInfo(
        name=project_name,
        path=str(project_root),
        spec_id=spec_id,
        git_repo=git_repo,
    )

    # Cache the result
    _project_cache[cache_key] = info

    logger.debug("Detected project: %s", info)
    return info


def _find_git_root(path: Path) -> Path | None:
    """Find the git repository root from a path.

    Walks up the directory tree looking for a .git directory.

    Args:
        path: Starting path to search from.

    Returns:
        Path to git root, or None if not in a git repository.
    """
    current = path
    for _ in range(50):  # Safety limit on depth
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent
    return None


def _get_git_repo_name(git_root: Path) -> str | None:
    """Get the git repository name from the .git/config.

    Attempts to parse the origin remote URL to extract repo name.

    Args:
        git_root: Path to the git repository root.

    Returns:
        Repository name, or None if not determinable.
    """
    config_path = git_root / ".git" / "config"
    if not config_path.is_file():
        return None

    try:
        content = config_path.read_text(encoding="utf-8")
        # Look for origin URL
        # Match patterns like:
        #   url = git@github.com:user/repo.git
        #   url = https://github.com/user/repo.git
        match = re.search(
            r"url\s*=\s*.*[/:]([^/]+?)(?:\.git)?\s*$", content, re.MULTILINE
        )
        if match:
            return match.group(1)
    except OSError:
        pass
    return None


def _detect_project_name(project_root: Path) -> str:
    """Detect project name from configuration files or directory.

    Checks in order:
    1. pyproject.toml [project] name
    2. package.json name
    3. Directory name

    Args:
        project_root: Path to the project root directory.

    Returns:
        Detected project name.
    """
    # Try pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if pyproject.is_file():
        name = _extract_pyproject_name(pyproject)
        if name:
            return name

    # Try package.json
    package_json = project_root / "package.json"
    if package_json.is_file():
        name = _extract_package_json_name(package_json)
        if name:
            return name

    # Fall back to directory name
    return project_root.name


def _extract_pyproject_name(pyproject_path: Path) -> str | None:
    """Extract project name from pyproject.toml.

    Args:
        pyproject_path: Path to pyproject.toml file.

    Returns:
        Project name or None if not found.
    """
    try:
        content = pyproject_path.read_text(encoding="utf-8")
        # Simple pattern matching for [project] name = "..."
        # More robust parsing would use tomllib, but we keep dependencies minimal
        match = re.search(
            r'^\[project\].*?^name\s*=\s*["\']([^"\']+)["\']',
            content,
            re.MULTILINE | re.DOTALL,
        )
        if match:
            return match.group(1)
    except OSError:
        pass
    return None


def _extract_package_json_name(package_json_path: Path) -> str | None:
    """Extract project name from package.json.

    Args:
        package_json_path: Path to package.json file.

    Returns:
        Project name or None if not found.
    """
    import json

    try:
        content = package_json_path.read_text(encoding="utf-8")
        data = json.loads(content)
        name = data.get("name")
        if isinstance(name, str) and name:
            # Handle scoped packages like @org/package
            if name.startswith("@") and "/" in name:
                parts = name.split("/")
                return str(parts[-1])
            return str(name)
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _extract_spec_id(project_root: Path) -> str | None:
    """Extract spec ID from CLAUDE.md or related files.

    Looks for spec ID patterns in:
    1. CLAUDE.md in project root
    2. docs/spec/active/*/PROGRESS.md files

    Spec ID patterns:
    - SPEC-YYYY-MM-DD-NNN format
    - project_id: ... in YAML frontmatter

    Args:
        project_root: Path to the project root directory.

    Returns:
        Spec ID if found, None otherwise.
    """
    # Check CLAUDE.md for spec reference
    claude_md = project_root / "CLAUDE.md"
    if claude_md.is_file():
        spec_id = _extract_spec_from_claude_md(claude_md)
        if spec_id:
            return spec_id

    # Check for active spec in docs/spec/active/
    spec_dir = project_root / "docs" / "spec" / "active"
    if spec_dir.is_dir():
        spec_id = _find_active_spec(spec_dir)
        if spec_id:
            return spec_id

    return None


def _extract_spec_from_claude_md(claude_md_path: Path) -> str | None:
    """Extract spec ID from CLAUDE.md file.

    Looks for patterns like:
    - spec_id: SPEC-2025-12-19-001
    - project_id: SPEC-2025-12-19-001
    - Active Spec: SPEC-2025-12-19-001

    Args:
        claude_md_path: Path to CLAUDE.md file.

    Returns:
        Spec ID if found, None otherwise.
    """
    try:
        content = claude_md_path.read_text(encoding="utf-8")
        # Look for spec ID patterns
        patterns = [
            r'(?:spec_id|project_id):\s*["\']?(SPEC-\d{4}-\d{2}-\d{2}-\d+)["\']?',
            r'Active\s+Spec:\s*["\']?(SPEC-\d{4}-\d{2}-\d{2}-\d+)["\']?',
            r"\b(SPEC-\d{4}-\d{2}-\d{2}-\d+)\b",  # Any SPEC-... pattern
        ]
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                return match.group(1)
    except OSError:
        pass
    return None


def _find_active_spec(spec_dir: Path) -> str | None:
    """Find active spec ID from docs/spec/active/ directory.

    Looks for PROGRESS.md files with project_id in frontmatter.

    Args:
        spec_dir: Path to docs/spec/active/ directory.

    Returns:
        Most recent spec ID if found, None otherwise.
    """
    try:
        # Look for PROGRESS.md files in subdirectories
        progress_files = list(spec_dir.glob("*/PROGRESS.md"))
        if not progress_files:
            return None

        # Sort by directory name (which typically includes date)
        progress_files.sort(key=lambda p: p.parent.name, reverse=True)

        # Extract spec ID from the most recent one
        for progress_file in progress_files:
            content = progress_file.read_text(encoding="utf-8")
            match = re.search(
                r'project_id:\s*["\']?(SPEC-\d{4}-\d{2}-\d{2}-\d+)["\']?',
                content,
            )
            if match:
                return match.group(1)
    except OSError:
        pass
    return None
