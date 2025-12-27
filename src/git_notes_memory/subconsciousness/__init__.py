"""LLM-powered subconsciousness layer for intelligent memory management.

This module provides cognitive capabilities for the memory system:
- Implicit capture: Auto-detect memory-worthy content from transcripts
- Semantic linking: Bidirectional relationships between memories
- Memory decay: Archive stale memories based on access patterns
- Consolidation: Merge related memories into abstractions
- Proactive surfacing: Surface relevant memories before queries

Environment Variables:
    MEMORY_SUBCONSCIOUSNESS_ENABLED: Master switch (default: false)
    MEMORY_LLM_PROVIDER: LLM provider (anthropic, openai, ollama)
    MEMORY_LLM_MODEL: Model name (e.g., claude-sonnet-4-20250514)
    MEMORY_LLM_API_KEY: API key (or ANTHROPIC_API_KEY, OPENAI_API_KEY)

Example:
    >>> from git_notes_memory.subconsciousness import get_llm_client
    >>> client = get_llm_client()
    >>> response = await client.complete("Summarize this transcript")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_notes_memory.registry import ServiceRegistry

if TYPE_CHECKING:
    from .capture_store import CaptureStore
    from .config import SubconsciousnessConfig
    from .llm_client import LLMClient

__all__ = [
    # Configuration
    "is_subconsciousness_enabled",
    "get_subconsciousness_config",
    # Client
    "get_llm_client",
    # Capture Store
    "get_capture_store",
    # Hook Integration
    "is_subconsciousness_available",
    "analyze_session_transcript",
    "analyze_session_transcript_sync",
    "HookIntegrationResult",
    # Models (re-exported)
    "LLMResponse",
    "LLMConfig",
    "LLMUsage",
    "CaptureConfidence",
    "ImplicitMemory",
    "ImplicitCapture",
    "ThreatDetection",
    "ReviewStatus",
    "ThreatLevel",
    # Reset function for testing
    "reset_subconsciousness_services",
]


def is_subconsciousness_enabled() -> bool:
    """Check if subconsciousness features are enabled.

    Returns:
        True if MEMORY_SUBCONSCIOUSNESS_ENABLED is set to a truthy value.
    """
    from .config import is_subconsciousness_enabled as _is_enabled

    return _is_enabled()


def get_subconsciousness_config() -> SubconsciousnessConfig:
    """Get the subconsciousness configuration.

    Returns:
        SubconsciousnessConfig with all settings.
    """
    from .config import get_subconsciousness_config as _get_config

    return _get_config()


def get_llm_client() -> LLMClient:
    """Get the singleton LLM client instance.

    Uses ServiceRegistry for thread-safe singleton management.

    Returns:
        LLMClient configured based on environment variables.

    Raises:
        SubconsciousnessDisabledError: If subconsciousness is not enabled.
        LLMConfigurationError: If LLM provider is not configured.
    """
    from .llm_client import LLMClient as LLMClientClass
    from .llm_client import get_default_llm_client

    # Check if already registered
    try:
        return ServiceRegistry.get(LLMClientClass)
    except (TypeError, ValueError):
        # Not registered yet or needs initialization
        pass

    # Create and register
    client = get_default_llm_client()
    ServiceRegistry.register(LLMClientClass, client)
    return client


def get_capture_store() -> CaptureStore:
    """Get the singleton capture store instance.

    Uses ServiceRegistry for thread-safe singleton management.

    Returns:
        CaptureStore for storing implicit captures awaiting review.
    """
    from .capture_store import CaptureStore as CaptureStoreClass
    from .capture_store import get_default_capture_store

    # Check if already registered
    try:
        return ServiceRegistry.get(CaptureStoreClass)
    except (TypeError, ValueError):
        # Not registered yet or needs initialization
        pass

    # Create and register
    store = get_default_capture_store()
    ServiceRegistry.register(CaptureStoreClass, store)
    return store


def reset_subconsciousness_services() -> None:
    """Reset all subconsciousness service singletons.

    Used in testing to ensure clean state between tests.
    Also resets the module-level caches in individual service files.
    """
    from .adversarial_detector import reset_default_detector
    from .capture_store import reset_default_capture_store
    from .implicit_capture_agent import reset_default_agent
    from .implicit_capture_service import reset_implicit_capture_service
    from .llm_client import reset_default_client

    # Reset module-level caches
    reset_default_client()
    reset_default_capture_store()
    reset_default_detector()
    reset_default_agent()
    reset_implicit_capture_service()

    # ServiceRegistry.reset() is handled separately if needed


# Re-export models for convenience
def __getattr__(name: str) -> object:
    """Lazy import for models."""
    if name == "LLMResponse":
        from .models import LLMResponse

        return LLMResponse
    if name == "LLMConfig":
        from .models import LLMConfig

        return LLMConfig
    if name == "LLMUsage":
        from .models import LLMUsage

        return LLMUsage
    if name == "CaptureConfidence":
        from .models import CaptureConfidence

        return CaptureConfidence
    if name == "ImplicitMemory":
        from .models import ImplicitMemory

        return ImplicitMemory
    if name == "ImplicitCapture":
        from .models import ImplicitCapture

        return ImplicitCapture
    if name == "ThreatDetection":
        from .models import ThreatDetection

        return ThreatDetection
    if name == "ReviewStatus":
        from .models import ReviewStatus

        return ReviewStatus
    if name == "ThreatLevel":
        from .models import ThreatLevel

        return ThreatLevel
    if name == "SubconsciousnessConfig":
        from .config import SubconsciousnessConfig

        return SubconsciousnessConfig
    # Hook integration
    if name == "is_subconsciousness_available":
        from .hook_integration import is_subconsciousness_available

        return is_subconsciousness_available
    if name == "analyze_session_transcript":
        from .hook_integration import analyze_session_transcript

        return analyze_session_transcript
    if name == "analyze_session_transcript_sync":
        from .hook_integration import analyze_session_transcript_sync

        return analyze_session_transcript_sync
    if name == "HookIntegrationResult":
        from .hook_integration import HookIntegrationResult

        return HookIntegrationResult
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
