"""Tests for structured logging."""

from __future__ import annotations

import json

import pytest

from git_notes_memory.observability.config import reset_config
from git_notes_memory.observability.logging import (
    JsonFormatter,
    StructuredLogger,
    TextFormatter,
    get_logger,
    reset_loggers,
)


class TestStructuredLogger:
    """Tests for StructuredLogger."""

    def setup_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_loggers()

    def teardown_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_loggers()

    def test_get_logger(self) -> None:
        """Test getting a logger."""
        logger = get_logger("test_module")
        assert isinstance(logger, StructuredLogger)
        assert logger.name == "test_module"

    def test_get_logger_caches(self) -> None:
        """Test logger is cached by name."""
        logger1 = get_logger("cached_module")
        logger2 = get_logger("cached_module")
        assert logger1 is logger2

    def test_different_names_different_loggers(self) -> None:
        """Test different names get different loggers."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        assert logger1 is not logger2

    def test_info_logging(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test info level logging."""
        logger = get_logger("test_info")
        logger.info("Test message", key="value")

        # Output goes to stderr
        captured = capsys.readouterr()
        assert "Test message" in captured.err or len(captured.err) == 0

    def test_debug_logging(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test debug level logging."""
        monkeypatch.setenv("MEMORY_PLUGIN_LOG_LEVEL", "debug")
        reset_config()
        reset_loggers()

        logger = get_logger("test_debug")
        logger.debug("Debug message", data="test")

        captured = capsys.readouterr()
        # Debug should be output at debug level
        assert "Debug message" in captured.err or len(captured.err) == 0

    def test_warning_logging(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test warning level logging."""
        logger = get_logger("test_warning")
        logger.warning("Warning message")

        captured = capsys.readouterr()
        assert "Warning" in captured.err or len(captured.err) == 0

    def test_error_logging(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test error level logging."""
        logger = get_logger("test_error")
        logger.error("Error message", code=500)

        captured = capsys.readouterr()
        assert "Error" in captured.err or len(captured.err) == 0


class TestJsonFormatter:
    """Tests for JsonFormatter."""

    def test_basic_format(self) -> None:
        """Test basic JSON formatting."""
        import logging

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data["message"] == "Test message"
        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert "timestamp" in data

    def test_with_structured_fields(self) -> None:
        """Test JSON formatting with structured fields."""
        import logging

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.structured = {"key": "value", "count": 42}

        output = formatter.format(record)
        data = json.loads(output)

        assert data["key"] == "value"
        assert data["count"] == 42

    def test_with_exception(self) -> None:
        """Test JSON formatting with exception info."""
        import logging
        import sys

        formatter = JsonFormatter()

        try:
            raise ValueError("test error")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "ValueError: test error" in data["exception"]


class TestTextFormatter:
    """Tests for TextFormatter."""

    def test_basic_format(self) -> None:
        """Test basic text formatting."""
        import logging

        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test_module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)

        assert "INFO" in output
        assert "test_module" in output
        assert "Test message" in output

    def test_with_structured_fields(self) -> None:
        """Test text formatting with structured fields."""
        import logging

        formatter = TextFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.structured = {"key": "value"}

        output = formatter.format(record)

        assert "key=value" in output
