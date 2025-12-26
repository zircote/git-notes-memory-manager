---
document_type: requirements
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T23:50:00Z
status: draft
github_issue: 10
---

# Observability Instrumentation and Distributed Tracing - Product Requirements Document

## Executive Summary

This specification defines comprehensive observability instrumentation for the git-notes-memory plugin. The implementation adds operation timing, structured logging, metrics collection, and distributed tracing to enable performance monitoring, debugging, and operational insights.

The current codebase has ~92 logging statements but lacks structured telemetry, correlation IDs, and performance metrics. This makes diagnosing issues, identifying bottlenecks, and understanding system behavior extremely difficult.

The solution implements a three-tier approach:
- **Tier 1**: Operation timing decorator, hook metrics, in-memory collection (MVP)
- **Tier 2**: Structured JSON logging, correlation IDs, full metrics with Prometheus export
- **Tier 3**: OpenTelemetry integration with OTLP export

All observability features use optional extras (`pip install .[monitoring]`) to keep the core package lightweight.

## Problem Statement

### The Problem

The git-notes-memory plugin lacks observability infrastructure:

1. **Basic Python logging only** - 92 unstructured string log statements across the codebase
2. **No correlation IDs** - Cannot trace operations across services (capture→embed→index)
3. **No performance metrics** - Unknown latency, throughput, or resource usage
4. **No distributed tracing** - No span context propagation
5. **Silent hook failures** - All hooks exit(0), errors invisible to users
6. **No operation timing** - Critical paths (embedding, vector search, git operations) unmeasured

### Impact

| User Type | Pain Point |
|-----------|------------|
| Plugin users | Cannot diagnose slow operations or understand why hooks timeout |
| Developers | Cannot identify bottlenecks during feature development |
| Operators | Cannot monitor system health in production deployments |
| Contributors | Cannot correlate failures across the capture→embed→index pipeline |

### Current State

The codebase analysis reveals:

| Dimension | Status | Grade |
|-----------|--------|-------|
| Logging coverage | 92 statements | C+ |
| Hook timeouts | 4/5 hooks protected | D |
| Error visibility | Most logged, 5+ silent | C |
| Performance metrics | None | F |
| Structured logging | Limited | D |

**Critical Gaps Identified:**
- `stop_handler.py` lacks all timeout protection
- `capture.py:489` - Silent exception during note parsing
- `git_ops.py:481` - cat-file batch has no timeout
- No metrics for embedding/search latency
- No visibility into lock contention

## Goals and Success Criteria

### Primary Goal

Enable comprehensive observability for git-notes-memory operations to support debugging, performance optimization, and production monitoring.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Critical path coverage | 100% of 6 core operations instrumented | Code audit of timing decorators |
| Hook timing visibility | All 5 hooks report execution duration | `/memory:metrics` output verification |
| Silent failure elimination | 0 silent exceptions without logging | Static analysis + test coverage |
| Structured log adoption | 100% of new logs use structured format | Code review check |
| Optional dependency isolation | Core package adds 0 new runtime deps | `pip show git-notes-memory` verification |

### Non-Goals (Explicit Exclusions)

- **Real-time alerting** - Metrics export enables alerting but we don't implement rules
- **Log aggregation** - We produce structured logs; aggregation is user's infrastructure
- **Auto-remediation** - We surface issues; users decide how to respond
- **Retroactive instrumentation of tests** - New tests may use observability; existing tests unchanged
- **UI dashboard** - CLI metrics output only; visualization is external tooling

## User Analysis

### Primary Users

| User Type | Role | Needs | Context |
|-----------|------|-------|---------|
| Plugin developers | Internal devs | Debug hook performance, trace failures | Development/testing |
| Claude Code users | End users | Understand slow operations, timeout causes | Daily usage |
| Platform operators | Ops/SRE | Monitor production deployments, set up alerts | Production monitoring |
| Open source contributors | External devs | Understand codebase behavior, contribute fixes | Development |

### User Stories

1. **As a plugin developer**, I want to see operation timing so that I can identify performance bottlenecks
2. **As a Claude Code user**, I want to understand why my hooks are slow so that I can configure them appropriately
3. **As a platform operator**, I want to export metrics to Prometheus so that I can set up alerting dashboards
4. **As a contributor**, I want correlation IDs in logs so that I can trace requests across services

## Functional Requirements

### Must Have (P0)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | `@measure_duration` decorator for operation timing | Core timing mechanism | Decorator applied to 6 critical operations, emits histogram metrics |
| FR-002 | Hook execution timing with timeout tracking | Hooks are timing-critical (2-30s limits) | All 5 hooks report duration, timeout percentage used |
| FR-003 | In-memory metrics collection | Must work without external dependencies | MetricsCollector stores counters, histograms, gauges |
| FR-004 | `/memory:metrics` command | User-facing metrics access | Command outputs operation statistics in plain text |
| FR-005 | Unified debug levels (quiet/info/debug/trace) | Replace fragmented HOOK_DEBUG | Single env var controls all observability verbosity |
| FR-006 | JSON export format for metrics | Machine-readable output for tooling | `/memory:metrics --format=json` works |
| FR-007 | Session identification in all telemetry | Multi-user distinguishability | session_id resource attribute on all spans/metrics |

### Should Have (P1)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-101 | Structured JSON logging throughout codebase | Modern observability standard | New StructuredLogger class, JSON format default |
| FR-102 | Correlation IDs for request tracing | Trace operations across services | trace_id propagates capture→embed→index |
| FR-103 | Prometheus text format export | Standard monitoring integration | `/memory:metrics --format=prometheus` works |
| FR-104 | Context propagation via contextvars | Thread-safe trace context | Span context available in nested calls |
| FR-105 | All proposed metrics from GitHub issue | Complete metrics coverage | Counters, histograms, gauges as specified |
| FR-106 | Graceful degradation metrics | Track "capture without index" patterns | Metric for partial success operations |

### Nice to Have (P2)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-201 | OpenTelemetry SDK integration | Industry-standard tracing | OTLP export functional with `.[monitoring]` extra |
| FR-202 | OTLP export to collectors | Production observability stacks | Configurable endpoint, working export |
| FR-203 | `/memory:traces` command | Trace inspection | Shows recent traces for operations |
| FR-204 | `/memory:health --timing` | Health check with timing | Reports system health with latency info |
| FR-205 | Docker Compose local observability stack | Developer experience, easy setup | Single `docker compose up` provides Grafana + collector |
| FR-206 | Session identification in telemetry | Multi-user distinguishability | Each session has unique ID visible in all telemetry |
| FR-207 | Provider configuration documentation | Support multiple backends | Docs for Datadog, Jaeger, Honeycomb, Grafana Cloud, etc. |
| FR-208 | Pre-built Grafana dashboards | Immediate value from stack | JSON dashboard configs for memory operations |

## Non-Functional Requirements

### Performance

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| Decorator overhead | <1ms per operation | Must not noticeably impact operation timing |
| Metrics collection | <100μs per metric emit | High-frequency emission (every operation) |
| Memory footprint | <10MB for 1 hour of metrics | In-memory storage without external deps |
| Hook timing overhead | <5% of timeout budget | UserPromptSubmit has 2s timeout |

### Compatibility

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| Python version | 3.11+ | Match project requirements |
| Platform support | macOS, Linux, Windows | Cross-platform plugin |
| Existing behavior | No breaking changes | Backward compatibility |
| Log format transition | Opt-out to text format | Gradual migration path |

### Reliability

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| Core operation success | 100% even if metrics fail | Observability never blocks main functionality |
| Graceful degradation | Silent fallback if monitoring unavailable | Optional extras pattern |
| Thread safety | Full thread-safe metrics | Concurrent hook invocations |

### Multi-Session Distinguishability

When multiple users or sessions send telemetry to the same collector, each session MUST be distinguishable:

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| Session ID generation | Unique per Claude Code session | Enables filtering by user/session in dashboards |
| Resource attributes | session_id, user_home, repo_path, hostname | Standard OTel resource attributes for filtering |
| Metric labels | session_id on all metrics | Prometheus queries can filter by session |
| Log context | session_id in all structured logs | Log aggregation can filter by session |
| Trace attributes | session_id as span attribute | Trace filtering in Jaeger/Tempo |

**Session ID Strategy**:
- Generated at SessionStart hook invocation
- Persisted in environment for hook process lifetime
- Format: `{hostname}:{repo_hash}:{timestamp}` for human readability
- Also includes UUID suffix for uniqueness guarantee

## Technical Constraints

### Dependency Strategy

**Core package (required runtime dependencies):**
- Python stdlib only for observability basics
- No new required dependencies

**Optional extras (`pip install .[monitoring]`):**
- `opentelemetry-api ~= 1.32.0`
- `opentelemetry-sdk ~= 1.32.0`
- `opentelemetry-exporter-otlp-proto-grpc ~= 1.32.0`
- `prometheus-client >= 0.17.0`

### Local Observability Stack (Docker Compose)

A Docker Compose stack for local development and testing:

| Service | Image | Purpose | Port |
|---------|-------|---------|------|
| OTEL Collector | `otel/opentelemetry-collector-contrib` | Receives OTLP, exports to backends | 4317 (gRPC), 4318 (HTTP) |
| Prometheus | `prom/prometheus` | Metrics storage and querying | 9090 |
| Grafana | `grafana/grafana` | Visualization and dashboards | 3000 |
| Tempo | `grafana/tempo` | Distributed trace storage | 3200 |
| Loki | `grafana/loki` | Log aggregation | 3100 |

**Stack Requirements:**
- Single `docker compose up` to start all services
- Pre-configured datasources in Grafana
- Pre-built dashboards for memory plugin metrics
- Volume persistence for data between restarts
- Health checks for all services

**Default Endpoints (for plugin configuration):**
```bash
MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4317
MEMORY_PLUGIN_PROMETHEUS_PUSHGATEWAY=http://localhost:9091
```

### Integration Requirements

| Integration Point | Method | Notes |
|-------------------|--------|-------|
| Existing logging | Wrap/enhance, don't replace | Preserve HOOK_DEBUG behavior initially |
| Hook timeout system | Add timing before/after | Don't change timeout mechanism |
| Service singletons | Inject metrics collector | Use existing factory pattern |

## Dependencies

### Internal Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| CaptureService | Instrumentation target | Add timing to capture() |
| RecallService | Instrumentation target | Add timing to search() |
| EmbeddingService | Instrumentation target | Add timing to embed() |
| IndexService | Instrumentation target | Add timing to insert/search |
| GitOps | Instrumentation target | Add timing to subprocess calls |
| Hook handlers (5) | Instrumentation target | Add timing wrapper |

### External Dependencies

| Dependency | Version | Purpose | Required? |
|------------|---------|---------|-----------|
| opentelemetry-api | ~= 1.32.0 | Tracing API | Optional |
| opentelemetry-sdk | ~= 1.32.0 | Tracing SDK | Optional |
| opentelemetry-exporter-otlp | ~= 1.32.0 | OTLP export | Optional |
| prometheus-client | >= 0.17.0 | Prometheus format | Optional |

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Performance overhead from instrumentation | Medium | Medium | Measure overhead in benchmarks, use efficient timing |
| Breaking existing logging behavior | Low | High | Opt-out mechanism for text format, gradual rollout |
| Optional dependency version conflicts | Medium | Low | Follow OTel versioning guidelines, wide version ranges |
| Increased code complexity | Medium | Medium | Clean separation in observability.py module |
| Metrics memory growth unbounded | Low | Medium | Implement rolling windows, configurable retention |

## Open Questions

- [x] Which debug level naming: standard (quiet/info/debug/trace) vs semantic vs numeric?
  - **Resolved**: Standard naming (quiet/info/debug/trace)
- [x] Which export formats for /memory:metrics?
  - **Resolved**: All four (JSON, Prometheus, OTLP, plain text)
- [x] How to handle backward compatibility with HOOK_DEBUG?
  - **Resolved**: Unified debug levels replace HOOK_DEBUG
- [x] Tiered implementation priority?
  - **Resolved**: All three tiers, with Tier 3 as optional extras

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| Span | A unit of work within a trace, with start/end time and tags |
| Trace | A collection of spans representing a complete request flow |
| Histogram | Metric type for measuring distributions (e.g., latency) |
| Counter | Metric type for monotonically increasing values |
| Gauge | Metric type for point-in-time values that can increase or decrease |
| Correlation ID | Unique identifier propagated across service calls for tracing |
| OTLP | OpenTelemetry Protocol - standard for exporting telemetry data |

### References

- [GitHub Issue #10](https://github.com/zircote/git-notes-memory/issues/10) - Original requirements
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/) - Tracing framework
- [Prometheus Client Python](https://prometheus.github.io/client_python/) - Metrics library
- [structlog](https://www.structlog.org/en/stable/) - Structured logging library

### Provider Documentation Requirements

Documentation must cover configuration for these observability providers:

| Provider | Type | Configuration Method | Priority |
|----------|------|---------------------|----------|
| Local Docker Stack | All-in-one | Docker Compose file | P0 |
| Grafana Cloud | Metrics, Traces, Logs | OTLP endpoint + API key | P1 |
| Datadog | APM, Metrics, Logs | Datadog Agent + API key | P1 |
| Jaeger | Traces | OTLP or Jaeger endpoint | P1 |
| Honeycomb | Traces, Events | OTLP endpoint + API key | P2 |
| New Relic | APM | OTLP endpoint + license key | P2 |
| AWS X-Ray | Traces | ADOT collector | P2 |
| Azure Monitor | All | Azure exporter | P2 |

**Documentation Structure:**
```
docs/observability/
├── README.md           # Overview and quick start
├── docker-compose.md   # Local stack setup
├── providers/
│   ├── grafana-cloud.md
│   ├── datadog.md
│   ├── jaeger.md
│   ├── honeycomb.md
│   ├── newrelic.md
│   ├── aws-xray.md
│   └── azure-monitor.md
├── dashboards/
│   ├── grafana/
│   │   └── memory-operations.json
│   └── datadog/
│       └── memory-operations.json
└── troubleshooting.md
```

### Critical Instrumentation Points (from codebase analysis)

| Location | What to Measure | Priority |
|----------|-----------------|----------|
| `capture.py::CaptureService.capture()` | Total capture time, lock, embed, insert | P0 |
| `recall.py::RecallService.search()` | Query embedding, vector search, result count | P0 |
| `embedding.py::EmbeddingService.embed()` | Model load (one-time), inference per call | P0 |
| `index.py::IndexService` | Insert/update/delete, KNN search, FTS5 | P0 |
| `git_ops.py::GitOps` | Subprocess call durations, failures | P0 |
| Hook handlers (5 total) | Total execution, timeout %, input/output sizes | P0 |
| `capture.py::_acquire_lock()` | Lock acquisition time, contention | P1 |
| `note_parser.py` | YAML parsing time | P1 |
| `sync.py::SyncService.reindex()` | Full reindex duration | P1 |

### Silent Failure Points (to address)

| File | Line | Context | Action |
|------|------|---------|--------|
| capture.py | 122-123 | Lock release OSError | Add warning log |
| capture.py | 489-490 | Note parsing exception | Add warning log |
| git_ops.py | 1084 | Push failure | Add warning log |
| sync.py | 444-445 | Hash verification exception | Add warning log |
| index.py | 300-301 | Index creation OperationalError | Add warning log |
