"""Thread-safe in-memory metrics collection.

Provides counters, histograms, and gauges without external dependencies.
Designed for short-lived hook processes with bounded memory usage.

Usage:
    from git_notes_memory.observability import get_metrics

    metrics = get_metrics()
    metrics.increment("memories_captured_total", labels={"namespace": "decisions"})
    metrics.observe("capture_duration_ms", 150.5)
    metrics.set_gauge("active_connections", 3)
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from git_notes_memory.observability.config import get_config

# Default histogram buckets aligned with hook timeouts
# Values in milliseconds for clarity
DEFAULT_LATENCY_BUCKETS: tuple[float, ...] = (
    1,
    2,
    5,
    10,
    25,
    50,
    100,  # Sub-100ms operations
    250,
    500,
    750,
    1000,  # Sub-second (UserPromptSubmit 2s)
    2000,
    5000,  # 2-5s (SessionStart, Stop)
    10000,
    15000,
    30000,  # 10-30s (PreCompact, default)
    float("inf"),
)


def _freeze_labels(labels: dict[str, str] | None) -> frozenset[tuple[str, str]]:
    """Convert mutable labels dict to immutable frozenset for storage."""
    if not labels:
        return frozenset()
    return frozenset(labels.items())


def _labels_to_dict(frozen_labels: frozenset[tuple[str, str]]) -> dict[str, str]:
    """Convert frozen labels back to dict for export."""
    return dict(frozen_labels)


@dataclass
class CounterValue:
    """Atomic counter value with labels."""

    value: float = 0.0
    created_at: float = field(default_factory=time.time)

    def increment(self, amount: float = 1.0) -> None:
        """Increment the counter value."""
        self.value += amount


@dataclass
class HistogramValue:
    """Histogram with configurable buckets and rolling window samples."""

    buckets: tuple[float, ...] = DEFAULT_LATENCY_BUCKETS
    samples: deque[float] = field(default_factory=lambda: deque(maxlen=3600))
    sum_value: float = 0.0
    count: int = 0
    bucket_counts: dict[float, int] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Initialize bucket counts."""
        if not self.bucket_counts:
            self.bucket_counts = dict.fromkeys(self.buckets, 0)

    def observe(self, value: float) -> None:
        """Record an observation."""
        self.samples.append(value)
        self.sum_value += value
        self.count += 1

        # Update bucket counts
        for bucket in self.buckets:
            if value <= bucket:
                self.bucket_counts[bucket] = self.bucket_counts.get(bucket, 0) + 1
                break


@dataclass
class GaugeValue:
    """Point-in-time gauge value."""

    value: float = 0.0
    updated_at: float = field(default_factory=time.time)

    def set(self, value: float) -> None:
        """Set the gauge value."""
        self.value = value
        self.updated_at = time.time()

    def increment(self, amount: float = 1.0) -> None:
        """Increment the gauge value."""
        self.value += amount
        self.updated_at = time.time()

    def decrement(self, amount: float = 1.0) -> None:
        """Decrement the gauge value."""
        self.value -= amount
        self.updated_at = time.time()


class MetricsCollector:
    """Thread-safe in-memory metrics collection.

    Stores counters, histograms, and gauges with label support.
    Uses a rolling window for histogram samples to bound memory.

    Thread safety is achieved via a single lock protecting all state.
    This is acceptable for the expected low contention in hook processes.
    """

    def __init__(self, max_samples: int = 3600) -> None:
        """Initialize the metrics collector.

        Args:
            max_samples: Maximum samples to retain per histogram (rolling window).
        """
        self._lock = threading.Lock()
        self._max_samples = max_samples

        # Metric storage: name -> labels_frozenset -> value
        self._counters: dict[str, dict[frozenset[tuple[str, str]], CounterValue]] = {}
        self._histograms: dict[
            str, dict[frozenset[tuple[str, str]], HistogramValue]
        ] = {}
        self._gauges: dict[str, dict[frozenset[tuple[str, str]], GaugeValue]] = {}

    def increment(
        self,
        name: str,
        amount: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter.

        Args:
            name: Metric name (e.g., "memories_captured_total").
            amount: Amount to increment by (default 1.0).
            labels: Optional labels dict (e.g., {"namespace": "decisions"}).
        """
        config = get_config()
        if not config.enabled or not config.metrics_enabled:
            return

        frozen_labels = _freeze_labels(labels)

        with self._lock:
            if name not in self._counters:
                self._counters[name] = {}

            if frozen_labels not in self._counters[name]:
                self._counters[name][frozen_labels] = CounterValue()

            self._counters[name][frozen_labels].increment(amount)

    def observe(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        """Record an observation in a histogram.

        Args:
            name: Metric name (e.g., "capture_duration_ms").
            value: Observed value.
            labels: Optional labels dict.
            buckets: Custom bucket boundaries (uses DEFAULT_LATENCY_BUCKETS if not set).
        """
        config = get_config()
        if not config.enabled or not config.metrics_enabled:
            return

        frozen_labels = _freeze_labels(labels)
        effective_buckets = buckets or DEFAULT_LATENCY_BUCKETS

        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = {}

            if frozen_labels not in self._histograms[name]:
                self._histograms[name][frozen_labels] = HistogramValue(
                    buckets=effective_buckets,
                    samples=deque(maxlen=self._max_samples),
                )

            self._histograms[name][frozen_labels].observe(value)

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge value.

        Args:
            name: Metric name (e.g., "active_connections").
            value: Current value.
            labels: Optional labels dict.
        """
        config = get_config()
        if not config.enabled or not config.metrics_enabled:
            return

        frozen_labels = _freeze_labels(labels)

        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = {}

            if frozen_labels not in self._gauges[name]:
                self._gauges[name][frozen_labels] = GaugeValue()

            self._gauges[name][frozen_labels].set(value)

    def increment_gauge(
        self,
        name: str,
        amount: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a gauge value.

        Args:
            name: Metric name.
            amount: Amount to increment by (default 1.0).
            labels: Optional labels dict.
        """
        config = get_config()
        if not config.enabled or not config.metrics_enabled:
            return

        frozen_labels = _freeze_labels(labels)

        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = {}

            if frozen_labels not in self._gauges[name]:
                self._gauges[name][frozen_labels] = GaugeValue()

            self._gauges[name][frozen_labels].increment(amount)

    def decrement_gauge(
        self,
        name: str,
        amount: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Decrement a gauge value.

        Args:
            name: Metric name.
            amount: Amount to decrement by (default 1.0).
            labels: Optional labels dict.
        """
        config = get_config()
        if not config.enabled or not config.metrics_enabled:
            return

        frozen_labels = _freeze_labels(labels)

        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = {}

            if frozen_labels not in self._gauges[name]:
                self._gauges[name][frozen_labels] = GaugeValue()

            self._gauges[name][frozen_labels].decrement(amount)

    def export_json(self) -> str:
        """Export all metrics as JSON.

        Returns:
            JSON string with all metrics data.
        """
        with self._lock:
            data: dict[str, Any] = {
                "counters": {},
                "histograms": {},
                "gauges": {},
            }

            # Export counters
            for counter_name, counter_label_values in self._counters.items():
                data["counters"][counter_name] = []
                for labels, counter in counter_label_values.items():
                    data["counters"][counter_name].append(
                        {
                            "labels": _labels_to_dict(labels),
                            "value": counter.value,
                            "created_at": counter.created_at,
                        }
                    )

            # Export histograms
            for hist_name, hist_label_values in self._histograms.items():
                data["histograms"][hist_name] = []
                for labels, histogram in hist_label_values.items():
                    # Calculate percentiles from samples
                    samples = list(histogram.samples)
                    percentiles: dict[str, float] = {}
                    if samples:
                        sorted_samples = sorted(samples)
                        n = len(sorted_samples)
                        for p in (50, 90, 95, 99):
                            idx = int(n * p / 100)
                            percentiles[f"p{p}"] = sorted_samples[min(idx, n - 1)]

                    data["histograms"][hist_name].append(
                        {
                            "labels": _labels_to_dict(labels),
                            "count": histogram.count,
                            "sum": histogram.sum_value,
                            "percentiles": percentiles,
                            "bucket_counts": {
                                str(k) if k != float("inf") else "+Inf": v
                                for k, v in histogram.bucket_counts.items()
                            },
                            "created_at": histogram.created_at,
                        }
                    )

            # Export gauges
            for gauge_name, gauge_label_values in self._gauges.items():
                data["gauges"][gauge_name] = []
                for labels, gauge in gauge_label_values.items():
                    data["gauges"][gauge_name].append(
                        {
                            "labels": _labels_to_dict(labels),
                            "value": gauge.value,
                            "updated_at": gauge.updated_at,
                        }
                    )

            return json.dumps(data, indent=2)

    def export_text(self) -> str:
        """Export all metrics as human-readable text.

        Returns:
            Plain text summary of all metrics.
        """
        with self._lock:
            lines = []
            lines.append("=== Metrics Summary ===\n")

            # Export counters
            if self._counters:
                lines.append("## Counters\n")
                for counter_name, counter_label_values in sorted(
                    self._counters.items()
                ):
                    for labels, counter in counter_label_values.items():
                        label_str = (
                            "{"
                            + ", ".join(f'{k}="{v}"' for k, v in sorted(labels))
                            + "}"
                            if labels
                            else ""
                        )
                        lines.append(f"{counter_name}{label_str}: {counter.value}")
                lines.append("")

            # Export histograms
            if self._histograms:
                lines.append("## Histograms\n")
                for hist_name, hist_label_values in sorted(self._histograms.items()):
                    for labels, histogram in hist_label_values.items():
                        label_str = (
                            "{"
                            + ", ".join(f'{k}="{v}"' for k, v in sorted(labels))
                            + "}"
                            if labels
                            else ""
                        )
                        lines.append(f"{hist_name}{label_str}:")
                        lines.append(f"  count: {histogram.count}")
                        lines.append(f"  sum: {histogram.sum_value:.2f}")
                        if histogram.count > 0:
                            lines.append(
                                f"  mean: {histogram.sum_value / histogram.count:.2f}"
                            )

                        # Calculate percentiles
                        samples = list(histogram.samples)
                        if samples:
                            sorted_samples = sorted(samples)
                            n = len(sorted_samples)
                            for p in (50, 90, 95, 99):
                                idx = int(n * p / 100)
                                pct_value = sorted_samples[min(idx, n - 1)]
                                lines.append(f"  p{p}: {pct_value:.2f}")
                lines.append("")

            # Export gauges
            if self._gauges:
                lines.append("## Gauges\n")
                for gauge_name, gauge_label_values in sorted(self._gauges.items()):
                    for labels, gauge in gauge_label_values.items():
                        label_str = (
                            "{"
                            + ", ".join(f'{k}="{v}"' for k, v in sorted(labels))
                            + "}"
                            if labels
                            else ""
                        )
                        lines.append(f"{gauge_name}{label_str}: {gauge.value}")
                lines.append("")

            return "\n".join(lines)

    def reset(self) -> None:
        """Reset all metrics to empty state.

        Primarily for testing.
        """
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._gauges.clear()

    def get_counter_value(
        self, name: str, labels: dict[str, str] | None = None
    ) -> float:
        """Get a counter's current value.

        Args:
            name: Metric name.
            labels: Labels to match.

        Returns:
            Counter value, or 0.0 if not found.
        """
        frozen_labels = _freeze_labels(labels)
        with self._lock:
            if name in self._counters and frozen_labels in self._counters[name]:
                return self._counters[name][frozen_labels].value
            return 0.0

    def get_gauge_value(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get a gauge's current value.

        Args:
            name: Metric name.
            labels: Labels to match.

        Returns:
            Gauge value, or 0.0 if not found.
        """
        frozen_labels = _freeze_labels(labels)
        with self._lock:
            if name in self._gauges and frozen_labels in self._gauges[name]:
                return self._gauges[name][frozen_labels].value
            return 0.0


# Singleton instance
_metrics_instance: MetricsCollector | None = None
_metrics_lock = threading.Lock()


@lru_cache(maxsize=1)
def get_metrics() -> MetricsCollector:
    """Get the global MetricsCollector singleton.

    Returns:
        MetricsCollector: The global metrics collector instance.
    """
    global _metrics_instance
    with _metrics_lock:
        if _metrics_instance is None:
            config = get_config()
            _metrics_instance = MetricsCollector(max_samples=config.metrics_retention)
        return _metrics_instance


def reset_metrics() -> None:
    """Reset the global metrics collector.

    Primarily for testing.
    """
    global _metrics_instance
    with _metrics_lock:
        if _metrics_instance is not None:
            _metrics_instance.reset()
        get_metrics.cache_clear()
        _metrics_instance = None
