#!/usr/bin/env python3
"""Hook: Process session end with uncaptured content detection and index sync.

This hook performs session-end tasks:
1. Analyzes session transcript for uncaptured memorable content
2. Prompts user to capture worthy content (if configured)
3. Synchronizes the memory index

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_STOP_ENABLED: Enable this hook (default: true)
    HOOK_STOP_PROMPT_UNCAPTURED: Prompt for uncaptured content (default: true)
    HOOK_STOP_SYNC_INDEX: Sync index on session end (default: true)
    HOOK_DEBUG: Enable debug logging (default: false)

Exit codes:
    0 - Success (non-blocking)
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


def main() -> None:
    """Main hook entry point.

    Delegates to the stop_handler module for actual processing.
    Falls back gracefully if the library is not installed.
    """
    try:
        from git_notes_memory.hooks.stop_handler import main as handler_main

        handler_main()
    except ImportError:
        # Library not installed, exit silently (non-blocking)
        print(json.dumps({"continue": True}))
        sys.exit(0)
    except Exception:
        # Any unexpected error, exit silently (non-blocking)
        print(json.dumps({"continue": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
