"""Export backends for observability data.

This subpackage provides exporters for:
- Prometheus text format (stdlib only)
- OTLP (requires opentelemetry-exporter-otlp)
- prometheus-client integration (requires prometheus-client)

All exporters gracefully degrade when optional dependencies are not installed.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "export_prometheus_text",
    "export_json",
    "PrometheusExporter",
]


def __getattr__(name: str) -> Any:
    """Lazy import implementation for exporters."""
    if name == "export_prometheus_text":
        from git_notes_memory.observability.exporters.prometheus import (
            export_prometheus_text,
        )

        return export_prometheus_text

    if name == "PrometheusExporter":
        from git_notes_memory.observability.exporters.prometheus import (
            PrometheusExporter,
        )

        return PrometheusExporter

    if name == "export_json":
        from git_notes_memory.observability.exporters.json_exporter import (
            export_json,
        )

        return export_json

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
