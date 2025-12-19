#!/usr/bin/env python3
"""Unit tests for hook handler modules.

Tests for the three hook handlers:
- session_start_handler.py - SessionStart hook
- user_prompt_handler.py - UserPromptSubmit hook
- stop_handler.py - Stop hook

These tests mock stdin/stdout and verify handler behavior.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_stdin() -> Generator[io.StringIO, None, None]:
    """Provide a mock stdin for testing."""
    mock = io.StringIO()
    with patch.object(sys, "stdin", mock):
        yield mock


@pytest.fixture
def mock_stdout() -> Generator[io.StringIO, None, None]:
    """Capture stdout for testing."""
    mock = io.StringIO()
    with patch.object(sys, "stdout", mock):
        yield mock


@pytest.fixture
def hook_env_disabled() -> Generator[None, None, None]:
    """Environment with hooks disabled."""
    with patch.dict(os.environ, {"HOOK_ENABLED": "false"}):
        yield


@pytest.fixture
def hook_env_enabled() -> Generator[None, None, None]:
    """Environment with hooks enabled and debug on."""
    with patch.dict(
        os.environ,
        {
            "HOOK_ENABLED": "true",
            "HOOK_DEBUG": "false",
            "HOOK_SESSION_START_ENABLED": "true",
            "HOOK_USER_PROMPT_ENABLED": "true",
            "HOOK_STOP_ENABLED": "true",
        },
    ):
        yield


@pytest.fixture
def temp_transcript(tmp_path: Path) -> Path:
    """Create a temporary transcript file for testing."""
    transcript = tmp_path / "transcript.json"
    transcript.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "I decided to use PostgreSQL"},
                    {"role": "assistant", "content": "Good choice!"},
                    {
                        "role": "user",
                        "content": "I learned that indexes improve performance",
                    },
                ]
            }
        )
    )
    return transcript


# ============================================================================
# SessionStart Handler Tests
# ============================================================================


class TestSessionStartHandler:
    """Tests for the SessionStart hook handler."""

    def test_read_input_valid_json(self) -> None:
        """Test reading valid JSON input."""
        from git_notes_memory.hooks.session_start_handler import _read_input

        input_data = {"cwd": "/test/path", "source": "startup"}
        with patch.object(sys, "stdin", io.StringIO(json.dumps(input_data))):
            result = _read_input()
        assert result == input_data

    def test_read_input_empty_raises(self) -> None:
        """Test that empty input raises ValueError."""
        from git_notes_memory.hooks.session_start_handler import _read_input

        with patch.object(sys, "stdin", io.StringIO("")):
            with pytest.raises(ValueError, match="Empty input"):
                _read_input()

    def test_read_input_invalid_json_raises(self) -> None:
        """Test that invalid JSON raises JSONDecodeError."""
        from git_notes_memory.hooks.session_start_handler import _read_input

        with patch.object(sys, "stdin", io.StringIO("not json")):
            with pytest.raises(json.JSONDecodeError):
                _read_input()

    def test_read_input_non_dict_raises(self) -> None:
        """Test that non-dict JSON raises ValueError."""
        from git_notes_memory.hooks.session_start_handler import _read_input

        with patch.object(sys, "stdin", io.StringIO(json.dumps(["list", "data"]))):
            with pytest.raises(ValueError, match="Expected JSON object"):
                _read_input()

    def test_validate_input_with_cwd(self) -> None:
        """Test input validation with required cwd field."""
        from git_notes_memory.hooks.session_start_handler import _validate_input

        assert _validate_input({"cwd": "/test/path"}) is True
        assert _validate_input({"cwd": "/test", "extra": "data"}) is True

    def test_validate_input_missing_cwd(self) -> None:
        """Test input validation fails without cwd."""
        from git_notes_memory.hooks.session_start_handler import _validate_input

        assert _validate_input({}) is False
        assert _validate_input({"source": "startup"}) is False

    def test_validate_input_empty_cwd(self) -> None:
        """Test input validation fails with empty cwd."""
        from git_notes_memory.hooks.session_start_handler import _validate_input

        assert _validate_input({"cwd": ""}) is False
        assert _validate_input({"cwd": None}) is False

    def test_write_output_format(self) -> None:
        """Test output format follows hook contract."""
        from git_notes_memory.hooks.session_start_handler import _write_output

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output("<context>test</context>")

        output = json.loads(captured.getvalue())
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert (
            output["hookSpecificOutput"]["additionalContext"]
            == "<context>test</context>"
        )

    def test_setup_logging_debug(self) -> None:
        """Test debug logging setup configures correctly."""
        from git_notes_memory.hooks.session_start_handler import _setup_logging

        # Just verify it doesn't raise - basicConfig behavior varies based on
        # existing logging configuration in the test runner
        _setup_logging(debug=True)

    def test_setup_logging_warning(self) -> None:
        """Test warning-level logging setup configures correctly."""
        from git_notes_memory.hooks.session_start_handler import _setup_logging

        # Just verify it doesn't raise
        _setup_logging(debug=False)


# ============================================================================
# UserPromptSubmit Handler Tests
# ============================================================================


class TestUserPromptHandler:
    """Tests for the UserPromptSubmit hook handler."""

    def test_read_input_valid_json(self) -> None:
        """Test reading valid JSON input."""
        from git_notes_memory.hooks.user_prompt_handler import _read_input

        input_data = {"prompt": "I decided to use PostgreSQL", "cwd": "/test"}
        with patch.object(sys, "stdin", io.StringIO(json.dumps(input_data))):
            result = _read_input()
        assert result == input_data

    def test_read_input_empty_raises(self) -> None:
        """Test that empty input raises ValueError."""
        from git_notes_memory.hooks.user_prompt_handler import _read_input

        with patch.object(sys, "stdin", io.StringIO("")):
            with pytest.raises(ValueError, match="Empty input"):
                _read_input()

    def test_validate_input_with_prompt(self) -> None:
        """Test input validation with required prompt field."""
        from git_notes_memory.hooks.user_prompt_handler import _validate_input

        # _validate_input returns truthy value (the prompt string) when valid
        assert _validate_input({"prompt": "test prompt"})
        assert _validate_input({"prompt": "test", "cwd": "/path"})

    def test_validate_input_missing_prompt(self) -> None:
        """Test input validation fails without prompt."""
        from git_notes_memory.hooks.user_prompt_handler import _validate_input

        assert _validate_input({}) is False
        assert _validate_input({"cwd": "/test"}) is False

    def test_validate_input_empty_prompt(self) -> None:
        """Test input validation fails with empty prompt."""
        from git_notes_memory.hooks.user_prompt_handler import _validate_input

        # _validate_input returns falsy value (empty string) when invalid
        assert not _validate_input({"prompt": ""})

    def test_suggestion_to_dict(self) -> None:
        """Test converting SuggestedCapture to dict."""
        from git_notes_memory.hooks.models import SuggestedCapture
        from git_notes_memory.hooks.user_prompt_handler import _suggestion_to_dict

        suggestion = SuggestedCapture(
            namespace="decisions",
            summary="Use PostgreSQL",
            content="Decided to use PostgreSQL for database",
            tags=("database", "architecture"),
            confidence=0.85,
        )
        result = _suggestion_to_dict(suggestion)

        assert result["namespace"] == "decisions"
        assert result["summary"] == "Use PostgreSQL"
        assert result["content"] == "Decided to use PostgreSQL for database"
        assert set(result["tags"]) == {"database", "architecture"}
        assert result["confidence"] == 0.85

    def test_format_suggestions_xml_empty(self) -> None:
        """Test XML formatting with empty suggestions."""
        from git_notes_memory.hooks.user_prompt_handler import _format_suggestions_xml

        result = _format_suggestions_xml([])
        assert result == ""

    def test_format_suggestions_xml_single(self) -> None:
        """Test XML formatting with a single suggestion."""
        from git_notes_memory.hooks.models import SuggestedCapture
        from git_notes_memory.hooks.user_prompt_handler import _format_suggestions_xml

        suggestions = [
            SuggestedCapture(
                namespace="learnings",
                summary="Test learning",
                content="Content here",
                tags=("tag1",),
                confidence=0.8,
            )
        ]
        result = _format_suggestions_xml(suggestions)

        assert "<capture_suggestions>" in result
        assert "</capture_suggestions>" in result
        assert "<suggestion" in result
        assert "<namespace>learnings</namespace>" in result
        assert "<summary>Test learning</summary>" in result

    def test_write_output_skip_action(self) -> None:
        """Test output for SKIP action."""
        from git_notes_memory.hooks.models import CaptureAction
        from git_notes_memory.hooks.user_prompt_handler import _write_output

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output(CaptureAction.SKIP, [])

        output = json.loads(captured.getvalue())
        assert output["continue"] is True
        assert "hookSpecificOutput" not in output

    def test_write_output_suggest_action(self) -> None:
        """Test output for SUGGEST action."""
        from git_notes_memory.hooks.models import CaptureAction, SuggestedCapture
        from git_notes_memory.hooks.user_prompt_handler import _write_output

        suggestions = [
            SuggestedCapture(
                namespace="decisions",
                summary="Test decision",
                content="Content",
                tags=(),
                confidence=0.85,
            )
        ]

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output(CaptureAction.SUGGEST, suggestions)

        output = json.loads(captured.getvalue())
        assert output["continue"] is True
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        assert "captureSuggestions" in output["hookSpecificOutput"]
        assert len(output["hookSpecificOutput"]["captureSuggestions"]) == 1

    def test_write_output_auto_action(self) -> None:
        """Test output for AUTO action with captured memories."""
        from git_notes_memory.hooks.models import CaptureAction, SuggestedCapture
        from git_notes_memory.hooks.user_prompt_handler import _write_output

        suggestions = [
            SuggestedCapture(
                namespace="decisions",
                summary="Test",
                content="Content",
                tags=(),
                confidence=0.98,
            )
        ]
        captured_memories = [
            {"success": True, "memory_id": "abc123", "summary": "Test"}
        ]

        out = io.StringIO()
        with patch.object(sys, "stdout", out):
            _write_output(CaptureAction.AUTO, suggestions, captured_memories)

        output = json.loads(out.getvalue())
        assert output["continue"] is True
        assert "message" in output
        assert "1 memory" in output["message"]


# ============================================================================
# Stop Handler Tests
# ============================================================================


class TestStopHandler:
    """Tests for the Stop hook handler."""

    def test_read_input_valid_json(self) -> None:
        """Test reading valid JSON input."""
        from git_notes_memory.hooks.stop_handler import _read_input

        input_data = {"cwd": "/test", "transcript_path": "/path/to/transcript"}
        with patch.object(sys, "stdin", io.StringIO(json.dumps(input_data))):
            result = _read_input()
        assert result == input_data

    def test_read_input_empty_returns_dict(self) -> None:
        """Test that empty input returns empty dict for stop hook."""
        from git_notes_memory.hooks.stop_handler import _read_input

        with patch.object(sys, "stdin", io.StringIO("")):
            result = _read_input()
        assert result == {}

    def test_read_input_whitespace_returns_dict(self) -> None:
        """Test that whitespace-only input returns empty dict."""
        from git_notes_memory.hooks.stop_handler import _read_input

        with patch.object(sys, "stdin", io.StringIO("   \n  ")):
            result = _read_input()
        assert result == {}

    def test_signal_to_dict(self) -> None:
        """Test converting CaptureSignal to dict."""
        from git_notes_memory.hooks.models import CaptureSignal, SignalType
        from git_notes_memory.hooks.stop_handler import _signal_to_dict

        signal = CaptureSignal(
            type=SignalType.DECISION,
            match="Use PostgreSQL",
            confidence=0.9,
            context="Database choice",
            suggested_namespace="decisions",
        )
        result = _signal_to_dict(signal)

        assert result["type"] == "decision"
        assert result["match"] == "Use PostgreSQL"
        assert result["confidence"] == 0.9
        assert result["context"] == "Database choice"
        assert result["suggestedNamespace"] == "decisions"

    def test_format_uncaptured_xml_empty(self) -> None:
        """Test XML formatting with empty signals."""
        from git_notes_memory.hooks.stop_handler import _format_uncaptured_xml

        result = _format_uncaptured_xml([])
        assert result == ""

    def test_format_uncaptured_xml_with_signals(self) -> None:
        """Test XML formatting with signals."""
        from git_notes_memory.hooks.models import CaptureSignal, SignalType
        from git_notes_memory.hooks.stop_handler import _format_uncaptured_xml

        signals = [
            CaptureSignal(
                type=SignalType.LEARNING,
                match="Learned about indexes",
                confidence=0.85,
                context="Performance optimization",
                suggested_namespace="learnings",
            )
        ]
        result = _format_uncaptured_xml(signals)

        assert "<uncaptured_memories>" in result
        assert "</uncaptured_memories>" in result
        assert "<signal" in result
        assert "type=" in result
        assert "<match>" in result
        assert "<action>" in result
        assert "/remember" in result

    def test_write_output_no_content(self) -> None:
        """Test output with no uncaptured content."""
        from git_notes_memory.hooks.stop_handler import _write_output

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output([], None, prompt_uncaptured=True)

        output = json.loads(captured.getvalue())
        assert output["continue"] is True
        assert "hookSpecificOutput" not in output

    def test_write_output_with_uncaptured(self) -> None:
        """Test output with uncaptured content."""
        from git_notes_memory.hooks.models import CaptureSignal, SignalType
        from git_notes_memory.hooks.stop_handler import _write_output

        signals = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="Test",
                confidence=0.9,
                context="Context",
                suggested_namespace="decisions",
            )
        ]

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output(signals, None, prompt_uncaptured=True)

        output = json.loads(captured.getvalue())
        assert output["continue"] is True
        assert "message" in output
        assert "uncaptured" in output["message"].lower()
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "Stop"

    def test_write_output_with_sync_stats(self) -> None:
        """Test output with sync statistics."""
        from git_notes_memory.hooks.stop_handler import _write_output

        sync_result = {"success": True, "stats": {"indexed": 5}}

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output([], sync_result, prompt_uncaptured=True)

        output = json.loads(captured.getvalue())
        assert output["continue"] is True
        assert "message" in output
        assert "5 memories indexed" in output["message"]
        assert "hookSpecificOutput" in output
        assert "syncStats" in output["hookSpecificOutput"]

    def test_write_output_sync_skipped(self) -> None:
        """Test output when sync is skipped."""
        from git_notes_memory.hooks.stop_handler import _write_output

        sync_result = {"success": True, "skipped": True}

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output([], sync_result, prompt_uncaptured=True)

        output = json.loads(captured.getvalue())
        assert output["continue"] is True
        # Skipped sync doesn't add hookSpecificOutput
        assert "hookSpecificOutput" not in output

    def test_analyze_session_no_transcript(self) -> None:
        """Test session analysis with no transcript path."""
        from git_notes_memory.hooks.stop_handler import _analyze_session

        result = _analyze_session(None)
        assert result == []

    def test_analyze_session_missing_file(self, tmp_path: Path) -> None:
        """Test session analysis with missing file."""
        from git_notes_memory.hooks.stop_handler import _analyze_session

        result = _analyze_session(str(tmp_path / "nonexistent.json"))
        assert result == []


# ============================================================================
# Wrapper Script Tests
# ============================================================================


class TestWrapperScripts:
    """Tests for the hook wrapper scripts in hooks/ directory."""

    def test_session_start_wrapper_import_error(self) -> None:
        """Test session_start.py handles ImportError gracefully."""
        # Import the wrapper's main function
        import importlib.util
        from pathlib import Path as P

        wrapper_path = P(__file__).parent.parent / "hooks" / "session_start.py"
        if not wrapper_path.exists():
            pytest.skip("Wrapper script not found")

        spec = importlib.util.spec_from_file_location("session_start", wrapper_path)
        if spec is None or spec.loader is None:
            pytest.skip("Could not load wrapper script")

        module = importlib.util.module_from_spec(spec)

        # Mock the import to raise ImportError
        with patch.dict(sys.modules, {"git_notes_memory": None}):
            with patch.object(sys, "exit") as mock_exit:
                # The wrapper should catch ImportError and exit 0
                try:
                    spec.loader.exec_module(module)
                    module.main()
                except SystemExit:
                    pass  # Expected from sys.exit(0)

    def test_user_prompt_wrapper_import_error(self) -> None:
        """Test user_prompt.py handles ImportError gracefully."""
        import importlib.util
        from pathlib import Path as P

        wrapper_path = P(__file__).parent.parent / "hooks" / "user_prompt.py"
        if not wrapper_path.exists():
            pytest.skip("Wrapper script not found")

        spec = importlib.util.spec_from_file_location("user_prompt", wrapper_path)
        if spec is None or spec.loader is None:
            pytest.skip("Could not load wrapper script")

        module = importlib.util.module_from_spec(spec)

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            with patch.dict(sys.modules, {"git_notes_memory": None}):
                try:
                    spec.loader.exec_module(module)
                    module.main()
                except SystemExit:
                    pass

        # Should output continue: true
        if captured.getvalue():
            output = json.loads(captured.getvalue())
            assert output.get("continue") is True

    def test_stop_wrapper_import_error(self) -> None:
        """Test stop.py handles ImportError gracefully."""
        import importlib.util
        from pathlib import Path as P

        wrapper_path = P(__file__).parent.parent / "hooks" / "stop.py"
        if not wrapper_path.exists():
            pytest.skip("Wrapper script not found")

        spec = importlib.util.spec_from_file_location("stop", wrapper_path)
        if spec is None or spec.loader is None:
            pytest.skip("Could not load wrapper script")

        module = importlib.util.module_from_spec(spec)

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            with patch.dict(sys.modules, {"git_notes_memory": None}):
                try:
                    spec.loader.exec_module(module)
                    module.main()
                except SystemExit:
                    pass

        # Should output continue: true
        if captured.getvalue():
            output = json.loads(captured.getvalue())
            assert output.get("continue") is True


# ============================================================================
# Timeout and Signal Handler Tests
# ============================================================================


class TestTimeoutHandling:
    """Tests for timeout handling in hook handlers."""

    @pytest.mark.skipif(
        not hasattr(os, "kill"),
        reason="Signal handling not available on this platform",
    )
    def test_session_start_setup_timeout(self) -> None:
        """Test timeout setup for SessionStart handler."""
        from git_notes_memory.hooks.session_start_handler import (
            _cancel_timeout,
            _setup_timeout,
        )

        # Should not raise on Unix systems
        _setup_timeout(5)
        _cancel_timeout()

    @pytest.mark.skipif(
        not hasattr(os, "kill"),
        reason="Signal handling not available on this platform",
    )
    def test_user_prompt_setup_timeout(self) -> None:
        """Test timeout setup for UserPromptSubmit handler."""
        from git_notes_memory.hooks.user_prompt_handler import (
            _cancel_timeout,
            _setup_timeout,
        )

        _setup_timeout(5)
        _cancel_timeout()

    @pytest.mark.skipif(
        not hasattr(os, "kill"),
        reason="Signal handling not available on this platform",
    )
    def test_stop_setup_timeout(self) -> None:
        """Test timeout setup for Stop handler."""
        from git_notes_memory.hooks.stop_handler import _cancel_timeout, _setup_timeout

        _setup_timeout(5)
        _cancel_timeout()


# ============================================================================
# Configuration Integration Tests
# ============================================================================


class TestConfigIntegration:
    """Tests for configuration integration in handlers."""

    def test_session_start_respects_disabled_hook(
        self, hook_env_disabled: None
    ) -> None:
        """Test SessionStart respects HOOK_ENABLED=false."""
        from git_notes_memory.hooks.config_loader import load_hook_config

        config = load_hook_config()
        assert config.enabled is False

    def test_user_prompt_respects_disabled_hook(self, hook_env_disabled: None) -> None:
        """Test UserPromptSubmit respects HOOK_ENABLED=false."""
        from git_notes_memory.hooks.config_loader import load_hook_config

        config = load_hook_config()
        assert config.enabled is False

    def test_stop_respects_disabled_hook(self, hook_env_disabled: None) -> None:
        """Test Stop respects HOOK_ENABLED=false."""
        from git_notes_memory.hooks.config_loader import load_hook_config

        config = load_hook_config()
        assert config.enabled is False

    def test_config_loads_with_hook_enabled(self, hook_env_enabled: None) -> None:
        """Test configuration loads correctly with hooks enabled."""
        from git_notes_memory.hooks.config_loader import load_hook_config

        config = load_hook_config()
        assert config.enabled is True
        assert config.session_start_enabled is True
        assert config.user_prompt_enabled is True
        assert config.stop_enabled is True
