"""Observability configuration management.

Provides centralized configuration for all observability features
via environment variables with sensible defaults.

Configuration File:
    The library checks for a config file before reading env vars.
    Priority order:
    1. ~/.local/memory-plugin.env
    2. ~/.local/share/memory-plugin/env
    3. Environment variables

Environment Variables:
    MEMORY_PLUGIN_OBSERVABILITY_ENABLED: Enable/disable all observability (default: true)
    MEMORY_PLUGIN_LOG_LEVEL: Logging level - quiet/info/debug/trace (default: info)
    MEMORY_PLUGIN_LOG_FORMAT: Log format - json/text (default: json)
    MEMORY_PLUGIN_METRICS_ENABLED: Enable metrics collection (default: true)
    MEMORY_PLUGIN_METRICS_RETENTION: Rolling window size (default: 3600)
    MEMORY_PLUGIN_TRACING_ENABLED: Enable distributed tracing (default: true)
    MEMORY_PLUGIN_OTLP_ENDPOINT: OTLP export endpoint (default: http://localhost:4317)
    MEMORY_PLUGIN_PROMETHEUS_PORT: Prometheus scrape port (default: 9090)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path


class LogLevel(str, Enum):
    """Unified log level enumeration.

    Replaces fragmented HOOK_DEBUG with a graduated system:
    - quiet: Errors only, minimal output
    - info: Normal operation, key events (default)
    - debug: Detailed debugging information
    - trace: Full trace context, all spans
    """

    QUIET = "quiet"
    INFO = "info"
    DEBUG = "debug"
    TRACE = "trace"

    @classmethod
    def from_string(cls, value: str) -> LogLevel:
        """Parse log level from string, case-insensitive."""
        normalized = value.lower().strip()
        try:
            return cls(normalized)
        except ValueError:
            # Fall back to INFO for unknown values
            return cls.INFO

    def to_python_level(self) -> int:
        """Convert to Python logging level."""
        import logging

        mapping = {
            LogLevel.QUIET: logging.ERROR,
            LogLevel.INFO: logging.INFO,
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.TRACE: logging.DEBUG - 5,  # Custom TRACE level
        }
        return mapping.get(self, logging.INFO)


class LogFormat(str, Enum):
    """Log output format."""

    JSON = "json"
    TEXT = "text"

    @classmethod
    def from_string(cls, value: str) -> LogFormat:
        """Parse log format from string, case-insensitive."""
        normalized = value.lower().strip()
        try:
            return cls(normalized)
        except ValueError:
            return cls.JSON


@dataclass(frozen=True)
class ObservabilityConfig:
    """Immutable configuration for observability features.

    All settings are frozen after initialization to prevent
    accidental modification during runtime.
    """

    # Master switch
    enabled: bool = True

    # Logging
    log_level: LogLevel = LogLevel.INFO
    log_format: LogFormat = LogFormat.JSON

    # Metrics
    metrics_enabled: bool = True
    metrics_retention: int = 3600  # Rolling window size in samples

    # Tracing
    tracing_enabled: bool = True

    # Export endpoints
    otlp_endpoint: str | None = None
    prometheus_port: int | None = None

    # Service identification
    service_name: str = "git-notes-memory"

    def is_debug(self) -> bool:
        """Check if debug or trace level is enabled."""
        return self.log_level in (LogLevel.DEBUG, LogLevel.TRACE)

    def is_trace(self) -> bool:
        """Check if trace level is enabled."""
        return self.log_level == LogLevel.TRACE


_config_loaded = False


def _load_env_file() -> None:
    """Load environment variables from a config file.

    This enables configuration of the memory-plugin library without requiring
    shell profile modifications. Useful for:
    - Claude Code hooks (run in clean environment without shell env vars)
    - System services or cron jobs
    - Docker containers without env passthrough

    File Locations (checked in order):

    Unix/macOS:
        1. ~/.local/share/memory-plugin/env (recommended - same dir as data)

    Windows:
        1. %LOCALAPPDATA%/memory-plugin/env

    File Format:
        # Comments start with #
        export MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4318
        MEMORY_PLUGIN_OTLP_ALLOW_INTERNAL=true

        Both 'export VAR=value' and 'VAR=value' syntaxes are supported.
        Values can be quoted with single or double quotes.

    Behavior:
        - Only loads once per process (cached)
        - Does NOT override existing environment variables
        - Silently skips if file doesn't exist or can't be read

    Example ~/.local/share/memory-plugin/env:
        # Memory Plugin Configuration
        # See CLAUDE.md for full documentation

        # OTLP/Observability
        export MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4318
        export MEMORY_PLUGIN_OTLP_ALLOW_INTERNAL=true

        # Hook behavior
        export HOOK_SESSION_START_ENABLED=true
        export HOOK_STOP_ENABLED=true

        # Remote sync (optional)
        # export HOOK_SESSION_START_FETCH_REMOTE=true
        # export HOOK_STOP_PUSH_REMOTE=true
    """
    global _config_loaded
    if _config_loaded:
        return

    # Platform-specific config paths
    if os.name == "nt":  # Windows
        # Windows: use LOCALAPPDATA or APPDATA
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        app_data = os.environ.get("APPDATA", "")
        config_paths = []
        if local_app_data:
            config_paths.append(Path(local_app_data) / "memory-plugin" / "env")
        if app_data:
            config_paths.append(Path(app_data) / "memory-plugin" / "env")
    else:
        # Unix/macOS
        config_paths = [
            Path.home() / ".local" / "share" / "memory-plugin" / "env",
        ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path) as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if not line or line.startswith("#"):
                            continue
                        # Handle 'export VAR=value' or 'VAR=value'
                        if line.startswith("export "):
                            line = line[7:]
                        if "=" in line:
                            key, _, value = line.partition("=")
                            key = key.strip()
                            # Strip inline comments (# after value)
                            if "#" in value:
                                value = value.split("#", 1)[0]
                            value = value.strip().strip("\"'")
                            # Expand shell variables ($HOME, $USER, etc.)
                            value = os.path.expandvars(value)
                            # Only set if not already in environment
                            if key not in os.environ:
                                os.environ[key] = value
            except (OSError, PermissionError):
                pass  # Silently skip if file can't be read
            break  # Stop after first file found

    _config_loaded = True


def _parse_bool(value: str | None, default: bool = True) -> bool:
    """Parse boolean from environment variable."""
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


def _parse_int(value: str | None, default: int) -> int:
    """Parse integer from environment variable."""
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _load_config_from_env() -> ObservabilityConfig:
    """Load configuration from environment variables.

    First loads from config file (~/.local/memory-plugin.env) if present,
    then reads from environment variables.
    """
    # Load from config file first
    _load_env_file()

    # Master switch
    enabled = _parse_bool(
        os.environ.get("MEMORY_PLUGIN_OBSERVABILITY_ENABLED"), default=True
    )

    # Logging configuration
    log_level = LogLevel.from_string(os.environ.get("MEMORY_PLUGIN_LOG_LEVEL", "info"))
    log_format = LogFormat.from_string(
        os.environ.get("MEMORY_PLUGIN_LOG_FORMAT", "json")
    )

    # Backward compatibility: respect HOOK_DEBUG if set
    hook_debug = os.environ.get("HOOK_DEBUG", "").lower()
    if hook_debug in ("true", "1", "yes", "on"):
        log_level = LogLevel.DEBUG

    # Metrics configuration
    metrics_enabled = _parse_bool(
        os.environ.get("MEMORY_PLUGIN_METRICS_ENABLED"), default=True
    )
    metrics_retention = _parse_int(
        os.environ.get("MEMORY_PLUGIN_METRICS_RETENTION"), default=3600
    )

    # Tracing configuration
    tracing_enabled = _parse_bool(
        os.environ.get("MEMORY_PLUGIN_TRACING_ENABLED"), default=True
    )

    # Export endpoints
    otlp_endpoint = os.environ.get("MEMORY_PLUGIN_OTLP_ENDPOINT")
    prometheus_port_str = os.environ.get("MEMORY_PLUGIN_PROMETHEUS_PORT")
    prometheus_port = (
        _parse_int(prometheus_port_str, default=0) if prometheus_port_str else None
    )

    # Service name
    service_name = os.environ.get("MEMORY_PLUGIN_SERVICE_NAME", "git-notes-memory")

    return ObservabilityConfig(
        enabled=enabled,
        log_level=log_level,
        log_format=log_format,
        metrics_enabled=metrics_enabled,
        metrics_retention=metrics_retention,
        tracing_enabled=tracing_enabled,
        otlp_endpoint=otlp_endpoint,
        prometheus_port=prometheus_port,
        service_name=service_name,
    )


@lru_cache(maxsize=1)
def get_config() -> ObservabilityConfig:
    """Get the observability configuration singleton.

    Configuration is loaded once from environment variables and cached.
    Use `get_config.cache_clear()` to reload if environment changes.

    Returns:
        ObservabilityConfig: Frozen configuration dataclass.
    """
    return _load_config_from_env()


def reset_config() -> None:
    """Clear the configuration cache, forcing reload on next access.

    Primarily for testing.
    """
    get_config.cache_clear()
