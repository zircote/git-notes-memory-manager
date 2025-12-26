"""Tests for transcript chunking."""

from __future__ import annotations

import pytest

from git_notes_memory.subconsciousness.transcript_chunker import (
    TranscriptChunk,
    TranscriptChunker,
    Turn,
    chunk_transcript,
    parse_transcript,
)


class TestTurn:
    """Tests for Turn dataclass."""

    def test_basic_turn(self) -> None:
        """Test creating a basic turn."""
        turn = Turn(
            role="user",
            content="Hello, how are you?",
            line_start=0,
            line_end=0,
        )
        assert turn.role == "user"
        assert turn.content == "Hello, how are you?"

    def test_token_estimate(self) -> None:
        """Test token estimation (approx 4 chars per token)."""
        turn = Turn(
            role="user",
            content="x" * 400,  # 400 chars
            line_start=0,
            line_end=0,
        )
        # 400 / 4 + 1 = 101
        assert turn.token_estimate == 101

    def test_is_frozen(self) -> None:
        """Test turn is immutable."""
        turn = Turn(role="user", content="test", line_start=0, line_end=0)
        with pytest.raises(AttributeError):
            turn.content = "modified"  # type: ignore[misc]


class TestTranscriptChunk:
    """Tests for TranscriptChunk dataclass."""

    def test_basic_chunk(self) -> None:
        """Test creating a basic chunk."""
        turns = (
            Turn("user", "Hello", 0, 0),
            Turn("assistant", "Hi there", 1, 1),
        )
        chunk = TranscriptChunk(
            turns=turns,
            chunk_index=0,
            total_chunks=1,
            overlap_turns=0,
            source_hash="abc123",
            line_range=(0, 1),
        )
        assert chunk.chunk_index == 0
        assert chunk.is_first
        assert chunk.is_last
        assert len(chunk.turns) == 2

    def test_token_estimate(self) -> None:
        """Test chunk token estimation."""
        turns = (
            Turn("user", "x" * 100, 0, 0),  # ~26 tokens
            Turn("assistant", "y" * 200, 1, 1),  # ~51 tokens
        )
        chunk = TranscriptChunk(
            turns=turns,
            chunk_index=0,
            total_chunks=1,
            overlap_turns=0,
            source_hash="abc",
            line_range=(0, 1),
        )
        assert chunk.token_estimate == 26 + 51

    def test_to_text(self) -> None:
        """Test converting chunk to text."""
        turns = (
            Turn("user", "Hello", 0, 0),
            Turn("assistant", "Hi there", 1, 1),
        )
        chunk = TranscriptChunk(
            turns=turns,
            chunk_index=0,
            total_chunks=1,
            overlap_turns=0,
            source_hash="abc",
            line_range=(0, 1),
        )
        text = chunk.to_text()
        assert "user: Hello" in text
        assert "assistant: Hi there" in text

    def test_is_first_is_last(self) -> None:
        """Test first/last chunk detection."""
        turns = (Turn("user", "test", 0, 0),)

        first = TranscriptChunk(
            turns=turns,
            chunk_index=0,
            total_chunks=3,
            overlap_turns=0,
            source_hash="a",
            line_range=(0, 0),
        )
        assert first.is_first
        assert not first.is_last

        middle = TranscriptChunk(
            turns=turns,
            chunk_index=1,
            total_chunks=3,
            overlap_turns=0,
            source_hash="b",
            line_range=(0, 0),
        )
        assert not middle.is_first
        assert not middle.is_last

        last = TranscriptChunk(
            turns=turns,
            chunk_index=2,
            total_chunks=3,
            overlap_turns=0,
            source_hash="c",
            line_range=(0, 0),
        )
        assert not last.is_first
        assert last.is_last


class TestParseTranscript:
    """Tests for parse_transcript function."""

    def test_empty_transcript(self) -> None:
        """Test parsing empty transcript."""
        turns = parse_transcript("")
        assert turns == []

        turns = parse_transcript("   \n   ")
        assert turns == []

    def test_user_assistant_format(self) -> None:
        """Test parsing user:/assistant: format."""
        text = """user: Hello
assistant: Hi there
user: How are you?
assistant: I'm doing well"""

        turns = parse_transcript(text)

        assert len(turns) == 4
        assert turns[0].role == "user"
        assert turns[0].content == "Hello"
        assert turns[1].role == "assistant"
        assert turns[1].content == "Hi there"

    def test_human_claude_format(self) -> None:
        """Test parsing Human:/Assistant: format."""
        text = """Human: Hello
Assistant: Hi there"""

        turns = parse_transcript(text)

        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[1].role == "assistant"

    def test_multiline_content(self) -> None:
        """Test parsing multiline messages."""
        text = """user: This is a message
that spans multiple
lines

assistant: And this is
also multiline"""

        turns = parse_transcript(text)

        assert len(turns) == 2
        assert "spans multiple" in turns[0].content
        assert "lines" in turns[0].content
        assert "also multiline" in turns[1].content

    def test_system_message(self) -> None:
        """Test parsing system messages."""
        text = """system: You are helpful
user: Hello
assistant: Hi"""

        turns = parse_transcript(text)

        assert len(turns) == 3
        assert turns[0].role == "system"

    def test_line_numbers(self) -> None:
        """Test line number tracking."""
        text = """user: Line 0
assistant: Line 1
Line 2
user: Line 3"""

        turns = parse_transcript(text)

        assert turns[0].line_start == 0
        assert turns[0].line_end == 0
        # Second turn spans lines 1-2
        assert turns[1].line_start == 1
        assert turns[1].line_end == 2
        # Third turn
        assert turns[2].line_start == 3

    def test_case_insensitive_prefixes(self) -> None:
        """Test case-insensitive role prefixes."""
        text = """USER: Hello
ASSISTANT: Hi
User: Test
Assistant: Response"""

        turns = parse_transcript(text)

        assert len(turns) == 4
        assert all(t.role in ("user", "assistant") for t in turns)


class TestTranscriptChunker:
    """Tests for TranscriptChunker class."""

    def test_empty_turns(self) -> None:
        """Test chunking empty turn list."""
        chunker = TranscriptChunker()
        chunks = chunker.chunk([])
        assert chunks == []

    def test_single_chunk_fits(self) -> None:
        """Test that small transcripts return single chunk."""
        turns = [
            Turn("user", "Hello", 0, 0),
            Turn("assistant", "Hi", 1, 1),
        ]
        chunker = TranscriptChunker(max_tokens=1000)
        chunks = chunker.chunk(turns)

        assert len(chunks) == 1
        assert chunks[0].is_first
        assert chunks[0].is_last
        assert chunks[0].overlap_turns == 0

    def test_multiple_chunks(self) -> None:
        """Test splitting into multiple chunks."""
        # Create turns that exceed max_tokens
        turns = [Turn("user", "x" * 1000, i * 2, i * 2) for i in range(10)]
        # Each turn is ~250 tokens, max 500 means ~2 per chunk
        chunker = TranscriptChunker(
            max_tokens=500,
            overlap_turns=1,
            min_chunk_turns=2,
        )
        chunks = chunker.chunk(turns)

        assert len(chunks) > 1
        assert chunks[0].is_first
        assert not chunks[0].is_last
        assert chunks[-1].is_last

    def test_overlap_maintained(self) -> None:
        """Test that overlap turns are included."""
        turns = [Turn("user", "x" * 400, i, i) for i in range(10)]
        chunker = TranscriptChunker(
            max_tokens=300,
            overlap_turns=2,
            min_chunk_turns=1,
        )
        chunks = chunker.chunk(turns)

        # Check that non-first chunks have overlap
        for i, chunk in enumerate(chunks):
            if i > 0:
                assert chunk.overlap_turns > 0

    def test_unique_source_hashes(self) -> None:
        """Test that each chunk gets unique hash."""
        turns = [Turn("user", f"message {i}", i, i) for i in range(10)]
        chunker = TranscriptChunker(max_tokens=100, min_chunk_turns=2)
        chunks = chunker.chunk(turns)

        hashes = [c.source_hash for c in chunks]
        assert len(hashes) == len(set(hashes))  # All unique

    def test_line_range_preserved(self) -> None:
        """Test that line ranges are correct."""
        turns = [
            Turn("user", "msg1", 0, 5),
            Turn("assistant", "msg2", 6, 10),
            Turn("user", "msg3", 11, 15),
        ]
        chunker = TranscriptChunker(max_tokens=10000)
        chunks = chunker.chunk(turns)

        assert len(chunks) == 1
        assert chunks[0].line_range == (0, 15)


class TestChunkTranscript:
    """Tests for chunk_transcript convenience function."""

    def test_basic_usage(self) -> None:
        """Test basic usage of convenience function."""
        text = """user: Hello
assistant: Hi there
user: How are you?
assistant: I'm well"""

        chunks = chunk_transcript(text)

        assert len(chunks) >= 1
        assert chunks[0].is_first
        assert all(c.source_hash for c in chunks)

    def test_custom_settings(self) -> None:
        """Test custom chunking settings."""
        # Create multiple turns that exceed max_tokens
        turns_text = "\n".join(
            f"{'user' if i % 2 == 0 else 'assistant'}: {'x' * 500}" for i in range(20)
        )

        chunks = chunk_transcript(turns_text, max_tokens=500)

        # Should split into multiple chunks (each turn is ~125 tokens)
        assert len(chunks) > 1

    def test_returns_empty_for_empty(self) -> None:
        """Test empty input returns empty list."""
        assert chunk_transcript("") == []
