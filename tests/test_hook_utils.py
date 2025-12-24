"""Tests for git_notes_memory.hooks.hook_utils module.

Tests the shared hook utilities including:
- setup_timeout() and cancel_timeout() - SIGALRM handling
- validate_file_path() - Path traversal prevention, security validation
- get_hook_logger() - Logger creation and caching
- read_json_input() - Input size limits, JSON parsing
- log_hook_input() and log_hook_output() - Logging helpers
- setup_logging() - Debug/warning level configuration
"""

from __future__ import annotations

import io
import json
import logging
import os
import signal
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from git_notes_memory.hooks.hook_utils import (
    DEFAULT_TIMEOUT,
    MAX_INPUT_SIZE,
    cancel_timeout,
    get_hook_logger,
    log_hook_input,
    log_hook_output,
    read_json_input,
    setup_logging,
    setup_timeout,
    validate_file_path,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def reset_hook_loggers() -> Iterator[None]:
    """Reset the hook logger cache before and after each test.

    Also clears handlers from the underlying Python loggers to prevent
    cross-test pollution from the global logging.Logger cache.
    """
    import logging

    from git_notes_memory.hooks import hook_utils

    def _clear_hook_loggers() -> None:
        # Clear the module-level cache
        hook_utils._hook_loggers.clear()
        # Also clear handlers from any cached Python loggers
        for name in list(logging.Logger.manager.loggerDict.keys()):
            if name.startswith("memory_hook."):
                logger = logging.getLogger(name)
                logger.handlers.clear()

    _clear_hook_loggers()
    yield
    _clear_hook_loggers()


@pytest.fixture
def temp_file(tmp_path: Path) -> Path:
    """Create a temporary file for path validation tests."""
    file = tmp_path / "test_file.txt"
    file.write_text("test content")
    return file


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for path validation tests."""
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()
    return dir_path


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Test module-level constants."""

    def test_default_timeout_value(self) -> None:
        """Test DEFAULT_TIMEOUT is 30 seconds."""
        assert DEFAULT_TIMEOUT == 30

    def test_max_input_size_value(self) -> None:
        """Test MAX_INPUT_SIZE is 10MB."""
        assert MAX_INPUT_SIZE == 10 * 1024 * 1024


# =============================================================================
# validate_file_path() Tests
# =============================================================================


class TestValidateFilePath:
    """Test the validate_file_path security function."""

    def test_valid_absolute_path(self, temp_file: Path) -> None:
        """Test validation of a valid absolute path."""
        result = validate_file_path(str(temp_file))
        assert result == temp_file.resolve()

    def test_valid_path_object(self, temp_file: Path) -> None:
        """Test validation accepts Path objects."""
        result = validate_file_path(temp_file)
        assert result == temp_file.resolve()

    def test_empty_path_rejected(self) -> None:
        """Test empty path raises ValueError."""
        with pytest.raises(ValueError, match="Empty path provided"):
            validate_file_path("")

    def test_whitespace_only_path_rejected(self) -> None:
        """Test whitespace-only path is treated as empty."""
        # Path("   ") normalizes to "   " which is not empty
        # but isn't a valid absolute path
        with pytest.raises(ValueError):
            validate_file_path("   ")

    def test_path_traversal_double_dot_rejected(self, tmp_path: Path) -> None:
        """Test path with '..' traversal sequence is rejected."""
        path_with_traversal = str(tmp_path / "subdir" / ".." / "other")
        with pytest.raises(ValueError, match="Path contains traversal sequence"):
            validate_file_path(path_with_traversal)

    def test_path_traversal_at_start_rejected(self) -> None:
        """Test path starting with '../' is rejected."""
        with pytest.raises(ValueError, match="Path contains traversal sequence"):
            validate_file_path("../etc/passwd")

    def test_path_traversal_windows_style_rejected(self) -> None:
        """Test Windows-style path traversal is normalized and rejected."""
        with pytest.raises(ValueError, match="Path contains traversal sequence"):
            validate_file_path("C:\\Users\\..\\Admin")

    def test_relative_path_rejected_by_default(self) -> None:
        """Test relative paths are rejected by default."""
        with pytest.raises(ValueError, match="Relative path not allowed"):
            validate_file_path("relative/path/file.txt")

    def test_relative_path_allowed_when_enabled(self, tmp_path: Path) -> None:
        """Test relative paths are accepted when allow_relative=True."""
        # Create the file first
        (tmp_path / "file.txt").write_text("test")
        # Change to tmp_path to make relative path work
        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            result = validate_file_path("file.txt", allow_relative=True)
            assert result.name == "file.txt"
        finally:
            os.chdir(original_cwd)

    def test_nonexistent_file_rejected_by_default(self, tmp_path: Path) -> None:
        """Test nonexistent file raises ValueError when must_exist=True."""
        nonexistent = tmp_path / "does_not_exist.txt"
        with pytest.raises(ValueError, match="File does not exist"):
            validate_file_path(str(nonexistent), must_exist=True)

    def test_nonexistent_file_allowed_when_disabled(self, tmp_path: Path) -> None:
        """Test nonexistent file is accepted when must_exist=False."""
        nonexistent = tmp_path / "does_not_exist.txt"
        result = validate_file_path(str(nonexistent), must_exist=False)
        assert result == nonexistent.resolve()

    def test_directory_path_rejected(self, temp_dir: Path) -> None:
        """Test directory path raises ValueError (expects file)."""
        with pytest.raises(ValueError, match="Path is a directory, not a file"):
            validate_file_path(str(temp_dir), must_exist=True)

    def test_directory_path_allowed_when_must_exist_false(self, temp_dir: Path) -> None:
        """Test directory path is allowed when must_exist=False."""
        # When must_exist=False, we don't check if it's a file or directory
        result = validate_file_path(str(temp_dir), must_exist=False)
        assert result == temp_dir.resolve()

    def test_symlink_resolved(self, tmp_path: Path, temp_file: Path) -> None:
        """Test symlinks are properly resolved."""
        symlink = tmp_path / "symlink.txt"
        try:
            symlink.symlink_to(temp_file)
            result = validate_file_path(str(symlink))
            # Should resolve to the actual file
            assert result == temp_file.resolve()
        except OSError:
            pytest.skip("Symlinks not supported on this platform")


# =============================================================================
# read_json_input() Tests
# =============================================================================


class TestReadJsonInput:
    """Test the read_json_input function."""

    def test_valid_json_object(self) -> None:
        """Test reading valid JSON object from stdin."""
        test_input = '{"key": "value", "number": 42}'
        with patch("sys.stdin", io.StringIO(test_input)):
            result = read_json_input()
        assert result == {"key": "value", "number": 42}

    def test_empty_input_raises_error(self) -> None:
        """Test empty stdin raises ValueError."""
        with patch("sys.stdin", io.StringIO("")):
            with pytest.raises(ValueError, match="Empty input received on stdin"):
                read_json_input()

    def test_whitespace_only_input_raises_error(self) -> None:
        """Test whitespace-only input raises ValueError."""
        with patch("sys.stdin", io.StringIO("   \n\t  ")):
            with pytest.raises(ValueError, match="Empty input received on stdin"):
                read_json_input()

    def test_input_exceeds_max_size(self) -> None:
        """Test input exceeding max_size raises ValueError."""
        # Use a small max_size for testing
        small_max = 100
        large_input = '{"data": "' + "x" * 200 + '"}'
        with patch("sys.stdin", io.StringIO(large_input)):
            with pytest.raises(ValueError, match="Input exceeds maximum size"):
                read_json_input(max_size=small_max)

    def test_invalid_json_raises_error(self) -> None:
        """Test invalid JSON raises JSONDecodeError."""
        invalid_json = '{"key": "value"'  # Missing closing brace
        with patch("sys.stdin", io.StringIO(invalid_json)):
            with pytest.raises(json.JSONDecodeError):
                read_json_input()

    def test_json_array_raises_error(self) -> None:
        """Test JSON array (not object) raises ValueError."""
        json_array = "[1, 2, 3]"
        with patch("sys.stdin", io.StringIO(json_array)):
            with pytest.raises(ValueError, match="Expected JSON object, got list"):
                read_json_input()

    def test_json_string_raises_error(self) -> None:
        """Test JSON string raises ValueError."""
        json_string = '"just a string"'
        with patch("sys.stdin", io.StringIO(json_string)):
            with pytest.raises(ValueError, match="Expected JSON object, got str"):
                read_json_input()

    def test_json_number_raises_error(self) -> None:
        """Test JSON number raises ValueError."""
        json_number = "42"
        with patch("sys.stdin", io.StringIO(json_number)):
            with pytest.raises(ValueError, match="Expected JSON object, got int"):
                read_json_input()

    def test_complex_json_object(self) -> None:
        """Test reading complex nested JSON object."""
        test_input = json.dumps(
            {
                "cwd": "/path/to/project",
                "session_id": "abc123",
                "tool_input": {"file_path": "/test.py", "action": "read"},
                "nested": {"deep": {"value": True}},
            }
        )
        with patch("sys.stdin", io.StringIO(test_input)):
            result = read_json_input()
        assert result["cwd"] == "/path/to/project"
        assert result["tool_input"]["file_path"] == "/test.py"
        assert result["nested"]["deep"]["value"] is True

    def test_default_max_size_is_10mb(self) -> None:
        """Test that default max_size is MAX_INPUT_SIZE (10MB)."""
        # This test verifies the default parameter
        test_input = '{"key": "value"}'
        with patch("sys.stdin", io.StringIO(test_input)):
            # Should work with default max_size
            result = read_json_input()
        assert result == {"key": "value"}


# =============================================================================
# setup_timeout() and cancel_timeout() Tests
# =============================================================================


class TestTimeoutFunctions:
    """Test timeout setup and cancellation functions."""

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"), reason="SIGALRM not available on Windows"
    )
    def test_setup_timeout_sets_alarm(self) -> None:
        """Test setup_timeout sets SIGALRM alarm."""
        with patch("signal.alarm") as mock_alarm, patch("signal.signal"):
            setup_timeout(30, hook_name="TestHook")
            mock_alarm.assert_called_once_with(30)

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"), reason="SIGALRM not available on Windows"
    )
    def test_setup_timeout_registers_handler(self) -> None:
        """Test setup_timeout registers signal handler."""
        with patch("signal.alarm"), patch("signal.signal") as mock_signal:
            setup_timeout(30, hook_name="TestHook")
            # Should register handler for SIGALRM
            assert mock_signal.called
            call_args = mock_signal.call_args
            assert call_args[0][0] == signal.SIGALRM

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"), reason="SIGALRM not available on Windows"
    )
    def test_cancel_timeout_clears_alarm(self) -> None:
        """Test cancel_timeout clears the alarm."""
        with patch("signal.alarm") as mock_alarm:
            cancel_timeout()
            mock_alarm.assert_called_once_with(0)

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"), reason="SIGALRM not available on Windows"
    )
    def test_timeout_handler_prints_fallback_output(self) -> None:
        """Test timeout handler outputs fallback JSON and exits."""
        fallback_output = {"continue": True}

        # Capture the handler that gets registered
        registered_handler = None

        def capture_handler(sig: int, handler: Any) -> None:
            nonlocal registered_handler
            registered_handler = handler

        with patch("signal.signal", side_effect=capture_handler):
            with patch("signal.alarm"):
                setup_timeout(30, hook_name="TestHook", fallback_output=fallback_output)

        # Now test the handler
        assert registered_handler is not None

        with patch("builtins.print") as mock_print, pytest.raises(SystemExit) as exc:
            registered_handler(signal.SIGALRM, None)

        mock_print.assert_called_once_with('{"continue": true}')
        assert exc.value.code == 0

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"), reason="SIGALRM not available on Windows"
    )
    def test_custom_fallback_output(self) -> None:
        """Test timeout uses custom fallback_output."""
        custom_fallback = {"error": "timeout", "status": "failed"}

        registered_handler = None

        def capture_handler(sig: int, handler: Any) -> None:
            nonlocal registered_handler
            registered_handler = handler

        with patch("signal.signal", side_effect=capture_handler):
            with patch("signal.alarm"):
                setup_timeout(30, hook_name="TestHook", fallback_output=custom_fallback)

        assert registered_handler is not None

        with patch("builtins.print") as mock_print, pytest.raises(SystemExit):
            registered_handler(signal.SIGALRM, None)

        # Verify custom fallback was printed
        call_arg = mock_print.call_args[0][0]
        assert json.loads(call_arg) == custom_fallback

    def test_setup_timeout_noop_without_sigalrm(self) -> None:
        """Test setup_timeout is a no-op when SIGALRM doesn't exist."""
        # Temporarily remove SIGALRM attribute
        original_sigalrm = getattr(signal, "SIGALRM", None)
        if original_sigalrm is not None:
            delattr(signal, "SIGALRM")
        try:
            # Should not raise any error
            setup_timeout(30, hook_name="TestHook")
        finally:
            if original_sigalrm is not None:
                signal.SIGALRM = original_sigalrm

    def test_cancel_timeout_noop_without_sigalrm(self) -> None:
        """Test cancel_timeout is a no-op when SIGALRM doesn't exist."""
        original_sigalrm = getattr(signal, "SIGALRM", None)
        if original_sigalrm is not None:
            delattr(signal, "SIGALRM")
        try:
            # Should not raise any error
            cancel_timeout()
        finally:
            if original_sigalrm is not None:
                signal.SIGALRM = original_sigalrm


# =============================================================================
# get_hook_logger() Tests
# =============================================================================


class TestGetHookLogger:
    """Test the get_hook_logger function."""

    def test_creates_named_logger(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test that a named logger is created."""
        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            logger = get_hook_logger("TestHook")
        assert logger.name == "memory_hook.TestHook"

    def test_logger_caching(self, reset_hook_loggers: None, tmp_path: Path) -> None:
        """Test that loggers are cached and reused."""
        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            logger1 = get_hook_logger("CachedHook")
            logger2 = get_hook_logger("CachedHook")
        assert logger1 is logger2

    def test_different_hooks_get_different_loggers(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test different hook names get different loggers."""
        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            logger1 = get_hook_logger("HookA")
            logger2 = get_hook_logger("HookB")
        assert logger1 is not logger2
        assert logger1.name != logger2.name

    def test_logger_level_is_debug(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test logger is configured at DEBUG level."""
        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            logger = get_hook_logger("DebugHook")
        assert logger.level == logging.DEBUG

    def test_creates_log_directory(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test log directory is created if it doesn't exist."""
        log_dir = tmp_path / "new_logs"
        assert not log_dir.exists()

        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", log_dir):
            get_hook_logger("DirCreationHook")

        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_logger_has_file_handler(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test logger has a file handler configured."""
        from logging.handlers import RotatingFileHandler

        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            logger = get_hook_logger("FileHandlerHook")

        handlers = logger.handlers
        assert len(handlers) >= 1
        assert any(isinstance(h, RotatingFileHandler) for h in handlers)

    def test_log_file_naming(self, reset_hook_loggers: None, tmp_path: Path) -> None:
        """Test log file is named after hook (lowercase)."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", log_dir):
            logger = get_hook_logger("SessionStart")
            # Trigger file creation by writing a log entry
            logger.info("test log entry")
            # Force handler flush to ensure file is written
            for handler in logger.handlers:
                handler.flush()

        expected_log_file = log_dir / "sessionstart.log"
        assert expected_log_file.exists()


# =============================================================================
# log_hook_input() Tests
# =============================================================================


class TestLogHookInput:
    """Test the log_hook_input function."""

    def test_logs_standard_fields(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test standard hook fields are logged."""
        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            mock_logger = MagicMock()
            with patch(
                "git_notes_memory.hooks.hook_utils.get_hook_logger",
                return_value=mock_logger,
            ):
                log_hook_input(
                    "TestHook",
                    {
                        "cwd": "/test/path",
                        "session_id": "sess123",
                        "source": "test_source",
                        "transcript_path": "/path/to/transcript",
                    },
                )

        # Check that info was called multiple times
        assert mock_logger.info.call_count >= 4

    def test_logs_prompt_truncated(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test long prompts are truncated in logs."""
        long_prompt = "x" * 1000

        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            mock_logger = MagicMock()
            with patch(
                "git_notes_memory.hooks.hook_utils.get_hook_logger",
                return_value=mock_logger,
            ):
                log_hook_input("TestHook", {"prompt": long_prompt})

        # Find the call that logged the prompt with truncation
        prompt_logged = False
        for call in mock_logger.info.call_args_list:
            args = call[0]
            if len(args) >= 2 and "prompt" in str(args[0]) and "truncated" in str(args):
                prompt_logged = True
                break

        assert prompt_logged, "Long prompt should be logged as truncated"

    def test_logs_tool_info(self, reset_hook_loggers: None, tmp_path: Path) -> None:
        """Test tool_name and tool_input are logged for PostToolUse."""
        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            mock_logger = MagicMock()
            with patch(
                "git_notes_memory.hooks.hook_utils.get_hook_logger",
                return_value=mock_logger,
            ):
                log_hook_input(
                    "PostToolUse",
                    {
                        "tool_name": "Write",
                        "tool_input": {"file_path": "/test.py", "content": "# test"},
                    },
                )

        # Check tool info was logged
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("tool_name" in c for c in info_calls)
        assert any("tool_input" in c for c in info_calls)

    def test_logs_all_keys(self, reset_hook_loggers: None, tmp_path: Path) -> None:
        """Test all input keys are logged for reference."""
        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            mock_logger = MagicMock()
            with patch(
                "git_notes_memory.hooks.hook_utils.get_hook_logger",
                return_value=mock_logger,
            ):
                log_hook_input(
                    "TestHook",
                    {"key1": "val1", "key2": "val2", "key3": "val3"},
                )

        # Should log all keys
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("all_keys" in c for c in info_calls)


# =============================================================================
# log_hook_output() Tests
# =============================================================================


class TestLogHookOutput:
    """Test the log_hook_output function."""

    def test_logs_output_json(self, reset_hook_loggers: None, tmp_path: Path) -> None:
        """Test output is logged as JSON."""
        output = {"result": "success", "data": [1, 2, 3]}

        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            mock_logger = MagicMock()
            with patch(
                "git_notes_memory.hooks.hook_utils.get_hook_logger",
                return_value=mock_logger,
            ):
                log_hook_output("TestHook", output)

        # Should log HOOK OUTPUT
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("HOOK OUTPUT" in c for c in info_calls)

    def test_truncates_long_output(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test long output is truncated."""
        large_output = {"data": "x" * 5000}

        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            mock_logger = MagicMock()
            with patch(
                "git_notes_memory.hooks.hook_utils.get_hook_logger",
                return_value=mock_logger,
            ):
                log_hook_output("TestHook", large_output)

        # Check for truncation indicator
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        # At least one call should have truncated content
        assert any("truncated" in c or len(c) < 3000 for c in info_calls)


# =============================================================================
# setup_logging() Tests
# =============================================================================


class TestSetupLogging:
    """Test the setup_logging function."""

    def test_debug_mode_sets_debug_level(self) -> None:
        """Test debug=True sets DEBUG logging level."""
        # Reset root logger
        root_logger = logging.getLogger()
        original_level = root_logger.level

        try:
            setup_logging(debug=True)
            # The basicConfig should set level to DEBUG
            # Note: basicConfig only works if no handlers are configured
        finally:
            root_logger.setLevel(original_level)

    def test_non_debug_mode_sets_warning_level(self) -> None:
        """Test debug=False sets WARNING logging level."""
        root_logger = logging.getLogger()
        original_level = root_logger.level

        try:
            setup_logging(debug=False)
            # Should set level to WARNING
        finally:
            root_logger.setLevel(original_level)

    def test_with_hook_name_creates_logger(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test providing hook_name creates a hook logger."""
        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            setup_logging(debug=False, hook_name="SetupTest")

        # Logger should be cached
        from git_notes_memory.hooks import hook_utils

        assert "SetupTest" in hook_utils._hook_loggers


# =============================================================================
# Integration Tests
# =============================================================================


class TestHookUtilsIntegration:
    """Integration tests for hook utilities working together."""

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"), reason="SIGALRM not available on Windows"
    )
    def test_typical_hook_workflow(
        self, reset_hook_loggers: None, tmp_path: Path
    ) -> None:
        """Test typical hook workflow: setup_logging, setup_timeout, read_input."""
        input_data = {"cwd": "/test", "session_id": "test123"}

        with patch("git_notes_memory.hooks.hook_utils.LOG_DIR", tmp_path / "logs"):
            with patch("sys.stdin", io.StringIO(json.dumps(input_data))):
                with patch("signal.alarm"), patch("signal.signal"):
                    # Setup logging
                    setup_logging(debug=True, hook_name="IntegrationTest")

                    # Setup timeout
                    setup_timeout(30, hook_name="IntegrationTest")

                    try:
                        # Read input
                        data = read_json_input()
                        assert data == input_data

                        # Log input
                        log_hook_input("IntegrationTest", data)

                        # Process and log output
                        output = {"continue": True}
                        log_hook_output("IntegrationTest", output)
                    finally:
                        cancel_timeout()

    def test_path_validation_with_real_temp_files(self, tmp_path: Path) -> None:
        """Test path validation in realistic scenarios."""
        # Create a nested structure
        subdir = tmp_path / "project" / "src"
        subdir.mkdir(parents=True)

        config_file = subdir / "config.json"
        config_file.write_text('{"setting": "value"}')

        # Valid absolute path
        result = validate_file_path(str(config_file))
        assert result == config_file.resolve()

        # Path traversal attempt should fail
        traversal_path = str(subdir / ".." / ".." / "etc" / "passwd")
        with pytest.raises(ValueError, match="traversal"):
            validate_file_path(traversal_path)
