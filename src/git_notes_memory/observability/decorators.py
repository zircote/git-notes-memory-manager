"""Convenience decorators for observability instrumentation.

Provides decorators that combine metrics collection and tracing
for common instrumentation patterns.

Usage:
    from git_notes_memory.observability import measure_duration

    @measure_duration("capture_operation")
    def capture_memory(namespace: str, content: str) -> str:
        # Function body...
        return memory_id

    # Or with custom labels:
    @measure_duration("search_operation", labels={"type": "semantic"})
    async def search_memories(query: str) -> list:
        # Async function body...
        return results
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast, overload

from git_notes_memory.observability.config import get_config
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.tracing import trace_operation

# Type variables for preserving function signatures
F = TypeVar("F", bound=Callable[..., Any])


@overload
def measure_duration(
    metric_name: str,
    *,
    labels: dict[str, str] | None = None,
    record_trace: bool = True,
) -> Callable[[F], F]: ...


@overload
def measure_duration(
    metric_name: Callable[..., Any],
    *,
    labels: dict[str, str] | None = None,
    record_trace: bool = True,
) -> Callable[..., Any]: ...


def measure_duration(
    metric_name: str | Callable[..., Any],
    *,
    labels: dict[str, str] | None = None,
    record_trace: bool = True,
) -> Callable[[F], F] | Callable[..., Any]:
    """Decorator to measure function execution duration.

    Records both a histogram metric and a trace span for the decorated function.
    Works with both sync and async functions.

    Args:
        metric_name: Name for the duration metric (e.g., "capture_duration_ms").
                    If a callable is passed directly, uses the function name.
        labels: Optional labels to attach to the metric.
        record_trace: Whether to also record a trace span (default True).

    Returns:
        Decorated function that records timing metrics.

    Example:
        @measure_duration("capture_duration_ms")
        def capture(namespace: str) -> str:
            ...

        @measure_duration("search_duration_ms", labels={"type": "semantic"})
        async def search(query: str) -> list:
            ...
    """

    def decorator(func: F) -> F:
        # Determine the actual metric name
        name = metric_name if isinstance(metric_name, str) else func.__name__

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            config = get_config()
            if not config.enabled:
                return func(*args, **kwargs)

            start = time.perf_counter()
            error_occurred = False

            try:
                if record_trace and config.tracing_enabled:
                    with trace_operation(name, **(labels or {})):
                        result = func(*args, **kwargs)
                        return result
                else:
                    return func(*args, **kwargs)
            except Exception:
                error_occurred = True
                raise
            finally:
                if config.metrics_enabled:
                    duration_ms = (time.perf_counter() - start) * 1000
                    metric_labels = dict(labels) if labels else {}
                    metric_labels["status"] = "error" if error_occurred else "success"
                    get_metrics().observe(
                        f"{name}_duration_ms",
                        duration_ms,
                        labels=metric_labels,
                    )

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            config = get_config()
            if not config.enabled:
                return await func(*args, **kwargs)

            start = time.perf_counter()
            error_occurred = False

            try:
                if record_trace and config.tracing_enabled:
                    with trace_operation(name, **(labels or {})):
                        result = await func(*args, **kwargs)
                        return result
                else:
                    return await func(*args, **kwargs)
            except Exception:
                error_occurred = True
                raise
            finally:
                if config.metrics_enabled:
                    duration_ms = (time.perf_counter() - start) * 1000
                    metric_labels = dict(labels) if labels else {}
                    metric_labels["status"] = "error" if error_occurred else "success"
                    get_metrics().observe(
                        f"{name}_duration_ms",
                        duration_ms,
                        labels=metric_labels,
                    )

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    # Handle being called with or without arguments
    if callable(metric_name):
        # Called as @measure_duration without parentheses
        return decorator(metric_name)

    return decorator


def timed_context(
    metric_name: str,
    labels: dict[str, str] | None = None,
) -> TimedContext:
    """Create a context manager for timing a code block.

    Use when you need to time a block of code rather than a whole function.

    Args:
        metric_name: Name for the duration metric.
        labels: Optional labels to attach to the metric.

    Returns:
        Context manager that records timing on exit.

    Example:
        with timed_context("batch_processing_ms", {"batch_size": "100"}):
            process_batch(items)
    """
    return TimedContext(metric_name, labels)


class TimedContext:
    """Context manager for timing code blocks.

    Records duration as a histogram metric on exit.
    """

    def __init__(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        self.metric_name = metric_name
        self.labels = labels or {}
        self.start_time: float = 0.0
        self.duration_ms: float = 0.0

    def __enter__(self) -> TimedContext:
        self.start_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000

        config = get_config()
        if config.enabled and config.metrics_enabled:
            metric_labels = dict(self.labels)
            metric_labels["status"] = "error" if exc_type else "success"
            get_metrics().observe(
                f"{self.metric_name}_duration_ms",
                self.duration_ms,
                labels=metric_labels,
            )


async def timed_async_context(
    metric_name: str,
    labels: dict[str, str] | None = None,
) -> AsyncTimedContext:
    """Create an async context manager for timing async code blocks.

    Args:
        metric_name: Name for the duration metric.
        labels: Optional labels to attach to the metric.

    Returns:
        Async context manager that records timing on exit.

    Example:
        async with timed_async_context("async_op_ms"):
            await some_async_operation()
    """
    return AsyncTimedContext(metric_name, labels)


class AsyncTimedContext:
    """Async context manager for timing async code blocks."""

    def __init__(
        self,
        metric_name: str,
        labels: dict[str, str] | None = None,
    ) -> None:
        self.metric_name = metric_name
        self.labels = labels or {}
        self.start_time: float = 0.0
        self.duration_ms: float = 0.0

    async def __aenter__(self) -> AsyncTimedContext:
        self.start_time = time.perf_counter()
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000

        config = get_config()
        if config.enabled and config.metrics_enabled:
            metric_labels = dict(self.labels)
            metric_labels["status"] = "error" if exc_type else "success"
            get_metrics().observe(
                f"{self.metric_name}_duration_ms",
                self.duration_ms,
                labels=metric_labels,
            )
