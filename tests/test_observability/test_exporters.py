"""Tests for observability exporters."""

from __future__ import annotations

import json

from git_notes_memory.observability.config import reset_config
from git_notes_memory.observability.exporters.json_exporter import (
    export_json,
    export_metrics_json,
    export_traces_json,
)
from git_notes_memory.observability.exporters.prometheus import export_prometheus_text
from git_notes_memory.observability.metrics import get_metrics, reset_metrics
from git_notes_memory.observability.session import reset_session
from git_notes_memory.observability.tracing import (
    clear_completed_spans,
    end_trace,
    trace_operation,
)


class TestPrometheusExporter:
    """Tests for Prometheus text exporter."""

    def setup_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_metrics()

    def teardown_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_metrics()

    def test_empty_metrics(self) -> None:
        """Test export with no metrics."""
        output = export_prometheus_text()
        # Should be empty or just whitespace
        assert output.strip() == ""

    def test_counter_export(self) -> None:
        """Test exporting counters."""
        metrics = get_metrics()
        metrics.increment("test_counter", labels={"env": "test"})
        metrics.increment("test_counter", amount=2.0, labels={"env": "test"})

        output = export_prometheus_text()

        assert "# HELP test_counter Counter metric" in output
        assert "# TYPE test_counter counter" in output
        assert 'test_counter{env="test"}' in output
        assert "3" in output or "3.0" in output

    def test_histogram_export(self) -> None:
        """Test exporting histograms."""
        metrics = get_metrics()
        metrics.observe("test_histogram", 10.0)
        metrics.observe("test_histogram", 50.0)

        output = export_prometheus_text()

        assert "# HELP test_histogram Histogram metric" in output
        assert "# TYPE test_histogram histogram" in output
        assert "test_histogram_bucket" in output
        assert "test_histogram_sum" in output
        assert "test_histogram_count" in output

    def test_gauge_export(self) -> None:
        """Test exporting gauges."""
        metrics = get_metrics()
        metrics.set_gauge("test_gauge", 42.0, labels={"type": "connections"})

        output = export_prometheus_text()

        assert "# HELP test_gauge Gauge metric" in output
        assert "# TYPE test_gauge gauge" in output
        assert 'test_gauge{type="connections"}' in output
        assert "42" in output


class TestJsonExporter:
    """Tests for JSON exporter."""

    def setup_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_metrics()
        clear_completed_spans()
        end_trace()
        reset_session()

    def teardown_method(self) -> None:
        """Reset state."""
        reset_config()
        reset_metrics()
        clear_completed_spans()
        end_trace()
        reset_session()

    def test_export_json_full(self) -> None:
        """Test full JSON export."""
        # Add some data
        metrics = get_metrics()
        metrics.increment("json_test_counter")
        with trace_operation("json_test_op"):
            pass

        output = export_json()
        data = json.loads(output)

        assert "export_time" in data
        assert "service_name" in data
        assert "session" in data
        assert "metrics" in data
        assert "traces" in data

    def test_export_json_metrics_only(self) -> None:
        """Test metrics-only JSON export."""
        metrics = get_metrics()
        metrics.increment("metrics_only_counter")

        output = export_json(include_traces=False, include_session=False)
        data = json.loads(output)

        assert "metrics" in data
        assert "traces" not in data
        assert "session" not in data

    def test_export_json_traces_only(self) -> None:
        """Test traces-only JSON export."""
        with trace_operation("traces_only_op"):
            pass

        output = export_json(include_metrics=False, include_session=False)
        data = json.loads(output)

        assert "traces" in data
        assert "metrics" not in data
        assert "session" not in data

    def test_export_metrics_json(self) -> None:
        """Test export_metrics_json shortcut."""
        metrics = get_metrics()
        metrics.increment("shortcut_counter")

        output = export_metrics_json()
        data = json.loads(output)

        assert "metrics" in data
        assert "traces" not in data

    def test_export_traces_json(self) -> None:
        """Test export_traces_json shortcut."""
        with trace_operation("shortcut_op"):
            pass

        output = export_traces_json()
        data = json.loads(output)

        assert "traces" in data
        assert "metrics" not in data

    def test_indent_option(self) -> None:
        """Test indent parameter."""
        output_indented = export_json(indent=2)
        output_compact = export_json(indent=0)

        # Indented should have newlines
        assert "\n" in output_indented
        # Compact has fewer characters
        assert len(output_compact) <= len(output_indented)


class TestExportersInit:
    """Tests for exporters __init__ lazy imports."""

    def test_lazy_import_prometheus(self) -> None:
        """Test lazy import of export_prometheus_text."""
        from git_notes_memory.observability.exporters import export_prometheus_text

        assert callable(export_prometheus_text)

    def test_lazy_import_json(self) -> None:
        """Test lazy import of export_json."""
        from git_notes_memory.observability.exporters import export_json

        assert callable(export_json)

    def test_invalid_attribute_raises(self) -> None:
        """Test accessing invalid attribute raises AttributeError."""
        import pytest

        from git_notes_memory.observability import exporters

        with pytest.raises(AttributeError, match="nonexistent"):
            _ = exporters.nonexistent
