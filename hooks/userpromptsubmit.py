#!/usr/bin/env python3
"""Hook: Capture prompts as memories when marker is present.

This hook detects memory capture markers in user prompts and stores
the content as memories in the git notes system.

Supported marker formats:

Inline Markers:
- [remember] content          -> Capture to 'learnings'
- [remember:decisions] content -> Capture to 'decisions' namespace
- [capture] content           -> Auto-detect namespace from content
- @memory content             -> Auto-detect namespace from content

Shorthand Markers:
- [decision] content          -> Capture to 'decisions'
- [learned] content           -> Capture to 'learnings'
- [blocker] content           -> Capture to 'blockers'
- [progress] content          -> Capture to 'progress'

Markdown Block Markers (for detailed captures):
- :::decision Title here      -> Multi-line capture to 'decisions'
  ## Context
  Details...
  :::
- :::decision content:::      -> Single-line block capture

Example prompts that would be captured:
- "[remember] We decided to use PostgreSQL because..."
- "[decision] Using JWT for authentication due to stateless scaling"
- ":::decision Use PostgreSQL\n## Context\nNeed JSONB support...\n:::"
"""

import json
import sys
from pathlib import Path

# Add plugin's src directory to sys.path for self-contained execution
_plugin_root = Path(__file__).resolve().parent.parent
_src_path = _plugin_root / "src"
if _src_path.exists() and str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))


def parse_prompt(prompt: str) -> tuple[bool, str | None, str]:
    """Parse prompt for capture markers using NamespaceParser.

    Returns:
        Tuple of (should_capture, namespace, content)
        - should_capture: True if a marker was found
        - namespace: Detected namespace (or None for auto-detect)
        - content: Cleaned content with marker removed
    """
    try:
        from git_notes_memory.hooks.namespace_parser import NamespaceParser

        parser = NamespaceParser()
        result = parser.parse(prompt)

        if result is None:
            return False, None, prompt

        return True, result.namespace, result.content

    except ImportError:
        # Fallback if library not available - use basic detection
        import re

        markers = [r"^\[remember\]\s*", r"^\[capture\]\s*", r"^@memory\s+"]
        for pattern in markers:
            match = re.match(pattern, prompt, re.IGNORECASE)
            if match:
                clean = prompt[match.end() :].strip()
                return True, None, clean

        return False, None, prompt


def capture_memory(content: str, namespace: str | None = None) -> dict:
    """Capture content as a memory.

    Args:
        content: The content to capture.
        namespace: Target namespace (None for auto-detection).

    Returns:
        Dict with capture result.
    """
    try:
        from git_notes_memory import get_capture_service

        capture = get_capture_service()

        # If no namespace specified, default to learnings
        target_namespace = namespace or "learnings"

        # Extract a summary from the first line or first 100 chars
        lines = content.strip().split("\n")
        summary = lines[0][:100] if lines else content[:100]

        result = capture.capture(
            namespace=target_namespace,
            summary=summary,
            content=content,
        )

        if result.success:
            return {
                "success": True,
                "memory_id": result.memory.id,
                "namespace": target_namespace,
                "message": f"Captured as memory: {result.memory.id[:16]}...",
            }
        else:
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
        return {"success": False, "error": str(e)}


def get_namespace_emoji(namespace: str) -> str:
    """Get display emoji for a namespace."""
    emojis = {
        "decisions": "\u2696\ufe0f",  # Balance scale
        "learnings": "\U0001F4A1",  # Light bulb
        "blockers": "\U0001F6D1",  # Stop sign
        "progress": "\U0001F680",  # Rocket
        "patterns": "\U0001F9E9",  # Puzzle piece
        "research": "\U0001F50D",  # Magnifying glass
        "reviews": "\U0001F441\ufe0f",  # Eye
        "retrospective": "\U0001F504",  # Counterclockwise
        "inception": "\U0001F331",  # Seedling
        "elicitation": "\U0001F4AC",  # Speech bubble
    }
    return emojis.get(namespace, "\U0001F4DD")  # Default: memo


def main() -> None:
    """Main hook entry point."""
    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        sys.exit(1)

    prompt = input_data.get("prompt", "")

    # Parse prompt for capture markers
    should, namespace, content = parse_prompt(prompt)

    if not should:
        # No marker found, pass through unchanged
        print(json.dumps({"continue": True}))
        return

    # Capture the memory
    result = capture_memory(content, namespace)

    # Output result with visual indicator
    output = {"continue": True}

    if result.get("success"):
        ns = result.get("namespace", "learnings")
        emoji = get_namespace_emoji(ns)
        # Extract summary for display (first 50 chars of content)
        summary = content[:50] + "..." if len(content) > 50 else content
        # Remove newlines for display
        summary = summary.replace("\n", " ")
        output["message"] = f'{emoji} Captured to {ns}: "{summary}"'
    else:
        output["warning"] = f"\U0001F4BE Capture failed: {result.get('error', 'Unknown error')}"

    print(json.dumps(output))


if __name__ == "__main__":
    main()
