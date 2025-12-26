"""JSON format exporter for observability data.

Exports metrics and traces in JSON format for analysis,
debugging, or integration with JSON-based systems.

Usage:
    from git_notes_memory.observability.exporters import export_json

    # Get all observability data as JSON
    data = export_json()
    print(data)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from git_notes_memory.observability.config import get_config
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.session import get_session_info
from git_notes_memory.observability.tracing import get_completed_spans


def export_json(
    include_metrics: bool = True,
    include_traces: bool = True,
    include_session: bool = True,
    indent: int = 2,
) -> str:
    """Export all observability data as JSON.

    Args:
        include_metrics: Include metrics data (default True).
        include_traces: Include completed traces (default True).
        include_session: Include session info (default True).
        indent: JSON indentation level (default 2).

    Returns:
        JSON string containing requested observability data.
    """
    config = get_config()
    data: dict[str, Any] = {
        "export_time": datetime.now(tz=UTC).isoformat(),
        "service_name": config.service_name,
    }

    # Add session info
    if include_session and config.enabled:
        session = get_session_info()
        data["session"] = session.to_dict()

    # Add metrics
    if include_metrics and config.enabled and config.metrics_enabled:
        metrics = get_metrics()
        # Parse the JSON from metrics export
        metrics_data = json.loads(metrics.export_json())
        data["metrics"] = metrics_data

    # Add traces
    if include_traces and config.enabled and config.tracing_enabled:
        spans = get_completed_spans()
        data["traces"] = [span.to_dict() for span in spans]

    return json.dumps(data, indent=indent)


def export_metrics_json(indent: int = 2) -> str:
    """Export only metrics as JSON.

    Args:
        indent: JSON indentation level.

    Returns:
        JSON string containing metrics data.
    """
    return export_json(
        include_metrics=True,
        include_traces=False,
        include_session=False,
        indent=indent,
    )


def export_traces_json(indent: int = 2) -> str:
    """Export only traces as JSON.

    Args:
        indent: JSON indentation level.

    Returns:
        JSON string containing trace data.
    """
    return export_json(
        include_metrics=False,
        include_traces=True,
        include_session=False,
        indent=indent,
    )
