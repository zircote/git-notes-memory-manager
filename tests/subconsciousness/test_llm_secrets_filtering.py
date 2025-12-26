"""Tests for secrets filtering in LLM client (CRIT-002)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from git_notes_memory.security.models import (
    FilterAction,
    FilterResult,
    SecretDetection,
    SecretType,
)
from git_notes_memory.subconsciousness.llm_client import LLMClient
from git_notes_memory.subconsciousness.models import (
    LLMMessage,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    MessageRole,
)

if TYPE_CHECKING:
    pass


class TestSecretsFiltering:
    """Test secrets filtering in LLMClient (CRIT-002)."""

    @pytest.fixture
    def mock_provider(self) -> MagicMock:
        """Create a mock LLM provider."""
        provider = MagicMock()
        provider.name = "test-provider"
        provider.complete = AsyncMock(
            return_value=LLMResponse(
                content="Test response",
                usage=LLMUsage(
                    prompt_tokens=10,
                    completion_tokens=5,
                    total_tokens=15,
                ),
                model="test-model",
                latency_ms=100,
            )
        )
        return provider

    @pytest.fixture
    def mock_secrets_service(self) -> MagicMock:
        """Create a mock secrets filtering service."""
        service = MagicMock()
        service.enabled = True
        return service

    def test_secrets_filtering_enabled_by_default(
        self,
        mock_provider: MagicMock,
    ) -> None:
        """Test that secrets filtering is enabled by default."""
        client = LLMClient(primary_provider=mock_provider)
        assert client.filter_secrets is True

    def test_secrets_service_initialized_when_enabled(
        self,
        mock_provider: MagicMock,
    ) -> None:
        """Test that secrets service is initialized when filtering is enabled."""
        with patch(
            "git_notes_memory.subconsciousness.llm_client.get_secrets_service"
        ) as mock_get:
            mock_service = MagicMock()
            mock_get.return_value = mock_service

            client = LLMClient(primary_provider=mock_provider)

            mock_get.assert_called_once()
            assert client._secrets_service is mock_service

    def test_secrets_service_not_initialized_when_disabled(
        self,
        mock_provider: MagicMock,
    ) -> None:
        """Test that secrets service is not initialized when filtering disabled."""
        with patch(
            "git_notes_memory.subconsciousness.llm_client.get_secrets_service"
        ) as mock_get:
            client = LLMClient(primary_provider=mock_provider, filter_secrets=False)

            mock_get.assert_not_called()
            assert client._secrets_service is None

    @pytest.mark.asyncio
    async def test_secrets_filtered_before_llm_call(
        self,
        mock_provider: MagicMock,
        mock_secrets_service: MagicMock,
    ) -> None:
        """Test that secrets are filtered before sending to LLM."""
        # Configure mock to filter content
        mock_secrets_service.filter.return_value = FilterResult(
            content="Filtered content without SSN",
            action=FilterAction.REDACTED,
            original_length=50,
            filtered_length=40,
        )

        with patch(
            "git_notes_memory.subconsciousness.llm_client.get_secrets_service",
            return_value=mock_secrets_service,
        ):
            client = LLMClient(primary_provider=mock_provider)

            request = LLMRequest.simple(
                "My SSN is 123-45-6789",
                system="You are a helpful assistant",
            )

            await client.complete_request(request)

            # Verify filter was called for each message
            assert mock_secrets_service.filter.call_count == 2

    @pytest.mark.asyncio
    async def test_filtered_content_used_in_request(
        self,
        mock_provider: MagicMock,
        mock_secrets_service: MagicMock,
    ) -> None:
        """Test that filtered (not original) content is used in request."""
        original_content = "My SSN is 123-45-6789"
        filtered_content = "My SSN is [REDACTED:SSN]"

        # Include a detection so had_secrets is True
        mock_detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=10,
            end=21,
            confidence=1.0,
            secret_hash="abc123",
        )

        mock_secrets_service.filter.return_value = FilterResult(
            content=filtered_content,
            action=FilterAction.REDACTED,
            original_length=len(original_content),
            filtered_length=len(filtered_content),
            detections=(mock_detection,),
        )

        with patch(
            "git_notes_memory.subconsciousness.llm_client.get_secrets_service",
            return_value=mock_secrets_service,
        ):
            client = LLMClient(primary_provider=mock_provider)

            request = LLMRequest(
                messages=(LLMMessage.user(original_content),),
            )

            # Directly test the filtering method
            filtered_request = client._filter_request_secrets(request)

            # Check that filtered content is in the new request
            assert filtered_request.messages[0].content == filtered_content
            assert filtered_request is not request  # New request created

    @pytest.mark.asyncio
    async def test_no_filtering_when_disabled(
        self,
        mock_provider: MagicMock,
    ) -> None:
        """Test that filtering is skipped when disabled."""
        with patch(
            "git_notes_memory.subconsciousness.llm_client.get_secrets_service"
        ) as mock_get:
            client = LLMClient(primary_provider=mock_provider, filter_secrets=False)

            request = LLMRequest.simple("My SSN is 123-45-6789")
            await client.complete_request(request)

            # Service should not be called
            mock_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_filtering_when_service_disabled(
        self,
        mock_provider: MagicMock,
        mock_secrets_service: MagicMock,
    ) -> None:
        """Test that filtering is skipped when service is disabled."""
        mock_secrets_service.enabled = False

        with patch(
            "git_notes_memory.subconsciousness.llm_client.get_secrets_service",
            return_value=mock_secrets_service,
        ):
            client = LLMClient(primary_provider=mock_provider)

            request = LLMRequest.simple("My SSN is 123-45-6789")
            await client.complete_request(request)

            # Filter should not be called
            mock_secrets_service.filter.assert_not_called()

    def test_filter_request_secrets_returns_original_when_no_secrets(
        self,
        mock_provider: MagicMock,
        mock_secrets_service: MagicMock,
    ) -> None:
        """Test that original request is returned when no secrets found."""
        mock_secrets_service.filter.return_value = FilterResult(
            content="Clean content",
            action=FilterAction.ALLOWED,
            original_length=13,
            filtered_length=13,
        )

        with patch(
            "git_notes_memory.subconsciousness.llm_client.get_secrets_service",
            return_value=mock_secrets_service,
        ):
            client = LLMClient(primary_provider=mock_provider)

            request = LLMRequest(
                messages=(LLMMessage.user("Clean content"),),
            )

            filtered = client._filter_request_secrets(request)

            # Should return the same request object
            assert filtered is request

    def test_filter_request_secrets_creates_new_request_when_filtered(
        self,
        mock_provider: MagicMock,
        mock_secrets_service: MagicMock,
    ) -> None:
        """Test that new request is created when secrets are filtered."""
        # Include a detection so had_secrets is True
        mock_detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=10,
            confidence=1.0,
            secret_hash="abc123",
        )

        mock_secrets_service.filter.return_value = FilterResult(
            content="Filtered content",
            action=FilterAction.REDACTED,
            original_length=25,
            filtered_length=16,
            detections=(mock_detection,),
        )

        with patch(
            "git_notes_memory.subconsciousness.llm_client.get_secrets_service",
            return_value=mock_secrets_service,
        ):
            client = LLMClient(primary_provider=mock_provider)

            original_request = LLMRequest(
                messages=(LLMMessage.user("Content with secrets"),),
                max_tokens=1000,
                temperature=0.5,
            )

            filtered = client._filter_request_secrets(original_request)

            # Should return a new request
            assert filtered is not original_request
            # Preserve other fields
            assert filtered.max_tokens == 1000
            assert filtered.temperature == 0.5
            # Content should be filtered
            assert filtered.messages[0].content == "Filtered content"

    def test_filter_preserves_message_roles(
        self,
        mock_provider: MagicMock,
        mock_secrets_service: MagicMock,
    ) -> None:
        """Test that message roles are preserved during filtering."""
        # Include a detection so had_secrets is True
        mock_detection = SecretDetection(
            secret_type=SecretType.PII_SSN,
            start=0,
            end=8,
            confidence=1.0,
            secret_hash="abc123",
        )

        mock_secrets_service.filter.return_value = FilterResult(
            content="Filtered",
            action=FilterAction.REDACTED,
            original_length=8,
            filtered_length=8,
            detections=(mock_detection,),
        )

        with patch(
            "git_notes_memory.subconsciousness.llm_client.get_secrets_service",
            return_value=mock_secrets_service,
        ):
            client = LLMClient(primary_provider=mock_provider)

            request = LLMRequest(
                messages=(
                    LLMMessage.system("System message"),
                    LLMMessage.user("User message"),
                    LLMMessage.assistant("Assistant message"),
                ),
            )

            filtered = client._filter_request_secrets(request)

            assert filtered.messages[0].role == MessageRole.SYSTEM
            assert filtered.messages[1].role == MessageRole.USER
            assert filtered.messages[2].role == MessageRole.ASSISTANT
