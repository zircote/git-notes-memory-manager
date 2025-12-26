"""Hook integration for subconsciousness layer.

This module provides integration points between the subconsciousness layer
and Claude Code hooks. It allows hooks to trigger LLM-powered implicit
capture without directly depending on the full subconsciousness module.

The main entry point is `analyze_session_transcript()` which:
1. Checks if subconsciousness is enabled
2. Reads the transcript file
3. Runs implicit capture with adversarial screening
4. Returns a summary of results

Usage from Stop hook:
    from git_notes_memory.subconsciousness.hook_integration import (
        analyze_session_transcript,
        is_subconsciousness_available,
    )

    if is_subconsciousness_available():
        result = await analyze_session_transcript(transcript_path, session_id)
        # Use result.summary for display
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .config import get_subconsciousness_config, is_subconsciousness_enabled

if TYPE_CHECKING:
    pass

__all__ = [
    "is_subconsciousness_available",
    "analyze_session_transcript",
    "HookIntegrationResult",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Result Model
# =============================================================================


@dataclass(frozen=True)
class HookIntegrationResult:
    """Result of hook-triggered implicit capture.

    Attributes:
        success: Whether capture completed without errors.
        captured_count: Number of memories captured (pending + auto-approved).
        auto_approved_count: Number of memories auto-approved.
        pending_count: Number of memories pending review.
        blocked_count: Number of memories blocked by screening.
        discarded_count: Number of memories discarded (low confidence).
        errors: List of error messages if any.
        summary: Human-readable summary for display.
    """

    success: bool
    captured_count: int
    auto_approved_count: int
    pending_count: int
    blocked_count: int
    discarded_count: int
    errors: tuple[str, ...]
    summary: str

    @classmethod
    def disabled(cls) -> HookIntegrationResult:
        """Create result for when subconsciousness is disabled."""
        return cls(
            success=True,
            captured_count=0,
            auto_approved_count=0,
            pending_count=0,
            blocked_count=0,
            discarded_count=0,
            errors=(),
            summary="Subconsciousness disabled",
        )

    @classmethod
    def empty(cls) -> HookIntegrationResult:
        """Create result for empty transcript."""
        return cls(
            success=True,
            captured_count=0,
            auto_approved_count=0,
            pending_count=0,
            blocked_count=0,
            discarded_count=0,
            errors=(),
            summary="No memories found",
        )

    @classmethod
    def error(cls, message: str) -> HookIntegrationResult:
        """Create result for an error."""
        return cls(
            success=False,
            captured_count=0,
            auto_approved_count=0,
            pending_count=0,
            blocked_count=0,
            discarded_count=0,
            errors=(message,),
            summary=f"Error: {message}",
        )


# =============================================================================
# Availability Check
# =============================================================================


def is_subconsciousness_available() -> bool:
    """Check if subconsciousness features are available.

    This checks:
    1. MEMORY_SUBCONSCIOUSNESS_ENABLED is true
    2. MEMORY_IMPLICIT_CAPTURE_ENABLED is true
    3. LLM API key is configured

    Returns:
        True if subconsciousness can be used.
    """
    if not is_subconsciousness_enabled():
        return False

    config = get_subconsciousness_config()
    if not config.implicit_capture_enabled:
        return False

    # Check API key (Ollama doesn't need one)
    from .config import LLMProvider

    # Ollama doesn't need an API key
    return config.provider == LLMProvider.OLLAMA or config.api_key is not None


# =============================================================================
# Session Analysis
# =============================================================================


async def analyze_session_transcript(
    transcript_path: str | Path,
    session_id: str | None = None,
    *,
    timeout_seconds: float = 60.0,
) -> HookIntegrationResult:
    """Analyze a session transcript for implicit captures.

    This is the main entry point for hook integration. It reads the
    transcript file and runs LLM-powered implicit capture.

    Args:
        transcript_path: Path to the session transcript file.
        session_id: Optional session identifier for tracking.
        timeout_seconds: Maximum time to wait for LLM analysis.

    Returns:
        HookIntegrationResult with capture statistics and summary.
    """
    if not is_subconsciousness_available():
        logger.debug("Subconsciousness not available, skipping analysis")
        return HookIntegrationResult.disabled()

    # Read transcript
    path = Path(transcript_path)
    if not path.exists():
        logger.warning("Transcript file not found: %s", path)
        return HookIntegrationResult.error(f"Transcript not found: {path}")

    try:
        transcript = path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to read transcript: %s", e)
        return HookIntegrationResult.error(f"Failed to read transcript: {e}")

    if not transcript.strip():
        logger.debug("Empty transcript, skipping analysis")
        return HookIntegrationResult.empty()

    # Run implicit capture with timeout
    try:
        result = await asyncio.wait_for(
            _run_implicit_capture(transcript, session_id),
            timeout=timeout_seconds,
        )
        return result
    except TimeoutError:
        logger.warning("Implicit capture timed out after %.1fs", timeout_seconds)
        return HookIntegrationResult.error(
            f"Analysis timed out after {timeout_seconds}s"
        )
    except Exception as e:
        logger.exception("Implicit capture failed: %s", e)
        return HookIntegrationResult.error(str(e))


async def _run_implicit_capture(
    transcript: str,
    session_id: str | None,
) -> HookIntegrationResult:
    """Run implicit capture on transcript content.

    Args:
        transcript: The transcript content.
        session_id: Optional session identifier.

    Returns:
        HookIntegrationResult with capture statistics.
    """
    from .implicit_capture_service import get_implicit_capture_service

    service = get_implicit_capture_service()

    # Also expire old pending captures while we're at it
    expired = service.expire_pending_captures()
    if expired > 0:
        logger.info("Expired %d old pending captures", expired)

    # Run capture
    result = await service.capture_from_transcript(
        transcript,
        session_id=session_id,
    )

    # Calculate pending (captured but not auto-approved)
    pending_count = result.capture_count - result.auto_approved_count

    # Build summary
    summary_parts = []
    if result.auto_approved_count > 0:
        summary_parts.append(f"{result.auto_approved_count} auto-captured")
    if pending_count > 0:
        summary_parts.append(f"{pending_count} pending review")
    if result.blocked_count > 0:
        summary_parts.append(f"{result.blocked_count} blocked")

    if summary_parts:
        summary = "Memories: " + ", ".join(summary_parts)
    else:
        summary = "No memories captured"

    return HookIntegrationResult(
        success=result.success,
        captured_count=result.capture_count,
        auto_approved_count=result.auto_approved_count,
        pending_count=pending_count,
        blocked_count=result.blocked_count,
        discarded_count=result.discarded_count,
        errors=result.errors,
        summary=summary,
    )


# =============================================================================
# Synchronous Wrapper
# =============================================================================


def analyze_session_transcript_sync(
    transcript_path: str | Path,
    session_id: str | None = None,
    *,
    timeout_seconds: float = 60.0,
) -> HookIntegrationResult:
    """Synchronous wrapper for analyze_session_transcript.

    This is useful for hooks that don't use async/await directly.

    Args:
        transcript_path: Path to the session transcript file.
        session_id: Optional session identifier for tracking.
        timeout_seconds: Maximum time to wait for LLM analysis.

    Returns:
        HookIntegrationResult with capture statistics and summary.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        # Already in an event loop, can't use asyncio.run
        # Create a new thread with its own event loop
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                asyncio.run,
                analyze_session_transcript(
                    transcript_path,
                    session_id,
                    timeout_seconds=timeout_seconds,
                ),
            )
            return future.result(timeout=timeout_seconds + 5)
    else:
        # No event loop, safe to use asyncio.run
        return asyncio.run(
            analyze_session_transcript(
                transcript_path,
                session_id,
                timeout_seconds=timeout_seconds,
            )
        )
