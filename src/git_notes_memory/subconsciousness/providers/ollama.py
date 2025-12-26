"""Ollama local LLM provider implementation.

This module provides an LLM provider for locally-running Ollama models.
It handles connection management and basic JSON parsing (no native JSON mode).

Environment Variables:
    MEMORY_OLLAMA_BASE_URL: Ollama server URL (default: http://localhost:11434)
    MEMORY_LLM_MODEL: Model name (default: llama3.2)

Example:
    >>> provider = OllamaProvider()
    >>> if await provider.is_available():
    ...     response = await provider.complete(request)

Note:
    Ollama must be running locally. Install from https://ollama.ai
    Start with: ollama serve
    Pull models with: ollama pull llama3.2
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..config import LLMProvider as LLMProviderEnum
from ..config import get_llm_model, get_subconsciousness_config
from ..models import (
    LLMConnectionError,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMUsage,
    MessageRole,
)

if TYPE_CHECKING:
    pass

__all__ = ["OllamaProvider"]


# =============================================================================
# Constants
# =============================================================================

# Default retry settings
DEFAULT_MAX_RETRIES = 2  # Fewer retries for local
DEFAULT_INITIAL_BACKOFF_MS = 500
DEFAULT_MAX_BACKOFF_MS = 5000
BACKOFF_MULTIPLIER = 2.0

# Connection check timeout
AVAILABILITY_CHECK_TIMEOUT = 2.0  # seconds


# =============================================================================
# Provider Implementation
# =============================================================================


@dataclass
class OllamaProvider:
    """Ollama local LLM provider implementation.

    Implements LLMProviderProtocol for locally-running Ollama models.
    Does not require an API key. JSON mode is simulated via prompting
    and regex extraction.

    Attributes:
        base_url: Ollama server URL.
        model: Model name to use.
        max_retries: Maximum retry attempts.
        timeout_ms: Request timeout in milliseconds.
    """

    base_url: str | None = None
    model: str | None = None
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout_ms: int = 60_000  # Longer timeout for local models

    def __post_init__(self) -> None:
        """Initialize with defaults from environment if not provided."""
        if self.base_url is None:
            config = get_subconsciousness_config()
            self.base_url = config.ollama_base_url
        if self.model is None:
            self.model = get_llm_model(LLMProviderEnum.OLLAMA)

    @property
    def name(self) -> str:
        """Get the provider name."""
        return "ollama"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request to Ollama.

        Args:
            request: The LLM request to process.

        Returns:
            LLMResponse with the generated content.

        Raises:
            LLMTimeoutError: If request times out.
            LLMConnectionError: If Ollama is not running.
            LLMProviderError: For other provider errors.
        """
        # Lazy import httpx
        try:
            import httpx
        except ImportError as e:
            msg = "httpx package not installed. Install with: pip install httpx"
            raise LLMProviderError(msg, provider=self.name, original_error=e) from e

        # Build messages
        messages = self._build_messages(request)

        # Add JSON instruction to system prompt if json_mode
        if request.json_mode:
            messages = self._add_json_instruction(messages)

        # Determine model
        model = request.model or self.model or "llama3.2"

        # Determine timeout
        timeout_ms = request.timeout_ms or self.timeout_ms

        # Build request
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        # Execute with retry
        start_time = time.monotonic()
        response_data = await self._execute_with_retry(
            httpx,
            payload,
            timeout_ms,
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)

        # Extract content
        content = response_data.get("message", {}).get("content", "")

        # If JSON mode, try to extract JSON
        if request.json_mode:
            content = self._extract_json(content)

        # Calculate usage (Ollama provides token counts)
        usage = self._calculate_usage(response_data)

        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
            latency_ms=latency_ms,
            request_id=request.request_id,
            raw_response=response_data,
        )

    async def complete_batch(
        self,
        requests: list[LLMRequest],
    ) -> list[LLMResponse]:
        """Send multiple completion requests.

        Processes requests sequentially as Ollama doesn't support batching.

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
        """Check if Ollama is running and reachable.

        Returns:
            True if Ollama server responds to health check.
        """
        try:
            import httpx
        except ImportError:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/tags",
                    timeout=AVAILABILITY_CHECK_TIMEOUT,
                )
                return response.status_code == 200
        except Exception:
            return False

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        """Convert LLMMessages to Ollama format.

        Args:
            request: The request containing messages.

        Returns:
            List of message dicts for Ollama API.
        """
        messages = []
        for msg in request.messages:
            messages.append(
                {
                    "role": msg.role.value,
                    "content": msg.content,
                }
            )
        return messages

    def _add_json_instruction(
        self,
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Add JSON output instruction to messages.

        Args:
            messages: Current messages list.

        Returns:
            Modified messages with JSON instruction.
        """
        json_instruction = (
            "\n\nIMPORTANT: Respond ONLY with valid JSON. "
            "Do not include any text before or after the JSON. "
            "Do not use markdown code blocks."
        )

        # Find and modify system message, or add one
        for msg in messages:
            if msg["role"] == MessageRole.SYSTEM.value:
                msg["content"] += json_instruction
                return messages

        # No system message, add one
        return [{"role": "system", "content": json_instruction.strip()}] + messages

    def _extract_json(self, content: str) -> str:
        """Extract JSON from potentially mixed content.

        Args:
            content: Raw content that may contain JSON.

        Returns:
            Extracted JSON string, or original content if no JSON found.
        """
        # Try to find JSON object
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                # Validate it's actual JSON
                json.loads(json_match.group())
                return json_match.group()
            except json.JSONDecodeError:
                pass

        # Try to find JSON array
        array_match = re.search(r"\[[\s\S]*\]", content)
        if array_match:
            try:
                json.loads(array_match.group())
                return array_match.group()
            except json.JSONDecodeError:
                pass

        # Return original content
        return content

    def _calculate_usage(self, response_data: dict[str, Any]) -> LLMUsage:
        """Calculate token usage from Ollama response.

        Args:
            response_data: Ollama API response.

        Returns:
            LLMUsage with token counts (cost is 0 for local models).
        """
        prompt_tokens = response_data.get("prompt_eval_count", 0)
        completion_tokens = response_data.get("eval_count", 0)

        return LLMUsage.from_tokens(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            # Local models have no cost
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
        )

    async def _execute_with_retry(
        self,
        httpx_module: Any,
        payload: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        """Execute request with retry.

        Args:
            httpx_module: The httpx module.
            payload: Request payload.
            timeout_ms: Request timeout.

        Returns:
            Ollama API response dict.

        Raises:
            LLMError subclass on failure.
        """
        last_error: Exception | None = None
        backoff_ms = DEFAULT_INITIAL_BACKOFF_MS

        for attempt in range(self.max_retries):
            try:
                async with httpx_module.AsyncClient() as client:
                    response = await asyncio.wait_for(
                        client.post(
                            f"{self.base_url}/api/chat",
                            json=payload,
                            timeout=timeout_ms / 1000,
                        ),
                        timeout=timeout_ms / 1000 + 1,  # Buffer for httpx timeout
                    )

                    if response.status_code != 200:
                        error_text = response.text
                        msg = f"Ollama error {response.status_code}: {error_text}"
                        raise LLMProviderError(
                            msg,
                            provider=self.name,
                            retryable=response.status_code >= 500,
                        )

                    result: dict[str, Any] = response.json()
                    return result

            except TimeoutError as e:
                last_error = e
                msg = f"Request timed out after {timeout_ms}ms"
                raise LLMTimeoutError(
                    msg,
                    provider=self.name,
                    timeout_ms=timeout_ms,
                ) from e

            except httpx_module.ConnectError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(backoff_ms / 1000)
                    backoff_ms = min(
                        int(backoff_ms * BACKOFF_MULTIPLIER),
                        DEFAULT_MAX_BACKOFF_MS,
                    )
                    continue
                msg = (
                    f"Failed to connect to Ollama at {self.base_url}. "
                    "Is Ollama running? Start with: ollama serve"
                )
                raise LLMConnectionError(msg, provider=self.name) from e

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(backoff_ms / 1000)
                    backoff_ms = min(
                        int(backoff_ms * BACKOFF_MULTIPLIER),
                        DEFAULT_MAX_BACKOFF_MS,
                    )
                    continue
                msg = f"Ollama request failed: {e}"
                raise LLMProviderError(
                    msg,
                    provider=self.name,
                    original_error=e,
                    retryable=False,
                ) from e

        # Should not reach here
        msg = f"All {self.max_retries} retry attempts failed"
        raise LLMProviderError(
            msg,
            provider=self.name,
            original_error=last_error,
            retryable=False,
        )
