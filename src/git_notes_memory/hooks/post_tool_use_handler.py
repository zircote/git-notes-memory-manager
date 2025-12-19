"""PostToolUse hook handler for file-contextual memory injection.

This handler triggers after file operations (Read, Write, Edit, MultiEdit)
to inject relevant memories based on the file's domain. It extracts
searchable terms from the file path and queries the memory index.

Usage (by Claude Code):
    echo '{"tool_name": "Write", "tool_input": {"file_path": "..."}, ...}' | python posttooluse.py

The output follows the hook response contract:
    {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "<related_memories>...</related_memories>"
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
    HOOK_DEBUG: Enable debug logging (default: false)
"""

from __future__ import annotations

import json
import logging
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from git_notes_memory.hooks.config_loader import load_hook_config
from git_notes_memory.hooks.domain_extractor import extract_domain_terms
from git_notes_memory.hooks.xml_formatter import XMLBuilder

if TYPE_CHECKING:
    from git_notes_memory.models import MemoryResult

__all__ = ["main"]

logger = logging.getLogger(__name__)

# Tools that trigger this hook
TRIGGERING_TOOLS = frozenset({"Read", "Write", "Edit", "MultiEdit"})

# Default timeout (seconds)
DEFAULT_TIMEOUT = 5

# Maximum input size (10MB) to prevent memory exhaustion
MAX_INPUT_SIZE = 10 * 1024 * 1024


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
        logger.warning("PostToolUse hook timed out after %d seconds", timeout)
        # Output continue:true to not block
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
        ValueError: If stdin is empty, too large, or not a dict.
    """
    input_text = sys.stdin.read(MAX_INPUT_SIZE + 1)
    if len(input_text) > MAX_INPUT_SIZE:
        msg = f"Input exceeds maximum size of {MAX_INPUT_SIZE} bytes"
        raise ValueError(msg)
    if not input_text.strip():
        msg = "Empty input received on stdin"
        raise ValueError(msg)
    result = json.loads(input_text)
    if not isinstance(result, dict):
        msg = f"Expected JSON object, got {type(result).__name__}"
        raise ValueError(msg)
    return dict(result)


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


def _write_output(context: str | None = None) -> None:
    """Write hook output to stdout.

    Args:
        context: XML context string to inject, or None for no injection.
    """
    if context:
        output: dict[str, Any] = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": context,
            }
        }
    else:
        output = {"continue": True}

    print(json.dumps(output))


def main() -> None:
    """Main entry point for the PostToolUse hook.

    Reads hook event data from stdin, extracts domain terms from the
    file path, searches for related memories, and outputs JSON for
    additionalContext injection.

    This function always outputs continue:true for non-blocking behavior,
    even on errors (which are logged to stderr).
    """
    # Load configuration first (before timeout setup)
    config = load_hook_config()

    # Set up logging based on config
    _setup_logging(config.debug)

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
    _setup_timeout(timeout)

    try:
        # Read and validate input
        input_data = _read_input()
        logger.debug("Received input: tool_name=%s", input_data.get("tool_name"))

        # Check if this is a triggering tool
        tool_name = input_data.get("tool_name", "")
        if tool_name not in TRIGGERING_TOOLS:
            logger.debug("Tool %s does not trigger PostToolUse", tool_name)
            _write_output()
            sys.exit(0)

        # Extract file path
        file_path = _extract_file_path(input_data)
        if not file_path:
            logger.debug("No file_path in tool input")
            _write_output()
            sys.exit(0)

        logger.debug("Processing file: %s", file_path)

        # Extract domain terms
        terms = extract_domain_terms(file_path)
        if not terms:
            logger.debug("No domain terms extracted from: %s", file_path)
            _write_output()
            sys.exit(0)

        logger.debug("Extracted terms: %s", terms)

        # Search for related memories
        results = _search_related_memories(
            terms=terms,
            max_results=config.post_tool_use_max_results,
            min_similarity=config.post_tool_use_min_similarity,
        )

        if not results:
            logger.debug("No related memories found")
            _write_output()
            sys.exit(0)

        logger.debug("Found %d related memories", len(results))

        # Format as XML
        context = _format_memories_xml(results, file_path)

        # Output result
        _write_output(context)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse hook input: %s", e)
        print(json.dumps({"continue": True}))
    except Exception as e:
        logger.exception("PostToolUse hook error: %s", e)
        print(json.dumps({"continue": True}))
    finally:
        _cancel_timeout()

    sys.exit(0)


if __name__ == "__main__":
    main()
