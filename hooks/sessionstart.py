#!/usr/bin/env python3
"""Hook: Inject memory context at session start.

This hook runs at the start of each Claude Code session and injects
context that includes:
1. Memory system status (index health, memory count)
2. Relevant memories for the current project/spec
3. Response guidance for memory capture markers
4. Available namespaces and their purposes

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_SESSION_START_ENABLED: Enable this hook (default: true)
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

    Delegates to the session_start_handler module for actual processing.
    Falls back gracefully if the library is not installed.
    """
    try:
        from git_notes_memory.hooks.session_start_handler import main as handler_main

        handler_main()
    except ImportError as e:
        # Library not installed - graceful degradation
        print(json.dumps({"continue": True}))
        print(f"[memory-hook] SessionStart unavailable: {e}", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        # Any unexpected error - fail gracefully with logging
        print(json.dumps({"continue": True}))
        print(f"[memory-hook] SessionStart error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
