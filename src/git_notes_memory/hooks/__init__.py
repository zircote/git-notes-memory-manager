"""Hook services for Claude Code integration.

ARCH-H-005: This module provides hook handlers and utilities for integrating
the memory system with Claude Code's hook mechanism.

Module Organization (by responsibility):
- **Handlers**: session_start_handler, stop_handler, user_prompt_handler,
  post_tool_use_handler, pre_compact_handler
- **Context**: context_builder, guidance_builder - Build session context
- **Detection**: signal_detector, capture_decider, novelty_checker - Analyze content
- **Analysis**: session_analyzer, project_detector, domain_extractor - Extract info
- **Formatting**: xml_formatter, namespace_parser, namespace_styles - Output formatting
- **Config**: config_loader, hook_utils - Configuration and utilities
- **Models**: models - Shared data structures

The hooks follow Claude Code's hook specification:
- Input: JSON from stdin with hook event data
- Output: JSON to stdout with hookSpecificOutput
- Exit 0 for non-blocking (continue session)
- Exit 1 for blocking (with hookSpecificOutput for user action)

Example usage::

    from git_notes_memory.hooks import (
        ContextBuilder,
        SignalDetector,
        XMLBuilder,
        load_hook_config,
    )

    # Build session context
    builder = ContextBuilder()
    context_xml = builder.build_context(project="my-project")

    # Detect capture signals
    detector = SignalDetector()
    signals = detector.detect("I decided to use PostgreSQL")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    # Configuration
    "HookConfig",
    "load_hook_config",
    # XML Formatting
    "XMLBuilder",
    # Context Building
    "ContextBuilder",
    "TokenBudget",
    # Signal Detection
    "SignalDetector",
    "SIGNAL_PATTERNS",
    "CaptureSignal",
    "SignalType",
    # Novelty Checking
    "NoveltyChecker",
    "NoveltyResult",
    # Capture Decision
    "CaptureDecider",
    "CaptureDecision",
    "CaptureAction",
    # Session Analysis
    "SessionAnalyzer",
    "TranscriptContent",
    # Project Detection
    "detect_project",
]

# =============================================================================
# Lazy Import System (consistent with ARCH-H-003 pattern)
# =============================================================================

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Configuration
    "HookConfig": ("git_notes_memory.hooks.config_loader", "HookConfig"),
    "load_hook_config": ("git_notes_memory.hooks.config_loader", "load_hook_config"),
    # XML Formatting
    "XMLBuilder": ("git_notes_memory.hooks.xml_formatter", "XMLBuilder"),
    # Context Building
    "ContextBuilder": ("git_notes_memory.hooks.context_builder", "ContextBuilder"),
    "TokenBudget": ("git_notes_memory.hooks.models", "TokenBudget"),
    # Signal Detection
    "SignalDetector": ("git_notes_memory.hooks.signal_detector", "SignalDetector"),
    "SIGNAL_PATTERNS": ("git_notes_memory.hooks.signal_detector", "SIGNAL_PATTERNS"),
    "CaptureSignal": ("git_notes_memory.hooks.models", "CaptureSignal"),
    "SignalType": ("git_notes_memory.hooks.models", "SignalType"),
    # Novelty Checking
    "NoveltyChecker": ("git_notes_memory.hooks.novelty_checker", "NoveltyChecker"),
    "NoveltyResult": ("git_notes_memory.hooks.models", "NoveltyResult"),
    # Capture Decision
    "CaptureDecider": ("git_notes_memory.hooks.capture_decider", "CaptureDecider"),
    "CaptureDecision": ("git_notes_memory.hooks.models", "CaptureDecision"),
    "CaptureAction": ("git_notes_memory.hooks.models", "CaptureAction"),
    # Session Analysis
    "SessionAnalyzer": ("git_notes_memory.hooks.session_analyzer", "SessionAnalyzer"),
    "TranscriptContent": (
        "git_notes_memory.hooks.session_analyzer",
        "TranscriptContent",
    ),
    # Project Detection
    "detect_project": ("git_notes_memory.hooks.project_detector", "detect_project"),
}

_LAZY_CACHE: dict[str, Any] = {}


def __getattr__(name: str) -> Any:
    """Lazy loading of hook services.

    This prevents expensive service initialization at import time.
    Uses dictionary-based lookup with caching (ARCH-H-003 pattern).
    """
    # Check cache first
    if name in _LAZY_CACHE:
        return _LAZY_CACHE[name]

    # Check if this is a known lazy import
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        import importlib

        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        _LAZY_CACHE[name] = value
        return value

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    """Return list of public attributes including lazy imports."""
    return list(__all__)


if TYPE_CHECKING:
    from git_notes_memory.hooks.capture_decider import CaptureDecider as CaptureDecider
    from git_notes_memory.hooks.config_loader import HookConfig as HookConfig
    from git_notes_memory.hooks.config_loader import (
        load_hook_config as load_hook_config,
    )
    from git_notes_memory.hooks.context_builder import ContextBuilder as ContextBuilder
    from git_notes_memory.hooks.models import CaptureAction as CaptureAction
    from git_notes_memory.hooks.models import CaptureDecision as CaptureDecision
    from git_notes_memory.hooks.models import CaptureSignal as CaptureSignal
    from git_notes_memory.hooks.models import NoveltyResult as NoveltyResult
    from git_notes_memory.hooks.models import SignalType as SignalType
    from git_notes_memory.hooks.models import TokenBudget as TokenBudget
    from git_notes_memory.hooks.novelty_checker import NoveltyChecker as NoveltyChecker
    from git_notes_memory.hooks.project_detector import detect_project as detect_project
    from git_notes_memory.hooks.session_analyzer import (
        SessionAnalyzer as SessionAnalyzer,
    )
    from git_notes_memory.hooks.session_analyzer import (
        TranscriptContent as TranscriptContent,
    )
    from git_notes_memory.hooks.signal_detector import (
        SIGNAL_PATTERNS as SIGNAL_PATTERNS,
    )
    from git_notes_memory.hooks.signal_detector import SignalDetector as SignalDetector
    from git_notes_memory.hooks.xml_formatter import XMLBuilder as XMLBuilder
