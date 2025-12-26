"""Anthropic Claude provider implementation.

This module provides an LLM provider for Anthropic's Claude models.
It handles API key management, rate limiting, and JSON structured output
via Claude's tool_use pattern.

Environment Variables:
    ANTHROPIC_API_KEY: API key for Anthropic
    MEMORY_LLM_API_KEY: Override API key (higher priority)

Example:
    >>> provider = AnthropicProvider()
    >>> if await provider.is_available():
    ...     response = await provider.complete(request)
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..config import LLMProvider as LLMProviderEnum
from ..config import get_llm_api_key, get_llm_model
from ..models import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMUsage,
    MessageRole,
)

if TYPE_CHECKING:
    pass

__all__ = ["AnthropicProvider"]


# =============================================================================
# Security Helpers
# =============================================================================

import re

# SEC-H-002: Patterns that may indicate sensitive data in error messages
_SENSITIVE_PATTERNS = [
    # API keys (sk-*, ant-*, etc.)
    (re.compile(r"\b(sk-[a-zA-Z0-9]{20,})", re.IGNORECASE), "[REDACTED_KEY]"),
    (re.compile(r"\b(ant-[a-zA-Z0-9]{20,})", re.IGNORECASE), "[REDACTED_KEY]"),
    # Generic long hex/base64 tokens
    (re.compile(r"\b([a-zA-Z0-9]{32,})\b"), "[REDACTED_TOKEN]"),
    # URLs with potential tokens in query params
    (re.compile(r"(https?://[^\s]+[?&](api_key|token|key)=[^\s&]+)"), "[REDACTED_URL]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[a-zA-Z0-9._-]+", re.IGNORECASE), "Bearer [REDACTED]"),
]


def _sanitize_error_message(error: Exception) -> str:
    """Sanitize error message to remove potential secrets.

    SEC-H-002: Third-party SDK exceptions may include API keys or tokens
    in their string representation. This function removes sensitive patterns.

    Args:
        error: The exception to sanitize.

    Returns:
        Sanitized error message safe for logging.
    """
    msg = str(error)
    for pattern, replacement in _SENSITIVE_PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg


# =============================================================================
# Constants
# =============================================================================

# Cost per million tokens for Claude models (as of Dec 2024)
# These are approximate and may change
CLAUDE_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku-20241022": {"input": 0.8, "output": 4.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
}

DEFAULT_PRICING = {"input": 3.0, "output": 15.0}

# Default retry settings
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF_MS = 1000
DEFAULT_MAX_BACKOFF_MS = 60000
BACKOFF_MULTIPLIER = 2.0

# JSON extraction tool for structured output
JSON_EXTRACT_TOOL = {
    "name": "extract_json",
    "description": "Extract structured JSON data from the analysis",
    "input_schema": {
        "type": "object",
        "properties": {
            "data": {
                "type": "object",
                "description": "The extracted structured data",
            },
        },
        "required": ["data"],
    },
}


# =============================================================================
# Provider Implementation
# =============================================================================


@dataclass
class AnthropicProvider:
    """Anthropic Claude provider implementation.

    Implements LLMProviderProtocol for Anthropic's Claude models.
    Supports JSON structured output via tool_use pattern.

    Attributes:
        api_key: API key for Anthropic.
        model: Model name to use.
        max_retries: Maximum retry attempts.
        timeout_ms: Request timeout in milliseconds.
    """

    api_key: str | None = None
    model: str | None = None
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout_ms: int = 30_000

    def __post_init__(self) -> None:
        """Initialize with defaults from environment if not provided."""
        if self.api_key is None:
            self.api_key = get_llm_api_key(LLMProviderEnum.ANTHROPIC)
        if self.model is None:
            self.model = get_llm_model(LLMProviderEnum.ANTHROPIC)

    @property
    def name(self) -> str:
        """Get the provider name."""
        return "anthropic"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to Claude.

        Args:
            request: The LLM request to process.

        Returns:
            LLMResponse with the generated content.

        Raises:
            LLMAuthenticationError: If API key is invalid or missing.
            LLMRateLimitError: If rate limit is exceeded.
            LLMTimeoutError: If request times out.
            LLMConnectionError: If connection fails.
            LLMProviderError: For other provider errors.
        """
        # Lazy import to avoid loading SDK if not used
        try:
            import anthropic
        except ImportError as e:
            msg = "anthropic package not installed. Install with: pip install anthropic"
            raise LLMProviderError(msg, provider=self.name, original_error=e) from e

        if not self.api_key:
            msg = (
                "Anthropic API key not configured. "
                "Set ANTHROPIC_API_KEY or MEMORY_LLM_API_KEY environment variable."
            )
            raise LLMAuthenticationError(msg, provider=self.name)

        # Build messages
        messages = self._build_messages(request)
        system_prompt = self._extract_system_prompt(request)

        # Determine model
        model = request.model or self.model or "claude-sonnet-4-20250514"

        # Determine timeout
        timeout_ms = request.timeout_ms or self.timeout_ms

        # Build request kwargs
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        # Add JSON mode via tool use if requested
        if request.json_mode:
            kwargs["tools"] = [JSON_EXTRACT_TOOL]
            kwargs["tool_choice"] = {"type": "tool", "name": "extract_json"}

        # Execute with retry
        start_time = time.monotonic()
        response = await self._execute_with_retry(
            anthropic.AsyncAnthropic(api_key=self.api_key),
            kwargs,
            timeout_ms,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)

        # Extract content
        content = self._extract_content(response, request.json_mode)

        # Calculate usage
        usage = self._calculate_usage(response, model)

        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
            latency_ms=latency_ms,
            request_id=request.request_id,
            raw_response=response.model_dump()
            if hasattr(response, "model_dump")
            else None,
        )

    async def complete_batch(
        self,
        requests: list[LLMRequest],
    ) -> list[LLMResponse]:
        """Send multiple completion requests.

        Currently processes requests sequentially. Future versions may
        use Anthropic's batch API when available.

        Args:
            requests: List of LLM requests to process.

        Returns:
            List of LLMResponse objects in the same order as requests.
        """
        responses = []
        for request in requests:
            response = await self.complete(request)
            responses.append(response)
        return responses

    async def is_available(self) -> bool:
        """Check if the provider is configured and reachable.

        Returns:
            True if API key is set and SDK is available.
        """
        if not self.api_key:
            return False

        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            return False

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        """Convert LLMMessages to Anthropic format.

        Args:
            request: The request containing messages.

        Returns:
            List of message dicts for Anthropic API.
        """
        messages = []
        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                # System messages handled separately
                continue
            messages.append(
                {
                    "role": msg.role.value,
                    "content": msg.content,
                }
            )
        return messages

    def _extract_system_prompt(self, request: LLMRequest) -> str | None:
        """Extract system prompt from messages.

        Args:
            request: The request containing messages.

        Returns:
            Combined system prompt or None.
        """
        system_parts = [
            msg.content for msg in request.messages if msg.role == MessageRole.SYSTEM
        ]
        return "\n\n".join(system_parts) if system_parts else None

    def _extract_content(self, response: Any, json_mode: bool) -> str:
        """Extract content from Anthropic response.

        Args:
            response: Anthropic API response.
            json_mode: Whether JSON mode was used.

        Returns:
            Extracted content string.
        """
        if json_mode:
            # Extract from tool use
            for block in response.content:
                if (
                    hasattr(block, "type")
                    and block.type == "tool_use"
                    and block.name == "extract_json"
                ):
                    # Return the JSON data as a string
                    data = block.input.get("data", {})
                    return json.dumps(data)

        # Regular text content
        text_parts = []
        for block in response.content:
            if hasattr(block, "type") and block.type == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts)

    def _calculate_usage(self, response: Any, model: str) -> LLMUsage:
        """Calculate token usage and cost.

        Args:
            response: Anthropic API response.
            model: Model name for pricing.

        Returns:
            LLMUsage with token counts and cost.
        """
        usage = response.usage
        prompt_tokens = usage.input_tokens
        completion_tokens = usage.output_tokens

        # Get pricing for model
        pricing = CLAUDE_PRICING.get(model, DEFAULT_PRICING)

        return LLMUsage.from_tokens(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_cost_per_million=pricing["input"],
            output_cost_per_million=pricing["output"],
        )

    async def _execute_with_retry(
        self,
        client: Any,
        kwargs: dict[str, Any],
        timeout_ms: int,
    ) -> Any:
        """Execute request with exponential backoff retry.

        Args:
            client: Anthropic async client.
            kwargs: Request kwargs.
            timeout_ms: Request timeout.

        Returns:
            Anthropic API response.

        Raises:
            LLMError subclass on failure.
        """
        import anthropic

        last_error: Exception | None = None
        backoff_ms = DEFAULT_INITIAL_BACKOFF_MS

        for attempt in range(self.max_retries):
            try:
                response = await asyncio.wait_for(
                    client.messages.create(**kwargs),
                    timeout=timeout_ms / 1000,
                )
                return response

            except TimeoutError as e:
                last_error = e
                msg = f"Request timed out after {timeout_ms}ms"
                raise LLMTimeoutError(
                    msg,
                    provider=self.name,
                    timeout_ms=timeout_ms,
                ) from e

            except anthropic.RateLimitError as e:
                last_error = e
                retry_after = self._parse_retry_after(e)
                if attempt < self.max_retries - 1:
                    # HIGH-007: Add jitter to prevent "thundering herd" on rate limits
                    # Note: random.random() is intentional here - not for crypto
                    jitter_factor = 0.5 + random.random()  # noqa: S311
                    jittered_retry = int(retry_after * jitter_factor)
                    await asyncio.sleep(jittered_retry / 1000)
                    backoff_ms = min(
                        int(backoff_ms * BACKOFF_MULTIPLIER),
                        DEFAULT_MAX_BACKOFF_MS,
                    )
                    continue
                raise LLMRateLimitError(
                    str(e),
                    provider=self.name,
                    retry_after_ms=retry_after,
                ) from e

            except anthropic.AuthenticationError as e:
                # SEC-H-002: Sanitize error to prevent API key exposure
                msg = f"Authentication failed: {_sanitize_error_message(e)}"
                raise LLMAuthenticationError(msg, provider=self.name) from e

            except anthropic.APIConnectionError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    # HIGH-007: Add jitter to prevent "thundering herd" on connection errors
                    # Note: random.random() is intentional here - not for crypto
                    jitter_factor = 0.5 + random.random()  # noqa: S311
                    jittered_backoff = int(backoff_ms * jitter_factor)
                    await asyncio.sleep(jittered_backoff / 1000)
                    backoff_ms = min(
                        int(backoff_ms * BACKOFF_MULTIPLIER),
                        DEFAULT_MAX_BACKOFF_MS,
                    )
                    continue
                # SEC-H-002: Sanitize error to prevent API key exposure
                msg = f"Connection failed: {_sanitize_error_message(e)}"
                raise LLMConnectionError(msg, provider=self.name) from e

            except anthropic.APIStatusError as e:
                last_error = e
                # SEC-H-002: Sanitize error to prevent API key exposure
                msg = f"API error: {_sanitize_error_message(e)}"
                raise LLMProviderError(
                    msg,
                    provider=self.name,
                    original_error=e,
                    retryable=e.status_code >= 500,
                ) from e

        # Should not reach here, but handle gracefully
        msg = f"All {self.max_retries} retry attempts failed"
        raise LLMProviderError(
            msg,
            provider=self.name,
            original_error=last_error,
            retryable=False,
        )

    def _parse_retry_after(self, error: Any) -> int:
        """Parse retry-after header from error.

        Args:
            error: The rate limit error.

        Returns:
            Retry delay in milliseconds.
        """
        # Try to extract from headers
        if hasattr(error, "response") and hasattr(error.response, "headers"):
            retry_after = error.response.headers.get("retry-after")
            if retry_after:
                try:
                    return int(float(retry_after) * 1000)
                except ValueError:
                    pass
        # Default to 60 seconds
        return 60_000
