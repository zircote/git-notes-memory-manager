#!/usr/bin/env python3
"""Hook: Preserve memories before context compaction.

This hook runs before context compaction (auto or manual) to capture
high-confidence uncaptured content that would otherwise be lost.

The hook:
1. Analyzes the session transcript for memorable signals
2. Filters to high-confidence (≥0.85) novel content
3. Auto-captures the top signals to preserve them
4. Reports captures via stderr (visible to user)

Environment Variables:
    HOOK_PRE_COMPACT_ENABLED: Enable this hook (default: true)
    HOOK_PRE_COMPACT_AUTO_CAPTURE: Auto-capture without prompt (default: true)
    HOOK_PRE_COMPACT_MIN_CONFIDENCE: Min confidence (default: 0.85)
    HOOK_PRE_COMPACT_MAX_CAPTURES: Max captures (default: 3)
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
    """Entry point for the PreCompact hook."""
    try:
        from git_notes_memory.hooks.pre_compact_handler import main as handler_main

        handler_main()
    except ImportError as e:
        # Library not installed - graceful degradation
        import json

        print(json.dumps({}), file=sys.stdout)
        print(f"[memory-hook] PreCompact unavailable: {e}", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        # Any other error - fail gracefully
        import json

        print(json.dumps({}), file=sys.stdout)
        print(f"[memory-hook] PreCompact error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
