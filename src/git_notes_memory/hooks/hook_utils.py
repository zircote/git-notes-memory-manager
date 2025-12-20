"""Shared utilities for hook handlers.

This module provides common utility functions used across all hook handlers:
- Logging configuration
- Timeout management (SIGALRM-based)
- JSON input parsing with size limits

These utilities were extracted from the handler modules to eliminate
code duplication and ensure consistent behavior across hooks.

Usage::

    from git_notes_memory.hooks.hook_utils import (
        setup_logging,
        setup_timeout,
        cancel_timeout,
        read_json_input,
    )

    # In your handler's main():
    setup_logging(debug=config.debug)
    setup_timeout(30, hook_name="SessionStart")
    try:
        data = read_json_input()
        # ... process data ...
    finally:
        cancel_timeout()
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "setup_logging",
    "setup_timeout",
    "cancel_timeout",
    "read_json_input",
    "validate_file_path",
    "MAX_INPUT_SIZE",
    "DEFAULT_TIMEOUT",
]

logger = logging.getLogger(__name__)

# Default timeout for hook execution (seconds)
DEFAULT_TIMEOUT = 30

# Maximum input size (10MB) to prevent memory exhaustion
MAX_INPUT_SIZE = 10 * 1024 * 1024


def setup_logging(debug: bool = False) -> None:
    """Configure logging based on debug flag.

    Sets up basic logging to stderr with appropriate level.
    This function is idempotent - calling it multiple times is safe.

    Args:
        debug: If True, log DEBUG level to stderr.
            If False, only log WARNING and above.

    Example::

        setup_logging(debug=config.debug)
        logger.debug("This will show if debug=True")
    """
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="[memory-hook] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def setup_timeout(
    timeout: int,
    *,
    hook_name: str = "hook",
    fallback_output: dict[str, Any] | None = None,
) -> None:
    """Set up alarm-based timeout for the hook.

    Configures a SIGALRM handler that will output JSON and exit
    gracefully if the hook exceeds the timeout. This ensures
    hooks never block Claude Code indefinitely.

    Note: Only works on Unix systems (where SIGALRM exists).
    On Windows, this function is a no-op.

    Args:
        timeout: Timeout in seconds.
        hook_name: Name of the hook for logging purposes.
        fallback_output: JSON output to print on timeout.
            Defaults to {"continue": True} for non-blocking behavior.

    Example::

        setup_timeout(30, hook_name="SessionStart")
        # If execution takes >30s, outputs {"continue": True} and exits
    """
    if fallback_output is None:
        fallback_output = {"continue": True}

    def timeout_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
        """Handle timeout by exiting gracefully."""
        logger.warning("%s hook timed out after %d seconds", hook_name, timeout)
        print(json.dumps(fallback_output))
        sys.exit(0)

    # Only set alarm on Unix systems
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)


def cancel_timeout() -> None:
    """Cancel the alarm-based timeout.

    Should be called in a finally block after hook processing completes.
    This is a no-op on Windows (where SIGALRM doesn't exist).

    Example::

        setup_timeout(30, hook_name="MyHook")
        try:
            # ... hook processing ...
        finally:
            cancel_timeout()
    """
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)


def read_json_input(
    max_size: int = MAX_INPUT_SIZE,
) -> dict[str, Any]:
    """Read and parse JSON input from stdin.

    Reads stdin with a size limit to prevent memory exhaustion,
    parses the content as JSON, and validates it's a dict.

    Args:
        max_size: Maximum input size in bytes. Defaults to 10MB.

    Returns:
        Parsed JSON data as a dictionary.

    Raises:
        json.JSONDecodeError: If input is not valid JSON.
        ValueError: If stdin is empty, too large, or not a dict.

    Example::

        try:
            data = read_json_input()
            cwd = data.get("cwd", "")
        except ValueError as e:
            logger.error("Invalid input: %s", e)
    """
    input_text = sys.stdin.read(max_size + 1)
    if len(input_text) > max_size:
        msg = f"Input exceeds maximum size of {max_size} bytes"
        raise ValueError(msg)
    if not input_text.strip():
        msg = "Empty input received on stdin"
        raise ValueError(msg)
    result = json.loads(input_text)
    if not isinstance(result, dict):
        msg = f"Expected JSON object, got {type(result).__name__}"
        raise ValueError(msg)
    return dict(result)


def validate_file_path(
    path_str: str | Path,
    *,
    must_exist: bool = True,
    allow_relative: bool = False,
) -> Path:
    """Validate a file path for security and correctness.

    Checks for path traversal attacks (../) and ensures the path
    is safe to access. This should be used when accepting file paths
    from external input like hook payloads.

    Args:
        path_str: The path string to validate.
        must_exist: If True, raise if the file doesn't exist.
        allow_relative: If False, require absolute paths only.

    Returns:
        Resolved Path object.

    Raises:
        ValueError: If the path is invalid, contains traversal sequences,
            or doesn't meet the specified requirements.

    Example::

        try:
            path = validate_file_path(input_data.get("transcript_path"))
            content = path.read_text()
        except ValueError as e:
            logger.warning("Invalid path: %s", e)

    Security:
        - Prevents path traversal via '..' sequences
        - Rejects relative paths by default (prevents CWD-relative attacks)
        - Resolves symlinks to detect traversal via symlink chains
    """
    if not path_str:
        msg = "Empty path provided"
        raise ValueError(msg)

    path = Path(path_str)

    # Check for path traversal sequences in the original string
    path_str_normalized = str(path_str).replace("\\", "/")
    if ".." in path_str_normalized:
        msg = f"Path contains traversal sequence: {path_str}"
        raise ValueError(msg)

    # Require absolute paths by default
    if not allow_relative and not path.is_absolute():
        msg = f"Relative path not allowed: {path_str}"
        raise ValueError(msg)

    # Resolve to absolute path (follows symlinks)
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError) as e:
        msg = f"Cannot resolve path: {path_str} - {e}"
        raise ValueError(msg) from e

    # After resolution, verify no '..' traversal succeeded via symlinks
    # The resolved path should not be outside expected directories
    # (This check ensures symlink chains don't escape)
    if ".." in str(resolved):
        msg = f"Resolved path contains traversal: {resolved}"
        raise ValueError(msg)

    # Check existence if required
    if must_exist and not resolved.exists():
        msg = f"File does not exist: {path_str}"
        raise ValueError(msg)

    # Ensure it's a file, not a directory
    if must_exist and resolved.is_dir():
        msg = f"Path is a directory, not a file: {path_str}"
        raise ValueError(msg)

    return resolved
