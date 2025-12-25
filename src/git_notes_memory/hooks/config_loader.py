"""Hook configuration loading and management.

This module provides the HookConfig dataclass and configuration loading
utilities for the hook handlers. Configuration can come from:
1. Default values (defined in HookConfig)
2. Environment variables (HOOK_* prefix)
3. Claude Code settings files

Environment Variables:
    HOOK_ENABLED: Master enable/disable for all hooks
    HOOK_SESSION_START_ENABLED: Enable SessionStart hook
    HOOK_SESSION_START_BUDGET_MODE: Token budget mode (adaptive/fixed/full)
    HOOK_SESSION_START_FIXED_BUDGET: Fixed budget amount
    HOOK_SESSION_START_INCLUDE_GUIDANCE: Include response guidance in SessionStart
    HOOK_SESSION_START_GUIDANCE_DETAIL: Guidance detail level (minimal/standard/detailed)
    HOOK_SESSION_START_MAX_MEMORIES: Maximum memories to retrieve (default: 30)
    HOOK_SESSION_START_AUTO_EXPAND_THRESHOLD: Relevance threshold for auto-expand hints (default: 0.85)
    HOOK_SESSION_START_FETCH_REMOTE: Fetch notes from remote on session start (default: false)
    HOOK_CAPTURE_DETECTION_ENABLED: Enable capture signal detection
    HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE: Minimum confidence for suggestions
    HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD: Confidence for auto-capture
    HOOK_CAPTURE_DETECTION_NOVELTY_THRESHOLD: Novelty score threshold
    HOOK_USER_PROMPT_ENABLED: Enable UserPromptSubmit hook
    HOOK_STOP_ENABLED: Enable Stop hook
    HOOK_STOP_PROMPT_UNCAPTURED: Prompt for uncaptured content
    HOOK_STOP_AUTO_CAPTURE: Auto-capture detected signals at session end (default: true)
    HOOK_STOP_AUTO_CAPTURE_MIN_CONFIDENCE: Minimum confidence for auto-capture (default: 0.8)
    HOOK_STOP_MAX_CAPTURES: Maximum auto-captures per session (default: 5)
    HOOK_STOP_PUSH_REMOTE: Push notes to remote on session stop (default: false)
    HOOK_POST_TOOL_USE_ENABLED: Enable PostToolUse hook
    HOOK_POST_TOOL_USE_MIN_SIMILARITY: Minimum similarity for memory recall
    HOOK_POST_TOOL_USE_MAX_RESULTS: Maximum memories to inject
    HOOK_POST_TOOL_USE_TIMEOUT: PostToolUse timeout in seconds
    HOOK_PRE_COMPACT_ENABLED: Enable PreCompact hook
    HOOK_PRE_COMPACT_AUTO_CAPTURE: Auto-capture without user prompt
    HOOK_PRE_COMPACT_PROMPT_FIRST: Show suggestions before capturing (suggestion mode)
    HOOK_PRE_COMPACT_MIN_CONFIDENCE: Minimum confidence for auto-capture
    HOOK_PRE_COMPACT_MAX_CAPTURES: Maximum memories to auto-capture
    HOOK_PRE_COMPACT_TIMEOUT: PreCompact timeout in seconds
    HOOK_TIMEOUT: Default hook timeout in seconds
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["HookConfig", "BudgetMode", "GuidanceDetailLevel", "load_hook_config"]


class BudgetMode(Enum):
    """Token budget allocation modes for SessionStart context.

    - ADAPTIVE: Dynamically calculates based on project complexity
    - FIXED: Uses a fixed token budget
    - FULL: Uses maximum available budget
    - MINIMAL: Uses minimal budget for fast startup
    """

    ADAPTIVE = "adaptive"
    FIXED = "fixed"
    FULL = "full"
    MINIMAL = "minimal"


class GuidanceDetailLevel(Enum):
    """Detail level for response guidance injection.

    - MINIMAL: Inline marker syntax only (~200 tokens)
    - STANDARD: Syntax + capture patterns (~500 tokens)
    - DETAILED: Full templates with examples (~1000 tokens)
    """

    MINIMAL = "minimal"
    STANDARD = "standard"
    DETAILED = "detailed"


@dataclass(frozen=True)
class HookConfig:
    """Configuration for hook handlers.

    This immutable dataclass holds all configuration options for the
    hook system. Values can be overridden via environment variables.

    Attributes:
        enabled: Master switch for all hooks.
        session_start_enabled: Enable SessionStart context injection.
        session_start_budget_mode: Token budget allocation strategy.
        session_start_fixed_budget: Fixed budget when mode is FIXED.
        session_start_max_budget: Maximum budget cap.
        session_start_include_guidance: Include response guidance in SessionStart.
        session_start_guidance_detail: Guidance detail level (minimal/standard/detailed).
        capture_detection_enabled: Enable signal detection in prompts.
        capture_detection_min_confidence: Minimum confidence for SUGGEST.
        capture_detection_auto_threshold: Confidence for AUTO capture.
        capture_detection_novelty_threshold: Novelty threshold (0=duplicate, 1=new).
        stop_enabled: Enable Stop hook processing.
        stop_prompt_uncaptured: Prompt for uncaptured memorable content.
        stop_sync_index: Sync search index on session end.
        post_tool_use_enabled: Enable PostToolUse hook for file-contextual memories.
        post_tool_use_min_similarity: Minimum similarity for memory recall.
        post_tool_use_max_results: Maximum memories to inject per tool use.
        post_tool_use_timeout: PostToolUse hook timeout in seconds.
        pre_compact_enabled: Enable PreCompact hook for memory preservation.
        pre_compact_auto_capture: Auto-capture without user prompt.
        pre_compact_prompt_first: Suggestion mode - show what would be captured via stderr
            instead of auto-capturing. User can then manually capture if desired.
        pre_compact_min_confidence: Minimum confidence for auto-capture.
        pre_compact_max_captures: Maximum memories to auto-capture per event.
        pre_compact_timeout: PreCompact hook timeout in seconds.
        timeout: Default timeout for hook operations (seconds).
        debug: Enable debug logging.
    """

    # Master control
    enabled: bool = True

    # SessionStart hook settings
    session_start_enabled: bool = True
    session_start_budget_mode: BudgetMode = BudgetMode.ADAPTIVE
    session_start_fixed_budget: int = 1000
    session_start_max_budget: int = 3000
    session_start_include_guidance: bool = True
    session_start_guidance_detail: GuidanceDetailLevel = GuidanceDetailLevel.STANDARD
    session_start_max_memories: int = 30  # Max memories to retrieve (20-30 recommended)
    session_start_auto_expand_threshold: float = (
        0.85  # Relevance threshold for auto-expand hint
    )
    session_start_fetch_remote: bool = (
        False  # Fetch notes from remote on start (opt-in)
    )

    # Capture detection settings
    capture_detection_enabled: bool = True  # Enabled by default when plugin is active
    capture_detection_min_confidence: float = 0.7
    capture_detection_auto_threshold: float = (
        0.85  # Lowered to auto-capture strong natural language signals
    )
    capture_detection_novelty_threshold: float = 0.3

    # Stop hook settings
    stop_enabled: bool = True
    stop_prompt_uncaptured: bool = True
    stop_sync_index: bool = True
    stop_auto_capture: bool = True  # Auto-capture detected signals at session end
    stop_auto_capture_min_confidence: float = 0.8  # Minimum confidence for auto-capture
    stop_max_captures: int = 50  # Maximum auto-captures per session
    stop_push_remote: bool = False  # Push notes to remote on stop (opt-in)

    # UserPromptSubmit hook settings
    user_prompt_enabled: bool = True  # Enabled by default when plugin is active

    # PostToolUse hook settings
    post_tool_use_enabled: bool = True
    post_tool_use_min_similarity: float = 0.6
    post_tool_use_max_results: int = 3
    post_tool_use_timeout: int = 5
    post_tool_use_auto_capture: bool = True  # Auto-capture signals in written content
    post_tool_use_auto_capture_min_confidence: float = 0.8  # Min confidence for capture

    # PreCompact hook settings
    pre_compact_enabled: bool = True
    pre_compact_auto_capture: bool = True
    pre_compact_prompt_first: bool = (
        False  # Suggestion mode: show what would be captured
    )
    pre_compact_min_confidence: float = 0.85
    pre_compact_max_captures: int = 50
    pre_compact_timeout: int = 15

    # Performance settings
    timeout: int = 30
    debug: bool = False

    # Budget tier thresholds (for adaptive mode)
    # Note: total must >= working_memory + semantic_context + commands (default 100)
    budget_tiers: tuple[tuple[str, int, int, int], ...] = field(
        default=(
            # (complexity, total_budget, working_memory, semantic_context)
            ("simple", 500, 300, 100),  # 300+100+100=500
            ("medium", 1000, 500, 300),  # 500+300+100=900 (margin for commands)
            ("complex", 2000, 900, 900),  # 900+900+100=1900 (margin)
            ("full", 3000, 1400, 1400),  # 1400+1400+100=2900 (margin)
        )
    )

    def get_budget_tier(self, complexity: str) -> tuple[int, int, int]:
        """Get budget allocation for a complexity level.

        Args:
            complexity: One of "simple", "medium", "complex", "full".

        Returns:
            Tuple of (total_budget, working_memory, semantic_context).

        Raises:
            ValueError: If complexity level is not recognized.
        """
        for tier_name, total, working, semantic in self.budget_tiers:
            if tier_name == complexity:
                return (total, working, semantic)
        msg = f"Unknown complexity level: {complexity}"
        raise ValueError(msg)


def _parse_bool(value: str) -> bool:
    """Parse a string to boolean.

    Args:
        value: String to parse (case-insensitive).

    Returns:
        True for "1", "true", "yes", "on"; False otherwise.
    """
    return value.lower() in {"1", "true", "yes", "on"}


def _parse_float(value: str, default: float) -> float:
    """Parse a string to float with fallback.

    Args:
        value: String to parse.
        default: Default value if parsing fails.

    Returns:
        Parsed float or default.
    """
    try:
        return float(value)
    except ValueError:
        return default


def _parse_int(value: str, default: int) -> int:
    """Parse a string to int with fallback.

    Args:
        value: String to parse.
        default: Default value if parsing fails.

    Returns:
        Parsed int or default.
    """
    try:
        return int(value)
    except ValueError:
        return default


def _parse_budget_mode(value: str) -> BudgetMode:
    """Parse budget mode from string.

    Args:
        value: Mode string (case-insensitive).

    Returns:
        BudgetMode enum value.

    Raises:
        ValueError: If mode is not recognized.
    """
    try:
        return BudgetMode(value.lower())
    except ValueError:
        valid = [m.value for m in BudgetMode]
        msg = f"Invalid budget mode '{value}'. Valid: {valid}"
        raise ValueError(msg) from None


def _parse_guidance_detail(value: str) -> GuidanceDetailLevel:
    """Parse guidance detail level from string.

    Args:
        value: Detail level string (case-insensitive).

    Returns:
        GuidanceDetailLevel enum value.

    Raises:
        ValueError: If level is not recognized.
    """
    try:
        return GuidanceDetailLevel(value.lower())
    except ValueError:
        valid = [level.value for level in GuidanceDetailLevel]
        msg = f"Invalid guidance detail level '{value}'. Valid: {valid}"
        raise ValueError(msg) from None


def load_hook_config(env: dict[str, str] | None = None) -> HookConfig:
    """Load hook configuration from environment variables.

    Reads configuration from environment variables with the HOOK_ prefix.
    Falls back to default values for unset variables.

    Args:
        env: Optional dict to use instead of os.environ (for testing).

    Returns:
        HookConfig with values from environment or defaults.

    Example::

        # Use real environment
        config = load_hook_config()

        # Use custom dict for testing
        config = load_hook_config({"HOOK_ENABLED": "false"})
    """
    if env is None:
        env = dict(os.environ)

    # Start with defaults
    defaults = HookConfig()
    kwargs: dict[str, Any] = {}

    # Master control
    if "HOOK_ENABLED" in env:
        kwargs["enabled"] = _parse_bool(env["HOOK_ENABLED"])

    # SessionStart settings
    if "HOOK_SESSION_START_ENABLED" in env:
        kwargs["session_start_enabled"] = _parse_bool(env["HOOK_SESSION_START_ENABLED"])
    if "HOOK_SESSION_START_BUDGET_MODE" in env:
        with contextlib.suppress(ValueError):
            kwargs["session_start_budget_mode"] = _parse_budget_mode(
                env["HOOK_SESSION_START_BUDGET_MODE"]
            )
    if "HOOK_SESSION_START_FIXED_BUDGET" in env:
        kwargs["session_start_fixed_budget"] = _parse_int(
            env["HOOK_SESSION_START_FIXED_BUDGET"],
            defaults.session_start_fixed_budget,
        )
    if "HOOK_SESSION_START_MAX_BUDGET" in env:
        kwargs["session_start_max_budget"] = _parse_int(
            env["HOOK_SESSION_START_MAX_BUDGET"],
            defaults.session_start_max_budget,
        )
    if "HOOK_SESSION_START_INCLUDE_GUIDANCE" in env:
        kwargs["session_start_include_guidance"] = _parse_bool(
            env["HOOK_SESSION_START_INCLUDE_GUIDANCE"]
        )
    if "HOOK_SESSION_START_GUIDANCE_DETAIL" in env:
        with contextlib.suppress(ValueError):
            kwargs["session_start_guidance_detail"] = _parse_guidance_detail(
                env["HOOK_SESSION_START_GUIDANCE_DETAIL"]
            )
    if "HOOK_SESSION_START_MAX_MEMORIES" in env:
        kwargs["session_start_max_memories"] = _parse_int(
            env["HOOK_SESSION_START_MAX_MEMORIES"],
            defaults.session_start_max_memories,
        )
    if "HOOK_SESSION_START_AUTO_EXPAND_THRESHOLD" in env:
        kwargs["session_start_auto_expand_threshold"] = _parse_float(
            env["HOOK_SESSION_START_AUTO_EXPAND_THRESHOLD"],
            defaults.session_start_auto_expand_threshold,
        )
    if "HOOK_SESSION_START_FETCH_REMOTE" in env:
        kwargs["session_start_fetch_remote"] = _parse_bool(
            env["HOOK_SESSION_START_FETCH_REMOTE"]
        )

    # Capture detection settings
    if "HOOK_CAPTURE_DETECTION_ENABLED" in env:
        kwargs["capture_detection_enabled"] = _parse_bool(
            env["HOOK_CAPTURE_DETECTION_ENABLED"]
        )
    if "HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE" in env:
        kwargs["capture_detection_min_confidence"] = _parse_float(
            env["HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE"],
            defaults.capture_detection_min_confidence,
        )
    if "HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD" in env:
        kwargs["capture_detection_auto_threshold"] = _parse_float(
            env["HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD"],
            defaults.capture_detection_auto_threshold,
        )
    if "HOOK_CAPTURE_DETECTION_NOVELTY_THRESHOLD" in env:
        kwargs["capture_detection_novelty_threshold"] = _parse_float(
            env["HOOK_CAPTURE_DETECTION_NOVELTY_THRESHOLD"],
            defaults.capture_detection_novelty_threshold,
        )

    # UserPromptSubmit hook settings
    if "HOOK_USER_PROMPT_ENABLED" in env:
        kwargs["user_prompt_enabled"] = _parse_bool(env["HOOK_USER_PROMPT_ENABLED"])

    # Stop hook settings
    if "HOOK_STOP_ENABLED" in env:
        kwargs["stop_enabled"] = _parse_bool(env["HOOK_STOP_ENABLED"])
    if "HOOK_STOP_PROMPT_UNCAPTURED" in env:
        kwargs["stop_prompt_uncaptured"] = _parse_bool(
            env["HOOK_STOP_PROMPT_UNCAPTURED"]
        )
    if "HOOK_STOP_SYNC_INDEX" in env:
        kwargs["stop_sync_index"] = _parse_bool(env["HOOK_STOP_SYNC_INDEX"])
    if "HOOK_STOP_AUTO_CAPTURE" in env:
        kwargs["stop_auto_capture"] = _parse_bool(env["HOOK_STOP_AUTO_CAPTURE"])
    if "HOOK_STOP_AUTO_CAPTURE_MIN_CONFIDENCE" in env:
        kwargs["stop_auto_capture_min_confidence"] = _parse_float(
            env["HOOK_STOP_AUTO_CAPTURE_MIN_CONFIDENCE"],
            defaults.stop_auto_capture_min_confidence,
        )
    if "HOOK_STOP_MAX_CAPTURES" in env:
        kwargs["stop_max_captures"] = _parse_int(
            env["HOOK_STOP_MAX_CAPTURES"],
            defaults.stop_max_captures,
        )
    if "HOOK_STOP_PUSH_REMOTE" in env:
        kwargs["stop_push_remote"] = _parse_bool(env["HOOK_STOP_PUSH_REMOTE"])

    # PostToolUse hook settings
    if "HOOK_POST_TOOL_USE_ENABLED" in env:
        kwargs["post_tool_use_enabled"] = _parse_bool(env["HOOK_POST_TOOL_USE_ENABLED"])
    if "HOOK_POST_TOOL_USE_MIN_SIMILARITY" in env:
        kwargs["post_tool_use_min_similarity"] = _parse_float(
            env["HOOK_POST_TOOL_USE_MIN_SIMILARITY"],
            defaults.post_tool_use_min_similarity,
        )
    if "HOOK_POST_TOOL_USE_MAX_RESULTS" in env:
        kwargs["post_tool_use_max_results"] = _parse_int(
            env["HOOK_POST_TOOL_USE_MAX_RESULTS"],
            defaults.post_tool_use_max_results,
        )
    if "HOOK_POST_TOOL_USE_TIMEOUT" in env:
        kwargs["post_tool_use_timeout"] = _parse_int(
            env["HOOK_POST_TOOL_USE_TIMEOUT"],
            defaults.post_tool_use_timeout,
        )
    if "HOOK_POST_TOOL_USE_AUTO_CAPTURE" in env:
        kwargs["post_tool_use_auto_capture"] = _parse_bool(
            env["HOOK_POST_TOOL_USE_AUTO_CAPTURE"]
        )
    if "HOOK_POST_TOOL_USE_AUTO_CAPTURE_MIN_CONFIDENCE" in env:
        kwargs["post_tool_use_auto_capture_min_confidence"] = _parse_float(
            env["HOOK_POST_TOOL_USE_AUTO_CAPTURE_MIN_CONFIDENCE"],
            defaults.post_tool_use_auto_capture_min_confidence,
        )

    # PreCompact hook settings
    if "HOOK_PRE_COMPACT_ENABLED" in env:
        kwargs["pre_compact_enabled"] = _parse_bool(env["HOOK_PRE_COMPACT_ENABLED"])
    if "HOOK_PRE_COMPACT_AUTO_CAPTURE" in env:
        kwargs["pre_compact_auto_capture"] = _parse_bool(
            env["HOOK_PRE_COMPACT_AUTO_CAPTURE"]
        )
    if "HOOK_PRE_COMPACT_PROMPT_FIRST" in env:
        kwargs["pre_compact_prompt_first"] = _parse_bool(
            env["HOOK_PRE_COMPACT_PROMPT_FIRST"]
        )
    if "HOOK_PRE_COMPACT_MIN_CONFIDENCE" in env:
        kwargs["pre_compact_min_confidence"] = _parse_float(
            env["HOOK_PRE_COMPACT_MIN_CONFIDENCE"],
            defaults.pre_compact_min_confidence,
        )
    if "HOOK_PRE_COMPACT_MAX_CAPTURES" in env:
        kwargs["pre_compact_max_captures"] = _parse_int(
            env["HOOK_PRE_COMPACT_MAX_CAPTURES"],
            defaults.pre_compact_max_captures,
        )
    if "HOOK_PRE_COMPACT_TIMEOUT" in env:
        kwargs["pre_compact_timeout"] = _parse_int(
            env["HOOK_PRE_COMPACT_TIMEOUT"],
            defaults.pre_compact_timeout,
        )

    # Performance settings
    if "HOOK_TIMEOUT" in env:
        kwargs["timeout"] = _parse_int(env["HOOK_TIMEOUT"], defaults.timeout)
    if "HOOK_DEBUG" in env:
        kwargs["debug"] = _parse_bool(env["HOOK_DEBUG"])

    return HookConfig(**kwargs)
