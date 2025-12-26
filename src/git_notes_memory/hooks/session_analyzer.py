"""Session transcript analyzer for uncaptured memory detection.

This module provides the SessionAnalyzer class for parsing and analyzing
session transcripts to detect potentially uncaptured memorable content
at session end.

The analyzer:
1. Parses transcript from file path (supports JSONL and plain text formats)
2. Applies signal detection to identify memorable content
3. Filters out already-captured memories via novelty checking
4. Ranks remaining signals by importance

Example::

    analyzer = SessionAnalyzer()
    uncaptured = analyzer.analyze("/path/to/transcript.jsonl")
    for signal in uncaptured:
        print(f"{signal.type.value}: {signal.match[:50]}...")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from git_notes_memory.hooks.hook_utils import validate_file_path
from git_notes_memory.hooks.models import CaptureSignal
from git_notes_memory.observability import get_logger

if TYPE_CHECKING:
    from git_notes_memory.hooks.novelty_checker import NoveltyChecker
    from git_notes_memory.hooks.signal_detector import SignalDetector

__all__ = ["SessionAnalyzer", "TranscriptContent"]

logger = get_logger(__name__)


@dataclass(frozen=True)
class TranscriptContent:
    """Parsed transcript content.

    Attributes:
        user_messages: List of user message strings.
        assistant_messages: List of assistant message strings.
        raw_content: The full raw transcript content.
        total_turns: Number of conversation turns.
    """

    user_messages: tuple[str, ...]
    assistant_messages: tuple[str, ...]
    raw_content: str
    total_turns: int

    @property
    def all_user_content(self) -> str:
        """Combine all user messages into single string."""
        return "\n\n".join(self.user_messages)


class SessionAnalyzer:
    """Analyzer for detecting uncaptured memories in session transcripts.

    Parses session transcripts and applies signal detection combined with
    novelty checking to identify content that should have been captured
    but wasn't.

    Example::

        analyzer = SessionAnalyzer()

        # Analyze transcript file
        uncaptured = analyzer.analyze("/path/to/transcript.md")

        # Check if there's anything worth prompting about
        if uncaptured:
            print(f"Found {len(uncaptured)} uncaptured memories")

    Attributes:
        min_confidence: Minimum confidence for signal inclusion.
        max_signals: Maximum signals to return.
        novelty_threshold: Minimum novelty score for inclusion.
    """

    # Pattern for extracting user messages from transcript
    # Matches "Human:" or "User:" prefixed blocks
    USER_PATTERN = re.compile(
        r"(?:^|\n)(?:Human|User):\s*(.*?)(?=\n(?:Human|User|Assistant):|$)",
        re.DOTALL | re.IGNORECASE,
    )

    # Pattern for extracting assistant messages from transcript
    # Matches "Assistant:" prefixed blocks
    ASSISTANT_PATTERN = re.compile(
        r"(?:^|\n)Assistant:\s*(.*?)(?=\n(?:Human|User|Assistant):|$)",
        re.DOTALL | re.IGNORECASE,
    )

    def __init__(
        self,
        min_confidence: float = 0.7,
        max_signals: int = 5,
        novelty_threshold: float = 0.3,
        *,
        signal_detector: SignalDetector | None = None,
        novelty_checker: NoveltyChecker | None = None,
    ) -> None:
        """Initialize the session analyzer.

        Args:
            min_confidence: Minimum confidence score for signal inclusion.
            max_signals: Maximum number of signals to return.
            novelty_threshold: Minimum novelty score for inclusion.
            signal_detector: Optional pre-configured SignalDetector.
            novelty_checker: Optional pre-configured NoveltyChecker.
        """
        self.min_confidence = min_confidence
        self.max_signals = max_signals
        self.novelty_threshold = novelty_threshold

        self._signal_detector = signal_detector
        self._novelty_checker = novelty_checker

    def _get_signal_detector(self) -> SignalDetector:
        """Get or create the SignalDetector instance."""
        if self._signal_detector is None:
            from git_notes_memory.hooks.signal_detector import SignalDetector

            self._signal_detector = SignalDetector()
        return self._signal_detector

    def _get_novelty_checker(self) -> NoveltyChecker:
        """Get or create the NoveltyChecker instance."""
        if self._novelty_checker is None:
            from git_notes_memory.hooks.novelty_checker import NoveltyChecker

            self._novelty_checker = NoveltyChecker(
                novelty_threshold=self.novelty_threshold,
            )
        return self._novelty_checker

    def parse_transcript(self, transcript_path: str | Path) -> TranscriptContent | None:
        """Parse a transcript file into structured content.

        Supports both JSONL format (Claude Code transcripts) and plain text format.
        JSONL format: Each line is a JSON object with 'message', 'type', 'userType' fields.
        Plain text format: Messages prefixed with 'Human:', 'User:', or 'Assistant:'.

        Args:
            transcript_path: Path to the transcript file.

        Returns:
            TranscriptContent with parsed messages, or None if file not found
            or path is invalid.

        Note:
            Path validation is performed to prevent path traversal attacks.
            Only absolute paths are accepted, and '..' sequences are rejected.
        """
        try:
            # Validate path for security (prevents path traversal)
            path = validate_file_path(transcript_path, must_exist=False)
        except ValueError as e:
            logger.warning("Invalid transcript path: %s", e)
            return None

        if not path.exists():
            logger.warning("Transcript file not found: %s", path)
            return None

        try:
            raw_content = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to read transcript: %s", e)
            return None

        # Detect format: JSONL if first non-empty line starts with '{'
        lines = raw_content.strip().split("\n")
        first_line = lines[0].strip() if lines else ""
        is_jsonl = first_line.startswith("{")

        if is_jsonl:
            return self._parse_jsonl_transcript(lines, raw_content)
        else:
            return self._parse_plain_text_transcript(raw_content)

    def _parse_jsonl_transcript(
        self, lines: list[str], raw_content: str
    ) -> TranscriptContent:
        """Parse JSONL format transcript (Claude Code format).

        Args:
            lines: Lines from the transcript file.
            raw_content: Full raw content string.

        Returns:
            TranscriptContent with extracted messages.
        """
        user_messages: list[str] = []
        assistant_messages: list[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Skip non-message entries (summaries, snapshots, etc.)
            entry_type = entry.get("type", "")
            if entry_type in ("summary", "snapshot", "isSnapshotUpdate"):
                continue

            # Extract message content
            message = entry.get("message", "")
            if not message:
                continue

            # Handle message as string or structured content
            if isinstance(message, dict):
                # Message might be structured with 'content' field
                content = message.get("content", "")
                if isinstance(content, list):
                    # Claude message format: content is list of {type, text} blocks
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                text_parts.append(text)
                    message = "\n".join(text_parts)
                elif isinstance(content, str):
                    message = content
                else:
                    message = str(message)
            message = str(message).strip()

            if not message:
                continue

            # Classify by userType field
            user_type = entry.get("userType", "").lower()
            if user_type in ("human", "user"):
                user_messages.append(message)
            elif user_type == "assistant":
                assistant_messages.append(message)
            else:
                # Default: treat as assistant if has message but unknown userType
                # This catches tool responses and other content
                if entry_type == "assistant" or "tool" in entry_type.lower():
                    assistant_messages.append(message)

        total_turns = max(len(user_messages), len(assistant_messages))

        logger.debug(
            "Parsed JSONL transcript: %d user, %d assistant messages",
            len(user_messages),
            len(assistant_messages),
        )

        return TranscriptContent(
            user_messages=tuple(user_messages),
            assistant_messages=tuple(assistant_messages),
            raw_content=raw_content,
            total_turns=total_turns,
        )

    def _parse_plain_text_transcript(self, raw_content: str) -> TranscriptContent:
        """Parse plain text format transcript.

        Args:
            raw_content: Full raw content string.

        Returns:
            TranscriptContent with extracted messages.
        """
        # Extract user messages using regex
        user_matches = self.USER_PATTERN.findall(raw_content)
        user_messages = tuple(msg.strip() for msg in user_matches if msg.strip())

        # Extract assistant messages using regex
        assistant_matches = self.ASSISTANT_PATTERN.findall(raw_content)
        assistant_messages = tuple(
            msg.strip() for msg in assistant_matches if msg.strip()
        )

        # Count conversation turns (approximation)
        total_turns = max(len(user_messages), len(assistant_messages))

        return TranscriptContent(
            user_messages=user_messages,
            assistant_messages=assistant_messages,
            raw_content=raw_content,
            total_turns=total_turns,
        )

    def analyze(
        self,
        transcript_path: str | Path,
        *,
        check_novelty: bool = True,
    ) -> list[CaptureSignal]:
        """Analyze transcript for uncaptured memorable content.

        Parses the transcript, detects signals in user messages, and filters
        out already-captured content via novelty checking.

        Args:
            transcript_path: Path to the transcript file.
            check_novelty: Whether to filter by novelty (skip duplicates).

        Returns:
            List of CaptureSignal objects for uncaptured content,
            sorted by confidence (highest first), limited to max_signals.
        """
        transcript = self.parse_transcript(transcript_path)

        if transcript is None:
            logger.debug("No transcript to analyze")
            return []

        if not transcript.user_messages and not transcript.assistant_messages:
            logger.debug("No messages in transcript")
            return []

        # Detect signals in all messages (user and assistant)
        detector = self._get_signal_detector()
        all_signals: list[CaptureSignal] = []

        # Scan user messages
        for message in transcript.user_messages:
            signals = detector.detect(message)
            all_signals.extend(signals)

        # Scan assistant messages (where markers are typically written)
        for message in transcript.assistant_messages:
            signals = detector.detect(message)
            all_signals.extend(signals)

        logger.debug(
            "Detected %d total signals in transcript (user: %d, assistant: %d)",
            len(all_signals),
            len(transcript.user_messages),
            len(transcript.assistant_messages),
        )

        if not all_signals:
            return []

        # Filter by minimum confidence
        filtered_signals = [
            s for s in all_signals if s.confidence >= self.min_confidence
        ]

        logger.debug(
            "After confidence filter (>= %.2f): %d signals",
            self.min_confidence,
            len(filtered_signals),
        )

        # Filter by novelty if enabled
        if check_novelty and filtered_signals:
            checker = self._get_novelty_checker()
            novel_signals = []

            for signal in filtered_signals:
                novelty = checker.check_signal_novelty(signal)
                if novelty.is_novel:
                    novel_signals.append(signal)
                else:
                    logger.debug(
                        "Signal filtered (duplicate): %s... (novelty=%.2f)",
                        signal.match[:30],
                        novelty.novelty_score,
                    )

            filtered_signals = novel_signals
            logger.debug("After novelty filter: %d signals", len(filtered_signals))

        # Sort by confidence (highest first) and limit
        filtered_signals.sort(key=lambda s: s.confidence, reverse=True)
        result = filtered_signals[: self.max_signals]

        logger.debug("Returning %d uncaptured signals", len(result))
        return result

    def analyze_content(
        self,
        content: str,
        *,
        check_novelty: bool = True,
    ) -> list[CaptureSignal]:
        """Analyze raw content string for uncaptured memories.

        Convenience method for analyzing content directly without a file.

        Args:
            content: Raw content string to analyze.
            check_novelty: Whether to filter by novelty.

        Returns:
            List of CaptureSignal objects for uncaptured content.
        """
        if not content.strip():
            return []

        # Detect signals
        detector = self._get_signal_detector()
        signals = detector.detect(content)

        if not signals:
            return []

        # Filter by confidence
        filtered = [s for s in signals if s.confidence >= self.min_confidence]

        # Filter by novelty
        if check_novelty and filtered:
            checker = self._get_novelty_checker()
            filtered = [s for s in filtered if checker.check_signal_novelty(s).is_novel]

        # Sort and limit
        filtered.sort(key=lambda s: s.confidence, reverse=True)
        return filtered[: self.max_signals]

    def has_uncaptured_content(
        self,
        transcript_path: str | Path,
        *,
        check_novelty: bool = True,
    ) -> bool:
        """Quick check if transcript has any uncaptured content.

        Args:
            transcript_path: Path to the transcript file.
            check_novelty: Whether to check novelty.

        Returns:
            True if there's at least one uncaptured signal.
        """
        signals = self.analyze(transcript_path, check_novelty=check_novelty)
        return len(signals) > 0
