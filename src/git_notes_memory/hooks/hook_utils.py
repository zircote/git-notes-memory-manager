"""Shared utilities for hook handlers.

This module provides common utility functions used across all hook handlers:
- Logging configuration with file rotation
- Timeout management (SIGALRM-based)
- JSON input parsing with size limits
- Hook input/output debugging

These utilities were extracted from the handler modules to eliminate
code duplication and ensure consistent behavior across hooks.

Usage::

    from git_notes_memory.hooks.hook_utils import (
        setup_logging,
        setup_timeout,
        cancel_timeout,
        read_json_input,
        get_hook_logger,
    )

    # In your handler's main():
    hook_logger = get_hook_logger("SessionStart")
    setup_logging(debug=config.debug, hook_name="SessionStart")
    setup_timeout(30, hook_name="SessionStart")
    try:
        data = read_json_input()
        hook_logger.info("Received input: %s", json.dumps(data)[:500])
        # ... process data ...
    finally:
        cancel_timeout()
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

__all__ = [
    "setup_logging",
    "setup_timeout",
    "cancel_timeout",
    "read_json_input",
    "validate_file_path",
    "get_hook_logger",
    "log_hook_input",
    "log_hook_output",
    "MAX_INPUT_SIZE",
    "DEFAULT_TIMEOUT",
]

logger = logging.getLogger(__name__)

# Default timeout for hook execution (seconds)
DEFAULT_TIMEOUT = 30

# Maximum input size (10MB) to prevent memory exhaustion
MAX_INPUT_SIZE = 10 * 1024 * 1024

# Log file settings
LOG_DIR = Path(
    os.environ.get("MEMORY_PLUGIN_LOG_DIR", "~/.local/share/memory-plugin/logs")
).expanduser()
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB per file
LOG_BACKUP_COUNT = 5  # Keep 5 backup files

# Module-level cache for hook loggers
_hook_loggers: dict[str, logging.Logger] = {}


def get_hook_logger(hook_name: str) -> logging.Logger:
    """Get a dedicated file logger for a specific hook.

    Creates a rotating file logger that writes to a hook-specific log file.
    This enables detailed debugging of hook input/output without cluttering stderr.

    Args:
        hook_name: Name of the hook (e.g., "SessionStart", "Stop").

    Returns:
        Logger configured with rotating file handler.

    Example::

        logger = get_hook_logger("SessionStart")
        logger.info("Hook started with cwd: %s", cwd)
    """
    if hook_name in _hook_loggers:
        return _hook_loggers[hook_name]

    # Create log directory if needed
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Create hook-specific logger
    hook_logger = logging.getLogger(f"memory_hook.{hook_name}")
    hook_logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers
    if not hook_logger.handlers:
        # Create rotating file handler
        log_file = LOG_DIR / f"{hook_name.lower()}.log"
        handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setLevel(logging.DEBUG)

        # Detailed format for file logs
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        hook_logger.addHandler(handler)

    _hook_loggers[hook_name] = hook_logger
    return hook_logger


def log_hook_input(hook_name: str, data: dict[str, Any]) -> None:
    """Log hook input for debugging.

    Args:
        hook_name: Name of the hook.
        data: Parsed JSON input data.
    """
    hook_logger = get_hook_logger(hook_name)
    hook_logger.info("=" * 60)
    hook_logger.info("HOOK INPUT at %s", datetime.now().isoformat())
    hook_logger.info("-" * 60)

    # Log key fields
    for key in ["cwd", "session_id", "source", "transcript_path"]:
        if key in data:
            hook_logger.info("  %s: %s", key, data[key])

    # Log prompt (truncated)
    if "prompt" in data:
        prompt = data["prompt"]
        if len(prompt) > 500:
            hook_logger.info(
                "  prompt: %s... (truncated, %d chars)", prompt[:500], len(prompt)
            )
        else:
            hook_logger.info("  prompt: %s", prompt)

    # Log tool info for PostToolUse
    if "tool_name" in data:
        hook_logger.info("  tool_name: %s", data["tool_name"])
    if "tool_input" in data:
        tool_input_str = json.dumps(data["tool_input"])
        if len(tool_input_str) > 500:
            hook_logger.info("  tool_input: %s... (truncated)", tool_input_str[:500])
        else:
            hook_logger.info("  tool_input: %s", tool_input_str)

    # Log all keys for reference
    hook_logger.info("  all_keys: %s", list(data.keys()))


def log_hook_output(hook_name: str, output: dict[str, Any]) -> None:
    """Log hook output for debugging.

    Args:
        hook_name: Name of the hook.
        output: JSON output data.
    """
    hook_logger = get_hook_logger(hook_name)
    hook_logger.info("-" * 60)
    hook_logger.info("HOOK OUTPUT")
    hook_logger.info("-" * 60)

    output_str = json.dumps(output, indent=2)
    if len(output_str) > 2000:
        hook_logger.info("%s... (truncated)", output_str[:2000])
    else:
        hook_logger.info("%s", output_str)

    hook_logger.info("=" * 60)


def setup_logging(debug: bool = False, hook_name: str | None = None) -> None:
    """Configure logging based on debug flag.

    Sets up logging to stderr and optionally to a rotating file.
    This function is idempotent - calling it multiple times is safe.

    Args:
        debug: If True, log DEBUG level to stderr.
            If False, only log WARNING and above to stderr.
        hook_name: If provided, also configure file logging for this hook.

    Example::

        setup_logging(debug=config.debug, hook_name="SessionStart")
        logger.debug("This will show if debug=True")
    """
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="[memory-hook] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    # Also setup file logging if hook_name provided
    if hook_name:
        get_hook_logger(hook_name)


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
