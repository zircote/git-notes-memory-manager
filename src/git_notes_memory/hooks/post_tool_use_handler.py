"""PostToolUse hook handler for file-contextual memory injection and capture.

This handler triggers after file operations (Read, Write, Edit, MultiEdit)
to:
1. Inject relevant memories based on the file's domain
2. Auto-capture memory-worthy content from Write/Edit operations

Usage (by Claude Code):
    echo '{"tool_name": "Write", "tool_input": {"file_path": "...", "content": "..."}, ...}' | python posttooluse.py

The output follows the hook response contract:
    {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "<related_memories>...</related_memories>",
            "capturedMemories": [...]  // If auto-capture succeeded
        }
    }

Exit codes:
    0 - Success (non-blocking, always continues)
    Non-zero - Error (logged to stderr, fails gracefully)

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_POST_TOOL_USE_ENABLED: Enable this hook (default: true)
    HOOK_POST_TOOL_USE_MIN_SIMILARITY: Min similarity threshold (default: 0.6)
    HOOK_POST_TOOL_USE_MAX_RESULTS: Max memories to inject (default: 3)
    HOOK_POST_TOOL_USE_AUTO_CAPTURE: Auto-capture from written content (default: true)
    HOOK_POST_TOOL_USE_AUTO_CAPTURE_MIN_CONFIDENCE: Min confidence (default: 0.8)
    HOOK_DEBUG: Enable debug logging (default: false)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from git_notes_memory.hooks.config_loader import load_hook_config
from git_notes_memory.hooks.domain_extractor import extract_domain_terms
from git_notes_memory.hooks.hook_utils import (
    cancel_timeout,
    log_hook_input,
    read_json_input,
    setup_logging,
    setup_timeout,
    timed_hook_execution,
)
from git_notes_memory.hooks.xml_formatter import XMLBuilder
from git_notes_memory.observability import get_logger

if TYPE_CHECKING:
    from git_notes_memory.hooks.models import CaptureSignal
    from git_notes_memory.models import MemoryResult

__all__ = ["main"]

logger = get_logger(__name__)

# Tools that trigger this hook
TRIGGERING_TOOLS = frozenset({"Read", "Write", "Edit", "MultiEdit"})

# Default timeout (seconds)
DEFAULT_TIMEOUT = 5


def _extract_file_path(input_data: dict[str, Any]) -> str | None:
    """Extract file path from tool input.

    Args:
        input_data: Hook input data containing tool_input.

    Returns:
        File path if found, None otherwise.
    """
    tool_input = input_data.get("tool_input", {})

    # Handle different tool input structures
    if isinstance(tool_input, dict):
        # Write and Edit use file_path
        return tool_input.get("file_path")

    return None


def _extract_content(input_data: dict[str, Any]) -> str | None:
    """Extract written content from tool input.

    Args:
        input_data: Hook input data containing tool_input.

    Returns:
        Content string if found, None otherwise.
    """
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if not isinstance(tool_input, dict):
        return None

    # Write tool uses 'content'
    if tool_name == "Write":
        return tool_input.get("content")

    # Edit tool uses 'new_string'
    if tool_name == "Edit":
        return tool_input.get("new_string")

    # MultiEdit has multiple edits
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
        contents = []
        for edit in edits:
            if isinstance(edit, dict) and edit.get("new_string"):
                contents.append(edit["new_string"])
        return "\n".join(contents) if contents else None

    return None


def _detect_signals(content: str, min_confidence: float) -> list[CaptureSignal]:
    """Detect capture signals in written content.

    Args:
        content: The content to analyze.
        min_confidence: Minimum confidence threshold.

    Returns:
        List of detected signals above the confidence threshold.
    """
    try:
        from git_notes_memory.hooks.signal_detector import SignalDetector

        detector = SignalDetector(min_confidence=min_confidence)
        signals = detector.detect(content)
        return signals

    except ImportError:
        logger.warning("SignalDetector not available")
        return []
    except Exception as e:
        logger.debug("Signal detection error: %s", e)
        return []


def _auto_capture_signals(
    signals: list[CaptureSignal],
    file_path: str | None,
) -> list[dict[str, Any]]:
    """Auto-capture detected signals as memories.

    Args:
        signals: List of detected capture signals.
        file_path: Source file path for context.

    Returns:
        List of capture results with memory_id and namespace.
    """
    if not signals:
        return []

    captured: list[dict[str, Any]] = []

    try:
        from git_notes_memory.capture import get_default_service

        capture_service = get_default_service()

        for signal in signals:
            try:
                # Extract summary from match or context
                content = signal.context or signal.match
                lines = content.strip().split("\n")
                summary = lines[0][:100] if lines else content[:100]

                # Add tags
                tags = ["auto-captured", "post-tool-use"]
                if file_path:
                    filename = Path(file_path).name
                    tags.append(f"file:{filename}")

                # Capture the memory
                result = capture_service.capture(
                    namespace=signal.suggested_namespace,
                    summary=summary,
                    content=content,
                    tags=tags,
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
                        "Auto-captured from write: %s (confidence: %.2f)",
                        result.memory.id,
                        signal.confidence,
                    )

            except Exception as e:
                logger.debug("Failed to capture signal: %s", e)

    except ImportError as e:
        logger.warning("Capture service unavailable: %s", e)
    except Exception as e:
        logger.warning("Auto-capture failed: %s", e)

    return captured


def _search_related_memories(
    terms: list[str],
    max_results: int,
    min_similarity: float,
) -> list[MemoryResult]:
    """Search for memories related to domain terms.

    Args:
        terms: Domain terms extracted from file path.
        max_results: Maximum number of results to return.
        min_similarity: Minimum similarity score threshold.

    Returns:
        List of memory results.
    """
    try:
        from git_notes_memory.recall import get_default_service

        recall = get_default_service()

        # Join terms for semantic search
        query = " ".join(terms)
        logger.debug("Searching for: %s", query)

        results = recall.search(
            query=query,
            k=max_results,
            min_similarity=min_similarity,
        )

        return list(results)

    except ImportError:
        logger.warning("RecallService not available")
        return []
    except Exception as e:
        logger.exception("Memory search error: %s", e)
        return []


def _format_memories_xml(
    results: list[MemoryResult],
    file_path: str,
) -> str:
    """Format memory results as XML for additionalContext.

    Args:
        results: Memory search results.
        file_path: Original file path for context.

    Returns:
        XML string for injection.
    """
    if not results:
        return ""

    builder = XMLBuilder("related_memories")

    # Add file context attribute
    filename = Path(file_path).name
    builder.add_element("root", "file", text=filename)

    # Add memory elements
    for result in results:
        memory = result.memory
        memory_key = builder.add_element(
            "root",
            "memory",
            namespace=memory.namespace,
            similarity=f"{1 - result.distance:.2f}",
        )

        builder.add_element(memory_key, "summary", text=memory.summary)

        # Add truncated content preview
        content_preview = (memory.content or "")[:200]
        if len(memory.content or "") > 200:
            content_preview += "..."
        if content_preview:
            builder.add_element(memory_key, "preview", text=content_preview)

        # Add tags if present
        if memory.tags:
            tags_key = builder.add_element(memory_key, "tags")
            for tag in memory.tags[:5]:  # Limit tags
                builder.add_element(tags_key, "tag", text=tag)

    return builder.to_string()


def _write_output(
    context: str | None = None,
    memory_count: int = 0,
    captured: list[dict[str, Any]] | None = None,
) -> None:
    """Write hook output to stdout.

    Args:
        context: XML context string to inject, or None for no injection.
        memory_count: Number of related memories found.
        captured: List of auto-captured memory results.
    """
    messages: list[str] = []
    hook_output: dict[str, Any] = {"hookEventName": "PostToolUse"}

    # Add captured memories to output
    if captured:
        hook_output["capturedMemories"] = captured
        ns_counts: dict[str, int] = {}
        for c in captured:
            ns = c.get("namespace", "unknown")
            ns_counts[ns] = ns_counts.get(ns, 0) + 1
        ns_summary = ", ".join(f"{v} {k}" for k, v in ns_counts.items())
        messages.append(f"📝 Auto-captured {len(captured)} memories: {ns_summary}")

    # Add context injection
    if context:
        hook_output["additionalContext"] = context
        if memory_count > 0:
            messages.append(f"🔍 Found {memory_count} related memories")

    # Build output
    if len(hook_output) > 1:  # More than just hookEventName
        output: dict[str, Any] = {"hookSpecificOutput": hook_output}
        if messages:
            output["message"] = "\n".join(messages)
    else:
        output = {"continue": True}

    print(json.dumps(output))


def main() -> None:
    """Main entry point for the PostToolUse hook.

    Reads hook event data from stdin, performs two functions:
    1. Extracts domain terms from file path and injects related memories
    2. Detects and auto-captures memory-worthy content from Write/Edit

    This function always outputs continue:true for non-blocking behavior,
    even on errors (which are logged to stderr).
    """
    # Load configuration first (before timeout setup)
    config = load_hook_config()

    # Set up logging based on config
    setup_logging(config.debug)

    logger.debug("PostToolUse hook invoked")

    # Check if hooks are enabled
    if not config.enabled:
        logger.debug("Hooks disabled via HOOK_ENABLED=false")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    if not config.post_tool_use_enabled:
        logger.debug("PostToolUse hook disabled via HOOK_POST_TOOL_USE_ENABLED=false")
        print(json.dumps({"continue": True}))
        sys.exit(0)

    # Set up timeout
    timeout = config.post_tool_use_timeout or DEFAULT_TIMEOUT
    setup_timeout(timeout, hook_name="PostToolUse")

    with timed_hook_execution("PostToolUse") as timer:
        try:
            # Read and validate input
            input_data = read_json_input()
            logger.debug("Received input: tool_name=%s", input_data.get("tool_name"))

            # Log full input to file for debugging
            log_hook_input("PostToolUse", input_data)

            # Check if this is a triggering tool
            tool_name = input_data.get("tool_name", "")
            if tool_name not in TRIGGERING_TOOLS:
                logger.debug("Tool %s does not trigger PostToolUse", tool_name)
                timer.set_status("skipped")
                _write_output()
                sys.exit(0)

            # Extract file path
            file_path = _extract_file_path(input_data)

            # Track outputs
            context: str | None = None
            memory_count = 0
            captured: list[dict[str, Any]] = []

            # Auto-capture signals from written content (Write/Edit/MultiEdit)
            if config.post_tool_use_auto_capture and tool_name in {
                "Write",
                "Edit",
                "MultiEdit",
            }:
                content = _extract_content(input_data)
                if content:
                    logger.debug("Extracted content length: %d", len(content))
                    signals = _detect_signals(
                        content,
                        min_confidence=config.post_tool_use_auto_capture_min_confidence,
                    )
                    if signals:
                        logger.debug("Detected %d signals in content", len(signals))
                        captured = _auto_capture_signals(signals, file_path)

            # Search for related memories based on file path
            if file_path:
                logger.debug("Processing file: %s", file_path)

                # Extract domain terms
                terms = extract_domain_terms(file_path)
                if terms:
                    logger.debug("Extracted terms: %s", terms)

                    # Search for related memories
                    results = _search_related_memories(
                        terms=terms,
                        max_results=config.post_tool_use_max_results,
                        min_similarity=config.post_tool_use_min_similarity,
                    )

                    if results:
                        logger.debug("Found %d related memories", len(results))
                        context = _format_memories_xml(results, file_path)
                        memory_count = len(results)

            # Output results if we have anything
            if context or captured:
                _write_output(
                    context=context, memory_count=memory_count, captured=captured
                )
            else:
                _write_output()

        except json.JSONDecodeError as e:
            timer.set_status("error")
            logger.error("Failed to parse hook input: %s", e)
            print(json.dumps({"continue": True}))
        except Exception as e:
            timer.set_status("error")
            logger.exception("PostToolUse hook error: %s", e)
            print(json.dumps({"continue": True}))
        finally:
            cancel_timeout()

    sys.exit(0)


if __name__ == "__main__":
    main()
