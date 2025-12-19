"""Hook services for Claude Code integration.

This module provides hook handlers and utilities for integrating the memory
system with Claude Code's hook mechanism. It enables:
- Automatic context injection at session start (SessionStart hook)
- Capture signal detection in user prompts (UserPromptSubmit hook)
- Session-end processing and cleanup (Stop hook)

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
    "CaptureSignal",
    "SignalType",
    # Capture Decision
    "CaptureDecider",
    "CaptureDecision",
    "CaptureAction",
    # Project Detection
    "detect_project",
]


def __getattr__(name: str) -> object:
    """Lazy loading of hook services.

    This prevents expensive service initialization at import time.
    """
    # Configuration
    if name == "HookConfig":
        from git_notes_memory.hooks.config_loader import HookConfig

        return HookConfig
    if name == "load_hook_config":
        from git_notes_memory.hooks.config_loader import load_hook_config

        return load_hook_config

    # XML Formatting
    if name == "XMLBuilder":
        from git_notes_memory.hooks.xml_formatter import XMLBuilder

        return XMLBuilder

    # Context Building
    if name == "ContextBuilder":
        from git_notes_memory.hooks.context_builder import ContextBuilder

        return ContextBuilder
    if name == "TokenBudget":
        from git_notes_memory.hooks.models import TokenBudget

        return TokenBudget

    # Signal Detection
    if name == "SignalDetector":
        from git_notes_memory.hooks.signal_detector import SignalDetector

        return SignalDetector
    if name == "CaptureSignal":
        from git_notes_memory.hooks.models import CaptureSignal

        return CaptureSignal
    if name == "SignalType":
        from git_notes_memory.hooks.models import SignalType

        return SignalType

    # Capture Decision
    if name == "CaptureDecider":
        from git_notes_memory.hooks.capture_decider import CaptureDecider

        return CaptureDecider
    if name == "CaptureDecision":
        from git_notes_memory.hooks.models import CaptureDecision

        return CaptureDecision
    if name == "CaptureAction":
        from git_notes_memory.hooks.models import CaptureAction

        return CaptureAction

    # Project Detection
    if name == "detect_project":
        from git_notes_memory.hooks.project_detector import detect_project

        return detect_project

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
