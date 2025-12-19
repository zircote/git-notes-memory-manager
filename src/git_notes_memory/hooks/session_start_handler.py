#!/usr/bin/env python3
"""SessionStart hook handler for memory context injection.

This script is invoked by Claude Code at session start to inject relevant
memory context. It reads hook event data from stdin, builds context using
the ContextBuilder, and outputs JSON for additionalContext injection.

Usage (by Claude Code):
    echo '{"session_id": "...", "cwd": "/path", ...}' | python session_start.py

The output follows the hook response contract:
    {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "<memory_context>...</memory_context>"
        }
    }

Exit codes:
    0 - Success (non-blocking, context injected or skipped)
    Non-zero - Error (logged to stderr, fails gracefully to non-blocking)

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_SESSION_START_ENABLED: Enable this hook (default: true)
    HOOK_DEBUG: Enable debug logging (default: false)
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from typing import Any

from git_notes_memory.config import HOOK_SESSION_START_TIMEOUT
from git_notes_memory.hooks.config_loader import load_hook_config
from git_notes_memory.hooks.context_builder import ContextBuilder
from git_notes_memory.hooks.project_detector import detect_project

__all__ = ["main"]

logger = logging.getLogger(__name__)


def _setup_logging(debug: bool = False) -> None:
    """Configure logging based on debug flag.

    Args:
        debug: If True, log DEBUG level to stderr.
    """
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="[memory-hook] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def _setup_timeout(timeout: int) -> None:
    """Set up alarm-based timeout for the hook.

    Args:
        timeout: Timeout in seconds.
    """

    def timeout_handler(signum: int, frame: Any) -> None:  # noqa: ARG001
        """Handle timeout by exiting gracefully."""
        logger.warning("SessionStart hook timed out after %d seconds", timeout)
        sys.exit(0)  # Non-blocking failure

    # Only set alarm on Unix systems
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)


def _cancel_timeout() -> None:
    """Cancel the alarm-based timeout."""
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)


def _read_input() -> dict[str, Any]:
    """Read and parse JSON input from stdin.

    Returns:
        Parsed JSON data.

    Raises:
        json.JSONDecodeError: If input is not valid JSON.
        ValueError: If stdin is empty or not a dict.
    """
    input_text = sys.stdin.read()
    if not input_text.strip():
        msg = "Empty input received on stdin"
        raise ValueError(msg)
    result = json.loads(input_text)
    if not isinstance(result, dict):
        msg = f"Expected JSON object, got {type(result).__name__}"
        raise ValueError(msg)
    return dict(result)


def _validate_input(data: dict[str, Any]) -> bool:
    """Validate hook input has required fields.

    Args:
        data: Parsed JSON input data.

    Returns:
        True if valid, False otherwise.
    """
    required_fields = ["cwd"]
    return all(field in data and data[field] for field in required_fields)


def _write_output(context: str) -> None:
    """Write hook output to stdout.

    Args:
        context: XML context string to inject.
    """
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(output))


def main() -> None:
    """Main entry point for the SessionStart hook.

    Reads hook event data from stdin, builds memory context, and outputs
    JSON for additionalContext injection.

    This function always exits with code 0 for non-blocking behavior,
    even on errors (which are logged to stderr).
    """
    # Load configuration first (before timeout setup)
    config = load_hook_config()

    # Set up logging based on config
    _setup_logging(config.debug)

    logger.debug("SessionStart hook invoked")

    # Check if hooks are enabled
    if not config.enabled:
        logger.debug("Hooks disabled via HOOK_ENABLED=false")
        sys.exit(0)

    if not config.session_start_enabled:
        logger.debug("SessionStart hook disabled via HOOK_SESSION_START_ENABLED=false")
        sys.exit(0)

    # Set up timeout
    timeout = config.timeout or HOOK_SESSION_START_TIMEOUT
    _setup_timeout(timeout)

    try:
        # Read and validate input
        input_data = _read_input()
        logger.debug("Received input: %s", input_data)

        if not _validate_input(input_data):
            logger.warning("Invalid hook input - missing required fields")
            sys.exit(0)

        # Extract working directory and session source
        cwd = input_data["cwd"]
        session_source = input_data.get("source", "startup")

        # Detect project information
        project_info = detect_project(cwd)
        logger.debug(
            "Detected project: name=%s, spec=%s",
            project_info.name,
            project_info.spec_id,
        )

        # Build context
        builder = ContextBuilder(config=config)
        context = builder.build_context(
            project=project_info.name,
            session_source=session_source,
            spec_id=project_info.spec_id,
        )

        logger.debug("Built context (%d chars)", len(context))

        # Output result
        _write_output(context)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse hook input: %s", e)
    except Exception as e:
        logger.exception("SessionStart hook error: %s", e)
    finally:
        _cancel_timeout()

    sys.exit(0)


if __name__ == "__main__":
    main()
