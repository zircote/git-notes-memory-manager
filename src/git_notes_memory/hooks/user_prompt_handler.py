#!/usr/bin/env python3
"""UserPromptSubmit hook handler for automatic memory capture.

This handler detects memorable content in user prompts using signal detection
and novelty checking. It integrates with the CaptureDecider to determine
what action to take based on detected signals.

Usage (by Claude Code):
    echo '{"prompt": "...", "cwd": "/path", ...}' | python user_prompt.py

The output follows the hook response contract:
    {
        "continue": true,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "captureSuggestions": [...],  // For SUGGEST action
            "capturedMemories": [...]      // For AUTO action
        }
    }

Exit codes:
    0 - Success (non-blocking, always continues)
    Non-zero - Error (logged to stderr, fails gracefully)

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_USER_PROMPT_ENABLED: Enable this hook (default: true)
    HOOK_DEBUG: Enable debug logging (default: false)
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from git_notes_memory.config import HOOK_USER_PROMPT_TIMEOUT
from git_notes_memory.hooks.capture_decider import CaptureDecider
from git_notes_memory.hooks.config_loader import load_hook_config
from git_notes_memory.hooks.hook_utils import (
    cancel_timeout,
    log_hook_input,
    read_json_input,
    setup_logging,
    setup_timeout,
)
from git_notes_memory.hooks.models import (
    CaptureAction,
    CaptureSignal,
    SignalType,
    SuggestedCapture,
)
from git_notes_memory.hooks.namespace_parser import NamespaceParser
from git_notes_memory.hooks.signal_detector import SignalDetector

__all__ = ["main"]

logger = logging.getLogger(__name__)


def _validate_input(data: dict[str, Any]) -> bool:
    """Validate hook input has required fields.

    Args:
        data: Parsed JSON input data.

    Returns:
        True if valid, False otherwise.
    """
    # prompt is required for UserPromptSubmit
    return "prompt" in data and data["prompt"]


def _suggestion_to_dict(suggestion: SuggestedCapture) -> dict[str, Any]:
    """Convert a SuggestedCapture to a JSON-serializable dict.

    Args:
        suggestion: The capture suggestion.

    Returns:
        Dict representation for JSON output.
    """
    return {
        "namespace": suggestion.namespace,
        "summary": suggestion.summary,
        "content": suggestion.content,
        "tags": list(suggestion.tags),
        "confidence": suggestion.confidence,
    }


def _format_suggestions_xml(suggestions: list[SuggestedCapture]) -> str:
    """Format capture suggestions as XML for injection.

    Args:
        suggestions: List of capture suggestions.

    Returns:
        XML string for additionalContext.
    """
    if not suggestions:
        return ""

    from git_notes_memory.hooks.xml_formatter import XMLBuilder

    builder = XMLBuilder("capture_suggestions")

    for suggestion in suggestions:
        # Add suggestion element with confidence attribute
        suggestion_key = builder.add_element(
            "root",
            "suggestion",
            confidence=str(suggestion.confidence),
        )

        # Add child elements
        builder.add_element(suggestion_key, "namespace", text=suggestion.namespace)
        builder.add_element(suggestion_key, "summary", text=suggestion.summary)
        builder.add_element(suggestion_key, "content", text=suggestion.content)

        if suggestion.tags:
            tags_key = builder.add_element(suggestion_key, "tags")
            for tag in suggestion.tags:
                builder.add_element(tags_key, "tag", text=tag)

    return builder.to_string()


def _capture_memory(suggestion: SuggestedCapture) -> dict[str, Any]:
    """Capture content as a memory (for AUTO action).

    Args:
        suggestion: The capture suggestion with pre-filled metadata.

    Returns:
        Dict with capture result.
    """
    try:
        from git_notes_memory.capture import CaptureService, get_default_service

        capture: CaptureService = get_default_service()
        result = capture.capture(
            summary=suggestion.summary,
            content=suggestion.content,
            namespace=suggestion.namespace,
            tags=list(suggestion.tags),
        )

        if result.success and result.memory:
            return {
                "success": True,
                "memory_id": result.memory.id,
                "summary": result.memory.summary,
            }
        return {
            "success": False,
            "error": "Capture failed",
        }

    except ImportError:
        return {
            "success": False,
            "error": "git-notes-memory library not installed",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def _write_output(
    action: CaptureAction,
    suggestions: list[SuggestedCapture],
    captured: list[dict[str, Any]] | None = None,
) -> None:
    """Write hook output to stdout.

    Args:
        action: The capture action taken.
        suggestions: List of capture suggestions (for SUGGEST action).
        captured: List of captured memory results (for AUTO action).
    """
    output: dict[str, Any] = {"continue": True}

    if action == CaptureAction.SKIP:
        # No suggestions, just continue
        pass

    elif action == CaptureAction.SUGGEST and suggestions:
        # Include suggestions for user review
        output["hookSpecificOutput"] = {
            "hookEventName": "UserPromptSubmit",
            "captureSuggestions": [_suggestion_to_dict(s) for s in suggestions],
        }
        # Also include XML format for additionalContext
        output["hookSpecificOutput"]["additionalContext"] = _format_suggestions_xml(
            suggestions
        )

    elif action == CaptureAction.AUTO and captured:
        # Report captured memories
        successful = [c for c in captured if c.get("success")]
        if successful:
            output["message"] = f"💾 Captured {len(successful)} memory(s) automatically"
            output["hookSpecificOutput"] = {
                "hookEventName": "UserPromptSubmit",
                "capturedMemories": captured,
            }

    print(json.dumps(output))


def main() -> None:
    """Main entry point for the UserPromptSubmit hook.

    Reads hook event data from stdin, detects memorable content in the
    user prompt, and either captures automatically or suggests captures.

    This function always outputs continue:true for non-blocking behavior,
    even on errors (which are logged to stderr).
    """
    # Load configuration first (before timeout setup)
    config = load_hook_config()

    # Set up logging based on config
    setup_logging(config.debug)

    logger.debug("UserPromptSubmit hook invoked")

    # Check if hooks are enabled
    if not config.enabled:
        logger.debug("Hooks disabled via HOOK_ENABLED=false")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    if not config.user_prompt_enabled:
        logger.debug("UserPromptSubmit hook disabled via HOOK_USER_PROMPT_ENABLED")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Set up timeout
    timeout = config.timeout or HOOK_USER_PROMPT_TIMEOUT
    setup_timeout(timeout, hook_name="UserPromptSubmit")

    try:
        # Read and validate input
        input_data = read_json_input()
        logger.debug(
            "Received input with prompt: %s...", input_data.get("prompt", "")[:50]
        )

        # Log full input to file for debugging
        log_hook_input("UserPromptSubmit", input_data)

        if not _validate_input(input_data):
            logger.warning("Invalid hook input - missing prompt field")
            print(json.dumps({"continue": True}))
            sys.exit(0)

        prompt = input_data["prompt"]

        # Check for inline markers first (namespace-aware parsing)
        namespace_parser = NamespaceParser()
        parsed_marker = namespace_parser.parse(prompt)

        signals: list[CaptureSignal] = []

        if parsed_marker:
            # Inline marker found - create a high-confidence EXPLICIT signal
            # with the resolved namespace (explicit or auto-detected)
            resolved_namespace = namespace_parser.resolve_namespace(parsed_marker)
            logger.debug(
                "Found inline marker: type=%s, namespace=%s (resolved: %s)",
                parsed_marker.marker_type,
                parsed_marker.namespace,
                resolved_namespace,
            )

            # Create an explicit capture signal
            signals = [
                CaptureSignal(
                    type=SignalType.EXPLICIT,
                    match=prompt[:50],  # First 50 chars for context
                    confidence=1.0,  # Inline markers are highest confidence
                    context=parsed_marker.content,
                    suggested_namespace=resolved_namespace,
                    position=0,
                )
            ]
        else:
            # No inline marker - use standard signal detection
            detector = SignalDetector()
            signals = list(detector.detect(prompt))

        logger.debug("Detected %d signals in prompt", len(signals))

        if not signals:
            # No signals detected, pass through
            print(json.dumps({"continue": True}))
            sys.exit(0)

        # Decide what action to take
        decider = CaptureDecider(config=config)
        decision = decider.decide(signals)

        logger.debug(
            "Capture decision: %s - %s", decision.action.value, decision.reason
        )

        # Handle the decision
        captured: list[dict[str, Any]] = []

        if decision.action == CaptureAction.AUTO:
            # Capture automatically
            for suggestion in decision.suggested_captures:
                result = _capture_memory(suggestion)
                captured.append(result)
                if result.get("success"):
                    logger.info(
                        "Auto-captured memory: %s (%s)",
                        result.get("memory_id", "")[:8],
                        suggestion.namespace,
                    )

        # Output result
        _write_output(
            action=decision.action,
            suggestions=list(decision.suggested_captures),
            captured=captured if captured else None,
        )

    except json.JSONDecodeError as e:
        logger.error("Failed to parse hook input: %s", e)
        print(json.dumps({"continue": True}))
    except Exception as e:
        logger.exception("UserPromptSubmit hook error: %s", e)
        print(json.dumps({"continue": True}))
    finally:
        cancel_timeout()

    sys.exit(0)


if __name__ == "__main__":
    main()
