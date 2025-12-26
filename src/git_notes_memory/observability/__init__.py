"""Observability instrumentation for git-notes-memory.

This module provides:
- Metrics collection (counters, histograms, gauges)
- Distributed tracing with span context propagation
- Structured logging with trace context injection
- Session identification for multi-tenant distinguishability

Usage:
    from git_notes_memory.observability import (
        get_config,
        get_metrics,
        measure_duration,
        trace_operation,
        get_current_trace_id,
        get_session_info,
        get_logger,
    )

All features are designed to gracefully degrade when optional
dependencies are not installed. Core package adds zero new
runtime dependencies.

Optional extras for full features:
    pip install git-notes-memory[monitoring]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    # Configuration
    "get_config",
    "ObservabilityConfig",
    "LogLevel",
    "LogFormat",
    # Metrics
    "get_metrics",
    "MetricsCollector",
    # Tracing
    "trace_operation",
    "get_current_span",
    "get_current_trace_id",
    "Span",
    # Session
    "get_session_info",
    "generate_session_id",
    "SessionInfo",
    # Decorators
    "measure_duration",
    # Logging
    "get_logger",
    "StructuredLogger",
]

# =============================================================================
# Lazy Import System (ARCH-H-003)
# =============================================================================
# Use dictionary-based approach for cleaner lazy imports with caching.
# PEP 562 (module-level __getattr__) is the standard pattern for this.

# Mapping of attribute names to their (module_path, attribute_name) tuples
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Config module
    "get_config": ("git_notes_memory.observability.config", "get_config"),
    "ObservabilityConfig": (
        "git_notes_memory.observability.config",
        "ObservabilityConfig",
    ),
    "LogLevel": ("git_notes_memory.observability.config", "LogLevel"),
    "LogFormat": ("git_notes_memory.observability.config", "LogFormat"),
    # Metrics module
    "get_metrics": ("git_notes_memory.observability.metrics", "get_metrics"),
    "MetricsCollector": ("git_notes_memory.observability.metrics", "MetricsCollector"),
    # Tracing module
    "trace_operation": ("git_notes_memory.observability.tracing", "trace_operation"),
    "get_current_span": ("git_notes_memory.observability.tracing", "get_current_span"),
    "get_current_trace_id": (
        "git_notes_memory.observability.tracing",
        "get_current_trace_id",
    ),
    "Span": ("git_notes_memory.observability.tracing", "Span"),
    # Session module
    "get_session_info": ("git_notes_memory.observability.session", "get_session_info"),
    "generate_session_id": (
        "git_notes_memory.observability.session",
        "generate_session_id",
    ),
    "SessionInfo": ("git_notes_memory.observability.session", "SessionInfo"),
    # Decorators module
    "measure_duration": (
        "git_notes_memory.observability.decorators",
        "measure_duration",
    ),
    # Logging module
    "get_logger": ("git_notes_memory.observability.logging", "get_logger"),
    "StructuredLogger": ("git_notes_memory.observability.logging", "StructuredLogger"),
}

# Cache for resolved lazy imports (prevents re-importing on repeated access)
_LAZY_CACHE: dict[str, Any] = {}


def __getattr__(name: str) -> Any:
    """Lazy import implementation for public API.

    This delays loading of submodules until they are actually accessed,
    keeping import time minimal for hook handlers with tight timeouts.

    ARCH-H-003: Refactored from long if-chain to dictionary-based lookup
    with import caching for better performance and maintainability.
    """
    # Check cache first
    if name in _LAZY_CACHE:
        return _LAZY_CACHE[name]

    # Check if this is a known lazy import
    if name in _LAZY_IMPORTS:
        module_path, attr_name = _LAZY_IMPORTS[name]
        # Import the module and get the attribute
        import importlib

        module = importlib.import_module(module_path)
        value = getattr(module, attr_name)
        # Cache for future access
        _LAZY_CACHE[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Return list of public attributes including lazy imports."""
    return list(__all__)


if TYPE_CHECKING:
    # Provide type hints for static analysis while keeping lazy imports at runtime
    from git_notes_memory.observability.config import (
        LogFormat as LogFormat,
    )
    from git_notes_memory.observability.config import (
        LogLevel as LogLevel,
    )
    from git_notes_memory.observability.config import (
        ObservabilityConfig as ObservabilityConfig,
    )
    from git_notes_memory.observability.config import (
        get_config as get_config,
    )
    from git_notes_memory.observability.decorators import (
        measure_duration as measure_duration,
    )
    from git_notes_memory.observability.logging import (
        StructuredLogger as StructuredLogger,
    )
    from git_notes_memory.observability.logging import (
        get_logger as get_logger,
    )
    from git_notes_memory.observability.metrics import (
        MetricsCollector as MetricsCollector,
    )
    from git_notes_memory.observability.metrics import (
        get_metrics as get_metrics,
    )
    from git_notes_memory.observability.session import (
        SessionInfo as SessionInfo,
    )
    from git_notes_memory.observability.session import (
        generate_session_id as generate_session_id,
    )
    from git_notes_memory.observability.session import (
        get_session_info as get_session_info,
    )
    from git_notes_memory.observability.tracing import (
        Span as Span,
    )
    from git_notes_memory.observability.tracing import (
        get_current_span as get_current_span,
    )
    from git_notes_memory.observability.tracing import (
        get_current_trace_id as get_current_trace_id,
    )
    from git_notes_memory.observability.tracing import (
        trace_operation as trace_operation,
    )
