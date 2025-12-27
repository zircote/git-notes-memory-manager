"""Implicit capture service with adversarial screening.

This module provides the main service for implicit memory capture,
combining transcript analysis with security screening:

1. Analyzes transcripts using ImplicitCaptureAgent
2. Screens each extracted memory using AdversarialDetector
3. Auto-approves high-confidence captures above threshold
4. Queues medium-confidence captures for human review
5. Discards low-confidence captures below review threshold
6. Returns results with threat information

The service is designed to be the primary entry point for implicit
memory capture from conversation transcripts.

Configuration Thresholds:
    - auto_capture_threshold (default 0.9): Auto-approve above this
    - review_threshold (default 0.7): Queue for review above this
    - Below review_threshold: Discarded
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

# Observability imports
from git_notes_memory.observability import get_logger, get_metrics, trace_operation

from .adversarial_detector import AdversarialDetector
from .capture_store import CaptureStore, create_capture
from .config import (
    DEFAULT_AUTO_CAPTURE_THRESHOLD,
    DEFAULT_REVIEW_THRESHOLD,
    get_subconsciousness_config,
)
from .implicit_capture_agent import ImplicitCaptureAgent
from .models import ImplicitCapture, ImplicitMemory, ReviewStatus, ThreatDetection

if TYPE_CHECKING:
    pass

__all__ = [
    "ImplicitCaptureService",
    "CaptureServiceResult",
    "get_implicit_capture_service",
    "reset_implicit_capture_service",
]

# Structured logger with trace context injection
logger = get_logger(__name__)


# =============================================================================
# Models
# =============================================================================


@dataclass(frozen=True)
class CaptureServiceResult:
    """Result of the implicit capture service.

    Attributes:
        captured: Memories that were stored successfully (pending or auto-approved).
        auto_approved: Memories that were auto-approved (high confidence).
        blocked: Memories that were blocked by adversarial screening.
        discarded: Memories that were discarded (low confidence).
        total_extracted: Total memories extracted from transcript.
        chunks_processed: Number of transcript chunks processed.
        errors: Any errors encountered.
    """

    captured: tuple[ImplicitCapture, ...]
    blocked: tuple[ImplicitCapture, ...]
    total_extracted: int
    chunks_processed: int
    auto_approved: tuple[ImplicitCapture, ...] = ()
    discarded: tuple[ImplicitCapture, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        """Check if capture succeeded without errors."""
        return len(self.errors) == 0

    @property
    def capture_count(self) -> int:
        """Get count of successfully captured memories."""
        return len(self.captured)

    @property
    def blocked_count(self) -> int:
        """Get count of blocked memories."""
        return len(self.blocked)

    @property
    def auto_approved_count(self) -> int:
        """Get count of auto-approved memories."""
        return len(self.auto_approved)

    @property
    def discarded_count(self) -> int:
        """Get count of discarded memories."""
        return len(self.discarded)


# =============================================================================
# Service
# =============================================================================


@dataclass
class ImplicitCaptureService:
    """Service for implicit memory capture with screening.

    Combines transcript analysis, adversarial screening, and storage
    into a single unified service. Supports three-tier confidence handling:

    1. High confidence (>= auto_capture_threshold): Auto-approved
    2. Medium confidence (>= review_threshold): Queued for review
    3. Low confidence (< review_threshold): Discarded

    Attributes:
        capture_agent: Agent for extracting memories from transcripts.
        detector: Detector for screening adversarial content.
        store: Store for persisting captures.
        expiration_days: Days until pending captures expire (default 7).
        auto_capture_threshold: Confidence for auto-approval (default 0.9).
        review_threshold: Minimum confidence for queuing (default 0.7).
    """

    capture_agent: ImplicitCaptureAgent
    detector: AdversarialDetector
    store: CaptureStore
    expiration_days: int = 7
    auto_capture_threshold: float = field(default=DEFAULT_AUTO_CAPTURE_THRESHOLD)
    review_threshold: float = field(default=DEFAULT_REVIEW_THRESHOLD)

    async def capture_from_transcript(
        self,
        transcript: str,
        *,
        session_id: str | None = None,
        existing_summaries: list[str] | None = None,
        skip_screening: bool = False,
        auto_approve: bool = True,
    ) -> CaptureServiceResult:
        """Capture memories from a conversation transcript.

        Implements three-tier confidence handling:
        1. High confidence (>= auto_capture_threshold): Auto-approved if enabled
        2. Medium confidence (>= review_threshold): Queued for review
        3. Low confidence (< review_threshold): Discarded

        Args:
            transcript: Raw transcript text to analyze.
            session_id: Optional session identifier.
            existing_summaries: Summaries of existing memories for dedup.
            skip_screening: Skip adversarial screening (for testing).
            auto_approve: Auto-approve high-confidence captures (default True).

        Returns:
            CaptureServiceResult with captured, auto-approved, blocked, and
            discarded memories.
        """
        metrics = get_metrics()
        start_time = time.time()

        with trace_operation(
            "service.capture_from_transcript",
            transcript_length=len(transcript),
            session_id=session_id or "none",
            skip_screening=skip_screening,
            auto_approve=auto_approve,
        ) as span:
            errors: list[str] = []

            # Step 1: Extract memories from transcript
            extraction = await self.capture_agent.analyze_transcript(
                transcript,
                existing_summaries=existing_summaries,
            )
            span.set_tag("extraction_memories", len(extraction.memories))
            span.set_tag("chunks_processed", extraction.chunks_processed)

            if not extraction.success:
                errors.extend(extraction.errors)

            if not extraction.memories:
                logger.info(
                    "No memories extracted from transcript",
                    transcript_length=len(transcript),
                    chunks_processed=extraction.chunks_processed,
                )
                return CaptureServiceResult(
                    captured=(),
                    blocked=(),
                    total_extracted=0,
                    chunks_processed=extraction.chunks_processed,
                    errors=tuple(errors),
                )

            # Step 2: Process each memory with screening and confidence handling
            captured: list[ImplicitCapture] = []
            auto_approved: list[ImplicitCapture] = []
            blocked: list[ImplicitCapture] = []
            discarded: list[ImplicitCapture] = []

            for memory in extraction.memories:
                try:
                    # Check confidence threshold before processing
                    confidence = memory.confidence.overall
                    if confidence < self.review_threshold:
                        # Discard low-confidence memories
                        capture = create_capture(
                            memory=memory,
                            threat_detection=ThreatDetection.safe(),
                            session_id=session_id,
                            expiration_days=self.expiration_days,
                        )
                        discarded.append(capture)
                        logger.debug(
                            "Discarded low-confidence memory",
                            confidence=round(confidence, 3),
                            threshold=self.review_threshold,
                            summary=memory.summary[:50],
                        )
                        metrics.increment(
                            "service_memory_discarded",
                            labels={"reason": "low_confidence"},
                        )
                        continue

                    # Screen for adversarial content
                    capture = await self._process_memory(
                        memory,
                        session_id=session_id,
                        skip_screening=skip_screening,
                    )

                    if capture.threat_detection.should_block:
                        blocked.append(capture)
                        logger.info(
                            "Blocked memory",
                            threat_level=capture.threat_detection.level.value,
                            summary=memory.summary[:50],
                        )
                        metrics.increment(
                            "service_memory_blocked",
                            labels={
                                "threat_level": capture.threat_detection.level.value
                            },
                        )
                    elif auto_approve and confidence >= self.auto_capture_threshold:
                        # Auto-approve high-confidence captures
                        approved_capture = ImplicitCapture(
                            id=capture.id,
                            memory=capture.memory,
                            status=ReviewStatus.APPROVED,
                            threat_detection=capture.threat_detection,
                            created_at=capture.created_at,
                            expires_at=capture.expires_at,
                            session_id=capture.session_id,
                            reviewed_at=capture.created_at,  # Auto-reviewed now
                        )
                        self.store.save(approved_capture)
                        auto_approved.append(approved_capture)
                        captured.append(approved_capture)
                        logger.info(
                            "Auto-approved memory",
                            confidence=round(confidence, 3),
                            namespace=memory.namespace,
                            summary=memory.summary[:50],
                        )
                        metrics.increment(
                            "service_memory_approved",
                            labels={"method": "auto", "namespace": memory.namespace},
                        )
                    else:
                        # Queue for review (pending status)
                        self.store.save(capture)
                        captured.append(capture)
                        logger.debug(
                            "Queued memory for review",
                            confidence=round(confidence, 3),
                            namespace=memory.namespace,
                            summary=memory.summary[:50],
                        )
                        metrics.increment(
                            "service_memory_queued",
                            labels={"namespace": memory.namespace},
                        )

                except Exception as e:
                    error_msg = f"Error processing memory '{memory.summary[:30]}': {e}"
                    logger.warning(
                        "Memory processing failed",
                        summary=memory.summary[:30],
                        error=str(e),
                    )
                    errors.append(error_msg)
                    metrics.increment(
                        "service_memory_errors",
                        labels={"error_type": type(e).__name__},
                    )

            # Record final metrics
            duration_ms = (time.time() - start_time) * 1000
            metrics.observe("service_capture_duration_ms", duration_ms)
            metrics.increment("service_capture_total", len(captured))

            span.set_tag("captured_count", len(captured))
            span.set_tag("auto_approved_count", len(auto_approved))
            span.set_tag("blocked_count", len(blocked))
            span.set_tag("discarded_count", len(discarded))
            span.set_tag("errors_count", len(errors))
            span.set_tag("duration_ms", duration_ms)

            logger.info(
                "Transcript capture completed",
                captured=len(captured),
                auto_approved=len(auto_approved),
                blocked=len(blocked),
                discarded=len(discarded),
                total_extracted=len(extraction.memories),
                duration_ms=round(duration_ms, 2),
            )

            return CaptureServiceResult(
                captured=tuple(captured),
                blocked=tuple(blocked),
                total_extracted=len(extraction.memories),
                chunks_processed=extraction.chunks_processed,
                auto_approved=tuple(auto_approved),
                discarded=tuple(discarded),
                errors=tuple(errors),
            )

    async def _process_memory(
        self,
        memory: ImplicitMemory,
        *,
        session_id: str | None = None,
        skip_screening: bool = False,
    ) -> ImplicitCapture:
        """Process a single memory through screening.

        Args:
            memory: The memory to process.
            session_id: Optional session identifier.
            skip_screening: Skip adversarial screening.

        Returns:
            ImplicitCapture with threat detection results.
        """
        # Screen the memory content
        if skip_screening:
            threat_detection = ThreatDetection.safe()
        else:
            # Screen both summary and content
            content_to_screen = f"{memory.summary}\n\n{memory.content}"
            detection_result = await self.detector.analyze(content_to_screen)
            threat_detection = detection_result.detection

        # Create the capture
        return create_capture(
            memory=memory,
            threat_detection=threat_detection,
            expiration_days=self.expiration_days,
            session_id=session_id,
        )

    async def capture_single(
        self,
        memory: ImplicitMemory,
        *,
        session_id: str | None = None,
    ) -> ImplicitCapture:
        """Capture a single memory with screening.

        Args:
            memory: The memory to capture.
            session_id: Optional session identifier.

        Returns:
            ImplicitCapture (may be blocked or pending).
        """
        capture = await self._process_memory(
            memory,
            session_id=session_id,
        )

        if not capture.threat_detection.should_block:
            self.store.save(capture)

        return capture

    def get_pending_captures(
        self,
        *,
        limit: int = 50,
    ) -> list[ImplicitCapture]:
        """Get pending captures awaiting review.

        Args:
            limit: Maximum captures to return.

        Returns:
            List of pending ImplicitCapture objects.
        """
        return self.store.get_pending(limit=limit)

    def approve_capture(self, capture_id: str) -> bool:
        """Approve a pending capture.

        Args:
            capture_id: ID of the capture to approve.

        Returns:
            True if approved successfully.
        """
        return self.store.update_status(capture_id, ReviewStatus.APPROVED)

    def reject_capture(self, capture_id: str) -> bool:
        """Reject a pending capture.

        Args:
            capture_id: ID of the capture to reject.

        Returns:
            True if rejected successfully.
        """
        return self.store.update_status(capture_id, ReviewStatus.REJECTED)

    def expire_pending_captures(self) -> int:
        """Mark expired pending captures as expired.

        This should be called periodically to clean up old pending captures.

        Returns:
            Number of captures expired.
        """
        return self.store.expire_old_captures()

    def cleanup_old_captures(self, older_than_days: int = 30) -> int:
        """Delete reviewed captures older than threshold.

        Args:
            older_than_days: Delete captures reviewed this many days ago.

        Returns:
            Number of captures deleted.
        """
        return self.store.cleanup_reviewed(older_than_days)

    def get_capture_stats(self) -> dict[str, int]:
        """Get counts of captures by status.

        Returns:
            Dict mapping status to count.
        """
        return self.store.count_by_status()


# =============================================================================
# Factory
# =============================================================================

_service: ImplicitCaptureService | None = None


def get_implicit_capture_service() -> ImplicitCaptureService:
    """Get the default implicit capture service.

    Returns:
        ImplicitCaptureService configured from environment.

    Raises:
        SubconsciousnessDisabledError: If subconsciousness is disabled.
        LLMConfigurationError: If LLM is not configured.
    """
    global _service
    if _service is None:
        from . import get_capture_store, get_llm_client

        llm_client = get_llm_client()
        config = get_subconsciousness_config()

        _service = ImplicitCaptureService(
            capture_agent=ImplicitCaptureAgent(llm_client=llm_client),
            detector=AdversarialDetector(llm_client=llm_client),
            store=get_capture_store(),
            auto_capture_threshold=config.auto_capture_threshold,
            review_threshold=config.review_threshold,
        )
    return _service


def reset_implicit_capture_service() -> None:
    """Reset the service singleton for testing."""
    global _service
    _service = None
