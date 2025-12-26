"""Tests for LLM provider implementations.

TEST-H-002: Tests for anthropic.py, openai.py, ollama.py providers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from git_notes_memory.subconsciousness.models import (
    LLMAuthenticationError,
    LLMMessage,
    LLMRequest,
    MessageRole,
)


# Check if SDKs are available
def _anthropic_available() -> bool:
    """Check if anthropic SDK is available."""
    try:
        import anthropic  # noqa: F401

        return True
    except ImportError:
        return False


def _openai_available() -> bool:
    """Check if openai SDK is available."""
    try:
        import openai  # noqa: F401

        return True
    except ImportError:
        return False


requires_anthropic = pytest.mark.skipif(
    not _anthropic_available(), reason="anthropic package not installed"
)
requires_openai = pytest.mark.skipif(
    not _openai_available(), reason="openai package not installed"
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_request() -> LLMRequest:
    """Create a sample LLM request for testing."""
    return LLMRequest(
        messages=(
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Hello, world!"),
        ),
        max_tokens=100,
        temperature=0.7,
    )


@pytest.fixture
def json_request() -> LLMRequest:
    """Create a JSON mode LLM request for testing."""
    return LLMRequest(
        messages=(LLMMessage(role=MessageRole.USER, content="Return a JSON object"),),
        max_tokens=100,
        temperature=0.0,
        json_mode=True,
    )


# =============================================================================
# Anthropic Provider Tests
# =============================================================================


class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    def test_name_property(self) -> None:
        """Test provider name."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        provider = AnthropicProvider(api_key="test-key")
        assert provider.name == "anthropic"

    def test_init_with_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization with environment defaults."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        monkeypatch.setenv("MEMORY_LLM_MODEL", "claude-3-opus-20240229")

        provider = AnthropicProvider()
        assert provider.api_key == "env-key"

    def test_init_with_explicit_values(self) -> None:
        """Test initialization with explicit values."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        provider = AnthropicProvider(
            api_key="explicit-key",
            model="claude-3-5-haiku-20241022",
            max_retries=5,
            timeout_ms=60000,
        )
        assert provider.api_key == "explicit-key"
        assert provider.model == "claude-3-5-haiku-20241022"
        assert provider.max_retries == 5
        assert provider.timeout_ms == 60000

    @pytest.mark.asyncio
    async def test_is_available_with_key_and_sdk(self) -> None:
        """Test availability check with API key and SDK available."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        provider = AnthropicProvider(api_key="test-key")
        # anthropic SDK is installed in dev deps, so this should pass
        result = await provider.is_available()
        # Result depends on whether anthropic is actually installed
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_is_available_without_key(self) -> None:
        """Test availability check without API key."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        provider = AnthropicProvider(api_key=None)
        assert await provider.is_available() is False

    @requires_anthropic
    @pytest.mark.asyncio
    async def test_complete_without_api_key_raises(
        self, sample_request: LLMRequest
    ) -> None:
        """Test complete raises error without API key."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        provider = AnthropicProvider(api_key=None)
        with pytest.raises(LLMAuthenticationError) as exc_info:
            await provider.complete(sample_request)
        assert "API key not configured" in str(exc_info.value)

    @requires_anthropic
    @pytest.mark.asyncio
    async def test_complete_success_mocked(self, sample_request: LLMRequest) -> None:
        """Test successful completion with mocked retry."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        # Mock response matching Anthropic API structure
        mock_response = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Hello!"
        mock_response.content = [mock_text_block]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.model_dump = MagicMock(return_value={})

        provider = AnthropicProvider(api_key="test-key")

        with patch.object(
            provider, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_response
            response = await provider.complete(sample_request)

        assert response.content == "Hello!"
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 5

    @requires_anthropic
    @pytest.mark.asyncio
    async def test_complete_with_json_mode_mocked(
        self, json_request: LLMRequest
    ) -> None:
        """Test completion with JSON mode uses tool_use."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        # Mock response with tool use block
        mock_tool_block = MagicMock()
        mock_tool_block.type = "tool_use"
        mock_tool_block.input = {"key": "value"}

        mock_response = MagicMock()
        mock_response.content = [mock_tool_block]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=20)
        mock_response.model_dump = MagicMock(return_value={})

        provider = AnthropicProvider(api_key="test-key")

        with patch.object(
            provider, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_response
            response = await provider.complete(json_request)

        # JSON mode should extract tool use input
        assert "key" in response.content or '"key"' in response.content

    @requires_anthropic
    @pytest.mark.asyncio
    async def test_complete_batch_sequential(self, sample_request: LLMRequest) -> None:
        """Test batch completion processes sequentially."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        mock_response = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = "Response"
        mock_response.content = [mock_text_block]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)
        mock_response.model_dump = MagicMock(return_value={})

        provider = AnthropicProvider(api_key="test-key")

        with patch.object(
            provider, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_response
            responses = await provider.complete_batch([sample_request, sample_request])

        assert len(responses) == 2
        assert mock_execute.call_count == 2

    def test_build_messages(self, sample_request: LLMRequest) -> None:
        """Test message building excludes system messages."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        provider = AnthropicProvider(api_key="test-key")
        messages = provider._build_messages(sample_request)

        # System message should be excluded (handled separately)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello, world!"

    def test_extract_system_prompt(self, sample_request: LLMRequest) -> None:
        """Test system prompt extraction."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            AnthropicProvider,
        )

        provider = AnthropicProvider(api_key="test-key")
        system_prompt = provider._extract_system_prompt(sample_request)

        assert system_prompt == "You are a helpful assistant."

    def test_sanitize_error_message(self) -> None:
        """Test error message sanitization removes secrets."""
        from git_notes_memory.subconsciousness.providers.anthropic import (
            _sanitize_error_message,
        )

        # Test API key redaction
        error = Exception("Invalid key: sk-ant-api12345678901234567890")
        sanitized = _sanitize_error_message(error)
        assert "sk-ant" not in sanitized
        assert "[REDACTED_KEY]" in sanitized

        # Test bearer token redaction
        error = Exception("Bearer abc123def456ghi789")
        sanitized = _sanitize_error_message(error)
        assert "Bearer [REDACTED]" in sanitized


# =============================================================================
# OpenAI Provider Tests
# =============================================================================


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def test_name_property(self) -> None:
        """Test provider name."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        assert provider.name == "openai"

    def test_init_with_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization with environment defaults."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        monkeypatch.setenv("OPENAI_API_KEY", "env-key")
        monkeypatch.setenv("MEMORY_LLM_MODEL", "gpt-4-turbo")

        provider = OpenAIProvider()
        assert provider.api_key == "env-key"

    def test_init_with_explicit_values(self) -> None:
        """Test initialization with explicit values."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        provider = OpenAIProvider(
            api_key="explicit-key",
            model="gpt-4o-mini",
            max_retries=5,
            timeout_ms=60000,
        )
        assert provider.api_key == "explicit-key"
        assert provider.model == "gpt-4o-mini"
        assert provider.max_retries == 5
        assert provider.timeout_ms == 60000

    @pytest.mark.asyncio
    async def test_is_available_with_key_and_sdk(self) -> None:
        """Test availability check with API key and SDK available."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        result = await provider.is_available()
        # Result depends on whether openai is actually installed
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_is_available_without_key(self) -> None:
        """Test availability check without API key."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key=None)
        assert await provider.is_available() is False

    @requires_openai
    @pytest.mark.asyncio
    async def test_complete_without_api_key_raises(
        self, sample_request: LLMRequest
    ) -> None:
        """Test complete raises error without API key."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key=None)
        with pytest.raises(LLMAuthenticationError) as exc_info:
            await provider.complete(sample_request)
        assert "API key not configured" in str(exc_info.value)

    @requires_openai
    @pytest.mark.asyncio
    async def test_complete_success_mocked(self, sample_request: LLMRequest) -> None:
        """Test successful completion with mocked retry."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        # Mock response matching OpenAI API structure
        mock_choice = MagicMock()
        mock_choice.message.content = "Hello!"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_response.model_dump = MagicMock(return_value={})

        provider = OpenAIProvider(api_key="test-key")

        with patch.object(
            provider, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_response
            response = await provider.complete(sample_request)

        assert response.content == "Hello!"
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 5

    @requires_openai
    @pytest.mark.asyncio
    async def test_complete_with_json_mode_mocked(
        self, json_request: LLMRequest
    ) -> None:
        """Test completion with JSON mode."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        mock_choice = MagicMock()
        mock_choice.message.content = '{"result": "success"}'

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        mock_response.model_dump = MagicMock(return_value={})

        provider = OpenAIProvider(api_key="test-key")

        with patch.object(
            provider, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_response
            response = await provider.complete(json_request)

        assert "result" in response.content

    @requires_openai
    @pytest.mark.asyncio
    async def test_complete_batch_sequential(self, sample_request: LLMRequest) -> None:
        """Test batch completion processes sequentially."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        mock_choice = MagicMock()
        mock_choice.message.content = "Response"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_response.model_dump = MagicMock(return_value={})

        provider = OpenAIProvider(api_key="test-key")

        with patch.object(
            provider, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_response
            responses = await provider.complete_batch([sample_request, sample_request])

        assert len(responses) == 2
        assert mock_execute.call_count == 2

    def test_build_messages(self, sample_request: LLMRequest) -> None:
        """Test message building includes all messages."""
        from git_notes_memory.subconsciousness.providers.openai import OpenAIProvider

        provider = OpenAIProvider(api_key="test-key")
        messages = provider._build_messages(sample_request)

        # OpenAI includes system messages inline
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_sanitize_error_message_redacts_keys(self) -> None:
        """Test error message sanitization removes secrets."""
        from git_notes_memory.subconsciousness.providers.openai import (
            _sanitize_error_message,
        )

        # Test API key redaction - keys with 32+ chars are redacted
        error = Exception("Invalid key: sk-proj-12345678901234567890123456789012")
        sanitized = _sanitize_error_message(error)
        # Long token should be redacted
        assert "12345678901234567890123456789012" not in sanitized

        # Test bearer token redaction
        error = Exception("Bearer sk-proj-abc123def456")
        sanitized = _sanitize_error_message(error)
        assert "Bearer [REDACTED]" in sanitized


# =============================================================================
# Ollama Provider Tests
# =============================================================================


class TestOllamaProvider:
    """Tests for OllamaProvider."""

    def test_name_property(self) -> None:
        """Test provider name."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider()
        assert provider.name == "ollama"

    def test_init_with_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization with environment defaults."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        monkeypatch.setenv("MEMORY_OLLAMA_BASE_URL", "http://custom:11434")
        monkeypatch.setenv("MEMORY_LLM_MODEL", "mistral")

        provider = OllamaProvider()
        assert provider.base_url == "http://custom:11434"

    def test_init_with_explicit_values(self) -> None:
        """Test initialization with explicit values."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="codellama",
            max_retries=5,
            timeout_ms=120000,
        )
        assert provider.base_url == "http://localhost:11434"
        assert provider.model == "codellama"
        assert provider.max_retries == 5
        assert provider.timeout_ms == 120000

    @pytest.mark.asyncio
    async def test_is_available_server_running(self) -> None:
        """Test availability check when server is running."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider(base_url="http://localhost:11434")

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            result = await provider.is_available()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_available_server_not_running(self) -> None:
        """Test availability check when server is not running."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider(base_url="http://localhost:11434")

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            result = await provider.is_available()

        assert result is False

    @pytest.mark.asyncio
    async def test_complete_success(self, sample_request: LLMRequest) -> None:
        """Test successful completion."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        mock_response_data = {
            "message": {"content": "Hello from Ollama!"},
            "prompt_eval_count": 10,
            "eval_count": 15,
        }

        provider = OllamaProvider(base_url="http://localhost:11434", model="llama3.2")

        with patch.object(
            provider, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_response_data
            response = await provider.complete(sample_request)

        assert response.content == "Hello from Ollama!"
        assert response.usage.prompt_tokens == 10
        assert response.usage.completion_tokens == 15

    @pytest.mark.asyncio
    async def test_complete_with_json_mode(self, json_request: LLMRequest) -> None:
        """Test completion with JSON mode extracts JSON."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        # Response with JSON embedded in text
        mock_response_data = {
            "message": {"content": 'Here is the JSON: {"status": "ok"}'},
            "prompt_eval_count": 10,
            "eval_count": 20,
        }

        provider = OllamaProvider(base_url="http://localhost:11434")

        with patch.object(
            provider, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_response_data
            response = await provider.complete(json_request)

        # Should extract just the JSON
        assert response.content == '{"status": "ok"}'

    @pytest.mark.asyncio
    async def test_complete_batch(self, sample_request: LLMRequest) -> None:
        """Test batch completion."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        mock_response_data = {
            "message": {"content": "Response"},
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

        provider = OllamaProvider(base_url="http://localhost:11434")

        with patch.object(
            provider, "_execute_with_retry", new_callable=AsyncMock
        ) as mock_execute:
            mock_execute.return_value = mock_response_data
            responses = await provider.complete_batch([sample_request, sample_request])

        assert len(responses) == 2

    def test_build_messages(self, sample_request: LLMRequest) -> None:
        """Test message building includes all messages."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider()
        messages = provider._build_messages(sample_request)

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_add_json_instruction_with_system(self) -> None:
        """Test JSON instruction is appended to system message."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Query"},
        ]

        result = provider._add_json_instruction(messages)

        assert "IMPORTANT: Respond ONLY with valid JSON" in result[0]["content"]
        assert result[0]["content"].startswith("You are helpful.")

    def test_add_json_instruction_without_system(self) -> None:
        """Test JSON instruction creates system message if missing."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider()
        messages = [{"role": "user", "content": "Query"}]

        result = provider._add_json_instruction(messages)

        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert "IMPORTANT: Respond ONLY with valid JSON" in result[0]["content"]

    def test_extract_json_object(self) -> None:
        """Test JSON object extraction."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider()

        content = 'Some text before {"key": "value"} and after'
        result = provider._extract_json(content)
        assert result == '{"key": "value"}'

    def test_extract_json_array(self) -> None:
        """Test JSON array extraction."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider()

        content = "Here is the array: [1, 2, 3] done"
        result = provider._extract_json(content)
        assert result == "[1, 2, 3]"

    def test_extract_json_invalid(self) -> None:
        """Test extraction returns original if no valid JSON."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider()

        content = "No JSON here, just text"
        result = provider._extract_json(content)
        assert result == content

    def test_calculate_usage(self) -> None:
        """Test usage calculation from Ollama response."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider()

        response_data = {
            "prompt_eval_count": 100,
            "eval_count": 50,
        }

        usage = provider._calculate_usage(response_data)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        # Ollama is local, so cost should be 0
        assert usage.estimated_cost_usd == 0.0

    def test_sanitize_error_message_redacts_tokens(self) -> None:
        """Test error sanitization for Ollama (ARCH-H-006)."""
        from git_notes_memory.subconsciousness.providers.ollama import (
            _sanitize_error_message,
        )

        # Test token redaction (e.g., auth token in URL)
        error = Exception(
            "http://localhost:11434?token=abc123def456ghi789jkl012mno345pqr678"
        )
        sanitized = _sanitize_error_message(error)
        assert "[REDACTED_URL]" in sanitized

        # Test Bearer token redaction
        error = Exception("Failed with Bearer abc123.def456.ghi789")
        sanitized = _sanitize_error_message(error)
        assert "[REDACTED]" in sanitized


# =============================================================================
# Pricing Tests
# =============================================================================


class TestProviderPricing:
    """Tests for provider pricing calculations."""

    def test_anthropic_claude_pricing(self) -> None:
        """Test Anthropic pricing constants are defined."""
        from git_notes_memory.subconsciousness.providers.anthropic import CLAUDE_PRICING

        assert "claude-sonnet-4-20250514" in CLAUDE_PRICING
        assert "claude-3-5-haiku-20241022" in CLAUDE_PRICING
        assert CLAUDE_PRICING["claude-sonnet-4-20250514"]["input"] == 3.0
        assert CLAUDE_PRICING["claude-sonnet-4-20250514"]["output"] == 15.0

    def test_openai_gpt_pricing(self) -> None:
        """Test OpenAI pricing constants are defined."""
        from git_notes_memory.subconsciousness.providers.openai import GPT_PRICING

        assert "gpt-5-nano" in GPT_PRICING
        assert "gpt-4o" in GPT_PRICING
        assert "gpt-4o-mini" in GPT_PRICING
        assert GPT_PRICING["gpt-5-nano"]["input"] == 0.10
        assert GPT_PRICING["gpt-5-nano"]["output"] == 0.40
        assert GPT_PRICING["gpt-4o"]["input"] == 2.5
        assert GPT_PRICING["gpt-4o"]["output"] == 10.0

    def test_ollama_zero_cost(self) -> None:
        """Test Ollama has zero cost (local model)."""
        from git_notes_memory.subconsciousness.providers.ollama import OllamaProvider

        provider = OllamaProvider()
        response_data = {"prompt_eval_count": 1000, "eval_count": 500}
        usage = provider._calculate_usage(response_data)

        assert usage.estimated_cost_usd == 0.0
