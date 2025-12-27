"""Tests for the rate limiter module."""

from __future__ import annotations

import asyncio

import pytest

from git_notes_memory.subconsciousness.rate_limiter import (
    RateLimiter,
    RateLimitExceededError,
    TokenBucket,
)


class TestTokenBucket:
    """Tests for TokenBucket class."""

    @pytest.mark.asyncio
    async def test_basic_acquire(self) -> None:
        """Test basic token acquisition."""
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)

        result = await bucket.acquire(1.0, wait=False)
        assert result is True
        assert bucket.tokens == pytest.approx(9.0, abs=0.1)

    @pytest.mark.asyncio
    async def test_acquire_multiple(self) -> None:
        """Test acquiring multiple tokens."""
        bucket = TokenBucket(capacity=10.0, refill_rate=1.0)

        await bucket.acquire(5.0, wait=False)
        assert bucket.tokens == pytest.approx(5.0, abs=0.1)

        await bucket.acquire(3.0, wait=False)
        assert bucket.tokens == pytest.approx(2.0, abs=0.2)

    @pytest.mark.asyncio
    async def test_acquire_exceeds_no_wait(self) -> None:
        """Test acquiring more tokens than available without waiting."""
        bucket = TokenBucket(capacity=5.0, refill_rate=1.0)

        with pytest.raises(RateLimitExceededError) as exc_info:
            await bucket.acquire(10.0, wait=False)

        assert exc_info.value.wait_time_ms > 0

    @pytest.mark.asyncio
    async def test_refill_over_time(self) -> None:
        """Test tokens refill over time."""
        bucket = TokenBucket(capacity=10.0, refill_rate=10.0)  # 10 tokens/sec

        # Drain the bucket
        await bucket.acquire(10.0, wait=False)
        assert bucket.tokens == pytest.approx(0.0, abs=0.1)

        # Wait 0.5 seconds, should have ~5 tokens back
        await asyncio.sleep(0.5)
        available = bucket.available()
        assert available == pytest.approx(5.0, abs=1.0)

    @pytest.mark.asyncio
    async def test_capacity_limit(self) -> None:
        """Test bucket doesn't exceed capacity."""
        bucket = TokenBucket(capacity=10.0, refill_rate=100.0)  # Fast refill

        # Wait for refill
        await asyncio.sleep(0.1)

        # Should still be at capacity
        available = bucket.available()
        assert available <= 10.0


class TestRateLimiter:
    """Tests for RateLimiter class."""

    @pytest.mark.asyncio
    async def test_basic_acquire(self) -> None:
        """Test basic rate limiter acquisition."""
        limiter = RateLimiter(rpm_limit=60, tpm_limit=10000)

        result = await limiter.acquire(tokens=100, wait=False)
        assert result is True

    @pytest.mark.asyncio
    async def test_rpm_limiting(self) -> None:
        """Test requests per minute limiting."""
        # Very low limit for testing
        limiter = RateLimiter(rpm_limit=2, tpm_limit=100000)

        # First two requests should succeed
        await limiter.acquire(wait=False)
        await limiter.acquire(wait=False)

        # Third should fail (bucket nearly empty)
        # Note: Due to refill, we need to be quick
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.acquire(wait=False)

        assert exc_info.value.limit_type == "rpm"

    @pytest.mark.asyncio
    async def test_tpm_limiting(self) -> None:
        """Test tokens per minute limiting."""
        # Very low token limit
        limiter = RateLimiter(rpm_limit=100, tpm_limit=100)

        # Request with too many tokens
        with pytest.raises(RateLimitExceededError) as exc_info:
            await limiter.acquire(tokens=200, wait=False)

        assert exc_info.value.limit_type == "tpm"

    @pytest.mark.asyncio
    async def test_status(self) -> None:
        """Test status reporting."""
        limiter = RateLimiter(rpm_limit=60, tpm_limit=10000)

        status = limiter.status()

        assert "available_rpm" in status
        assert "available_tpm" in status
        assert status["rpm_limit"] == 60.0
        assert status["tpm_limit"] == 10000.0

    @pytest.mark.asyncio
    async def test_wait_for_tokens(self) -> None:
        """Test waiting for tokens to become available."""
        # Fast refill for testing
        limiter = RateLimiter(rpm_limit=60, tpm_limit=10000)

        # Use up tokens and wait for refill
        await limiter.acquire(tokens=100, wait=True)
        await limiter.acquire(tokens=100, wait=True, timeout_ms=1000)

        # Both should succeed with waiting
