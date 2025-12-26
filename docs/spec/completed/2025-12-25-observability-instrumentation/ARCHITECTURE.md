---
document_type: architecture
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T23:50:00Z
status: draft
---

# Observability Instrumentation - Technical Architecture

## System Overview

The observability system adds comprehensive instrumentation to git-notes-memory through a layered architecture that keeps core functionality independent of monitoring infrastructure.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Application Layer                                   │
│  ┌─────────────┐  ┌───────────────┐ ┌───────────────────┐  ┌──────────────┐ │
│  │ CaptureService │ RecallService │ │ EmbeddingService  │  │ IndexService │ │
│  └──────┬──────┘  └──────┬────────┘ └──────┬────────────┘  └──────┬───────┘ │
│         │                │                 │                      │         │
│         v                v                 v                      v         │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                    Observability Facade                                 ││
│  │  ┌───────────────────┐  ┌──────────────────┐  ┌─────────────────┐       ││
│  │  │ @measure_duration │  │  trace_operation │  │StructuredLogger │       ││
│  │  └───────────────────┘  └──────────────────┘  └─────────────────┘       ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                              │                                              │
│         ┌────────────────────┼────────────────────┐                         │
│         v                    v                    v                         │
│  ┌────────────────┐   ┌─────────────┐      ┌──────────────┐                 │
│  │MetricsCollector│   │ SpanContext │      │ LogFormatter │                 │
│  │  (in-memory)   │   │(contextvars)│      │   (JSON)     │                 │
│  └──────┬─────────┘   └──────┬──────┘      └──────┬───────┘                 │
│         │                    │                    │                         │
└─────────┼────────────────────┼────────────────────┼─────────────────────────┘
          │                    │                    │
          v                    v                    v
   ┌──────────────┐      ┌──────────────┐      ┌─────────────┐
   │ Export Layer │      │ Export Layer │      │  stderr/    │
   │  (Optional)  │      │  (Optional)  │      │  file logs  │
   │ ┌──────────┐ │      │ ┌─────────┐  │      └─────────────┘
   │ │Prometheus│ │      │ │  OTLP   │  │
   │ │ format   │ │      │ │ export  │  │
   │ └──────────┘ │      │ └─────────┘  │
   └──────────────┘      └──────────────┘
```

### Key Design Decisions

1. **Facade pattern** - Single entry point (`observability.py`) for all instrumentation
2. **Zero-cost abstraction** - When disabled, observability adds minimal overhead
3. **Optional backends** - Prometheus/OTLP only loaded when extras installed
4. **Contextvar-based tracing** - Thread-safe span context propagation
5. **Decorator-first timing** - Clean, non-invasive instrumentation

## Component Design

### Component 1: MetricsCollector

**Purpose**: Thread-safe in-memory metrics storage and aggregation

**Responsibilities**:
- Store counters, histograms, and gauges
- Thread-safe concurrent access
- Export to multiple formats (JSON, Prometheus, plain text)
- Rolling window for histogram samples (configurable retention)

**Interfaces**:
```python
class MetricsCollector:
    def increment(self, name: str, value: int = 1, labels: dict | None = None) -> None
    def observe(self, name: str, value: float, labels: dict | None = None) -> None
    def set_gauge(self, name: str, value: float, labels: dict | None = None) -> None
    def export_json(self) -> dict[str, Any]
    def export_prometheus(self) -> str
    def export_text(self) -> str
    def reset(self) -> None
```

**Dependencies**: None (stdlib only)

**Technology**: Python dataclasses, threading.Lock, collections.deque

### Component 2: SpanContext

**Purpose**: Trace context propagation via contextvars

**Responsibilities**:
- Generate unique trace_id and span_id
- Maintain span stack for nested operations
- Propagate context across async/sync boundaries
- Emit span completion events

**Interfaces**:
```python
@dataclass
class Span:
    trace_id: str
    span_id: str
    operation: str
    start_time: float
    end_time: float | None = None
    parent_id: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    status: Literal["ok", "error"] = "ok"
    error: str | None = None

@contextmanager
def trace_operation(operation: str, **tags) -> Generator[Span, None, None]:
    """Create a new span for an operation."""

def get_current_span() -> Span | None:
    """Get the current span from context."""

def get_current_trace_id() -> str | None:
    """Get the current trace ID."""
```

**Dependencies**: None (stdlib contextvars)

**Technology**: contextvars, uuid, time.perf_counter

### Component 3: StructuredLogger

**Purpose**: JSON-structured logging with trace context injection

**Responsibilities**:
- Format log entries as JSON with consistent schema
- Inject trace_id/span_id from current context
- Support backward compatibility with text format
- Integrate with Python logging infrastructure

**Interfaces**:
```python
class StructuredLogger:
    def __init__(self, name: str) -> None
    def debug(self, message: str, **context) -> None
    def info(self, message: str, **context) -> None
    def warning(self, message: str, **context) -> None
    def error(self, message: str, exc_info: bool = False, **context) -> None
    def exception(self, message: str, **context) -> None

def get_logger(name: str) -> StructuredLogger:
    """Factory for structured loggers."""
```

**Log Schema**:
```json
{
  "timestamp": "2025-12-25T12:00:00.000Z",
  "level": "INFO",
  "message": "Memory captured successfully",
  "service": "git-notes-memory",
  "trace_id": "abc123def",
  "span_id": "xyz789",
  "operation": "capture",
  "namespace": "decisions",
  "memory_id": "decisions:abc123:0"
}
```

**Dependencies**: None (stdlib logging, json)

### Component 4: measure_duration Decorator

**Purpose**: Timing decorator for critical operations

**Responsibilities**:
- Measure function execution time
- Emit histogram metrics with status labels
- Handle both sync and async functions
- Propagate exceptions while recording timing

**Interfaces**:
```python
def measure_duration(
    operation: str,
    labels: dict[str, str] | None = None,
    record_args: list[str] | None = None
) -> Callable[[F], F]:
    """
    Decorator to measure and record function execution duration.

    Args:
        operation: Name for the metric (e.g., "memory_capture")
        labels: Static labels to add to all emissions
        record_args: Function argument names to extract as labels
    """
```

**Usage**:
```python
@measure_duration("memory_capture", labels={"service": "capture"})
def capture(self, namespace: str, summary: str, ...) -> CaptureResult:
    ...
```

**Dependencies**: MetricsCollector singleton

### Component 5: ObservabilityConfig

**Purpose**: Configuration for observability features

**Responsibilities**:
- Load configuration from environment variables
- Provide unified debug level control
- Configure export backends
- Manage feature flags

**Interfaces**:
```python
@dataclass(frozen=True)
class ObservabilityConfig:
    enabled: bool = True
    log_format: Literal["json", "text"] = "json"
    log_level: Literal["quiet", "info", "debug", "trace"] = "info"
    metrics_enabled: bool = True
    metrics_retention_seconds: int = 3600
    tracing_enabled: bool = True
    otlp_endpoint: str | None = None
    prometheus_port: int | None = None

def get_config() -> ObservabilityConfig:
    """Load configuration from environment."""
```

**Environment Variables**:
```bash
MEMORY_PLUGIN_OBSERVABILITY_ENABLED=true
MEMORY_PLUGIN_LOG_FORMAT=json
MEMORY_PLUGIN_LOG_LEVEL=info
MEMORY_PLUGIN_METRICS_ENABLED=true
MEMORY_PLUGIN_METRICS_RETENTION=3600
MEMORY_PLUGIN_TRACING_ENABLED=true
MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4317
MEMORY_PLUGIN_PROMETHEUS_PORT=9090
```

### Component 6: ExportBackends (Optional)

**Purpose**: External observability system integration

**Responsibilities**:
- Export metrics to Prometheus
- Export traces to OTLP collectors
- Graceful degradation when deps unavailable

**Interfaces**:
```python
class PrometheusExporter:
    """Prometheus metrics exporter (requires prometheus-client)."""
    def start_server(self, port: int) -> None
    def update_metrics(self, metrics: MetricsCollector) -> None

class OTLPExporter:
    """OpenTelemetry exporter (requires opentelemetry-*)."""
    def export_spans(self, spans: list[Span]) -> None
    def shutdown(self) -> None
```

**Dependencies**:
- `prometheus-client` (optional)
- `opentelemetry-sdk`, `opentelemetry-exporter-otlp` (optional)

### Component 7: SessionIdentifier

**Purpose**: Generate and propagate unique session identifiers for multi-tenant telemetry

**Responsibilities**:
- Generate unique session ID at SessionStart
- Include human-readable components for debugging
- Persist session ID across hook invocations
- Add session ID as resource attribute to all telemetry

**Interfaces**:
```python
@dataclass(frozen=True)
class SessionInfo:
    """Session identification for multi-tenant telemetry."""
    session_id: str           # Full unique ID
    hostname: str             # Machine identifier
    repo_hash: str            # SHA256 of repo path (privacy)
    user_hash: str            # SHA256 of username (privacy)
    started_at: datetime      # Session start timestamp
    uuid_suffix: str          # UUID for uniqueness guarantee

def generate_session_id() -> SessionInfo:
    """Generate a new session identifier."""

def get_current_session() -> SessionInfo | None:
    """Get the current session from environment."""

def get_resource_attributes() -> dict[str, str]:
    """Get OTel resource attributes including session ID."""
```

**Session ID Format**:
```
{hostname}:{repo_hash[:8]}:{timestamp}:{uuid[:8]}
Example: macbook-pro:a1b2c3d4:20251225T120000:e5f6g7h8
```

**Resource Attributes** (OTel standard):
```python
{
    "service.name": "git-notes-memory",
    "service.version": "0.4.0",
    "session.id": "macbook-pro:a1b2c3d4:20251225T120000:e5f6g7h8",
    "host.name": "macbook-pro",
    "repository.hash": "a1b2c3d4e5f6g7h8",
    "user.hash": "x1y2z3w4v5u6t7s8",
}
```

**Metric Labels**:
All metrics automatically include `session_id` label for filtering:
```
memory_capture_duration_ms{session_id="macbook-pro:a1b2c3d4:...", status="success"} 45.2
```

**Dependencies**: None (stdlib hashlib, uuid, datetime)

## Data Design

### Metrics Data Models

```python
@dataclass
class CounterValue:
    """Monotonically increasing counter."""
    name: str
    labels: frozenset[tuple[str, str]]
    value: int
    created_at: float

@dataclass
class HistogramValue:
    """Distribution of observed values."""
    name: str
    labels: frozenset[tuple[str, str]]
    samples: deque[float]  # Rolling window
    sum: float
    count: int
    buckets: tuple[float, ...]  # Prometheus-style buckets

@dataclass
class GaugeValue:
    """Point-in-time value."""
    name: str
    labels: frozenset[tuple[str, str]]
    value: float
    updated_at: float
```

### Histogram Bucket Configuration

Based on hook timeout thresholds and web search best practices:

```python
# Default buckets for latency histograms (in milliseconds)
DEFAULT_LATENCY_BUCKETS = (
    1, 2, 5, 10, 25, 50, 100,  # Sub-100ms operations
    250, 500, 750, 1000,       # Sub-second (UserPromptSubmit 2s timeout)
    2000, 5000,                # 2-5s (SessionStart, Stop timeouts)
    10000, 15000, 30000,       # 10-30s (PreCompact 15s, default 30s)
    float('inf')
)
```

### Data Flow

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   @measure  │───>│  Metrics    │───>│   Export    │
│   duration  │    │  Collector  │    │  (optional) │
└─────────────┘    └─────────────┘    └─────────────┘
                          │
                          v
                   ┌─────────────┐
                   │  In-memory  │
                   │   storage   │
                   └─────────────┘
                          │
              ┌───────────┼───────────┐
              v           v           v
       ┌─────────┐  ┌─────────┐  ┌─────────┐
       │  JSON   │  │ Prometheus│ │  Text   │
       │ export  │  │  format  │  │ summary │
       └─────────┘  └─────────┘  └─────────┘
```

### Storage Strategy

**In-memory storage** (default):
- Thread-safe dict for counters, histograms, gauges
- Rolling window for histogram samples (default 3600 samples)
- No persistence (metrics reset on process restart)

**Export targets** (optional):
- Prometheus scrape endpoint (pull-based)
- OTLP collector (push-based)

## API Design

### CLI Commands

#### `/memory:metrics`

**Purpose**: View current metrics

**Options**:
| Option | Description | Default |
|--------|-------------|---------|
| `--format` | Output format: `text`, `json`, `prometheus` | `text` |
| `--filter` | Filter by metric name pattern | None |
| `--since` | Show metrics since timestamp | None |

**Example Output (text)**:
```
Memory Plugin Metrics
=====================

Operations:
  memory_capture_total: 42
  memory_search_total: 156

Latency (p50/p95/p99):
  capture_duration_ms: 45/120/350
  search_duration_ms: 12/35/89
  embed_duration_ms: 85/110/145

Hooks:
  hook_invocations_total{hook=session_start}: 12
  hook_invocations_total{hook=post_tool_use}: 89
  hook_timeout_pct{hook=user_prompt}: 0.5%
```

#### `/memory:traces`

**Purpose**: View recent traces

**Options**:
| Option | Description | Default |
|--------|-------------|---------|
| `--operation` | Filter by operation name | None |
| `--limit` | Maximum traces to show | 10 |
| `--status` | Filter by status (ok/error) | None |

#### `/memory:health --timing`

**Purpose**: Health check with timing information

**Output**:
```
Health Status: OK

Components:
  Index: OK (last sync: 2025-12-25T12:00:00Z)
  Embedding: OK (model loaded, 384 dims)
  Git: OK (repo configured)

Timing (last 5 minutes):
  Avg capture latency: 45ms
  Avg search latency: 12ms
  Hook timeout rate: 0.1%
```

## Integration Points

### Internal Integrations

| System | Integration Type | Purpose |
|--------|-----------------|---------|
| CaptureService | Decorator | Time capture operations |
| RecallService | Decorator | Time search operations |
| EmbeddingService | Decorator | Time embedding inference |
| IndexService | Decorator | Time database operations |
| GitOps | Decorator | Time subprocess calls |
| Hook handlers | Wrapper | Time hook execution |

### External Integrations

| Service | Integration Type | Purpose |
|---------|-----------------|---------|
| Prometheus | Scrape endpoint | Metrics collection |
| OTLP collector | gRPC push | Trace export |
| Jaeger | Via OTLP | Trace visualization |
| Datadog | Via OTLP | APM integration |

## Security Design

### Data Protection

- **No PII in metrics**: Metric labels contain only operation names, namespaces, status
- **No secrets in logs**: Structured logger sanitizes sensitive fields
- **Trace context only**: Trace IDs are random UUIDs, no user data

### Considerations

- Prometheus endpoint (if enabled) should be protected by network policy
- OTLP endpoint credentials via environment variables only
- Log files follow existing permission model

## Performance Considerations

### Expected Load

- Hook invocations: 10-100/minute per active session
- Capture operations: 1-10/minute
- Search operations: 5-50/minute
- Metrics emissions: ~1000/minute peak

### Performance Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| Decorator overhead | <1ms | Must not impact 2s hook timeout |
| Memory per hour | <10MB | In-memory storage constraint |
| JSON log format | <0.5ms | High-frequency logging |
| Metrics export | <100ms | Background operation |

### Optimization Strategies

1. **Lazy metric creation** - Only create labels on first use
2. **Efficient timestamp** - Use time.perf_counter() for timing, not datetime
3. **Batch span export** - Queue spans, export in batches
4. **Struct caching** - Cache Prometheus format templates
5. **Rolling windows** - Bound histogram sample storage

## Reliability & Operations

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| Metrics collector full | Memory growth | Rolling window eviction |
| OTLP export fails | Spans lost | Retry with backoff, then drop |
| Prometheus endpoint down | No scrape | Metrics accumulate, timeout eviction |
| Logger fails | Log loss | Fallback to stderr |

### Graceful Degradation

1. **Missing optional deps** - Features disabled, no errors
2. **Export failures** - Operations continue, metrics lost
3. **High cardinality** - Label limits enforced
4. **Memory pressure** - Oldest samples evicted

### Monitoring & Alerting

Self-monitoring metrics:
- `observability_metrics_count` - Number of unique metrics
- `observability_export_errors_total` - Export failure count
- `observability_memory_bytes` - Memory usage

## Testing Strategy

### Unit Testing

- MetricsCollector thread safety tests
- Decorator timing accuracy tests
- Structured logger format tests
- Configuration loading tests

### Integration Testing

- End-to-end trace propagation
- Prometheus format compliance
- OTLP export validation

### Performance Testing

- Decorator overhead benchmarks
- Memory growth under load
- Concurrent access stress tests

## Module Structure

```
src/git_notes_memory/
├── observability/
│   ├── __init__.py           # Public API exports
│   ├── config.py             # ObservabilityConfig
│   ├── metrics.py            # MetricsCollector
│   ├── tracing.py            # SpanContext, trace_operation
│   ├── logging.py            # StructuredLogger
│   ├── decorators.py         # measure_duration
│   └── exporters/
│       ├── __init__.py
│       ├── prometheus.py     # Optional Prometheus exporter
│       └── otlp.py           # Optional OTLP exporter
```

## Local Observability Stack (Docker Compose)

### Stack Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Docker Compose Network                              │
│                                                                              │
│  ┌─────────────────┐                                                        │
│  │   git-notes-    │                                                        │
│  │   memory        │                                                        │
│  │   (host)        │                                                        │
│  └────────┬────────┘                                                        │
│           │ OTLP (4317)                                                     │
│           v                                                                  │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │  OTEL Collector │────>│   Prometheus    │<────│    Grafana      │       │
│  │  (4317, 4318)   │     │     (9090)      │     │     (3000)      │       │
│  └────────┬────────┘     └─────────────────┘     └────────┬────────┘       │
│           │                                               │                 │
│           v                                               v                 │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │     Tempo       │<────│                 │     │  Pre-built      │       │
│  │     (3200)      │     │    Collector    │     │  Dashboards     │       │
│  └─────────────────┘     │    Pipelines    │     └─────────────────┘       │
│           ^               │                 │                               │
│           │               └─────────────────┘                               │
│  ┌────────┴────────┐                                                        │
│  │      Loki       │                                                        │
│  │     (3100)      │                                                        │
│  └─────────────────┘                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Service Configuration

#### OTEL Collector

**Image**: `otel/opentelemetry-collector-contrib:latest`

**Receivers**:
- OTLP gRPC on port 4317
- OTLP HTTP on port 4318

**Exporters**:
- Prometheus (for Prometheus scraping)
- OTLP/HTTP to Tempo (traces)
- Loki (logs)

**Processors**:
- Batch processing for efficiency
- Memory limiter for stability
- Resource detection (session_id enrichment)

```yaml
# otel-collector-config.yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 1s
    send_batch_size: 1024
  memory_limiter:
    limit_mib: 512
    spike_limit_mib: 128
    check_interval: 1s

exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true
  loki:
    endpoint: http://loki:3100/loki/api/v1/push

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheus]
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/tempo]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [loki]
```

#### Grafana

**Image**: `grafana/grafana:latest`

**Pre-configured**:
- Datasources auto-provisioned
- Dashboards auto-provisioned
- Anonymous access for local dev

**Datasources**:
```yaml
# grafana/provisioning/datasources/datasources.yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
  - name: Tempo
    type: tempo
    url: http://tempo:3200
  - name: Loki
    type: loki
    url: http://loki:3100
```

#### Pre-built Dashboards

**Memory Operations Dashboard** (`memory-operations.json`):

| Panel | Type | Metrics/Queries |
|-------|------|-----------------|
| Capture Latency | Time series | `histogram_quantile(0.95, memory_capture_duration_ms_bucket)` |
| Search Latency | Time series | `histogram_quantile(0.95, memory_search_duration_ms_bucket)` |
| Operations/min | Stat | `rate(memories_captured_total[5m]) * 60` |
| Error Rate | Gauge | `rate(capture_errors_total[5m]) / rate(memories_captured_total[5m])` |
| Hook Timeout % | Table | `hook_timeout_pct_used` by hook |
| Active Sessions | Stat | `count(count by (session_id)(memory_capture_duration_ms_count))` |
| Session Details | Table | Grouped by `session_id` with latency stats |

**Hook Performance Dashboard** (`hook-performance.json`):

| Panel | Type | Metrics/Queries |
|-------|------|-----------------|
| Hook Latency by Type | Heatmap | `hook_execution_duration_ms_bucket` |
| Timeout Warnings | Alert list | `hook_timeout_pct_used > 80` |
| Invocations/min | Bar chart | `rate(hook_invocations_total[5m]) * 60` by hook |
| Error Rate by Hook | Table | `hook_errors_total` by hook and error |

**Trace Explorer**:
- Link from dashboard panels to Tempo traces
- Filter by `session_id` resource attribute
- Correlate with logs via trace ID

### Docker Compose File

```yaml
# docker-compose.observability.yaml
version: '3.8'

services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config", "/etc/otel-collector-config.yaml"]
    volumes:
      - ./observability/otel-collector-config.yaml:/etc/otel-collector-config.yaml:ro
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
      - "8889:8889"   # Prometheus scrape endpoint
    depends_on:
      - tempo
      - loki

  prometheus:
    image: prom/prometheus:latest
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    volumes:
      - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
    volumes:
      - ./observability/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./observability/grafana/dashboards:/var/lib/grafana/dashboards:ro
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
      - tempo
      - loki

  tempo:
    image: grafana/tempo:latest
    command: ["-config.file=/etc/tempo.yaml"]
    volumes:
      - ./observability/tempo.yaml:/etc/tempo.yaml:ro
      - tempo_data:/tmp/tempo
    ports:
      - "3200:3200"   # Tempo API
      - "4317"        # OTLP gRPC (internal)

  loki:
    image: grafana/loki:latest
    command: ["-config.file=/etc/loki/local-config.yaml"]
    volumes:
      - loki_data:/loki
    ports:
      - "3100:3100"

volumes:
  prometheus_data:
  grafana_data:
  tempo_data:
  loki_data:
```

### Usage

```bash
# Start the observability stack
cd docker/
docker compose -f docker-compose.observability.yaml up -d

# Configure the plugin to use local collector
export MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4317

# View dashboards
open http://localhost:3000

# Stop the stack
docker compose -f docker-compose.observability.yaml down
```

### File Structure

```
docker/
├── docker-compose.observability.yaml
└── observability/
    ├── otel-collector-config.yaml
    ├── prometheus.yml
    ├── tempo.yaml
    └── grafana/
        ├── provisioning/
        │   ├── datasources/
        │   │   └── datasources.yaml
        │   └── dashboards/
        │       └── dashboards.yaml
        └── dashboards/
            ├── memory-operations.json
            └── hook-performance.json
```

## Future Considerations

### Planned Extensions

1. **Auto-instrumentation** - Automatic patching of common libraries
2. **Sampling** - Configurable trace sampling for high-volume deployments
3. **Custom metrics** - User-defined metrics via configuration
4. **Dashboard templates** - Grafana/Datadog dashboard JSON exports

### Technical Debt

1. **Migrate existing logging** - Gradual replacement of logger.info() with structured
2. **Remove HOOK_DEBUG** - Fully replace with unified debug levels
3. **Type stub generation** - For optional dependency type checking
