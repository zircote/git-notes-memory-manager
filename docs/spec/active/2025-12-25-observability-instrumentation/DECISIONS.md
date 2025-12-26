---
document_type: decisions
project_id: SPEC-2025-12-25-001
---

# Observability Instrumentation - Architecture Decision Records

## ADR-001: Optional Dependencies via Extras

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: User, Claude

### Context

The observability system requires external libraries for full functionality (OpenTelemetry, prometheus-client). The core git-notes-memory package should remain lightweight with minimal dependencies, especially since it runs in Claude Code hooks with strict timeout constraints.

### Decision

Use Python's `extras_require` pattern to make observability dependencies optional:

```toml
[project.optional-dependencies]
monitoring = [
    "opentelemetry-api ~= 1.32.0",
    "opentelemetry-sdk ~= 1.32.0",
    "opentelemetry-exporter-otlp-proto-grpc ~= 1.32.0",
    "prometheus-client >= 0.17.0",
]
```

Users install via `pip install git-notes-memory[monitoring]`.

### Consequences

**Positive:**
- Core package adds zero new runtime dependencies
- Hook execution remains fast (no heavy imports)
- Users choose their observability stack

**Negative:**
- Conditional imports throughout observability code
- Testing requires both with/without extras scenarios
- Some features unavailable without extras

**Neutral:**
- Follows OpenTelemetry's own guidance for library instrumentation

### Alternatives Considered

1. **All dependencies required**: Rejected - adds unnecessary bloat for users who don't need monitoring
2. **Separate package (git-notes-memory-otel)**: Rejected - fragments the ecosystem unnecessarily
3. **Vendored minimal implementations**: Rejected - maintenance burden, compatibility issues

---

## ADR-002: Unified Debug Levels (quiet/info/debug/trace)

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: User, Claude

### Context

The codebase currently uses `HOOK_DEBUG=true/false` for hook debugging. This is binary and doesn't provide granular control. Different users need different verbosity levels:
- Production: Minimal output
- Development: Standard logging
- Debugging: Detailed traces
- Investigation: Full trace context

### Decision

Replace `HOOK_DEBUG` with a unified debug level system:

```bash
MEMORY_PLUGIN_LOG_LEVEL=quiet   # Errors only
MEMORY_PLUGIN_LOG_LEVEL=info    # Normal operation (default)
MEMORY_PLUGIN_LOG_LEVEL=debug   # Detailed debugging
MEMORY_PLUGIN_LOG_LEVEL=trace   # Full trace context, all spans
```

Standard naming (quiet/info/debug/trace) was chosen over semantic (silent/normal/verbose) or numeric (0/1/2/3).

### Consequences

**Positive:**
- Familiar naming for developers (matches Python logging)
- Granular control over verbosity
- Single configuration point

**Negative:**
- Breaking change for users relying on HOOK_DEBUG
- Requires documentation update

**Neutral:**
- HOOK_DEBUG can be deprecated with warning, pointing to new variable

### Alternatives Considered

1. **Semantic names (silent/normal/verbose/trace)**: Rejected - less familiar to Python developers
2. **Numeric levels (0/1/2/3)**: Rejected - less readable in configuration
3. **Keep HOOK_DEBUG, add separate flag**: Rejected - confusing with two overlapping controls

---

## ADR-003: JSON Structured Logging as Default

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: User, Claude

### Context

Current logging uses unstructured string messages with Python's standard logging. Modern observability systems (ELK, Loki, CloudWatch, Datadog) work better with structured JSON logs that can be queried and filtered by field.

### Decision

Make JSON structured logging the default format:

```json
{
  "timestamp": "2025-12-25T12:00:00.000Z",
  "level": "INFO",
  "message": "Memory captured successfully",
  "service": "git-notes-memory",
  "trace_id": "abc123def",
  "span_id": "xyz789",
  "namespace": "decisions"
}
```

Text format available via `MEMORY_PLUGIN_LOG_FORMAT=text` for backward compatibility.

### Consequences

**Positive:**
- Machine-parseable logs for observability pipelines
- Automatic trace context injection
- Better query/filter capabilities
- Consistent log schema

**Negative:**
- Harder to read raw logs in terminal during development
- Existing log analysis tools may need updates
- Slightly larger log output

**Neutral:**
- Text format remains available for users who prefer it

### Alternatives Considered

1. **Keep text format as default**: Rejected - misses opportunity for modern observability
2. **Dual output (both formats)**: Rejected - unnecessary complexity, storage overhead
3. **Gradual migration with deprecated warning**: Possible - but user preferred immediate adoption

---

## ADR-004: In-Memory Metrics with Rolling Window

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude (technical decision)

### Context

Metrics need to be stored somewhere between emission and export. Options include:
- External metrics backend (requires dependency)
- In-memory storage (no dependencies)
- File-based storage (persistence but I/O overhead)

Hook processes are short-lived, so persistence across invocations is not expected.

### Decision

Use in-memory storage with rolling window for histogram samples:

```python
@dataclass
class HistogramValue:
    samples: deque[float]  # Rolling window, maxlen=3600
    sum: float
    count: int
    buckets: tuple[float, ...]
```

Default retention: 3600 samples per histogram (configurable via `MEMORY_PLUGIN_METRICS_RETENTION`).

### Consequences

**Positive:**
- Zero external dependencies
- Fast access (no I/O)
- Bounded memory usage
- Thread-safe with Lock

**Negative:**
- Metrics lost on process restart
- Not suitable for long-running aggregation
- Memory grows with metric cardinality

**Neutral:**
- Export to external systems (Prometheus/OTLP) for persistence

### Alternatives Considered

1. **SQLite storage**: Rejected - I/O overhead, hook timeout risk
2. **Shared memory**: Rejected - cross-process complexity, platform-specific
3. **Redis**: Rejected - external dependency, network overhead

---

## ADR-005: Contextvars for Span Propagation

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude (technical decision)

### Context

Distributed tracing requires propagating trace context (trace_id, span_id) through the call stack. Options:
- Thread-local storage
- Explicit parameter passing
- contextvars module

### Decision

Use Python's `contextvars` module for span context propagation:

```python
from contextvars import ContextVar

_current_span: ContextVar[Span | None] = ContextVar('current_span', default=None)

@contextmanager
def trace_operation(operation: str, **tags):
    span = Span(trace_id=get_or_create_trace_id(), ...)
    token = _current_span.set(span)
    try:
        yield span
    finally:
        _current_span.reset(token)
```

### Consequences

**Positive:**
- Thread-safe by design
- Works with asyncio
- Clean context isolation
- Standard library (no dependencies)

**Negative:**
- Slightly more complex than thread-locals
- Context must be explicitly copied for thread pools

**Neutral:**
- Follows OpenTelemetry's approach

### Alternatives Considered

1. **Thread-local storage**: Rejected - doesn't work with asyncio
2. **Explicit parameter passing**: Rejected - invasive API changes throughout codebase
3. **Global state**: Rejected - not thread-safe

---

## ADR-006: Decorator Pattern for Timing

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude (technical decision)

### Context

Every critical operation needs timing instrumentation. Implementation options:
- Context managers at each call site
- Decorators on methods
- Monkey-patching
- AOP-style instrumentation

### Decision

Use decorators for timing instrumentation:

```python
@measure_duration("memory_capture", labels={"service": "capture"})
def capture(self, namespace: str, ...) -> CaptureResult:
    ...
```

### Consequences

**Positive:**
- Clean, declarative syntax
- Non-invasive to method implementation
- Easy to identify instrumented methods
- Composable with other decorators

**Negative:**
- Adds small overhead even when observability disabled
- Cannot instrument mid-function without refactoring
- Decorator order matters

**Neutral:**
- Pattern is familiar to Python developers

### Alternatives Considered

1. **Context managers everywhere**: Rejected - verbose, repetitive
2. **Monkey-patching at import**: Rejected - fragile, hard to debug
3. **AOP framework**: Rejected - external dependency, complexity

---

## ADR-007: Prometheus Histogram Bucket Configuration

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude (technical decision)

### Context

Prometheus histograms require bucket boundaries defined at initialization. The default prometheus-client buckets (0.005s to 10s) may not align with hook timeout thresholds (2s, 5s, 15s, 30s).

### Decision

Use custom bucket configuration aligned with hook timeouts:

```python
DEFAULT_LATENCY_BUCKETS = (
    1, 2, 5, 10, 25, 50, 100,    # Sub-100ms operations
    250, 500, 750, 1000,         # Sub-second (UserPromptSubmit 2s)
    2000, 5000,                  # 2-5s (SessionStart, Stop)
    10000, 15000, 30000,         # 10-30s (PreCompact, default)
    float('inf')
)
```

Values in milliseconds for clarity; convert for Prometheus (expects seconds).

### Consequences

**Positive:**
- Accurate percentile calculation around SLO thresholds
- Meaningful alerting on hook timeout approach
- Covers full range of expected latencies

**Negative:**
- More buckets = larger Prometheus payload
- May need adjustment based on actual latency distribution

**Neutral:**
- Can be overridden via configuration if needed

### Alternatives Considered

1. **Use default buckets**: Rejected - poor alignment with hook timeouts
2. **Fewer buckets**: Rejected - loses precision around SLO boundaries
3. **Dynamic bucket calculation**: Rejected - complexity, requires warmup period

---

## ADR-008: Graceful Degradation Pattern

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude (technical decision)

### Context

Observability features should never block or break core functionality. When optional dependencies are missing or exports fail, the system must continue operating.

### Decision

Implement graceful degradation at all integration points:

```python
# Import pattern
try:
    from opentelemetry.sdk.trace import TracerProvider
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

# Usage pattern
def export_traces(spans: list[Span]) -> None:
    if not OTEL_AVAILABLE:
        return  # Silent no-op
    try:
        _exporter.export(spans)
    except Exception:
        logger.warning("OTLP export failed, traces dropped")
        # Continue without raising
```

### Consequences

**Positive:**
- Core operations never blocked by observability failures
- Users without extras get full core functionality
- Export failures don't crash the application

**Negative:**
- Silently dropped data may confuse operators
- Harder to debug "why aren't my traces appearing"
- Requires comprehensive null-checking

**Neutral:**
- Warning logs surface issues without blocking

### Alternatives Considered

1. **Fail fast on missing deps**: Rejected - poor UX for users who don't need monitoring
2. **Queue and retry indefinitely**: Rejected - memory growth, delayed failures
3. **Feature flags with explicit opt-in**: Considered - but graceful degradation is simpler

---

## ADR-009: Command Naming Convention

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: User, Claude

### Context

New CLI commands need consistent naming. Existing commands follow `/memory:*` pattern (e.g., `/memory:capture`, `/memory:recall`). Observability commands could follow the same pattern or use a sub-namespace.

### Decision

Use `/memory:*` pattern for observability commands:

- `/memory:metrics` - View metrics
- `/memory:traces` - View traces
- `/memory:health --timing` - Health with timing info

### Consequences

**Positive:**
- Consistent with existing commands
- Discoverable via `/memory:` prefix
- No sub-namespace complexity

**Negative:**
- Growing number of commands in `/memory:*` namespace
- May need categorization in future

**Neutral:**
- Matches user expectations for plugin commands

### Alternatives Considered

1. **Sub-namespace (/memory:obs:*)**: Rejected - adds typing complexity
2. **Separate namespace (/observe:*)**: Rejected - fragments plugin surface
3. **Flags on existing commands**: Rejected - conflates purposes

---

## ADR-010: Session Identification Strategy

**Date**: 2025-12-26
**Status**: Accepted
**Deciders**: User, Claude

### Context

When multiple users or Claude Code sessions send telemetry to the same collector (e.g., a shared Grafana Cloud instance), their data must be distinguishable. Without session identification, debugging becomes impossible when multiple sessions' traces and metrics are interleaved.

### Decision

Generate a unique session ID at `SessionStart` hook invocation with the following format:

```
{hostname}:{repo_hash}:{timestamp}:{uuid_suffix}
```

Example: `macbook-pro:a1b2c3d4:20251225T120000:550e8400`

Components:
- **hostname**: Machine identifier for quick filtering
- **repo_hash**: SHA256 of repo absolute path (first 8 chars) - privacy-preserving
- **timestamp**: ISO8601 compact format for temporal ordering
- **uuid_suffix**: First 8 chars of UUID4 for uniqueness guarantee

The session ID is:
- Set as OTel resource attribute (`session.id`)
- Added as Prometheus label on all metrics
- Injected into all structured log entries
- Persisted in environment for hook process lifetime

### Consequences

**Positive:**
- Each session fully distinguishable in shared collectors
- Human-readable format aids debugging
- Privacy-preserving (hashes, not raw paths)
- Works across metrics, traces, and logs

**Negative:**
- Increased cardinality in Prometheus (one session_id label value per session)
- Slightly larger payloads
- Requires SessionStart hook for generation

**Neutral:**
- Session ID reused across hooks within same Claude Code session
- New sessions get new IDs (stateless between sessions)

### Alternatives Considered

1. **UUID only**: Rejected - not human-readable, hard to correlate visually
2. **Process PID**: Rejected - reused across sessions, not unique
3. **Username in plain text**: Rejected - privacy concern in shared environments
4. **Persistent session across restarts**: Rejected - complexity, storage requirements

---

## ADR-011: Local Observability Stack (Docker Compose)

**Date**: 2025-12-26
**Status**: Accepted
**Deciders**: User, Claude

### Context

Developers need an easy way to test and validate observability features locally without setting up external services. Production observability providers (Datadog, Grafana Cloud, etc.) require accounts and API keys, creating friction for development and testing.

### Decision

Provide a Docker Compose stack for local observability with the following services:

| Service | Image | Purpose | Port |
|---------|-------|---------|------|
| OTEL Collector | `otel/opentelemetry-collector-contrib` | Receives OTLP, routes to backends | 4317, 4318 |
| Prometheus | `prom/prometheus` | Metrics storage and querying | 9090 |
| Grafana | `grafana/grafana` | Visualization and dashboards | 3000 |
| Tempo | `grafana/tempo` | Distributed trace storage | 3200 |
| Loki | `grafana/loki` | Log aggregation | 3100 |

Stack features:
- Single `docker compose -f docker/docker-compose.observability.yaml up` command
- Pre-configured datasources in Grafana
- Pre-built dashboards for memory plugin metrics
- Volume persistence for data between restarts
- Health checks for all services

Default environment variables for plugin:
```bash
MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4317
MEMORY_PLUGIN_PROMETHEUS_PUSHGATEWAY=http://localhost:9091
```

### Consequences

**Positive:**
- Zero-friction local observability testing
- Consistent environment across developers
- Production-like telemetry flow for validation
- Pre-built dashboards provide immediate value

**Negative:**
- Docker required on developer machines
- Resource usage (~1GB RAM for full stack)
- Maintenance burden for image version updates

**Neutral:**
- Optional - developers can use external providers directly
- Stack designed for development, not production scale

### Alternatives Considered

1. **Jaeger only**: Rejected - traces only, no metrics or logs
2. **All-in-one Grafana stack image**: Rejected - less flexibility, harder to customize
3. **Kubernetes manifests**: Rejected - overkill for local development
4. **No local stack**: Rejected - friction for development and testing
