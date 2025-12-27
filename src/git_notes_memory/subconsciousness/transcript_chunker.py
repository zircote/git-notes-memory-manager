"""Transcript chunking for LLM analysis.

This module handles splitting conversation transcripts into manageable
chunks for LLM analysis. It preserves conversation structure by:

- Splitting at turn boundaries (not mid-message)
- Preserving context across chunks (sliding window)
- Marking chunk boundaries for source tracking
- Handling large transcripts efficiently

The chunker is designed to work with Claude's context window while
maintaining enough context for accurate memory extraction.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

__all__ = [
    "TranscriptChunk",
    "TranscriptChunker",
    "Turn",
    "chunk_transcript",
]


# =============================================================================
# Models
# =============================================================================


@dataclass(frozen=True)
class Turn:
    """A single turn in a conversation.

    A turn represents one message from a participant (user or assistant).

    Attributes:
        role: Who sent the message (user, assistant, system).
        content: The message text.
        line_start: Starting line number in original transcript.
        line_end: Ending line number in original transcript.
    """

    role: str
    content: str
    line_start: int
    line_end: int

    @property
    def token_estimate(self) -> int:
        """Estimate token count (approximately 4 characters per token)."""
        return len(self.content) // 4 + 1


@dataclass(frozen=True)
class TranscriptChunk:
    """A chunk of a transcript for LLM analysis.

    Chunks maintain context by including overlap with adjacent chunks.
    The content_hash enables deduplication.

    Attributes:
        turns: Sequence of turns in this chunk.
        chunk_index: Zero-based index of this chunk.
        total_chunks: Total number of chunks in the transcript.
        overlap_turns: Number of turns overlapping with previous chunk.
        source_hash: SHA256 hash of chunk content for deduplication.
        line_range: (start, end) line numbers in original transcript.
    """

    turns: tuple[Turn, ...]
    chunk_index: int
    total_chunks: int
    overlap_turns: int
    source_hash: str
    line_range: tuple[int, int]

    @property
    def token_estimate(self) -> int:
        """Estimate total token count for this chunk."""
        return sum(turn.token_estimate for turn in self.turns)

    @property
    def is_first(self) -> bool:
        """Check if this is the first chunk."""
        return self.chunk_index == 0

    @property
    def is_last(self) -> bool:
        """Check if this is the last chunk."""
        return self.chunk_index == self.total_chunks - 1

    def to_text(self) -> str:
        """Convert chunk to plain text format.

        Returns:
            Text with role prefixes (e.g., "user: ...", "assistant: ...").
        """
        lines = []
        for turn in self.turns:
            lines.append(f"{turn.role}: {turn.content}")
        return "\n\n".join(lines)


# =============================================================================
# Chunker
# =============================================================================


@dataclass
class TranscriptChunker:
    """Splits transcripts into chunks for LLM analysis.

    The chunker uses a sliding window approach to maintain context
    between chunks while staying within token limits.

    Attributes:
        max_tokens: Maximum tokens per chunk (default 100k).
        overlap_turns: Number of turns to repeat for context.
        min_chunk_turns: Minimum turns per chunk.
    """

    max_tokens: int = 100_000
    overlap_turns: int = 4
    min_chunk_turns: int = 8

    def chunk(self, turns: list[Turn]) -> list[TranscriptChunk]:
        """Split turns into chunks.

        Args:
            turns: List of conversation turns.

        Returns:
            List of TranscriptChunk objects.
        """
        if not turns:
            return []

        # For small conversations, return single chunk
        total_tokens = sum(t.token_estimate for t in turns)
        if total_tokens <= self.max_tokens:
            return [self._create_chunk(turns, 0, 1, 0)]

        # Split into multiple chunks
        chunks: list[TranscriptChunk] = []
        start_idx = 0
        chunk_index = 0

        while start_idx < len(turns):
            # Find how many turns fit in this chunk
            end_idx = self._find_chunk_end(turns, start_idx)

            # Create chunk
            chunk_turns = turns[start_idx:end_idx]
            overlap = min(self.overlap_turns, start_idx) if start_idx > 0 else 0

            # Include overlap from previous chunk
            if overlap > 0:
                overlap_start = start_idx - overlap
                chunk_turns = turns[overlap_start:end_idx]

            # Placeholder for total chunks (will update later)
            chunk = self._create_chunk(
                chunk_turns,
                chunk_index,
                0,  # Placeholder
                overlap if start_idx > 0 else 0,
            )
            chunks.append(chunk)

            # Move to next chunk
            start_idx = end_idx
            chunk_index += 1

        # Update total_chunks in all chunks
        total = len(chunks)
        chunks = [
            TranscriptChunk(
                turns=c.turns,
                chunk_index=c.chunk_index,
                total_chunks=total,
                overlap_turns=c.overlap_turns,
                source_hash=c.source_hash,
                line_range=c.line_range,
            )
            for c in chunks
        ]

        return chunks

    def _find_chunk_end(self, turns: list[Turn], start_idx: int) -> int:
        """Find the end index for a chunk starting at start_idx.

        Args:
            turns: All turns in the transcript.
            start_idx: Starting index for this chunk.

        Returns:
            End index (exclusive) for the chunk.
        """
        tokens = 0
        end_idx = start_idx

        for i in range(start_idx, len(turns)):
            turn_tokens = turns[i].token_estimate
            if tokens + turn_tokens > self.max_tokens:
                # Can't fit this turn
                break
            tokens += turn_tokens
            end_idx = i + 1

        # Ensure minimum chunk size
        min_end = min(start_idx + self.min_chunk_turns, len(turns))
        return max(end_idx, min_end)

    def _create_chunk(
        self,
        turns: list[Turn],
        chunk_index: int,
        total_chunks: int,
        overlap_turns: int,
    ) -> TranscriptChunk:
        """Create a TranscriptChunk from turns.

        Args:
            turns: Turns to include in the chunk.
            chunk_index: Index of this chunk.
            total_chunks: Total number of chunks.
            overlap_turns: Number of overlapping turns.

        Returns:
            TranscriptChunk with computed hash and line range.
        """
        # Compute source hash
        content = "\n".join(f"{t.role}:{t.content}" for t in turns)
        source_hash = hashlib.sha256(content.encode()).hexdigest()

        # Compute line range
        line_start = turns[0].line_start if turns else 0
        line_end = turns[-1].line_end if turns else 0

        return TranscriptChunk(
            turns=tuple(turns),
            chunk_index=chunk_index,
            total_chunks=total_chunks,
            overlap_turns=overlap_turns,
            source_hash=source_hash,
            line_range=(line_start, line_end),
        )


# =============================================================================
# Parser
# =============================================================================


def parse_transcript(text: str) -> list[Turn]:
    """Parse a transcript text into turns.

    Supports multiple formats:
    - "user: message" / "assistant: message" prefixed
    - "Human: " / "Assistant: " prefixed (Claude format)
    - Line-by-line alternating (assumes user starts)

    Args:
        text: Raw transcript text.

    Returns:
        List of Turn objects.
    """
    if not text.strip():
        return []

    turns: list[Turn] = []
    lines = text.split("\n")

    current_role: str | None = None
    current_content: list[str] = []
    current_start = 0

    role_prefixes = {
        "user:": "user",
        "human:": "user",
        "assistant:": "assistant",
        "claude:": "assistant",
        "system:": "system",
    }

    for line_num, line in enumerate(lines):
        stripped = line.strip().lower()

        # Check for role prefix
        new_role = None
        content_after_prefix = line.strip()

        for prefix, role in role_prefixes.items():
            if stripped.startswith(prefix):
                new_role = role
                content_after_prefix = line.strip()[len(prefix) :].strip()
                break

        if new_role is not None:
            # Save previous turn if any
            if current_role is not None and current_content:
                turns.append(
                    Turn(
                        role=current_role,
                        content="\n".join(current_content).strip(),
                        line_start=current_start,
                        line_end=line_num - 1,
                    )
                )

            # Start new turn
            current_role = new_role
            current_content = [content_after_prefix] if content_after_prefix else []
            current_start = line_num
        else:
            # Continue current turn
            if current_role is not None:
                current_content.append(line)
            elif line.strip():
                # No role yet, assume user starts
                current_role = "user"
                current_content = [line]
                current_start = line_num

    # Add final turn
    if current_role is not None and current_content:
        turns.append(
            Turn(
                role=current_role,
                content="\n".join(current_content).strip(),
                line_start=current_start,
                line_end=len(lines) - 1,
            )
        )

    return turns


# =============================================================================
# Convenience Function
# =============================================================================


def chunk_transcript(
    text: str,
    *,
    max_tokens: int = 100_000,
    overlap_turns: int = 4,
) -> list[TranscriptChunk]:
    """Parse and chunk a transcript in one step.

    Args:
        text: Raw transcript text.
        max_tokens: Maximum tokens per chunk.
        overlap_turns: Turns to repeat for context.

    Returns:
        List of TranscriptChunk objects.
    """
    turns = parse_transcript(text)
    chunker = TranscriptChunker(
        max_tokens=max_tokens,
        overlap_turns=overlap_turns,
    )
    return chunker.chunk(turns)
