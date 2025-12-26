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

# Lazy imports to avoid loading optional dependencies at import time
# This ensures the core package remains lightweight and fast to import

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


def __getattr__(name: str) -> Any:
    """Lazy import implementation for public API.

    This delays loading of submodules until they are actually accessed,
    keeping import time minimal for hook handlers with tight timeouts.
    """
    if name == "get_config":
        from git_notes_memory.observability.config import get_config

        return get_config

    if name == "ObservabilityConfig":
        from git_notes_memory.observability.config import ObservabilityConfig

        return ObservabilityConfig

    if name == "LogLevel":
        from git_notes_memory.observability.config import LogLevel

        return LogLevel

    if name == "LogFormat":
        from git_notes_memory.observability.config import LogFormat

        return LogFormat

    if name == "get_metrics":
        from git_notes_memory.observability.metrics import get_metrics

        return get_metrics

    if name == "MetricsCollector":
        from git_notes_memory.observability.metrics import MetricsCollector

        return MetricsCollector

    if name == "trace_operation":
        from git_notes_memory.observability.tracing import trace_operation

        return trace_operation

    if name == "get_current_span":
        from git_notes_memory.observability.tracing import get_current_span

        return get_current_span

    if name == "get_current_trace_id":
        from git_notes_memory.observability.tracing import get_current_trace_id

        return get_current_trace_id

    if name == "Span":
        from git_notes_memory.observability.tracing import Span

        return Span

    if name == "get_session_info":
        from git_notes_memory.observability.session import get_session_info

        return get_session_info

    if name == "generate_session_id":
        from git_notes_memory.observability.session import generate_session_id

        return generate_session_id

    if name == "SessionInfo":
        from git_notes_memory.observability.session import SessionInfo

        return SessionInfo

    if name == "measure_duration":
        from git_notes_memory.observability.decorators import measure_duration

        return measure_duration

    if name == "get_logger":
        from git_notes_memory.observability.logging import get_logger

        return get_logger

    if name == "StructuredLogger":
        from git_notes_memory.observability.logging import StructuredLogger

        return StructuredLogger

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
