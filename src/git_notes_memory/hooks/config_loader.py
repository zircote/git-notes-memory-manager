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
    HOOK_CAPTURE_DETECTION_ENABLED: Enable capture signal detection
    HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE: Minimum confidence for suggestions
    HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD: Confidence for auto-capture
    HOOK_CAPTURE_DETECTION_NOVELTY_THRESHOLD: Novelty score threshold
    HOOK_USER_PROMPT_ENABLED: Enable UserPromptSubmit hook
    HOOK_STOP_ENABLED: Enable Stop hook
    HOOK_STOP_PROMPT_UNCAPTURED: Prompt for uncaptured content
    HOOK_TIMEOUT: Default hook timeout in seconds
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = ["HookConfig", "BudgetMode", "load_hook_config"]


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
        capture_detection_enabled: Enable signal detection in prompts.
        capture_detection_min_confidence: Minimum confidence for SUGGEST.
        capture_detection_auto_threshold: Confidence for AUTO capture.
        capture_detection_novelty_threshold: Novelty threshold (0=duplicate, 1=new).
        stop_enabled: Enable Stop hook processing.
        stop_prompt_uncaptured: Prompt for uncaptured memorable content.
        stop_sync_index: Sync search index on session end.
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

    # Capture detection settings
    capture_detection_enabled: bool = False  # Disabled by default, opt-in
    capture_detection_min_confidence: float = 0.7
    capture_detection_auto_threshold: float = 0.95
    capture_detection_novelty_threshold: float = 0.3

    # Stop hook settings
    stop_enabled: bool = True
    stop_prompt_uncaptured: bool = True
    stop_sync_index: bool = True

    # UserPromptSubmit hook settings
    user_prompt_enabled: bool = False  # Uses capture_detection_enabled by default

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

    # Performance settings
    if "HOOK_TIMEOUT" in env:
        kwargs["timeout"] = _parse_int(env["HOOK_TIMEOUT"], defaults.timeout)
    if "HOOK_DEBUG" in env:
        kwargs["debug"] = _parse_bool(env["HOOK_DEBUG"])

    return HookConfig(**kwargs)
