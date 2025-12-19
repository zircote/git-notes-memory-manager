"""Signal detection for memorable content in user prompts.

This module provides the SignalDetector class for identifying capture signals
in user input text. It uses pre-compiled regex patterns to efficiently detect
decision-making, learning moments, blockers, and other memorable content.

The detector supports:
- Pattern-based signal detection with confidence scoring
- Automatic namespace classification based on signal type
- Context extraction around matched patterns
- De-duplication of overlapping matches

Example::

    detector = SignalDetector()
    signals = detector.detect("I decided to use SQLite for storage because...")
    for signal in signals:
        print(f"{signal.type}: {signal.match} (confidence={signal.confidence})")
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from git_notes_memory.hooks.models import CaptureSignal, SignalType

__all__ = ["SignalDetector", "SIGNAL_PATTERNS"]

logger = logging.getLogger(__name__)

# Pattern definitions by signal type
# Each pattern is a tuple of (regex_string, base_confidence)
# Higher base_confidence indicates a stronger signal
SIGNAL_PATTERNS: dict[SignalType, list[tuple[str, float]]] = {
    SignalType.DECISION: [
        # Strong decision signals (high confidence)
        (r"(?i)\b(I|we)\s+(decided|chose|selected|picked|opted)\s+(to|for|on)\b", 0.90),
        (r"(?i)\bthe decision (is|was) (to|that)\b", 0.88),
        (r"(?i)\bwe('ll| will)\s+go with\b", 0.85),
        (r"(?i)\bafter (considering|evaluating|weighing),?\s+(I|we)\b", 0.85),
        # Moderate decision signals
        (r"(?i)\b(I|we) went with\b", 0.80),
        (r"(?i)\bfinal(ly)? (choosing|decided|settled on)\b", 0.82),
        (r"(?i)\bmade the call to\b", 0.80),
    ],
    SignalType.LEARNING: [
        # Strong learning signals
        (
            r"(?i)\b(I|we)\s+(learned|realized|discovered|found out)\s+(that|about)?\b",
            0.90,
        ),
        (r"(?i)\bTIL\b", 0.95),  # Very strong explicit signal
        (r"(?i)\bturns out\b", 0.85),
        (r"(?i)\bkey (insight|takeaway|learning)[:\s]", 0.92),
        # Moderate learning signals
        (r"(?i)\binteresting(ly)?[,:]?\s+", 0.70),
        (r"(?i)\bI (didn't|never) (know|realize)\b", 0.80),
        (r"(?i)\bnow I (know|understand)\b", 0.82),
        (r"(?i)\baha moment\b", 0.88),
    ],
    SignalType.BLOCKER: [
        # Strong blocker signals
        (r"(?i)\bblocked (by|on)\b", 0.92),
        (r"(?i)\bstuck (on|with)\b", 0.88),
        (r"(?i)\bcan('t| not)\s+.{1,30}\s+because\b", 0.85),
        (r"(?i)\b(this|that) (is )?blocking\b", 0.90),
        # Moderate blocker signals
        (r"(?i)\bissue (with|is)[:\s]", 0.75),
        (r"(?i)\bproblem[:\s]", 0.70),
        (r"(?i)\b(I'm|we're) (having trouble|struggling) with\b", 0.80),
        (r"(?i)\bcan't (figure out|get|make)\b", 0.78),
    ],
    SignalType.RESOLUTION: [
        # Strong resolution signals
        (r"(?i)\b(fixed|resolved|solved) (the|this|that|it)\b", 0.92),
        (r"(?i)\bworkaround[:\s]", 0.88),
        (r"(?i)\bsolution[:\s]", 0.85),
        (r"(?i)\bfigured (it )?out\b", 0.88),
        # Moderate resolution signals
        (r"(?i)\bthat (worked|fixed it)\b", 0.85),
        (r"(?i)\bgot it (working|to work)\b", 0.82),
        (r"(?i)\bthe (fix|solution) (was|is)\b", 0.85),
        (r"(?i)\bfinally got\b", 0.75),
    ],
    SignalType.PREFERENCE: [
        # Strong preference signals
        (r"(?i)\bI (always )?(prefer|like) to\b", 0.88),
        (r"(?i)\bmy preference is\b", 0.90),
        (r"(?i)\bI('d| would) (rather|prefer)\b", 0.88),
        # Moderate preference signals
        (r"(?i)\bI (don't )?like (when|how|it when)\b", 0.75),
        (r"(?i)\bI want (to|it to)\b", 0.70),
        (r"(?i)\bI (need|require)\b", 0.68),
    ],
    SignalType.EXPLICIT: [
        # Explicit capture requests (highest confidence)
        (r"(?i)\bremember (this|that)\b", 0.98),
        (r"(?i)\bsave (this|that)( (for|as))?\b", 0.95),
        (r"(?i)\bnote (that|this)[:\s]?", 0.92),
        (r"(?i)\bfor (future|later) reference\b", 0.90),
        (r"(?i)\bdon't forget\b", 0.88),
        (r"(?i)\bkeep (this )?in mind\b", 0.85),
        (r"(?i)\bimportant[:\s]", 0.75),
    ],
}


class SignalDetector:
    """Detector for capture signals in user prompts.

    Uses pre-compiled regex patterns to identify memorable content
    in user input. Each detected signal includes:
    - Signal type (decision, learning, blocker, etc.)
    - Matched text
    - Confidence score (0.0-1.0)
    - Surrounding context
    - Suggested namespace

    The detector pre-compiles all patterns at instantiation for
    optimal performance during repeated detection calls.

    Example::

        detector = SignalDetector()

        # Detect signals in text
        text = "I decided to use async/await instead of callbacks"
        signals = detector.detect(text)

        # Each signal has type, match, confidence, context
        for s in signals:
            print(f"{s.type.value}: '{s.match}' (conf={s.confidence:.2f})")

    Attributes:
        context_window: Characters of context to extract around matches.
        min_confidence: Minimum confidence to include in results.
    """

    # Class-level compiled patterns cache
    _compiled_patterns: ClassVar[
        dict[SignalType, list[tuple[re.Pattern[str], float]]]
    ] = {}

    def __init__(
        self,
        context_window: int = 100,
        min_confidence: float = 0.0,
    ) -> None:
        """Initialize the signal detector.

        Args:
            context_window: Number of characters to include as context
                around each match (on each side).
            min_confidence: Minimum confidence score to include in results.
                Signals below this threshold are filtered out.
        """
        self.context_window = context_window
        self.min_confidence = min_confidence

        # Compile patterns if not already cached
        if not SignalDetector._compiled_patterns:
            self._compile_patterns()

    @classmethod
    def _compile_patterns(cls) -> None:
        """Compile all regex patterns and cache at class level.

        This is called once per class and cached for all instances.
        Pre-compilation significantly improves detection performance.
        """
        for signal_type, patterns in SIGNAL_PATTERNS.items():
            compiled = []
            for pattern_str, confidence in patterns:
                try:
                    compiled.append((re.compile(pattern_str), confidence))
                except re.error as e:
                    logger.warning(
                        "Failed to compile pattern for %s: %s",
                        signal_type.value,
                        e,
                    )
            cls._compiled_patterns[signal_type] = compiled

        logger.debug(
            "Compiled %d pattern groups",
            len(cls._compiled_patterns),
        )

    def detect(self, text: str) -> list[CaptureSignal]:
        """Detect capture signals in the given text.

        Scans the text for all defined signal patterns and returns
        a list of detected signals, sorted by position in the text.
        Overlapping matches are de-duplicated, keeping the highest
        confidence match.

        Args:
            text: The text to scan for signals.

        Returns:
            List of CaptureSignal objects, sorted by position.
            Empty list if no signals detected or text is too short.

        Example::

            text = "I learned that async/await is cleaner than callbacks"
            signals = detector.detect(text)
            # Returns [CaptureSignal(type=LEARNING, match="I learned that", ...)]
        """
        if not text or len(text) < 5:
            return []

        signals: list[CaptureSignal] = []

        for signal_type, patterns in self._compiled_patterns.items():
            for pattern, base_confidence in patterns:
                for match in pattern.finditer(text):
                    # Extract context around the match
                    context = self._extract_context(text, match.start(), match.end())

                    # Calculate final confidence (may be adjusted based on context)
                    confidence = self.score_confidence(
                        base_confidence,
                        match.group(),
                        context,
                    )

                    if confidence < self.min_confidence:
                        continue

                    signal = CaptureSignal(
                        type=signal_type,
                        match=match.group(),
                        confidence=confidence,
                        context=context,
                        suggested_namespace=signal_type.suggested_namespace,
                        position=match.start(),
                    )
                    signals.append(signal)

        # De-duplicate overlapping signals
        signals = self._deduplicate_signals(signals)

        # Sort by position
        signals.sort(key=lambda s: s.position)

        logger.debug(
            "Detected %d signals in text of length %d", len(signals), len(text)
        )
        return signals

    def _extract_context(self, text: str, start: int, end: int) -> str:
        """Extract context around a match.

        Gets surrounding text within the context window, trying to
        break at word boundaries when possible.

        Args:
            text: The full text.
            start: Start position of the match.
            end: End position of the match.

        Returns:
            Context string including the match and surrounding text.
        """
        # Calculate context bounds
        context_start = max(0, start - self.context_window)
        context_end = min(len(text), end + self.context_window)

        # Try to align to word boundaries
        if context_start > 0:
            # Find the start of the word
            while context_start > 0 and text[context_start - 1].isalnum():
                context_start -= 1
            # Or find next word boundary if in middle of word
            space_pos = text.rfind(" ", 0, start - self.context_window + 10)
            if space_pos > context_start:
                context_start = space_pos + 1

        if context_end < len(text):
            # Find the end of the word
            while context_end < len(text) and text[context_end].isalnum():
                context_end += 1
            # Or find next word boundary
            space_pos = text.find(" ", end + self.context_window - 10)
            if 0 < space_pos < context_end:
                context_end = space_pos

        context = text[context_start:context_end].strip()

        # Add ellipsis if truncated
        if context_start > 0:
            context = "..." + context
        if context_end < len(text):
            context = context + "..."

        return context

    def score_confidence(
        self,
        base_confidence: float,
        match: str,
        context: str,
    ) -> float:
        """Calculate confidence score for a signal.

        Adjusts the base confidence based on:
        - Match length (longer matches = higher confidence)
        - Context quality (complete sentences = higher confidence)
        - Signal strength indicators in context

        Args:
            base_confidence: The base confidence from pattern definition.
            match: The matched text.
            context: The surrounding context.

        Returns:
            Adjusted confidence score between 0.0 and 1.0.
        """
        confidence = base_confidence

        # Adjust for match length (longer = slightly more confident)
        if len(match) > 20:
            confidence = min(1.0, confidence + 0.02)
        elif len(match) < 5:
            confidence = max(0.0, confidence - 0.05)

        # Adjust for context quality
        if context:
            # Complete sentences tend to be more meaningful
            if context.endswith((".", "!", "?")):
                confidence = min(1.0, confidence + 0.02)

            # Short context might indicate noise
            if len(context) < 20:
                confidence = max(0.0, confidence - 0.05)

            # Reinforcing words in context increase confidence
            reinforcers = ["important", "critical", "key", "essential", "must", "need"]
            if any(r in context.lower() for r in reinforcers):
                confidence = min(1.0, confidence + 0.05)

        return round(confidence, 3)

    def _deduplicate_signals(
        self,
        signals: list[CaptureSignal],
    ) -> list[CaptureSignal]:
        """Remove overlapping signals, keeping highest confidence.

        When multiple patterns match overlapping text regions,
        keeps only the highest confidence match.

        Args:
            signals: List of detected signals.

        Returns:
            De-duplicated list of signals.
        """
        if len(signals) <= 1:
            return signals

        # Sort by position for efficient overlap detection
        signals.sort(key=lambda s: s.position)

        result: list[CaptureSignal] = []
        for signal in signals:
            # Check if this signal overlaps with the previous one
            if result:
                prev = result[-1]
                prev_end = prev.position + len(prev.match)

                # If overlapping, keep the higher confidence one
                if signal.position < prev_end:
                    if signal.confidence > prev.confidence:
                        result[-1] = signal
                    continue

            result.append(signal)

        return result

    def classify(self, signal: CaptureSignal) -> str:
        """Get the namespace classification for a signal.

        This is a convenience method that returns the suggested
        namespace for a detected signal. The namespace is already
        available on the signal object.

        Args:
            signal: The signal to classify.

        Returns:
            Suggested namespace string.
        """
        return signal.suggested_namespace

    def detect_all_types(self, text: str) -> dict[SignalType, list[CaptureSignal]]:
        """Detect signals and group by type.

        Convenience method that returns signals organized by their type,
        useful for reporting or analysis.

        Args:
            text: The text to scan.

        Returns:
            Dictionary mapping SignalType to list of signals of that type.
        """
        all_signals = self.detect(text)
        grouped: dict[SignalType, list[CaptureSignal]] = {}

        for signal in all_signals:
            if signal.type not in grouped:
                grouped[signal.type] = []
            grouped[signal.type].append(signal)

        return grouped
