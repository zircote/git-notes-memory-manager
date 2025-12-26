"""Distributed tracing with span context propagation.

Provides lightweight tracing without external dependencies using
Python's contextvars for thread-safe context propagation.

Usage:
    from git_notes_memory.observability import (
        trace_operation,
        get_current_span,
        get_current_trace_id,
    )

    with trace_operation("capture", namespace="decisions") as span:
        # Do work...
        span.set_tag("memory_id", "abc123")

    # Access current trace context anywhere in call stack
    trace_id = get_current_trace_id()
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from git_notes_memory.observability.config import get_config

# Context variable for span propagation
_current_span: ContextVar[Span | None] = ContextVar("current_span", default=None)

# Context variable for trace ID (persists across span creation)
_current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)


def _generate_id() -> str:
    """Generate a short unique ID suitable for spans."""
    return uuid.uuid4().hex[:16]


def _generate_trace_id() -> str:
    """Generate a unique trace ID."""
    return uuid.uuid4().hex


@dataclass
class Span:
    """A unit of work within a trace.

    Represents a single operation with timing, tags, and parent relationship.
    Immutable after creation except for tags which can be added.
    """

    trace_id: str
    span_id: str
    operation: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    parent_span_id: str | None = None
    tags: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"
    error_message: str | None = None

    @property
    def duration_ms(self) -> float | None:
        """Duration in milliseconds, or None if not yet ended."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000

    @property
    def start_datetime(self) -> datetime:
        """Start time as datetime."""
        return datetime.fromtimestamp(self.start_time, tz=UTC)

    @property
    def end_datetime(self) -> datetime | None:
        """End time as datetime, or None if not yet ended."""
        if self.end_time is None:
            return None
        return datetime.fromtimestamp(self.end_time, tz=UTC)

    def set_tag(self, key: str, value: Any) -> None:
        """Add or update a tag on this span.

        Args:
            key: Tag name.
            value: Tag value (should be JSON-serializable).
        """
        self.tags[key] = value

    def set_status(self, status: str, error_message: str | None = None) -> None:
        """Set the span status.

        Args:
            status: Status string ("ok", "error").
            error_message: Optional error message for error status.
        """
        self.status = status
        self.error_message = error_message

    def finish(self) -> None:
        """Mark the span as finished, recording end time."""
        if self.end_time is None:
            self.end_time = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "operation": self.operation,
            "start_time": self.start_datetime.isoformat(),
            "end_time": self.end_datetime.isoformat() if self.end_datetime else None,
            "duration_ms": self.duration_ms,
            "parent_span_id": self.parent_span_id,
            "tags": self.tags,
            "status": self.status,
            "error_message": self.error_message,
        }


# Store completed spans for later export
_completed_spans: list[Span] = []
_max_spans: int = 1000  # Rolling buffer


def _record_span(span: Span) -> None:
    """Record a completed span for potential export.

    Uses a rolling buffer to bound memory usage.
    """
    _completed_spans.append(span)
    # Trim if over limit
    while len(_completed_spans) > _max_spans:
        _completed_spans.pop(0)


def get_completed_spans() -> list[Span]:
    """Get all completed spans for export.

    Returns:
        List of completed Span objects.
    """
    return list(_completed_spans)


def clear_completed_spans() -> None:
    """Clear the completed spans buffer.

    Typically called after successful export.
    """
    _completed_spans.clear()


def get_current_span() -> Span | None:
    """Get the current span from context.

    Returns:
        Current Span or None if not in a traced context.
    """
    return _current_span.get()


def get_current_trace_id() -> str | None:
    """Get the current trace ID from context.

    Returns:
        Current trace ID or None if not in a traced context.
    """
    return _current_trace_id.get()


def get_current_span_id() -> str | None:
    """Get the current span ID from context.

    Returns:
        Current span ID or None if not in a traced context.
    """
    span = get_current_span()
    return span.span_id if span else None


@contextmanager
def trace_operation(
    operation: str,
    **tags: Any,
) -> Generator[Span, None, None]:
    """Context manager for tracing an operation.

    Creates a new span and sets it as the current span for the duration
    of the context. Automatically records timing and handles nested spans.

    Args:
        operation: Name of the operation being traced.
        **tags: Additional tags to add to the span.

    Yields:
        The created Span object.

    Example:
        with trace_operation("capture", namespace="decisions") as span:
            # Do work
            span.set_tag("memory_id", result.id)
    """
    config = get_config()

    # If tracing disabled, yield a dummy span but don't record
    if not config.enabled or not config.tracing_enabled:
        dummy_span = Span(
            trace_id="",
            span_id="",
            operation=operation,
            tags=dict(tags),
        )
        yield dummy_span
        return

    # Get or create trace ID
    trace_id = _current_trace_id.get()
    if trace_id is None:
        trace_id = _generate_trace_id()

    # Get parent span if exists
    parent_span = _current_span.get()
    parent_span_id = parent_span.span_id if parent_span else None

    # Create new span
    span = Span(
        trace_id=trace_id,
        span_id=_generate_id(),
        operation=operation,
        parent_span_id=parent_span_id,
        tags=dict(tags),
    )

    # Set context
    trace_token = _current_trace_id.set(trace_id)
    span_token = _current_span.set(span)

    try:
        yield span
    except Exception as e:
        span.set_status("error", str(e))
        raise
    finally:
        span.finish()
        _record_span(span)

        # Restore context
        _current_span.reset(span_token)
        _current_trace_id.reset(trace_token)


def start_trace(trace_id: str | None = None) -> str:
    """Start a new trace or continue an existing one.

    Args:
        trace_id: Optional trace ID to continue. Generates new if None.

    Returns:
        The trace ID being used.
    """
    if trace_id is None:
        trace_id = _generate_trace_id()
    _current_trace_id.set(trace_id)
    return trace_id


def end_trace() -> None:
    """End the current trace."""
    _current_trace_id.set(None)
    _current_span.set(None)
