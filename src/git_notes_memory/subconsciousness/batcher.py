"""Request batcher for LLM API calls.

This module implements a request batcher that collects multiple
LLM requests and sends them together to reduce API call overhead.

The batcher supports:
- Timeout-based flush (send after N milliseconds)
- Size-based flush (send after N requests collected)
- Partial batch failure handling
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .models import LLMRequest, LLMResponse

if TYPE_CHECKING:
    pass

__all__ = [
    "RequestBatcher",
    "BatchResult",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Types
# =============================================================================


BatchExecutor = Callable[
    [list[LLMRequest]],
    Coroutine[Any, Any, list[LLMResponse]],
]


# =============================================================================
# Models
# =============================================================================


@dataclass(frozen=True)
class BatchResult:
    """Result from a batched request.

    Attributes:
        request: The original request.
        response: The response if successful.
        error: The error if failed.
    """

    request: LLMRequest
    response: LLMResponse | None = None
    error: Exception | None = None

    @property
    def success(self) -> bool:
        """Check if request succeeded."""
        return self.response is not None and self.error is None


# =============================================================================
# Pending Request
# =============================================================================


@dataclass
class _PendingRequest:
    """Internal tracking for pending batched requests."""

    request: LLMRequest
    future: asyncio.Future[LLMResponse]


# =============================================================================
# Request Batcher
# =============================================================================


@dataclass
class RequestBatcher:
    """Batches LLM requests for efficient processing.

    Collects requests and sends them in batches based on:
    - Maximum batch size (send when N requests accumulated)
    - Maximum wait time (send after N milliseconds)

    The batcher is async-safe and handles concurrent submissions.

    Attributes:
        executor: Async function to execute batched requests.
        max_batch_size: Maximum requests per batch.
        max_wait_ms: Maximum wait time before flushing batch.
        name: Optional name for logging.
    """

    executor: BatchExecutor
    max_batch_size: int = 10
    max_wait_ms: int = 5000
    name: str = "default"

    _pending: list[_PendingRequest] = field(default_factory=list, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _flush_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _closed: bool = field(default=False, repr=False)

    async def submit(self, request: LLMRequest) -> LLMResponse:
        """Submit a request for batched execution.

        The request will be batched with others and executed when:
        - The batch reaches max_batch_size, or
        - max_wait_ms has elapsed since the first request in batch

        Args:
            request: The LLM request to submit.

        Returns:
            LLMResponse when the batch is executed.

        Raises:
            RuntimeError: If batcher is closed.
            Exception: If the request fails during batch execution.
        """
        if self._closed:
            msg = "Batcher is closed"
            raise RuntimeError(msg)

        loop = asyncio.get_event_loop()
        future: asyncio.Future[LLMResponse] = loop.create_future()

        async with self._lock:
            pending = _PendingRequest(request=request, future=future)
            self._pending.append(pending)

            # Check if we should flush immediately (size-based)
            if len(self._pending) >= self.max_batch_size:
                # Flush synchronously under lock
                await self._flush_batch()
            elif len(self._pending) == 1:
                # First request in batch, schedule timeout flush
                self._schedule_flush()

        # Wait for result
        return await future

    async def flush(self) -> None:
        """Force flush any pending requests.

        Use this to ensure all pending requests are sent before shutdown.
        """
        async with self._lock:
            if self._pending:
                await self._flush_batch()

    async def close(self) -> None:
        """Close the batcher and flush pending requests.

        After closing, no new requests can be submitted.
        """
        self._closed = True
        await self.flush()

        # Cancel scheduled flush
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task

    def pending_count(self) -> int:
        """Get count of pending requests."""
        return len(self._pending)

    def _schedule_flush(self) -> None:
        """Schedule a timeout-based flush."""
        if self._flush_task and not self._flush_task.done():
            # Already scheduled
            return

        async def _delayed_flush() -> None:
            await asyncio.sleep(self.max_wait_ms / 1000)
            async with self._lock:
                if self._pending:
                    await self._flush_batch()

        self._flush_task = asyncio.create_task(_delayed_flush())

    async def _flush_batch(self) -> None:
        """Flush current batch (must be called with lock held).

        Executes all pending requests and resolves their futures.
        """
        if not self._pending:
            return

        # Cancel scheduled flush
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()

        # Take all pending requests
        batch = self._pending.copy()
        self._pending.clear()

        # Extract just the requests
        requests = [p.request for p in batch]

        logger.debug(
            "Flushing batch of %d requests (batcher=%s)",
            len(requests),
            self.name,
        )

        try:
            # Execute batch
            responses = await self.executor(requests)

            # Match responses to futures
            for i, pending in enumerate(batch):
                if i < len(responses):
                    pending.future.set_result(responses[i])
                else:
                    error = RuntimeError(f"No response for request {i} in batch")
                    pending.future.set_exception(error)

        except Exception as e:
            # Batch execution failed, fail all futures
            logger.error(
                "Batch execution failed: %s (batcher=%s)",
                e,
                self.name,
            )
            for pending in batch:
                if not pending.future.done():
                    pending.future.set_exception(e)


# =============================================================================
# Sequential Fallback
# =============================================================================


class SequentialBatcher:
    """A non-batching "batcher" that executes requests sequentially.

    Useful as a fallback when batching is not beneficial or when
    the provider doesn't support batch operations.
    """

    def __init__(
        self,
        executor: Callable[[LLMRequest], Coroutine[Any, Any, LLMResponse]],
    ) -> None:
        """Initialize with a single-request executor.

        Args:
            executor: Async function to execute single requests.
        """
        self._executor = executor

    async def submit(self, request: LLMRequest) -> LLMResponse:
        """Execute request immediately (no batching).

        Args:
            request: The LLM request to execute.

        Returns:
            LLMResponse from the executor.
        """
        return await self._executor(request)

    async def flush(self) -> None:
        """No-op for sequential execution."""
        pass

    async def close(self) -> None:
        """No-op for sequential execution."""
        pass

    def pending_count(self) -> int:
        """Always 0 for sequential execution."""
        return 0
