"""Tests for ImplicitCaptureAgent."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from git_notes_memory.subconsciousness.implicit_capture_agent import (
    ExtractionResult,
    ImplicitCaptureAgent,
)
from git_notes_memory.subconsciousness.models import LLMResponse, LLMUsage
from git_notes_memory.subconsciousness.transcript_chunker import TranscriptChunk, Turn


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_empty_result(self) -> None:
        """Test empty extraction result."""
        result = ExtractionResult(
            memories=(),
            chunks_processed=0,
        )
        assert result.success
        assert result.memory_count == 0

    def test_result_with_memories(self) -> None:
        """Test result with memories (using placeholder)."""
        # This test verifies basic structure
        result = ExtractionResult(
            memories=(),  # Empty for now, real test needs ImplicitMemory
            chunks_processed=2,
            errors=(),
        )
        assert result.success
        assert result.chunks_processed == 2

    def test_result_with_errors(self) -> None:
        """Test result with errors."""
        result = ExtractionResult(
            memories=(),
            chunks_processed=1,
            errors=("Error 1", "Error 2"),
        )
        assert not result.success
        assert len(result.errors) == 2

    def test_is_frozen(self) -> None:
        """Test ExtractionResult is immutable."""
        result = ExtractionResult(memories=(), chunks_processed=0)
        with pytest.raises(AttributeError):
            result.chunks_processed = 5  # type: ignore[misc]


class TestImplicitCaptureAgent:
    """Tests for ImplicitCaptureAgent."""

    @pytest.fixture
    def mock_llm_client(self) -> MagicMock:
        """Create a mock LLM client."""
        client = MagicMock()
        client.complete = AsyncMock()
        return client

    @pytest.fixture
    def agent(self, mock_llm_client: MagicMock) -> ImplicitCaptureAgent:
        """Create an agent with mocked LLM."""
        return ImplicitCaptureAgent(
            llm_client=mock_llm_client,
            min_confidence=0.5,
        )

    def make_llm_response(self, memories: list[dict[str, Any]]) -> LLMResponse:
        """Create a mock LLM response with memories."""
        return LLMResponse(
            content=json.dumps({"memories": memories}),
            model="test-model",
            usage=LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            latency_ms=100,
        )

    @pytest.mark.asyncio
    async def test_analyze_empty_transcript(
        self,
        agent: ImplicitCaptureAgent,
    ) -> None:
        """Test analyzing empty transcript."""
        result = await agent.analyze_transcript("")
        assert result.chunks_processed == 0
        assert result.memory_count == 0
        assert result.success

    @pytest.mark.asyncio
    async def test_analyze_simple_transcript(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test analyzing simple transcript with one memory."""
        # Setup mock response
        mock_llm_client.complete.return_value = self.make_llm_response(
            [
                {
                    "namespace": "decisions",
                    "summary": "Use PostgreSQL for persistence",
                    "content": "We decided to use PostgreSQL for the database.",
                    "confidence": {
                        "relevance": 0.9,
                        "actionability": 0.8,
                        "novelty": 0.7,
                        "specificity": 0.9,
                        "coherence": 0.8,
                    },
                    "rationale": "Database choice is important",
                    "tags": ["database", "architecture"],
                }
            ]
        )

        transcript = """user: What database should we use?
assistant: Let's use PostgreSQL for persistence."""

        result = await agent.analyze_transcript(transcript)

        assert result.success
        assert result.chunks_processed == 1
        assert result.memory_count == 1

        memory = result.memories[0]
        assert memory.namespace == "decisions"
        assert memory.summary == "Use PostgreSQL for persistence"
        assert memory.confidence.overall >= 0.5
        assert "database" in memory.tags

    @pytest.mark.asyncio
    async def test_filters_low_confidence(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that low-confidence memories are filtered."""
        mock_llm_client.complete.return_value = self.make_llm_response(
            [
                {
                    "namespace": "decisions",
                    "summary": "Low confidence decision",
                    "content": "Some vague decision",
                    "confidence": {
                        "relevance": 0.2,
                        "actionability": 0.1,
                        "novelty": 0.1,
                        "specificity": 0.1,
                        "coherence": 0.1,
                    },
                    "rationale": "Not sure about this",
                }
            ]
        )

        result = await agent.analyze_transcript("user: Hello\nassistant: Hi")

        assert result.success
        assert result.memory_count == 0  # Filtered out

    @pytest.mark.asyncio
    async def test_deduplicates_memories(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that duplicate memories are filtered."""
        # Same content appears twice
        mock_llm_client.complete.return_value = self.make_llm_response(
            [
                {
                    "namespace": "decisions",
                    "summary": "First occurrence",
                    "content": "Identical content",
                    "confidence": {
                        "relevance": 0.9,
                        "actionability": 0.9,
                        "novelty": 0.9,
                        "specificity": 0.9,
                        "coherence": 0.9,
                    },
                },
                {
                    "namespace": "decisions",
                    "summary": "Second occurrence",
                    "content": "Identical content",  # Same content
                    "confidence": {
                        "relevance": 0.9,
                        "actionability": 0.9,
                        "novelty": 0.9,
                        "specificity": 0.9,
                        "coherence": 0.9,
                    },
                },
            ]
        )

        result = await agent.analyze_transcript("user: Hello\nassistant: Hi")

        assert result.memory_count == 1  # Only first kept

    @pytest.mark.asyncio
    async def test_sorts_by_confidence(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that memories are sorted by confidence."""
        mock_llm_client.complete.return_value = self.make_llm_response(
            [
                {
                    "namespace": "decisions",
                    "summary": "Medium confidence",
                    "content": "Content A",
                    "confidence": {
                        "relevance": 0.6,
                        "actionability": 0.6,
                        "novelty": 0.6,
                        "specificity": 0.6,
                        "coherence": 0.6,
                    },
                },
                {
                    "namespace": "learnings",
                    "summary": "High confidence",
                    "content": "Content B",
                    "confidence": {
                        "relevance": 0.9,
                        "actionability": 0.9,
                        "novelty": 0.9,
                        "specificity": 0.9,
                        "coherence": 0.9,
                    },
                },
            ]
        )

        result = await agent.analyze_transcript("user: Hello\nassistant: Hi")

        assert result.memory_count == 2
        # Highest confidence first
        assert result.memories[0].summary == "High confidence"
        assert result.memories[1].summary == "Medium confidence"

    @pytest.mark.asyncio
    async def test_handles_invalid_json(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test handling of invalid JSON response."""
        mock_llm_client.complete.return_value = LLMResponse(
            content="Not valid JSON",
            model="test",
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_ms=50,
        )

        result = await agent.analyze_transcript("user: Hello\nassistant: Hi")

        assert result.success  # No error raised
        assert result.memory_count == 0

    @pytest.mark.asyncio
    async def test_handles_missing_memories_array(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test handling of response without memories array."""
        mock_llm_client.complete.return_value = LLMResponse(
            content=json.dumps({"other": "data"}),
            model="test",
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_ms=50,
        )

        result = await agent.analyze_transcript("user: Hello\nassistant: Hi")

        assert result.success
        assert result.memory_count == 0

    @pytest.mark.asyncio
    async def test_handles_llm_error(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test handling of LLM errors."""
        mock_llm_client.complete.side_effect = Exception("LLM error")

        result = await agent.analyze_transcript("user: Hello\nassistant: Hi")

        assert not result.success
        assert len(result.errors) == 1
        assert "LLM error" in result.errors[0]

    @pytest.mark.asyncio
    async def test_truncates_long_summary(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that long summaries are truncated to 100 chars."""
        long_summary = "x" * 200
        mock_llm_client.complete.return_value = self.make_llm_response(
            [
                {
                    "namespace": "decisions",
                    "summary": long_summary,
                    "content": "Content",
                    "confidence": {
                        "relevance": 0.9,
                        "actionability": 0.9,
                        "novelty": 0.9,
                        "specificity": 0.9,
                        "coherence": 0.9,
                    },
                }
            ]
        )

        result = await agent.analyze_transcript("user: Hello\nassistant: Hi")

        assert result.memory_count == 1
        assert len(result.memories[0].summary) == 100

    @pytest.mark.asyncio
    async def test_limits_tags_to_5(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that tags are limited to 5."""
        mock_llm_client.complete.return_value = self.make_llm_response(
            [
                {
                    "namespace": "decisions",
                    "summary": "Test",
                    "content": "Content",
                    "confidence": {
                        "relevance": 0.9,
                        "actionability": 0.9,
                        "novelty": 0.9,
                        "specificity": 0.9,
                        "coherence": 0.9,
                    },
                    "tags": ["a", "b", "c", "d", "e", "f", "g"],
                }
            ]
        )

        result = await agent.analyze_transcript("user: Hello\nassistant: Hi")

        assert result.memory_count == 1
        assert len(result.memories[0].tags) == 5

    @pytest.mark.asyncio
    async def test_skips_invalid_memory_items(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that invalid memory items are skipped."""
        mock_llm_client.complete.return_value = self.make_llm_response(
            [
                {
                    "namespace": "decisions",
                    # Missing summary and content
                },
                {
                    "namespace": "decisions",
                    "summary": "Valid",
                    "content": "Valid content",
                    "confidence": {
                        "relevance": 0.9,
                        "actionability": 0.9,
                        "novelty": 0.9,
                        "specificity": 0.9,
                        "coherence": 0.9,
                    },
                },
            ]
        )

        result = await agent.analyze_transcript("user: Hello\nassistant: Hi")

        assert result.memory_count == 1
        assert result.memories[0].summary == "Valid"

    @pytest.mark.asyncio
    async def test_with_existing_summaries(
        self,
        agent: ImplicitCaptureAgent,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that existing summaries are passed to prompt."""
        mock_llm_client.complete.return_value = self.make_llm_response([])

        await agent.analyze_transcript(
            "user: Hello\nassistant: Hi",
            existing_summaries=["Prior decision 1", "Prior decision 2"],
        )

        # Verify prompt contains existing summaries
        call_args = mock_llm_client.complete.call_args
        prompt = call_args[0][0]
        assert "Existing Memories" in prompt
        assert "Prior decision 1" in prompt


class TestParseResponse:
    """Tests for response parsing."""

    @pytest.fixture
    def agent(self) -> ImplicitCaptureAgent:
        """Create an agent with mock client."""
        return ImplicitCaptureAgent(
            llm_client=MagicMock(),
            min_confidence=0.5,
        )

    @pytest.fixture
    def sample_chunk(self) -> TranscriptChunk:
        """Create a sample chunk."""
        return TranscriptChunk(
            turns=(Turn("user", "Hello", 0, 0),),
            chunk_index=0,
            total_chunks=1,
            overlap_turns=0,
            source_hash="abc123",
            line_range=(0, 0),
        )

    def test_parse_empty_response(
        self,
        agent: ImplicitCaptureAgent,
        sample_chunk: TranscriptChunk,
    ) -> None:
        """Test parsing empty response."""
        memories = agent._parse_response("{}", sample_chunk)
        assert memories == []

    def test_parse_invalid_json(
        self,
        agent: ImplicitCaptureAgent,
        sample_chunk: TranscriptChunk,
    ) -> None:
        """Test parsing invalid JSON."""
        memories = agent._parse_response("not json", sample_chunk)
        assert memories == []

    def test_parse_valid_memory(
        self,
        agent: ImplicitCaptureAgent,
        sample_chunk: TranscriptChunk,
    ) -> None:
        """Test parsing valid memory."""
        content = json.dumps(
            {
                "memories": [
                    {
                        "namespace": "decisions",
                        "summary": "Test decision",
                        "content": "Decision content",
                        "confidence": {
                            "relevance": 0.9,
                            "actionability": 0.8,
                            "novelty": 0.7,
                            "specificity": 0.9,
                            "coherence": 0.8,
                        },
                        "rationale": "Important decision",
                        "tags": ["test"],
                        "source_lines": [0, 5],
                    }
                ]
            }
        )

        memories = agent._parse_response(content, sample_chunk)

        assert len(memories) == 1
        memory = memories[0]
        assert memory.namespace == "decisions"
        assert memory.summary == "Test decision"
        assert memory.rationale == "Important decision"
        assert "test" in memory.tags
        assert memory.source_range == (0, 5)  # Adjusted by chunk offset

    def test_parse_source_lines_adjustment(
        self,
        agent: ImplicitCaptureAgent,
    ) -> None:
        """Test that source lines are adjusted by chunk offset."""
        chunk = TranscriptChunk(
            turns=(Turn("user", "Hello", 100, 110),),
            chunk_index=1,
            total_chunks=2,
            overlap_turns=0,
            source_hash="def456",
            line_range=(100, 110),
        )

        content = json.dumps(
            {
                "memories": [
                    {
                        "namespace": "decisions",
                        "summary": "Test",
                        "content": "Content",
                        "confidence": {
                            "relevance": 0.9,
                            "actionability": 0.9,
                            "novelty": 0.9,
                            "specificity": 0.9,
                            "coherence": 0.9,
                        },
                        "source_lines": [5, 10],
                    }
                ]
            }
        )

        memories = agent._parse_response(content, chunk)

        assert len(memories) == 1
        # Source lines adjusted: 100 + 5 = 105, 100 + 10 = 110
        assert memories[0].source_range == (105, 110)
