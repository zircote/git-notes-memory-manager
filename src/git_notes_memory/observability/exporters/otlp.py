"""OTLP HTTP exporter for metrics, traces, and logs.

Exports telemetry to OpenTelemetry Collector via OTLP/HTTP protocol.
Uses stdlib only - no external dependencies required.

The exporter pushes to:
- {endpoint}/v1/traces for spans
- {endpoint}/v1/metrics for metrics
- {endpoint}/v1/logs for log records

Usage:
    from git_notes_memory.observability.exporters.otlp import OTLPExporter

    exporter = OTLPExporter("http://localhost:4318")
    exporter.export_traces(spans)
    exporter.export_metrics(metrics)
    exporter.export_logs([LogRecord(body="test", severity="INFO")])

Environment:
    MEMORY_PLUGIN_OTLP_ENDPOINT: OTLP HTTP endpoint (e.g., http://localhost:4318)
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from git_notes_memory.observability.config import get_config

if TYPE_CHECKING:
    from git_notes_memory.observability.metrics import MetricsCollector
    from git_notes_memory.observability.tracing import Span


# OTLP severity numbers (SeverityNumber)
SEVERITY_MAP: dict[str, int] = {
    "TRACE": 1,
    "DEBUG": 5,
    "INFO": 9,
    "WARN": 13,
    "WARNING": 13,
    "ERROR": 17,
    "FATAL": 21,
    "CRITICAL": 21,
}


@dataclass
class LogRecord:
    """A log record for OTLP export.

    Attributes:
        body: The log message body.
        severity: Log level (DEBUG, INFO, WARN, ERROR, etc.).
        timestamp: Unix timestamp in seconds (defaults to now).
        attributes: Additional key-value attributes.
        trace_id: Optional trace ID for correlation.
        span_id: Optional span ID for correlation.
    """

    body: str
    severity: str = "INFO"
    timestamp: float = field(default_factory=time.time)
    attributes: dict[str, str | int | float | bool] = field(default_factory=dict)
    trace_id: str | None = None
    span_id: str | None = None

logger = logging.getLogger(__name__)


# =============================================================================
# SEC-H-001: SSRF Prevention
# =============================================================================


def _is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to a private/internal IP address.

    Args:
        hostname: The hostname or IP address to check.

    Returns:
        True if the address is private/internal (RFC 1918, loopback, link-local).
    """
    try:
        # Check if it's already an IP address
        addr = ipaddress.ip_address(hostname)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        # It's a hostname, check common internal names
        lower = hostname.lower()
        return lower in ("localhost", "127.0.0.1", "::1") or lower.endswith(
            (".local", ".internal", ".localhost")
        )


def _validate_otlp_endpoint(endpoint: str) -> tuple[bool, str]:
    """Validate an OTLP endpoint URL for SSRF safety.

    SEC-H-001: Validates endpoint to prevent SSRF attacks via
    malicious OTLP configuration.

    Args:
        endpoint: The endpoint URL to validate.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    try:
        parsed = urlparse(endpoint)

        # Check scheme
        if parsed.scheme not in ("http", "https"):
            return False, f"Invalid scheme '{parsed.scheme}': only http/https allowed"

        # Check hostname exists
        if not parsed.hostname:
            return False, "Missing hostname in endpoint URL"

        # Check for private IPs (warn but allow with env var override)
        if _is_private_ip(parsed.hostname):
            allow_internal = os.environ.get(
                "MEMORY_PLUGIN_OTLP_ALLOW_INTERNAL", ""
            ).lower() in ("true", "1", "yes")

            if not allow_internal:
                return (
                    False,
                    f"Internal endpoint '{parsed.hostname}' blocked for SSRF safety. "
                    "Set MEMORY_PLUGIN_OTLP_ALLOW_INTERNAL=true to allow.",
                )
            logger.warning(
                "SEC-H-001: Internal OTLP endpoint '%s' allowed via override",
                parsed.hostname,
            )

        return True, ""

    except Exception as e:
        return False, f"Failed to parse endpoint URL: {e}"


class OTLPExporter:
    """OTLP HTTP exporter for OpenTelemetry Collector.

    Converts internal metrics and spans to OTLP JSON format and
    pushes them via HTTP POST to the configured endpoint.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        timeout: float = 5.0,
        service_name: str | None = None,
    ) -> None:
        """Initialize the OTLP exporter.

        Args:
            endpoint: OTLP HTTP endpoint (e.g., http://localhost:4318).
                     If None, reads from config/environment.
            timeout: HTTP request timeout in seconds.
            service_name: Service name for resource attributes.
        """
        config = get_config()
        self.endpoint = endpoint or config.otlp_endpoint
        self.timeout = timeout
        self.service_name = service_name or config.service_name

        # SEC-H-001: Validate endpoint for SSRF safety
        if self.endpoint:
            is_valid, error = _validate_otlp_endpoint(self.endpoint)
            if not is_valid:
                logger.warning("SEC-H-001: OTLP endpoint validation failed: %s", error)
                self._enabled = False
            else:
                self._enabled = True
        else:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        """Check if exporter is enabled (endpoint configured)."""
        return self._enabled

    def _make_resource(self) -> dict[str, Any]:
        """Create OTLP resource with service attributes."""
        return {
            "attributes": [
                {"key": "service.name", "value": {"stringValue": self.service_name}},
                {
                    "key": "telemetry.sdk.name",
                    "value": {"stringValue": "git-notes-memory"},
                },
                {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
            ]
        }

    def _span_to_otlp(self, span: Span) -> dict[str, Any]:
        """Convert internal Span to OTLP span format."""
        # Convert times to nanoseconds
        start_ns = int(span.start_time * 1e9)
        end_ns = int(span.end_time * 1e9) if span.end_time else start_ns

        # Build attributes from tags
        attributes = []
        for key, value in span.tags.items():
            if isinstance(value, bool):
                attributes.append({"key": key, "value": {"boolValue": value}})
            elif isinstance(value, int):
                attributes.append({"key": key, "value": {"intValue": str(value)}})
            elif isinstance(value, float):
                attributes.append({"key": key, "value": {"doubleValue": value}})
            else:
                attributes.append({"key": key, "value": {"stringValue": str(value)}})

        # Map status
        status_code = 1 if span.status == "ok" else 2  # 1=OK, 2=ERROR

        otlp_span: dict[str, Any] = {
            "traceId": span.trace_id,
            "spanId": span.span_id,
            "name": span.operation,
            "kind": 1,  # INTERNAL
            "startTimeUnixNano": str(start_ns),
            "endTimeUnixNano": str(end_ns),
            "attributes": attributes,
            "status": {"code": status_code},
        }

        if span.parent_span_id:
            otlp_span["parentSpanId"] = span.parent_span_id

        if span.error_message:
            otlp_span["status"]["message"] = span.error_message

        return otlp_span

    def export_traces(self, spans: list[Span]) -> bool:
        """Export spans to OTLP endpoint.

        Args:
            spans: List of completed Span objects.

        Returns:
            True if export succeeded, False otherwise.
        """
        if not self._enabled or not spans:
            return False

        # Build OTLP trace payload
        payload = {
            "resourceSpans": [
                {
                    "resource": self._make_resource(),
                    "scopeSpans": [
                        {
                            "scope": {"name": "git-notes-memory"},
                            "spans": [self._span_to_otlp(s) for s in spans],
                        }
                    ],
                }
            ]
        }

        return self._post(f"{self.endpoint}/v1/traces", payload)

    def _log_to_otlp(self, record: LogRecord) -> dict[str, Any]:
        """Convert LogRecord to OTLP log format."""
        time_ns = int(record.timestamp * 1e9)
        severity_number = SEVERITY_MAP.get(record.severity.upper(), 9)  # Default INFO

        # Build attributes
        attributes: list[dict[str, Any]] = []
        for key, value in record.attributes.items():
            if isinstance(value, bool):
                attributes.append({"key": key, "value": {"boolValue": value}})
            elif isinstance(value, int):
                attributes.append({"key": key, "value": {"intValue": str(value)}})
            elif isinstance(value, float):
                attributes.append({"key": key, "value": {"doubleValue": value}})
            else:
                attributes.append({"key": key, "value": {"stringValue": str(value)}})

        otlp_log: dict[str, Any] = {
            "timeUnixNano": str(time_ns),
            "severityNumber": severity_number,
            "severityText": record.severity.upper(),
            "body": {"stringValue": record.body},
            "attributes": attributes,
        }

        if record.trace_id:
            otlp_log["traceId"] = record.trace_id
        if record.span_id:
            otlp_log["spanId"] = record.span_id

        return otlp_log

    def export_logs(self, logs: list[LogRecord]) -> bool:
        """Export log records to OTLP endpoint.

        Args:
            logs: List of LogRecord objects.

        Returns:
            True if export succeeded, False otherwise.
        """
        if not self._enabled or not logs:
            return False

        # Build OTLP logs payload
        payload = {
            "resourceLogs": [
                {
                    "resource": self._make_resource(),
                    "scopeLogs": [
                        {
                            "scope": {"name": "git-notes-memory"},
                            "logRecords": [self._log_to_otlp(log) for log in logs],
                        }
                    ],
                }
            ]
        }

        return self._post(f"{self.endpoint}/v1/logs", payload)

    def _counter_to_otlp(
        self,
        name: str,
        labels: frozenset[tuple[str, str]],
        value: float,
        time_ns: int,
    ) -> dict[str, Any]:
        """Convert internal counter to OTLP metric format."""
        attributes = [
            {"key": k, "value": {"stringValue": v}} for k, v in sorted(labels)
        ]

        return {
            "name": name,
            "sum": {
                "dataPoints": [
                    {
                        "asDouble": value,
                        "timeUnixNano": str(time_ns),
                        "attributes": attributes,
                    }
                ],
                "aggregationTemporality": 2,  # CUMULATIVE
                "isMonotonic": True,
            },
        }

    def _histogram_to_otlp(
        self,
        name: str,
        labels: frozenset[tuple[str, str]],
        histogram: Any,
        time_ns: int,
    ) -> dict[str, Any]:
        """Convert internal histogram to OTLP metric format."""
        attributes = [
            {"key": k, "value": {"stringValue": v}} for k, v in sorted(labels)
        ]

        # Build bucket counts (must be in order)
        sorted_buckets = sorted(histogram.buckets)
        bucket_counts = [histogram.bucket_counts.get(b, 0) for b in sorted_buckets]
        explicit_bounds = [b for b in sorted_buckets if b != float("inf")]

        return {
            "name": name,
            "histogram": {
                "dataPoints": [
                    {
                        "count": str(histogram.count),
                        "sum": histogram.sum_value,
                        "bucketCounts": [str(c) for c in bucket_counts],
                        "explicitBounds": explicit_bounds,
                        "timeUnixNano": str(time_ns),
                        "attributes": attributes,
                    }
                ],
                "aggregationTemporality": 2,  # CUMULATIVE
            },
        }

    def _gauge_to_otlp(
        self,
        name: str,
        labels: frozenset[tuple[str, str]],
        value: float,
        time_ns: int,
    ) -> dict[str, Any]:
        """Convert internal gauge to OTLP metric format."""
        attributes = [
            {"key": k, "value": {"stringValue": v}} for k, v in sorted(labels)
        ]

        return {
            "name": name,
            "gauge": {
                "dataPoints": [
                    {
                        "asDouble": value,
                        "timeUnixNano": str(time_ns),
                        "attributes": attributes,
                    }
                ],
            },
        }

    def export_metrics(self, metrics: MetricsCollector) -> bool:
        """Export metrics to OTLP endpoint.

        Args:
            metrics: MetricsCollector instance with current metrics.

        Returns:
            True if export succeeded, False otherwise.
        """
        if not self._enabled:
            return False

        time_ns = int(time.time() * 1e9)
        otlp_metrics: list[dict[str, Any]] = []

        with metrics._lock:
            # Export counters
            for counter_name, counter_label_values in metrics._counters.items():
                for labels, counter in counter_label_values.items():
                    otlp_metrics.append(
                        self._counter_to_otlp(
                            counter_name, labels, counter.value, time_ns
                        )
                    )

            # Export histograms
            for hist_name, hist_label_values in metrics._histograms.items():
                for labels, histogram in hist_label_values.items():
                    otlp_metrics.append(
                        self._histogram_to_otlp(hist_name, labels, histogram, time_ns)
                    )

            # Export gauges
            for gauge_name, gauge_label_values in metrics._gauges.items():
                for labels, gauge in gauge_label_values.items():
                    otlp_metrics.append(
                        self._gauge_to_otlp(gauge_name, labels, gauge.value, time_ns)
                    )

        if not otlp_metrics:
            return False

        # Build OTLP metrics payload
        payload = {
            "resourceMetrics": [
                {
                    "resource": self._make_resource(),
                    "scopeMetrics": [
                        {
                            "scope": {"name": "git-notes-memory"},
                            "metrics": otlp_metrics,
                        }
                    ],
                }
            ]
        }

        return self._post(f"{self.endpoint}/v1/metrics", payload)

    def _post(self, url: str, payload: dict[str, Any]) -> bool:
        """POST JSON payload to URL.

        Args:
            url: Target URL.
            payload: JSON-serializable payload.

        Returns:
            True if request succeeded (2xx), False otherwise.
        """
        try:
            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310
                status: int = response.status
                return 200 <= status < 300

        except urllib.error.URLError as e:
            logger.debug("OTLP export failed: %s", e)
            return False
        except Exception as e:
            logger.debug("OTLP export error: %s", e)
            return False


# Singleton instance
_exporter: OTLPExporter | None = None


def get_otlp_exporter() -> OTLPExporter:
    """Get the OTLP exporter singleton.

    Returns:
        OTLPExporter instance configured from environment.
    """
    global _exporter
    if _exporter is None:
        _exporter = OTLPExporter()
    return _exporter


def reset_otlp_exporter() -> None:
    """Reset the OTLP exporter singleton (for testing)."""
    global _exporter
    _exporter = None


def export_traces_if_configured(spans: list[Span]) -> bool:
    """Export traces if OTLP endpoint is configured.

    Convenience function that checks configuration before attempting export.

    Args:
        spans: List of completed spans.

    Returns:
        True if export succeeded or no endpoint configured, False on failure.
    """
    exporter = get_otlp_exporter()
    if not exporter.enabled:
        return True  # No endpoint = success (nothing to do)
    return exporter.export_traces(spans)


def export_metrics_if_configured() -> bool:
    """Export metrics if OTLP endpoint is configured.

    Convenience function that checks configuration before attempting export.

    Returns:
        True if export succeeded or no endpoint configured, False on failure.
    """
    from git_notes_memory.observability.metrics import get_metrics

    exporter = get_otlp_exporter()
    if not exporter.enabled:
        return True  # No endpoint = success (nothing to do)
    return exporter.export_metrics(get_metrics())


def export_logs_if_configured(logs: list[LogRecord]) -> bool:
    """Export logs if OTLP endpoint is configured.

    Convenience function that checks configuration before attempting export.

    Args:
        logs: List of LogRecord objects.

    Returns:
        True if export succeeded or no endpoint configured, False on failure.
    """
    exporter = get_otlp_exporter()
    if not exporter.enabled:
        return True  # No endpoint = success (nothing to do)
    return exporter.export_logs(logs)
