"""Capture decision logic for detected signals.

This module provides the CaptureDecider class for determining what action
to take when memorable content is detected. It combines signal detection,
novelty checking, and threshold-based decision making.

Decision thresholds:
- AUTO (≥0.95): Capture silently with notification
- SUGGEST (0.7-0.95): Show suggestion, user confirms
- SKIP (<0.7): No action, unless explicit signal

Example::

    decider = CaptureDecider()
    decision = decider.decide(signals)
    if decision.action == CaptureAction.AUTO:
        for capture in decision.suggested_captures:
            memory_service.capture(capture)
    elif decision.action == CaptureAction.SUGGEST:
        show_suggestions(decision.suggested_captures)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_notes_memory.hooks.models import (
    CaptureAction,
    CaptureDecision,
    CaptureSignal,
    NoveltyResult,
    SignalType,
    SuggestedCapture,
)
from git_notes_memory.observability import get_logger

if TYPE_CHECKING:
    from git_notes_memory.hooks.config_loader import HookConfig
    from git_notes_memory.hooks.novelty_checker import NoveltyChecker

__all__ = ["CaptureDecider"]

logger = get_logger(__name__)


class CaptureDecider:
    """Decider for memory capture actions based on detected signals.

    Takes detected signals and determines the appropriate action:
    - AUTO: High-confidence signals are captured automatically
    - SUGGEST: Medium-confidence signals are suggested to the user
    - SKIP: Low-confidence signals are ignored

    The decider also performs novelty checking to avoid capturing
    duplicate content that already exists in the memory store.

    Example::

        decider = CaptureDecider()

        # Decide on detected signals
        decision = decider.decide(signals)
        print(f"Action: {decision.action.value}")
        print(f"Reason: {decision.reason}")

        # Generate capture suggestions
        for capture in decision.suggested_captures:
            print(f"  {capture.namespace}: {capture.summary}")

    Attributes:
        auto_threshold: Confidence threshold for AUTO capture.
        suggest_threshold: Confidence threshold for SUGGEST.
        novelty_threshold: Minimum novelty score to capture.
        check_novelty_enabled: Whether to check for duplicates.
    """

    def __init__(
        self,
        auto_threshold: float = 0.95,
        suggest_threshold: float = 0.7,
        novelty_threshold: float = 0.3,
        *,
        check_novelty_enabled: bool = True,
        novelty_checker: NoveltyChecker | None = None,
        config: HookConfig | None = None,
    ) -> None:
        """Initialize the capture decider.

        Args:
            auto_threshold: Confidence threshold for automatic capture.
                Signals at or above this threshold are captured without
                user confirmation. Default 0.95.
            suggest_threshold: Confidence threshold for suggestions.
                Signals at or above this threshold (but below auto) are
                suggested to the user. Default 0.7.
            novelty_threshold: Minimum novelty score (0.0-1.0) required
                for capture. Content below this is considered duplicate.
                Default 0.3.
            check_novelty_enabled: Whether to perform novelty checking.
                If False, all signals pass novelty check.
            novelty_checker: Optional pre-configured NoveltyChecker.
                If not provided, one will be created lazily.
            config: Optional HookConfig to override default thresholds.
        """
        # Apply config overrides if provided
        if config is not None:
            auto_threshold = config.capture_detection_auto_threshold
            suggest_threshold = config.capture_detection_min_confidence
            novelty_threshold = config.capture_detection_novelty_threshold

        self.auto_threshold = auto_threshold
        self.suggest_threshold = suggest_threshold
        self.novelty_threshold = novelty_threshold
        self.check_novelty_enabled = check_novelty_enabled

        self._novelty_checker = novelty_checker

    def _get_novelty_checker(self) -> NoveltyChecker:
        """Get or create the NoveltyChecker instance."""
        if self._novelty_checker is None:
            from git_notes_memory.hooks.novelty_checker import NoveltyChecker

            self._novelty_checker = NoveltyChecker(
                novelty_threshold=self.novelty_threshold,
            )
        return self._novelty_checker

    def decide(
        self,
        signals: list[CaptureSignal],
        *,
        check_novelty: bool | None = None,
    ) -> CaptureDecision:
        """Decide capture action for detected signals.

        Evaluates all signals, checks novelty, and returns a decision
        with the appropriate action and suggested captures.

        Args:
            signals: List of detected capture signals.
            check_novelty: Override for novelty checking. If None, uses
                the instance setting (check_novelty_enabled).

        Returns:
            CaptureDecision with action, signals, and suggested captures.

        Example::

            signals = detector.detect("I decided to use PostgreSQL")
            decision = decider.decide(signals)

            if decision.action == CaptureAction.AUTO:
                # Capture automatically
                for capture in decision.suggested_captures:
                    memory_service.capture(capture)
            elif decision.action == CaptureAction.SUGGEST:
                # Show to user
                print("Would you like to capture this?")
        """
        if not signals:
            return CaptureDecision(
                action=CaptureAction.SKIP,
                signals=(),
                suggested_captures=(),
                reason="No signals detected",
            )

        # Determine if we should check novelty
        should_check = (
            check_novelty if check_novelty is not None else self.check_novelty_enabled
        )

        # Process each signal
        novel_signals: list[tuple[CaptureSignal, NoveltyResult | None]] = []

        for signal in signals:
            if should_check:
                novelty = self._check_signal_novelty(signal)
                if novelty.is_novel:
                    novel_signals.append((signal, novelty))
                else:
                    logger.debug(
                        "Signal skipped (duplicate): %s (novelty=%.2f)",
                        signal.match[:30],
                        novelty.novelty_score,
                    )
            else:
                novel_signals.append((signal, None))

        if not novel_signals:
            return CaptureDecision(
                action=CaptureAction.SKIP,
                signals=tuple(signals),
                suggested_captures=(),
                reason="All signals are duplicates of existing memories",
            )

        # Determine action based on highest confidence among novel signals
        highest_confidence = max(s.confidence for s, _ in novel_signals)

        if highest_confidence >= self.auto_threshold:
            action = CaptureAction.AUTO
            reason = f"High confidence signal detected ({highest_confidence:.2f} >= {self.auto_threshold})"
        elif highest_confidence >= self.suggest_threshold:
            action = CaptureAction.SUGGEST
            reason = f"Medium confidence signal detected ({highest_confidence:.2f})"
        else:
            action = CaptureAction.SKIP
            reason = f"Low confidence signals ({highest_confidence:.2f} < {self.suggest_threshold})"

        # Check for explicit signals - these always trigger SUGGEST at minimum
        has_explicit = any(s.type == SignalType.EXPLICIT for s, _ in novel_signals)
        if has_explicit and action == CaptureAction.SKIP:
            action = CaptureAction.SUGGEST
            reason = "Explicit capture request detected"

        # Generate suggested captures for AUTO and SUGGEST actions
        suggested_captures: tuple[SuggestedCapture, ...] = ()
        if action in (CaptureAction.AUTO, CaptureAction.SUGGEST):
            suggested_captures = tuple(
                self._generate_suggestion(signal, novelty)
                for signal, novelty in novel_signals
                if signal.confidence >= self.suggest_threshold
                or signal.type == SignalType.EXPLICIT
            )

        return CaptureDecision(
            action=action,
            signals=tuple(signals),
            suggested_captures=suggested_captures,
            reason=reason,
        )

    def _check_signal_novelty(self, signal: CaptureSignal) -> NoveltyResult:
        """Check novelty of a signal.

        Args:
            signal: The capture signal to check.

        Returns:
            NoveltyResult with novelty score and similar memory info.
        """
        checker = self._get_novelty_checker()
        return checker.check_signal_novelty(signal)

    def _generate_suggestion(
        self,
        signal: CaptureSignal,
        novelty: NoveltyResult | None,
    ) -> SuggestedCapture:
        """Generate a suggested capture from a signal.

        Creates a SuggestedCapture with pre-filled metadata based on
        the signal type, content, and context.

        Args:
            signal: The capture signal.
            novelty: Optional novelty check result.

        Returns:
            SuggestedCapture with namespace, summary, content, and tags.
        """
        # Generate summary from context or match
        summary = self._extract_summary(signal)

        # Generate tags from signal type and content
        tags = self._extract_tags(signal)

        # Determine confidence (factor in novelty if available)
        confidence = signal.confidence
        if novelty is not None:
            # Slightly reduce confidence if there's some similarity
            confidence = confidence * (0.5 + 0.5 * novelty.novelty_score)

        return SuggestedCapture(
            namespace=signal.suggested_namespace,
            summary=summary,
            content=signal.context or signal.match,
            tags=tags,
            confidence=round(confidence, 3),
        )

    def _extract_summary(self, signal: CaptureSignal) -> str:
        """Extract a summary from the signal.

        Args:
            signal: The capture signal.

        Returns:
            Summary string suitable for memory storage.
        """
        # Use context if available, otherwise match
        text = signal.context if signal.context else signal.match

        # Clean up the text
        text = text.strip()

        # Remove leading/trailing ellipsis from context extraction
        if text.startswith("..."):
            text = text[3:].strip()
        if text.endswith("..."):
            text = text[:-3].strip()

        # Truncate if too long (summaries should be concise)
        max_length = 200
        if len(text) > max_length:
            # Find a good breaking point
            break_point = text.rfind(" ", 0, max_length - 3)
            if break_point > max_length // 2:
                text = text[:break_point] + "..."
            else:
                text = text[: max_length - 3] + "..."

        return text

    def _extract_tags(self, signal: CaptureSignal) -> tuple[str, ...]:
        """Extract tags from a signal.

        Generates relevant tags based on signal type and content.

        Args:
            signal: The capture signal.

        Returns:
            Tuple of tag strings.
        """
        tags: list[str] = []

        # Always add signal type as a tag
        tags.append(signal.type.value)

        # Add content-based tags
        content = (signal.context or signal.match).lower()

        # Technology tags
        tech_keywords = {
            "python": ["python", "pip", "pytest", "django", "flask"],
            "javascript": ["javascript", "js", "node", "npm", "react", "vue"],
            "typescript": ["typescript", "ts"],
            "database": ["database", "sql", "postgres", "mysql", "sqlite", "mongodb"],
            "api": ["api", "rest", "graphql", "endpoint"],
            "docker": ["docker", "container", "kubernetes", "k8s"],
            "git": ["git", "commit", "branch", "merge", "rebase"],
            "testing": ["test", "unittest", "pytest", "jest", "testing"],
            "performance": ["performance", "optimization", "cache", "fast", "slow"],
            "security": ["security", "auth", "authentication", "encryption"],
        }

        for tag, keywords in tech_keywords.items():
            if any(kw in content for kw in keywords):
                tags.append(tag)

        # Limit to reasonable number of tags
        return tuple(tags[:5])

    def should_capture(
        self,
        signals: list[CaptureSignal],
    ) -> bool:
        """Quick check if any signals warrant capture.

        Convenience method that returns True if the decision would
        be AUTO or SUGGEST.

        Args:
            signals: List of detected signals.

        Returns:
            True if capture is recommended.
        """
        decision = self.decide(signals)
        return decision.action in (CaptureAction.AUTO, CaptureAction.SUGGEST)

    def decide_single(
        self,
        signal: CaptureSignal,
        *,
        check_novelty: bool | None = None,
    ) -> CaptureDecision:
        """Decide capture action for a single signal.

        Convenience method for processing a single signal.

        Args:
            signal: The capture signal to evaluate.
            check_novelty: Override for novelty checking.

        Returns:
            CaptureDecision for the signal.
        """
        return self.decide([signal], check_novelty=check_novelty)
