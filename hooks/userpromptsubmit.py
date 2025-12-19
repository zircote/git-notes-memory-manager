#!/usr/bin/env python3
"""Hook: Capture prompts as memories when marker is present.

This hook is DISABLED by default. Enable in hooks.json when ready.

The hook looks for a special marker in prompts to capture them:
- [remember] or [capture] at the start of a prompt
- Only captures when explicitly marked to avoid over-capturing

Example prompts that would be captured:
- "[remember] We decided to use PostgreSQL because..."
- "[capture] The authentication flow works like this..."
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Bootstrap: Add plugin's src directory to sys.path for self-contained execution
_plugin_root = Path(__file__).resolve().parent.parent
_src_path = _plugin_root / "src"
if _src_path.exists() and str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))


def should_capture(prompt: str) -> tuple[bool, str]:
    """Check if prompt should be captured and extract clean content.

    Returns:
        Tuple of (should_capture, cleaned_content)
    """
    # Look for capture markers at the start
    markers = [r"^\[remember\]\s*", r"^\[capture\]\s*", r"^@memory\s+"]

    for pattern in markers:
        match = re.match(pattern, prompt, re.IGNORECASE)
        if match:
            # Remove marker and return clean content
            clean = prompt[match.end() :].strip()
            return True, clean

    return False, prompt


def capture_memory(content: str) -> dict:
    """Capture content as a memory.

    Returns dict with capture result.
    """
    try:
        # Import here to avoid startup cost when hook is disabled
        from git_notes_memory import get_capture_service

        capture = get_capture_service()

        # Use the main capture() method with learnings namespace
        # Extract a summary from the first line or first 100 chars
        lines = content.strip().split("\n")
        summary = lines[0][:100] if lines else content[:100]

        result = capture.capture(
            namespace="learnings",
            summary=summary,
            content=content,
        )

        if result.success:
            return {
                "success": True,
                "memory_id": result.memory.id,
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


def main() -> None:
    """Main hook entry point."""
    # Read hook input from stdin
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        sys.exit(1)

    prompt = input_data.get("prompt", "")

    # Check if this prompt should be captured
    should, content = should_capture(prompt)

    if not should:
        # No marker found, pass through unchanged
        print(json.dumps({"continue": True}))
        return

    # Capture the memory
    result = capture_memory(content)

    # Output result with visual indicator
    output = {"continue": True}
    if result.get("success"):
        # Extract summary for display (first 50 chars of content)
        summary = content[:50] + "..." if len(content) > 50 else content
        output["message"] = f"💾 Captured to learnings: \"{summary}\""
    else:
        output["warning"] = f"💾 Capture failed: {result.get('error', 'Unknown error')}"

    print(json.dumps(output))


if __name__ == "__main__":
    main()
