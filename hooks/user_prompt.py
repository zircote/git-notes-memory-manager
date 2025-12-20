#!/usr/bin/env python3
"""Hook: Detect memorable content in user prompts.

This hook detects signals indicating memorable content (decisions, learnings,
blockers, etc.) in user prompts and either captures automatically or suggests
capture to the user.

The hook uses pattern-based signal detection combined with novelty checking
to avoid duplicate captures.

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_USER_PROMPT_ENABLED: Enable this hook (default: true)
    HOOK_DEBUG: Enable debug logging (default: false)

Exit codes:
    0 - Success (non-blocking)
"""

from __future__ import annotations

import sys


def main() -> None:
    """Main hook entry point.

    Delegates to the user_prompt_handler module for actual processing.
    Falls back gracefully if the library is not installed.
    """
    try:
        from git_notes_memory.hooks.user_prompt_handler import main as handler_main

        handler_main()
    except ImportError:
        # Library not installed, exit silently (non-blocking)
        import json

        print(json.dumps({"continue": True}))
        sys.exit(0)
    except Exception as e:
        # Log error for debugging, but exit gracefully (non-blocking)
        import json

        print(f"[memory-hook] UserPromptSubmit error: {e}", file=sys.stderr)
        print(json.dumps({"continue": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
