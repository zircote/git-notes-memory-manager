"""Tests for distributed tracing."""

from __future__ import annotations

import pytest

from git_notes_memory.observability.config import reset_config
from git_notes_memory.observability.tracing import (
    Span,
    clear_completed_spans,
    end_trace,
    get_completed_spans,
    get_current_span,
    get_current_span_id,
    get_current_trace_id,
    start_trace,
    trace_operation,
)


class TestSpan:
    """Tests for Span dataclass."""

    def test_span_creation(self) -> None:
        """Test creating a span."""
        span = Span(
            trace_id="trace123",
            span_id="span456",
            operation="test_operation",
        )

        assert span.trace_id == "trace123"
        assert span.span_id == "span456"
        assert span.operation == "test_operation"
        assert span.status == "ok"
        assert span.error_message is None
        assert span.parent_span_id is None
        assert span.tags == {}

    def test_duration_ms_before_finish(self) -> None:
        """Test duration is None before finish."""
        span = Span(trace_id="t1", span_id="s1", operation="op")
        assert span.duration_ms is None

    def test_duration_ms_after_finish(self) -> None:
        """Test duration calculated after finish."""
        span = Span(trace_id="t1", span_id="s1", operation="op")
        span.finish()

        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_set_tag(self) -> None:
        """Test setting tags on span."""
        span = Span(trace_id="t1", span_id="s1", operation="op")
        span.set_tag("namespace", "decisions")
        span.set_tag("memory_id", "abc123")

        assert span.tags == {"namespace": "decisions", "memory_id": "abc123"}

    def test_set_status(self) -> None:
        """Test setting span status."""
        span = Span(trace_id="t1", span_id="s1", operation="op")
        span.set_status("error", "Something went wrong")

        assert span.status == "error"
        assert span.error_message == "Something went wrong"

    def test_start_datetime(self) -> None:
        """Test start_datetime property."""
        span = Span(trace_id="t1", span_id="s1", operation="op")
        dt = span.start_datetime

        assert dt is not None
        assert dt.tzinfo is not None  # Has timezone

    def test_end_datetime_before_finish(self) -> None:
        """Test end_datetime is None before finish."""
        span = Span(trace_id="t1", span_id="s1", operation="op")
        assert span.end_datetime is None

    def test_end_datetime_after_finish(self) -> None:
        """Test end_datetime set after finish."""
        span = Span(trace_id="t1", span_id="s1", operation="op")
        span.finish()

        assert span.end_datetime is not None
        assert span.end_datetime >= span.start_datetime

    def test_finish_idempotent(self) -> None:
        """Test finish only sets end_time once."""
        span = Span(trace_id="t1", span_id="s1", operation="op")
        span.finish()
        first_end = span.end_time

        span.finish()

        assert span.end_time == first_end

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        span = Span(
            trace_id="t1",
            span_id="s1",
            operation="test_op",
            tags={"key": "value"},
        )
        span.finish()

        data = span.to_dict()

        assert data["trace_id"] == "t1"
        assert data["span_id"] == "s1"
        assert data["operation"] == "test_op"
        assert data["tags"] == {"key": "value"}
        assert data["status"] == "ok"
        assert data["start_time"] is not None
        assert data["end_time"] is not None
        assert data["duration_ms"] is not None


class TestTraceOperation:
    """Tests for trace_operation context manager."""

    def setup_method(self) -> None:
        """Reset state before each test."""
        reset_config()
        clear_completed_spans()
        end_trace()

    def teardown_method(self) -> None:
        """Reset state after each test."""
        reset_config()
        clear_completed_spans()
        end_trace()

    def test_creates_span(self) -> None:
        """Test trace_operation creates a span."""
        with trace_operation("test_operation") as span:
            assert span.operation == "test_operation"
            assert span.trace_id != ""
            assert span.span_id != ""

    def test_records_span(self) -> None:
        """Test span is recorded after context exit."""
        with trace_operation("test_operation"):
            pass

        spans = get_completed_spans()
        assert len(spans) == 1
        assert spans[0].operation == "test_operation"
        assert spans[0].end_time is not None

    def test_propagates_trace_id(self) -> None:
        """Test trace_id propagates to nested spans."""
        with trace_operation("outer") as outer_span:
            outer_trace_id = outer_span.trace_id
            with trace_operation("inner") as inner_span:
                assert inner_span.trace_id == outer_trace_id
                assert inner_span.parent_span_id == outer_span.span_id

    def test_tags_from_kwargs(self) -> None:
        """Test tags passed via kwargs."""
        with trace_operation("test_op", namespace="decisions", count=5) as span:
            assert span.tags["namespace"] == "decisions"
            assert span.tags["count"] == 5

    def test_records_error(self) -> None:
        """Test errors are recorded on span."""
        with pytest.raises(ValueError, match="test error"):
            with trace_operation("failing_op"):
                raise ValueError("test error")

        spans = get_completed_spans()
        assert len(spans) == 1
        assert spans[0].status == "error"
        assert spans[0].error_message == "test error"

    def test_context_functions(self) -> None:
        """Test context accessor functions."""
        assert get_current_span() is None
        assert get_current_trace_id() is None
        assert get_current_span_id() is None

        with trace_operation("test_op") as span:
            assert get_current_span() is span
            assert get_current_trace_id() == span.trace_id
            assert get_current_span_id() == span.span_id

        # Restored after exit
        assert get_current_span() is None

    def test_disabled_tracing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test tracing disabled via config."""
        monkeypatch.setenv("MEMORY_PLUGIN_TRACING_ENABLED", "false")
        reset_config()

        with trace_operation("test_op") as span:
            # Returns dummy span
            assert span.trace_id == ""
            assert span.span_id == ""

        # No spans recorded
        assert len(get_completed_spans()) == 0


class TestStartEndTrace:
    """Tests for start_trace and end_trace."""

    def setup_method(self) -> None:
        """Reset state."""
        end_trace()

    def teardown_method(self) -> None:
        """Reset state."""
        end_trace()

    def test_start_trace_generates_id(self) -> None:
        """Test start_trace generates a trace ID."""
        trace_id = start_trace()
        assert trace_id is not None
        assert len(trace_id) > 0

    def test_start_trace_with_id(self) -> None:
        """Test starting trace with specific ID."""
        trace_id = start_trace("custom-trace-id")
        assert trace_id == "custom-trace-id"
        assert get_current_trace_id() == "custom-trace-id"

    def test_end_trace(self) -> None:
        """Test ending trace clears context."""
        start_trace()
        assert get_current_trace_id() is not None

        end_trace()
        assert get_current_trace_id() is None


class TestCompletedSpans:
    """Tests for completed spans buffer."""

    def setup_method(self) -> None:
        """Clear spans."""
        clear_completed_spans()
        end_trace()
        reset_config()

    def teardown_method(self) -> None:
        """Clear spans."""
        clear_completed_spans()
        end_trace()
        reset_config()

    def test_get_completed_spans(self) -> None:
        """Test getting completed spans."""
        with trace_operation("op1"):
            pass
        with trace_operation("op2"):
            pass

        spans = get_completed_spans()
        assert len(spans) == 2
        assert spans[0].operation == "op1"
        assert spans[1].operation == "op2"

    def test_clear_completed_spans(self) -> None:
        """Test clearing completed spans."""
        with trace_operation("op"):
            pass

        clear_completed_spans()

        assert len(get_completed_spans()) == 0
