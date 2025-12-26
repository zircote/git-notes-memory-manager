"""Structured logging with trace context injection.

Provides a StructuredLogger that automatically includes trace IDs,
session info, and supports both JSON and text output formats.

Usage:
    from git_notes_memory.observability import get_logger

    logger = get_logger(__name__)
    logger.info("Memory captured", memory_id="abc123", namespace="decisions")
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from git_notes_memory.observability.config import LogFormat, LogLevel, get_config
from git_notes_memory.observability.session import get_session_info
from git_notes_memory.observability.tracing import (
    get_current_span_id,
    get_current_trace_id,
)

# Custom TRACE level (below DEBUG)
TRACE_LEVEL = logging.DEBUG - 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


class StructuredLogger:
    """Logger that emits structured log records with trace context.

    Automatically injects:
    - trace_id and span_id from current trace context
    - session_id from global session
    - Timestamp in ISO format

    Supports JSON and text output formats based on configuration.
    """

    def __init__(self, name: str) -> None:
        """Initialize the structured logger.

        Args:
            name: Logger name (typically __name__).
        """
        self.name = name
        self._logger = logging.getLogger(name)
        self._configured = False

    def _ensure_configured(self) -> None:
        """Ensure the logger is configured on first use."""
        if self._configured:
            return

        config = get_config()
        level = config.log_level.to_python_level()
        self._logger.setLevel(level)

        # Only add handler if none exist
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(level)

            if config.log_format == LogFormat.JSON:
                handler.setFormatter(JsonFormatter())
            else:
                handler.setFormatter(TextFormatter())

            self._logger.addHandler(handler)

        self._configured = True

    def _build_extra(self, **kwargs: Any) -> dict[str, Any]:
        """Build extra fields with trace context."""
        extra: dict[str, Any] = dict(kwargs)

        # Add trace context if available
        trace_id = get_current_trace_id()
        span_id = get_current_span_id()
        if trace_id:
            extra["trace_id"] = trace_id
        if span_id:
            extra["span_id"] = span_id

        # Add session context
        config = get_config()
        if config.enabled:
            session = get_session_info()
            extra["session_id"] = session.short_id

        return extra

    def trace(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log at TRACE level (below DEBUG).

        Supports both format-string style (msg % args) and structured kwargs.
        """
        self._ensure_configured()
        config = get_config()
        if config.log_level == LogLevel.TRACE:
            extra = self._build_extra(**kwargs)
            self._logger.log(TRACE_LEVEL, msg, *args, extra={"structured": extra})

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log at DEBUG level.

        Supports both format-string style (msg % args) and structured kwargs.
        """
        self._ensure_configured()
        extra = self._build_extra(**kwargs)
        self._logger.debug(msg, *args, extra={"structured": extra})

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log at INFO level.

        Supports both format-string style (msg % args) and structured kwargs.
        """
        self._ensure_configured()
        extra = self._build_extra(**kwargs)
        self._logger.info(msg, *args, extra={"structured": extra})

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log at WARNING level.

        Supports both format-string style (msg % args) and structured kwargs.
        """
        self._ensure_configured()
        extra = self._build_extra(**kwargs)
        self._logger.warning(msg, *args, extra={"structured": extra})

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log at ERROR level.

        Supports both format-string style (msg % args) and structured kwargs.
        """
        self._ensure_configured()
        extra = self._build_extra(**kwargs)
        self._logger.error(msg, *args, extra={"structured": extra})

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log at ERROR level with exception info.

        Supports both format-string style (msg % args) and structured kwargs.
        """
        self._ensure_configured()
        extra = self._build_extra(**kwargs)
        self._logger.exception(msg, *args, extra={"structured": extra})


class JsonFormatter(logging.Formatter):
    """Formatter that outputs JSON-structured log records."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        output: dict[str, Any] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add structured fields if present
        structured = getattr(record, "structured", None)
        if structured:
            output.update(structured)

        # Add exception info if present
        if record.exc_info:
            output["exception"] = self.formatException(record.exc_info)

        return json.dumps(output)


class TextFormatter(logging.Formatter):
    """Formatter that outputs human-readable text with context."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as text."""
        timestamp = datetime.now(tz=UTC).strftime("%H:%M:%S.%f")[:-3]
        level = record.levelname[:4]
        msg = record.getMessage()

        parts = [f"{timestamp} {level} [{record.name}] {msg}"]

        # Add structured fields if present
        structured = getattr(record, "structured", None)
        if structured:
            fields = " ".join(f"{k}={v}" for k, v in structured.items())
            parts.append(f"  {fields}")

        # Add exception info if present
        if record.exc_info:
            parts.append(self.formatException(record.exc_info))

        return "\n".join(parts)


# Logger cache
_loggers: dict[str, StructuredLogger] = {}


def get_logger(name: str) -> StructuredLogger:
    """Get or create a StructuredLogger for the given name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        StructuredLogger instance.
    """
    if name not in _loggers:
        _loggers[name] = StructuredLogger(name)
    return _loggers[name]


def reset_loggers() -> None:
    """Reset all loggers.

    Primarily for testing.
    """
    _loggers.clear()
