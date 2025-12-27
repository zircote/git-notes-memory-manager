"""Configuration for the subconsciousness layer.

This module provides configuration management for LLM-powered features.
All settings can be overridden via environment variables.

Environment Variables:
    MEMORY_SUBCONSCIOUSNESS_ENABLED: Master switch (default: false)
    MEMORY_LLM_PROVIDER: Provider name (anthropic, openai, ollama)
    MEMORY_LLM_MODEL: Model name for the provider
    MEMORY_LLM_API_KEY: API key (falls back to provider-specific keys)

    # Thresholds
    MEMORY_AUTO_CAPTURE_THRESHOLD: Confidence for auto-capture (default: 0.9)
    MEMORY_REVIEW_THRESHOLD: Confidence for review queue (default: 0.7)
    MEMORY_ARCHIVE_THRESHOLD: Decay score for archival (default: 0.3)
    MEMORY_SURFACING_THRESHOLD: Relevance for surfacing (default: 0.6)
    MEMORY_CONSOLIDATION_THRESHOLD: Similarity for consolidation (default: 0.85)

    # Feature toggles
    MEMORY_IMPLICIT_CAPTURE_ENABLED: Enable implicit capture (default: true)
    MEMORY_CONSOLIDATION_ENABLED: Enable consolidation (default: true)
    MEMORY_FORGETTING_ENABLED: Enable decay/forgetting (default: true)
    MEMORY_SURFACING_ENABLED: Enable proactive surfacing (default: true)
    MEMORY_LINKING_ENABLED: Enable semantic linking (default: true)

    # Rate limits
    MEMORY_LLM_RPM_LIMIT: Requests per minute (default: 60)
    MEMORY_LLM_TPM_LIMIT: Tokens per minute (default: 100000)
    MEMORY_LLM_DAILY_COST_LIMIT: Daily cost limit in USD (default: 10.0)

    # Timeouts
    MEMORY_LLM_TIMEOUT_MS: Request timeout in milliseconds (default: 30000)
    MEMORY_LLM_BATCH_TIMEOUT_MS: Batch timeout in milliseconds (default: 5000)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

__all__ = [
    # Enums
    "LLMProvider",
    # Configuration
    "SubconsciousnessConfig",
    "get_subconsciousness_config",
    # Helpers
    "is_subconsciousness_enabled",
    "get_llm_provider",
    "get_llm_model",
    "get_llm_api_key",
    # Defaults
    "DEFAULT_LLM_PROVIDER",
    "DEFAULT_ANTHROPIC_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_OLLAMA_MODEL",
    "DEFAULT_AUTO_CAPTURE_THRESHOLD",
    "DEFAULT_REVIEW_THRESHOLD",
    "DEFAULT_ARCHIVE_THRESHOLD",
    "DEFAULT_SURFACING_THRESHOLD",
    "DEFAULT_CONSOLIDATION_THRESHOLD",
    "DEFAULT_LLM_RPM_LIMIT",
    "DEFAULT_LLM_TPM_LIMIT",
    "DEFAULT_LLM_DAILY_COST_LIMIT",
    "DEFAULT_LLM_TIMEOUT_MS",
    "DEFAULT_LLM_BATCH_TIMEOUT_MS",
]


# =============================================================================
# Enums
# =============================================================================


class LLMProvider(Enum):
    """Supported LLM providers.

    Each provider has different capabilities and configuration requirements:
    - ANTHROPIC: Claude models, JSON via tool_use pattern
    - OPENAI: GPT models, native JSON mode
    - OLLAMA: Local models, basic JSON parsing
    """

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"

    @classmethod
    def from_string(cls, value: str) -> LLMProvider:
        """Parse a provider string to enum.

        Args:
            value: Provider name (case-insensitive)

        Returns:
            LLMProvider enum value.

        Raises:
            ValueError: If provider is not recognized.
        """
        value_lower = value.lower().strip()
        for provider in cls:
            if provider.value == value_lower:
                return provider
        valid = ", ".join(p.value for p in cls)
        msg = f"Unknown LLM provider: {value!r}. Valid providers: {valid}"
        raise ValueError(msg)


# =============================================================================
# Defaults
# =============================================================================

# Provider defaults
DEFAULT_LLM_PROVIDER = LLMProvider.OPENAI
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_OLLAMA_MODEL = "llama3.2"

# Threshold defaults
DEFAULT_AUTO_CAPTURE_THRESHOLD = 0.9
DEFAULT_REVIEW_THRESHOLD = 0.7
DEFAULT_ARCHIVE_THRESHOLD = 0.3
DEFAULT_SURFACING_THRESHOLD = 0.6
DEFAULT_CONSOLIDATION_THRESHOLD = 0.85

# Rate limit defaults
DEFAULT_LLM_RPM_LIMIT = 60  # requests per minute
DEFAULT_LLM_TPM_LIMIT = 100_000  # tokens per minute
DEFAULT_LLM_DAILY_COST_LIMIT = 10.0  # USD

# Timeout defaults
DEFAULT_LLM_TIMEOUT_MS = 30_000  # 30 seconds
DEFAULT_LLM_BATCH_TIMEOUT_MS = 5_000  # 5 seconds for batch flush


# =============================================================================
# Configuration Dataclass
# =============================================================================


@dataclass(frozen=True)
class SubconsciousnessConfig:
    """Complete configuration for the subconsciousness layer.

    This frozen dataclass holds all configuration values for LLM-powered
    features. Use get_subconsciousness_config() to get the singleton instance.

    Attributes:
        enabled: Master switch for subconsciousness features.
        provider: Which LLM provider to use.
        model: Model name for the provider.
        api_key: API key for the provider (may be None for Ollama).

        auto_capture_threshold: Confidence for auto-capture (>= this = auto).
        review_threshold: Confidence for review queue (>= this = queue).
        archive_threshold: Decay score for archival (<= this = archive).
        surfacing_threshold: Relevance for surfacing (>= this = surface).
        consolidation_threshold: Similarity for consolidation.

        implicit_capture_enabled: Enable implicit transcript capture.
        consolidation_enabled: Enable memory consolidation.
        forgetting_enabled: Enable decay-based archival.
        surfacing_enabled: Enable proactive memory surfacing.
        linking_enabled: Enable semantic memory linking.

        rpm_limit: Maximum requests per minute.
        tpm_limit: Maximum tokens per minute.
        daily_cost_limit: Maximum daily cost in USD.

        timeout_ms: Request timeout in milliseconds.
        batch_timeout_ms: Batch flush timeout in milliseconds.
    """

    # Core settings
    enabled: bool = False
    provider: LLMProvider = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_OPENAI_MODEL
    api_key: str | None = None

    # Thresholds
    auto_capture_threshold: float = DEFAULT_AUTO_CAPTURE_THRESHOLD
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD
    archive_threshold: float = DEFAULT_ARCHIVE_THRESHOLD
    surfacing_threshold: float = DEFAULT_SURFACING_THRESHOLD
    consolidation_threshold: float = DEFAULT_CONSOLIDATION_THRESHOLD

    # Feature toggles
    implicit_capture_enabled: bool = True
    consolidation_enabled: bool = True
    forgetting_enabled: bool = True
    surfacing_enabled: bool = True
    linking_enabled: bool = True

    # Rate limits
    rpm_limit: int = DEFAULT_LLM_RPM_LIMIT
    tpm_limit: int = DEFAULT_LLM_TPM_LIMIT
    daily_cost_limit: float = DEFAULT_LLM_DAILY_COST_LIMIT

    # Timeouts
    timeout_ms: int = DEFAULT_LLM_TIMEOUT_MS
    batch_timeout_ms: int = DEFAULT_LLM_BATCH_TIMEOUT_MS

    # Ollama-specific
    ollama_base_url: str = field(default="http://localhost:11434")


# =============================================================================
# Helper Functions
# =============================================================================


def _parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse a boolean environment variable.

    Args:
        value: Environment variable value.
        default: Default if value is None or empty.

    Returns:
        Boolean interpretation of the value.
    """
    if not value:
        return default
    return value.lower() in ("1", "true", "yes", "on", "enabled")


def _parse_float(value: str | None, default: float) -> float:
    """Parse a float environment variable.

    Args:
        value: Environment variable value.
        default: Default if value is None or invalid.

    Returns:
        Float value or default.
    """
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_int(value: str | None, default: int) -> int:
    """Parse an integer environment variable.

    Args:
        value: Environment variable value.
        default: Default if value is None or invalid.

    Returns:
        Integer value or default.
    """
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def is_subconsciousness_enabled() -> bool:
    """Check if subconsciousness features are enabled.

    Returns:
        True if MEMORY_SUBCONSCIOUSNESS_ENABLED is truthy.
    """
    return _parse_bool(os.environ.get("MEMORY_SUBCONSCIOUSNESS_ENABLED"), False)


def get_llm_provider() -> LLMProvider:
    """Get the configured LLM provider.

    Returns:
        LLMProvider enum value.
    """
    value = os.environ.get("MEMORY_LLM_PROVIDER")
    if not value:
        return DEFAULT_LLM_PROVIDER
    return LLMProvider.from_string(value)


def get_llm_model(provider: LLMProvider | None = None) -> str:
    """Get the model name for the specified provider.

    Args:
        provider: LLM provider. Uses configured provider if None.

    Returns:
        Model name string.
    """
    # Check for explicit model override
    explicit_model = os.environ.get("MEMORY_LLM_MODEL")
    if explicit_model:
        return explicit_model

    # Use provider-specific defaults
    if provider is None:
        provider = get_llm_provider()

    if provider == LLMProvider.ANTHROPIC:
        return DEFAULT_ANTHROPIC_MODEL
    if provider == LLMProvider.OPENAI:
        return DEFAULT_OPENAI_MODEL
    if provider == LLMProvider.OLLAMA:
        return DEFAULT_OLLAMA_MODEL

    return DEFAULT_ANTHROPIC_MODEL


def get_llm_api_key(provider: LLMProvider | None = None) -> str | None:
    """Get the API key for the specified provider.

    Checks in order:
    1. MEMORY_LLM_API_KEY (generic override)
    2. Provider-specific key (ANTHROPIC_API_KEY, OPENAI_API_KEY)

    Args:
        provider: LLM provider. Uses configured provider if None.

    Returns:
        API key string or None if not found (OK for Ollama).
    """
    # Check for generic override
    generic_key = os.environ.get("MEMORY_LLM_API_KEY")
    if generic_key:
        return generic_key

    # Check provider-specific keys
    if provider is None:
        provider = get_llm_provider()

    if provider == LLMProvider.ANTHROPIC:
        return os.environ.get("ANTHROPIC_API_KEY")
    if provider == LLMProvider.OPENAI:
        return os.environ.get("OPENAI_API_KEY")
    if provider == LLMProvider.OLLAMA:
        return None  # Ollama doesn't require an API key

    return None


def get_subconsciousness_config() -> SubconsciousnessConfig:
    """Get the complete subconsciousness configuration.

    Reads all environment variables and returns a frozen config object.
    This function does not cache; call sparingly or cache the result.

    Returns:
        SubconsciousnessConfig with all settings.
    """
    provider = get_llm_provider()

    return SubconsciousnessConfig(
        # Core settings
        enabled=is_subconsciousness_enabled(),
        provider=provider,
        model=get_llm_model(provider),
        api_key=get_llm_api_key(provider),
        # Thresholds
        auto_capture_threshold=_parse_float(
            os.environ.get("MEMORY_AUTO_CAPTURE_THRESHOLD"),
            DEFAULT_AUTO_CAPTURE_THRESHOLD,
        ),
        review_threshold=_parse_float(
            os.environ.get("MEMORY_REVIEW_THRESHOLD"),
            DEFAULT_REVIEW_THRESHOLD,
        ),
        archive_threshold=_parse_float(
            os.environ.get("MEMORY_ARCHIVE_THRESHOLD"),
            DEFAULT_ARCHIVE_THRESHOLD,
        ),
        surfacing_threshold=_parse_float(
            os.environ.get("MEMORY_SURFACING_THRESHOLD"),
            DEFAULT_SURFACING_THRESHOLD,
        ),
        consolidation_threshold=_parse_float(
            os.environ.get("MEMORY_CONSOLIDATION_THRESHOLD"),
            DEFAULT_CONSOLIDATION_THRESHOLD,
        ),
        # Feature toggles
        implicit_capture_enabled=_parse_bool(
            os.environ.get("MEMORY_IMPLICIT_CAPTURE_ENABLED"),
            True,
        ),
        consolidation_enabled=_parse_bool(
            os.environ.get("MEMORY_CONSOLIDATION_ENABLED"),
            True,
        ),
        forgetting_enabled=_parse_bool(
            os.environ.get("MEMORY_FORGETTING_ENABLED"),
            True,
        ),
        surfacing_enabled=_parse_bool(
            os.environ.get("MEMORY_SURFACING_ENABLED"),
            True,
        ),
        linking_enabled=_parse_bool(
            os.environ.get("MEMORY_LINKING_ENABLED"),
            True,
        ),
        # Rate limits
        rpm_limit=_parse_int(
            os.environ.get("MEMORY_LLM_RPM_LIMIT"),
            DEFAULT_LLM_RPM_LIMIT,
        ),
        tpm_limit=_parse_int(
            os.environ.get("MEMORY_LLM_TPM_LIMIT"),
            DEFAULT_LLM_TPM_LIMIT,
        ),
        daily_cost_limit=_parse_float(
            os.environ.get("MEMORY_LLM_DAILY_COST_LIMIT"),
            DEFAULT_LLM_DAILY_COST_LIMIT,
        ),
        # Timeouts
        timeout_ms=_parse_int(
            os.environ.get("MEMORY_LLM_TIMEOUT_MS"),
            DEFAULT_LLM_TIMEOUT_MS,
        ),
        batch_timeout_ms=_parse_int(
            os.environ.get("MEMORY_LLM_BATCH_TIMEOUT_MS"),
            DEFAULT_LLM_BATCH_TIMEOUT_MS,
        ),
        # Ollama
        ollama_base_url=os.environ.get(
            "MEMORY_OLLAMA_BASE_URL",
            "http://localhost:11434",
        ),
    )
