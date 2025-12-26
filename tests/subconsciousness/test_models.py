"""Tests for subconsciousness models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from git_notes_memory.subconsciousness.models import (
    CaptureConfidence,
    ImplicitCapture,
    ImplicitMemory,
    LLMAuthenticationError,
    LLMConnectionError,
    LLMError,
    LLMErrorType,
    LLMMessage,
    LLMProviderError,
    LLMRateLimitError,
    LLMRequest,
    LLMResponse,
    LLMTimeoutError,
    LLMUsage,
    MessageRole,
    ReviewStatus,
    ThreatDetection,
    ThreatLevel,
)


class TestLLMMessage:
    """Tests for LLMMessage dataclass."""

    def test_user_message(self) -> None:
        """Test creating a user message."""
        msg = LLMMessage.user("Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"

    def test_assistant_message(self) -> None:
        """Test creating an assistant message."""
        msg = LLMMessage.assistant("Hi there")
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "Hi there"

    def test_system_message(self) -> None:
        """Test creating a system message."""
        msg = LLMMessage.system("You are helpful")
        assert msg.role == MessageRole.SYSTEM
        assert msg.content == "You are helpful"

    def test_is_frozen(self) -> None:
        """Test message is immutable."""
        msg = LLMMessage.user("Test")
        with pytest.raises(AttributeError):
            msg.content = "Modified"  # type: ignore[misc]


class TestLLMRequest:
    """Tests for LLMRequest dataclass."""

    def test_simple_request(self) -> None:
        """Test creating a simple request."""
        request = LLMRequest.simple("What is 2+2?")
        assert len(request.messages) == 1
        assert request.messages[0].role == MessageRole.USER
        assert request.messages[0].content == "What is 2+2?"

    def test_simple_request_with_system(self) -> None:
        """Test simple request with system prompt."""
        request = LLMRequest.simple(
            "What is 2+2?",
            system="Be concise",
        )
        assert len(request.messages) == 2
        assert request.messages[0].role == MessageRole.SYSTEM
        assert request.messages[1].role == MessageRole.USER

    def test_simple_request_json_mode(self) -> None:
        """Test simple request with JSON mode."""
        request = LLMRequest.simple("List 3 items", json_mode=True)
        assert request.json_mode is True

    def test_default_values(self) -> None:
        """Test default request values."""
        request = LLMRequest(messages=())
        assert request.max_tokens == 4096
        assert request.temperature == 0.0
        assert request.json_mode is False

    def test_is_frozen(self) -> None:
        """Test request is immutable."""
        request = LLMRequest.simple("Test")
        with pytest.raises(AttributeError):
            request.max_tokens = 1000  # type: ignore[misc]


class TestLLMUsage:
    """Tests for LLMUsage dataclass."""

    def test_from_tokens(self) -> None:
        """Test creating usage from token counts."""
        usage = LLMUsage.from_tokens(
            prompt_tokens=100,
            completion_tokens=50,
        )
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.estimated_cost_usd == 0.0

    def test_from_tokens_with_pricing(self) -> None:
        """Test cost calculation with pricing."""
        usage = LLMUsage.from_tokens(
            prompt_tokens=1_000_000,  # 1M tokens
            completion_tokens=500_000,  # 0.5M tokens
            input_cost_per_million=3.0,
            output_cost_per_million=15.0,
        )
        # Expected: 1M * $3/M + 0.5M * $15/M = $3 + $7.50 = $10.50
        assert usage.estimated_cost_usd == pytest.approx(10.5)

    def test_is_frozen(self) -> None:
        """Test usage is immutable."""
        usage = LLMUsage.from_tokens(100, 50)
        with pytest.raises(AttributeError):
            usage.total_tokens = 200  # type: ignore[misc]


class TestLLMResponse:
    """Tests for LLMResponse dataclass."""

    def test_basic_response(self) -> None:
        """Test creating a basic response."""
        usage = LLMUsage(100, 50, 150)
        response = LLMResponse(
            content="Hello!",
            model="test-model",
            usage=usage,
            latency_ms=500,
        )
        assert response.content == "Hello!"
        assert response.model == "test-model"
        assert response.latency_ms == 500

    def test_to_json(self) -> None:
        """Test JSON serialization."""
        usage = LLMUsage(100, 50, 150, 0.01)
        response = LLMResponse(
            content="Test",
            model="test-model",
            usage=usage,
            latency_ms=100,
            request_id="req-123",
        )

        data = response.to_json()

        assert data["content"] == "Test"
        assert data["model"] == "test-model"
        assert data["latency_ms"] == 100
        assert data["request_id"] == "req-123"
        assert data["usage"]["total_tokens"] == 150

    def test_timestamp_default(self) -> None:
        """Test default timestamp is set."""
        usage = LLMUsage(0, 0, 0)
        response = LLMResponse(
            content="",
            model="test",
            usage=usage,
            latency_ms=0,
        )
        assert response.timestamp is not None
        assert response.timestamp.tzinfo == UTC


class TestLLMErrors:
    """Tests for LLM error classes."""

    def test_base_error(self) -> None:
        """Test base LLMError."""
        error = LLMError("Test error")
        assert str(error) == "Test error"
        assert error.error_type == LLMErrorType.UNKNOWN
        assert error.retryable is False

    def test_rate_limit_error(self) -> None:
        """Test LLMRateLimitError."""
        error = LLMRateLimitError(
            "Rate limit exceeded",
            provider="anthropic",
            retry_after_ms=30_000,
        )
        assert error.error_type == LLMErrorType.RATE_LIMIT
        assert error.retryable is True
        assert error.retry_after_ms == 30_000
        assert "anthropic" in str(error)
        assert "30000ms" in str(error)

    def test_authentication_error(self) -> None:
        """Test LLMAuthenticationError."""
        error = LLMAuthenticationError(
            "Invalid API key",
            provider="openai",
        )
        assert error.error_type == LLMErrorType.AUTHENTICATION
        assert error.retryable is False

    def test_timeout_error(self) -> None:
        """Test LLMTimeoutError."""
        error = LLMTimeoutError(
            "Request timed out",
            provider="ollama",
            timeout_ms=30_000,
        )
        assert error.error_type == LLMErrorType.TIMEOUT
        assert error.retryable is True
        assert error.timeout_ms == 30_000

    def test_connection_error(self) -> None:
        """Test LLMConnectionError."""
        error = LLMConnectionError(
            "Failed to connect",
            provider="ollama",
        )
        assert error.error_type == LLMErrorType.CONNECTION
        assert error.retryable is True
        assert error.retry_after_ms == 5000

    def test_provider_error(self) -> None:
        """Test LLMProviderError with original exception."""
        original = ValueError("Original error")
        error = LLMProviderError(
            "Provider error",
            provider="anthropic",
            original_error=original,
            retryable=True,
        )
        assert error.error_type == LLMErrorType.PROVIDER
        assert error.original_error is original
        assert error.retryable is True


class TestReviewStatus:
    """Tests for ReviewStatus enum."""

    def test_enum_values(self) -> None:
        """Test all status values exist."""
        assert ReviewStatus.PENDING.value == "pending"
        assert ReviewStatus.APPROVED.value == "approved"
        assert ReviewStatus.REJECTED.value == "rejected"
        assert ReviewStatus.EXPIRED.value == "expired"


class TestThreatLevel:
    """Tests for ThreatLevel enum."""

    def test_enum_values(self) -> None:
        """Test all threat levels exist."""
        assert ThreatLevel.NONE.value == "none"
        assert ThreatLevel.LOW.value == "low"
        assert ThreatLevel.MEDIUM.value == "medium"
        assert ThreatLevel.HIGH.value == "high"
        assert ThreatLevel.CRITICAL.value == "critical"


class TestCaptureConfidence:
    """Tests for CaptureConfidence dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic confidence score."""
        conf = CaptureConfidence(overall=0.85)
        assert conf.overall == 0.85
        assert conf.relevance == 0.0

    def test_with_all_factors(self) -> None:
        """Test confidence with all factors specified."""
        conf = CaptureConfidence(
            overall=0.8,
            relevance=0.9,
            actionability=0.7,
            novelty=0.6,
            specificity=0.8,
            coherence=0.95,
        )
        assert conf.overall == 0.8
        assert conf.relevance == 0.9
        assert conf.coherence == 0.95

    def test_from_factors(self) -> None:
        """Test creating confidence from factors with weighted average."""
        conf = CaptureConfidence.from_factors(
            relevance=1.0,
            actionability=1.0,
            novelty=1.0,
            specificity=1.0,
            coherence=1.0,
        )
        # All factors at 1.0 should give overall 1.0
        assert conf.overall == pytest.approx(1.0)

    def test_from_factors_weighted(self) -> None:
        """Test factor weighting works correctly."""
        # Default weights: relevance=0.25, actionability=0.30, novelty=0.20,
        # specificity=0.15, coherence=0.10
        conf = CaptureConfidence.from_factors(
            relevance=0.0,
            actionability=1.0,  # Weight 0.30
            novelty=0.0,
            specificity=0.0,
            coherence=0.0,
        )
        # Only actionability at 1.0 with weight 0.30
        assert conf.overall == pytest.approx(0.30)

    def test_validation_range_low(self) -> None:
        """Test validation rejects values below 0."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            CaptureConfidence(overall=-0.1)

    def test_validation_range_high(self) -> None:
        """Test validation rejects values above 1.0."""
        with pytest.raises(ValueError, match="must be between 0.0 and 1.0"):
            CaptureConfidence(overall=1.5)

    def test_is_frozen(self) -> None:
        """Test confidence is immutable."""
        conf = CaptureConfidence(overall=0.5)
        with pytest.raises(AttributeError):
            conf.overall = 0.9  # type: ignore[misc]


class TestThreatDetection:
    """Tests for ThreatDetection dataclass."""

    def test_safe_factory(self) -> None:
        """Test creating a safe detection."""
        detection = ThreatDetection.safe()
        assert detection.level == ThreatLevel.NONE
        assert detection.should_block is False
        assert len(detection.patterns_found) == 0

    def test_blocked_factory(self) -> None:
        """Test creating a blocked detection."""
        detection = ThreatDetection.blocked(
            level=ThreatLevel.HIGH,
            patterns=["prompt_injection", "data_exfil"],
            explanation="Suspicious patterns detected",
        )
        assert detection.level == ThreatLevel.HIGH
        assert detection.should_block is True
        assert "prompt_injection" in detection.patterns_found
        assert "data_exfil" in detection.patterns_found

    def test_is_frozen(self) -> None:
        """Test detection is immutable."""
        detection = ThreatDetection.safe()
        with pytest.raises(AttributeError):
            detection.level = ThreatLevel.HIGH  # type: ignore[misc]


class TestImplicitMemory:
    """Tests for ImplicitMemory dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic implicit memory."""
        conf = CaptureConfidence(overall=0.8)
        memory = ImplicitMemory(
            namespace="decisions",
            summary="Use PostgreSQL for persistence",
            content="## Context\nWe decided to use PostgreSQL.",
            confidence=conf,
            source_hash="abc123",
        )
        assert memory.namespace == "decisions"
        assert memory.summary == "Use PostgreSQL for persistence"
        assert memory.source_hash == "abc123"

    def test_with_all_fields(self) -> None:
        """Test memory with all optional fields."""
        conf = CaptureConfidence(overall=0.9)
        memory = ImplicitMemory(
            namespace="learnings",
            summary="Learned about async patterns",
            content="Details about async/await...",
            confidence=conf,
            source_hash="def456",
            source_range=(10, 25),
            rationale="Contains actionable learning about concurrency",
            tags=("async", "python", "patterns"),
        )
        assert memory.source_range == (10, 25)
        assert memory.rationale == "Contains actionable learning about concurrency"
        assert "async" in memory.tags

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        conf = CaptureConfidence(overall=0.7, relevance=0.8)
        memory = ImplicitMemory(
            namespace="decisions",
            summary="Test decision",
            content="Content here",
            confidence=conf,
            source_hash="hash123",
            tags=("tag1", "tag2"),
        )

        data = memory.to_dict()

        assert data["namespace"] == "decisions"
        assert data["summary"] == "Test decision"
        assert data["confidence"]["overall"] == 0.7
        assert data["confidence"]["relevance"] == 0.8
        assert data["source_hash"] == "hash123"
        assert data["tags"] == ["tag1", "tag2"]

    def test_is_frozen(self) -> None:
        """Test memory is immutable."""
        conf = CaptureConfidence(overall=0.5)
        memory = ImplicitMemory(
            namespace="test",
            summary="Test",
            content="Test",
            confidence=conf,
            source_hash="hash",
        )
        with pytest.raises(AttributeError):
            memory.namespace = "other"  # type: ignore[misc]


class TestImplicitCapture:
    """Tests for ImplicitCapture dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating a basic capture."""
        conf = CaptureConfidence(overall=0.8)
        memory = ImplicitMemory(
            namespace="decisions",
            summary="Test decision",
            content="Content",
            confidence=conf,
            source_hash="hash",
        )
        now = datetime.now(UTC)
        capture = ImplicitCapture(
            id="cap-001",
            memory=memory,
            status=ReviewStatus.PENDING,
            threat_detection=ThreatDetection.safe(),
            created_at=now,
            expires_at=datetime(2099, 12, 31, tzinfo=UTC),
        )

        assert capture.id == "cap-001"
        assert capture.status == ReviewStatus.PENDING
        assert capture.is_reviewable is True
        assert capture.is_expired is False

    def test_is_expired(self) -> None:
        """Test expiration check."""
        conf = CaptureConfidence(overall=0.5)
        memory = ImplicitMemory(
            namespace="test",
            summary="Test",
            content="Test",
            confidence=conf,
            source_hash="hash",
        )
        # Create an already-expired capture
        capture = ImplicitCapture(
            id="cap-expired",
            memory=memory,
            status=ReviewStatus.PENDING,
            threat_detection=ThreatDetection.safe(),
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            expires_at=datetime(2020, 1, 2, tzinfo=UTC),  # In the past
        )

        assert capture.is_expired is True
        assert capture.is_reviewable is False

    def test_is_reviewable_with_threat(self) -> None:
        """Test reviewability with threat block."""
        conf = CaptureConfidence(overall=0.5)
        memory = ImplicitMemory(
            namespace="test",
            summary="Test",
            content="Test",
            confidence=conf,
            source_hash="hash",
        )
        capture = ImplicitCapture(
            id="cap-threat",
            memory=memory,
            status=ReviewStatus.PENDING,
            threat_detection=ThreatDetection.blocked(
                ThreatLevel.HIGH,
                ["injection"],
                "Blocked",
            ),
            created_at=datetime.now(UTC),
            expires_at=datetime(2099, 12, 31, tzinfo=UTC),
        )

        # Not reviewable because threat blocks it
        assert capture.is_reviewable is False

    def test_is_reviewable_non_pending(self) -> None:
        """Test reviewability with non-pending status."""
        conf = CaptureConfidence(overall=0.5)
        memory = ImplicitMemory(
            namespace="test",
            summary="Test",
            content="Test",
            confidence=conf,
            source_hash="hash",
        )
        capture = ImplicitCapture(
            id="cap-approved",
            memory=memory,
            status=ReviewStatus.APPROVED,  # Already reviewed
            threat_detection=ThreatDetection.safe(),
            created_at=datetime.now(UTC),
            expires_at=datetime(2099, 12, 31, tzinfo=UTC),
        )

        assert capture.is_reviewable is False

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        conf = CaptureConfidence(overall=0.7)
        memory = ImplicitMemory(
            namespace="decisions",
            summary="Test",
            content="Content",
            confidence=conf,
            source_hash="hash",
        )
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        exp = datetime(2024, 1, 22, 12, 0, 0, tzinfo=UTC)
        capture = ImplicitCapture(
            id="cap-test",
            memory=memory,
            status=ReviewStatus.PENDING,
            threat_detection=ThreatDetection.safe(),
            created_at=now,
            expires_at=exp,
            session_id="session-123",
        )

        data = capture.to_dict()

        assert data["id"] == "cap-test"
        assert data["status"] == "pending"
        assert data["threat_detection"]["level"] == "none"
        assert data["session_id"] == "session-123"
        assert "2024-01-15" in data["created_at"]
        assert data["reviewed_at"] is None

    def test_is_frozen(self) -> None:
        """Test capture is immutable."""
        conf = CaptureConfidence(overall=0.5)
        memory = ImplicitMemory(
            namespace="test",
            summary="Test",
            content="Test",
            confidence=conf,
            source_hash="hash",
        )
        capture = ImplicitCapture(
            id="cap-frozen",
            memory=memory,
            status=ReviewStatus.PENDING,
            threat_detection=ThreatDetection.safe(),
            created_at=datetime.now(UTC),
            expires_at=datetime(2099, 12, 31, tzinfo=UTC),
        )
        with pytest.raises(AttributeError):
            capture.status = ReviewStatus.APPROVED  # type: ignore[misc]
