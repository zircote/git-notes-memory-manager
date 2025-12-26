"""PreCompact hook handler for memory preservation before compaction.

This handler triggers before context compaction to auto-capture high-confidence
uncaptured content that would otherwise be lost. It analyzes the transcript
for signals, filters to high-confidence items, and captures them automatically.

Usage (by Claude Code):
    echo '{"trigger": "auto", "transcript_path": "/path/to/transcript", ...}' | python precompact.py

The output follows the hook response contract:
    {}  # PreCompact is side-effects only

Side effects:
    1. Captures written to git notes via CaptureService
    2. stderr shows: "Auto-captured N memories before compaction"

Exit codes:
    0 - Success (non-blocking)
    Non-zero - Error (logged to stderr, fails gracefully)

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_PRE_COMPACT_ENABLED: Enable this hook (default: true)
    HOOK_PRE_COMPACT_AUTO_CAPTURE: Auto-capture without prompt (default: true)
    HOOK_PRE_COMPACT_PROMPT_FIRST: Suggestion mode - show what would be captured (default: false)
    HOOK_PRE_COMPACT_MIN_CONFIDENCE: Min confidence (default: 0.85)
    HOOK_PRE_COMPACT_MAX_CAPTURES: Max captures (default: 3)
    HOOK_DEBUG: Enable debug logging (default: false)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from git_notes_memory.hooks.config_loader import load_hook_config
from git_notes_memory.hooks.hook_utils import (
    cancel_timeout,
    get_hook_logger,
    log_hook_input,
    log_hook_output,
    read_json_input,
    setup_logging,
    setup_timeout,
    timed_hook_execution,
)
from git_notes_memory.hooks.namespace_styles import get_style
from git_notes_memory.hooks.session_analyzer import SessionAnalyzer
from git_notes_memory.observability import get_logger

if TYPE_CHECKING:
    from git_notes_memory.hooks.models import CaptureSignal

__all__ = ["main"]

logger = get_logger(__name__)

# Default timeout (seconds)
DEFAULT_TIMEOUT = 15


def _extract_summary(signal: CaptureSignal) -> str:
    """Extract a summary from a capture signal.

    Args:
        signal: The capture signal to summarize.

    Returns:
        A summary string (max 100 chars).
    """
    # Use the matched text as primary source
    text = signal.match.strip()

    # Fall back to context if match is very short
    if len(text) < 20 and signal.context:
        text = signal.context.strip()

    # Clean up the text - remove common signal prefixes for cleaner summaries
    for prefix in ("TIL ", "Learned ", "Decided ", "Found "):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix) :]
            break

    # Truncate to 100 chars
    if len(text) > 100:
        text = text[:97] + "..."

    return text


def _capture_memory(
    signal: CaptureSignal,
    namespace: str,
) -> dict[str, Any]:
    """Capture a signal as a memory.

    Args:
        signal: The capture signal with content.
        namespace: Target namespace for the memory.

    Returns:
        Dict with capture result (success, memory_id, or error).
    """
    try:
        from git_notes_memory.capture import get_default_service

        capture = get_default_service()

        # Extract summary and content
        summary = _extract_summary(signal)
        content = signal.context if signal.context else signal.match

        result = capture.capture(
            namespace=namespace,
            summary=summary,
            content=content,
            tags=["auto-captured", "pre-compact"],
        )

        if result.success and result.memory:
            return {
                "success": True,
                "memory_id": result.memory.id,
                "summary": result.memory.summary,
            }
        return {
            "success": False,
            "error": result.warning or "Capture failed",
        }

    except ImportError:
        return {
            "success": False,
            "error": "git-notes-memory library not installed",
        }
    except Exception as e:
        logger.debug("Failed to capture memory: %s", e, exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


def _report_captures(captured: list[dict[str, Any]]) -> None:
    """Report captured memories to user via stderr.

    Args:
        captured: List of capture results.
    """
    successful = [c for c in captured if c.get("success")]

    if not successful:
        return

    # Write to stderr so user sees it
    print(
        f"[memory-hook] Auto-captured {len(successful)} "
        f"memor{'y' if len(successful) == 1 else 'ies'} before compaction:",
        file=sys.stderr,
    )

    for capture in successful:
        summary = capture.get("summary", "")[:50]
        print(f"  - {summary}", file=sys.stderr)


def _report_suggestions(signals: list[CaptureSignal]) -> None:
    """Report suggested captures to user via stderr (suggestion mode).

    When HOOK_PRE_COMPACT_PROMPT_FIRST is enabled, this outputs what would
    be captured without actually capturing, allowing users to manually
    capture if desired.

    Args:
        signals: List of capture signals that would be captured.
    """
    if not signals:
        return

    # Write to stderr so user sees it
    print(
        f"[memory-hook] Found {len(signals)} "
        f"memor{'y' if len(signals) == 1 else 'ies'} to capture before compaction:",
        file=sys.stderr,
    )
    print(
        "[memory-hook] (Suggestion mode - use /capture to save manually)",
        file=sys.stderr,
    )

    for sig in signals:
        summary = _extract_summary(sig)[:50]
        namespace = sig.suggested_namespace
        confidence = f"{sig.confidence:.0%}"
        # Use unicode block marker
        style = get_style(namespace)
        marker = f"▶ {style.label}"
        print(f"  {marker} ({confidence}) {summary}", file=sys.stderr)


def main() -> None:
    """Main entry point for the PreCompact hook.

    Reads hook event data from stdin, analyzes the transcript for
    uncaptured high-confidence signals, and auto-captures them.

    Output is side-effects only (captures + stderr messages).
    """
    # Load configuration first (before timeout setup)
    config = load_hook_config()

    # Set up logging based on config
    setup_logging(config.debug)

    # Get dedicated file logger for debugging
    hook_logger = get_hook_logger("PreCompact")
    hook_logger.info("PreCompact hook invoked")
    hook_logger.info(
        "Config: auto_capture=%s, prompt_first=%s, min_conf=%.2f, max=%d",
        config.pre_compact_auto_capture,
        config.pre_compact_prompt_first,
        config.pre_compact_min_confidence,
        config.pre_compact_max_captures,
    )

    # Check if hooks are enabled
    if not config.enabled:
        hook_logger.info("Hooks disabled via HOOK_ENABLED=false - exiting")
        print(json.dumps({}))
        sys.exit(0)

    if not config.pre_compact_enabled:
        hook_logger.info(
            "PreCompact hook disabled via HOOK_PRE_COMPACT_ENABLED=false - exiting"
        )
        print(json.dumps({}))
        sys.exit(0)

    # Set up timeout
    timeout = config.pre_compact_timeout or DEFAULT_TIMEOUT
    setup_timeout(timeout, hook_name="PreCompact", fallback_output={})

    with timed_hook_execution("PreCompact") as timer:
        try:
            # Read input
            input_data = read_json_input()
            logger.debug("Received input: trigger=%s", input_data.get("trigger"))

            # Log full input to file for debugging
            log_hook_input("PreCompact", input_data)

            # Get transcript path
            transcript_path = input_data.get("transcript_path")
            if not transcript_path:
                hook_logger.info("No transcript_path in input - exiting")
                timer.set_status("skipped")
                print(json.dumps({}))
                sys.exit(0)

            hook_logger.info("Transcript path: %s", transcript_path)

            # Check if transcript exists
            if not Path(transcript_path).exists():
                hook_logger.info(
                    "Transcript file not found: %s - exiting", transcript_path
                )
                timer.set_status("skipped")
                print(json.dumps({}))
                sys.exit(0)

            hook_logger.info("Transcript exists, checking config...")

            # Check if auto-capture is enabled
            if not config.pre_compact_auto_capture:
                hook_logger.info(
                    "Auto-capture disabled via HOOK_PRE_COMPACT_AUTO_CAPTURE=false - exiting"
                )
                timer.set_status("skipped")
                print(json.dumps({}))
                sys.exit(0)

            hook_logger.info("Analyzing transcript for uncaptured signals...")

            # Analyze transcript for uncaptured signals
            analyzer = SessionAnalyzer(
                min_confidence=config.pre_compact_min_confidence,
                max_signals=config.pre_compact_max_captures,
            )

            signals = analyzer.analyze(transcript_path, check_novelty=True)

            if not signals:
                hook_logger.info("No uncaptured signals found in transcript - exiting")
                timer.set_status("skipped")
                print(json.dumps({}))
                sys.exit(0)

            hook_logger.info("Found %d uncaptured signals", len(signals))
            for sig in signals[:5]:
                hook_logger.info(
                    "  Signal: type=%s, ns=%s, conf=%.2f, match=%s...",
                    sig.type.value,
                    sig.suggested_namespace,
                    sig.confidence,
                    sig.match[:50],
                )

            # Check for suggestion mode (prompt_first)
            if config.pre_compact_prompt_first:
                hook_logger.info("Suggestion mode enabled - showing suggestions only")
                _report_suggestions(signals)
                print(json.dumps({}))
                sys.exit(0)

            hook_logger.info("Auto-capturing signals...")

            # Capture the signals
            captured: list[dict[str, Any]] = []

            for signal in signals:
                result = _capture_memory(signal, signal.suggested_namespace)
                captured.append(result)

                if result.get("success"):
                    hook_logger.info("  Captured: %s", result)
                else:
                    hook_logger.info("  Failed: %s", result)

            successful = len([c for c in captured if c.get("success")])
            hook_logger.info(
                "Auto-capture result: %d captured, %d remaining",
                successful,
                len(signals) - successful,
            )

            # Report captures to user
            _report_captures(captured)

            # Output empty JSON (PreCompact is side-effects only)
            output: dict[str, Any] = {}
            log_hook_output("PreCompact", output)
            print(json.dumps(output))

        except json.JSONDecodeError as e:
            timer.set_status("error")
            hook_logger.error("Failed to parse hook input: %s", e)
            print(json.dumps({}))
        except Exception as e:
            timer.set_status("error")
            hook_logger.exception("PreCompact hook error: %s", e)
            print(json.dumps({}))
        finally:
            cancel_timeout()

    sys.exit(0)


if __name__ == "__main__":
    main()
