"""Tests for the secrets filtering configuration module."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from git_notes_memory.security.config import (
    DEFAULT_CONFIG,
    SecretsConfig,
    _load_from_env,
    _load_from_yaml,
    _parse_strategy,
    get_secrets_config,
)
from git_notes_memory.security.models import FilterStrategy


class TestSecretsConfigDefaults:
    """Test SecretsConfig default values."""

    def test_default_enabled(self) -> None:
        """Test that filtering is enabled by default."""
        config = SecretsConfig()
        assert config.enabled is True

    def test_default_strategy(self) -> None:
        """Test that default strategy is REDACT."""
        config = SecretsConfig()
        assert config.default_strategy == FilterStrategy.REDACT

    def test_default_entropy_enabled(self) -> None:
        """Test that entropy detection is enabled by default."""
        config = SecretsConfig()
        assert config.entropy_enabled is True

    def test_default_pii_enabled(self) -> None:
        """Test that PII detection is enabled by default."""
        config = SecretsConfig()
        assert config.pii_enabled is True

    def test_default_audit_enabled(self) -> None:
        """Test that audit logging is enabled by default."""
        config = SecretsConfig()
        assert config.audit_enabled is True

    def test_default_confidence_threshold(self) -> None:
        """Test default confidence threshold."""
        config = SecretsConfig()
        assert config.confidence_threshold == 0.5


class TestSecretsConfigNamespaceStrategies:
    """Test SecretsConfig namespace strategy handling."""

    def test_namespace_strategies_dict(self) -> None:
        """Test namespace_strategies_dict property."""
        config = SecretsConfig(
            namespace_strategies=(
                ("decisions", FilterStrategy.WARN),
                ("progress", FilterStrategy.MASK),
            )
        )
        strategies = config.namespace_strategies_dict
        assert strategies["decisions"] == FilterStrategy.WARN
        assert strategies["progress"] == FilterStrategy.MASK

    def test_get_strategy_for_namespace_found(self) -> None:
        """Test getting strategy for a configured namespace."""
        config = SecretsConfig(
            namespace_strategies=(("decisions", FilterStrategy.WARN),),
            default_strategy=FilterStrategy.REDACT,
        )
        assert config.get_strategy_for_namespace("decisions") == FilterStrategy.WARN

    def test_get_strategy_for_namespace_default(self) -> None:
        """Test getting strategy for unconfigured namespace uses default."""
        config = SecretsConfig(
            namespace_strategies=(("decisions", FilterStrategy.WARN),),
            default_strategy=FilterStrategy.REDACT,
        )
        assert config.get_strategy_for_namespace("progress") == FilterStrategy.REDACT


class TestParseStrategy:
    """Test the _parse_strategy function."""

    def test_parse_valid_strategies(self) -> None:
        """Test parsing all valid strategy values."""
        assert _parse_strategy("redact") == FilterStrategy.REDACT
        assert _parse_strategy("mask") == FilterStrategy.MASK
        assert _parse_strategy("block") == FilterStrategy.BLOCK
        assert _parse_strategy("warn") == FilterStrategy.WARN

    def test_parse_case_insensitive(self) -> None:
        """Test that strategy parsing is case-insensitive."""
        assert _parse_strategy("REDACT") == FilterStrategy.REDACT
        assert _parse_strategy("Mask") == FilterStrategy.MASK
        assert _parse_strategy("BLOCK") == FilterStrategy.BLOCK
        assert _parse_strategy("WaRn") == FilterStrategy.WARN

    def test_parse_invalid_strategy(self) -> None:
        """Test that invalid strategy raises ValueError."""
        with pytest.raises(ValueError, match="Invalid strategy 'invalid'"):
            _parse_strategy("invalid")

    def test_parse_empty_strategy(self) -> None:
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid strategy ''"):
            _parse_strategy("")


class TestLoadFromEnv:
    """Test the _load_from_env function."""

    def test_empty_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test with no environment variables set."""
        # Clear all SECRETS_FILTER_ vars
        for key in list(os.environ.keys()):
            if key.startswith("SECRETS_FILTER_"):
                monkeypatch.delenv(key, raising=False)

        config = _load_from_env()
        assert config == {}

    def test_enabled_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_ENABLED=true."""
        monkeypatch.setenv("SECRETS_FILTER_ENABLED", "true")
        config = _load_from_env()
        assert config["enabled"] is True

    def test_enabled_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_ENABLED=false."""
        monkeypatch.setenv("SECRETS_FILTER_ENABLED", "false")
        config = _load_from_env()
        assert config["enabled"] is False

    def test_entropy_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_ENTROPY_ENABLED."""
        monkeypatch.setenv("SECRETS_FILTER_ENTROPY_ENABLED", "false")
        config = _load_from_env()
        assert config["entropy_enabled"] is False

    def test_pii_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_PII_ENABLED."""
        monkeypatch.setenv("SECRETS_FILTER_PII_ENABLED", "false")
        config = _load_from_env()
        assert config["pii_enabled"] is False

    def test_audit_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_AUDIT_ENABLED."""
        monkeypatch.setenv("SECRETS_FILTER_AUDIT_ENABLED", "false")
        config = _load_from_env()
        assert config["audit_enabled"] is False

    def test_default_strategy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_DEFAULT_STRATEGY."""
        monkeypatch.setenv("SECRETS_FILTER_DEFAULT_STRATEGY", "block")
        config = _load_from_env()
        assert config["default_strategy"] == FilterStrategy.BLOCK

    def test_allowlist_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_ALLOWLIST_PATH."""
        monkeypatch.setenv("SECRETS_FILTER_ALLOWLIST_PATH", "/custom/allowlist.yaml")
        config = _load_from_env()
        assert config["allowlist_path"] == Path("/custom/allowlist.yaml")

    def test_audit_log_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_AUDIT_LOG_PATH."""
        monkeypatch.setenv("SECRETS_FILTER_AUDIT_LOG_PATH", "/custom/audit.jsonl")
        config = _load_from_env()
        assert config["audit_log_path"] == Path("/custom/audit.jsonl")

    def test_confidence_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_CONFIDENCE_THRESHOLD."""
        monkeypatch.setenv("SECRETS_FILTER_CONFIDENCE_THRESHOLD", "0.8")
        config = _load_from_env()
        assert config["confidence_threshold"] == 0.8

    def test_detectors_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test SECRETS_FILTER_DETECTORS_DISABLED."""
        monkeypatch.setenv(
            "SECRETS_FILTER_DETECTORS_DISABLED", "HighEntropyStrings, JwtToken"
        )
        config = _load_from_env()
        assert config["detectors_disabled"] == ("HighEntropyStrings", "JwtToken")

    def test_detectors_disabled_empty_items(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test SECRETS_FILTER_DETECTORS_DISABLED with empty items filtered."""
        monkeypatch.setenv(
            "SECRETS_FILTER_DETECTORS_DISABLED", "HighEntropyStrings,,  ,JwtToken"
        )
        config = _load_from_env()
        assert config["detectors_disabled"] == ("HighEntropyStrings", "JwtToken")


class TestLoadFromYaml:
    """Test the _load_from_yaml function."""

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Test loading from non-existent file returns empty dict."""
        config = _load_from_yaml(tmp_path / "nonexistent.yaml")
        assert config == {}

    def test_empty_file(self, tmp_path: Path) -> None:
        """Test loading from empty file returns empty dict."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        config = _load_from_yaml(config_file)
        assert config == {}

    def test_non_dict_content(self, tmp_path: Path) -> None:
        """Test loading file with non-dict content returns empty dict."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("- item1\n- item2\n")
        config = _load_from_yaml(config_file)
        assert config == {}

    def test_basic_config(self, tmp_path: Path) -> None:
        """Test loading basic configuration."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
secrets_filtering:
  enabled: false
  entropy_enabled: false
  pii_enabled: false
  audit_enabled: false
""")
        config = _load_from_yaml(config_file)
        assert config["enabled"] is False
        assert config["entropy_enabled"] is False
        assert config["pii_enabled"] is False
        assert config["audit_enabled"] is False

    def test_default_strategy(self, tmp_path: Path) -> None:
        """Test loading default_strategy from YAML."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
secrets_filtering:
  default_strategy: warn
""")
        config = _load_from_yaml(config_file)
        assert config["default_strategy"] == FilterStrategy.WARN

    def test_namespace_strategies(self, tmp_path: Path) -> None:
        """Test loading namespace_strategies from YAML."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
secrets_filtering:
  namespace_strategies:
    decisions: warn
    progress: mask
""")
        config = _load_from_yaml(config_file)
        strategies = config["namespace_strategies"]
        assert isinstance(strategies, tuple)
        # Convert to dict for easier testing
        strategies_dict = dict(strategies)
        assert strategies_dict["decisions"] == FilterStrategy.WARN
        assert strategies_dict["progress"] == FilterStrategy.MASK

    def test_paths(self, tmp_path: Path) -> None:
        """Test loading path settings from YAML."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
secrets_filtering:
  allowlist_path: /custom/allowlist.yaml
  audit_log_path: /custom/audit.jsonl
""")
        config = _load_from_yaml(config_file)
        assert config["allowlist_path"] == Path("/custom/allowlist.yaml")
        assert config["audit_log_path"] == Path("/custom/audit.jsonl")

    def test_confidence_threshold(self, tmp_path: Path) -> None:
        """Test loading confidence_threshold from YAML."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
secrets_filtering:
  confidence_threshold: 0.75
""")
        config = _load_from_yaml(config_file)
        assert config["confidence_threshold"] == 0.75

    def test_detectors_enabled(self, tmp_path: Path) -> None:
        """Test loading detectors_enabled list from YAML."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
secrets_filtering:
  detectors_enabled:
    - AwsKeyDetector
    - GitHubTokenDetector
""")
        config = _load_from_yaml(config_file)
        assert config["detectors_enabled"] == ("AwsKeyDetector", "GitHubTokenDetector")

    def test_detectors_disabled(self, tmp_path: Path) -> None:
        """Test loading detectors_disabled list from YAML."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
secrets_filtering:
  detectors_disabled:
    - HighEntropyStrings
    - JwtToken
""")
        config = _load_from_yaml(config_file)
        assert config["detectors_disabled"] == ("HighEntropyStrings", "JwtToken")

    def test_top_level_config(self, tmp_path: Path) -> None:
        """Test loading config from top level (no secrets_filtering key)."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
enabled: false
default_strategy: block
""")
        config = _load_from_yaml(config_file)
        assert config["enabled"] is False
        assert config["default_strategy"] == FilterStrategy.BLOCK

    def test_invalid_namespace_strategies(self, tmp_path: Path) -> None:
        """Test that invalid namespace_strategies is ignored."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
secrets_filtering:
  namespace_strategies: "not a dict"
""")
        config = _load_from_yaml(config_file)
        assert "namespace_strategies" not in config

    def test_invalid_detectors_lists(self, tmp_path: Path) -> None:
        """Test that invalid detector lists are ignored."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
secrets_filtering:
  detectors_enabled: "not a list"
  detectors_disabled: 123
""")
        config = _load_from_yaml(config_file)
        assert "detectors_enabled" not in config
        assert "detectors_disabled" not in config


class TestGetSecretsConfig:
    """Test the get_secrets_config function."""

    def test_defaults_with_no_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test getting config with no YAML file and no env vars."""
        # Clear environment
        for key in list(os.environ.keys()):
            if key.startswith("SECRETS_FILTER_"):
                monkeypatch.delenv(key, raising=False)
        # Use tmp_path as home to avoid finding real config files
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        config = get_secrets_config(data_dir=tmp_path)
        assert config.enabled is True
        assert config.default_strategy == FilterStrategy.REDACT
        assert config.allowlist_path == tmp_path / "secrets-allowlist.yaml"
        assert config.audit_log_path == tmp_path / "secrets-audit.jsonl"

    def test_yaml_config_loaded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that YAML config is loaded when present."""
        # Clear environment
        for key in list(os.environ.keys()):
            if key.startswith("SECRETS_FILTER_"):
                monkeypatch.delenv(key, raising=False)

        config_file = tmp_path / ".memory-secrets.yaml"
        config_file.write_text("""
secrets_filtering:
  enabled: false
  default_strategy: warn
""")
        monkeypatch.chdir(tmp_path)

        config = get_secrets_config(data_dir=tmp_path)
        assert config.enabled is False
        assert config.default_strategy == FilterStrategy.WARN

    def test_explicit_config_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test loading from explicit config path."""
        # Clear environment
        for key in list(os.environ.keys()):
            if key.startswith("SECRETS_FILTER_"):
                monkeypatch.delenv(key, raising=False)

        config_file = tmp_path / "custom-config.yaml"
        config_file.write_text("""
secrets_filtering:
  default_strategy: block
""")

        config = get_secrets_config(config_path=config_file, data_dir=tmp_path)
        assert config.default_strategy == FilterStrategy.BLOCK

    def test_env_overrides_yaml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that environment variables override YAML config."""
        config_file = tmp_path / ".memory-secrets.yaml"
        config_file.write_text("""
secrets_filtering:
  enabled: false
  default_strategy: warn
""")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SECRETS_FILTER_ENABLED", "true")
        monkeypatch.setenv("SECRETS_FILTER_DEFAULT_STRATEGY", "block")

        config = get_secrets_config(data_dir=tmp_path)
        assert config.enabled is True  # Env overrides YAML
        assert config.default_strategy == FilterStrategy.BLOCK  # Env overrides YAML

    def test_data_dir_from_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that data_dir is loaded from MEMORY_PLUGIN_DATA_DIR."""
        # Clear environment
        for key in list(os.environ.keys()):
            if key.startswith("SECRETS_FILTER_"):
                monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.chdir(tmp_path)

        custom_data_dir = tmp_path / "custom_data"
        monkeypatch.setenv("MEMORY_PLUGIN_DATA_DIR", str(custom_data_dir))

        config = get_secrets_config()
        assert config.allowlist_path == custom_data_dir / "secrets-allowlist.yaml"
        assert config.audit_log_path == custom_data_dir / "secrets-audit.jsonl"


class TestDefaultConfig:
    """Test the DEFAULT_CONFIG constant."""

    def test_default_config_is_secrets_config(self) -> None:
        """Test that DEFAULT_CONFIG is a SecretsConfig instance."""
        assert isinstance(DEFAULT_CONFIG, SecretsConfig)

    def test_default_config_has_expected_defaults(self) -> None:
        """Test that DEFAULT_CONFIG has expected default values."""
        assert DEFAULT_CONFIG.enabled is True
        assert DEFAULT_CONFIG.default_strategy == FilterStrategy.REDACT
        assert DEFAULT_CONFIG.entropy_enabled is True
        assert DEFAULT_CONFIG.pii_enabled is True
