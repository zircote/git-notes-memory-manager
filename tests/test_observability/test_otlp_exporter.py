"""Tests for the OTLP HTTP exporter."""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any

import pytest

from git_notes_memory.observability.config import reset_config
from git_notes_memory.observability.exporters.otlp import (
    OTLPExporter,
    export_metrics_if_configured,
    export_traces_if_configured,
    get_otlp_exporter,
    reset_otlp_exporter,
)
from git_notes_memory.observability.metrics import MetricsCollector
from git_notes_memory.observability.tracing import Span


class TestOTLPExporter:
    """Tests for OTLPExporter class."""

    def setup_method(self) -> None:
        """Reset singletons before each test."""
        reset_otlp_exporter()
        reset_config()

    def test_exporter_disabled_without_endpoint(self) -> None:
        """Exporter should be disabled when no endpoint configured."""
        exporter = OTLPExporter(endpoint=None)
        assert not exporter.enabled

    def test_exporter_enabled_with_endpoint(self) -> None:
        """Exporter should be enabled when endpoint is configured."""
        exporter = OTLPExporter(endpoint="http://localhost:4318")
        assert exporter.enabled

    def test_span_to_otlp_conversion(self) -> None:
        """Test conversion of internal Span to OTLP format."""
        exporter = OTLPExporter(endpoint="http://localhost:4318")

        span = Span(
            trace_id="abc123def456",
            span_id="span789",
            operation="test_operation",
            start_time=1000.0,
            end_time=1000.5,
            parent_span_id="parent123",
            tags={"key": "value", "count": 42, "flag": True},
            status="ok",
        )

        otlp_span = exporter._span_to_otlp(span)

        assert otlp_span["traceId"] == "abc123def456"
        assert otlp_span["spanId"] == "span789"
        assert otlp_span["name"] == "test_operation"
        assert otlp_span["parentSpanId"] == "parent123"
        assert otlp_span["status"]["code"] == 1  # OK

        # Check time conversion (nanoseconds)
        assert otlp_span["startTimeUnixNano"] == str(int(1000.0 * 1e9))
        assert otlp_span["endTimeUnixNano"] == str(int(1000.5 * 1e9))

        # Check attributes
        attr_dict = {a["key"]: a["value"] for a in otlp_span["attributes"]}
        assert attr_dict["key"] == {"stringValue": "value"}
        assert attr_dict["count"] == {"intValue": "42"}
        assert attr_dict["flag"] == {"boolValue": True}

    def test_span_to_otlp_error_status(self) -> None:
        """Test conversion of error span to OTLP format."""
        exporter = OTLPExporter(endpoint="http://localhost:4318")

        span = Span(
            trace_id="abc123",
            span_id="span789",
            operation="failed_operation",
            start_time=1000.0,
            end_time=1000.1,
            status="error",
            error_message="Something went wrong",
        )

        otlp_span = exporter._span_to_otlp(span)

        assert otlp_span["status"]["code"] == 2  # ERROR
        assert otlp_span["status"]["message"] == "Something went wrong"

    def test_export_traces_disabled(self) -> None:
        """Export should return False when exporter is disabled."""
        exporter = OTLPExporter(endpoint=None)

        span = Span(
            trace_id="abc",
            span_id="123",
            operation="test",
            start_time=time.time(),
        )
        span.finish()

        assert not exporter.export_traces([span])

    def test_export_traces_empty_list(self) -> None:
        """Export should return False for empty span list."""
        exporter = OTLPExporter(endpoint="http://localhost:4318")
        assert not exporter.export_traces([])

    def test_counter_to_otlp_conversion(self) -> None:
        """Test conversion of counter metric to OTLP format."""
        exporter = OTLPExporter(endpoint="http://localhost:4318")

        time_ns = int(time.time() * 1e9)
        labels = frozenset([("namespace", "decisions")])

        otlp_metric = exporter._counter_to_otlp(
            "memories_captured_total", labels, 42.0, time_ns
        )

        assert otlp_metric["name"] == "memories_captured_total"
        assert "sum" in otlp_metric
        assert otlp_metric["sum"]["isMonotonic"] is True
        assert otlp_metric["sum"]["aggregationTemporality"] == 2  # CUMULATIVE

        data_point = otlp_metric["sum"]["dataPoints"][0]
        assert data_point["asDouble"] == 42.0
        assert data_point["timeUnixNano"] == str(time_ns)

    def test_gauge_to_otlp_conversion(self) -> None:
        """Test conversion of gauge metric to OTLP format."""
        exporter = OTLPExporter(endpoint="http://localhost:4318")

        time_ns = int(time.time() * 1e9)
        labels = frozenset([("model", "all-MiniLM-L6-v2")])

        otlp_metric = exporter._gauge_to_otlp(
            "embedding_model_load_time_ms", labels, 150.5, time_ns
        )

        assert otlp_metric["name"] == "embedding_model_load_time_ms"
        assert "gauge" in otlp_metric

        data_point = otlp_metric["gauge"]["dataPoints"][0]
        assert data_point["asDouble"] == 150.5

    def test_resource_attributes(self) -> None:
        """Test resource attributes include service name."""
        exporter = OTLPExporter(
            endpoint="http://localhost:4318", service_name="test-service"
        )

        resource = exporter._make_resource()

        attr_dict = {
            a["key"]: a["value"]["stringValue"] for a in resource["attributes"]
        }
        assert attr_dict["service.name"] == "test-service"
        assert attr_dict["telemetry.sdk.name"] == "git-notes-memory"
        assert attr_dict["telemetry.sdk.language"] == "python"


class TestOTLPExporterIntegration:
    """Integration tests with mock HTTP server."""

    @pytest.fixture
    def mock_otlp_server(self) -> tuple[HTTPServer, list[dict[str, Any]]]:
        """Create a mock OTLP HTTP server."""
        received_requests: list[dict[str, Any]] = []

        class OTLPHandler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                pass  # Suppress logging

            def do_POST(self) -> None:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                received_requests.append(
                    {
                        "path": self.path,
                        "body": json.loads(body.decode("utf-8")),
                    }
                )
                self.send_response(200)
                self.end_headers()

        server = HTTPServer(("localhost", 0), OTLPHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        yield server, received_requests

        server.shutdown()

    def test_export_traces_to_server(
        self, mock_otlp_server: tuple[HTTPServer, list[dict[str, Any]]]
    ) -> None:
        """Test exporting traces to mock server."""
        server, received = mock_otlp_server
        endpoint = f"http://localhost:{server.server_address[1]}"

        exporter = OTLPExporter(endpoint=endpoint)

        span = Span(
            trace_id="abc123",
            span_id="span789",
            operation="capture",
            start_time=time.time() - 0.1,
            tags={"namespace": "decisions"},
        )
        span.finish()

        result = exporter.export_traces([span])

        assert result is True
        assert len(received) == 1
        assert received[0]["path"] == "/v1/traces"
        assert "resourceSpans" in received[0]["body"]

    def test_export_metrics_to_server(
        self, mock_otlp_server: tuple[HTTPServer, list[dict[str, Any]]]
    ) -> None:
        """Test exporting metrics to mock server."""
        server, received = mock_otlp_server
        endpoint = f"http://localhost:{server.server_address[1]}"

        exporter = OTLPExporter(endpoint=endpoint)

        # Create metrics collector with some data
        metrics = MetricsCollector()
        metrics.increment("test_counter", labels={"label": "value"})
        metrics.observe("test_histogram", 50.0)
        metrics.set_gauge("test_gauge", 100.0)

        result = exporter.export_metrics(metrics)

        assert result is True
        assert len(received) == 1
        assert received[0]["path"] == "/v1/metrics"
        assert "resourceMetrics" in received[0]["body"]

    def test_export_failure_returns_false(self) -> None:
        """Test that export returns False on connection failure."""
        exporter = OTLPExporter(endpoint="http://localhost:59999")  # Unlikely to exist

        span = Span(
            trace_id="abc",
            span_id="123",
            operation="test",
            start_time=time.time(),
        )
        span.finish()

        result = exporter.export_traces([span])
        assert result is False


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self) -> None:
        """Reset singletons before each test."""
        reset_otlp_exporter()
        reset_config()

    def test_get_otlp_exporter_singleton(self) -> None:
        """get_otlp_exporter returns same instance."""
        exporter1 = get_otlp_exporter()
        exporter2 = get_otlp_exporter()
        assert exporter1 is exporter2

    def test_reset_otlp_exporter(self) -> None:
        """reset_otlp_exporter clears singleton."""
        exporter1 = get_otlp_exporter()
        reset_otlp_exporter()
        exporter2 = get_otlp_exporter()
        assert exporter1 is not exporter2

    def test_export_traces_if_configured_no_endpoint(self) -> None:
        """export_traces_if_configured returns True when no endpoint."""
        spans = [
            Span(
                trace_id="abc", span_id="123", operation="test", start_time=time.time()
            )
        ]
        # No endpoint configured, should return True (nothing to do)
        result = export_traces_if_configured(spans)
        assert result is True

    def test_export_metrics_if_configured_no_endpoint(self) -> None:
        """export_metrics_if_configured returns True when no endpoint."""
        # No endpoint configured, should return True (nothing to do)
        result = export_metrics_if_configured()
        assert result is True

    def test_export_with_configured_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test export functions use configured endpoint."""
        reset_config()
        monkeypatch.setenv("MEMORY_PLUGIN_OTLP_ENDPOINT", "http://localhost:4318")

        # Reset to pick up new config
        reset_otlp_exporter()
        reset_config()

        exporter = get_otlp_exporter()
        assert exporter.enabled
        assert exporter.endpoint == "http://localhost:4318"
