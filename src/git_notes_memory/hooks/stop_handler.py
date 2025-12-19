#!/usr/bin/env python3
"""Stop hook handler for session-end processing.

This handler performs session-end tasks including:
1. Analyzing session transcript for uncaptured memorable content
2. Prompting user to capture worthy content (if configured)
3. Synchronizing the memory index

Usage (by Claude Code):
    echo '{"cwd": "/path", "transcript_path": "...", ...}' | python stop.py

The output follows the hook response contract:
    {
        "continue": true,
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "uncapturedContent": [...],  // Detected but not captured
            "syncStats": {...}            // Index sync statistics
        }
    }

Exit codes:
    0 - Success (non-blocking, always continues)
    Non-zero - Error (logged to stderr, fails gracefully)

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_STOP_ENABLED: Enable this hook (default: true)
    HOOK_STOP_PROMPT_UNCAPTURED: Prompt for uncaptured content (default: true)
    HOOK_STOP_SYNC_INDEX: Sync index on session end (default: true)
    HOOK_DEBUG: Enable debug logging (default: false)
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from pathlib import Path
from typing import Any

from git_notes_memory.config import HOOK_STOP_TIMEOUT
from git_notes_memory.hooks.config_loader import load_hook_config
from git_notes_memory.hooks.models import CaptureSignal

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
        logger.warning("Stop hook timed out after %d seconds", timeout)
        # Output continue:true to not block the user
        print(json.dumps({"continue": True}))
        sys.exit(0)

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
    """
    input_text = sys.stdin.read()
    if not input_text.strip():
        # Empty input is OK for stop hook
        return {}
    result = json.loads(input_text)
    if not isinstance(result, dict):
        return {}
    return dict(result)


def _analyze_session(transcript_path: str | None) -> list[CaptureSignal]:
    """Analyze session transcript for uncaptured content.

    Args:
        transcript_path: Path to session transcript file.

    Returns:
        List of CaptureSignal objects for uncaptured content.
    """
    if not transcript_path:
        logger.debug("No transcript path provided")
        return []

    path = Path(transcript_path)
    if not path.exists():
        logger.debug("Transcript file not found: %s", path)
        return []

    try:
        from git_notes_memory.hooks.session_analyzer import SessionAnalyzer

        analyzer = SessionAnalyzer(
            min_confidence=0.7,
            max_signals=5,
            novelty_threshold=0.3,
        )

        signals = analyzer.analyze(path, check_novelty=True)
        logger.debug("Found %d uncaptured signals in transcript", len(signals))
        return signals

    except ImportError as e:
        logger.warning("Session analysis unavailable: %s", e)
        return []
    except Exception as e:
        logger.warning("Session analysis failed: %s", e)
        return []


def _sync_index() -> dict[str, Any]:
    """Perform incremental index sync.

    Returns:
        Dict with sync result.
    """
    try:
        from git_notes_memory.sync import SyncService, get_sync_service

        sync: SyncService = get_sync_service()
        # reindex(full=False) does incremental sync
        indexed = sync.reindex(full=False)

        return {
            "success": True,
            "stats": {
                "indexed": indexed,
            },
        }

    except ImportError:
        # Library not installed, skip silently
        return {"success": True, "skipped": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _signal_to_dict(signal: CaptureSignal) -> dict[str, Any]:
    """Convert a CaptureSignal to a JSON-serializable dict.

    Args:
        signal: The capture signal.

    Returns:
        Dict representation for JSON output.
    """
    return {
        "type": signal.type.value,
        "match": signal.match,
        "confidence": signal.confidence,
        "context": signal.context,
        "suggestedNamespace": signal.suggested_namespace,
    }


def _format_uncaptured_xml(signals: list[CaptureSignal]) -> str:
    """Format uncaptured signals as XML for Claude context.

    Args:
        signals: List of uncaptured signals.

    Returns:
        XML string for additionalContext.
    """
    if not signals:
        return ""

    from git_notes_memory.hooks.xml_formatter import XMLBuilder

    builder = XMLBuilder("uncaptured_memories")

    for sig in signals:
        # Add signal element with type and confidence
        sig_key = builder.add_element(
            "root",
            "signal",
            type=sig.type.value,
            confidence=str(sig.confidence),
        )

        # Add child elements
        builder.add_element(sig_key, "match", text=sig.match)
        builder.add_element(sig_key, "context", text=sig.context)
        builder.add_element(sig_key, "namespace", text=sig.suggested_namespace)

    # Add action hint
    builder.add_element(
        "root",
        "action",
        text="Consider capturing these memories before ending the session using /remember",
    )

    return builder.to_string()


def _write_output(
    uncaptured: list[CaptureSignal],
    sync_result: dict[str, Any] | None,
    *,
    prompt_uncaptured: bool,
) -> None:
    """Write hook output to stdout.

    Args:
        uncaptured: List of uncaptured signals.
        sync_result: Index sync result.
        prompt_uncaptured: Whether to prompt for uncaptured content.
    """
    output: dict[str, Any] = {"continue": True}

    hook_output: dict[str, Any] = {"hookEventName": "Stop"}

    # Include uncaptured content if found and prompting is enabled
    if uncaptured and prompt_uncaptured:
        hook_output["uncapturedContent"] = [_signal_to_dict(s) for s in uncaptured]
        hook_output["additionalContext"] = _format_uncaptured_xml(uncaptured)

        # Add a message about uncaptured content
        output["message"] = (
            f"Found {len(uncaptured)} potentially uncaptured memory(s) "
            "from this session. Consider using /remember to capture them."
        )

    # Include sync stats if sync was performed
    if sync_result and not sync_result.get("skipped"):
        if sync_result.get("success"):
            stats = sync_result.get("stats", {})
            hook_output["syncStats"] = stats
            indexed = stats.get("indexed", 0)
            if indexed > 0:
                sync_msg = f"Index synced: {indexed} memories indexed"
                if "message" in output:
                    output["message"] += f"\n{sync_msg}"
                else:
                    output["message"] = sync_msg
        else:
            hook_output["syncError"] = sync_result.get("error", "Unknown error")

    # Only add hookSpecificOutput if we have content
    if len(hook_output) > 1:  # More than just hookEventName
        output["hookSpecificOutput"] = hook_output

    print(json.dumps(output))


def main() -> None:
    """Main entry point for the Stop hook.

    Reads hook event data from stdin, analyzes session transcript for
    uncaptured content, and syncs the memory index.

    This function always outputs continue:true for non-blocking behavior,
    even on errors (which are logged to stderr).
    """
    # Load configuration first (before timeout setup)
    config = load_hook_config()

    # Set up logging based on config
    _setup_logging(config.debug)

    logger.debug("Stop hook invoked")

    # Check if hooks are enabled
    if not config.enabled:
        logger.debug("Hooks disabled via HOOK_ENABLED=false")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    if not config.stop_enabled:
        logger.debug("Stop hook disabled via HOOK_STOP_ENABLED")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Set up timeout
    timeout = config.timeout or HOOK_STOP_TIMEOUT
    _setup_timeout(timeout)

    try:
        # Read input (may be empty for stop hook)
        input_data = _read_input()
        logger.debug("Received stop hook input: %s", list(input_data.keys()))

        # Analyze session transcript for uncaptured content
        uncaptured: list[CaptureSignal] = []
        if config.stop_prompt_uncaptured:
            transcript_path = input_data.get("transcript_path")
            uncaptured = _analyze_session(transcript_path)

        # Sync index if enabled
        sync_result: dict[str, Any] | None = None
        if config.stop_sync_index:
            sync_result = _sync_index()
            if sync_result.get("success") and not sync_result.get("skipped"):
                stats = sync_result.get("stats", {})
                logger.info(
                    "Index synced: %d memories indexed",
                    stats.get("indexed", 0),
                )
            elif not sync_result.get("success"):
                logger.warning("Index sync failed: %s", sync_result.get("error"))

        # Output result
        _write_output(
            uncaptured=uncaptured,
            sync_result=sync_result,
            prompt_uncaptured=config.stop_prompt_uncaptured,
        )

    except json.JSONDecodeError as e:
        logger.error("Failed to parse hook input: %s", e)
        print(json.dumps({"continue": True}))
    except Exception as e:
        logger.exception("Stop hook error: %s", e)
        print(json.dumps({"continue": True}))
    finally:
        _cancel_timeout()

    sys.exit(0)


if __name__ == "__main__":
    main()
