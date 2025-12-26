"""Rate limiter for LLM API calls.

This module implements a token bucket rate limiter for controlling
the rate of API requests to prevent hitting provider rate limits.

The rate limiter supports:
- Requests per minute (RPM) limiting
- Tokens per minute (TPM) limiting
- Per-provider rate limits
- Async-compatible locking
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

__all__ = [
    "RateLimiter",
    "TokenBucket",
    "RateLimitExceededError",
]


# =============================================================================
# Exceptions
# =============================================================================


class RateLimitExceededError(Exception):
    """Raised when rate limit would be exceeded.

    Attributes:
        wait_time_ms: How long to wait before retrying.
        limit_type: Which limit was exceeded (rpm or tpm).
    """

    def __init__(
        self,
        message: str,
        *,
        wait_time_ms: int = 0,
        limit_type: str = "rpm",
    ) -> None:
        super().__init__(message)
        self.wait_time_ms = wait_time_ms
        self.limit_type = limit_type


# =============================================================================
# Token Bucket Implementation
# =============================================================================


@dataclass
class TokenBucket:
    """Token bucket for rate limiting.

    Implements a classic token bucket algorithm:
    - Bucket holds up to `capacity` tokens
    - Tokens are added at `refill_rate` per second
    - Requests consume tokens; if insufficient, wait or reject

    Attributes:
        capacity: Maximum tokens the bucket can hold.
        refill_rate: Tokens added per second.
        tokens: Current token count.
        last_refill: Timestamp of last refill.
    """

    capacity: float
    refill_rate: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self) -> None:
        """Initialize with full bucket."""
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    async def acquire(
        self,
        tokens: float = 1.0,
        *,
        wait: bool = True,
        timeout_ms: int | None = None,
    ) -> bool:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire.
            wait: Whether to wait for tokens to become available.
            timeout_ms: Maximum time to wait in milliseconds.

        Returns:
            True if tokens were acquired.

        Raises:
            RateLimitExceededError: If wait=False and tokens unavailable.
            TimeoutError: If timeout exceeded while waiting.
        """
        async with self._lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            if not wait:
                wait_time_s = (tokens - self.tokens) / self.refill_rate
                wait_time_ms = int(wait_time_s * 1000)
                msg = f"Rate limit exceeded. Wait {wait_time_ms}ms."
                raise RateLimitExceededError(
                    msg,
                    wait_time_ms=wait_time_ms,
                )

        # Wait for tokens to become available
        start_time = time.monotonic()
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

            # Check timeout
            if timeout_ms is not None:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                if elapsed_ms >= timeout_ms:
                    msg = f"Rate limit timeout after {timeout_ms}ms"
                    raise TimeoutError(msg)

            # Wait a bit before checking again
            wait_time = (tokens - self.tokens) / self.refill_rate
            wait_time = min(wait_time, 1.0)  # Cap at 1 second
            await asyncio.sleep(wait_time)

    async def refund(self, tokens: float = 1.0) -> None:
        """Refund tokens back to the bucket.

        RES-M-003: Thread-safe token refund using async lock.

        Args:
            tokens: Number of tokens to refund.
        """
        async with self._lock:
            self.tokens = min(self.capacity, self.tokens + tokens)

    def available(self) -> float:
        """Get current available tokens (without locking).

        Returns:
            Approximate available tokens.
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        return min(self.capacity, self.tokens + tokens_to_add)


# =============================================================================
# Rate Limiter
# =============================================================================


@dataclass
class RateLimiter:
    """Rate limiter with RPM and TPM limits.

    Manages two token buckets:
    - One for requests per minute (RPM)
    - One for tokens per minute (TPM)

    Both limits must be satisfied for a request to proceed.

    Attributes:
        rpm_limit: Maximum requests per minute.
        tpm_limit: Maximum tokens per minute.
        name: Optional name for logging.
    """

    rpm_limit: int = 60
    tpm_limit: int = 100_000
    name: str = "default"

    _rpm_bucket: TokenBucket = field(init=False, repr=False)
    _tpm_bucket: TokenBucket = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize token buckets."""
        # RPM: capacity = rpm_limit, refill = rpm_limit / 60 per second
        self._rpm_bucket = TokenBucket(
            capacity=float(self.rpm_limit),
            refill_rate=self.rpm_limit / 60.0,
        )

        # TPM: capacity = tpm_limit, refill = tpm_limit / 60 per second
        self._tpm_bucket = TokenBucket(
            capacity=float(self.tpm_limit),
            refill_rate=self.tpm_limit / 60.0,
        )

    async def acquire(
        self,
        tokens: int = 0,
        *,
        wait: bool = True,
        timeout_ms: int | None = None,
    ) -> bool:
        """Acquire permission to make a request.

        Args:
            tokens: Estimated token count for the request.
            wait: Whether to wait for limits to allow request.
            timeout_ms: Maximum time to wait.

        Returns:
            True if request is allowed.

        Raises:
            RateLimitExceededError: If wait=False and rate limited.
            TimeoutError: If timeout exceeded.
        """
        # Acquire RPM first
        try:
            await self._rpm_bucket.acquire(1.0, wait=wait, timeout_ms=timeout_ms)
        except RateLimitExceededError as e:
            e.limit_type = "rpm"
            raise

        # Acquire TPM if we have token estimate
        if tokens > 0:
            try:
                await self._tpm_bucket.acquire(
                    float(tokens),
                    wait=wait,
                    timeout_ms=timeout_ms,
                )
            except RateLimitExceededError as e:
                e.limit_type = "tpm"
                # RES-M-003: Refund the RPM token since request won't proceed
                # Use async-safe refund method to prevent race condition
                await self._rpm_bucket.refund(1.0)
                raise

        return True

    async def report_usage(self, tokens: int) -> None:
        """Report actual token usage after request completes.

        If actual usage differs from estimate, adjust TPM bucket.
        This is called after the request completes with actual counts.

        Args:
            tokens: Actual token count used.
        """
        # This is informational - the tokens were already consumed
        # We could track metrics here
        pass

    def available_rpm(self) -> float:
        """Get approximate available requests."""
        return self._rpm_bucket.available()

    def available_tpm(self) -> float:
        """Get approximate available tokens."""
        return self._tpm_bucket.available()

    def status(self) -> dict[str, float]:
        """Get current rate limiter status.

        Returns:
            Dict with available_rpm and available_tpm.
        """
        return {
            "available_rpm": self.available_rpm(),
            "available_tpm": self.available_tpm(),
            "rpm_limit": float(self.rpm_limit),
            "tpm_limit": float(self.tpm_limit),
        }
