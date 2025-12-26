"""Export backends for observability data.

This subpackage provides exporters for:
- Prometheus text format (stdlib only)
- OTLP (requires opentelemetry-exporter-otlp)
- prometheus-client integration (requires prometheus-client)

All exporters gracefully degrade when optional dependencies are not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Explicit imports for static analysis and runtime use
from git_notes_memory.observability.exporters.json_exporter import export_json
from git_notes_memory.observability.exporters.prometheus import (
    PrometheusExporter,
    export_prometheus_text,
)

__all__ = [
    "export_prometheus_text",
    "export_json",
    "PrometheusExporter",
]


if TYPE_CHECKING:
    # Re-export for type checkers
    pass


def __getattr__(name: str) -> Any:
    """Lazy import fallback for any additional exports."""
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
