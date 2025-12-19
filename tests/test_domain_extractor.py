"""Tests for git_notes_memory.hooks.domain_extractor module.

Tests the domain term extraction from file paths including:
- DomainExtractor class
- extract_domain_terms convenience function
- Directory filtering
- Filename parsing
"""

from __future__ import annotations

import pytest

from git_notes_memory.hooks.domain_extractor import (
    MAX_TERMS,
    MIN_TERM_LENGTH,
    SKIP_DIRECTORIES,
    DomainExtractor,
    extract_domain_terms,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def domain_extractor() -> DomainExtractor:
    """Create a DomainExtractor instance with defaults."""
    return DomainExtractor()


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Test module constants."""

    def test_min_term_length(self) -> None:
        """Test minimum term length is 3."""
        assert MIN_TERM_LENGTH == 3

    def test_max_terms(self) -> None:
        """Test maximum terms is 5."""
        assert MAX_TERMS == 5

    def test_skip_directories_contains_common(self) -> None:
        """Test skip_directories contains common structural dirs."""
        assert "src" in SKIP_DIRECTORIES
        assert "lib" in SKIP_DIRECTORIES
        assert "tests" in SKIP_DIRECTORIES
        assert "node_modules" in SKIP_DIRECTORIES
        assert "__pycache__" in SKIP_DIRECTORIES

    def test_skip_directories_is_frozenset(self) -> None:
        """Test skip_directories is immutable."""
        assert isinstance(SKIP_DIRECTORIES, frozenset)


# =============================================================================
# Basic Extraction Tests
# =============================================================================


class TestBasicExtraction:
    """Test basic domain term extraction."""

    def test_extract_from_simple_path(self, domain_extractor: DomainExtractor) -> None:
        """Test extraction from simple path."""
        terms = domain_extractor.extract("auth/jwt_handler.py")
        assert "auth" in terms
        assert "jwt" in terms
        assert "handler" in terms

    def test_extract_from_path_with_src(
        self, domain_extractor: DomainExtractor
    ) -> None:
        """Test that src directory is skipped."""
        terms = domain_extractor.extract("src/auth/jwt_handler.py")
        assert "src" not in terms
        assert "auth" in terms
        assert "jwt" in terms

    def test_extract_from_tests_path(self, domain_extractor: DomainExtractor) -> None:
        """Test that tests directory is skipped."""
        terms = domain_extractor.extract("tests/test_database.py")
        assert "tests" not in terms
        assert "test" not in terms  # test prefix skipped
        assert "database" in terms

    def test_extract_preserves_order(self, domain_extractor: DomainExtractor) -> None:
        """Test that terms are in path order (dirs first, then filename)."""
        terms = domain_extractor.extract("services/user/profile.py")
        # Directories come before filename parts
        assert terms.index("services") < terms.index("profile")
        assert terms.index("user") < terms.index("profile")

    def test_extract_returns_lowercase(self, domain_extractor: DomainExtractor) -> None:
        """Test that all terms are lowercase."""
        terms = domain_extractor.extract("Services/User/JWT_Handler.py")
        for term in terms:
            assert term == term.lower()


# =============================================================================
# Directory Filtering Tests
# =============================================================================


class TestDirectoryFiltering:
    """Test directory filtering logic."""

    @pytest.mark.parametrize(
        "skip_dir",
        [
            "src",
            "lib",
            "libs",
            "test",
            "tests",
            "app",
            "core",
            "pkg",
            "build",
            "dist",
            "node_modules",
            "__pycache__",
            ".venv",
            ".git",
            "docs",
            "static",
            "assets",
            "utils",
            "helpers",
            "common",
        ],
    )
    def test_skip_directories_filtered(
        self, domain_extractor: DomainExtractor, skip_dir: str
    ) -> None:
        """Test that common directories are filtered out."""
        terms = domain_extractor.extract(f"{skip_dir}/important/handler.py")
        assert skip_dir not in terms

    def test_hidden_directories_filtered(
        self, domain_extractor: DomainExtractor
    ) -> None:
        """Test that hidden directories are filtered."""
        terms = domain_extractor.extract(".hidden/auth/handler.py")
        assert ".hidden" not in terms
        assert "auth" in terms

    def test_short_directories_filtered(
        self, domain_extractor: DomainExtractor
    ) -> None:
        """Test that short directory names (<3 chars) are filtered."""
        terms = domain_extractor.extract("db/api/authentication.py")
        assert "db" not in terms  # 2 chars
        assert "api" in terms  # 3 chars
        assert "authentication" in terms


# =============================================================================
# Filename Parsing Tests
# =============================================================================


class TestFilenameParsing:
    """Test filename term extraction."""

    def test_underscore_split(self, domain_extractor: DomainExtractor) -> None:
        """Test splitting on underscores."""
        terms = domain_extractor.extract("jwt_token_handler.py")
        assert "jwt" in terms
        assert "token" in terms
        assert "handler" in terms

    def test_hyphen_split(self, domain_extractor: DomainExtractor) -> None:
        """Test splitting on hyphens."""
        terms = domain_extractor.extract("user-profile-service.py")
        assert "user" in terms
        assert "profile" in terms
        assert "service" in terms

    def test_dot_split(self, domain_extractor: DomainExtractor) -> None:
        """Test splitting on dots (excluding extension)."""
        terms = domain_extractor.extract("user.profile.service.py")
        assert "user" in terms
        assert "profile" in terms
        assert "service" in terms

    def test_test_prefix_filtered(self, domain_extractor: DomainExtractor) -> None:
        """Test that test prefix is filtered from filenames."""
        terms = domain_extractor.extract("test_database.py")
        assert "test" not in terms
        assert "database" in terms

    @pytest.mark.parametrize("prefix", ["test", "spec", "mock", "stub", "fake"])
    def test_common_prefixes_filtered(
        self, domain_extractor: DomainExtractor, prefix: str
    ) -> None:
        """Test that common test prefixes are filtered."""
        terms = domain_extractor.extract(f"{prefix}_handler.py")
        assert prefix not in terms
        assert "handler" in terms

    def test_short_terms_filtered(self, domain_extractor: DomainExtractor) -> None:
        """Test that short terms (<3 chars) are filtered."""
        terms = domain_extractor.extract("a_db_handler.py")
        assert "a" not in terms
        assert "db" not in terms  # 2 chars
        assert "handler" in terms


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_path(self, domain_extractor: DomainExtractor) -> None:
        """Test empty path returns empty list."""
        assert domain_extractor.extract("") == []

    def test_single_file(self, domain_extractor: DomainExtractor) -> None:
        """Test single file without directory."""
        terms = domain_extractor.extract("handler.py")
        assert terms == ["handler"]

    def test_deeply_nested_path(self, domain_extractor: DomainExtractor) -> None:
        """Test deeply nested path."""
        terms = domain_extractor.extract(
            "services/auth/jwt/validation/token_validator.py"
        )
        assert "services" in terms
        assert "auth" in terms
        assert "jwt" in terms
        assert "validation" in terms
        assert "token" in terms

    def test_max_terms_limit(self, domain_extractor: DomainExtractor) -> None:
        """Test that max_terms limit is respected."""
        # Create a path with many components
        terms = domain_extractor.extract(
            "services/auth/jwt/validation/middleware/helpers/token_validator_utility.py"
        )
        assert len(terms) <= MAX_TERMS

    def test_absolute_path(self, domain_extractor: DomainExtractor) -> None:
        """Test absolute path handling."""
        terms = domain_extractor.extract("/home/user/project/src/auth/handler.py")
        assert "auth" in terms
        assert "handler" in terms
        # /home, user, project, src should all be filtered

    def test_windows_path(self, domain_extractor: DomainExtractor) -> None:
        """Test Windows-style path handling."""
        # Path library normalizes separators
        terms = domain_extractor.extract("C:/Users/dev/project/auth/handler.py")
        assert "auth" in terms
        assert "handler" in terms

    def test_duplicate_terms_deduplicated(
        self, domain_extractor: DomainExtractor
    ) -> None:
        """Test that duplicate terms are removed."""
        terms = domain_extractor.extract("auth/auth_handler.py")
        # Should only have one 'auth'
        assert terms.count("auth") == 1


# =============================================================================
# Custom Configuration Tests
# =============================================================================


class TestCustomConfiguration:
    """Test DomainExtractor with custom configuration."""

    def test_custom_skip_directories(self) -> None:
        """Test custom skip_directories."""
        custom_skip = frozenset({"custom", "skip"})
        extractor = DomainExtractor(skip_directories=custom_skip)
        terms = extractor.extract("custom/auth/handler.py")
        assert "custom" not in terms
        assert "auth" in terms

    def test_custom_min_term_length(self) -> None:
        """Test custom min_term_length."""
        extractor = DomainExtractor(min_term_length=5)
        terms = extractor.extract("auth/jwt/handler.py")
        assert "auth" not in terms  # 4 chars
        assert "jwt" not in terms  # 3 chars
        assert "handler" in terms  # 7 chars

    def test_custom_max_terms(self) -> None:
        """Test custom max_terms."""
        extractor = DomainExtractor(max_terms=2)
        terms = extractor.extract("services/auth/jwt/handler.py")
        assert len(terms) == 2


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunction:
    """Test the module-level convenience function."""

    def test_extract_domain_terms_basic(self) -> None:
        """Test convenience function works."""
        terms = extract_domain_terms("src/auth/jwt_handler.py")
        assert "auth" in terms
        assert "jwt" in terms
        assert "handler" in terms

    def test_extract_domain_terms_empty(self) -> None:
        """Test convenience function with empty path."""
        assert extract_domain_terms("") == []

    def test_extract_domain_terms_returns_list(self) -> None:
        """Test convenience function returns list."""
        result = extract_domain_terms("auth/handler.py")
        assert isinstance(result, list)


# =============================================================================
# Real-World Path Tests
# =============================================================================


class TestRealWorldPaths:
    """Test with realistic file paths."""

    def test_python_project_path(self, domain_extractor: DomainExtractor) -> None:
        """Test typical Python project path."""
        terms = domain_extractor.extract(
            "src/git_notes_memory/hooks/session_start_handler.py"
        )
        assert "git_notes_memory" in terms or "git" in terms
        assert "hooks" in terms
        assert "session" in terms
        assert "start" in terms
        assert "handler" in terms

    def test_react_component_path(self, domain_extractor: DomainExtractor) -> None:
        """Test typical React component path."""
        terms = domain_extractor.extract("src/components/UserProfile/UserProfile.tsx")
        assert "components" in terms
        assert "userprofile" in terms or "user" in terms

    def test_java_package_path(self, domain_extractor: DomainExtractor) -> None:
        """Test typical Java package path."""
        # Shorter path to ensure filename parts are included within max_terms
        terms = domain_extractor.extract("com/example/auth/jwt_token_service.java")
        assert "example" in terms
        assert "auth" in terms
        assert "jwt" in terms or "token" in terms

    def test_go_project_path(self, domain_extractor: DomainExtractor) -> None:
        """Test typical Go project path."""
        terms = domain_extractor.extract("internal/auth/jwt_handler.go")
        # internal is in skip list
        assert "internal" not in terms
        assert "auth" in terms
        assert "jwt" in terms
        assert "handler" in terms
