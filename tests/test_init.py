"""Tests for git_notes_memory package entry point (__init__.py).

This module tests the lazy loading behavior and public API of the package.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    pass


class TestPackageVersion:
    """Tests for package version exposure."""

    def test_version_accessible(self) -> None:
        """Test that __version__ is accessible and valid."""
        from git_notes_memory import __version__

        # Version should be a valid semver string
        assert __version__
        assert len(__version__.split(".")) == 3

    def test_version_is_string(self) -> None:
        """Test that __version__ is a string."""
        from git_notes_memory import __version__

        assert isinstance(__version__, str)

    def test_version_follows_semver(self) -> None:
        """Test that __version__ follows semantic versioning."""
        from git_notes_memory import __version__

        parts = __version__.split(".")
        assert len(parts) == 3
        # All parts should be numeric
        for part in parts:
            assert part.isdigit() or part.split("-")[0].isdigit()


class TestLazyLoading:
    """Tests for lazy loading behavior."""

    def test_import_does_not_load_embedding_model(self) -> None:
        """Test that importing the package doesn't load the embedding model.

        This is a critical performance test - loading the embedding model
        at import time would be slow and memory-intensive.
        """
        # Save original modules to restore after test
        # This prevents breaking isinstance() checks in subsequent tests
        original_modules = {
            key: sys.modules[key]
            for key in list(sys.modules.keys())
            if key.startswith("git_notes_memory")
        }

        try:
            # Remove any cached imports
            for mod in list(original_modules.keys()):
                del sys.modules[mod]

            # Import the package - this should NOT load sentence_transformers
            with patch.dict(sys.modules, {"sentence_transformers": None}):
                # If sentence_transformers is accessed, this will raise
                import git_notes_memory  # noqa: F401

                # If we get here without error, lazy loading is working
                assert True
        finally:
            # Restore original modules to maintain class identity
            # for isinstance() checks in subsequent tests
            for key in list(sys.modules.keys()):
                if key.startswith("git_notes_memory"):
                    del sys.modules[key]
            sys.modules.update(original_modules)

    def test_models_import_without_embedding(self) -> None:
        """Test that model classes can be imported without embedding service."""
        from git_notes_memory import (
            CaptureResult,
            CommitInfo,
            HydrationLevel,
            Memory,
            MemoryResult,
            NoteRecord,
        )

        # These should all be the actual classes
        assert Memory.__name__ == "Memory"
        assert MemoryResult.__name__ == "MemoryResult"
        assert HydrationLevel.__name__ == "HydrationLevel"
        assert CaptureResult.__name__ == "CaptureResult"
        assert CommitInfo.__name__ == "CommitInfo"
        assert NoteRecord.__name__ == "NoteRecord"

    def test_exceptions_import_without_embedding(self) -> None:
        """Test that exception classes can be imported without embedding service."""
        from git_notes_memory import (
            CaptureError,
            EmbeddingError,
            MemoryError,
            MemoryIndexError,
            ParseError,
            StorageError,
            ValidationError,
        )

        # These should all be exception classes
        assert issubclass(MemoryError, Exception)
        assert issubclass(StorageError, MemoryError)
        assert issubclass(MemoryIndexError, MemoryError)
        assert issubclass(EmbeddingError, MemoryError)
        assert issubclass(ParseError, MemoryError)
        assert issubclass(CaptureError, MemoryError)
        assert issubclass(ValidationError, MemoryError)

    def test_factory_functions_are_callable(self) -> None:
        """Test that factory functions are returned as callables."""
        from git_notes_memory import (
            get_capture_service,
            get_recall_service,
            get_sync_service,
        )

        assert callable(get_capture_service)
        assert callable(get_recall_service)
        assert callable(get_sync_service)


class TestPublicAPI:
    """Tests for the public API surface."""

    def test_all_exports_accessible(self) -> None:
        """Test that all items in __all__ are accessible."""
        import git_notes_memory

        for name in git_notes_memory.__all__:
            # Each name should be accessible without error
            obj = getattr(git_notes_memory, name)
            assert obj is not None, f"Failed to access {name}"

    def test_unknown_attribute_raises_error(self) -> None:
        """Test that unknown attributes raise AttributeError."""
        import git_notes_memory

        with pytest.raises(AttributeError) as exc_info:
            _ = git_notes_memory.nonexistent_attribute

        assert "nonexistent_attribute" in str(exc_info.value)

    def test_all_contains_expected_factories(self) -> None:
        """Test that __all__ contains the factory functions."""
        import git_notes_memory

        expected_factories = [
            "get_capture_service",
            "get_recall_service",
            "get_sync_service",
            "is_auto_capture_enabled",
        ]
        for factory in expected_factories:
            assert factory in git_notes_memory.__all__

    def test_all_contains_expected_models(self) -> None:
        """Test that __all__ contains the model classes."""
        import git_notes_memory

        expected_models = [
            "Memory",
            "MemoryResult",
            "HydrationLevel",
            "HydratedMemory",
            "SpecContext",
            "IndexStats",
            "VerificationResult",
            "CaptureResult",
            "CaptureAccumulator",
            "Pattern",
            "PatternType",
            "PatternStatus",
            "CommitInfo",
            "NoteRecord",
        ]
        for model in expected_models:
            assert model in git_notes_memory.__all__

    def test_all_contains_expected_exceptions(self) -> None:
        """Test that __all__ contains the exception classes."""
        import git_notes_memory

        expected_exceptions = [
            "MemoryError",
            "StorageError",
            "MemoryIndexError",
            "EmbeddingError",
            "ParseError",
            "CaptureError",
            "ValidationError",
        ]
        for exc in expected_exceptions:
            assert exc in git_notes_memory.__all__


class TestModelInstantiation:
    """Tests for model instantiation via package imports."""

    def test_memory_can_be_instantiated(self) -> None:
        """Test that Memory can be instantiated."""
        from datetime import UTC, datetime

        from git_notes_memory import Memory

        memory = Memory(
            id="test:abc1234:0",
            commit_sha="abc1234",
            namespace="decisions",
            summary="Test memory",
            content="Full content",
            timestamp=datetime.now(UTC),
        )
        assert memory.id == "test:abc1234:0"
        assert memory.namespace == "decisions"

    def test_capture_result_can_be_instantiated(self) -> None:
        """Test that CaptureResult can be instantiated."""
        from git_notes_memory import CaptureResult

        result = CaptureResult(success=True, indexed=True)
        assert result.success is True
        assert result.indexed is True

    def test_hydration_level_enum_values(self) -> None:
        """Test HydrationLevel enum values."""
        from git_notes_memory import HydrationLevel

        assert HydrationLevel.SUMMARY.value == 1
        assert HydrationLevel.FULL.value == 2
        assert HydrationLevel.FILES.value == 3

    def test_pattern_type_enum_values(self) -> None:
        """Test PatternType enum values."""
        from git_notes_memory import PatternType

        assert PatternType.SUCCESS.value == "success"
        assert PatternType.ANTI_PATTERN.value == "anti-pattern"


class TestExceptionBehavior:
    """Tests for exception behavior via package imports."""

    def test_exceptions_can_be_raised(self) -> None:
        """Test that exceptions can be raised and caught."""
        from git_notes_memory import MemoryError, StorageError

        with pytest.raises(StorageError):
            raise StorageError("Test storage error", "Try again")

        with pytest.raises(MemoryError):
            raise StorageError("Also caught as MemoryError", "Recovery hint")

    def test_exception_inheritance(self) -> None:
        """Test exception inheritance hierarchy."""
        from git_notes_memory import (
            CaptureError,
            EmbeddingError,
            MemoryError,
            MemoryIndexError,
            ParseError,
            StorageError,
            ValidationError,
        )

        # All custom exceptions inherit from MemoryError
        assert issubclass(StorageError, MemoryError)
        assert issubclass(MemoryIndexError, MemoryError)
        assert issubclass(EmbeddingError, MemoryError)
        assert issubclass(ParseError, MemoryError)
        assert issubclass(CaptureError, MemoryError)
        assert issubclass(ValidationError, MemoryError)

        # MemoryError inherits from Exception
        assert issubclass(MemoryError, Exception)


class TestDocstring:
    """Tests for package docstring and documentation."""

    def test_package_has_docstring(self) -> None:
        """Test that the package has a docstring."""
        import git_notes_memory

        assert git_notes_memory.__doc__ is not None
        assert len(git_notes_memory.__doc__) > 50

    def test_docstring_contains_usage_example(self) -> None:
        """Test that the docstring contains a usage example."""
        import git_notes_memory

        assert "get_capture_service" in git_notes_memory.__doc__
        assert "get_recall_service" in git_notes_memory.__doc__
