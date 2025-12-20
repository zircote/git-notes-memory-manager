#!/usr/bin/env python3
"""Hook: Inject related memories after file write operations.

This hook runs after Write, Edit, or MultiEdit tool calls and injects
relevant memories based on the modified file's domain. It extracts
searchable terms from the file path and queries the memory index.

Example: After editing src/auth/jwt_handler.py, this hook might inject
memories related to authentication, JWT tokens, and related decisions.

Environment Variables:
    HOOK_POST_TOOL_USE_ENABLED: Enable this hook (default: true)
    HOOK_POST_TOOL_USE_MIN_SIMILARITY: Min similarity (default: 0.6)
    HOOK_POST_TOOL_USE_MAX_RESULTS: Max memories (default: 3)
"""

# Bootstrap: Ensure venv exists and re-exec if needed (MUST be first import)
import bootstrap  # noqa: F401, I001

import sys
from pathlib import Path

# Add plugin's src directory to sys.path for self-contained execution
_plugin_root = Path(__file__).resolve().parent.parent
_src_path = _plugin_root / "src"
if _src_path.exists() and str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))


def main() -> None:
    """Entry point for the PostToolUse hook."""
    try:
        from git_notes_memory.hooks.post_tool_use_handler import main as handler_main

        handler_main()
    except ImportError as e:
        # Library not installed - graceful degradation
        import json

        print(json.dumps({"continue": True}), file=sys.stdout)
        print(f"[memory-hook] PostToolUse unavailable: {e}", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        # Any other error - fail gracefully
        import json

        print(json.dumps({"continue": True}), file=sys.stdout)
        print(f"[memory-hook] PostToolUse error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
