"""Tests for circuit breaker functionality in LLM client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from git_notes_memory.subconsciousness.llm_client import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    LLMClient,
)
from git_notes_memory.subconsciousness.models import (
    LLMError,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)

if TYPE_CHECKING:
    pass


class TestCircuitBreaker:
    """Test CircuitBreaker state machine."""

    def test_initial_state_is_closed(self) -> None:
        """Circuit breaker starts in closed state."""
        cb = CircuitBreaker()
        assert cb._state == CircuitState.CLOSED
        assert cb.allow_request()

    def test_allow_request_when_closed(self) -> None:
        """Closed circuit allows all requests."""
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(10):
            assert cb.allow_request()

    def test_opens_after_threshold_failures(self) -> None:
        """Circuit opens after failure_threshold consecutive failures."""
        cb = CircuitBreaker(failure_threshold=3)

        # Record 2 failures - still closed
        cb.record_failure()
        cb.record_failure()
        assert cb._state == CircuitState.CLOSED
        assert cb.allow_request()

        # Third failure opens circuit
        cb.record_failure()
        assert cb._state == CircuitState.OPEN
        assert not cb.allow_request()

    def test_success_resets_failure_count(self) -> None:
        """Success in closed state resets failure count."""
        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        assert cb._failure_count == 2

        cb.record_success()
        assert cb._failure_count == 0

        # Now need 3 more failures to open
        cb.record_failure()
        cb.record_failure()
        assert cb._state == CircuitState.CLOSED

    def test_open_circuit_blocks_requests(self) -> None:
        """Open circuit blocks all requests."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=60)

        cb.record_failure()
        assert cb._state == CircuitState.OPEN

        # All requests blocked
        for _ in range(10):
            assert not cb.allow_request()

    def test_transitions_to_half_open_after_timeout(self) -> None:
        """Circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=0.1)

        cb.record_failure()
        assert cb._state == CircuitState.OPEN

        # Simulate time passing
        cb._last_failure_time = datetime.now(UTC) - timedelta(seconds=1)

        # Next allow_request should transition to half-open
        assert cb.allow_request()
        assert cb._state == CircuitState.HALF_OPEN

    def test_half_open_limits_requests(self) -> None:
        """Half-open state limits number of test requests."""
        cb = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=0,
            half_open_max_requests=2,
        )

        cb.record_failure()
        cb._last_failure_time = datetime.now(UTC) - timedelta(seconds=1)

        # First request transitions from OPEN to HALF_OPEN (doesn't count against limit)
        assert cb.allow_request()
        assert cb._state == CircuitState.HALF_OPEN

        # Second request allowed (1st half-open request)
        assert cb.allow_request()

        # Third request allowed (2nd half-open request)
        assert cb.allow_request()

        # Fourth request blocked (limit reached)
        assert not cb.allow_request()

    def test_half_open_success_closes_circuit(self) -> None:
        """Successful requests in half-open close the circuit."""
        cb = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=0,
            half_open_max_requests=1,
        )

        cb.record_failure()
        cb._last_failure_time = datetime.now(UTC) - timedelta(seconds=1)
        cb.allow_request()  # Transition to half-open
        assert cb._state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb._state == CircuitState.CLOSED
        assert cb._failure_count == 0

    def test_half_open_failure_reopens_circuit(self) -> None:
        """Failure in half-open reopens the circuit."""
        cb = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=0,
            half_open_max_requests=1,
        )

        cb.record_failure()
        cb._last_failure_time = datetime.now(UTC) - timedelta(seconds=1)
        cb.allow_request()  # Transition to half-open
        assert cb._state == CircuitState.HALF_OPEN

        cb.record_failure()
        assert cb._state == CircuitState.OPEN

    def test_reset_restores_closed_state(self) -> None:
        """Reset restores circuit to initial closed state."""
        cb = CircuitBreaker(failure_threshold=1)

        cb.record_failure()
        assert cb._state == CircuitState.OPEN

        cb.reset()
        assert cb._state == CircuitState.CLOSED
        assert cb._failure_count == 0
        assert cb._success_count == 0
        assert cb._last_failure_time is None

    def test_status_returns_state_info(self) -> None:
        """Status method returns circuit state information."""
        cb = CircuitBreaker(failure_threshold=5, recovery_timeout_seconds=30)

        status = cb.status()
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["failure_threshold"] == 5
        assert status["recovery_timeout_seconds"] == 30
        assert status["last_failure_time"] is None

        cb.record_failure()
        status = cb.status()
        assert status["failure_count"] == 1
        assert status["last_failure_time"] is not None


class TestCircuitOpenError:
    """Test CircuitOpenError exception."""

    def test_error_message_includes_provider(self) -> None:
        """Error message includes provider name."""
        error = CircuitOpenError(provider="anthropic", state=CircuitState.OPEN)
        assert "anthropic" in str(error)
        assert "open" in str(error)

    def test_error_is_retryable(self) -> None:
        """CircuitOpenError is marked as retryable."""
        error = CircuitOpenError(provider="test", state=CircuitState.OPEN)
        assert error.retryable is True

    def test_error_stores_circuit_state(self) -> None:
        """Error stores the circuit state."""
        error = CircuitOpenError(provider="test", state=CircuitState.HALF_OPEN)
        assert error.circuit_state == CircuitState.HALF_OPEN


class TestLLMClientWithCircuitBreaker:
    """Test LLMClient circuit breaker integration."""

    @pytest.fixture
    def mock_provider(self) -> MagicMock:
        """Create a mock LLM provider."""
        provider = MagicMock()
        provider.name = "test-primary"
        provider.complete = AsyncMock()
        return provider

    @pytest.fixture
    def mock_fallback(self) -> MagicMock:
        """Create a mock fallback provider."""
        provider = MagicMock()
        provider.name = "test-fallback"
        provider.complete = AsyncMock()
        return provider

    @pytest.fixture
    def mock_response(self) -> LLMResponse:
        """Create a mock LLM response."""
        return LLMResponse(
            content="Test response",
            usage=LLMUsage(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            ),
            model="test-model",
            latency_ms=100,
        )

    def test_client_creates_circuit_breakers(self, mock_provider: MagicMock) -> None:
        """Client creates circuit breakers for providers."""
        client = LLMClient(
            primary_provider=mock_provider,
            circuit_breaker_threshold=10,
            circuit_breaker_timeout=120,
        )

        assert client._primary_circuit is not None
        assert client._primary_circuit.failure_threshold == 10
        assert client._primary_circuit.recovery_timeout_seconds == 120
        assert client._fallback_circuit is None

    def test_client_creates_fallback_circuit(
        self,
        mock_provider: MagicMock,
        mock_fallback: MagicMock,
    ) -> None:
        """Client creates circuit breaker for fallback provider."""
        client = LLMClient(
            primary_provider=mock_provider,
            fallback_provider=mock_fallback,
        )

        assert client._primary_circuit is not None
        assert client._fallback_circuit is not None

    @pytest.mark.asyncio
    async def test_success_records_in_circuit_breaker(
        self,
        mock_provider: MagicMock,
        mock_response: LLMResponse,
    ) -> None:
        """Successful requests are recorded in circuit breaker."""
        mock_provider.complete.return_value = mock_response

        client = LLMClient(primary_provider=mock_provider)
        request = LLMRequest.simple("test prompt")

        await client._execute_single(request)

        assert client._primary_circuit is not None
        assert client._primary_circuit._failure_count == 0

    @pytest.mark.asyncio
    async def test_failure_records_in_circuit_breaker(
        self,
        mock_provider: MagicMock,
    ) -> None:
        """Failed requests are recorded in circuit breaker."""
        mock_provider.complete.side_effect = LLMError(
            "Provider error",
            retryable=False,
        )

        client = LLMClient(primary_provider=mock_provider)
        request = LLMRequest.simple("test prompt")

        with pytest.raises(LLMError):
            await client._execute_single(request)

        assert client._primary_circuit is not None
        assert client._primary_circuit._failure_count == 1

    @pytest.mark.asyncio
    async def test_open_circuit_falls_back(
        self,
        mock_provider: MagicMock,
        mock_fallback: MagicMock,
        mock_response: LLMResponse,
    ) -> None:
        """Open primary circuit uses fallback provider."""
        mock_fallback.complete.return_value = mock_response

        client = LLMClient(
            primary_provider=mock_provider,
            fallback_provider=mock_fallback,
            circuit_breaker_threshold=1,
        )

        # Open the primary circuit
        assert client._primary_circuit is not None
        client._primary_circuit.record_failure()
        assert client._primary_circuit._state == CircuitState.OPEN

        request = LLMRequest.simple("test prompt")
        response = await client._execute_single(request)

        assert response == mock_response
        mock_fallback.complete.assert_called_once()
        mock_provider.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_circuits_open_raises_error(
        self,
        mock_provider: MagicMock,
        mock_fallback: MagicMock,
    ) -> None:
        """Both circuits open raises CircuitOpenError."""
        client = LLMClient(
            primary_provider=mock_provider,
            fallback_provider=mock_fallback,
            circuit_breaker_threshold=1,
        )

        # Open both circuits
        assert client._primary_circuit is not None
        assert client._fallback_circuit is not None
        client._primary_circuit.record_failure()
        client._fallback_circuit.record_failure()

        request = LLMRequest.simple("test prompt")

        with pytest.raises(CircuitOpenError) as exc_info:
            await client._execute_single(request)

        assert "test-primary/test-fallback" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_primary_circuit_open_no_fallback_raises_error(
        self,
        mock_provider: MagicMock,
    ) -> None:
        """Open primary circuit with no fallback raises CircuitOpenError."""
        client = LLMClient(
            primary_provider=mock_provider,
            circuit_breaker_threshold=1,
        )

        # Open primary circuit
        assert client._primary_circuit is not None
        client._primary_circuit.record_failure()

        request = LLMRequest.simple("test prompt")

        with pytest.raises(CircuitOpenError) as exc_info:
            await client._execute_single(request)

        assert "test-primary" in str(exc_info.value)

    def test_status_includes_circuit_breakers(
        self,
        mock_provider: MagicMock,
        mock_fallback: MagicMock,
    ) -> None:
        """Status method includes circuit breaker information."""
        client = LLMClient(
            primary_provider=mock_provider,
            fallback_provider=mock_fallback,
        )

        status = client.status()
        assert "primary_circuit_breaker" in status
        assert "fallback_circuit_breaker" in status
        primary_cb = status["primary_circuit_breaker"]
        assert isinstance(primary_cb, dict)
        assert primary_cb["state"] == "closed"
