"""LLM provider implementations.

This module contains provider-agnostic abstractions and concrete implementations
for various LLM backends (Anthropic, OpenAI, Ollama).

Usage:
    >>> from git_notes_memory.subconsciousness.providers import get_provider
    >>> provider = get_provider("anthropic")
    >>> response = await provider.complete(request)

Available Providers:
    - anthropic: Claude models via Anthropic API
    - openai: GPT models via OpenAI API
    - ollama: Local models via Ollama
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..config import LLMProvider
    from ..models import LLMRequest, LLMResponse

__all__ = [
    # Protocol
    "LLMProviderProtocol",
    # Factory
    "get_provider",
    # Providers (lazy imports)
    "AnthropicProvider",
    "OpenAIProvider",
    "OllamaProvider",
]


# =============================================================================
# Provider Protocol
# =============================================================================


@runtime_checkable
class LLMProviderProtocol(Protocol):
    """Protocol defining the interface for LLM providers.

    All providers must implement this interface to be used with LLMClient.
    The protocol is runtime-checkable for duck typing.

    Methods:
        complete: Send a single request and get a response.
        complete_batch: Send multiple requests efficiently.
        is_available: Check if the provider is configured and reachable.
    """

    @property
    def name(self) -> str:
        """Get the provider name (anthropic, openai, ollama)."""
        ...

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a single completion request.

        Args:
            request: The LLM request to process.

        Returns:
            LLMResponse with the generated content.

        Raises:
            LLMError: If the request fails.
        """
        ...

    async def complete_batch(
        self,
        requests: list[LLMRequest],
    ) -> list[LLMResponse]:
        """Send multiple completion requests efficiently.

        Providers may batch these internally for efficiency.
        Failed requests will have their exceptions raised.

        Args:
            requests: List of LLM requests to process.

        Returns:
            List of LLMResponse objects in the same order as requests.

        Raises:
            LLMError: If any request fails fatally.
        """
        ...

    async def is_available(self) -> bool:
        """Check if the provider is configured and reachable.

        Returns:
            True if the provider can accept requests.
        """
        ...


# =============================================================================
# Factory Function
# =============================================================================


def get_provider(
    provider: LLMProvider | str,
    **kwargs: object,
) -> LLMProviderProtocol:
    """Get a provider instance by name.

    Args:
        provider: Provider enum or string name.
        **kwargs: Provider-specific configuration.

    Returns:
        LLMProviderProtocol implementation.

    Raises:
        ValueError: If provider is not recognized.
        ImportError: If provider dependencies are not installed.
    """
    from ..config import LLMProvider as LLMProviderEnum

    # Normalize to enum
    if isinstance(provider, str):
        provider_enum = LLMProviderEnum.from_string(provider)
    else:
        provider_enum = provider

    if provider_enum == LLMProviderEnum.ANTHROPIC:
        from .anthropic import AnthropicProvider

        return AnthropicProvider(**kwargs)  # type: ignore[arg-type]

    if provider_enum == LLMProviderEnum.OPENAI:
        from .openai import OpenAIProvider

        return OpenAIProvider(**kwargs)  # type: ignore[arg-type]

    if provider_enum == LLMProviderEnum.OLLAMA:
        from .ollama import OllamaProvider

        return OllamaProvider(**kwargs)  # type: ignore[arg-type]

    msg = f"Unknown provider: {provider_enum}"
    raise ValueError(msg)


# =============================================================================
# Lazy Imports
# =============================================================================


def __getattr__(name: str) -> object:
    """Lazy import for provider classes."""
    if name == "AnthropicProvider":
        from .anthropic import AnthropicProvider

        return AnthropicProvider
    if name == "OpenAIProvider":
        from .openai import OpenAIProvider

        return OpenAIProvider
    if name == "OllamaProvider":
        from .ollama import OllamaProvider

        return OllamaProvider
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
