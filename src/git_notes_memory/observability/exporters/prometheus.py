"""Prometheus text format exporter.

Exports metrics in Prometheus exposition format without requiring
the prometheus-client library. This allows basic metrics export
with zero additional dependencies.

Usage:
    from git_notes_memory.observability.exporters import export_prometheus_text

    # Get metrics in Prometheus format
    text = export_prometheus_text()
    print(text)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_notes_memory.observability.metrics import get_metrics

if TYPE_CHECKING:
    from git_notes_memory.observability.metrics import MetricsCollector


def _format_labels(labels: frozenset[tuple[str, str]]) -> str:
    """Format labels as Prometheus label string."""
    if not labels:
        return ""
    label_parts = [f'{k}="{v}"' for k, v in sorted(labels)]
    return "{" + ",".join(label_parts) + "}"


def _format_metric_line(
    name: str,
    labels: frozenset[tuple[str, str]],
    value: float,
    suffix: str = "",
) -> str:
    """Format a single metric line in Prometheus format."""
    full_name = f"{name}{suffix}" if suffix else name
    label_str = _format_labels(labels)
    return f"{full_name}{label_str} {value}"


def export_prometheus_text() -> str:
    """Export all metrics in Prometheus text exposition format.

    Returns:
        String containing all metrics in Prometheus format.

    Example output:
        # HELP memories_captured_total Total memories captured
        # TYPE memories_captured_total counter
        memories_captured_total{namespace="decisions"} 42

        # HELP capture_duration_ms_bucket Capture operation duration
        # TYPE capture_duration_ms_bucket histogram
        capture_duration_ms_bucket{le="10"} 5
        capture_duration_ms_bucket{le="50"} 15
        capture_duration_ms_bucket{le="+Inf"} 20
        capture_duration_ms_sum 1234.5
        capture_duration_ms_count 20
    """
    metrics = get_metrics()
    lines: list[str] = []

    # Access internal state (for export purposes)
    with metrics._lock:
        # Export counters
        for counter_name, counter_label_values in sorted(metrics._counters.items()):
            lines.append(f"# HELP {counter_name} Counter metric")
            lines.append(f"# TYPE {counter_name} counter")
            for labels, counter in counter_label_values.items():
                lines.append(_format_metric_line(counter_name, labels, counter.value))
            lines.append("")

        # Export histograms
        for hist_name, hist_label_values in sorted(metrics._histograms.items()):
            lines.append(f"# HELP {hist_name} Histogram metric")
            lines.append(f"# TYPE {hist_name} histogram")
            for labels, histogram in hist_label_values.items():
                # Bucket counts (cumulative)
                cumulative = 0
                for bucket in sorted(histogram.buckets):
                    cumulative += histogram.bucket_counts.get(bucket, 0)
                    bucket_labels = frozenset(labels | {("le", _format_le(bucket))})
                    lines.append(
                        _format_metric_line(
                            hist_name, bucket_labels, cumulative, "_bucket"
                        )
                    )

                # Sum and count
                lines.append(
                    _format_metric_line(hist_name, labels, histogram.sum_value, "_sum")
                )
                lines.append(
                    _format_metric_line(
                        hist_name, labels, float(histogram.count), "_count"
                    )
                )
            lines.append("")

        # Export gauges
        for gauge_name, gauge_label_values in sorted(metrics._gauges.items()):
            lines.append(f"# HELP {gauge_name} Gauge metric")
            lines.append(f"# TYPE {gauge_name} gauge")
            for labels, gauge in gauge_label_values.items():
                lines.append(_format_metric_line(gauge_name, labels, gauge.value))
            lines.append("")

    return "\n".join(lines)


def _format_le(value: float) -> str:
    """Format a bucket boundary for the 'le' label."""
    if value == float("inf"):
        return "+Inf"
    if value == int(value):
        return str(int(value))
    return str(value)


class PrometheusExporter:
    """Prometheus text format exporter class.

    Provides a class-based interface for exporting metrics in Prometheus format.
    """

    def export(self, metrics: MetricsCollector | None = None) -> str:
        """Export metrics in Prometheus text exposition format.

        Args:
            metrics: Optional MetricsCollector instance. If not provided,
                uses the global singleton.

        Returns:
            String containing all metrics in Prometheus format.
        """
        if metrics is None:
            return export_prometheus_text()

        lines: list[str] = []

        # Access internal state (for export purposes)
        with metrics._lock:
            # Export counters
            for counter_name, counter_label_values in sorted(metrics._counters.items()):
                lines.append(f"# HELP {counter_name} Counter metric")
                lines.append(f"# TYPE {counter_name} counter")
                for labels, counter in counter_label_values.items():
                    lines.append(
                        _format_metric_line(counter_name, labels, counter.value)
                    )
                lines.append("")

            # Export histograms
            for hist_name, hist_label_values in sorted(metrics._histograms.items()):
                lines.append(f"# HELP {hist_name} Histogram metric")
                lines.append(f"# TYPE {hist_name} histogram")
                for labels, histogram in hist_label_values.items():
                    # Bucket counts (cumulative)
                    cumulative = 0
                    for bucket in sorted(histogram.buckets):
                        cumulative += histogram.bucket_counts.get(bucket, 0)
                        bucket_labels = frozenset(labels | {("le", _format_le(bucket))})
                        lines.append(
                            _format_metric_line(
                                hist_name, bucket_labels, cumulative, "_bucket"
                            )
                        )

                    # Sum and count
                    lines.append(
                        _format_metric_line(
                            hist_name, labels, histogram.sum_value, "_sum"
                        )
                    )
                    lines.append(
                        _format_metric_line(
                            hist_name, labels, float(histogram.count), "_count"
                        )
                    )
                lines.append("")

            # Export gauges
            for gauge_name, gauge_label_values in sorted(metrics._gauges.items()):
                lines.append(f"# HELP {gauge_name} Gauge metric")
                lines.append(f"# TYPE {gauge_name} gauge")
                for labels, gauge in gauge_label_values.items():
                    lines.append(_format_metric_line(gauge_name, labels, gauge.value))
                lines.append("")

        return "\n".join(lines)
