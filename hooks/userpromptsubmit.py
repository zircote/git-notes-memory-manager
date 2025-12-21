#!/usr/bin/env python3
"""Hook: Detect and capture memory-worthy content in user prompts.

This hook delegates to user_prompt_handler for full signal detection
including inline markers, block markers, and semantic patterns.

Supported marker formats:
- Inline: [decision], [learned], [blocker], [progress], [remember]
- Block: ▶ decision ───, ▶ learned ───, etc.
- Colon blocks: :::decision, :::learned, etc.

Exit codes:
    0 - Success (non-blocking)
"""

import json
import sys
from pathlib import Path

# Add plugin's src directory to sys.path for self-contained execution
_plugin_root = Path(__file__).resolve().parent.parent
_src_path = _plugin_root / "src"
if _src_path.exists() and str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))


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
        print(json.dumps({"continue": True}))
        sys.exit(0)
    except Exception as e:
        # Log error for debugging, but exit gracefully (non-blocking)
        print(f"[memory-hook] UserPromptSubmit error: {e}", file=sys.stderr)
        print(json.dumps({"continue": True}))
        sys.exit(0)


if __name__ == "__main__":
    main()
