#!/usr/bin/env python3
"""Hook: Inject memory capture context at session start.

This hook runs at the start of each Claude Code session and injects
context that reminds the user and assistant about memory capture markers.

The hook:
1. Provides memory system status (index health, memory count)
2. Reminds about capture markers: [remember], [capture], @memory
3. Lists available namespaces and their purposes
4. Suggests relevant memories if spec context is available
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Bootstrap: Add plugin's src directory to sys.path for self-contained execution
_plugin_root = Path(__file__).resolve().parent.parent
_src_path = _plugin_root / "src"
if _src_path.exists() and str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))


def get_memory_status() -> dict:
    """Get current memory system status.

    Returns:
        Dict with status information.
    """
    try:
        from git_notes_memory.config import get_index_path
        from git_notes_memory.index import IndexService

        index_path = get_index_path()
        if not index_path.exists():
            return {
                "initialized": False,
                "total_memories": 0,
                "message": "Memory index not initialized. Run `/memory:sync` to initialize.",
            }

        index = IndexService(index_path)
        index.initialize()
        stats = index.get_stats()
        index.close()

        return {
            "initialized": True,
            "total_memories": stats.total_memories,
            "by_namespace": dict(stats.by_namespace) if stats.by_namespace else {},
        }

    except ImportError:
        return {
            "initialized": False,
            "total_memories": 0,
            "error": "git-notes-memory library not installed",
        }
    except Exception as e:
        return {
            "initialized": False,
            "total_memories": 0,
            "error": str(e),
        }


def build_context_message(status: dict) -> str:
    """Build the context injection message.

    Args:
        status: Memory system status dict.

    Returns:
        Formatted context message for Claude.
    """
    lines = []

    # Memory system status
    if status.get("initialized"):
        total = status.get("total_memories", 0)
        lines.append(f"Memory system active: {total} memories indexed.")
        if status.get("by_namespace"):
            ns_summary = ", ".join(
                f"{ns}: {count}" for ns, count in list(status["by_namespace"].items())[:5]
            )
            lines.append(f"Namespaces: {ns_summary}")
    else:
        lines.append("Memory system: not initialized.")
        if status.get("error"):
            lines.append(f"Note: {status['error']}")

    lines.append("")
    lines.append("MEMORY CAPTURE MARKERS:")
    lines.append(
        "When you discover important information worth preserving, prefix your response with:"
    )
    lines.append("- [remember] <content> - Captures as a 'learnings' memory")
    lines.append("- [capture] <content> - Captures as a 'learnings' memory")
    lines.append("- @memory <content> - Same as [capture]")
    lines.append("")
    lines.append(
        "Examples of what to capture: decisions, learnings, blockers, "
        "patterns, progress, and key insights."
    )

    return "\n".join(lines)


def main() -> None:
    """Main hook entry point."""
    # Read hook input from stdin (not used but must be consumed)
    try:
        _input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _input_data = {}  # noqa: F841

    # Get memory system status
    status = get_memory_status()

    # Build context message
    context_message = build_context_message(status)

    # Output the context injection
    output = {
        "continue": True,
        "additionalContext": context_message,
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
