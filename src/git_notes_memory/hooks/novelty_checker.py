"""Novelty checking for detected capture signals.

This module provides the NoveltyChecker class for determining whether
a detected capture signal represents new information or is a duplicate
of existing memories. It uses semantic similarity search to find
similar memories and calculates a novelty score.

The novelty score ranges from 0.0 (duplicate) to 1.0 (completely new):
- 0.0-0.3: Likely duplicate, skip capture
- 0.3-0.7: Partial novelty, consider suggesting capture
- 0.7-1.0: High novelty, recommend capture

Example::

    checker = NoveltyChecker()
    score = checker.check_novelty("I decided to use SQLite for storage")
    if score >= 0.3:
        print("Novel content detected!")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_notes_memory.hooks.models import CaptureSignal, NoveltyResult
from git_notes_memory.observability import get_logger

if TYPE_CHECKING:
    from git_notes_memory.embedding import EmbeddingService
    from git_notes_memory.recall import RecallService

__all__ = ["NoveltyChecker"]

logger = get_logger(__name__)


class NoveltyChecker:
    """Checker for novelty of detected capture signals.

    Uses semantic similarity search to determine if a detected signal
    represents new information that should be captured, or if it's
    redundant with existing memories.

    The checker queries for similar memories using the signal's context,
    calculates similarity scores, and returns a novelty score indicating
    how "new" the content is.

    Example::

        checker = NoveltyChecker()

        # Check novelty of some text
        result = checker.check_novelty("I decided to use async/await")
        print(f"Novelty: {result.novelty_score:.2f}")
        if result.is_novel:
            print("This is new information!")

        # Check novelty of a detected signal
        signal = CaptureSignal(type=SignalType.DECISION, match="...", ...)
        result = checker.check_signal_novelty(signal)

    Attributes:
        novelty_threshold: Minimum novelty score to consider content novel.
        similarity_threshold: Similarity above which content is duplicate.
        k: Number of similar memories to check.
    """

    def __init__(
        self,
        novelty_threshold: float = 0.3,
        similarity_threshold: float = 0.7,
        k: int = 5,
        *,
        recall_service: RecallService | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        """Initialize the novelty checker.

        Args:
            novelty_threshold: Minimum novelty score (0.0-1.0) to consider
                content as novel. Default 0.3 means content is novel if
                it's less than 70% similar to existing memories.
            similarity_threshold: Similarity score (0.0-1.0) above which
                content is considered a duplicate. Default 0.7.
            k: Number of similar memories to check when calculating
                novelty. More memories = more accurate but slower.
            recall_service: Optional pre-configured RecallService instance.
                If not provided, one will be created lazily.
            embedding_service: Optional pre-configured EmbeddingService.
                If not provided, one will be created lazily.
        """
        self.novelty_threshold = novelty_threshold
        self.similarity_threshold = similarity_threshold
        self.k = k

        self._recall_service = recall_service
        self._embedding_service = embedding_service

    def _get_recall_service(self) -> RecallService:
        """Get or create the RecallService instance."""
        if self._recall_service is None:
            from git_notes_memory.recall import get_default_service

            self._recall_service = get_default_service()
        return self._recall_service

    def _get_embedding_service(self) -> EmbeddingService:
        """Get or create the EmbeddingService instance."""
        if self._embedding_service is None:
            from git_notes_memory.embedding import get_default_service

            self._embedding_service = get_default_service()
        return self._embedding_service

    def check_novelty(
        self,
        text: str,
        *,
        namespace: str | None = None,
    ) -> NoveltyResult:
        """Check novelty of text content.

        Searches for semantically similar memories and calculates a
        novelty score based on how different the text is from existing
        content.

        Args:
            text: The text content to check for novelty.
            namespace: Optional namespace to limit search scope.
                If provided, only checks against memories in that namespace.

        Returns:
            NoveltyResult with novelty score and similar memory info.

        Example::

            result = checker.check_novelty("I decided to use SQLite")
            print(f"Novelty: {result.novelty_score:.2f}")
            if result.similar_memory_ids:
                print(f"Similar to: {result.similar_memory_ids}")
        """
        if not text or not text.strip():
            # Empty text is considered fully novel (nothing to duplicate)
            return NoveltyResult(
                novelty_score=1.0,
                is_novel=True,
                similar_memory_ids=[],
                highest_similarity=0.0,
            )

        try:
            # Check if embedding model is loaded to avoid blocking hooks
            # If not loaded, assume novel (safe default) rather than block
            embedding = self._get_embedding_service()
            if not embedding.is_loaded:
                logger.debug(
                    "Embedding model not loaded, skipping novelty check "
                    "(assuming novel to avoid blocking hook execution)"
                )
                return NoveltyResult(
                    novelty_score=1.0,
                    is_novel=True,
                    similar_memory_ids=[],
                    highest_similarity=0.0,
                )

            recall = self._get_recall_service()
            results = recall.search(
                text,
                k=self.k,
                namespace=namespace,
                min_similarity=0.0,  # Get all results, filter ourselves
            )

            if not results:
                # No similar memories found = completely novel
                logger.debug("No similar memories found for: %s...", text[:50])
                return NoveltyResult(
                    novelty_score=1.0,
                    is_novel=True,
                    similar_memory_ids=[],
                    highest_similarity=0.0,
                )

            # Calculate similarity from distance
            # RecallService returns MemoryResult with distance attribute
            similarities: list[tuple[str, float]] = []
            for result in results:
                # Convert distance to similarity (1 / (1 + distance))
                distance = result.distance
                similarity = 1.0 / (1.0 + distance) if distance >= 0 else 0.0
                similarities.append((result.memory.id, similarity))

            # Get highest similarity
            highest_similarity = max(sim for _, sim in similarities)

            # Calculate novelty score (inverse of highest similarity)
            # If highest_similarity = 0.9, novelty = 0.1
            novelty_score = 1.0 - highest_similarity

            # Collect IDs of similar memories above threshold
            similar_ids = [
                mem_id
                for mem_id, sim in similarities
                if sim >= self.similarity_threshold
            ]

            is_novel = novelty_score >= self.novelty_threshold

            logger.debug(
                "Novelty check: score=%.2f, highest_sim=%.2f, similar_count=%d, is_novel=%s",
                novelty_score,
                highest_similarity,
                len(similar_ids),
                is_novel,
            )

            return NoveltyResult(
                novelty_score=novelty_score,
                is_novel=is_novel,
                similar_memory_ids=similar_ids,
                highest_similarity=highest_similarity,
            )

        except Exception as e:
            # On error, assume novel to avoid blocking captures
            logger.warning("Novelty check failed: %s", e)
            return NoveltyResult(
                novelty_score=1.0,
                is_novel=True,
                similar_memory_ids=[],
                highest_similarity=0.0,
            )

    def check_signal_novelty(
        self,
        signal: CaptureSignal,
    ) -> NoveltyResult:
        """Check novelty of a detected capture signal.

        Uses the signal's context (or match if no context) to check
        for similar existing memories. The suggested namespace from
        the signal is used to narrow the search scope.

        Args:
            signal: The capture signal to check.

        Returns:
            NoveltyResult with novelty score and similar memory info.

        Example::

            detector = SignalDetector()
            signals = detector.detect("I learned that async is better")
            for signal in signals:
                result = checker.check_signal_novelty(signal)
                if result.is_novel:
                    print(f"Novel {signal.type.value}: {signal.match}")
        """
        # Use context if available, otherwise fall back to match
        text = signal.context if signal.context else signal.match

        return self.check_novelty(
            text,
            namespace=signal.suggested_namespace,
        )

    def batch_check_novelty(
        self,
        signals: list[CaptureSignal],
    ) -> list[NoveltyResult]:
        """Check novelty for multiple signals.

        Checks each signal individually and returns results in the
        same order as the input signals.

        Args:
            signals: List of capture signals to check.

        Returns:
            List of NoveltyResult objects, one per input signal.

        Example::

            detector = SignalDetector()
            signals = detector.detect(long_text)
            results = checker.batch_check_novelty(signals)
            for signal, result in zip(signals, results):
                if result.is_novel:
                    process_novel_signal(signal)
        """
        return [self.check_signal_novelty(signal) for signal in signals]
