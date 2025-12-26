"""Tests for observability configuration."""

from __future__ import annotations

import pytest

from git_notes_memory.observability.config import (
    LogFormat,
    LogLevel,
    ObservabilityConfig,
    get_config,
    reset_config,
)


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_from_string_valid_values(self) -> None:
        """Test parsing valid log level strings."""
        assert LogLevel.from_string("quiet") == LogLevel.QUIET
        assert LogLevel.from_string("info") == LogLevel.INFO
        assert LogLevel.from_string("debug") == LogLevel.DEBUG
        assert LogLevel.from_string("trace") == LogLevel.TRACE

    def test_from_string_case_insensitive(self) -> None:
        """Test case-insensitive parsing."""
        assert LogLevel.from_string("QUIET") == LogLevel.QUIET
        assert LogLevel.from_string("Info") == LogLevel.INFO
        assert LogLevel.from_string("DEBUG") == LogLevel.DEBUG

    def test_from_string_with_whitespace(self) -> None:
        """Test parsing with whitespace."""
        assert LogLevel.from_string("  info  ") == LogLevel.INFO

    def test_from_string_invalid_falls_back_to_info(self) -> None:
        """Test invalid values fall back to INFO."""
        assert LogLevel.from_string("invalid") == LogLevel.INFO
        assert LogLevel.from_string("") == LogLevel.INFO

    def test_to_python_level(self) -> None:
        """Test conversion to Python logging levels."""
        import logging

        assert LogLevel.QUIET.to_python_level() == logging.ERROR
        assert LogLevel.INFO.to_python_level() == logging.INFO
        assert LogLevel.DEBUG.to_python_level() == logging.DEBUG
        assert LogLevel.TRACE.to_python_level() == logging.DEBUG - 5


class TestLogFormat:
    """Tests for LogFormat enum."""

    def test_from_string_valid_values(self) -> None:
        """Test parsing valid format strings."""
        assert LogFormat.from_string("json") == LogFormat.JSON
        assert LogFormat.from_string("text") == LogFormat.TEXT

    def test_from_string_case_insensitive(self) -> None:
        """Test case-insensitive parsing."""
        assert LogFormat.from_string("JSON") == LogFormat.JSON
        assert LogFormat.from_string("Text") == LogFormat.TEXT

    def test_from_string_invalid_falls_back_to_json(self) -> None:
        """Test invalid values fall back to JSON."""
        assert LogFormat.from_string("invalid") == LogFormat.JSON


class TestObservabilityConfig:
    """Tests for ObservabilityConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ObservabilityConfig()
        assert config.enabled is True
        assert config.log_level == LogLevel.INFO
        assert config.log_format == LogFormat.JSON
        assert config.metrics_enabled is True
        assert config.metrics_retention == 3600
        assert config.tracing_enabled is True
        assert config.otlp_endpoint is None
        assert config.prometheus_port is None
        assert config.service_name == "git-notes-memory"

    def test_is_debug(self) -> None:
        """Test is_debug() method."""
        assert ObservabilityConfig(log_level=LogLevel.DEBUG).is_debug() is True
        assert ObservabilityConfig(log_level=LogLevel.TRACE).is_debug() is True
        assert ObservabilityConfig(log_level=LogLevel.INFO).is_debug() is False
        assert ObservabilityConfig(log_level=LogLevel.QUIET).is_debug() is False

    def test_is_trace(self) -> None:
        """Test is_trace() method."""
        assert ObservabilityConfig(log_level=LogLevel.TRACE).is_trace() is True
        assert ObservabilityConfig(log_level=LogLevel.DEBUG).is_trace() is False
        assert ObservabilityConfig(log_level=LogLevel.INFO).is_trace() is False

    def test_frozen_dataclass(self) -> None:
        """Test that config is immutable."""
        config = ObservabilityConfig()
        with pytest.raises(AttributeError):
            config.enabled = False  # type: ignore[misc]


class TestGetConfig:
    """Tests for get_config() singleton."""

    def setup_method(self) -> None:
        """Reset config before each test."""
        reset_config()

    def teardown_method(self) -> None:
        """Reset config after each test."""
        reset_config()

    def test_get_config_returns_singleton(self) -> None:
        """Test that get_config returns the same instance."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_get_config_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading config from environment variables."""
        monkeypatch.setenv("MEMORY_PLUGIN_OBSERVABILITY_ENABLED", "false")
        monkeypatch.setenv("MEMORY_PLUGIN_LOG_LEVEL", "debug")
        monkeypatch.setenv("MEMORY_PLUGIN_LOG_FORMAT", "text")
        monkeypatch.setenv("MEMORY_PLUGIN_METRICS_ENABLED", "false")
        monkeypatch.setenv("MEMORY_PLUGIN_METRICS_RETENTION", "7200")
        monkeypatch.setenv("MEMORY_PLUGIN_TRACING_ENABLED", "false")
        monkeypatch.setenv("MEMORY_PLUGIN_SERVICE_NAME", "test-service")

        config = get_config()

        assert config.enabled is False
        assert config.log_level == LogLevel.DEBUG
        assert config.log_format == LogFormat.TEXT
        assert config.metrics_enabled is False
        assert config.metrics_retention == 7200
        assert config.tracing_enabled is False
        assert config.service_name == "test-service"

    def test_hook_debug_backward_compatibility(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test HOOK_DEBUG env var enables debug level."""
        monkeypatch.setenv("HOOK_DEBUG", "true")

        config = get_config()
        assert config.log_level == LogLevel.DEBUG

    def test_otlp_endpoint_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test OTLP endpoint configuration."""
        monkeypatch.setenv("MEMORY_PLUGIN_OTLP_ENDPOINT", "http://localhost:4317")

        config = get_config()
        assert config.otlp_endpoint == "http://localhost:4317"

    def test_prometheus_port_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test Prometheus port configuration."""
        monkeypatch.setenv("MEMORY_PLUGIN_PROMETHEUS_PORT", "9090")

        config = get_config()
        assert config.prometheus_port == 9090

    def test_reset_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test config reset forces reload."""
        config1 = get_config()
        # Clear HOOK_DEBUG to ensure MEMORY_PLUGIN_LOG_LEVEL takes effect
        monkeypatch.delenv("HOOK_DEBUG", raising=False)
        monkeypatch.setenv("MEMORY_PLUGIN_LOG_LEVEL", "trace")
        reset_config()
        config2 = get_config()

        assert config1 is not config2
        assert config2.log_level == LogLevel.TRACE
