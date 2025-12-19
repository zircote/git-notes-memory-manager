"""Tests for git_notes_memory.main module."""

from __future__ import annotations

from git_notes_memory import __version__
from git_notes_memory.main import main


def test_version() -> None:
    """Test that version is defined and valid."""
    assert __version__
    assert len(__version__.split(".")) == 3


def test_main_no_args_returns_zero() -> None:
    """Test that main() with no args returns 0 (shows help)."""
    result = main([])
    assert result == 0


def test_main_version_flag() -> None:
    """Test that --version flag works."""
    result = main(["--version"])
    assert result == 0


def test_main_unknown_command() -> None:
    """Test that unimplemented commands return 1."""
    result = main(["status"])
    assert result == 1
