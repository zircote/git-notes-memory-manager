"""Domain term extraction from file paths.

This module provides utilities for extracting searchable domain terms from
file paths. It's used by the PostToolUse hook to find related memories
when editing files.

The extraction process:
1. Parse path into directory components and filename
2. Filter out common/uninformative directories (src, lib, tests, etc.)
3. Split filename on separators (_, -, .)
4. Filter out short terms (<3 chars)
5. Return top N terms for search

Example:
    >>> extract_domain_terms("src/auth/jwt_handler.py")
    ["auth", "jwt", "handler"]
    >>> extract_domain_terms("tests/test_database.py")
    ["database"]
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["extract_domain_terms", "DomainExtractor"]

# Directories to skip when extracting domain terms
# These are common structural directories that don't indicate domain
SKIP_DIRECTORIES: frozenset[str] = frozenset(
    {
        # Common source directories
        "src",
        "lib",
        "libs",
        "source",
        "sources",
        # Test directories
        "test",
        "tests",
        "spec",
        "specs",
        "test_",
        "__tests__",
        # App structure directories
        "app",
        "apps",
        "core",
        "internal",
        "pkg",
        "packages",
        # Python-specific
        "__pycache__",
        ".venv",
        "venv",
        "env",
        # Build directories
        "build",
        "dist",
        "out",
        "target",
        # Config directories
        "config",
        "configs",
        "settings",
        # Hidden directories
        ".git",
        ".github",
        ".vscode",
        ".idea",
        # Node/JS specific
        "node_modules",
        "__mocks__",
        # Documentation
        "docs",
        "doc",
        # Assets
        "static",
        "assets",
        "public",
        # Common structural
        "bin",
        "scripts",
        "tools",
        "utils",
        "helpers",
        "common",
        "shared",
    }
)

# Minimum length for a term to be considered useful
MIN_TERM_LENGTH = 3

# Maximum number of terms to return
MAX_TERMS = 5

# Pattern to split filenames into terms
_SPLIT_PATTERN = re.compile(r"[_\-./]")


class DomainExtractor:
    """Extracts searchable domain terms from file paths.

    This class provides methods to extract meaningful domain terms from
    file paths for use in semantic search queries.

    Example::

        extractor = DomainExtractor()
        terms = extractor.extract("src/auth/jwt_handler.py")
        # ["auth", "jwt", "handler"]

    Attributes:
        skip_directories: Set of directory names to skip.
        min_term_length: Minimum length for included terms.
        max_terms: Maximum number of terms to return.
    """

    def __init__(
        self,
        *,
        skip_directories: frozenset[str] | None = None,
        min_term_length: int = MIN_TERM_LENGTH,
        max_terms: int = MAX_TERMS,
    ) -> None:
        """Initialize the domain extractor.

        Args:
            skip_directories: Custom set of directories to skip.
                Defaults to SKIP_DIRECTORIES.
            min_term_length: Minimum term length to include. Default 3.
            max_terms: Maximum terms to return. Default 5.
        """
        self.skip_directories = skip_directories or SKIP_DIRECTORIES
        self.min_term_length = min_term_length
        self.max_terms = max_terms

    def extract(self, file_path: str) -> list[str]:
        """Extract domain terms from a file path.

        Args:
            file_path: Absolute or relative file path to extract terms from.

        Returns:
            List of domain terms (lowercase), limited to max_terms.
            Empty list if no useful terms can be extracted.

        Example::

            extractor = DomainExtractor()

            # Extracts directory and filename components
            extractor.extract("src/auth/jwt_handler.py")
            # ["auth", "jwt", "handler"]

            # Filters test directory, extracts from filename
            extractor.extract("tests/test_database.py")
            # ["database"]

            # Handles nested paths
            extractor.extract("services/user/profile/avatar_service.py")
            # ["user", "profile", "avatar", "service"]
        """
        if not file_path:
            return []

        path = Path(file_path)
        terms: list[str] = []

        # Extract terms from directory components
        for part in path.parts[:-1]:  # Exclude filename
            part_lower = part.lower()
            if self._is_useful_directory(part_lower):
                terms.append(part_lower)

        # Extract terms from filename
        filename_terms = self._extract_from_filename(path.stem)
        terms.extend(filename_terms)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_terms: list[str] = []
        for term in terms:
            if term not in seen:
                seen.add(term)
                unique_terms.append(term)

        return unique_terms[: self.max_terms]

    def _is_useful_directory(self, directory: str) -> bool:
        """Check if a directory name is useful for domain extraction.

        Args:
            directory: Directory name (lowercase).

        Returns:
            True if the directory should be included as a term.
        """
        # Skip empty or hidden
        if not directory or directory.startswith("."):
            return False

        # Skip known uninformative directories
        if directory in self.skip_directories:
            return False

        # Skip very short names
        return len(directory) >= self.min_term_length

    def _extract_from_filename(self, stem: str) -> list[str]:
        """Extract terms from a filename stem.

        Args:
            stem: Filename without extension.

        Returns:
            List of terms extracted from the filename.
        """
        if not stem:
            return []

        # Split on common separators
        parts = _SPLIT_PATTERN.split(stem.lower())

        terms: list[str] = []
        for part in parts:
            # Skip common prefixes
            if part in ("test", "spec", "mock", "stub", "fake"):
                continue

            # Include if long enough
            if len(part) >= self.min_term_length:
                terms.append(part)

        return terms


# Module-level singleton for performance (avoid creating instance per call)
_default_extractor: DomainExtractor | None = None


def _get_default_extractor() -> DomainExtractor:
    """Get or create the default DomainExtractor singleton.

    Returns:
        Cached DomainExtractor instance.
    """
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = DomainExtractor()
    return _default_extractor


def extract_domain_terms(file_path: str) -> list[str]:
    """Extract searchable domain terms from a file path.

    This is a convenience function that uses a cached DomainExtractor
    with default settings for better performance.

    Args:
        file_path: Absolute or relative file path.

    Returns:
        List of domain terms (max 5).

    Example::

        terms = extract_domain_terms("src/auth/jwt_handler.py")
        # ["auth", "jwt", "handler"]

        terms = extract_domain_terms("tests/test_database.py")
        # ["database"]
    """
    return _get_default_extractor().extract(file_path)
