# Observability

This document describes the observability features in git-notes-memory, including metrics, tracing, and structured logging.

## Overview

The `observability` module provides lightweight, zero-dependency instrumentation for:

- **Metrics**: Counters, histograms, and gauges for operational monitoring
- **Tracing**: Span-based distributed tracing with context propagation
- **Structured Logging**: JSON/text formatted logs with context

All observability features gracefully degrade if not configured and have minimal performance impact (<1ms overhead per operation).

## Metrics

### Viewing Metrics

Use the `/memory:metrics` command:

```bash
# Default text format
/memory:metrics

# JSON format for tooling
/memory:metrics --format json

# Prometheus exposition format
/memory:metrics --format prometheus

# Filter by pattern
/memory:metrics --filter "capture"
```

### Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `memories_captured_total` | counter | Total captures by namespace |
| `index_inserts_total` | counter | Index insert operations |
| `index_searches_total` | counter | Vector and text search operations |
| `hook_executions_total` | counter | Hook executions by hook/status |
| `hook_timeouts_total` | counter | Hook timeout events |
| `git_commands_total` | counter | Git subprocess calls by command/status |
| `embeddings_generated_total` | counter | Embeddings created |
| `silent_failures_total` | counter | Suppressed errors by location |
| `memory_capture_duration_ms` | histogram | Capture operation latency |
| `index_insert_duration_ms` | histogram | Index insert latency |
| `index_search_vector_duration_ms` | histogram | Vector search latency |
| `hook_execution_duration_ms` | histogram | Hook execution time by hook |
| `git_command_duration_ms` | histogram | Git command latency |
| `embedding_generate_duration_ms` | histogram | Embedding generation time |
| `embedding_model_load_time_ms` | gauge | Model load time on startup |

### Prometheus Integration

Export metrics in Prometheus text format for scraping:

```bash
# Get metrics in Prometheus format
/memory:metrics --format prometheus > /tmp/metrics.txt

# Or programmatically
from git_notes_memory.observability import get_metrics
from git_notes_memory.observability.exporters import PrometheusExporter

metrics = get_metrics()
exporter = PrometheusExporter()
prometheus_text = exporter.export(metrics)
```

## Tracing

### Viewing Traces

Use the `/memory:traces` command:

```bash
# View recent traces
/memory:traces

# Filter by operation
/memory:traces --operation capture

# Filter by status
/memory:traces --status error

# Limit results
/memory:traces --limit 5
```

### Trace Spans

Operations are instrumented with hierarchical spans:

```
capture (root span)
├── capture.resolve_commit
├── capture.count_existing
├── capture.git_append
├── capture.index
│   └── capture.embed
└── index.insert
```

### Programmatic Access

```python
from git_notes_memory.observability.tracing import trace_operation, get_current_span

# Create a span
with trace_operation("my_operation", labels={"key": "value"}):
    # Nested spans automatically link to parent
    with trace_operation("nested"):
        pass

    # Access current span
    span = get_current_span()
    span.set_attribute("custom_key", "custom_value")
```

## Structured Logging

### Configuration

```bash
# Enable debug logging
export HOOK_DEBUG=true

# View hook-specific logs
tail -f ~/.local/share/memory-plugin/logs/sessionstart.log
```

### Log Format

JSON format (default):
```json
{
  "timestamp": "2024-01-15T10:30:00.123456",
  "level": "INFO",
  "logger": "git_notes_memory.capture",
  "message": "Captured memory: decisions:abc123:0",
  "extra": {
    "memory_id": "decisions:abc123:0",
    "namespace": "decisions"
  }
}
```

### Programmatic Usage

```python
from git_notes_memory.observability import get_logger

logger = get_logger(__name__)
logger.info("Processing memory", memory_id="abc:123", namespace="decisions")
```

## Health Checks

Use `/memory:health` for system health:

```bash
# Basic health check
/memory:health

# Include timing percentiles
/memory:health --timing
```

Health check includes:
- Git repository status
- Index database connectivity
- Embedding model status
- Recent operation latencies

## Performance Characteristics

| Operation | p50 | p95 | p99 |
|-----------|-----|-----|-----|
| Capture (no embed) | <50ms | <100ms | <200ms |
| Capture (with embed) | <200ms | <500ms | <1s |
| Vector search | <10ms | <50ms | <100ms |
| Hook execution | <100ms | <500ms | <1s |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PLUGIN_OBSERVABILITY_ENABLED` | Master switch for observability | `true` |
| `MEMORY_PLUGIN_LOG_LEVEL` | Log level: quiet/info/debug/trace | `info` |
| `MEMORY_PLUGIN_LOG_FORMAT` | Log format: json/text | `json` |
| `MEMORY_PLUGIN_METRICS_ENABLED` | Enable metrics collection | `true` |
| `MEMORY_PLUGIN_TRACING_ENABLED` | Enable distributed tracing | `true` |
| `MEMORY_PLUGIN_OTLP_ENDPOINT` | OTLP HTTP endpoint for telemetry export | (none) |
| `MEMORY_PLUGIN_SERVICE_NAME` | Service name in telemetry | `git-notes-memory` |
| `MEMORY_PLUGIN_LOG_DIR` | Log file directory | `~/.local/share/memory-plugin/logs` |
| `HOOK_DEBUG` | Enable debug logging (legacy) | `false` |

## OTLP Export (Push Telemetry)

When `MEMORY_PLUGIN_OTLP_ENDPOINT` is set, telemetry is automatically pushed to an OpenTelemetry Collector at session end.

### Quick Setup with Docker

```bash
# Start the local observability stack
cd docker && docker compose up -d

# Configure the plugin to send telemetry
export MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4318

# Run Claude Code - telemetry will be exported on session end
claude
```

### Configuration

```bash
# Set the OTLP HTTP endpoint (required for push)
export MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4318

# Optional: Custom service name
export MEMORY_PLUGIN_SERVICE_NAME=my-project-memory
```

The exporter pushes:
- **Traces** to `{endpoint}/v1/traces`
- **Metrics** to `{endpoint}/v1/metrics`

### Viewing Telemetry

With the Docker stack running:

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3000 | Dashboards and exploration |
| Prometheus | http://localhost:9090 | Metrics queries |
| Tempo | http://localhost:3200 | Trace search |
| Loki | http://localhost:3100 | Log aggregation |

### Programmatic Export

```python
from git_notes_memory.observability.exporters import OTLPExporter

# Create exporter with custom endpoint
exporter = OTLPExporter(endpoint="http://localhost:4318")

# Export traces
from git_notes_memory.observability.tracing import get_completed_spans
spans = get_completed_spans()
exporter.export_traces(spans)

# Export metrics
from git_notes_memory.observability.metrics import get_metrics
exporter.export_metrics(get_metrics())
```

## Best Practices

1. **Monitor silent failures**: Watch `silent_failures_total` to detect suppressed errors
2. **Track hook latency**: Keep `hook_execution_duration_ms` p95 under timeout thresholds
3. **Watch embedding loads**: `embedding_model_load_time_ms` indicates cold start impact
4. **Use correlation IDs**: Trace operations across hooks using span context
