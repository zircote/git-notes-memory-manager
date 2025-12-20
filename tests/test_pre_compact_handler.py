"""Tests for git_notes_memory.hooks.pre_compact_handler module.

Tests the PreCompact hook handler including:
- Input validation
- Transcript analysis integration
- Memory capture integration
- Error handling
- User feedback via stderr
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from git_notes_memory.hooks.hook_utils import read_json_input
from git_notes_memory.hooks.models import CaptureSignal, SignalType
from git_notes_memory.hooks.pre_compact_handler import (
    DEFAULT_TIMEOUT,
    _capture_memory,
    _extract_summary,
    _report_captures,
    _report_suggestions,
    main,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_hook_config() -> MagicMock:
    """Create mock HookConfig."""
    config = MagicMock()
    config.enabled = True
    config.debug = False
    config.pre_compact_enabled = True
    config.pre_compact_auto_capture = True
    config.pre_compact_prompt_first = False
    config.pre_compact_min_confidence = 0.85
    config.pre_compact_max_captures = 3
    config.pre_compact_timeout = 15
    return config


@pytest.fixture
def sample_signal() -> CaptureSignal:
    """Create a sample capture signal."""
    return CaptureSignal(
        type=SignalType.DECISION,
        match="We decided to use PostgreSQL for persistence",
        confidence=0.9,
        context="We decided to use PostgreSQL for persistence because of ACID compliance",
        suggested_namespace="decisions",
        position=0,
    )


@pytest.fixture
def sample_signals() -> list[CaptureSignal]:
    """Create multiple sample signals."""
    return [
        CaptureSignal(
            type=SignalType.DECISION,
            match="We decided to use PostgreSQL",
            confidence=0.9,
            context="We decided to use PostgreSQL for ACID compliance",
            suggested_namespace="decisions",
            position=0,
        ),
        CaptureSignal(
            type=SignalType.LEARNING,
            match="TIL that pytest fixtures can have scope",
            confidence=0.85,
            context="TIL that pytest fixtures can have scope='module'",
            suggested_namespace="learnings",
            position=100,
        ),
    ]


@pytest.fixture
def sample_input_data(tmp_path: Path) -> dict[str, Any]:
    """Create sample input data with transcript file."""
    transcript_file = tmp_path / "transcript.md"
    transcript_file.write_text(
        "Human: We decided to use PostgreSQL for the database.\n\n"
        "Assistant: That's a good choice for ACID compliance.\n"
    )

    return {
        "trigger": "auto",
        "transcript_path": str(transcript_file),
    }


@dataclass(frozen=True)
class MockMemory:
    """Mock Memory for testing."""

    id: str
    summary: str


@dataclass(frozen=True)
class MockCaptureResult:
    """Mock CaptureResult for testing."""

    success: bool
    memory: MockMemory | None = None
    warning: str | None = None


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Test module constants."""

    def test_default_timeout(self) -> None:
        """Test default timeout is 15 seconds."""
        assert DEFAULT_TIMEOUT == 15


# =============================================================================
# Input Reading Tests
# =============================================================================


class TestReadInput:
    """Test read_json_input function (from hook_utils)."""

    def test_valid_json_input(self) -> None:
        """Test reading valid JSON input."""
        input_data = '{"trigger": "auto", "transcript_path": "/path/to/file"}'
        with patch("sys.stdin", StringIO(input_data)):
            result = read_json_input()
            assert result == {"trigger": "auto", "transcript_path": "/path/to/file"}

    def test_empty_input_raises(self) -> None:
        """Test that empty input raises ValueError."""
        with patch("sys.stdin", StringIO("")):
            with pytest.raises(ValueError, match="Empty input"):
                read_json_input()

    def test_invalid_json_raises(self) -> None:
        """Test that invalid JSON raises JSONDecodeError."""
        with patch("sys.stdin", StringIO("not valid json")):
            with pytest.raises(json.JSONDecodeError):
                read_json_input()

    def test_non_dict_raises(self) -> None:
        """Test that non-dict JSON raises ValueError."""
        with patch("sys.stdin", StringIO('["a", "b"]')):
            with pytest.raises(ValueError, match="Expected JSON object"):
                read_json_input()


# =============================================================================
# Summary Extraction Tests
# =============================================================================


class TestExtractSummary:
    """Test _extract_summary function."""

    def test_basic_summary(self, sample_signal: CaptureSignal) -> None:
        """Test basic summary extraction."""
        summary = _extract_summary(sample_signal)
        assert "PostgreSQL" in summary
        assert len(summary) <= 100

    def test_truncates_long_text(self) -> None:
        """Test that long text is truncated."""
        long_match = "x" * 150
        signal = CaptureSignal(
            type=SignalType.DECISION,
            match=long_match,
            confidence=0.9,
            context=None,
            suggested_namespace="decisions",
            position=0,
        )

        summary = _extract_summary(signal)
        assert len(summary) <= 100
        assert summary.endswith("...")

    def test_uses_context_for_short_match(self) -> None:
        """Test that context is used when match is short."""
        signal = CaptureSignal(
            type=SignalType.DECISION,
            match="short",
            confidence=0.9,
            context="This is a longer context with more useful information",
            suggested_namespace="decisions",
            position=0,
        )

        summary = _extract_summary(signal)
        assert "longer context" in summary


# =============================================================================
# Memory Capture Tests
# =============================================================================


class TestCaptureMemory:
    """Test _capture_memory function."""

    def test_successful_capture(self, sample_signal: CaptureSignal) -> None:
        """Test successful memory capture."""
        mock_capture = MagicMock()
        mock_memory = MockMemory(id="decisions:abc123:0", summary="Test summary")
        mock_result = MockCaptureResult(success=True, memory=mock_memory)
        mock_capture.capture.return_value = mock_result

        with patch(
            "git_notes_memory.capture.get_default_service",
            return_value=mock_capture,
        ):
            result = _capture_memory(sample_signal, "decisions")

        assert result["success"] is True
        assert result["memory_id"] == "decisions:abc123:0"
        assert result["summary"] == "Test summary"

    def test_capture_failure(self, sample_signal: CaptureSignal) -> None:
        """Test capture failure handling."""
        mock_capture = MagicMock()
        mock_result = MockCaptureResult(success=False, warning="Duplicate content")
        mock_capture.capture.return_value = mock_result

        with patch(
            "git_notes_memory.capture.get_default_service",
            return_value=mock_capture,
        ):
            result = _capture_memory(sample_signal, "decisions")

        assert result["success"] is False
        assert "Duplicate content" in result["error"]

    def test_import_error_handling(self, sample_signal: CaptureSignal) -> None:
        """Test ImportError handling."""
        with patch(
            "git_notes_memory.capture.get_default_service",
            side_effect=ImportError("Module not found"),
        ):
            result = _capture_memory(sample_signal, "decisions")

        assert result["success"] is False
        assert "not installed" in result["error"]

    def test_exception_handling(self, sample_signal: CaptureSignal) -> None:
        """Test general exception handling."""
        mock_capture = MagicMock()
        mock_capture.capture.side_effect = RuntimeError("Unexpected error")

        with patch(
            "git_notes_memory.capture.get_default_service",
            return_value=mock_capture,
        ):
            result = _capture_memory(sample_signal, "decisions")

        assert result["success"] is False
        assert "Unexpected error" in result["error"]


# =============================================================================
# Report Captures Tests
# =============================================================================


class TestReportCaptures:
    """Test _report_captures function."""

    def test_reports_successful_captures(self, capsys: pytest.CaptureFixture) -> None:
        """Test reporting of successful captures."""
        captured = [
            {"success": True, "memory_id": "abc123", "summary": "Test memory 1"},
            {"success": True, "memory_id": "def456", "summary": "Test memory 2"},
        ]

        _report_captures(captured)

        stderr = capsys.readouterr().err
        assert "Auto-captured 2 memories" in stderr
        assert "Test memory 1" in stderr
        assert "Test memory 2" in stderr

    def test_single_capture_grammar(self, capsys: pytest.CaptureFixture) -> None:
        """Test singular grammar for single capture."""
        captured = [
            {"success": True, "memory_id": "abc123", "summary": "Test memory"},
        ]

        _report_captures(captured)

        stderr = capsys.readouterr().err
        assert "1 memory" in stderr
        assert "memories" not in stderr

    def test_no_output_for_failures(self, capsys: pytest.CaptureFixture) -> None:
        """Test no output when all captures failed."""
        captured = [
            {"success": False, "error": "Failed"},
        ]

        _report_captures(captured)

        stderr = capsys.readouterr().err
        assert stderr == ""

    def test_no_output_for_empty_list(self, capsys: pytest.CaptureFixture) -> None:
        """Test no output for empty list."""
        _report_captures([])

        stderr = capsys.readouterr().err
        assert stderr == ""


# =============================================================================
# Report Suggestions Tests (Suggestion Mode)
# =============================================================================


class TestReportSuggestions:
    """Test _report_suggestions function (suggestion mode)."""

    def test_reports_suggestions(
        self,
        sample_signals: list[CaptureSignal],
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test reporting of suggested captures."""
        _report_suggestions(sample_signals)

        stderr = capsys.readouterr().err
        assert "Found 2 memories" in stderr
        assert "Suggestion mode" in stderr
        assert "[decisions]" in stderr
        assert "[learnings]" in stderr
        # Should show confidence percentages
        assert "90%" in stderr
        assert "85%" in stderr

    def test_single_suggestion_grammar(
        self,
        sample_signal: CaptureSignal,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test singular grammar for single suggestion."""
        _report_suggestions([sample_signal])

        stderr = capsys.readouterr().err
        assert "1 memory" in stderr
        assert "memories" not in stderr

    def test_no_output_for_empty_list(self, capsys: pytest.CaptureFixture) -> None:
        """Test no output for empty signal list."""
        _report_suggestions([])

        stderr = capsys.readouterr().err
        assert stderr == ""

    def test_includes_namespace_and_confidence(
        self,
        sample_signal: CaptureSignal,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test that output includes namespace and confidence."""
        _report_suggestions([sample_signal])

        stderr = capsys.readouterr().err
        assert "[decisions]" in stderr
        assert "(90%)" in stderr
        assert "PostgreSQL" in stderr


# =============================================================================
# Main Function Tests
# =============================================================================


class TestMain:
    """Test main function integration."""

    def test_hooks_disabled(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when hooks are disabled globally."""
        mock_hook_config.enabled = False

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}

    def test_pre_compact_disabled(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when PreCompact hook is specifically disabled."""
        mock_hook_config.pre_compact_enabled = False

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}

    def test_no_transcript_path(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when no transcript_path is provided."""
        input_data = json.dumps({"trigger": "auto"})

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}

    def test_transcript_not_found(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when transcript file doesn't exist."""
        input_data = json.dumps(
            {
                "trigger": "auto",
                "transcript_path": "/nonexistent/path.md",
            }
        )

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}

    def test_auto_capture_disabled(
        self,
        mock_hook_config: MagicMock,
        sample_input_data: dict[str, Any],
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when auto-capture is disabled."""
        mock_hook_config.pre_compact_auto_capture = False
        input_data = json.dumps(sample_input_data)

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}

    def test_no_signals_found(
        self,
        mock_hook_config: MagicMock,
        sample_input_data: dict[str, Any],
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when no signals are found in transcript."""
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = []
        input_data = json.dumps(sample_input_data)

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            patch(
                "git_notes_memory.hooks.pre_compact_handler.SessionAnalyzer",
                return_value=mock_analyzer,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}

    def test_successful_capture(
        self,
        mock_hook_config: MagicMock,
        sample_input_data: dict[str, Any],
        sample_signals: list[CaptureSignal],
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test successful signal capture."""
        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = sample_signals

        mock_capture = MagicMock()
        mock_memory = MockMemory(id="decisions:abc123:0", summary="Test summary")
        mock_result = MockCaptureResult(success=True, memory=mock_memory)
        mock_capture.capture.return_value = mock_result

        input_data = json.dumps(sample_input_data)

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            patch(
                "git_notes_memory.hooks.pre_compact_handler.SessionAnalyzer",
                return_value=mock_analyzer,
            ),
            patch(
                "git_notes_memory.capture.get_default_service",
                return_value=mock_capture,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}  # PreCompact is side-effects only

        # Should have reported captures to stderr
        assert "Auto-captured" in captured.err

    def test_json_decode_error_graceful(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test graceful handling of JSON decode errors."""
        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO("not valid json")),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}

    def test_exception_graceful_handling(
        self,
        mock_hook_config: MagicMock,
        sample_input_data: dict[str, Any],
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test graceful handling of unexpected exceptions."""
        input_data = json.dumps(sample_input_data)

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            patch(
                "git_notes_memory.hooks.pre_compact_handler.SessionAnalyzer",
                side_effect=RuntimeError("Unexpected error"),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}

    def test_suggestion_mode_prompt_first(
        self,
        mock_hook_config: MagicMock,
        sample_input_data: dict[str, Any],
        sample_signals: list[CaptureSignal],
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test suggestion mode (HOOK_PRE_COMPACT_PROMPT_FIRST=true)."""
        # Enable suggestion mode
        mock_hook_config.pre_compact_prompt_first = True

        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = sample_signals

        mock_capture = MagicMock()

        input_data = json.dumps(sample_input_data)

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            patch(
                "git_notes_memory.hooks.pre_compact_handler.SessionAnalyzer",
                return_value=mock_analyzer,
            ),
            patch(
                "git_notes_memory.capture.get_default_service",
                return_value=mock_capture,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {}  # PreCompact is side-effects only

        # Should show suggestions, NOT auto-captured
        assert "Found 2 memories" in captured.err
        assert "Suggestion mode" in captured.err
        assert "Auto-captured" not in captured.err

        # Capture should NOT have been called
        mock_capture.capture.assert_not_called()

    def test_suggestion_mode_does_not_capture(
        self,
        mock_hook_config: MagicMock,
        sample_input_data: dict[str, Any],
        sample_signals: list[CaptureSignal],
    ) -> None:
        """Test that suggestion mode does not call CaptureService."""
        mock_hook_config.pre_compact_prompt_first = True

        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = sample_signals

        mock_capture = MagicMock()

        input_data = json.dumps(sample_input_data)

        with (
            patch(
                "git_notes_memory.hooks.pre_compact_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            patch(
                "git_notes_memory.hooks.pre_compact_handler.SessionAnalyzer",
                return_value=mock_analyzer,
            ),
            patch(
                "git_notes_memory.capture.get_default_service",
                return_value=mock_capture,
            ),
            pytest.raises(SystemExit),
        ):
            main()

        # Capture should NOT have been called in suggestion mode
        mock_capture.capture.assert_not_called()
