"""Unified LLM client with rate limiting, batching, and fallback.

This module provides the main entry point for LLM operations.
It integrates:
- Provider selection and fallback
- Rate limiting
- Request batching
- Usage tracking
- Timeout and cancellation

Example:
    >>> from git_notes_memory.subconsciousness import get_llm_client
    >>> client = get_llm_client()
    >>> response = await client.complete("Summarize this text")
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

# Observability imports
from git_notes_memory.observability import get_logger, get_metrics, trace_operation

# CRIT-002: Import secrets filtering service for LLM prompt sanitization
from git_notes_memory.security.service import (
    SecretsFilteringService,
)
from git_notes_memory.security.service import (
    get_default_service as get_secrets_service,
)

from .batcher import RequestBatcher, SequentialBatcher
from .config import (
    LLMProvider,
    get_llm_api_key,
    get_llm_model,
    get_subconsciousness_config,
    is_subconsciousness_enabled,
)
from .models import (
    LLMAuthenticationError,
    LLMError,
    LLMMessage,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)
from .providers import LLMProviderProtocol, get_provider
from .rate_limiter import RateLimiter

if TYPE_CHECKING:
    pass

__all__ = [
    "LLMClient",
    "get_default_llm_client",
    "SubconsciousnessDisabledError",
    "LLMConfigurationError",
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    "UsageTracker",
]

# Structured logger with trace context injection
logger = get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class SubconsciousnessDisabledError(Exception):
    """Raised when subconsciousness features are disabled."""

    def __init__(
        self,
        message: str = "Subconsciousness is disabled. Set MEMORY_SUBCONSCIOUSNESS_ENABLED=true",
    ) -> None:
        super().__init__(message)


class LLMConfigurationError(Exception):
    """Raised when LLM configuration is invalid."""

    pass


# =============================================================================
# Usage Tracker
# =============================================================================


@dataclass
class UsageTracker:
    """Tracks LLM usage for cost management.

    Attributes:
        daily_limit_usd: Maximum daily spending.
        session_limit_usd: Maximum session spending.
        warning_threshold: Fraction of limit to warn at (0.8 = 80%).
    """

    daily_limit_usd: float = 10.0
    session_limit_usd: float = 5.0
    warning_threshold: float = 0.8

    _daily_total: float = field(default=0.0, repr=False)
    _session_total: float = field(default=0.0, repr=False)
    _daily_tokens: int = field(default=0, repr=False)
    _session_tokens: int = field(default=0, repr=False)
    _request_count: int = field(default=0, repr=False)
    _last_reset: datetime = field(
        default_factory=lambda: datetime.now(UTC),
        repr=False,
    )

    def record(self, usage: LLMUsage) -> None:
        """Record usage from a response.

        Args:
            usage: Token usage information.
        """
        self._daily_total += usage.estimated_cost_usd
        self._session_total += usage.estimated_cost_usd
        self._daily_tokens += usage.total_tokens
        self._session_tokens += usage.total_tokens
        self._request_count += 1

        # Check warnings
        if self._session_total >= self.session_limit_usd * self.warning_threshold:
            logger.warning(
                "Session cost approaching limit: $%.2f / $%.2f",
                self._session_total,
                self.session_limit_usd,
            )

        if self._daily_total >= self.daily_limit_usd * self.warning_threshold:
            logger.warning(
                "Daily cost approaching limit: $%.2f / $%.2f",
                self._daily_total,
                self.daily_limit_usd,
            )

    def check_limits(self) -> None:
        """Check if limits are exceeded.

        Raises:
            LLMProviderError: If daily or session limit exceeded.
        """
        if self._daily_total >= self.daily_limit_usd:
            msg = (
                f"Daily cost limit exceeded: ${self._daily_total:.2f} >= "
                f"${self.daily_limit_usd:.2f}"
            )
            raise LLMProviderError(msg, retryable=False)

        if self._session_total >= self.session_limit_usd:
            msg = (
                f"Session cost limit exceeded: ${self._session_total:.2f} >= "
                f"${self.session_limit_usd:.2f}"
            )
            raise LLMProviderError(msg, retryable=False)

    def reset_session(self) -> None:
        """Reset session counters."""
        self._session_total = 0.0
        self._session_tokens = 0
        self._request_count = 0

    def reset_daily(self) -> None:
        """Reset daily counters."""
        self._daily_total = 0.0
        self._daily_tokens = 0
        self._last_reset = datetime.now(UTC)

    def status(self) -> dict[str, float | int]:
        """Get usage status.

        Returns:
            Dict with usage metrics.
        """
        return {
            "daily_cost_usd": self._daily_total,
            "session_cost_usd": self._session_total,
            "daily_tokens": self._daily_tokens,
            "session_tokens": self._session_tokens,
            "request_count": self._request_count,
            "daily_limit_usd": self.daily_limit_usd,
            "session_limit_usd": self.session_limit_usd,
        }


# =============================================================================
# Circuit Breaker
# =============================================================================


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """Circuit breaker for provider resilience.

    Prevents repeated calls to a failing provider by opening the circuit
    after a threshold of failures. After a recovery timeout, the circuit
    moves to half-open state to test if the provider recovered.

    Attributes:
        failure_threshold: Number of failures before opening circuit.
        recovery_timeout_seconds: Seconds to wait before testing recovery.
        half_open_max_requests: Requests allowed in half-open state.
    """

    failure_threshold: int = 5
    recovery_timeout_seconds: float = 60.0
    half_open_max_requests: int = 1

    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _failure_count: int = field(default=0, repr=False)
    _success_count: int = field(default=0, repr=False)
    _last_failure_time: datetime | None = field(default=None, repr=False)
    _half_open_requests: int = field(default=0, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def allow_request(self) -> bool:
        """Check if a request should be allowed.

        Returns:
            True if request is allowed, False if circuit is open.
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if self._last_failure_time is not None:
                elapsed = (datetime.now(UTC) - self._last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout_seconds:
                    logger.info(
                        "Circuit breaker recovery timeout elapsed (%.1fs), "
                        "transitioning to half-open",
                        elapsed,
                    )
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_requests = 0
                    return True
            return False

        # Half-open state: allow limited requests to test recovery
        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_requests < self.half_open_max_requests:
                self._half_open_requests += 1
                return True
            return False

        return True  # pragma: no cover

    def record_success(self) -> None:
        """Record a successful request.

        In half-open state, success closes the circuit.
        In closed state, resets failure count.
        """
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_requests:
                logger.info("Circuit breaker closing after successful recovery")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request.

        In half-open state, failure reopens the circuit.
        In closed state, increments failure count and may open circuit.
        """
        self._last_failure_time = datetime.now(UTC)

        if self._state == CircuitState.HALF_OPEN:
            # Any failure in half-open reopens circuit
            logger.warning("Circuit breaker reopening after half-open failure")
            self._state = CircuitState.OPEN
            self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                logger.warning(
                    "Circuit breaker opening after %d failures",
                    self._failure_count,
                )
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._half_open_requests = 0

    def status(self) -> dict[str, object]:
        """Get circuit breaker status.

        Returns:
            Dict with state, failure count, and timing info.
        """
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout_seconds,
            "last_failure_time": (
                self._last_failure_time.isoformat() if self._last_failure_time else None
            ),
        }


class CircuitOpenError(LLMError):
    """Raised when circuit breaker is open."""

    def __init__(self, provider: str, state: CircuitState) -> None:
        """Initialize circuit open error.

        Args:
            provider: Provider name.
            state: Current circuit state.
        """
        super().__init__(
            f"Circuit breaker is {state.value} for provider {provider}",
            provider=provider,
            retryable=True,  # Will become available after recovery timeout
        )
        self.circuit_state = state


# =============================================================================
# LLM Client
# =============================================================================


@dataclass
class LLMClient:
    """Unified LLM client with rate limiting and fallback.

    This is the main entry point for LLM operations. It handles:
    - Primary and fallback provider selection
    - Rate limiting per provider
    - Request batching (optional)
    - Usage tracking and limits
    - Timeout and cancellation
    - Circuit breaker for resilience
    - Secrets filtering for privacy (CRIT-002)

    Attributes:
        primary_provider: Main LLM provider to use.
        fallback_provider: Backup provider if primary fails.
        rate_limiter: Rate limiter for API calls.
        usage_tracker: Tracks costs and token usage.
        batch_requests: Whether to batch requests.
        default_timeout_ms: Default request timeout.
        circuit_breaker_threshold: Failures before opening circuit.
        circuit_breaker_timeout: Seconds before recovery attempt.
        filter_secrets: Whether to filter secrets from prompts (CRIT-002).
    """

    primary_provider: LLMProviderProtocol
    fallback_provider: LLMProviderProtocol | None = None
    rate_limiter: RateLimiter | None = None
    usage_tracker: UsageTracker | None = None
    batch_requests: bool = False
    default_timeout_ms: int = 30_000
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0
    filter_secrets: bool = True  # CRIT-002: Enable secrets filtering by default

    _batcher: RequestBatcher | SequentialBatcher | None = field(
        default=None,
        repr=False,
    )
    _primary_circuit: CircuitBreaker | None = field(default=None, repr=False)
    _fallback_circuit: CircuitBreaker | None = field(default=None, repr=False)
    _secrets_service: SecretsFilteringService | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize batcher, circuit breakers, and secrets service."""
        if self.batch_requests:
            self._batcher = RequestBatcher(
                executor=self._execute_batch,
                name=self.primary_provider.name,
            )
        else:
            self._batcher = SequentialBatcher(executor=self._execute_single)

        # Initialize circuit breakers for each provider
        self._primary_circuit = CircuitBreaker(
            failure_threshold=self.circuit_breaker_threshold,
            recovery_timeout_seconds=self.circuit_breaker_timeout,
        )
        if self.fallback_provider:
            self._fallback_circuit = CircuitBreaker(
                failure_threshold=self.circuit_breaker_threshold,
                recovery_timeout_seconds=self.circuit_breaker_timeout,
            )

        # CRIT-002: Initialize secrets filtering service
        if self.filter_secrets:
            self._secrets_service = get_secrets_service()

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
        timeout_ms: int | None = None,
    ) -> LLMResponse:
        """Send a simple completion request.

        Args:
            prompt: User prompt text.
            system: Optional system prompt.
            json_mode: Request structured JSON output.
            timeout_ms: Request timeout override.

        Returns:
            LLMResponse with the generated content.

        Raises:
            LLMError: If the request fails.
        """
        request = LLMRequest.simple(prompt, system=system, json_mode=json_mode)
        if timeout_ms:
            request = LLMRequest(
                messages=request.messages,
                json_mode=request.json_mode,
                timeout_ms=timeout_ms,
            )
        return await self.complete_request(request)

    async def complete_request(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request.

        CRIT-002: Filters secrets/PII from messages before sending to LLM provider.

        Args:
            request: The LLM request to process.

        Returns:
            LLMResponse with the generated content.

        Raises:
            LLMError: If the request fails.
        """
        metrics = get_metrics()
        start_time = time.time()
        provider_name = self.primary_provider.name
        model = request.model or "default"

        with trace_operation(
            "llm.complete_request",
            provider=provider_name,
            model=model,
        ) as span:
            try:
                # CRIT-002: Filter secrets from messages before sending to external LLM
                if self._secrets_service and self._secrets_service.enabled:
                    request = self._filter_request_secrets(request)

                # Check usage limits
                if self.usage_tracker:
                    self.usage_tracker.check_limits()

                # Acquire rate limit
                if self.rate_limiter:
                    # Estimate tokens (rough: 4 chars per token)
                    estimated_tokens = sum(
                        len(m.content) // 4 for m in request.messages
                    )
                    await self.rate_limiter.acquire(tokens=estimated_tokens)
                    span.set_tag("estimated_tokens", estimated_tokens)

                # Submit via batcher (guaranteed initialized after __post_init__)
                if self._batcher is None:
                    msg = "Batcher not initialized"
                    raise RuntimeError(msg)
                response = await self._batcher.submit(request)

                # Record usage
                if self.usage_tracker:
                    self.usage_tracker.record(response.usage)

                # Record metrics
                latency_ms = (time.time() - start_time) * 1000
                metrics.observe(
                    "llm_request_duration_ms",
                    latency_ms,
                    labels={"provider": provider_name, "model": response.model},
                )
                metrics.increment(
                    "llm_tokens_total",
                    response.usage.prompt_tokens,
                    labels={"provider": provider_name, "type": "prompt"},
                )
                metrics.increment(
                    "llm_tokens_total",
                    response.usage.completion_tokens,
                    labels={"provider": provider_name, "type": "completion"},
                )
                metrics.observe(
                    "llm_cost_usd",
                    response.usage.estimated_cost_usd,
                    labels={"provider": provider_name, "model": response.model},
                )
                metrics.increment(
                    "llm_requests_total",
                    labels={"provider": provider_name, "status": "success"},
                )

                # Set span tags for tracing
                span.set_tag("latency_ms", latency_ms)
                span.set_tag("prompt_tokens", response.usage.prompt_tokens)
                span.set_tag("completion_tokens", response.usage.completion_tokens)
                span.set_tag("cost_usd", response.usage.estimated_cost_usd)
                span.set_tag("response_model", response.model)

                logger.debug(
                    "LLM request completed",
                    provider=provider_name,
                    model=response.model,
                    latency_ms=round(latency_ms, 2),
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    cost_usd=response.usage.estimated_cost_usd,
                )

                return response

            except Exception as e:
                # Record error metrics
                latency_ms = (time.time() - start_time) * 1000
                error_type = type(e).__name__
                metrics.increment(
                    "llm_requests_total",
                    labels={"provider": provider_name, "status": "error"},
                )
                metrics.increment(
                    "llm_errors_total",
                    labels={"provider": provider_name, "error_type": error_type},
                )
                metrics.observe(
                    "llm_request_duration_ms",
                    latency_ms,
                    labels={"provider": provider_name, "model": model},
                )

                span.set_tag("error_type", error_type)
                span.set_status("error", str(e))

                logger.error(
                    "LLM request failed",
                    provider=provider_name,
                    model=model,
                    error_type=error_type,
                    error=str(e),
                    latency_ms=round(latency_ms, 2),
                )
                raise

    def _filter_request_secrets(self, request: LLMRequest) -> LLMRequest:
        """Filter secrets from all messages in a request.

        CRIT-002: This ensures no PII or secrets are sent to external LLM providers,
        addressing GDPR Art. 44-49 compliance for cross-border data transfers.

        Args:
            request: The original LLM request.

        Returns:
            A new LLMRequest with filtered message content.
        """
        if self._secrets_service is None:
            return request

        filtered_messages: list[LLMMessage] = []
        secrets_found = False

        for message in request.messages:
            result = self._secrets_service.filter(
                content=message.content,
                source="llm_request",
                namespace="subconsciousness",
            )
            if result.had_secrets:
                secrets_found = True
                logger.info(
                    "CRIT-002: Filtered %d secrets from %s message before LLM call",
                    result.detection_count,
                    message.role.value,
                )

            # Create new message with filtered content
            filtered_messages.append(
                LLMMessage(role=message.role, content=result.content)
            )

        if not secrets_found:
            return request

        # Return new request with filtered messages
        return LLMRequest(
            messages=tuple(filtered_messages),
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            json_mode=request.json_mode,
            json_schema=request.json_schema,
            timeout_ms=request.timeout_ms,
            request_id=request.request_id,
        )

    async def complete_batch(
        self,
        requests: list[LLMRequest],
    ) -> list[LLMResponse]:
        """Send multiple completion requests.

        Args:
            requests: List of requests to process.

        Returns:
            List of responses in the same order.
        """
        # Use gather for concurrent execution
        tasks = [self.complete_request(r) for r in requests]
        return await asyncio.gather(*tasks)

    async def _execute_single(self, request: LLMRequest) -> LLMResponse:
        """Execute a single request with circuit breaker and fallback.

        Args:
            request: The request to execute.

        Returns:
            LLMResponse from primary or fallback provider.

        Raises:
            CircuitOpenError: If both circuits are open.
            LLMAuthenticationError: If authentication fails.
            LLMError: If request fails and no fallback available.
        """
        metrics = get_metrics()

        with trace_operation(
            "llm.execute_single",
            primary_provider=self.primary_provider.name,
            has_fallback=self.fallback_provider is not None,
        ) as span:
            # Check primary circuit breaker
            primary_allowed = (
                self._primary_circuit.allow_request() if self._primary_circuit else True
            )
            span.set_tag("primary_circuit_allowed", primary_allowed)

            if primary_allowed:
                try:
                    with trace_operation(
                        "llm.provider_call",
                        provider=self.primary_provider.name,
                        is_fallback=False,
                    ):
                        response = await self._execute_with_timeout(
                            self.primary_provider,
                            request,
                        )
                    # Record success
                    if self._primary_circuit:
                        self._primary_circuit.record_success()
                    span.set_tag("provider_used", self.primary_provider.name)
                    metrics.increment(
                        "llm_circuit_breaker_success",
                        labels={"provider": self.primary_provider.name},
                    )
                    return response
                except LLMAuthenticationError:
                    # Don't fallback on auth errors, don't count as circuit failure
                    metrics.increment(
                        "llm_auth_errors_total",
                        labels={"provider": self.primary_provider.name},
                    )
                    raise
                except LLMError as e:
                    # Record failure in circuit breaker
                    if self._primary_circuit:
                        self._primary_circuit.record_failure()
                    metrics.increment(
                        "llm_circuit_breaker_failure",
                        labels={"provider": self.primary_provider.name},
                    )

                    if not e.retryable and self.fallback_provider is None:
                        raise

                    # Fall through to try fallback
                    span.set_tag("primary_failed", True)
                    span.set_tag("primary_error", str(e))
                    logger.warning(
                        "Primary provider failed, trying fallback",
                        provider=self.primary_provider.name,
                        error=str(e),
                    )
            else:
                span.set_tag("primary_circuit_open", True)
                metrics.increment(
                    "llm_circuit_breaker_open",
                    labels={"provider": self.primary_provider.name},
                )
                logger.warning(
                    "Primary provider circuit is open, trying fallback",
                    provider=self.primary_provider.name,
                )

            # Try fallback provider if available
            if self.fallback_provider:
                fallback_allowed = (
                    self._fallback_circuit.allow_request()
                    if self._fallback_circuit
                    else True
                )
                span.set_tag("fallback_circuit_allowed", fallback_allowed)

                if fallback_allowed:
                    try:
                        with trace_operation(
                            "llm.provider_call",
                            provider=self.fallback_provider.name,
                            is_fallback=True,
                        ):
                            response = await self._execute_with_timeout(
                                self.fallback_provider,
                                request,
                            )
                        # Record success
                        if self._fallback_circuit:
                            self._fallback_circuit.record_success()
                        span.set_tag("provider_used", self.fallback_provider.name)
                        span.set_tag("used_fallback", True)
                        metrics.increment(
                            "llm_fallback_used",
                            labels={"fallback_provider": self.fallback_provider.name},
                        )
                        logger.info(
                            "Fallback provider succeeded",
                            provider=self.fallback_provider.name,
                        )
                        return response
                    except LLMError:
                        if self._fallback_circuit:
                            self._fallback_circuit.record_failure()
                        metrics.increment(
                            "llm_circuit_breaker_failure",
                            labels={"provider": self.fallback_provider.name},
                        )
                        raise
                else:
                    # Both circuits are open
                    metrics.increment(
                        "llm_circuit_breaker_open",
                        labels={"provider": self.fallback_provider.name},
                    )
                    raise CircuitOpenError(
                        provider=f"{self.primary_provider.name}/{self.fallback_provider.name}",
                        state=CircuitState.OPEN,
                    )

            # No fallback, primary circuit was open
            if not primary_allowed:
                raise CircuitOpenError(
                    provider=self.primary_provider.name,
                    state=CircuitState.OPEN,
                )

            # This shouldn't be reached, but satisfy type checker
            msg = "Request failed with no fallback available"
            raise LLMError(msg, retryable=False)

    async def _execute_batch(
        self,
        requests: list[LLMRequest],
    ) -> list[LLMResponse]:
        """Execute a batch of requests.

        Args:
            requests: List of requests to execute.

        Returns:
            List of responses.
        """
        return await self.primary_provider.complete_batch(requests)

    async def _execute_with_timeout(
        self,
        provider: LLMProviderProtocol,
        request: LLMRequest,
    ) -> LLMResponse:
        """Execute request with timeout.

        Args:
            provider: Provider to use.
            request: Request to execute.

        Returns:
            LLMResponse from provider.
        """
        timeout_ms = request.timeout_ms or self.default_timeout_ms

        try:
            return await asyncio.wait_for(
                provider.complete(request),
                timeout=timeout_ms / 1000,
            )
        except TimeoutError as e:
            from .models import LLMTimeoutError

            msg = f"Request timed out after {timeout_ms}ms"
            raise LLMTimeoutError(
                msg,
                provider=provider.name,
                timeout_ms=timeout_ms,
            ) from e

    async def close(self) -> None:
        """Close the client and flush pending requests."""
        if self._batcher:
            await self._batcher.close()

    def status(self) -> dict[str, object]:
        """Get client status.

        Returns:
            Dict with provider, rate limiter, circuit breaker, and usage status.
        """
        status: dict[str, object] = {
            "primary_provider": self.primary_provider.name,
            "fallback_provider": (
                self.fallback_provider.name if self.fallback_provider else None
            ),
            "batch_requests": self.batch_requests,
            "pending_requests": (self._batcher.pending_count() if self._batcher else 0),
        }

        if self.rate_limiter:
            status["rate_limiter"] = self.rate_limiter.status()

        if self.usage_tracker:
            status["usage"] = self.usage_tracker.status()

        # Add circuit breaker status
        if self._primary_circuit:
            status["primary_circuit_breaker"] = self._primary_circuit.status()
        if self._fallback_circuit:
            status["fallback_circuit_breaker"] = self._fallback_circuit.status()

        return status


# =============================================================================
# Factory Function
# =============================================================================

_default_client: LLMClient | None = None


def get_default_llm_client() -> LLMClient:
    """Get the default LLM client singleton.

    Creates a client configured from environment variables.
    The client is cached for reuse.

    Returns:
        LLMClient configured from environment.

    Raises:
        SubconsciousnessDisabledError: If subconsciousness is disabled.
        LLMConfigurationError: If configuration is invalid.
    """
    global _default_client

    if _default_client is not None:
        return _default_client

    # Check if enabled
    if not is_subconsciousness_enabled():
        raise SubconsciousnessDisabledError()

    config = get_subconsciousness_config()

    # Validate configuration
    if config.provider != LLMProvider.OLLAMA:
        api_key = get_llm_api_key(config.provider)
        if not api_key:
            provider_name = config.provider.value
            env_var = (
                "ANTHROPIC_API_KEY"
                if config.provider == LLMProvider.ANTHROPIC
                else "OPENAI_API_KEY"
            )
            msg = (
                f"No API key configured for {provider_name}. "
                f"Set {env_var} or MEMORY_LLM_API_KEY environment variable."
            )
            raise LLMConfigurationError(msg)

    # Create primary provider
    primary = get_provider(
        config.provider,
        api_key=get_llm_api_key(config.provider),
        model=get_llm_model(config.provider),
        timeout_ms=config.timeout_ms,
    )

    # Create fallback provider (Ollama as local fallback)
    fallback: LLMProviderProtocol | None = None
    if config.provider != LLMProvider.OLLAMA:
        try:
            fallback = get_provider(
                LLMProvider.OLLAMA,
                base_url=config.ollama_base_url,
            )
        except Exception:
            # Ollama not available, no fallback
            logger.debug("Ollama not available for fallback")

    # Create rate limiter
    rate_limiter = RateLimiter(
        rpm_limit=config.rpm_limit,
        tpm_limit=config.tpm_limit,
        name=config.provider.value,
    )

    # Create usage tracker
    usage_tracker = UsageTracker(
        daily_limit_usd=config.daily_cost_limit,
    )

    # Create client
    _default_client = LLMClient(
        primary_provider=primary,
        fallback_provider=fallback,
        rate_limiter=rate_limiter,
        usage_tracker=usage_tracker,
        default_timeout_ms=config.timeout_ms,
    )

    return _default_client


def reset_default_client() -> None:
    """Reset the default client singleton.

    Useful for testing or reconfiguration.
    """
    global _default_client
    _default_client = None
