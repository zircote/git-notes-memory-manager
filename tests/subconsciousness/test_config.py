"""Tests for subconsciousness configuration."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from git_notes_memory.subconsciousness.config import (
    DEFAULT_ANTHROPIC_MODEL,
    DEFAULT_ARCHIVE_THRESHOLD,
    DEFAULT_AUTO_CAPTURE_THRESHOLD,
    DEFAULT_LLM_RPM_LIMIT,
    DEFAULT_LLM_TIMEOUT_MS,
    DEFAULT_OPENAI_MODEL,
    LLMProvider,
    get_llm_api_key,
    get_llm_model,
    get_llm_provider,
    get_subconsciousness_config,
    is_subconsciousness_enabled,
)

if TYPE_CHECKING:
    pass


class TestLLMProvider:
    """Tests for LLMProvider enum."""

    def test_from_string_anthropic(self) -> None:
        """Test parsing 'anthropic' provider."""
        assert LLMProvider.from_string("anthropic") == LLMProvider.ANTHROPIC
        assert LLMProvider.from_string("ANTHROPIC") == LLMProvider.ANTHROPIC
        assert LLMProvider.from_string("  Anthropic  ") == LLMProvider.ANTHROPIC

    def test_from_string_openai(self) -> None:
        """Test parsing 'openai' provider."""
        assert LLMProvider.from_string("openai") == LLMProvider.OPENAI

    def test_from_string_ollama(self) -> None:
        """Test parsing 'ollama' provider."""
        assert LLMProvider.from_string("ollama") == LLMProvider.OLLAMA

    def test_from_string_invalid(self) -> None:
        """Test parsing invalid provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMProvider.from_string("invalid")


class TestIsSubconsciousnessEnabled:
    """Tests for is_subconsciousness_enabled()."""

    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test subconsciousness is disabled by default."""
        monkeypatch.delenv("MEMORY_SUBCONSCIOUSNESS_ENABLED", raising=False)
        assert is_subconsciousness_enabled() is False

    def test_enabled_with_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test enabling with 'true'."""
        monkeypatch.setenv("MEMORY_SUBCONSCIOUSNESS_ENABLED", "true")
        assert is_subconsciousness_enabled() is True

    def test_enabled_with_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test enabling with '1'."""
        monkeypatch.setenv("MEMORY_SUBCONSCIOUSNESS_ENABLED", "1")
        assert is_subconsciousness_enabled() is True

    def test_disabled_with_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test explicitly disabled with 'false'."""
        monkeypatch.setenv("MEMORY_SUBCONSCIOUSNESS_ENABLED", "false")
        assert is_subconsciousness_enabled() is False


class TestGetLLMProvider:
    """Tests for get_llm_provider()."""

    def test_default_is_anthropic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default provider is Anthropic."""
        monkeypatch.delenv("MEMORY_LLM_PROVIDER", raising=False)
        assert get_llm_provider() == LLMProvider.ANTHROPIC

    def test_custom_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test setting custom provider."""
        monkeypatch.setenv("MEMORY_LLM_PROVIDER", "openai")
        assert get_llm_provider() == LLMProvider.OPENAI


class TestGetLLMModel:
    """Tests for get_llm_model()."""

    def test_default_anthropic_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default Anthropic model."""
        monkeypatch.delenv("MEMORY_LLM_MODEL", raising=False)
        assert get_llm_model(LLMProvider.ANTHROPIC) == DEFAULT_ANTHROPIC_MODEL

    def test_default_openai_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default OpenAI model."""
        monkeypatch.delenv("MEMORY_LLM_MODEL", raising=False)
        assert get_llm_model(LLMProvider.OPENAI) == DEFAULT_OPENAI_MODEL

    def test_explicit_model_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test explicit model override."""
        monkeypatch.setenv("MEMORY_LLM_MODEL", "custom-model")
        assert get_llm_model(LLMProvider.ANTHROPIC) == "custom-model"


class TestGetLLMApiKey:
    """Tests for get_llm_api_key()."""

    def test_anthropic_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test getting Anthropic API key."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
        monkeypatch.delenv("MEMORY_LLM_API_KEY", raising=False)
        assert get_llm_api_key(LLMProvider.ANTHROPIC) == "test-anthropic-key"

    def test_openai_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test getting OpenAI API key."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.delenv("MEMORY_LLM_API_KEY", raising=False)
        assert get_llm_api_key(LLMProvider.OPENAI) == "test-openai-key"

    def test_generic_key_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test generic key overrides provider-specific."""
        monkeypatch.setenv("MEMORY_LLM_API_KEY", "generic-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
        assert get_llm_api_key(LLMProvider.ANTHROPIC) == "generic-key"

    def test_ollama_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test Ollama returns None (no key needed)."""
        monkeypatch.delenv("MEMORY_LLM_API_KEY", raising=False)
        assert get_llm_api_key(LLMProvider.OLLAMA) is None


class TestGetSubconsciousnessConfig:
    """Tests for get_subconsciousness_config()."""

    def test_default_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test default configuration values."""
        # Clear all env vars
        for key in list(os.environ.keys()):
            if key.startswith("MEMORY_"):
                monkeypatch.delenv(key, raising=False)

        config = get_subconsciousness_config()

        assert config.enabled is False
        assert config.provider == LLMProvider.ANTHROPIC
        assert config.auto_capture_threshold == DEFAULT_AUTO_CAPTURE_THRESHOLD
        assert config.archive_threshold == DEFAULT_ARCHIVE_THRESHOLD
        assert config.rpm_limit == DEFAULT_LLM_RPM_LIMIT
        assert config.timeout_ms == DEFAULT_LLM_TIMEOUT_MS

    def test_custom_thresholds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test custom threshold configuration."""
        monkeypatch.setenv("MEMORY_AUTO_CAPTURE_THRESHOLD", "0.85")
        monkeypatch.setenv("MEMORY_ARCHIVE_THRESHOLD", "0.2")

        config = get_subconsciousness_config()

        assert config.auto_capture_threshold == 0.85
        assert config.archive_threshold == 0.2

    def test_feature_toggles(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test feature toggle configuration."""
        monkeypatch.setenv("MEMORY_IMPLICIT_CAPTURE_ENABLED", "false")
        monkeypatch.setenv("MEMORY_SURFACING_ENABLED", "false")

        config = get_subconsciousness_config()

        assert config.implicit_capture_enabled is False
        assert config.surfacing_enabled is False
        # Others default to True
        assert config.consolidation_enabled is True

    def test_config_is_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test config object is immutable."""
        config = get_subconsciousness_config()

        with pytest.raises(AttributeError):
            config.enabled = True  # type: ignore[misc]
