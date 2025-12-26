"""Export backends for observability data.

This subpackage provides exporters for:
- Prometheus text format (stdlib only)
- OTLP HTTP (stdlib only - no opentelemetry SDK required)
- JSON format (stdlib only)

All exporters use stdlib only for zero additional dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Explicit imports for static analysis and runtime use
from git_notes_memory.observability.exporters.json_exporter import export_json
from git_notes_memory.observability.exporters.otlp import (
    OTLPExporter,
    export_metrics_if_configured,
    export_traces_if_configured,
    get_otlp_exporter,
)
from git_notes_memory.observability.exporters.prometheus import (
    PrometheusExporter,
    export_prometheus_text,
)

__all__ = [
    "export_prometheus_text",
    "export_json",
    "PrometheusExporter",
    "OTLPExporter",
    "get_otlp_exporter",
    "export_traces_if_configured",
    "export_metrics_if_configured",
]


if TYPE_CHECKING:
    # Re-export for type checkers
    pass


def __getattr__(name: str) -> Any:
    """Lazy import fallback for any additional exports."""
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
