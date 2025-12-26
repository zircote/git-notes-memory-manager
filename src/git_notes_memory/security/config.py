"""Configuration for the secrets filtering system.

Provides configuration loading from environment variables, YAML files,
and default values. Supports per-namespace strategy overrides.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from git_notes_memory.security.models import FilterStrategy

__all__ = [
    "SecretsConfig",
    "get_secrets_config",
    "DEFAULT_CONFIG",
]


@dataclass(frozen=True)
class SecretsConfig:
    """Configuration for secrets filtering.

    Attributes:
        enabled: Whether secrets filtering is enabled
        default_strategy: Default strategy for handling detected secrets
        namespace_strategies: Per-namespace strategy overrides
        entropy_enabled: Whether to check for high-entropy strings
        pii_enabled: Whether to detect PII (SSN, credit cards, phone)
        allowlist_path: Path to the allowlist YAML file
        audit_log_path: Path to the audit log file
        audit_enabled: Whether to log filtering events
        detectors_enabled: List of detect-secrets plugins to enable (empty = all)
        detectors_disabled: List of detect-secrets plugins to disable
        confidence_threshold: Minimum confidence to report a detection (0.0 - 1.0)
    """

    enabled: bool = True
    default_strategy: FilterStrategy = FilterStrategy.REDACT
    namespace_strategies: tuple[tuple[str, FilterStrategy], ...] = field(
        default_factory=tuple
    )
    entropy_enabled: bool = True
    pii_enabled: bool = True
    allowlist_path: Path | None = None
    audit_log_path: Path | None = None
    audit_enabled: bool = True
    detectors_enabled: tuple[str, ...] = field(default_factory=tuple)
    detectors_disabled: tuple[str, ...] = field(default_factory=tuple)
    confidence_threshold: float = 0.5

    @property
    def namespace_strategies_dict(self) -> dict[str, FilterStrategy]:
        """Get namespace strategies as a dictionary."""
        return dict(self.namespace_strategies)

    def get_strategy_for_namespace(self, namespace: str) -> FilterStrategy:
        """Get the filtering strategy for a specific namespace.

        Args:
            namespace: The memory namespace.

        Returns:
            The strategy to use for this namespace.
        """
        strategies = self.namespace_strategies_dict
        return strategies.get(namespace, self.default_strategy)


def _parse_strategy(value: str) -> FilterStrategy:
    """Parse a strategy string to FilterStrategy enum.

    Args:
        value: Strategy string (case-insensitive).

    Returns:
        The corresponding FilterStrategy.

    Raises:
        ValueError: If the strategy is not recognized.
    """
    try:
        return FilterStrategy(value.lower())
    except ValueError:
        valid = ", ".join(s.value for s in FilterStrategy)
        msg = f"Invalid strategy '{value}'. Valid strategies: {valid}"
        raise ValueError(msg) from None


def _load_from_env() -> dict[str, object]:
    """Load configuration from environment variables.

    Environment variables:
        SECRETS_FILTER_ENABLED: "true" or "false"
        SECRETS_FILTER_DEFAULT_STRATEGY: "redact", "mask", "block", "warn"
        SECRETS_FILTER_ENTROPY_ENABLED: "true" or "false"
        SECRETS_FILTER_PII_ENABLED: "true" or "false"
        SECRETS_FILTER_ALLOWLIST_PATH: Path to allowlist file
        SECRETS_FILTER_AUDIT_LOG_PATH: Path to audit log
        SECRETS_FILTER_AUDIT_ENABLED: "true" or "false"
        SECRETS_FILTER_CONFIDENCE_THRESHOLD: Float 0.0-1.0
        SECRETS_FILTER_DETECTORS_DISABLED: Comma-separated list

    Returns:
        Dictionary of configuration values from environment.
    """
    config: dict[str, object] = {}

    # Boolean settings
    if enabled := os.environ.get("SECRETS_FILTER_ENABLED"):
        config["enabled"] = enabled.lower() == "true"

    if entropy := os.environ.get("SECRETS_FILTER_ENTROPY_ENABLED"):
        config["entropy_enabled"] = entropy.lower() == "true"

    if pii := os.environ.get("SECRETS_FILTER_PII_ENABLED"):
        config["pii_enabled"] = pii.lower() == "true"

    if audit := os.environ.get("SECRETS_FILTER_AUDIT_ENABLED"):
        config["audit_enabled"] = audit.lower() == "true"

    # Strategy
    if strategy := os.environ.get("SECRETS_FILTER_DEFAULT_STRATEGY"):
        config["default_strategy"] = _parse_strategy(strategy)

    # Paths
    if allowlist := os.environ.get("SECRETS_FILTER_ALLOWLIST_PATH"):
        config["allowlist_path"] = Path(allowlist)

    if audit_log := os.environ.get("SECRETS_FILTER_AUDIT_LOG_PATH"):
        config["audit_log_path"] = Path(audit_log)

    # Confidence threshold
    if threshold := os.environ.get("SECRETS_FILTER_CONFIDENCE_THRESHOLD"):
        config["confidence_threshold"] = float(threshold)

    # Disabled detectors
    if disabled := os.environ.get("SECRETS_FILTER_DETECTORS_DISABLED"):
        config["detectors_disabled"] = tuple(
            d.strip() for d in disabled.split(",") if d.strip()
        )

    return config


def _load_from_yaml(path: Path) -> dict[str, object]:
    """Load configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Dictionary of configuration values from the file.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        yaml.YAMLError: If the file is not valid YAML.
    """
    config: dict[str, object] = {}

    if not path.exists():
        return config

    with path.open() as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return config

    # Get the secrets_filtering section - cast to Any for YAML flexibility
    raw_config: Any = data.get("secrets_filtering", data)
    if not isinstance(raw_config, dict):
        return config
    secrets_config: dict[str, Any] = raw_config

    # Boolean settings
    if "enabled" in secrets_config:
        config["enabled"] = bool(secrets_config["enabled"])

    if "entropy_enabled" in secrets_config:
        config["entropy_enabled"] = bool(secrets_config["entropy_enabled"])

    if "pii_enabled" in secrets_config:
        config["pii_enabled"] = bool(secrets_config["pii_enabled"])

    if "audit_enabled" in secrets_config:
        config["audit_enabled"] = bool(secrets_config["audit_enabled"])

    # Strategy
    if "default_strategy" in secrets_config:
        config["default_strategy"] = _parse_strategy(
            str(secrets_config["default_strategy"])
        )

    # Namespace strategies
    if "namespace_strategies" in secrets_config:
        ns_strategies: Any = secrets_config["namespace_strategies"]
        if isinstance(ns_strategies, dict):
            config["namespace_strategies"] = tuple(
                (str(ns), _parse_strategy(str(strategy)))
                for ns, strategy in ns_strategies.items()
            )

    # Paths
    if "allowlist_path" in secrets_config:
        config["allowlist_path"] = Path(str(secrets_config["allowlist_path"]))

    if "audit_log_path" in secrets_config:
        config["audit_log_path"] = Path(str(secrets_config["audit_log_path"]))

    # Confidence threshold
    if "confidence_threshold" in secrets_config:
        config["confidence_threshold"] = float(secrets_config["confidence_threshold"])

    # Detector lists
    if "detectors_enabled" in secrets_config:
        enabled_list: Any = secrets_config["detectors_enabled"]
        if isinstance(enabled_list, list):
            config["detectors_enabled"] = tuple(str(x) for x in enabled_list)

    if "detectors_disabled" in secrets_config:
        disabled_list: Any = secrets_config["detectors_disabled"]
        if isinstance(disabled_list, list):
            config["detectors_disabled"] = tuple(str(x) for x in disabled_list)

    return config


def get_secrets_config(
    config_path: Path | None = None,
    data_dir: Path | None = None,
) -> SecretsConfig:
    """Get the secrets filtering configuration.

    Configuration is loaded in priority order:
    1. Environment variables (highest priority)
    2. YAML config file (if provided or found)
    3. Default values (lowest priority)

    Args:
        config_path: Optional path to YAML config file.
        data_dir: Optional data directory for allowlist/audit paths.

    Returns:
        The secrets filtering configuration.
    """
    # Start with defaults
    config: dict[str, object] = {}

    # Load from YAML if provided or found in standard locations
    yaml_paths = []
    if config_path:
        yaml_paths.append(config_path)

    # Standard config locations
    yaml_paths.extend(
        [
            Path.cwd() / ".memory-secrets.yaml",
            Path.cwd() / ".claude" / "memory-secrets.yaml",
            Path.home() / ".config" / "memory-plugin" / "secrets.yaml",
        ]
    )

    for path in yaml_paths:
        if path.exists():
            config.update(_load_from_yaml(path))
            break

    # Override with environment variables
    config.update(_load_from_env())

    # Set default paths if not configured
    if data_dir is None:
        data_dir = Path(
            os.environ.get(
                "MEMORY_PLUGIN_DATA_DIR",
                Path.home() / ".local" / "share" / "memory-plugin",
            )
        )

    if "allowlist_path" not in config:
        config["allowlist_path"] = data_dir / "secrets-allowlist.yaml"

    if "audit_log_path" not in config:
        config["audit_log_path"] = data_dir / "secrets-audit.jsonl"

    return SecretsConfig(**config)  # type: ignore[arg-type]


# Default configuration instance
DEFAULT_CONFIG = SecretsConfig()
