"""Pytest configuration and shared fixtures.

This module provides common fixtures and test utilities:
- Service singleton reset via ServiceRegistry.reset()
- Git repository setup with mock notes
- In-memory index for fast tests
- Mock embedding service for deterministic tests

The autouse fixture ensures all service singletons are reset between tests.

Architecture Note (ARCH-002):
  Previously this module accessed internal module variables directly
  (_sync_service, _capture_service, etc.) to reset singletons. This
  violated encapsulation and required knowledge of internal module structure.

  Now we use ServiceRegistry.reset() which provides a clean public interface
  for resetting all service singletons atomically.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from git_notes_memory.embedding import EmbeddingService
from git_notes_memory.models import CommitInfo, Memory
from git_notes_memory.registry import ServiceRegistry

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch

# =============================================================================
# Environment & Singleton Reset
# =============================================================================


@pytest.fixture(autouse=True)
def reset_service_singletons() -> Iterator[None]:
    """Reset all service singletons before and after each test.

    This fixture uses ServiceRegistry.reset() to ensure clean state
    between tests. It's applied automatically to all tests.

    The ServiceRegistry provides a centralized way to manage singletons,
    replacing the previous approach of accessing module-level private
    variables directly.
    """
    # Reset before test
    ServiceRegistry.reset()

    yield

    # Reset after test
    ServiceRegistry.reset()


@pytest.fixture
def isolated_env(monkeypatch: MonkeyPatch, tmp_path: Path) -> Path:
    """Set up an isolated environment with temporary paths.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Pytest temporary path fixture.

    Returns:
        Path to the temporary data directory.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)

    monkeypatch.setenv("MEMORY_PLUGIN_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MEMORY_PLUGIN_LOG_DIR", str(tmp_path / "logs"))

    return data_dir


# =============================================================================
# Git Repository Fixtures
# =============================================================================


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository with initial commit.

    Args:
        tmp_path: Pytest temporary path fixture.

    Returns:
        Path to the git repository.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(
        ["git", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    # Configure git for the test
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    # Create initial commit
    initial_file = repo / "README.md"
    initial_file.write_text("# Test Repository\n")
    subprocess.run(
        ["git", "add", "."],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    return repo


@pytest.fixture
def git_repo_with_history(git_repo: Path) -> Path:
    """Create a git repository with multiple commits.

    Args:
        git_repo: Basic git repository fixture.

    Returns:
        Path to the git repository with history.
    """
    # Add more commits
    for i in range(3):
        test_file = git_repo / f"file{i}.txt"
        test_file.write_text(f"Content {i}\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Add file {i}"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )

    return git_repo


@pytest.fixture
def git_repo_path(git_repo: Path) -> str:
    """Get the absolute path to the git repository as a string.

    Args:
        git_repo: Basic git repository fixture.

    Returns:
        Absolute path string.
    """
    return str(git_repo.resolve())


# =============================================================================
# Mock Services
# =============================================================================


@pytest.fixture
def mock_embedding_service() -> EmbeddingService:
    """Create a mock embedding service that returns deterministic vectors.

    Returns:
        A mock EmbeddingService instance.
    """
    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.dimensions = 384
    mock_service.model_name = "mock-model"
    mock_service.is_loaded = True

    # Return deterministic embeddings based on text hash
    def mock_embed(text: str) -> list[float]:
        if not text:
            return [0.0] * 384
        # Create a deterministic vector from the text
        import hashlib

        hash_bytes = hashlib.md5(text.encode(), usedforsecurity=False).digest()
        # Expand to 384 dimensions
        values = []
        for i in range(384):
            byte_idx = i % len(hash_bytes)
            values.append((hash_bytes[byte_idx] - 128) / 128.0)
        return values

    mock_service.embed.side_effect = mock_embed

    def mock_embed_batch(texts: list[str], **kwargs: Any) -> list[list[float]]:
        return [mock_embed(t) for t in texts]

    mock_service.embed_batch.side_effect = mock_embed_batch

    return mock_service


@pytest.fixture
def registered_mock_embedding(
    mock_embedding_service: EmbeddingService,
) -> EmbeddingService:
    """Register a mock embedding service in the ServiceRegistry.

    Args:
        mock_embedding_service: The mock embedding service.

    Returns:
        The registered mock service.
    """
    ServiceRegistry.register(EmbeddingService, mock_embedding_service)
    return mock_embedding_service


# =============================================================================
# Model Fixtures
# =============================================================================


@pytest.fixture
def sample_memory() -> Memory:
    """Create a sample Memory object for testing.

    Returns:
        A Memory instance with test data.
    """
    return Memory(
        id="decisions:abc1234:0",
        commit_sha="abc1234567890abcdef",
        namespace="decisions",
        summary="Use PostgreSQL for persistence",
        content="## Context\n\nWe need a reliable database.\n\n## Decision\n\nUse PostgreSQL.",
        timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        spec="test-project",
        phase="implementation",
        tags=("database", "architecture"),
        status="active",
        relates_to=(),
    )


@pytest.fixture
def sample_memories() -> list[Memory]:
    """Create multiple sample Memory objects for testing.

    Returns:
        A list of Memory instances.
    """
    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
    return [
        Memory(
            id="decisions:abc1234:0",
            commit_sha="abc1234567890abcdef",
            namespace="decisions",
            summary="Use PostgreSQL",
            content="Decision content",
            timestamp=base_time,
            spec="project-a",
            tags=("database",),
        ),
        Memory(
            id="learnings:def5678:0",
            commit_sha="def5678901234567890",
            namespace="learnings",
            summary="TIL about indexes",
            content="Learning content",
            timestamp=base_time,
            spec="project-a",
            tags=("database", "performance"),
        ),
        Memory(
            id="blockers:ghi9012:0",
            commit_sha="ghi9012345678901234",
            namespace="blockers",
            summary="CI pipeline failing",
            content="Blocker content",
            timestamp=base_time,
            spec="project-b",
            status="active",
            tags=("ci",),
        ),
    ]


@pytest.fixture
def sample_commit_info() -> CommitInfo:
    """Create a sample CommitInfo object for testing.

    Returns:
        A CommitInfo instance with test data.
    """
    return CommitInfo(
        sha="abc1234567890abcdef1234567890abcdef123456",
        author_name="Test User",
        author_email="test@example.com",
        date="2024-01-15T10:30:00Z",
        message="Test commit message",
    )


# =============================================================================
# Utility Functions
# =============================================================================


def get_head_sha(repo: Path) -> str:
    """Get the HEAD commit SHA of a repository.

    Args:
        repo: Path to the git repository.

    Returns:
        The full SHA of HEAD.
    """
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def add_git_note(
    repo: Path,
    namespace: str,
    content: str,
    commit: str = "HEAD",
) -> None:
    """Add a git note to a repository.

    Args:
        repo: Path to the git repository.
        namespace: Note namespace (e.g., "decisions").
        content: Note content.
        commit: Commit to attach note to.
    """
    ref = f"refs/notes/mem/{namespace}"
    subprocess.run(
        ["git", "notes", "--ref", ref, "add", "-f", "-m", content, commit],
        cwd=repo,
        capture_output=True,
        check=True,
    )


# =============================================================================
# Skip Markers
# =============================================================================


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests",
    )
    config.addinivalue_line(
        "markers",
        "requires_model: marks tests that require the embedding model",
    )


# Check for CI environment
IS_CI = os.environ.get("CI", "").lower() in ("true", "1", "yes")


# Skip slow tests in CI by default (can override with -m slow)
slow = pytest.mark.skipif(
    IS_CI and os.environ.get("RUN_SLOW_TESTS", "").lower() not in ("true", "1", "yes"),
    reason="Slow test skipped in CI (set RUN_SLOW_TESTS=true to run)",
)

# Skip tests that require the embedding model
requires_model = pytest.mark.skipif(
    os.environ.get("SKIP_MODEL_TESTS", "").lower() in ("true", "1", "yes"),
    reason="Model tests skipped (set SKIP_MODEL_TESTS=false to run)",
)
