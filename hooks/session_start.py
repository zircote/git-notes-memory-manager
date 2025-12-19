#!/usr/bin/env python3
"""Hook: Inject memory context at session start.

This hook injects relevant memory context into Claude Code sessions at startup.
It reads the hook event data from stdin and outputs additionalContext for
injection into the session.

The actual context building logic is delegated to the session_start_handler
module in the git_notes_memory.hooks package.

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_SESSION_START_ENABLED: Enable this hook (default: true)
    HOOK_DEBUG: Enable debug logging (default: false)

Exit codes:
    0 - Success (non-blocking)
"""

from __future__ import annotations

import sys


def main() -> None:
    """Main hook entry point.

    Delegates to the session_start_handler module for actual processing.
    Falls back gracefully if the library is not installed.
    """
    try:
        from git_notes_memory.hooks.session_start_handler import main as handler_main

        handler_main()
    except ImportError:
        # Library not installed, exit silently (non-blocking)
        sys.exit(0)
    except Exception:
        # Any unexpected error, exit silently (non-blocking)
        sys.exit(0)


if __name__ == "__main__":
    main()
