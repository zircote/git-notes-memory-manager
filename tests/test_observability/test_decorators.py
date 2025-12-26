"""Tests for observability decorators."""

from __future__ import annotations

import asyncio
import json

import pytest

from git_notes_memory.observability.config import reset_config
from git_notes_memory.observability.decorators import (
    AsyncTimedContext,
    measure_duration,
    timed_context,
)
from git_notes_memory.observability.metrics import get_metrics, reset_metrics
from git_notes_memory.observability.tracing import clear_completed_spans, end_trace


class TestMeasureDuration:
    """Tests for measure_duration decorator."""

    def setup_method(self) -> None:
        """Reset state before each test."""
        reset_config()
        reset_metrics()
        clear_completed_spans()
        end_trace()

    def teardown_method(self) -> None:
        """Reset state after each test."""
        reset_config()
        reset_metrics()
        clear_completed_spans()
        end_trace()

    def test_with_metric_name(self) -> None:
        """Test decorator with explicit metric name."""

        @measure_duration("my_operation")
        def do_work() -> str:
            return "done"

        result = do_work()

        assert result == "done"

        # Check metric was recorded
        data = json.loads(get_metrics().export_json())
        assert "my_operation_duration_ms" in data["histograms"]

    def test_without_parentheses(self) -> None:
        """Test decorator without arguments."""

        @measure_duration
        def simple_function() -> int:
            return 42

        result = simple_function()

        assert result == 42

        # Check metric was recorded with function name
        data = json.loads(get_metrics().export_json())
        assert "simple_function_duration_ms" in data["histograms"]

    def test_with_labels(self) -> None:
        """Test decorator with custom labels."""

        @measure_duration("labeled_op", labels={"type": "test"})
        def labeled_work() -> None:
            pass

        labeled_work()

        data = json.loads(get_metrics().export_json())
        hist_data = data["histograms"]["labeled_op_duration_ms"][0]
        # Labels include the custom label + status
        assert hist_data["labels"]["type"] == "test"
        assert hist_data["labels"]["status"] == "success"

    def test_records_error_status(self) -> None:
        """Test error status recorded on exception."""

        @measure_duration("failing_op")
        def failing_work() -> None:
            raise ValueError("intentional error")

        with pytest.raises(ValueError, match="intentional error"):
            failing_work()

        data = json.loads(get_metrics().export_json())
        hist_data = data["histograms"]["failing_op_duration_ms"][0]
        assert hist_data["labels"]["status"] == "error"

    def test_async_function(self) -> None:
        """Test decorator works with async functions."""

        @measure_duration("async_op")
        async def async_work() -> str:
            await asyncio.sleep(0.001)
            return "async done"

        result = asyncio.run(async_work())

        assert result == "async done"

        data = json.loads(get_metrics().export_json())
        assert "async_op_duration_ms" in data["histograms"]

    def test_preserves_function_metadata(self) -> None:
        """Test decorator preserves function name and docstring."""

        @measure_duration("test_op")
        def documented_function() -> None:
            """This is a docstring."""
            pass

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a docstring."

    def test_no_trace_option(self) -> None:
        """Test disabling trace recording."""

        @measure_duration("no_trace_op", record_trace=False)
        def no_trace_work() -> None:
            pass

        no_trace_work()

        # Metric should still be recorded
        data = json.loads(get_metrics().export_json())
        assert "no_trace_op_duration_ms" in data["histograms"]

    def test_disabled_observability(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test decorator when observability is disabled."""
        monkeypatch.setenv("MEMORY_PLUGIN_OBSERVABILITY_ENABLED", "false")
        reset_config()

        @measure_duration("disabled_op")
        def disabled_work() -> str:
            return "still works"

        result = disabled_work()

        assert result == "still works"


class TestTimedContext:
    """Tests for TimedContext context manager."""

    def setup_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_metrics()

    def teardown_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_metrics()

    def test_basic_timing(self) -> None:
        """Test basic timing context."""
        with timed_context("block_timing") as ctx:
            pass

        assert ctx.duration_ms >= 0

        data = json.loads(get_metrics().export_json())
        assert "block_timing_duration_ms" in data["histograms"]

    def test_with_labels(self) -> None:
        """Test timing context with labels."""
        with timed_context("labeled_block", labels={"batch_size": "100"}) as ctx:
            pass

        assert ctx.duration_ms >= 0

        data = json.loads(get_metrics().export_json())
        hist_data = data["histograms"]["labeled_block_duration_ms"][0]
        assert hist_data["labels"]["batch_size"] == "100"

    def test_error_status(self) -> None:
        """Test error status on exception."""
        with pytest.raises(RuntimeError):
            with timed_context("error_block"):
                raise RuntimeError("test error")

        data = json.loads(get_metrics().export_json())
        hist_data = data["histograms"]["error_block_duration_ms"][0]
        assert hist_data["labels"]["status"] == "error"

    def test_success_status(self) -> None:
        """Test success status on normal exit."""
        with timed_context("success_block"):
            pass

        data = json.loads(get_metrics().export_json())
        hist_data = data["histograms"]["success_block_duration_ms"][0]
        assert hist_data["labels"]["status"] == "success"


class TestAsyncTimedContext:
    """Tests for AsyncTimedContext."""

    def setup_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_metrics()

    def teardown_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_metrics()

    def test_async_timing(self) -> None:
        """Test async timing context."""

        async def async_block() -> float:
            ctx = AsyncTimedContext("async_block_timing")
            async with ctx:
                await asyncio.sleep(0.001)
            return ctx.duration_ms

        duration = asyncio.run(async_block())

        assert duration >= 1.0  # At least 1ms

        data = json.loads(get_metrics().export_json())
        assert "async_block_timing_duration_ms" in data["histograms"]

    def test_async_error_status(self) -> None:
        """Test async error status."""

        async def failing_block() -> None:
            async with AsyncTimedContext("async_error_block"):
                await asyncio.sleep(0.001)
                raise ValueError("async error")

        with pytest.raises(ValueError, match="async error"):
            asyncio.run(failing_block())

        data = json.loads(get_metrics().export_json())
        hist_data = data["histograms"]["async_error_block_duration_ms"][0]
        assert hist_data["labels"]["status"] == "error"
