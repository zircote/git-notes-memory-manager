---
document_type: implementation_plan
project_id: SPEC-2025-12-25-001
version: 1.1.0
last_updated: 2025-12-26T00:15:00Z
status: draft
estimated_effort: 7-10 days
phases: 6
tasks: 29
---

# Observability Instrumentation - Implementation Plan

## Overview

This implementation plan covers all three tiers of observability instrumentation for git-notes-memory. The work is organized into 6 phases that build incrementally from core infrastructure to optional integrations and local observability stack.

## Phase Summary

| Phase | Name | Key Deliverables | Tier |
|-------|------|------------------|------|
| 1 | Core Infrastructure | observability module, config, metrics collector | Tier 1 |
| 2 | Instrumentation | decorators applied to critical paths, hook timing | Tier 1 |
| 3 | Structured Logging | StructuredLogger, JSON format, correlation IDs | Tier 2 |
| 4 | CLI & Export | /memory:metrics command, Prometheus format | Tier 2 |
| 5 | OpenTelemetry | OTLP export, optional extras | Tier 3 |
| 6 | Local Stack & Docs | Docker Compose, provider documentation | Tier 3 |

---

## Phase 1: Core Infrastructure

**Goal**: Establish the observability module foundation with configuration and metrics collection

**Prerequisites**: None

### Tasks

#### Task 1.1: Create observability module structure

- **Description**: Create the `src/git_notes_memory/observability/` directory structure with `__init__.py` exposing public API
- **Files**:
  - `src/git_notes_memory/observability/__init__.py`
  - `src/git_notes_memory/observability/config.py`
- **Acceptance Criteria**:
  - [ ] Module importable as `from git_notes_memory.observability import ...`
  - [ ] Lazy imports to avoid loading optional dependencies at import time
  - [ ] No new runtime dependencies added

#### Task 1.2: Implement ObservabilityConfig

- **Description**: Create configuration dataclass that loads from environment variables
- **File**: `src/git_notes_memory/observability/config.py`
- **Acceptance Criteria**:
  - [ ] Frozen dataclass with all config fields
  - [ ] `get_config()` factory with environment variable loading
  - [ ] Default values match specification (enabled=True, log_format=json, etc.)
  - [ ] Unified debug levels: quiet, info, debug, trace
  - [ ] Tests for all environment variable combinations
- **Notes**: Replaces fragmented HOOK_DEBUG with unified system

#### Task 1.3: Implement MetricsCollector

- **Description**: Thread-safe in-memory metrics storage with counter, histogram, gauge support
- **File**: `src/git_notes_memory/observability/metrics.py`
- **Acceptance Criteria**:
  - [ ] `increment()`, `observe()`, `set_gauge()` methods
  - [ ] Thread-safe via threading.Lock
  - [ ] Label support with frozenset storage
  - [ ] Rolling window for histogram samples (configurable size)
  - [ ] `export_json()`, `export_text()` methods
  - [ ] `reset()` for testing
  - [ ] Tests for concurrent access
- **Dependencies**: None (stdlib only)

#### Task 1.4: Implement SpanContext and trace_operation

- **Description**: Context propagation for distributed tracing using contextvars
- **File**: `src/git_notes_memory/observability/tracing.py`
- **Acceptance Criteria**:
  - [ ] `Span` dataclass with trace_id, span_id, operation, timing, tags
  - [ ] `trace_operation()` context manager
  - [ ] `get_current_span()`, `get_current_trace_id()` accessors
  - [ ] Parent span tracking for nested operations
  - [ ] UUID generation for trace/span IDs
  - [ ] Tests for nested span scenarios
- **Dependencies**: None (stdlib contextvars)

#### Task 1.5: Implement SessionIdentifier

- **Description**: Create session identification component for multi-tenant distinguishability
- **File**: `src/git_notes_memory/observability/session.py`
- **Acceptance Criteria**:
  - [ ] `SessionInfo` frozen dataclass with hostname, repo_hash, user_hash, timestamp, uuid
  - [ ] `generate_session_id()` factory returning unique identifiers
  - [ ] Format: `{hostname}:{repo_hash}:{timestamp}:{uuid_suffix}` for human readability
  - [ ] Privacy-preserving hashes (SHA256 of repo path, username)
  - [ ] `get_session_info()` singleton accessor
  - [ ] Integration with SessionStart hook for generation
  - [ ] Tests verify uniqueness and format
- **Dependencies**: None (stdlib only)

#### Task 1.6: Implement measure_duration decorator

- **Description**: Timing decorator that emits histogram metrics
- **File**: `src/git_notes_memory/observability/decorators.py`
- **Acceptance Criteria**:
  - [ ] Decorator works on sync functions
  - [ ] Emits `{operation}_duration_ms` histogram
  - [ ] Adds status label (success/error)
  - [ ] Adds session_id label from current session
  - [ ] Propagates exceptions while recording timing
  - [ ] Optional `record_args` for dynamic labels
  - [ ] Tests verify timing accuracy within 10%
- **Dependencies**: MetricsCollector singleton, SessionIdentifier

### Phase 1 Deliverables

- [ ] `observability/` module with 6 files
- [ ] Configuration loading from environment
- [ ] In-memory metrics collection
- [ ] Span context propagation
- [ ] Timing decorator ready for use
- [ ] Session identification for multi-tenant telemetry

### Phase 1 Exit Criteria

- [ ] All unit tests passing
- [ ] No new runtime dependencies
- [ ] Module importable without side effects

---

## Phase 2: Instrumentation

**Goal**: Apply instrumentation to all critical paths identified in codebase analysis

**Prerequisites**: Phase 1 complete

### Tasks

#### Task 2.1: Instrument CaptureService

- **Description**: Add timing to capture operations
- **File**: `src/git_notes_memory/capture.py`
- **Acceptance Criteria**:
  - [ ] `@measure_duration("memory_capture")` on `capture()` method
  - [ ] `trace_operation("capture")` context with namespace tag
  - [ ] Nested spans for lock acquisition, git append, embed, index insert
  - [ ] Counter: `memories_captured_total` with namespace label
  - [ ] Tests verify metrics emitted
- **Changes**:
  - Add decorator to `capture()` method (~line 350)
  - Wrap lock acquisition in span (~line 93)
  - Wrap git append in span (~line 496)
  - Wrap embedding in span (~line 528)
  - Wrap index insert in span (~line 537)

#### Task 2.2: Instrument RecallService

- **Description**: Add timing to search operations
- **File**: `src/git_notes_memory/recall.py`
- **Acceptance Criteria**:
  - [ ] `@measure_duration("memory_search")` on `search()` method
  - [ ] `trace_operation("search")` with search type tag
  - [ ] Nested spans for query embedding, vector search
  - [ ] Counter: `searches_performed_total` with type label
  - [ ] Histogram: result count distribution
  - [ ] Tests verify metrics emitted
- **Changes**:
  - Add decorator to `search()` method (~line 136)
  - Wrap query embedding in span (~line 173)
  - Wrap vector search in span (~line 179)

#### Task 2.3: Instrument EmbeddingService

- **Description**: Add timing to embedding operations, especially model load
- **File**: `src/git_notes_memory/embedding.py`
- **Acceptance Criteria**:
  - [ ] `@measure_duration("embedding_generation")` on `embed()` method
  - [ ] One-time gauge: `model_load_time_ms` recorded on first load
  - [ ] Counter: `embeddings_generated_total`
  - [ ] Model dimension logged as gauge
  - [ ] Tests verify model load timing captured
- **Changes**:
  - Add timing around `load()` method (~line 109)
  - Add decorator to `embed()` method (~line 180)

#### Task 2.4: Instrument IndexService

- **Description**: Add timing to database operations
- **File**: `src/git_notes_memory/index.py`
- **Acceptance Criteria**:
  - [ ] `@measure_duration("index_insert")` on `insert()` method
  - [ ] `@measure_duration("index_search")` on `search_vector()` method
  - [ ] Gauge: `index_memory_count` updated on insert/delete
  - [ ] Counter: `index_operations_total` with operation type label
  - [ ] Tests verify metrics emitted
- **Changes**:
  - Add decorator to `insert()` (~line 365)
  - Add decorator to `search_vector()` (~line 992)
  - Update memory count gauge after modifications

#### Task 2.5: Instrument GitOps

- **Description**: Add timing to subprocess calls
- **File**: `src/git_notes_memory/git_ops.py`
- **Acceptance Criteria**:
  - [ ] `trace_operation("git_operation")` around subprocess calls
  - [ ] Histogram: `git_operation_duration_ms` with operation label
  - [ ] Counter: `git_errors_total` with operation label
  - [ ] Fix: Add timeout to `show_notes_batch()` (~line 481)
  - [ ] Tests verify timing captured
- **Changes**:
  - Wrap `_run_command()` or individual operations
  - Add timeout to cat-file batch command

#### Task 2.6: Instrument Hook Handlers

- **Description**: Add execution timing and timeout tracking to all 5 hooks
- **Files**:
  - `src/git_notes_memory/hooks/session_start_handler.py`
  - `src/git_notes_memory/hooks/user_prompt_handler.py`
  - `src/git_notes_memory/hooks/post_tool_use_handler.py`
  - `src/git_notes_memory/hooks/pre_compact_handler.py`
  - `src/git_notes_memory/hooks/stop_handler.py`
- **Acceptance Criteria**:
  - [ ] Each hook emits `hook_execution_duration_ms` histogram
  - [ ] Gauge: `hook_timeout_pct_used` (duration / timeout * 100)
  - [ ] Counter: `hook_invocations_total` with hook name label
  - [ ] Counter: `hook_errors_total` with hook name and category labels
  - [ ] Fix: Add timeout protection to stop_handler.py operations
  - [ ] Tests verify metrics emitted
- **Changes**:
  - Add timing wrapper around `main()` in each handler
  - Calculate timeout percentage used
  - Add timeout to stop_handler remote push and index sync

#### Task 2.7: Fix Silent Failure Points

- **Description**: Add logging to 5 identified silent exception handlers
- **Files**: Various
- **Acceptance Criteria**:
  - [ ] `capture.py:122-123` - Lock release OSError logged at warning
  - [ ] `capture.py:489-490` - Note parsing exception logged at warning
  - [ ] `git_ops.py:1084` - Push failure logged at warning
  - [ ] `sync.py:444-445` - Hash verification exception logged at warning
  - [ ] `index.py:300-301` - Index creation error logged at warning
  - [ ] Counter: `silent_failures_total` with location label
  - [ ] Tests verify logging occurs

### Phase 2 Deliverables

- [ ] All 6 critical services instrumented
- [ ] All 5 hooks have timing
- [ ] Silent failure points addressed
- [ ] ~15 new metrics defined

### Phase 2 Exit Criteria

- [ ] All unit tests passing
- [ ] No performance regression (decorator overhead <1ms)
- [ ] Hook timeout compliance verified

---

## Phase 3: Structured Logging

**Goal**: Implement structured JSON logging with trace context injection

**Prerequisites**: Phase 2 complete

### Tasks

#### Task 3.1: Implement StructuredLogger

- **Description**: JSON-structured logger with trace context injection
- **File**: `src/git_notes_memory/observability/logging.py`
- **Acceptance Criteria**:
  - [ ] StructuredLogger class with debug/info/warning/error/exception methods
  - [ ] Automatic trace_id/span_id injection from current context
  - [ ] JSON format with consistent schema (timestamp, level, message, service, etc.)
  - [ ] Text format fallback when configured
  - [ ] `get_logger(name)` factory function
  - [ ] Tests verify JSON output format
- **Schema**: See ARCHITECTURE.md for log entry format

#### Task 3.2: Implement LogFormatter

- **Description**: Python logging Formatter for structured output
- **File**: `src/git_notes_memory/observability/logging.py`
- **Acceptance Criteria**:
  - [ ] Subclass of logging.Formatter
  - [ ] Injects trace context automatically
  - [ ] Configurable field inclusion
  - [ ] Backward compatible with existing log handlers
  - [ ] Tests verify formatter integration

#### Task 3.3: Migrate hook logging to structured format

- **Description**: Update hook handlers to use StructuredLogger
- **Files**: All hook handler files
- **Acceptance Criteria**:
  - [ ] Each hook uses `get_logger(__name__)`
  - [ ] Context fields added to log calls (namespace, memory_id, hook_name)
  - [ ] Existing log messages preserved (content unchanged)
  - [ ] Tests verify structured output
- **Notes**: Gradual migration - new logs structured, existing can remain

#### Task 3.4: Update hook_utils for structured logging

- **Description**: Update shared hook utilities to use structured logging
- **File**: `src/git_notes_memory/hooks/hook_utils.py`
- **Acceptance Criteria**:
  - [ ] Replace `logger.debug()` calls with structured equivalents
  - [ ] Add context fields to input/output logging
  - [ ] Maintain backward compatibility with file logs
  - [ ] Tests verify log format

### Phase 3 Deliverables

- [ ] StructuredLogger implementation
- [ ] LogFormatter for Python logging integration
- [ ] Hook handlers using structured logging
- [ ] Documentation for log format

### Phase 3 Exit Criteria

- [ ] JSON logs parse correctly
- [ ] Trace context propagates through logs
- [ ] Text format still available via config

---

## Phase 4: CLI & Export

**Goal**: Implement CLI commands and Prometheus export format

**Prerequisites**: Phase 3 complete

### Tasks

#### Task 4.1: Implement /memory:metrics command

- **Description**: CLI command to view metrics
- **File**: `hooks/commands/metrics.md` (command definition)
- **Acceptance Criteria**:
  - [ ] Plain text output by default
  - [ ] `--format=json` for JSON output
  - [ ] `--format=prometheus` for Prometheus format
  - [ ] `--filter` for metric name filtering
  - [ ] Tests verify all output formats
- **Implementation**: Use command handler pattern from existing commands

#### Task 4.2: Implement Prometheus text format export

- **Description**: Export metrics in Prometheus exposition format
- **File**: `src/git_notes_memory/observability/exporters/prometheus.py`
- **Acceptance Criteria**:
  - [ ] Counter format: `metric_name{labels} value`
  - [ ] Histogram format with buckets: `metric_name_bucket{le="X"} count`
  - [ ] Gauge format: `metric_name{labels} value`
  - [ ] TYPE and HELP comments
  - [ ] Tests verify format compliance
- **Dependencies**: None (stdlib string formatting)

#### Task 4.3: Implement /memory:traces command

- **Description**: CLI command to view recent traces
- **File**: `hooks/commands/traces.md` (command definition)
- **Acceptance Criteria**:
  - [ ] Lists recent traces with operation, duration, status
  - [ ] `--operation` filter
  - [ ] `--limit` option (default 10)
  - [ ] `--status` filter (ok/error)
  - [ ] Tests verify output format

#### Task 4.4: Implement /memory:health --timing

- **Description**: Add timing information to health check
- **File**: Update existing health command or create new
- **Acceptance Criteria**:
  - [ ] Shows component health status
  - [ ] `--timing` flag adds latency percentiles
  - [ ] Shows hook timeout rate
  - [ ] Tests verify output

#### Task 4.5: Update pyproject.toml for metrics command

- **Description**: Register new CLI commands
- **File**: `pyproject.toml`, `plugin.json`
- **Acceptance Criteria**:
  - [ ] Commands registered in plugin.json
  - [ ] Help text for all new commands
  - [ ] No new required dependencies

### Phase 4 Deliverables

- [ ] `/memory:metrics` command with 3 output formats
- [ ] `/memory:traces` command
- [ ] `/memory:health --timing` enhancement
- [ ] Prometheus export format

### Phase 4 Exit Criteria

- [ ] All commands functional
- [ ] Output formats match specification
- [ ] No new runtime dependencies

---

## Phase 5: OpenTelemetry Integration

**Goal**: Implement optional OpenTelemetry integration with OTLP export

**Prerequisites**: Phase 4 complete

### Tasks

#### Task 5.1: Add optional dependencies to pyproject.toml

- **Description**: Configure `[monitoring]` extras
- **File**: `pyproject.toml`
- **Acceptance Criteria**:
  - [ ] `[project.optional-dependencies]` section with `monitoring` key
  - [ ] OpenTelemetry packages: api ~= 1.32.0, sdk ~= 1.32.0, exporter-otlp ~= 1.32.0
  - [ ] prometheus-client >= 0.17.0
  - [ ] `pip install .[monitoring]` works
  - [ ] Core package unchanged without extras

#### Task 5.2: Implement OTLP exporter wrapper

- **Description**: Wrapper for OpenTelemetry OTLP exporter
- **File**: `src/git_notes_memory/observability/exporters/otlp.py`
- **Acceptance Criteria**:
  - [ ] Graceful import failure when deps not installed
  - [ ] Convert internal Span to OTLP Span
  - [ ] Configurable endpoint via environment variable
  - [ ] Batch export with retry
  - [ ] Shutdown cleanup
  - [ ] Tests with mocked exporter

#### Task 5.3: Implement OpenTelemetry TracerProvider integration

- **Description**: Optional OTel SDK initialization
- **File**: `src/git_notes_memory/observability/otel.py`
- **Acceptance Criteria**:
  - [ ] Initialize TracerProvider when deps available
  - [ ] Configure BatchSpanProcessor
  - [ ] Service name: "git-notes-memory"
  - [ ] Resource attributes (version, etc.)
  - [ ] Graceful fallback when deps unavailable
  - [ ] Tests verify initialization

#### Task 5.4: Implement prometheus-client integration

- **Description**: Optional Prometheus client library integration
- **File**: `src/git_notes_memory/observability/exporters/prometheus.py`
- **Acceptance Criteria**:
  - [ ] Optional use of prometheus-client when available
  - [ ] Fallback to text format when not installed
  - [ ] HTTP server for scrape endpoint (configurable port)
  - [ ] Metrics registration with proper types
  - [ ] Tests with mocked server

#### Task 5.5: Update /memory:metrics for OTLP format

- **Description**: Add OTLP format option to metrics command
- **File**: Update metrics command
- **Acceptance Criteria**:
  - [ ] `--format=otlp` triggers OTLP export
  - [ ] Error message if deps not installed
  - [ ] Documentation for setup

#### Task 5.6: Documentation for observability

- **Description**: Document configuration and usage
- **Files**:
  - Update README.md
  - Update CLAUDE.md
  - Create `docs/observability.md` if needed
- **Acceptance Criteria**:
  - [ ] Environment variable reference
  - [ ] Installation instructions for extras
  - [ ] Example configurations for Prometheus, Jaeger, Datadog
  - [ ] Troubleshooting guide

### Phase 5 Deliverables

- [ ] `[monitoring]` optional extras
- [ ] OTLP exporter
- [ ] prometheus-client integration
- [ ] Documentation

### Phase 5 Exit Criteria

- [ ] Core package has no new runtime deps
- [ ] Optional features work when deps installed
- [ ] Graceful degradation when deps missing
- [ ] Documentation complete

---

## Phase 6: Local Observability Stack & Documentation

**Goal**: Provide turnkey local observability environment and multi-provider documentation

**Prerequisites**: Phase 5 complete

### Tasks

#### Task 6.1: Create Docker Compose observability stack

- **Description**: Docker Compose configuration for local OTEL collector, Prometheus, Grafana, Tempo, Loki
- **Files**:
  - `docker/docker-compose.observability.yaml`
  - `docker/otel-collector-config.yaml`
  - `docker/prometheus.yml`
  - `docker/grafana/provisioning/datasources/datasources.yaml`
  - `docker/grafana/provisioning/dashboards/dashboards.yaml`
- **Acceptance Criteria**:
  - [ ] Single `docker compose up` starts all services
  - [ ] OTEL Collector receives OTLP on 4317 (gRPC) and 4318 (HTTP)
  - [ ] Prometheus scrapes metrics on 9090
  - [ ] Grafana accessible on 3000 with pre-configured datasources
  - [ ] Tempo for traces on 3200
  - [ ] Loki for logs on 3100
  - [ ] Health checks for all services
  - [ ] Volume persistence between restarts
  - [ ] Tests verify services start correctly

#### Task 6.2: Create pre-built Grafana dashboards

- **Description**: JSON dashboard definitions for memory plugin operations
- **Files**:
  - `docker/grafana/provisioning/dashboards/memory-operations.json`
  - `docker/grafana/provisioning/dashboards/hook-performance.json`
- **Acceptance Criteria**:
  - [ ] Memory Operations dashboard with capture/recall/embed/index panels
  - [ ] Hook Performance dashboard with timeout % gauges per hook type
  - [ ] Session filtering dropdown
  - [ ] Time range selector
  - [ ] Auto-refresh enabled
  - [ ] Validated against Grafana dashboard schema

#### Task 6.3: Create provider configuration documentation

- **Description**: Documentation for configuring alternative observability providers
- **Files**:
  - `docs/observability/README.md`
  - `docs/observability/docker-compose.md`
  - `docs/observability/providers/grafana-cloud.md`
  - `docs/observability/providers/datadog.md`
  - `docs/observability/providers/jaeger.md`
  - `docs/observability/providers/honeycomb.md`
  - `docs/observability/providers/newrelic.md`
  - `docs/observability/providers/aws-xray.md`
  - `docs/observability/providers/azure-monitor.md`
  - `docs/observability/troubleshooting.md`
- **Acceptance Criteria**:
  - [ ] Each provider doc includes: prerequisites, environment variables, verification steps
  - [ ] Code examples for each provider
  - [ ] Troubleshooting common issues
  - [ ] Links to provider documentation
  - [ ] Consistent format across all provider docs

#### Task 6.4: Update project documentation

- **Description**: Update README.md and CLAUDE.md with observability section
- **Files**:
  - `README.md`
  - `CLAUDE.md`
- **Acceptance Criteria**:
  - [ ] Observability section in README with quick start
  - [ ] Environment variable reference table
  - [ ] Link to detailed docs
  - [ ] CLAUDE.md updated with new commands and environment variables

### Phase 6 Deliverables

- [ ] Docker Compose stack for local observability
- [ ] Pre-built Grafana dashboards
- [ ] Provider documentation for 7 observability platforms
- [ ] Updated project documentation

### Phase 6 Exit Criteria

- [ ] Docker stack starts cleanly
- [ ] Dashboards load without errors
- [ ] All provider docs reviewed for accuracy
- [ ] README observability section complete

---

## Dependency Graph

```
Phase 1: Core Infrastructure
├── Task 1.1: Module structure
├── Task 1.2: ObservabilityConfig
├── Task 1.3: MetricsCollector ────────────────────┐
├── Task 1.4: SpanContext ─────────────────────────┤
├── Task 1.5: SessionIdentifier ───────────────────┤
└── Task 1.6: measure_duration ────────────────────┤
                                                   │
Phase 2: Instrumentation                           │
├── Task 2.1: CaptureService ◄─────────────────────┤
├── Task 2.2: RecallService ◄──────────────────────┤
├── Task 2.3: EmbeddingService ◄───────────────────┤
├── Task 2.4: IndexService ◄───────────────────────┤
├── Task 2.5: GitOps ◄─────────────────────────────┤
├── Task 2.6: Hook Handlers ◄──────────────────────┤
└── Task 2.7: Silent Failures ◄────────────────────┘
                     │
Phase 3: Structured Logging
├── Task 3.1: StructuredLogger ◄───────────────────┐
├── Task 3.2: LogFormatter ◄───────────────────────┤
├── Task 3.3: Hook logging migration ◄─────────────┤
└── Task 3.4: hook_utils update ◄──────────────────┘
                     │
Phase 4: CLI & Export
├── Task 4.1: /memory:metrics ◄────────────────────┐
├── Task 4.2: Prometheus format ◄──────────────────┤
├── Task 4.3: /memory:traces ◄─────────────────────┤
├── Task 4.4: /memory:health --timing ◄────────────┤
└── Task 4.5: pyproject.toml update ◄──────────────┘
                     │
Phase 5: OpenTelemetry
├── Task 5.1: Optional deps ◄──────────────────────┐
├── Task 5.2: OTLP exporter ◄──────────────────────┤
├── Task 5.3: TracerProvider ◄─────────────────────┤
├── Task 5.4: prometheus-client ◄──────────────────┤
├── Task 5.5: OTLP format ◄────────────────────────┤
└── Task 5.6: Documentation ◄──────────────────────┘
                     │
Phase 6: Local Stack & Docs
├── Task 6.1: Docker Compose stack ◄───────────────┐
├── Task 6.2: Grafana dashboards ◄─────────────────┤
├── Task 6.3: Provider documentation ◄─────────────┤
└── Task 6.4: Project documentation ◄──────────────┘
```

## Risk Mitigation Tasks

| Risk | Mitigation Task | Phase |
|------|-----------------|-------|
| Performance overhead | Task 1.5: Benchmark decorator overhead | Phase 1 |
| Breaking existing logging | Task 3.2: Text format fallback | Phase 3 |
| Optional dependency conflicts | Task 5.1: Wide version ranges | Phase 5 |
| Memory growth | Task 1.3: Rolling window eviction | Phase 1 |

## Testing Checklist

- [ ] Unit tests for MetricsCollector thread safety
- [ ] Unit tests for SpanContext nested spans
- [ ] Unit tests for measure_duration timing accuracy
- [ ] Integration tests for trace propagation
- [ ] Integration tests for Prometheus format compliance
- [ ] Performance tests for decorator overhead (<1ms)
- [ ] Performance tests for memory growth (<10MB/hour)

## Documentation Tasks

- [ ] Update CLAUDE.md with new environment variables
- [ ] Update README.md with observability section
- [ ] Create docs/observability.md with full reference
- [ ] Add examples for Prometheus/Jaeger/Datadog integration

## Launch Checklist

- [ ] All tests passing
- [ ] Documentation complete
- [ ] No new required dependencies
- [ ] Performance benchmarks pass
- [ ] CHANGELOG updated
- [ ] Version bumped appropriately

## Post-Launch

- [ ] Monitor for issues (24-48 hours)
- [ ] Gather feedback on log format
- [ ] Consider auto-instrumentation in future
- [ ] Archive planning documents
