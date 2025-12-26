#!/usr/bin/env python3
"""SessionStart hook handler for memory context injection.

This script is invoked by Claude Code at session start to inject relevant
memory context. It reads hook event data from stdin, builds context using
the ContextBuilder, and outputs JSON for additionalContext injection.

Usage (by Claude Code):
    echo '{"session_id": "...", "cwd": "/path", ...}' | python session_start.py

The output follows the hook response contract:
    {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "<memory_context>...</memory_context>"
        }
    }

Exit codes:
    0 - Success (non-blocking, context injected or skipped)
    Non-zero - Error (logged to stderr, fails gracefully to non-blocking)

Environment Variables:
    HOOK_ENABLED: Master switch for hooks (default: true)
    HOOK_SESSION_START_ENABLED: Enable this hook (default: true)
    HOOK_SESSION_START_FETCH_REMOTE: Fetch notes from remote on start (default: false)
    HOOK_DEBUG: Enable debug logging (default: false)
"""

from __future__ import annotations

import json
import sys
from typing import Any

from git_notes_memory.config import HOOK_SESSION_START_TIMEOUT, get_project_index_path
from git_notes_memory.git_ops import GitOps
from git_notes_memory.hooks.config_loader import load_hook_config
from git_notes_memory.hooks.context_builder import ContextBuilder
from git_notes_memory.hooks.guidance_builder import GuidanceBuilder
from git_notes_memory.hooks.hook_utils import (
    cancel_timeout,
    log_hook_input,
    read_json_input,
    setup_logging,
    setup_timeout,
    timed_hook_execution,
)
from git_notes_memory.hooks.project_detector import detect_project
from git_notes_memory.observability import get_logger

__all__ = ["main"]

logger = get_logger(__name__)


def _validate_input(data: dict[str, Any]) -> bool:
    """Validate hook input has required fields.

    Args:
        data: Parsed JSON input data.

    Returns:
        True if valid, False otherwise.
    """
    required_fields = ["cwd"]
    return all(field in data and data[field] for field in required_fields)


def _get_memory_count() -> int:
    """Get total memory count from index.

    Uses lightweight direct SQLite query without full IndexService
    initialization to avoid loading sqlite-vec extension on hot path.

    Returns:
        Number of memories indexed, or 0 if index doesn't exist.
    """
    import sqlite3

    try:
        index_path = get_project_index_path()
        if not index_path.exists():
            return 0
        # Use direct SQLite query for performance (skip full initialization)
        conn = sqlite3.connect(str(index_path))
        cursor = conn.execute("SELECT COUNT(*) FROM memories")
        row = cursor.fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception:
        logger.debug("Failed to get memory count from index", exc_info=True)
        return 0


def _write_output(context: str, memory_count: int = 0) -> None:
    """Write hook output to stdout.

    Args:
        context: XML context string to inject.
        memory_count: Number of memories in the system.
    """
    output: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    # Add user-visible status message
    if memory_count > 0:
        output["message"] = f"📚 Memory system: {memory_count} memories indexed"
    else:
        output["message"] = "📚 Memory system: initialized"
    print(json.dumps(output))


def main() -> None:
    """Main entry point for the SessionStart hook.

    Reads hook event data from stdin, builds memory context, and outputs
    JSON for additionalContext injection.

    This function always exits with code 0 for non-blocking behavior,
    even on errors (which are logged to stderr).
    """
    # Load configuration first (before timeout setup)
    config = load_hook_config()

    # Set up logging based on config
    setup_logging(config.debug)

    logger.debug("SessionStart hook invoked")

    # Check if hooks are enabled
    if not config.enabled:
        logger.debug("Hooks disabled via HOOK_ENABLED=false")
        sys.exit(0)

    if not config.session_start_enabled:
        logger.debug("SessionStart hook disabled via HOOK_SESSION_START_ENABLED=false")
        sys.exit(0)

    # Set up timeout
    timeout = config.timeout or HOOK_SESSION_START_TIMEOUT
    setup_timeout(timeout, hook_name="SessionStart")

    with timed_hook_execution("SessionStart") as timer:
        try:
            # Read and validate input
            input_data = read_json_input()
            logger.debug("Received input: %s", input_data)

            # Log full input to file for debugging
            log_hook_input("SessionStart", input_data)

            if not _validate_input(input_data):
                logger.warning("Invalid hook input - missing required fields")
                timer.set_status("skipped")
                sys.exit(0)

            # Extract working directory and session source
            cwd = input_data["cwd"]
            session_source = input_data.get("source", "startup")

            # Detect project information
            project_info = detect_project(cwd)
            logger.debug(
                "Detected project: name=%s, spec=%s",
                project_info.name,
                project_info.spec_id,
            )

            # Ensure git notes sync is configured for this repository
            git_ops: GitOps | None = None
            try:
                git_ops = GitOps(repo_path=cwd)
                if git_ops.ensure_sync_configured():
                    logger.debug("Git notes sync configured for repository")
                else:
                    logger.debug(
                        "Git notes sync not configured (no remote or not a git repo)"
                    )
            except Exception as e:
                logger.debug("Could not configure git notes sync: %s", e)

            # Migrate from old fetch refspec to new tracking refs pattern
            # This is idempotent and safe to call every session
            if git_ops is not None:
                try:
                    if git_ops.migrate_fetch_config():
                        logger.debug(
                            "Migrated git notes fetch refspec to tracking refs pattern"
                        )
                except Exception as e:
                    logger.debug("Fetch refspec migration skipped: %s", e)

            # Fetch and merge notes from remote if enabled (opt-in via env var)
            # This ensures we have the latest memories from collaborators
            if git_ops is not None and config.session_start_fetch_remote:
                try:
                    fetch_results = git_ops.fetch_notes_from_remote()
                    merged_count = 0
                    for ns, success in fetch_results.items():
                        if success and git_ops.merge_notes_from_tracking(ns):
                            merged_count += 1
                    # Reindex to include fetched memories
                    if merged_count > 0:
                        from git_notes_memory.sync import get_sync_service as get_sync

                        sync_service = get_sync(repo_path=cwd)
                        sync_service.reindex()
                        logger.debug(
                            "Fetched and merged %d namespaces from remote", merged_count
                        )
                except Exception as e:
                    logger.debug("Remote fetch on start skipped: %s", e)

            # Build response guidance if enabled
            guidance_xml = ""
            if config.session_start_include_guidance:
                guidance_builder = GuidanceBuilder()
                guidance_xml = guidance_builder.build_guidance(
                    config.session_start_guidance_detail.value
                )
                logger.debug(
                    "Built response guidance (%d chars, level=%s)",
                    len(guidance_xml),
                    config.session_start_guidance_detail.value,
                )

            # Build memory context
            context_builder = ContextBuilder(config=config)
            memory_context = context_builder.build_context(
                project=project_info.name,
                session_source=session_source,
                spec_id=project_info.spec_id,
            )

            logger.debug("Built memory context (%d chars)", len(memory_context))

            # Combine guidance and memory context
            if guidance_xml:
                full_context = f"{guidance_xml}\n\n{memory_context}"
            else:
                full_context = memory_context

            logger.debug("Total context (%d chars)", len(full_context))

            # Get memory count for status message
            memory_count = _get_memory_count()

            # Output result with memory count
            _write_output(full_context, memory_count=memory_count)

        except json.JSONDecodeError as e:
            timer.set_status("error")
            logger.error("Failed to parse hook input: %s", e)
            print(json.dumps({"continue": True}))
        except Exception as e:
            timer.set_status("error")
            logger.exception("SessionStart hook error: %s", e)
            print(json.dumps({"continue": True}))
        finally:
            cancel_timeout()

    sys.exit(0)


if __name__ == "__main__":
    main()
