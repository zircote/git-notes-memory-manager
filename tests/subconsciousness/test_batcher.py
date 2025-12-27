"""Tests for request batcher functionality.

TEST-H-005: Tests for batcher.py.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from git_notes_memory.subconsciousness.batcher import (
    BatchResult,
    RequestBatcher,
    SequentialBatcher,
)
from git_notes_memory.subconsciousness.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    MessageRole,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_request() -> LLMRequest:
    """Create a sample LLM request."""
    return LLMRequest(
        messages=(
            LLMMessage(role=MessageRole.SYSTEM, content="You are helpful."),
            LLMMessage(role=MessageRole.USER, content="Hello"),
        ),
        max_tokens=100,
        temperature=0.7,
    )


@pytest.fixture
def sample_response() -> LLMResponse:
    """Create a sample LLM response."""
    return LLMResponse(
        content="Hello! How can I help?",
        model="gpt-5-nano",
        usage=LLMUsage.from_tokens(
            prompt_tokens=10,
            completion_tokens=5,
            input_cost_per_million=0.10,
            output_cost_per_million=0.40,
        ),
        latency_ms=100,
    )


@pytest.fixture
def mock_executor(sample_response: LLMResponse) -> AsyncMock:
    """Create a mock batch executor."""
    executor = AsyncMock()
    executor.return_value = [sample_response]
    return executor


# =============================================================================
# BatchResult Tests
# =============================================================================


class TestBatchResult:
    """Tests for the BatchResult dataclass."""

    def test_success_with_response(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test that success is True when response is present."""
        result = BatchResult(request=sample_request, response=sample_response)
        assert result.success is True
        assert result.error is None

    def test_failure_with_error(self, sample_request: LLMRequest) -> None:
        """Test that success is False when error is present."""
        error = ValueError("API error")
        result = BatchResult(request=sample_request, error=error)
        assert result.success is False
        assert result.response is None

    def test_failure_with_both_response_and_error(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test that success is False when both response and error present."""
        error = ValueError("Partial failure")
        result = BatchResult(
            request=sample_request, response=sample_response, error=error
        )
        assert result.success is False

    def test_batch_result_is_frozen(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test that BatchResult is immutable."""
        result = BatchResult(request=sample_request, response=sample_response)
        with pytest.raises(AttributeError):
            result.response = None  # type: ignore[misc]


# =============================================================================
# RequestBatcher Initialization Tests
# =============================================================================


class TestRequestBatcherInit:
    """Tests for RequestBatcher initialization."""

    def test_init_with_defaults(self, mock_executor: AsyncMock) -> None:
        """Test initialization with default values."""
        batcher = RequestBatcher(executor=mock_executor)
        assert batcher.max_batch_size == 10
        assert batcher.max_wait_ms == 5000
        assert batcher.name == "default"
        assert batcher.pending_count() == 0

    def test_init_with_custom_values(self, mock_executor: AsyncMock) -> None:
        """Test initialization with custom values."""
        batcher = RequestBatcher(
            executor=mock_executor,
            max_batch_size=5,
            max_wait_ms=1000,
            name="test-batcher",
        )
        assert batcher.max_batch_size == 5
        assert batcher.max_wait_ms == 1000
        assert batcher.name == "test-batcher"


# =============================================================================
# RequestBatcher submit Tests
# =============================================================================


class TestRequestBatcherSubmit:
    """Tests for the submit method."""

    @pytest.mark.asyncio
    async def test_submit_single_request(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test submitting a single request."""
        executor = AsyncMock(return_value=[sample_response])
        batcher = RequestBatcher(executor=executor, max_batch_size=1, max_wait_ms=5000)

        result = await batcher.submit(sample_request)

        assert result == sample_response
        executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_triggers_flush_at_max_size(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test that reaching max_batch_size triggers flush."""
        responses = [sample_response, sample_response, sample_response]
        executor = AsyncMock(return_value=responses)
        batcher = RequestBatcher(executor=executor, max_batch_size=3, max_wait_ms=60000)

        # Submit 3 requests concurrently
        results = await asyncio.gather(
            batcher.submit(sample_request),
            batcher.submit(sample_request),
            batcher.submit(sample_request),
        )

        assert len(results) == 3
        # Executor should be called at least once
        assert executor.call_count >= 1

    @pytest.mark.asyncio
    async def test_submit_closed_batcher_raises(
        self, sample_request: LLMRequest, mock_executor: AsyncMock
    ) -> None:
        """Test that submitting to closed batcher raises error."""
        batcher = RequestBatcher(executor=mock_executor)
        await batcher.close()

        with pytest.raises(RuntimeError, match="Batcher is closed"):
            await batcher.submit(sample_request)

    @pytest.mark.asyncio
    async def test_submit_timeout_flush(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test that timeout triggers flush."""
        executor = AsyncMock(return_value=[sample_response])
        batcher = RequestBatcher(
            executor=executor,
            max_batch_size=100,  # Won't trigger size-based
            max_wait_ms=100,  # 100ms timeout
        )

        # Submit one request (won't hit size threshold)
        result = await batcher.submit(sample_request)

        assert result == sample_response
        executor.assert_called_once()
        await batcher.close()


# =============================================================================
# RequestBatcher flush Tests
# =============================================================================


class TestRequestBatcherFlush:
    """Tests for the flush method."""

    @pytest.mark.asyncio
    async def test_flush_empty_batcher(self, mock_executor: AsyncMock) -> None:
        """Test flushing empty batcher is no-op."""
        batcher = RequestBatcher(executor=mock_executor)
        await batcher.flush()
        mock_executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_manual_flush(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test manual flush sends pending requests."""
        executor = AsyncMock(return_value=[sample_response])
        batcher = RequestBatcher(
            executor=executor,
            max_batch_size=100,  # Won't trigger automatically
            max_wait_ms=60000,  # Long timeout
        )

        # Start submit but don't await
        submit_task = asyncio.create_task(batcher.submit(sample_request))

        # Give it time to register
        await asyncio.sleep(0.01)

        # Flush manually
        await batcher.flush()

        result = await submit_task
        assert result == sample_response
        executor.assert_called_once()
        await batcher.close()


# =============================================================================
# RequestBatcher close Tests
# =============================================================================


class TestRequestBatcherClose:
    """Tests for the close method."""

    @pytest.mark.asyncio
    async def test_close_flushes_pending(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test that close flushes pending requests."""
        executor = AsyncMock(return_value=[sample_response])
        batcher = RequestBatcher(
            executor=executor,
            max_batch_size=100,
            max_wait_ms=60000,
        )

        submit_task = asyncio.create_task(batcher.submit(sample_request))
        await asyncio.sleep(0.01)

        await batcher.close()

        result = await submit_task
        assert result == sample_response

    @pytest.mark.asyncio
    async def test_close_prevents_new_submissions(
        self, sample_request: LLMRequest, mock_executor: AsyncMock
    ) -> None:
        """Test that close prevents new submissions."""
        batcher = RequestBatcher(executor=mock_executor)
        await batcher.close()

        with pytest.raises(RuntimeError, match="Batcher is closed"):
            await batcher.submit(sample_request)


# =============================================================================
# RequestBatcher Error Handling Tests
# =============================================================================


class TestRequestBatcherErrors:
    """Tests for error handling in RequestBatcher."""

    @pytest.mark.asyncio
    async def test_executor_error_propagates(self, sample_request: LLMRequest) -> None:
        """Test that executor errors propagate to submitters."""
        error = ValueError("API connection failed")
        executor = AsyncMock(side_effect=error)
        batcher = RequestBatcher(executor=executor, max_batch_size=1, max_wait_ms=5000)

        with pytest.raises(ValueError, match="API connection failed"):
            await batcher.submit(sample_request)

    @pytest.mark.asyncio
    async def test_missing_response_for_request(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test error when executor returns fewer responses than requests."""
        # Returns only 1 response for 2 requests
        executor = AsyncMock(return_value=[sample_response])
        batcher = RequestBatcher(executor=executor, max_batch_size=2, max_wait_ms=5000)

        # Submit 2 requests
        task1 = asyncio.create_task(batcher.submit(sample_request))
        task2 = asyncio.create_task(batcher.submit(sample_request))

        # First should succeed, second should fail
        results = await asyncio.gather(task1, task2, return_exceptions=True)

        assert results[0] == sample_response
        assert isinstance(results[1], RuntimeError)
        assert "No response for request" in str(results[1])
        await batcher.close()

    @pytest.mark.asyncio
    async def test_batch_failure_fails_all_futures(
        self, sample_request: LLMRequest
    ) -> None:
        """Test that batch execution failure fails all pending futures."""
        error = ConnectionError("Network error")
        executor = AsyncMock(side_effect=error)
        batcher = RequestBatcher(executor=executor, max_batch_size=3, max_wait_ms=5000)

        # Submit 3 requests that will be batched
        tasks = [
            asyncio.create_task(batcher.submit(sample_request)),
            asyncio.create_task(batcher.submit(sample_request)),
            asyncio.create_task(batcher.submit(sample_request)),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should fail with the same error
        for result in results:
            assert isinstance(result, ConnectionError)
            assert "Network error" in str(result)
        await batcher.close()


# =============================================================================
# RequestBatcher pending_count Tests
# =============================================================================


class TestRequestBatcherPendingCount:
    """Tests for the pending_count method."""

    @pytest.mark.asyncio
    async def test_pending_count_starts_at_zero(self, mock_executor: AsyncMock) -> None:
        """Test that pending count starts at zero."""
        batcher = RequestBatcher(executor=mock_executor)
        assert batcher.pending_count() == 0
        await batcher.close()

    @pytest.mark.asyncio
    async def test_pending_count_after_flush(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test pending count after flush is zero."""
        executor = AsyncMock(return_value=[sample_response])
        batcher = RequestBatcher(executor=executor, max_batch_size=1, max_wait_ms=5000)

        await batcher.submit(sample_request)
        assert batcher.pending_count() == 0
        await batcher.close()


# =============================================================================
# SequentialBatcher Tests
# =============================================================================


class TestSequentialBatcher:
    """Tests for the SequentialBatcher class."""

    @pytest.mark.asyncio
    async def test_submit_executes_immediately(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test that submit executes request immediately."""
        executor = AsyncMock(return_value=sample_response)
        batcher = SequentialBatcher(executor=executor)

        result = await batcher.submit(sample_request)

        assert result == sample_response
        executor.assert_called_once_with(sample_request)

    @pytest.mark.asyncio
    async def test_flush_is_noop(self) -> None:
        """Test that flush is a no-op."""
        executor = AsyncMock()
        batcher = SequentialBatcher(executor=executor)

        await batcher.flush()
        executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_is_noop(self) -> None:
        """Test that close is a no-op."""
        executor = AsyncMock()
        batcher = SequentialBatcher(executor=executor)

        await batcher.close()
        executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_count_always_zero(self) -> None:
        """Test that pending count is always zero."""
        executor = AsyncMock()
        batcher = SequentialBatcher(executor=executor)
        assert batcher.pending_count() == 0

    @pytest.mark.asyncio
    async def test_sequential_error_propagates(
        self, sample_request: LLMRequest
    ) -> None:
        """Test that executor errors propagate."""
        error = ValueError("Request failed")
        executor = AsyncMock(side_effect=error)
        batcher = SequentialBatcher(executor=executor)

        with pytest.raises(ValueError, match="Request failed"):
            await batcher.submit(sample_request)


# =============================================================================
# Concurrent Operations Tests
# =============================================================================


class TestBatcherConcurrency:
    """Tests for concurrent batcher operations."""

    @pytest.mark.asyncio
    async def test_concurrent_submissions(
        self, sample_request: LLMRequest, sample_response: LLMResponse
    ) -> None:
        """Test multiple concurrent submissions."""
        call_count = 0

        async def counting_executor(requests: list[LLMRequest]) -> list[LLMResponse]:
            nonlocal call_count
            call_count += 1
            return [sample_response] * len(requests)

        batcher = RequestBatcher(
            executor=counting_executor,
            max_batch_size=5,
            max_wait_ms=100,
        )

        # Submit 10 requests concurrently
        tasks = [asyncio.create_task(batcher.submit(sample_request)) for _ in range(10)]

        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        # Should have batched (≤3 batches for 10 requests with size 5)
        assert call_count <= 3
        await batcher.close()

    @pytest.mark.asyncio
    async def test_batch_preserves_order(self, sample_response: LLMResponse) -> None:
        """Test that responses match request order."""
        responses = []
        for i in range(5):
            resp = LLMResponse(
                content=f"Response {i}",
                model="gpt-5-nano",
                usage=sample_response.usage,
                latency_ms=100,
            )
            responses.append(resp)

        executor = AsyncMock(return_value=responses)
        batcher = RequestBatcher(executor=executor, max_batch_size=5, max_wait_ms=5000)

        # Create 5 distinct requests
        requests = []
        for i in range(5):
            req = LLMRequest(
                messages=(LLMMessage(role=MessageRole.USER, content=f"Q{i}"),),
                max_tokens=100,
                request_id=f"req-{i}",
            )
            requests.append(req)

        # Submit all
        results = await asyncio.gather(*[batcher.submit(req) for req in requests])

        # Check order preserved
        for i, result in enumerate(results):
            assert result.content == f"Response {i}"
        await batcher.close()
