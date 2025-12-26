"""Implicit capture agent for LLM-based memory extraction.

This module implements the agent that analyzes conversation transcripts
using LLMs to identify memory-worthy content. The agent:

1. Chunks transcripts for efficient processing
2. Sends chunks to LLM with extraction prompts
3. Parses structured JSON responses
4. Converts to ImplicitMemory objects
5. Deduplicates against existing memories

The agent is designed for async operation to allow parallel chunk processing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .models import CaptureConfidence, ImplicitMemory
from .prompts import get_extraction_prompt
from .transcript_chunker import TranscriptChunk, chunk_transcript

if TYPE_CHECKING:
    from .adversarial_detector import AdversarialDetector
    from .llm_client import LLMClient

__all__ = [
    "ImplicitCaptureAgent",
    "ExtractionResult",
    "get_implicit_capture_agent",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Models
# =============================================================================


@dataclass(frozen=True)
class ExtractionResult:
    """Result of extracting memories from a transcript.

    Attributes:
        memories: Extracted memories ordered by confidence.
        chunks_processed: Number of chunks analyzed.
        errors: Any errors encountered during extraction.
    """

    memories: tuple[ImplicitMemory, ...]
    chunks_processed: int
    errors: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        """Check if extraction succeeded without errors."""
        return len(self.errors) == 0

    @property
    def memory_count(self) -> int:
        """Get the number of extracted memories."""
        return len(self.memories)


# =============================================================================
# Agent
# =============================================================================


@dataclass
class ImplicitCaptureAgent:
    """Agent for extracting memories from conversation transcripts.

    The agent uses an LLM to analyze transcript chunks and identify
    content worth preserving as long-term memories.

    CRIT-004: Now supports optional adversarial screening to detect
    prompt injection, memory poisoning, and other attack patterns.

    Attributes:
        llm_client: LLM client for completions.
        max_tokens_per_chunk: Maximum tokens per chunk.
        overlap_turns: Turns to overlap between chunks.
        min_confidence: Minimum confidence threshold for memories.
        project_context: Optional context about the project.
        adversarial_detector: Optional detector for adversarial content.
            If provided, memories are screened before acceptance.
        block_on_adversarial: If True and adversarial content is detected,
            block the memory. Default True.
    """

    llm_client: LLMClient
    max_tokens_per_chunk: int = 50_000
    overlap_turns: int = 4
    min_confidence: float = 0.5
    project_context: str | None = None
    adversarial_detector: AdversarialDetector | None = None
    block_on_adversarial: bool = True
    _seen_hashes: set[str] = field(default_factory=set, repr=False)

    async def analyze_transcript(
        self,
        transcript: str,
        *,
        existing_summaries: list[str] | None = None,
    ) -> ExtractionResult:
        """Analyze a transcript and extract memories.

        Args:
            transcript: Raw transcript text to analyze.
            existing_summaries: Summaries of existing memories for dedup.

        Returns:
            ExtractionResult with extracted memories.
        """
        # Reset seen hashes for this extraction
        self._seen_hashes = set()

        # Chunk the transcript
        chunks = chunk_transcript(
            transcript,
            max_tokens=self.max_tokens_per_chunk,
            overlap_turns=self.overlap_turns,
        )

        if not chunks:
            return ExtractionResult(
                memories=(),
                chunks_processed=0,
            )

        # Process each chunk
        all_memories: list[ImplicitMemory] = []
        errors: list[str] = []

        for chunk in chunks:
            try:
                memories = await self._process_chunk(
                    chunk,
                    existing_summaries=existing_summaries,
                )
                all_memories.extend(memories)
            except Exception as e:
                error_msg = f"Error processing chunk {chunk.chunk_index}: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)

        # Sort by confidence (highest first)
        all_memories.sort(key=lambda m: m.confidence.overall, reverse=True)

        return ExtractionResult(
            memories=tuple(all_memories),
            chunks_processed=len(chunks),
            errors=tuple(errors),
        )

    async def _process_chunk(
        self,
        chunk: TranscriptChunk,
        *,
        existing_summaries: list[str] | None = None,
    ) -> list[ImplicitMemory]:
        """Process a single chunk and extract memories.

        Args:
            chunk: The transcript chunk to analyze.
            existing_summaries: Summaries for deduplication.

        Returns:
            List of extracted memories from this chunk.
        """
        # Build the prompt
        prompt = get_extraction_prompt(
            chunk.to_text(),
            project_context=self.project_context,
            existing_summaries=existing_summaries,
        )

        # Call LLM with JSON mode enabled
        response = await self.llm_client.complete(
            prompt.user,
            system=prompt.system,
            json_mode=True,
        )

        # Parse response
        memories = self._parse_response(response.content, chunk)

        # CRIT-004: Screen memories for adversarial content
        if self.adversarial_detector and memories:
            memories = await self._screen_memories(memories)

        return memories

    async def _screen_memories(
        self,
        memories: list[ImplicitMemory],
    ) -> list[ImplicitMemory]:
        """Screen memories for adversarial content.

        CRIT-004: Activates adversarial screening to detect prompt injection,
        memory poisoning, and other attack patterns.

        Args:
            memories: List of memories to screen.

        Returns:
            List of memories that passed screening.
        """
        if not self.adversarial_detector:
            return memories

        screened: list[ImplicitMemory] = []
        for memory in memories:
            try:
                # Analyze both summary and content for threats
                combined = f"{memory.summary}\n\n{memory.content}"
                result = await self.adversarial_detector.analyze(combined)

                if result.should_block and self.block_on_adversarial:
                    logger.warning(
                        "Blocked adversarial memory (level=%s, patterns=%s): %s",
                        result.detection.level.value,
                        result.detection.patterns_found,
                        memory.summary[:50],
                    )
                    continue

                # Log warnings for non-blocking detections
                if result.detection.level.value not in ("none", "low"):
                    logger.info(
                        "Adversarial screening detected (level=%s): %s",
                        result.detection.level.value,
                        memory.summary[:50],
                    )

                screened.append(memory)

            except Exception as e:
                # On screening error, fail closed (block) or open based on config
                if self.block_on_adversarial:
                    logger.warning(
                        "Screening error, blocking memory as precaution: %s - %s",
                        memory.summary[:50],
                        e,
                    )
                else:
                    logger.warning(
                        "Screening error, allowing memory: %s - %s",
                        memory.summary[:50],
                        e,
                    )
                    screened.append(memory)

        return screened

    def _parse_response(
        self,
        content: str,
        chunk: TranscriptChunk,
    ) -> list[ImplicitMemory]:
        """Parse LLM response and convert to ImplicitMemory objects.

        Args:
            content: JSON response content from LLM.
            chunk: The chunk this response is for (for source info).

        Returns:
            List of parsed memories.
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM response as JSON: %s", e)
            return []

        memories_data = data.get("memories", [])
        if not isinstance(memories_data, list):
            logger.warning("Expected 'memories' array, got: %s", type(memories_data))
            return []

        memories: list[ImplicitMemory] = []
        for item in memories_data:
            try:
                memory = self._parse_memory_item(item, chunk)
                if memory is not None:
                    memories.append(memory)
            except Exception as e:
                logger.debug("Failed to parse memory item: %s", e)

        return memories

    def _parse_memory_item(
        self,
        item: dict[str, Any],
        chunk: TranscriptChunk,
    ) -> ImplicitMemory | None:
        """Parse a single memory item from LLM response.

        Args:
            item: Dictionary from LLM response.
            chunk: Source chunk for this memory.

        Returns:
            ImplicitMemory or None if invalid/duplicate.
        """
        # Validate required fields
        namespace = item.get("namespace")
        summary_raw = item.get("summary")
        content_raw = item.get("content")
        confidence_data = item.get("confidence", {})

        if not all([namespace, summary_raw, content_raw]):
            return None

        # Type narrow after validation
        summary = str(summary_raw)
        content = str(content_raw)

        # Build confidence with safe parsing (PROMPT-M-002)
        try:
            confidence = CaptureConfidence.from_factors(
                relevance=self._safe_float(confidence_data.get("relevance", 0)),
                actionability=self._safe_float(confidence_data.get("actionability", 0)),
                novelty=self._safe_float(confidence_data.get("novelty", 0)),
                specificity=self._safe_float(confidence_data.get("specificity", 0)),
                coherence=self._safe_float(confidence_data.get("coherence", 0)),
            )
        except (TypeError, ValueError) as e:
            logger.debug("Failed to parse confidence data: %s", e)
            return None

        # Skip low confidence
        if confidence.overall < self.min_confidence:
            logger.debug(
                "Skipping low-confidence memory (%.2f < %.2f): %s",
                confidence.overall,
                self.min_confidence,
                summary[:50],
            )
            return None

        # Calculate source hash for deduplication
        source_hash = self._compute_source_hash(content)

        # Check for duplicates
        if source_hash in self._seen_hashes:
            logger.debug("Skipping duplicate memory: %s", summary[:50])
            return None
        self._seen_hashes.add(source_hash)

        # Parse source lines
        source_range: tuple[int, int] | None = None
        source_lines = item.get("source_lines")
        if isinstance(source_lines, list) and len(source_lines) == 2:
            try:
                # Adjust relative lines to absolute using chunk's line range
                start = chunk.line_range[0] + int(source_lines[0])
                end = chunk.line_range[0] + int(source_lines[1])
                source_range = (start, end)
            except (ValueError, TypeError):
                # Invalid source_lines format - skip source range extraction
                # This can happen if LLM returns non-integer values
                source_range = None

        # Parse tags
        tags_raw = item.get("tags", [])
        if isinstance(tags_raw, list):
            tags = tuple(str(t) for t in tags_raw[:5])
        else:
            tags = ()

        return ImplicitMemory(
            namespace=str(namespace),
            summary=summary[:100],  # Enforce max length
            content=content,
            confidence=confidence,
            source_hash=source_hash,
            source_range=source_range,
            rationale=str(item.get("rationale", "")),
            tags=tags,
        )

    def _safe_float(self, value: object) -> float:
        """Safely convert a value to float.

        PROMPT-M-002: Handles malformed LLM responses gracefully.

        Args:
            value: Value to convert (typically from JSON parsing).

        Returns:
            Float value, or 0.0 if conversion fails.
        """
        if value is None:
            return 0.0
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

    def _compute_source_hash(self, content: str) -> str:
        """Compute a hash for deduplication.

        Args:
            content: Memory content to hash.

        Returns:
            Hex digest of content hash.
        """
        import hashlib

        return hashlib.sha256(content.encode()).hexdigest()[:16]


# =============================================================================
# Factory
# =============================================================================

_agent: ImplicitCaptureAgent | None = None


def get_implicit_capture_agent(
    *,
    enable_adversarial_screening: bool = True,
) -> ImplicitCaptureAgent:
    """Get the default implicit capture agent.

    CRIT-004: Now enables adversarial screening by default.

    Args:
        enable_adversarial_screening: If True, enables adversarial content
            screening to detect prompt injection and memory poisoning.
            Default True.

    Returns:
        ImplicitCaptureAgent configured from environment.

    Raises:
        SubconsciousnessDisabledError: If subconsciousness is disabled.
        LLMConfigurationError: If LLM is not configured.
    """
    global _agent
    if _agent is None:
        from . import get_llm_client
        from .adversarial_detector import get_adversarial_detector

        llm_client = get_llm_client()

        # CRIT-004: Enable adversarial detector by default
        adversarial_detector = None
        if enable_adversarial_screening:
            try:
                adversarial_detector = get_adversarial_detector()
            except Exception as e:
                # Log but don't fail - screening is defense-in-depth
                logger.warning("Could not initialize adversarial detector: %s", e)

        _agent = ImplicitCaptureAgent(
            llm_client=llm_client,
            adversarial_detector=adversarial_detector,
        )
    return _agent


def reset_default_agent() -> None:
    """Reset the default agent singleton.

    Useful for testing or reconfiguration.
    """
    global _agent
    _agent = None
