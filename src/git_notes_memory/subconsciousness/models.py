"""Data models for the subconsciousness LLM layer.

This module defines frozen dataclasses for LLM requests, responses, and errors.
All models are immutable for thread-safety and to prevent accidental mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

__all__ = [
    # Enums
    "LLMErrorType",
    "MessageRole",
    "ReviewStatus",
    "ThreatLevel",
    # LLM Request Models
    "LLMRequest",
    "LLMMessage",
    # LLM Response Models
    "LLMUsage",
    "LLMResponse",
    "LLMConfig",
    # Implicit Capture Models
    "CaptureConfidence",
    "ImplicitMemory",
    "ImplicitCapture",
    "ThreatDetection",
    # Error Models
    "LLMError",
    "LLMRateLimitError",
    "LLMAuthenticationError",
    "LLMTimeoutError",
    "LLMConnectionError",
    "LLMProviderError",
]


# =============================================================================
# Enums
# =============================================================================


class MessageRole(Enum):
    """Role of a message in an LLM conversation.

    Attributes:
        USER: Message from the user/application.
        ASSISTANT: Message from the LLM.
        SYSTEM: System prompt/instructions.
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ReviewStatus(Enum):
    """Status of an implicit capture awaiting review.

    Captures move through this lifecycle:
    - PENDING: Awaiting human review
    - APPROVED: User approved, ready for permanent storage
    - REJECTED: User rejected, will be discarded
    - EXPIRED: Review window expired, auto-discarded
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ThreatLevel(Enum):
    """Adversarial threat level detected in content.

    Used to screen for prompt injection, data exfiltration,
    and other malicious patterns in transcripts.

    Levels:
    - NONE: No adversarial patterns detected
    - LOW: Minor suspicious patterns, likely benign
    - MEDIUM: Concerning patterns, flag for review
    - HIGH: Strong adversarial indicators, block capture
    - CRITICAL: Definite attack, block and alert
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LLMErrorType(Enum):
    """Categories of LLM errors for retry logic.

    Used to determine appropriate retry behavior:
    - RATE_LIMIT: Wait and retry with backoff
    - AUTHENTICATION: Do not retry, fix configuration
    - TIMEOUT: Retry with longer timeout
    - CONNECTION: Retry after brief delay
    - PROVIDER: Provider-specific error, may retry
    - UNKNOWN: Unknown error, log and may retry
    """

    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    PROVIDER = "provider"
    UNKNOWN = "unknown"


# =============================================================================
# Request Models
# =============================================================================


@dataclass(frozen=True)
class LLMMessage:
    """A single message in an LLM conversation.

    Attributes:
        role: Who sent this message (user, assistant, system).
        content: Text content of the message.
    """

    role: MessageRole
    content: str

    @classmethod
    def user(cls, content: str) -> LLMMessage:
        """Create a user message."""
        return cls(role=MessageRole.USER, content=content)

    @classmethod
    def assistant(cls, content: str) -> LLMMessage:
        """Create an assistant message."""
        return cls(role=MessageRole.ASSISTANT, content=content)

    @classmethod
    def system(cls, content: str) -> LLMMessage:
        """Create a system message."""
        return cls(role=MessageRole.SYSTEM, content=content)


@dataclass(frozen=True)
class LLMRequest:
    """A request to an LLM provider.

    Attributes:
        messages: Conversation messages.
        model: Model name override (uses config default if None).
        max_tokens: Maximum tokens in response.
        temperature: Sampling temperature (0.0-2.0).
        json_mode: Request structured JSON output.
        json_schema: JSON schema for structured output.
        timeout_ms: Request-specific timeout override.
        request_id: Unique identifier for tracking.
    """

    messages: tuple[LLMMessage, ...]
    model: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0
    json_mode: bool = False
    json_schema: dict[str, Any] | None = None
    timeout_ms: int | None = None
    request_id: str | None = None

    @classmethod
    def simple(
        cls,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
    ) -> LLMRequest:
        """Create a simple single-turn request.

        Args:
            prompt: User prompt text.
            system: Optional system prompt.
            json_mode: Request structured JSON output.

        Returns:
            LLMRequest with the configured messages.
        """
        messages: list[LLMMessage] = []
        if system:
            messages.append(LLMMessage.system(system))
        messages.append(LLMMessage.user(prompt))
        return cls(messages=tuple(messages), json_mode=json_mode)


# =============================================================================
# Response Models
# =============================================================================


@dataclass(frozen=True)
class LLMUsage:
    """Token usage information from an LLM response.

    Attributes:
        prompt_tokens: Tokens in the input prompt.
        completion_tokens: Tokens in the generated response.
        total_tokens: Sum of prompt and completion tokens.
        estimated_cost_usd: Estimated cost in USD (approximate).
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float = 0.0

    @classmethod
    def from_tokens(
        cls,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        input_cost_per_million: float = 0.0,
        output_cost_per_million: float = 0.0,
    ) -> LLMUsage:
        """Create usage from token counts with optional cost calculation.

        Args:
            prompt_tokens: Input tokens.
            completion_tokens: Output tokens.
            input_cost_per_million: Cost per million input tokens.
            output_cost_per_million: Cost per million output tokens.

        Returns:
            LLMUsage with calculated cost.
        """
        total = prompt_tokens + completion_tokens
        cost = (
            prompt_tokens * input_cost_per_million / 1_000_000
            + completion_tokens * output_cost_per_million / 1_000_000
        )
        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            estimated_cost_usd=cost,
        )


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM provider.

    Attributes:
        content: Text content of the response.
        model: Model that generated the response.
        usage: Token usage information.
        latency_ms: Request latency in milliseconds.
        request_id: Unique identifier for the request.
        timestamp: When the response was received.
        raw_response: Raw response from provider (for debugging).
    """

    content: str
    model: str
    usage: LLMUsage
    latency_ms: int
    request_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    raw_response: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dict."""
        return {
            "content": self.content,
            "model": self.model,
            "usage": {
                "prompt_tokens": self.usage.prompt_tokens,
                "completion_tokens": self.usage.completion_tokens,
                "total_tokens": self.usage.total_tokens,
                "estimated_cost_usd": self.usage.estimated_cost_usd,
            },
            "latency_ms": self.latency_ms,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass(frozen=True)
class LLMConfig:
    """Provider-specific configuration.

    Used to configure individual LLM providers with their specific
    settings like model names, base URLs, and rate limits.

    Attributes:
        provider_name: Name of the provider (anthropic, openai, ollama).
        model: Model name to use.
        api_key: API key for authentication (optional for Ollama).
        base_url: Base URL for API calls (optional override).
        timeout_ms: Request timeout in milliseconds.
        max_retries: Maximum retry attempts.
        rate_limit_rpm: Requests per minute limit.
        rate_limit_tpm: Tokens per minute limit.
    """

    provider_name: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    timeout_ms: int = 30_000
    max_retries: int = 3
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100_000


# =============================================================================
# Implicit Capture Models
# =============================================================================


@dataclass(frozen=True)
class CaptureConfidence:
    """Confidence score with factor breakdown for explainability.

    The overall score is a weighted combination of individual factors.
    Each factor is normalized to 0.0-1.0 range.

    Attributes:
        overall: Combined confidence score (0.0-1.0).
        relevance: How relevant is this to the project/context.
        actionability: Is this actionable (decision, task, learning)?
        novelty: Is this new information vs. already captured?
        specificity: Is this specific enough to be useful?
        coherence: Is the content well-formed and coherent?
    """

    overall: float
    relevance: float = 0.0
    actionability: float = 0.0
    novelty: float = 0.0
    specificity: float = 0.0
    coherence: float = 0.0

    def __post_init__(self) -> None:
        """Validate all scores are in valid range."""
        for field_name in (
            "overall",
            "relevance",
            "actionability",
            "novelty",
            "specificity",
            "coherence",
        ):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                msg = f"{field_name} must be between 0.0 and 1.0, got {value}"
                raise ValueError(msg)

    @classmethod
    def from_factors(
        cls,
        *,
        relevance: float = 0.0,
        actionability: float = 0.0,
        novelty: float = 0.0,
        specificity: float = 0.0,
        coherence: float = 0.0,
        weights: dict[str, float] | None = None,
    ) -> CaptureConfidence:
        """Create confidence from individual factors.

        Args:
            relevance: Relevance score (0.0-1.0).
            actionability: Actionability score (0.0-1.0).
            novelty: Novelty score (0.0-1.0).
            specificity: Specificity score (0.0-1.0).
            coherence: Coherence score (0.0-1.0).
            weights: Optional custom weights for each factor.

        Returns:
            CaptureConfidence with calculated overall score.
        """
        default_weights = {
            "relevance": 0.25,
            "actionability": 0.30,
            "novelty": 0.20,
            "specificity": 0.15,
            "coherence": 0.10,
        }
        w = weights or default_weights

        overall = (
            relevance * w.get("relevance", 0.25)
            + actionability * w.get("actionability", 0.30)
            + novelty * w.get("novelty", 0.20)
            + specificity * w.get("specificity", 0.15)
            + coherence * w.get("coherence", 0.10)
        )

        return cls(
            overall=min(1.0, max(0.0, overall)),
            relevance=relevance,
            actionability=actionability,
            novelty=novelty,
            specificity=specificity,
            coherence=coherence,
        )


@dataclass(frozen=True)
class ImplicitMemory:
    """A memory extracted from transcript analysis.

    This represents the content that was identified as memory-worthy
    by the LLM analysis, before user review.

    Attributes:
        namespace: Memory namespace (decisions, learnings, etc.).
        summary: One-line summary (≤100 chars).
        content: Full memory content.
        confidence: Confidence score with factor breakdown.
        source_hash: SHA256 hash of source transcript for deduplication.
        source_range: Line range in source (start, end).
        rationale: LLM's explanation for why this is memory-worthy.
        tags: Suggested tags for the memory.
    """

    namespace: str
    summary: str
    content: str
    confidence: CaptureConfidence
    source_hash: str
    source_range: tuple[int, int] | None = None
    rationale: str = ""
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "namespace": self.namespace,
            "summary": self.summary,
            "content": self.content,
            "confidence": {
                "overall": self.confidence.overall,
                "relevance": self.confidence.relevance,
                "actionability": self.confidence.actionability,
                "novelty": self.confidence.novelty,
                "specificity": self.confidence.specificity,
                "coherence": self.confidence.coherence,
            },
            "source_hash": self.source_hash,
            "source_range": list(self.source_range) if self.source_range else None,
            "rationale": self.rationale,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class ThreatDetection:
    """Result of adversarial content screening.

    Used to detect and classify potential prompt injection,
    data exfiltration attempts, and other malicious patterns.

    Attributes:
        level: Overall threat level.
        patterns_found: List of specific patterns detected.
        explanation: Human-readable explanation of findings.
        should_block: Whether capture should be blocked.
    """

    level: ThreatLevel
    patterns_found: tuple[str, ...] = ()
    explanation: str = ""
    should_block: bool = False

    @classmethod
    def safe(cls) -> ThreatDetection:
        """Create a detection result indicating no threats."""
        return cls(level=ThreatLevel.NONE)

    @classmethod
    def blocked(
        cls,
        level: ThreatLevel,
        patterns: list[str],
        explanation: str,
    ) -> ThreatDetection:
        """Create a detection result that blocks capture."""
        return cls(
            level=level,
            patterns_found=tuple(patterns),
            explanation=explanation,
            should_block=True,
        )


@dataclass(frozen=True)
class ImplicitCapture:
    """An implicit capture awaiting review.

    This wraps an ImplicitMemory with review status and metadata.
    Captures are stored in a queue until the user reviews them.

    Attributes:
        id: Unique identifier for this capture.
        memory: The extracted memory content.
        status: Current review status.
        threat_detection: Adversarial screening result.
        created_at: When the capture was created.
        expires_at: When the capture expires if not reviewed.
        session_id: Claude session that created this capture.
        reviewed_at: When the capture was reviewed (if applicable).
    """

    id: str
    memory: ImplicitMemory
    status: ReviewStatus
    threat_detection: ThreatDetection
    created_at: datetime
    expires_at: datetime
    session_id: str | None = None
    reviewed_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        """Check if this capture has expired."""
        return datetime.now(UTC) > self.expires_at

    @property
    def is_reviewable(self) -> bool:
        """Check if this capture can still be reviewed."""
        return (
            self.status == ReviewStatus.PENDING
            and not self.is_expired
            and not self.threat_detection.should_block
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "id": self.id,
            "memory": self.memory.to_dict(),
            "status": self.status.value,
            "threat_detection": {
                "level": self.threat_detection.level.value,
                "patterns_found": list(self.threat_detection.patterns_found),
                "explanation": self.threat_detection.explanation,
                "should_block": self.threat_detection.should_block,
            },
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "session_id": self.session_id,
            "reviewed_at": (self.reviewed_at.isoformat() if self.reviewed_at else None),
        }


# =============================================================================
# Error Models
# =============================================================================


class LLMError(Exception):
    """Base exception for LLM operations.

    Attributes:
        error_type: Category of error for retry logic.
        message: Human-readable error message.
        provider: Which provider raised the error.
        retryable: Whether this error can be retried.
        retry_after_ms: Suggested wait time before retry (if applicable).
    """

    def __init__(
        self,
        message: str,
        *,
        error_type: LLMErrorType = LLMErrorType.UNKNOWN,
        provider: str | None = None,
        retryable: bool = False,
        retry_after_ms: int | None = None,
    ) -> None:
        """Initialize the error.

        Args:
            message: Human-readable error message.
            error_type: Category of error.
            provider: Which provider raised this error.
            retryable: Whether this error can be retried.
            retry_after_ms: Suggested wait time before retry.
        """
        super().__init__(message)
        self.error_type = error_type
        self.provider = provider
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms

    def __str__(self) -> str:
        """Format error message with context."""
        parts = [super().__str__()]
        if self.provider:
            parts.append(f"[provider={self.provider}]")
        if self.retry_after_ms:
            parts.append(f"[retry_after={self.retry_after_ms}ms]")
        return " ".join(parts)


class LLMRateLimitError(LLMError):
    """Rate limit exceeded.

    This error should trigger backoff and retry after the specified delay.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        provider: str | None = None,
        retry_after_ms: int = 60_000,  # Default 1 minute
    ) -> None:
        super().__init__(
            message,
            error_type=LLMErrorType.RATE_LIMIT,
            provider=provider,
            retryable=True,
            retry_after_ms=retry_after_ms,
        )


class LLMAuthenticationError(LLMError):
    """Authentication failed.

    This error should not be retried; the API key needs to be fixed.
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        *,
        provider: str | None = None,
    ) -> None:
        super().__init__(
            message,
            error_type=LLMErrorType.AUTHENTICATION,
            provider=provider,
            retryable=False,
        )


class LLMTimeoutError(LLMError):
    """Request timed out.

    This error may be retried with a longer timeout or smaller request.
    """

    def __init__(
        self,
        message: str = "Request timed out",
        *,
        provider: str | None = None,
        timeout_ms: int | None = None,
    ) -> None:
        super().__init__(
            message,
            error_type=LLMErrorType.TIMEOUT,
            provider=provider,
            retryable=True,
            retry_after_ms=1000,  # Wait 1 second before retry
        )
        self.timeout_ms = timeout_ms


class LLMConnectionError(LLMError):
    """Failed to connect to the provider.

    Common for Ollama when not running, or network issues.
    """

    def __init__(
        self,
        message: str = "Connection failed",
        *,
        provider: str | None = None,
    ) -> None:
        super().__init__(
            message,
            error_type=LLMErrorType.CONNECTION,
            provider=provider,
            retryable=True,
            retry_after_ms=5000,  # Wait 5 seconds before retry
        )


class LLMProviderError(LLMError):
    """Provider-specific error.

    Wraps errors from the underlying provider SDK.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        original_error: Exception | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            message,
            error_type=LLMErrorType.PROVIDER,
            provider=provider,
            retryable=retryable,
        )
        self.original_error = original_error
