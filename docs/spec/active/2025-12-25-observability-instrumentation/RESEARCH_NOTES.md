---
document_type: research
project_id: SPEC-2025-12-25-001
last_updated: 2025-12-25T23:50:00Z
---

# Observability Instrumentation - Research Notes

## Research Summary

This document captures findings from codebase analysis and external research conducted during the planning phase for observability instrumentation.

## Codebase Analysis

### Current Logging Inventory

| Module | Logger Calls | Coverage | Notes |
|--------|--------------|----------|-------|
| capture.py | 9 | Lock, capture, embed, index | Missing: lock release errors |
| recall.py | 8 | Search, hydration, batch | Missing: timing |
| embedding.py | 9 | Model load, prewarm, errors | Missing: load duration |
| index.py | 3 | Minimal | Missing: operation timing |
| git_ops.py | 8 | Git operations, timeouts | Missing: subprocess timing |
| sync.py | 1+ | Sync operations | Missing: verification failures |
| Hook handlers | 81 | Extensive | Missing: execution timing |

**Total**: ~92 logging statements across the codebase.

### Critical Operation Paths

#### Capture Pipeline (capture.py:350-554)

```
Lock Acquisition (59-123)
├─ Timeout: 10 seconds configurable
├─ Retry interval: 100ms
├─ Logging: debug on acquire/release
└─ Silent failure: OSError on release (line 122-123)

Validation (280-300)
├─ Namespace, summary length, content size
└─ All logged at WARNING level

Commit Resolution (476-483)
├─ get_commit_info() call
└─ Silent exception: Line 489 - except Exception: index = 0

Git Note Writing (496-503)
├─ append_note() subprocess
├─ Timeout: 30 seconds
└─ Error: raises CaptureError

Embedding & Indexing (520-547)
├─ Conditional on index_service availability
├─ Graceful degradation on failure
└─ Warning logs on embed/index failure
```

#### Search Pipeline (recall.py:136-214)

```
Query Embedding (173-175)
├─ Calls _get_embedding()
├─ May trigger model load (lazy)
└─ Timing: Unknown

Vector Search (179-184)
├─ KNN query via sqlite-vec
├─ Distance calculation
└─ Debug log: result count

Result Processing (188-197)
├─ Distance to similarity conversion
└─ Min similarity filtering
```

### Hook Timeout Configuration

Source: `src/git_notes_memory/config.py` (lines 530-533)

| Hook | Timeout | Criticality |
|------|---------|-------------|
| SessionStart | 5s | Medium |
| UserPromptSubmit | 2s | **High** (blocks UI) |
| PostToolUse | 5s | Medium |
| PreCompact | 15s | Low |
| Stop | 5s | Medium |
| Default | 30s | Fallback |

**Platform Note**: Timeout uses SIGALRM, only works on Unix. Windows has no timeout enforcement.

### Silent Failure Points

| File | Line | Context | Impact |
|------|------|---------|--------|
| capture.py | 122-123 | Lock release OSError | Silent cleanup failure |
| capture.py | 489-490 | Note parsing exception | Index defaults to 0 |
| git_ops.py | 1084 | Push failure after merge | Silent no-op |
| sync.py | 444-445 | Hash verification exception | Skipped in drift |
| index.py | 300-301 | Index creation OperationalError | Suppressed error |

### Subprocess Operations Without Timeout

| Call | File | Line | Risk |
|------|------|------|------|
| git cat-file --batch | git_ops.py | 481 | **No timeout, can hang** |

### Existing HOOK_DEBUG Usage

- All hook handlers check `HOOK_DEBUG` environment variable
- When enabled, logs input/output JSON to files
- Location: `~/.local/share/memory-plugin/logs/{hookname}.log`
- Rotating file handler: 5MB per file, 5 backups

## Technical Research

### OpenTelemetry Python Best Practices

**Source**: [OpenTelemetry Python Docs](https://opentelemetry.io/docs/languages/python/)

**Key Findings**:

1. **Library vs Application Pattern**:
   - Libraries should only depend on `opentelemetry-api`
   - SDK is application's choice
   - Follows our extras pattern perfectly

2. **Version Compatibility**:
   - Use `~= 1.32.0` style for tight compatibility
   - API and SDK versions must match
   - Current stable: 1.39.1 (Dec 2025)

3. **Optional Dependency Pattern**:
   ```python
   # From opentelemetry-python-contrib
   # Optional deps have extra field: extra == 'instruments'
   ```

4. **Instrumentation Pattern**:
   - Move dependency checks into Instrumentor.instrument()
   - Don't require all optional deps to be installed

### Prometheus Histogram Buckets

**Sources**:
- [Prometheus Client Python](https://prometheus.github.io/client_python/instrumenting/histogram/)
- [Prometheus Histograms Best Practices](https://prometheus.io/docs/practices/histograms/)

**Key Findings**:

1. **Default Buckets**:
   ```python
   # 15 buckets: 5ms to 10s
   (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
   ```

2. **SLO Alignment**:
   > "If your SLO is 99% of requests under 300ms, include buckets around 200ms, 300ms, and 400ms"

3. **Trade-offs**:
   - More buckets = better accuracy but larger payload
   - Default buckets tailored for web services (ms to seconds)
   - Custom buckets recommended for specific use cases

4. **Recommended Pattern**:
   ```python
   h = Histogram('request_latency_seconds', 'Description',
                 buckets=[0.1, 0.2, 0.5, 1.0, 2.0, 5.0])
   ```

### Structured Logging: structlog vs python-json-logger

**Sources**:
- [structlog documentation](https://www.structlog.org/)
- [Better Stack Logging Comparison](https://betterstack.com/community/guides/logging/best-python-logging-libraries/)

**Key Findings**:

1. **structlog**:
   - Full-featured structured logging library
   - Context binding for automatic field inclusion
   - Processor pipeline for formatting
   - Native log levels faster than stdlib
   - Colorized console output for development
   - Recommended for new projects

2. **python-json-logger**:
   - Simple JSON formatter for stdlib logging
   - Less opinionated, smaller scope
   - Works well for adding JSON to existing setups

3. **Recommendation**:
   > "structlog is a robust option for structured logging"
   > "Modern cloud-native applications need structured logs"

4. **Combined Usage**:
   - Can use python-json-logger to format structlog output
   - Useful for stdlib compatibility

## Competitive Analysis

### How Other Python Projects Handle Observability

| Project | Approach | Notes |
|---------|----------|-------|
| FastAPI | OpenTelemetry integration | Optional via starlette-exporter |
| Django | django-prometheus, django-otel | Multiple community packages |
| Celery | Built-in events, optional Prometheus | Event-based architecture |
| SQLAlchemy | Engine events for timing | Callback-based |

### Common Patterns Identified

1. **Decorator-based timing** - Universal pattern
2. **Optional dependencies** - Standard for plugins/libraries
3. **Graceful degradation** - Expected behavior
4. **Contextvar propagation** - Standard for async-safe tracing

## Recommended Approaches

### Module Structure

```
src/git_notes_memory/observability/
├── __init__.py           # Public API, lazy imports
├── config.py             # Configuration loading
├── metrics.py            # In-memory metrics collector
├── tracing.py            # Span context propagation
├── logging.py            # Structured logger
├── decorators.py         # @measure_duration
└── exporters/
    ├── __init__.py
    ├── prometheus.py     # Optional
    └── otlp.py           # Optional
```

### Histogram Bucket Configuration

Aligned with hook timeouts:

```python
DEFAULT_LATENCY_BUCKETS = (
    1, 2, 5, 10, 25, 50, 100,    # Sub-100ms
    250, 500, 750, 1000,         # Sub-second
    2000, 5000,                  # Hook timeout range
    10000, 15000, 30000,         # Extended operations
    float('inf')
)
```

### Configuration Environment Variables

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

## Anti-Patterns to Avoid

1. **High cardinality labels** - Don't include user IDs, file paths, or unbounded values in metric labels
2. **Blocking exports** - Never block core operations waiting for export
3. **Unbounded memory** - Always use rolling windows for histogram samples
4. **Synchronous OTLP** - Use async/batch export to avoid latency
5. **Over-instrumentation** - Don't measure trivial operations

## Open Questions from Research

All resolved during elicitation:

- [x] Debug level naming → Standard (quiet/info/debug/trace)
- [x] Export formats → All four (JSON, Prometheus, OTLP, text)
- [x] Backward compatibility → JSON as default, text opt-out
- [x] Tier priority → All three tiers with optional extras

## Sources

### Official Documentation
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Prometheus Client Python](https://prometheus.github.io/client_python/)
- [structlog](https://www.structlog.org/)
- [Python logging module](https://docs.python.org/3/library/logging.html)

### Best Practices Guides
- [OpenTelemetry Best Practices](https://betterstack.com/community/guides/observability/opentelemetry-best-practices/)
- [Prometheus Histograms Guide](https://prometheus.io/docs/practices/histograms/)
- [Python Logging Best Practices](https://betterstack.com/community/guides/logging/best-python-logging-libraries/)

### Codebase References
- `src/git_notes_memory/config.py:530-533` - Hook timeout constants
- `src/git_notes_memory/hooks/hook_utils.py` - Timeout implementation
- `src/git_notes_memory/capture.py` - Main capture pipeline
- `src/git_notes_memory/recall.py` - Search pipeline
- `tests/test_hooks_performance.py` - Performance thresholds
