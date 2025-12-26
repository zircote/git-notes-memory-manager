"""Tests for metrics collection."""

from __future__ import annotations

import json
import threading
import time

import pytest

from git_notes_memory.observability.config import reset_config
from git_notes_memory.observability.metrics import (
    DEFAULT_LATENCY_BUCKETS,
    CounterValue,
    GaugeValue,
    HistogramValue,
    MetricsCollector,
    get_metrics,
    reset_metrics,
)


class TestCounterValue:
    """Tests for CounterValue dataclass."""

    def test_initial_value(self) -> None:
        """Test counter starts at zero."""
        counter = CounterValue()
        assert counter.value == 0.0
        assert counter.created_at > 0

    def test_increment_default(self) -> None:
        """Test incrementing by default amount."""
        counter = CounterValue()
        counter.increment()
        assert counter.value == 1.0

    def test_increment_custom_amount(self) -> None:
        """Test incrementing by custom amount."""
        counter = CounterValue()
        counter.increment(5.5)
        assert counter.value == 5.5


class TestHistogramValue:
    """Tests for HistogramValue dataclass."""

    def test_default_buckets(self) -> None:
        """Test default bucket boundaries."""
        histogram = HistogramValue()
        assert histogram.buckets == DEFAULT_LATENCY_BUCKETS

    def test_observe(self) -> None:
        """Test observing values."""
        histogram = HistogramValue()
        histogram.observe(10.0)
        histogram.observe(20.0)

        assert histogram.count == 2
        assert histogram.sum_value == 30.0
        assert list(histogram.samples) == [10.0, 20.0]

    def test_bucket_counts(self) -> None:
        """Test bucket count tracking."""
        histogram = HistogramValue(buckets=(10.0, 50.0, 100.0, float("inf")))
        histogram.observe(5.0)  # <= 10
        histogram.observe(30.0)  # <= 50
        histogram.observe(75.0)  # <= 100
        histogram.observe(200.0)  # <= +Inf

        assert histogram.bucket_counts[10.0] == 1
        assert histogram.bucket_counts[50.0] == 1
        assert histogram.bucket_counts[100.0] == 1
        assert histogram.bucket_counts[float("inf")] == 1

    def test_rolling_window(self) -> None:
        """Test samples are bounded by maxlen."""
        histogram = HistogramValue()
        histogram.samples = histogram.samples.__class__(maxlen=3)

        for i in range(5):
            histogram.observe(float(i))

        # Only last 3 values retained
        assert list(histogram.samples) == [2.0, 3.0, 4.0]


class TestGaugeValue:
    """Tests for GaugeValue dataclass."""

    def test_initial_value(self) -> None:
        """Test gauge starts at zero."""
        gauge = GaugeValue()
        assert gauge.value == 0.0

    def test_set(self) -> None:
        """Test setting gauge value."""
        gauge = GaugeValue()
        old_time = gauge.updated_at
        time.sleep(0.01)
        gauge.set(42.0)

        assert gauge.value == 42.0
        assert gauge.updated_at > old_time

    def test_increment(self) -> None:
        """Test incrementing gauge."""
        gauge = GaugeValue()
        gauge.set(10.0)
        gauge.increment(5.0)
        assert gauge.value == 15.0

    def test_decrement(self) -> None:
        """Test decrementing gauge."""
        gauge = GaugeValue()
        gauge.set(10.0)
        gauge.decrement(3.0)
        assert gauge.value == 7.0


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def setup_method(self) -> None:
        """Reset config before each test."""
        reset_config()
        reset_metrics()

    def teardown_method(self) -> None:
        """Reset after each test."""
        reset_config()
        reset_metrics()

    def test_increment_counter(self) -> None:
        """Test counter increment."""
        collector = MetricsCollector()
        collector.increment("test_counter")
        collector.increment("test_counter", amount=2.0)

        assert collector.get_counter_value("test_counter") == 3.0

    def test_increment_counter_with_labels(self) -> None:
        """Test counter increment with labels."""
        collector = MetricsCollector()
        collector.increment("test_counter", labels={"namespace": "decisions"})
        collector.increment("test_counter", labels={"namespace": "learnings"})

        assert (
            collector.get_counter_value(
                "test_counter", labels={"namespace": "decisions"}
            )
            == 1.0
        )
        assert (
            collector.get_counter_value(
                "test_counter", labels={"namespace": "learnings"}
            )
            == 1.0
        )

    def test_observe_histogram(self) -> None:
        """Test histogram observation."""
        collector = MetricsCollector()
        collector.observe("test_duration", 100.0)
        collector.observe("test_duration", 200.0)

        # Verify through export
        data = json.loads(collector.export_json())
        assert "test_duration" in data["histograms"]
        hist_data = data["histograms"]["test_duration"][0]
        assert hist_data["count"] == 2
        assert hist_data["sum"] == 300.0

    def test_set_gauge(self) -> None:
        """Test gauge set."""
        collector = MetricsCollector()
        collector.set_gauge("active_connections", 5.0)

        assert collector.get_gauge_value("active_connections") == 5.0

    def test_increment_gauge(self) -> None:
        """Test gauge increment."""
        collector = MetricsCollector()
        collector.set_gauge("active_connections", 5.0)
        collector.increment_gauge("active_connections", 3.0)

        assert collector.get_gauge_value("active_connections") == 8.0

    def test_decrement_gauge(self) -> None:
        """Test gauge decrement."""
        collector = MetricsCollector()
        collector.set_gauge("active_connections", 10.0)
        collector.decrement_gauge("active_connections", 2.0)

        assert collector.get_gauge_value("active_connections") == 8.0

    def test_export_json(self) -> None:
        """Test JSON export."""
        collector = MetricsCollector()
        collector.increment("counter1")
        collector.observe("histogram1", 50.0)
        collector.set_gauge("gauge1", 10.0)

        data = json.loads(collector.export_json())

        assert "counters" in data
        assert "histograms" in data
        assert "gauges" in data
        assert "counter1" in data["counters"]
        assert "histogram1" in data["histograms"]
        assert "gauge1" in data["gauges"]

    def test_export_text(self) -> None:
        """Test text export."""
        collector = MetricsCollector()
        collector.increment("counter1", labels={"env": "test"})
        collector.observe("histogram1", 50.0)
        collector.set_gauge("gauge1", 10.0)

        text = collector.export_text()

        assert "=== Metrics Summary ===" in text
        assert "## Counters" in text
        assert "counter1" in text
        assert "## Histograms" in text
        assert "histogram1" in text
        assert "## Gauges" in text
        assert "gauge1" in text

    def test_reset(self) -> None:
        """Test metrics reset."""
        collector = MetricsCollector()
        collector.increment("counter1")
        collector.observe("histogram1", 50.0)
        collector.set_gauge("gauge1", 10.0)

        collector.reset()

        assert collector.get_counter_value("counter1") == 0.0
        assert collector.get_gauge_value("gauge1") == 0.0

    def test_thread_safety(self) -> None:
        """Test thread-safe operations."""
        collector = MetricsCollector()
        errors: list[Exception] = []

        def increment_counter() -> None:
            try:
                for _ in range(100):
                    collector.increment("concurrent_counter")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=increment_counter) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert collector.get_counter_value("concurrent_counter") == 1000.0

    def test_disabled_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test metrics disabled via config."""
        monkeypatch.setenv("MEMORY_PLUGIN_METRICS_ENABLED", "false")
        reset_config()

        collector = MetricsCollector()
        collector.increment("disabled_counter")

        # Counter should not be recorded
        assert collector.get_counter_value("disabled_counter") == 0.0


class TestGetMetrics:
    """Tests for get_metrics() singleton."""

    def setup_method(self) -> None:
        """Reset before each test."""
        reset_config()
        reset_metrics()

    def teardown_method(self) -> None:
        """Reset after each test."""
        reset_config()
        reset_metrics()

    def test_returns_singleton(self) -> None:
        """Test get_metrics returns same instance."""
        metrics1 = get_metrics()
        metrics2 = get_metrics()
        assert metrics1 is metrics2

    def test_reset_creates_new_instance(self) -> None:
        """Test reset_metrics creates new instance."""
        metrics1 = get_metrics()
        reset_metrics()
        metrics2 = get_metrics()
        assert metrics1 is not metrics2
