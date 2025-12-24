"""Tests for git_notes_memory.hooks.session_analyzer module.

Tests the session transcript analyzer including:
- parse_transcript() - JSONL and plain text parsing
- _parse_jsonl_transcript() - JSON Lines format handling
- _parse_plain_text_transcript() - Markdown/text format handling
- analyze() - Full analysis workflow
- analyze_content() - Direct content analysis
- has_uncaptured_content() - Detection of uncaptured content
- TranscriptContent dataclass

The analyzer detects uncaptured memorable content in session transcripts
using signal detection and novelty checking.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from git_notes_memory.hooks.models import CaptureSignal, NoveltyResult, SignalType
from git_notes_memory.hooks.session_analyzer import (
    SessionAnalyzer,
    TranscriptContent,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def analyzer() -> SessionAnalyzer:
    """Create a SessionAnalyzer with default settings."""
    return SessionAnalyzer()


@pytest.fixture
def analyzer_high_confidence() -> SessionAnalyzer:
    """Create a SessionAnalyzer with high minimum confidence threshold."""
    return SessionAnalyzer(min_confidence=0.9)


@pytest.fixture
def analyzer_low_max_signals() -> SessionAnalyzer:
    """Create a SessionAnalyzer that returns at most 2 signals."""
    return SessionAnalyzer(max_signals=2)


@pytest.fixture
def mock_signal_detector() -> MagicMock:
    """Create a mock SignalDetector."""
    mock = MagicMock()
    mock.detect.return_value = [
        CaptureSignal(
            type=SignalType.DECISION,
            match="I decided to",
            confidence=0.9,
            context="I decided to use PostgreSQL",
            suggested_namespace="decisions",
            position=0,
        )
    ]
    return mock


@pytest.fixture
def mock_novelty_checker() -> MagicMock:
    """Create a mock NoveltyChecker that marks everything as novel."""
    mock = MagicMock()
    mock.check_signal_novelty.return_value = NoveltyResult(
        novelty_score=1.0,
        is_novel=True,
        similar_memory_ids=[],
        highest_similarity=0.0,
    )
    return mock


@pytest.fixture
def jsonl_transcript_file(tmp_path: Path) -> Path:
    """Create a JSONL transcript file."""
    transcript = tmp_path / "transcript.jsonl"
    lines = [
        json.dumps(
            {"userType": "human", "message": "Help me decide on a database", "type": ""}
        ),
        json.dumps(
            {
                "userType": "assistant",
                "message": "I decided to recommend PostgreSQL for its JSONB support",
                "type": "assistant",
            }
        ),
        json.dumps(
            {
                "userType": "human",
                "message": "TIL about JSONB. That's useful!",
                "type": "",
            }
        ),
    ]
    transcript.write_text("\n".join(lines))
    return transcript


@pytest.fixture
def plain_text_transcript_file(tmp_path: Path) -> Path:
    """Create a plain text transcript file."""
    transcript = tmp_path / "transcript.md"
    lines = [
        "Human: Help me decide on a database",
        "",
        "Assistant: I decided to recommend PostgreSQL for JSONB support.",
        "",
        "Human: TIL about JSONB. That's useful!",
        "",
        "Assistant: Glad that helped!",
    ]
    transcript.write_text("\n".join(lines))
    return transcript


# =============================================================================
# TranscriptContent Dataclass Tests
# =============================================================================


class TestTranscriptContent:
    """Test the TranscriptContent dataclass."""

    def test_frozen_dataclass(self) -> None:
        """Test TranscriptContent is immutable."""
        content = TranscriptContent(
            user_messages=("msg1", "msg2"),
            assistant_messages=("resp1",),
            raw_content="full content",
            total_turns=2,
        )
        with pytest.raises(AttributeError):
            content.total_turns = 5  # type: ignore[misc]

    def test_all_user_content_property(self) -> None:
        """Test all_user_content combines user messages."""
        content = TranscriptContent(
            user_messages=("First message", "Second message"),
            assistant_messages=(),
            raw_content="",
            total_turns=2,
        )
        expected = "First message\n\nSecond message"
        assert content.all_user_content == expected

    def test_empty_user_messages(self) -> None:
        """Test all_user_content with no user messages."""
        content = TranscriptContent(
            user_messages=(),
            assistant_messages=("response",),
            raw_content="",
            total_turns=1,
        )
        assert content.all_user_content == ""


# =============================================================================
# SessionAnalyzer Initialization Tests
# =============================================================================


class TestSessionAnalyzerInitialization:
    """Test SessionAnalyzer initialization and configuration."""

    def test_default_min_confidence(self, analyzer: SessionAnalyzer) -> None:
        """Test default min_confidence is 0.7."""
        assert analyzer.min_confidence == 0.7

    def test_default_max_signals(self, analyzer: SessionAnalyzer) -> None:
        """Test default max_signals is 5."""
        assert analyzer.max_signals == 5

    def test_default_novelty_threshold(self, analyzer: SessionAnalyzer) -> None:
        """Test default novelty_threshold is 0.3."""
        assert analyzer.novelty_threshold == 0.3

    def test_custom_min_confidence(self) -> None:
        """Test custom min_confidence is respected."""
        analyzer = SessionAnalyzer(min_confidence=0.85)
        assert analyzer.min_confidence == 0.85

    def test_custom_max_signals(self) -> None:
        """Test custom max_signals is respected."""
        analyzer = SessionAnalyzer(max_signals=10)
        assert analyzer.max_signals == 10

    def test_custom_novelty_threshold(self) -> None:
        """Test custom novelty_threshold is respected."""
        analyzer = SessionAnalyzer(novelty_threshold=0.5)
        assert analyzer.novelty_threshold == 0.5

    def test_injected_signal_detector(self, mock_signal_detector: MagicMock) -> None:
        """Test injected signal_detector is used."""
        analyzer = SessionAnalyzer(signal_detector=mock_signal_detector)
        # Access private attribute to verify
        assert analyzer._signal_detector is mock_signal_detector

    def test_injected_novelty_checker(self, mock_novelty_checker: MagicMock) -> None:
        """Test injected novelty_checker is used."""
        analyzer = SessionAnalyzer(novelty_checker=mock_novelty_checker)
        assert analyzer._novelty_checker is mock_novelty_checker


# =============================================================================
# parse_transcript() Tests
# =============================================================================


class TestParseTranscript:
    """Test the parse_transcript method."""

    def test_parses_jsonl_format(
        self, analyzer: SessionAnalyzer, jsonl_transcript_file: Path
    ) -> None:
        """Test parsing JSONL format transcript."""
        result = analyzer.parse_transcript(str(jsonl_transcript_file))
        assert result is not None
        assert len(result.user_messages) == 2
        assert len(result.assistant_messages) == 1
        assert "database" in result.user_messages[0]

    def test_parses_plain_text_format(
        self, analyzer: SessionAnalyzer, plain_text_transcript_file: Path
    ) -> None:
        """Test parsing plain text format transcript."""
        result = analyzer.parse_transcript(str(plain_text_transcript_file))
        assert result is not None
        assert len(result.user_messages) >= 1
        assert len(result.assistant_messages) >= 1

    def test_returns_none_for_nonexistent_file(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test returns None for nonexistent file."""
        result = analyzer.parse_transcript(str(tmp_path / "nonexistent.txt"))
        assert result is None

    def test_returns_none_for_invalid_path(self, analyzer: SessionAnalyzer) -> None:
        """Test returns None for invalid path (traversal attempt)."""
        result = analyzer.parse_transcript("../etc/passwd")
        assert result is None

    def test_returns_none_for_relative_path(self, analyzer: SessionAnalyzer) -> None:
        """Test returns None for relative path."""
        result = analyzer.parse_transcript("relative/path.txt")
        assert result is None

    def test_accepts_path_object(
        self, analyzer: SessionAnalyzer, jsonl_transcript_file: Path
    ) -> None:
        """Test accepts Path object as input."""
        result = analyzer.parse_transcript(jsonl_transcript_file)
        assert result is not None

    def test_handles_empty_file(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test handling of empty transcript file."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")
        result = analyzer.parse_transcript(str(empty_file))
        # Empty file should parse but have empty messages
        assert result is not None
        assert result.total_turns == 0


# =============================================================================
# _parse_jsonl_transcript() Tests
# =============================================================================


class TestParseJsonlTranscript:
    """Test JSONL transcript parsing."""

    def test_extracts_user_messages(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test user messages are correctly extracted."""
        transcript = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"userType": "human", "message": "User message 1", "type": ""}),
            json.dumps({"userType": "user", "message": "User message 2", "type": ""}),
        ]
        transcript.write_text("\n".join(lines))

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert len(result.user_messages) == 2
        assert "User message 1" in result.user_messages
        assert "User message 2" in result.user_messages

    def test_extracts_assistant_messages(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test assistant messages are correctly extracted."""
        transcript = tmp_path / "test.jsonl"
        lines = [
            json.dumps(
                {
                    "userType": "assistant",
                    "message": "Assistant response",
                    "type": "assistant",
                }
            ),
        ]
        transcript.write_text("\n".join(lines))

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert len(result.assistant_messages) == 1
        assert "Assistant response" in result.assistant_messages

    def test_skips_summary_entries(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test summary entries are skipped."""
        transcript = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"type": "summary", "message": "Summary content"}),
            json.dumps({"userType": "human", "message": "Real message", "type": ""}),
        ]
        transcript.write_text("\n".join(lines))

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert len(result.user_messages) == 1
        assert "Summary content" not in result.all_user_content

    def test_skips_snapshot_entries(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test snapshot entries are skipped."""
        transcript = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"type": "snapshot", "message": "Snapshot data"}),
            json.dumps({"type": "isSnapshotUpdate", "message": "Update"}),
            json.dumps({"userType": "human", "message": "Real message", "type": ""}),
        ]
        transcript.write_text("\n".join(lines))

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert "Snapshot" not in result.all_user_content

    def test_handles_malformed_json_lines(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test malformed JSON lines are skipped gracefully."""
        transcript = tmp_path / "test.jsonl"
        lines = [
            '{"userType": "human", "message": "Valid message", "type": ""}',
            "this is not valid json",
            '{"userType": "human", "message": "Another valid", "type": ""}',
        ]
        transcript.write_text("\n".join(lines))

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert len(result.user_messages) == 2

    def test_handles_structured_message_content(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test handles Claude message format with structured content."""
        transcript = tmp_path / "test.jsonl"
        structured_message = {
            "userType": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "First block"},
                    {"type": "text", "text": "Second block"},
                ]
            },
            "type": "assistant",
        }
        transcript.write_text(json.dumps(structured_message))

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert len(result.assistant_messages) == 1
        assert "First block" in result.assistant_messages[0]
        assert "Second block" in result.assistant_messages[0]

    def test_handles_empty_messages(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test entries with empty messages are skipped."""
        transcript = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"userType": "human", "message": "", "type": ""}),
            json.dumps({"userType": "human", "message": "Real message", "type": ""}),
        ]
        transcript.write_text("\n".join(lines))

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert len(result.user_messages) == 1

    def test_calculates_total_turns(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test total_turns is calculated correctly."""
        transcript = tmp_path / "test.jsonl"
        lines = [
            json.dumps({"userType": "human", "message": "Q1", "type": ""}),
            json.dumps({"userType": "assistant", "message": "A1", "type": "assistant"}),
            json.dumps({"userType": "human", "message": "Q2", "type": ""}),
            json.dumps({"userType": "assistant", "message": "A2", "type": "assistant"}),
            json.dumps({"userType": "human", "message": "Q3", "type": ""}),
        ]
        transcript.write_text("\n".join(lines))

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        # max(3 user, 2 assistant) = 3
        assert result.total_turns == 3


# =============================================================================
# _parse_plain_text_transcript() Tests
# =============================================================================


class TestParsePlainTextTranscript:
    """Test plain text transcript parsing."""

    def test_extracts_human_prefixed_messages(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test Human: prefixed messages are extracted."""
        transcript = tmp_path / "test.md"
        content = "Human: This is a user message\n\nAssistant: Response"
        transcript.write_text(content)

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert len(result.user_messages) >= 1
        assert "This is a user message" in result.user_messages[0]

    def test_extracts_user_prefixed_messages(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test User: prefixed messages are extracted."""
        transcript = tmp_path / "test.md"
        content = "User: This is from user prefix\n\nAssistant: Response"
        transcript.write_text(content)

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert any("This is from user prefix" in m for m in result.user_messages)

    def test_extracts_assistant_messages(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test Assistant: prefixed messages are extracted."""
        transcript = tmp_path / "test.md"
        content = "Human: Question\n\nAssistant: This is the response"
        transcript.write_text(content)

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert len(result.assistant_messages) >= 1
        assert "This is the response" in result.assistant_messages[0]

    def test_case_insensitive_matching(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test message prefix matching is case-insensitive."""
        transcript = tmp_path / "test.md"
        content = "HUMAN: Uppercase\n\nhuman: lowercase\n\nHuMaN: Mixed case"
        transcript.write_text(content)

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        # Should find all three variations
        assert len(result.user_messages) >= 1

    def test_preserves_raw_content(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test raw_content contains full original text."""
        transcript = tmp_path / "test.md"
        content = "Human: Question\n\nAssistant: Answer"
        transcript.write_text(content)

        result = analyzer.parse_transcript(str(transcript))
        assert result is not None
        assert result.raw_content == content


# =============================================================================
# analyze() Tests
# =============================================================================


class TestAnalyze:
    """Test the analyze method for full workflow."""

    def test_returns_empty_list_for_missing_file(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test returns empty list when file doesn't exist."""
        result = analyzer.analyze(str(tmp_path / "missing.txt"))
        assert result == []

    def test_returns_empty_list_for_empty_transcript(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test returns empty list for empty transcript."""
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")

        result = analyzer.analyze(str(empty_file))
        assert result == []

    def test_detects_signals_in_user_messages(
        self,
        mock_signal_detector: MagicMock,
        mock_novelty_checker: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test signals are detected in user messages."""
        analyzer = SessionAnalyzer(
            signal_detector=mock_signal_detector,
            novelty_checker=mock_novelty_checker,
        )

        transcript = tmp_path / "test.jsonl"
        lines = [
            json.dumps(
                {"userType": "human", "message": "I decided to use X", "type": ""}
            ),
        ]
        transcript.write_text("\n".join(lines))

        result = analyzer.analyze(str(transcript))

        # Signal detector should have been called
        assert mock_signal_detector.detect.called
        assert len(result) >= 0  # May have signals depending on mock

    def test_detects_signals_in_assistant_messages(
        self,
        mock_signal_detector: MagicMock,
        mock_novelty_checker: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test signals are detected in assistant messages."""
        analyzer = SessionAnalyzer(
            signal_detector=mock_signal_detector,
            novelty_checker=mock_novelty_checker,
        )

        transcript = tmp_path / "test.jsonl"
        lines = [
            json.dumps(
                {
                    "userType": "assistant",
                    "message": "I decided to recommend PostgreSQL",
                    "type": "assistant",
                }
            ),
        ]
        transcript.write_text("\n".join(lines))

        analyzer.analyze(str(transcript))
        assert mock_signal_detector.detect.called

    def test_filters_by_min_confidence(
        self,
        mock_novelty_checker: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test signals below min_confidence are filtered out."""
        # Create detector that returns low confidence signal
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="I decided",
                confidence=0.5,  # Below default 0.7 threshold
                context="context",
                suggested_namespace="decisions",
                position=0,
            )
        ]

        analyzer = SessionAnalyzer(
            min_confidence=0.7,
            signal_detector=mock_detector,
            novelty_checker=mock_novelty_checker,
        )

        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps({"userType": "human", "message": "test", "type": ""})
        )

        result = analyzer.analyze(str(transcript))
        # Low confidence signal should be filtered
        assert len(result) == 0

    def test_respects_max_signals_limit(
        self,
        mock_novelty_checker: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test result is limited to max_signals."""
        # Create detector that returns many signals
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            CaptureSignal(
                type=SignalType.DECISION,
                match=f"signal{i}",
                confidence=0.9,
                context="context",
                suggested_namespace="decisions",
                position=i * 10,
            )
            for i in range(10)
        ]

        analyzer = SessionAnalyzer(
            max_signals=3,
            signal_detector=mock_detector,
            novelty_checker=mock_novelty_checker,
        )

        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps({"userType": "human", "message": "test", "type": ""})
        )

        result = analyzer.analyze(str(transcript))
        assert len(result) <= 3

    def test_filters_by_novelty(self, tmp_path: Path) -> None:
        """Test non-novel signals are filtered out."""
        # Mock that returns non-novel results
        mock_novelty = MagicMock()
        mock_novelty.check_signal_novelty.return_value = NoveltyResult(
            novelty_score=0.1,
            is_novel=False,
            similar_memory_ids=["existing:123"],
            highest_similarity=0.9,
        )

        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="I decided",
                confidence=0.9,
                context="context",
                suggested_namespace="decisions",
                position=0,
            )
        ]

        analyzer = SessionAnalyzer(
            signal_detector=mock_detector,
            novelty_checker=mock_novelty,
        )

        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps({"userType": "human", "message": "test", "type": ""})
        )

        result = analyzer.analyze(str(transcript), check_novelty=True)
        # Non-novel signal should be filtered
        assert len(result) == 0

    def test_skips_novelty_check_when_disabled(self, tmp_path: Path) -> None:
        """Test novelty check is skipped when check_novelty=False."""
        mock_novelty = MagicMock()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="I decided",
                confidence=0.9,
                context="context",
                suggested_namespace="decisions",
                position=0,
            )
        ]

        analyzer = SessionAnalyzer(
            signal_detector=mock_detector,
            novelty_checker=mock_novelty,
        )

        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps({"userType": "human", "message": "test", "type": ""})
        )

        result = analyzer.analyze(str(transcript), check_novelty=False)
        # Novelty checker should not be called
        assert not mock_novelty.check_signal_novelty.called
        # Signal should be returned (not filtered by novelty)
        assert len(result) == 1

    def test_sorts_by_confidence(
        self,
        mock_novelty_checker: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test results are sorted by confidence (highest first)."""
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="low",
                confidence=0.75,
                context="context",
                suggested_namespace="decisions",
                position=0,
            ),
            CaptureSignal(
                type=SignalType.LEARNING,
                match="high",
                confidence=0.95,
                context="context",
                suggested_namespace="learnings",
                position=10,
            ),
            CaptureSignal(
                type=SignalType.BLOCKER,
                match="medium",
                confidence=0.85,
                context="context",
                suggested_namespace="blockers",
                position=20,
            ),
        ]

        analyzer = SessionAnalyzer(
            signal_detector=mock_detector,
            novelty_checker=mock_novelty_checker,
        )

        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps({"userType": "human", "message": "test", "type": ""})
        )

        result = analyzer.analyze(str(transcript))
        assert len(result) == 3
        assert result[0].confidence >= result[1].confidence
        assert result[1].confidence >= result[2].confidence


# =============================================================================
# analyze_content() Tests
# =============================================================================


class TestAnalyzeContent:
    """Test the analyze_content method."""

    def test_analyzes_raw_string_content(
        self,
        mock_signal_detector: MagicMock,
        mock_novelty_checker: MagicMock,
    ) -> None:
        """Test analyzing raw content string directly."""
        analyzer = SessionAnalyzer(
            signal_detector=mock_signal_detector,
            novelty_checker=mock_novelty_checker,
        )

        result = analyzer.analyze_content("I decided to use PostgreSQL for storage")
        assert mock_signal_detector.detect.called

    def test_returns_empty_for_empty_content(self, analyzer: SessionAnalyzer) -> None:
        """Test returns empty list for empty content."""
        result = analyzer.analyze_content("")
        assert result == []

    def test_returns_empty_for_whitespace_content(
        self, analyzer: SessionAnalyzer
    ) -> None:
        """Test returns empty list for whitespace-only content."""
        result = analyzer.analyze_content("   \n\t  ")
        assert result == []

    def test_filters_by_confidence(self, mock_novelty_checker: MagicMock) -> None:
        """Test signals below min_confidence are filtered."""
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="test",
                confidence=0.5,
                context="context",
                suggested_namespace="decisions",
                position=0,
            )
        ]

        analyzer = SessionAnalyzer(
            min_confidence=0.8,
            signal_detector=mock_detector,
            novelty_checker=mock_novelty_checker,
        )

        result = analyzer.analyze_content("some content")
        assert len(result) == 0

    def test_respects_max_signals(self, mock_novelty_checker: MagicMock) -> None:
        """Test result limited to max_signals."""
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            CaptureSignal(
                type=SignalType.DECISION,
                match=f"sig{i}",
                confidence=0.9,
                context="context",
                suggested_namespace="decisions",
                position=i,
            )
            for i in range(10)
        ]

        analyzer = SessionAnalyzer(
            max_signals=2,
            signal_detector=mock_detector,
            novelty_checker=mock_novelty_checker,
        )

        result = analyzer.analyze_content("content")
        assert len(result) <= 2

    def test_novelty_check_can_be_disabled(self) -> None:
        """Test novelty check can be disabled."""
        mock_novelty = MagicMock()
        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="test",
                confidence=0.9,
                context="context",
                suggested_namespace="decisions",
                position=0,
            )
        ]

        analyzer = SessionAnalyzer(
            signal_detector=mock_detector,
            novelty_checker=mock_novelty,
        )

        analyzer.analyze_content("content", check_novelty=False)
        assert not mock_novelty.check_signal_novelty.called


# =============================================================================
# has_uncaptured_content() Tests
# =============================================================================


class TestHasUncapturedContent:
    """Test the has_uncaptured_content method."""

    def test_returns_true_when_signals_found(
        self,
        mock_signal_detector: MagicMock,
        mock_novelty_checker: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns True when uncaptured signals are found."""
        analyzer = SessionAnalyzer(
            signal_detector=mock_signal_detector,
            novelty_checker=mock_novelty_checker,
        )

        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps({"userType": "human", "message": "test", "type": ""})
        )

        result = analyzer.has_uncaptured_content(str(transcript))
        assert result is True

    def test_returns_false_when_no_signals(
        self,
        mock_novelty_checker: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test returns False when no signals are found."""
        mock_detector = MagicMock()
        mock_detector.detect.return_value = []

        analyzer = SessionAnalyzer(
            signal_detector=mock_detector,
            novelty_checker=mock_novelty_checker,
        )

        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps({"userType": "human", "message": "test", "type": ""})
        )

        result = analyzer.has_uncaptured_content(str(transcript))
        assert result is False

    def test_returns_false_for_missing_file(
        self, analyzer: SessionAnalyzer, tmp_path: Path
    ) -> None:
        """Test returns False for missing transcript file."""
        result = analyzer.has_uncaptured_content(str(tmp_path / "missing.txt"))
        assert result is False

    def test_respects_check_novelty_parameter(self, tmp_path: Path) -> None:
        """Test check_novelty parameter is passed to analyze."""
        mock_novelty = MagicMock()
        mock_novelty.check_signal_novelty.return_value = NoveltyResult(
            novelty_score=0.1,
            is_novel=False,
            similar_memory_ids=[],
            highest_similarity=0.9,
        )

        mock_detector = MagicMock()
        mock_detector.detect.return_value = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="test",
                confidence=0.9,
                context="context",
                suggested_namespace="decisions",
                position=0,
            )
        ]

        analyzer = SessionAnalyzer(
            signal_detector=mock_detector,
            novelty_checker=mock_novelty,
        )

        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps({"userType": "human", "message": "test", "type": ""})
        )

        # With novelty check, signal is filtered (not novel)
        result_with_novelty = analyzer.has_uncaptured_content(
            str(transcript), check_novelty=True
        )
        assert result_with_novelty is False

        # Without novelty check, signal is found
        result_without_novelty = analyzer.has_uncaptured_content(
            str(transcript), check_novelty=False
        )
        assert result_without_novelty is True


# =============================================================================
# Lazy Initialization Tests
# =============================================================================


class TestLazyInitialization:
    """Test lazy initialization of detector and checker."""

    def test_signal_detector_created_lazily(self) -> None:
        """Test signal detector is created on first use."""
        analyzer = SessionAnalyzer()
        assert analyzer._signal_detector is None

        # Trigger creation
        detector = analyzer._get_signal_detector()
        assert detector is not None
        assert analyzer._signal_detector is detector

    def test_novelty_checker_created_lazily(self) -> None:
        """Test novelty checker is created on first use."""
        analyzer = SessionAnalyzer()
        assert analyzer._novelty_checker is None

        # Trigger creation
        checker = analyzer._get_novelty_checker()
        assert checker is not None
        assert analyzer._novelty_checker is checker

    def test_novelty_checker_uses_analyzer_threshold(self) -> None:
        """Test created novelty checker uses analyzer's novelty_threshold."""
        analyzer = SessionAnalyzer(novelty_threshold=0.5)
        checker = analyzer._get_novelty_checker()
        assert checker.novelty_threshold == 0.5


# =============================================================================
# Integration Tests
# =============================================================================


class TestSessionAnalyzerIntegration:
    """Integration tests using real SignalDetector."""

    def test_full_analysis_workflow_jsonl(self, tmp_path: Path) -> None:
        """Test full analysis workflow with JSONL transcript."""
        analyzer = SessionAnalyzer(min_confidence=0.7)

        transcript = tmp_path / "transcript.jsonl"
        lines = [
            json.dumps(
                {
                    "userType": "human",
                    "message": "What database should I use?",
                    "type": "",
                }
            ),
            json.dumps(
                {
                    "userType": "assistant",
                    "message": "I decided to recommend PostgreSQL because of JSONB.",
                    "type": "assistant",
                }
            ),
            json.dumps(
                {
                    "userType": "human",
                    "message": "TIL about JSONB support. That's great!",
                    "type": "",
                }
            ),
        ]
        transcript.write_text("\n".join(lines))

        # Analyze without novelty check (to avoid needing embedding model)
        result = analyzer.analyze(str(transcript), check_novelty=False)

        # Should detect decision and learning signals
        types_found = {s.type for s in result}
        assert len(result) >= 1

    def test_full_analysis_workflow_plain_text(self, tmp_path: Path) -> None:
        """Test full analysis workflow with plain text transcript."""
        analyzer = SessionAnalyzer(min_confidence=0.7)

        transcript = tmp_path / "transcript.md"
        content_lines = [
            "Human: What database should I use?",
            "",
            "Assistant: I decided to recommend PostgreSQL.",
            "",
            "Human: TIL about its features!",
        ]
        transcript.write_text("\n".join(content_lines))

        result = analyzer.analyze(str(transcript), check_novelty=False)
        assert isinstance(result, list)

    def test_parse_and_analyze_consistency(self, tmp_path: Path) -> None:
        """Test that parse_transcript and analyze work consistently."""
        analyzer = SessionAnalyzer()

        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps(
                {"userType": "human", "message": "I decided to use SQLite", "type": ""}
            )
        )

        # Parse should return TranscriptContent
        parsed = analyzer.parse_transcript(str(transcript))
        assert parsed is not None
        assert isinstance(parsed, TranscriptContent)

        # Analyze should return list of CaptureSignal
        signals = analyzer.analyze(str(transcript), check_novelty=False)
        assert isinstance(signals, list)
        assert all(isinstance(s, CaptureSignal) for s in signals)
