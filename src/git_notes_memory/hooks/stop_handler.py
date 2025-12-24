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
import sys
from pathlib import Path
from typing import Any

from git_notes_memory.config import HOOK_STOP_TIMEOUT
from git_notes_memory.hooks.config_loader import load_hook_config
from git_notes_memory.hooks.hook_utils import (
    cancel_timeout,
    get_hook_logger,
    log_hook_input,
    read_json_input,
    setup_logging,
    setup_timeout,
)
from git_notes_memory.hooks.models import CaptureSignal

__all__ = ["main"]

logger = logging.getLogger(__name__)


def _read_input_with_fallback() -> dict[str, Any]:
    """Read and parse JSON input from stdin with fallback for empty input.

    QUAL-001: Wraps hook_utils.read_json_input() with Stop-hook-specific
    fallback behavior (empty input is valid for stop hooks).

    Returns:
        Parsed JSON data, or empty dict if stdin is empty.
    """
    try:
        return read_json_input()
    except ValueError as e:
        # Empty input is OK for stop hook
        # Check for the specific error message from read_json_input
        err_msg = str(e).lower()
        if "empty input" in err_msg or "stdin" in err_msg and "empty" in err_msg:
            return {}
        raise


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


def _auto_capture_signals(
    signals: list[CaptureSignal],
    min_confidence: float,
    max_captures: int,
) -> tuple[list[dict[str, Any]], list[CaptureSignal]]:
    """Auto-capture high-confidence signals.

    Args:
        signals: List of detected capture signals.
        min_confidence: Minimum confidence threshold for auto-capture.
        max_captures: Maximum number of signals to auto-capture.

    Returns:
        Tuple of (captured_results, remaining_signals).
        - captured_results: List of dicts with memory_id and namespace
        - remaining_signals: Signals that were not auto-captured
    """
    if not signals:
        return [], []

    # Sort by confidence (highest first) and filter by threshold
    eligible = sorted(
        [s for s in signals if s.confidence >= min_confidence],
        key=lambda s: s.confidence,
        reverse=True,
    )

    # Limit to max_captures
    to_capture = eligible[:max_captures]
    remaining = [s for s in signals if s not in to_capture]

    captured: list[dict[str, Any]] = []

    try:
        from git_notes_memory.capture import get_default_service

        capture_service = get_default_service()

        for signal in to_capture:
            try:
                # Extract summary from first line or first 100 chars
                content = signal.context or signal.match
                lines = content.strip().split("\n")
                summary = lines[0][:100] if lines else content[:100]

                # Capture the memory
                result = capture_service.capture(
                    namespace=signal.suggested_namespace,
                    summary=summary,
                    content=content,
                )

                if result.success and result.memory:
                    captured.append(
                        {
                            "memory_id": result.memory.id,
                            "namespace": signal.suggested_namespace,
                            "summary": summary[:50],
                            "confidence": signal.confidence,
                        }
                    )
                    logger.info(
                        "Auto-captured memory: %s (confidence: %.2f)",
                        result.memory.id,
                        signal.confidence,
                    )
                else:
                    # Capture failed, add back to remaining
                    remaining.append(signal)
                    logger.warning(
                        "Auto-capture failed for signal: %s",
                        result.warning or "Unknown error",
                    )

            except Exception as e:
                # Capture failed, add back to remaining
                remaining.append(signal)
                logger.warning("Auto-capture error: %s", e)

    except ImportError as e:
        logger.warning("Capture service unavailable: %s", e)
        return [], signals
    except Exception as e:
        logger.warning("Auto-capture failed: %s", e)
        return [], signals

    return captured, remaining


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
    captured: list[dict[str, Any]],
    sync_result: dict[str, Any] | None,
    *,
    prompt_uncaptured: bool,
) -> None:
    """Write hook output to stdout.

    Args:
        uncaptured: List of uncaptured signals.
        captured: List of auto-captured memory results.
        sync_result: Index sync result.
        prompt_uncaptured: Whether to prompt for uncaptured content.
    """
    output: dict[str, Any] = {"continue": True}

    hook_output: dict[str, Any] = {"hookEventName": "Stop"}
    messages: list[str] = []

    # Report auto-captured content
    if captured:
        hook_output["capturedMemories"] = captured
        ns_counts: dict[str, int] = {}
        for c in captured:
            ns = c.get("namespace", "unknown")
            ns_counts[ns] = ns_counts.get(ns, 0) + 1
        ns_summary = ", ".join(f"{v} {k}" for k, v in ns_counts.items())
        messages.append(f"📝 Auto-captured {len(captured)} memories: {ns_summary}")

    # Include uncaptured content if found and prompting is enabled
    if uncaptured and prompt_uncaptured:
        hook_output["uncapturedContent"] = [_signal_to_dict(s) for s in uncaptured]
        hook_output["additionalContext"] = _format_uncaptured_xml(uncaptured)
        messages.append(
            f"🛑 {len(uncaptured)} potentially uncaptured memory(s) remain. "
            "Consider using /remember to capture them."
        )

    # Include sync stats if sync was performed
    if sync_result and not sync_result.get("skipped"):
        if sync_result.get("success"):
            stats = sync_result.get("stats", {})
            hook_output["syncStats"] = stats
            indexed = stats.get("indexed", 0)
            if indexed > 0:
                messages.append(f"📚 Index synced: {indexed} memories indexed")
        else:
            hook_output["syncError"] = sync_result.get("error", "Unknown error")

    # Combine messages
    if messages:
        output["message"] = "\n".join(messages)

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

    # Set up logging based on config - with file logging
    setup_logging(config.debug, hook_name="Stop")
    hook_logger = get_hook_logger("Stop")

    logger.debug("Stop hook invoked")
    hook_logger.info("Stop hook invoked")

    # Check if hooks are enabled
    if not config.enabled:
        logger.debug("Hooks disabled via HOOK_ENABLED=false")
        hook_logger.info("Hooks disabled via HOOK_ENABLED=false")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    if not config.stop_enabled:
        logger.debug("Stop hook disabled via HOOK_STOP_ENABLED")
        hook_logger.info("Stop hook disabled via HOOK_STOP_ENABLED")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Set up timeout
    timeout = config.timeout or HOOK_STOP_TIMEOUT
    setup_timeout(timeout, hook_name="Stop")

    try:
        # QUAL-001: Use hook_utils.read_json_input with fallback
        input_data = _read_input_with_fallback()
        logger.debug("Received stop hook input: %s", list(input_data.keys()))

        # Log full input to file for debugging
        log_hook_input("Stop", input_data)
        hook_logger.info(
            "Config: stop_auto_capture=%s, stop_prompt_uncaptured=%s, stop_sync_index=%s",
            config.stop_auto_capture,
            config.stop_prompt_uncaptured,
            config.stop_sync_index,
        )

        # Analyze session transcript for uncaptured content
        detected_signals: list[CaptureSignal] = []
        if config.stop_prompt_uncaptured or config.stop_auto_capture:
            transcript_path = input_data.get("transcript_path")
            hook_logger.info("Analyzing transcript: %s", transcript_path)
            detected_signals = _analyze_session(transcript_path)
            hook_logger.info("Found %d signals in transcript", len(detected_signals))
            for sig in detected_signals[:5]:  # Log first 5
                hook_logger.info(
                    "  Signal: type=%s, ns=%s, conf=%.2f, match=%s...",
                    sig.type.value,
                    sig.suggested_namespace,
                    sig.confidence,
                    sig.match[:50],
                )
        else:
            hook_logger.info(
                "Skipping transcript analysis (auto_capture=%s, prompt_uncaptured=%s)",
                config.stop_auto_capture,
                config.stop_prompt_uncaptured,
            )

        # Auto-capture high-confidence signals
        captured: list[dict[str, Any]] = []
        uncaptured: list[CaptureSignal] = detected_signals
        if config.stop_auto_capture and detected_signals:
            hook_logger.info(
                "Auto-capturing signals (min_conf=%.2f, max=%d)",
                config.stop_auto_capture_min_confidence,
                config.stop_max_captures,
            )
            captured, uncaptured = _auto_capture_signals(
                detected_signals,
                min_confidence=config.stop_auto_capture_min_confidence,
                max_captures=config.stop_max_captures,
            )
            hook_logger.info(
                "Auto-capture result: %d captured, %d remaining",
                len(captured),
                len(uncaptured),
            )
            for c in captured:
                hook_logger.info("  Captured: %s", c)
            logger.debug(
                "Auto-capture: %d captured, %d remaining",
                len(captured),
                len(uncaptured),
            )
        else:
            hook_logger.info(
                "Auto-capture skipped (auto_capture=%s, signals=%d)",
                config.stop_auto_capture,
                len(detected_signals),
            )

        # Sync index if enabled (after auto-capture to include new memories)
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
            captured=captured,
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
        cancel_timeout()

    sys.exit(0)


if __name__ == "__main__":
    main()
