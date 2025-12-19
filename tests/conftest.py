"""Shared pytest fixtures for git_notes_memory tests.

This module provides fixtures for test isolation, particularly for
resetting singleton service instances between tests.
"""

from __future__ import annotations

import pytest


def _close_index_connections() -> None:
    """Close any open IndexService database connections.

    This prevents ResourceWarning about unclosed sqlite3.Connection
    objects when singletons are reset.
    """
    try:
        from git_notes_memory import sync

        svc = sync._sync_service
        if svc is not None and hasattr(svc, "_index") and svc._index:
            svc._index.close()
    except (ImportError, AttributeError):
        pass

    try:
        from git_notes_memory import capture

        svc = capture._capture_service
        if svc is not None and hasattr(svc, "_index") and svc._index:
            svc._index.close()
    except (ImportError, AttributeError):
        pass

    try:
        from git_notes_memory import recall

        svc = recall._recall_service
        if svc is not None and hasattr(svc, "_index") and svc._index:
            svc._index.close()
    except (ImportError, AttributeError):
        pass


def _reset_all_singletons() -> None:
    """Reset all service singletons to None.

    This clears singleton state from all service modules.
    First closes any open database connections to prevent resource warnings.
    """
    # Close database connections first to prevent ResourceWarning
    _close_index_connections()

    try:
        from git_notes_memory import sync

        sync._sync_service = None
    except (ImportError, AttributeError):
        pass

    try:
        from git_notes_memory import capture

        capture._capture_service = None
    except (ImportError, AttributeError):
        pass

    try:
        from git_notes_memory import recall

        recall._recall_service = None
    except (ImportError, AttributeError):
        pass

    try:
        from git_notes_memory import search

        search._optimizer = None
    except (ImportError, AttributeError):
        pass

    try:
        from git_notes_memory import patterns

        patterns._manager = None
    except (ImportError, AttributeError):
        pass

    try:
        from git_notes_memory import lifecycle

        lifecycle._manager = None
    except (ImportError, AttributeError):
        pass


@pytest.fixture(autouse=True)
def reset_service_singletons() -> None:
    """Reset all service singletons before and after each test.

    This fixture ensures test isolation by clearing singleton state
    that may have been set during test execution or prior imports.
    Without this, tests that import services (even indirectly via
    __init__.py) can pollute subsequent tests.

    The fixture uses autouse=True to run automatically for every test.
    It resets BEFORE the test (so tests start clean) and AFTER the test
    (to clean up any state the test created).
    """
    # Reset before test
    _reset_all_singletons()
    yield
    # Reset after test
    _reset_all_singletons()


@pytest.fixture
def sample_fixture() -> str:
    """Example fixture - replace with project-specific fixtures."""
    return "sample_value"
