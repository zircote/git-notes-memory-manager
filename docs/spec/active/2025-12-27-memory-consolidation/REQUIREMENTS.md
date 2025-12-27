# Memory Consolidation: Requirements

**Spec ID:** SPEC-2025-12-27-001
**Status:** Draft
**GitHub Issue:** TBD
**Related Research:** `docs/research/CognitiveSubstrate/memory-consolidation-*.md`

## Problem Statement

The `git_notes_memory.subconsciousness` module has configuration toggles for consolidation, forgetting, surfacing, and linking - but these features are not implemented. Without memory consolidation:

1. **Unbounded memory growth** - Early memories pollute search results as the index grows
2. **No temporal decay** - A 6-month-old obsolete decision carries the same weight as yesterday's
3. **No abstraction** - 50 semantically related memories consume 50x the retrieval cost instead of being consolidated
4. **Contradictions unresolved** - Superseded information is returned alongside current, causing confusion

## Solution Overview

Extend the existing subconsciousness module with a memory consolidation pipeline that runs asynchronously to:

| Capability | Description |
|------------|-------------|
| **Decay** | Compute retention scores, demote stale memories to cold/archived tiers |
| **Cluster** | Group semantically similar memories regardless of time |
| **Summarize** | Generate consolidated summaries via LLM |
| **Supersede** | Detect when newer memories invalidate older via LLM judgment |
| **Link** | Create edges between related memories for graph traversal |

## Stakeholders

| Role | Needs |
|------|-------|
| Plugin Users | Better recall quality, reduced noise in search results |
| Claude Code Sessions | Relevant consolidated context at session start |
| Memory Authors | Confidence that decisions/learnings are preserved and abstracted |
| System Operators | Observable consolidation runs, configurable behavior |

## Functional Requirements

### FR-1: Memory Tier System

**FR-1.1** Memories SHALL be assignable to one of four tiers based on retention score:
- `HOT` (≥0.6): Active memories, included in reflexive/standard retrieval
- `WARM` (≥0.3): Summaries and moderately active memories, included in standard retrieval
- `COLD` (<0.3, ≥archive_threshold): Historical, excluded from default search
- `ARCHIVED` (<archive_threshold): Superseded or very old, audit access only

**FR-1.2** Tier thresholds SHALL be configurable via environment variables.

**FR-1.3** Tier transitions SHALL be logged for auditability.

### FR-2: Retention Score Calculation

**FR-2.1** The system SHALL compute a retention score (0.0-1.0) for each memory based on:
- **Recency** (40% weight): Exponential decay with configurable half-life (default: 30 days)
- **Activation** (20% weight): Log-scale based on retrieval count (spaced repetition)
- **Importance** (40% weight): Namespace-based weighting (decisions > learnings > progress)

**FR-2.2** Superseded memories SHALL receive a 0.2x penalty on their retention score.

**FR-2.3** Retention parameters SHALL be tunable (half-life, weights, thresholds).

### FR-3: Semantic Clustering

**FR-3.1** The system SHALL cluster memories by semantic similarity using embeddings, **ignoring temporal proximity**.

**FR-3.2** Clustering SHALL use AgglomerativeClustering with configurable:
- Similarity threshold (default: 0.85)
- Min cluster size (default: 3)
- Max cluster size (default: 20)

**FR-3.3** Memories from different sessions/dates SHALL cluster together if semantically related.

### FR-4: LLM-Powered Summarization

**FR-4.1** Clusters meeting size requirements SHALL be summarized via LLM.

**FR-4.2** Summaries SHALL preserve:
- Key facts still valid
- Decisions with rationale and outcomes
- Superseded facts with what replaced them
- Source memory references (provenance)

**FR-4.3** Summaries SHALL have confidence scores matching the `CaptureConfidence` pattern.

**FR-4.4** Summary generation SHALL use configurable LLM providers with fallback chain:
1. OpenAI (GPT-5-nano/mini when available, gpt-4o-mini fallback)
2. LM Studio (OpenAI-compatible local endpoint)
3. Ollama (local)

### FR-5: Supersession Detection

**FR-5.1** The system SHALL detect when newer memories supersede older ones via LLM judgment.

**FR-5.2** Supersession SHALL be detected for:
- Direct contradictions (decision changed)
- Replacements (updated version of same info)
- Obsolescence (topic no longer relevant)

**FR-5.3** Supersession edges SHALL include:
- Confidence level (high/medium/low)
- LLM-provided explanation
- Run ID for traceability

**FR-5.4** Conservative detection: Only mark superseded with clear evidence.

### FR-6: Memory Edges (Graph Structure)

**FR-6.1** The system SHALL create relationship edges between memories:
- `SUPERSEDES`: Newer invalidates older
- `CONSOLIDATES`: Summary abstracts sources
- `REFERENCES`: Explicit causal/contextual link

**FR-6.2** Edges SHALL be stored in a dedicated git notes ref (`refs/notes/mem-edges/`).

**FR-6.3** Edges SHALL include weight (0.0-1.0) for ranking.

### FR-7: Tiered Retrieval

**FR-7.1** RecallService SHALL support retrieval modes:
- `REFLEXIVE`: Hot only (for auto-injection)
- `STANDARD`: Hot + Warm (default search)
- `DEEP`: Hot + Warm + Cold (explicit historical queries)
- `EXHAUSTIVE`: All tiers (audit/debug)

**FR-7.2** Each retrieval SHALL increment the memory's `activation_count`.

**FR-7.3** Search results SHALL include summaries when `include_summaries=True`.

### FR-8: Temporal Reasoning for Explicit Recall

**FR-8.1** A `ReasonedRecallService` SHALL resolve relative temporal references in memories.

**FR-8.2** Temporal references ("yesterday", "last week", "this morning") SHALL be resolved against the memory's creation timestamp.

**FR-8.3** Queries with temporal patterns (e.g., "when did...", "what date...") SHALL auto-enable reasoning mode.

**FR-8.4** Reasoned answers SHALL include:
- Direct answer
- Confidence score
- Reasoning chain
- Resolved temporal references
- Source memories (provenance)

### FR-9: SessionStart Summary Injection

**FR-9.1** Consolidated summaries SHALL be injected into Claude Code sessions via the SessionStart hook's `additionalContext`.

**FR-9.2** Injection SHALL be **idempotent**: Multiple Start events produce exactly one summary block (replace, not accumulate).

**FR-9.3** Summary blocks SHALL use unique XML-style tags for detection and replacement:
```xml
<memory_consolidated_summaries version="..." generated_at="...">
...
</memory_consolidated_summaries>
```

**FR-9.4** Summary selection SHALL prioritize by configurable strategy:
- Semantic relevance to current session
- Recency of the summary
- Activation count
- Confidence score

**FR-9.5** Injection SHALL respect a configurable token budget (default: 2000 tokens).

**FR-9.6** Non-summary context SHALL be preserved during injection/replacement.

### FR-10: Consolidation Pipeline

**FR-10.1** The consolidation service SHALL execute a 6-phase pipeline:
1. **SCAN**: Load memories, compute retention scores
2. **CLUSTER**: Group by semantic similarity
3. **SUMMARIZE**: Generate summaries via LLM
4. **SUPERSESSION**: Detect contradictions via LLM judgment
5. **TIER**: Assign tiers based on retention scores
6. **PERSIST**: Write to git notes, update SQLite index

**FR-10.2** Consolidation SHALL support:
- Full mode: Process all memories
- Incremental mode: Process since last run
- Dry-run mode: Compute without persisting
- Checkpoint/resume: Resume from interrupted run

**FR-10.3** Consolidation results SHALL be logged to `refs/notes/mem-runs/`.

### FR-11: Background Trigger

**FR-11.1** Consolidation SHALL be triggerable via:
- Manual CLI command (`/memory:consolidate`)
- Background hook (when observability module installed)
- Memory pressure signal (count exceeds threshold)

**FR-11.2** The consolidation hook SHALL activate when:
- The `[consolidation]` pip extra is installed
- The observability module is detected

**FR-11.3** Background triggers SHALL respect:
- Minimum interval between runs (default: 24 hours)
- Memory count threshold (default: 50 new memories since last run)
- Session idle time (default: 30 minutes)

## Non-Functional Requirements

### NFR-1: Performance

**NFR-1.1** Consolidation of 1000 memories SHALL complete in <5 minutes.

**NFR-1.2** Retention score calculation SHALL be O(1) per memory.

**NFR-1.3** Clustering SHALL use pre-computed embeddings from the index.

### NFR-2: Backward Compatibility

**NFR-2.1** Existing Memory model SHALL remain unchanged.

**NFR-2.2** Existing git notes refs (`refs/notes/mem/*`) SHALL remain untouched.

**NFR-2.3** All existing tests SHALL pass without modification.

**NFR-2.4** Systems without the `[consolidation]` extra SHALL function normally.

### NFR-3: Feature Gating

**NFR-3.1** Consolidation dependencies SHALL be optional via pip extras:
```toml
[project.optional-dependencies]
consolidation = ["scikit-learn>=1.3", "openai>=1.0", "httpx>=0.25"]
```

**NFR-3.2** Without the extra installed:
- All imports SHALL succeed (lazy loading)
- Service factory SHALL raise `NotImplementedError` with helpful message
- No sklearn/openai SHALL be loaded

### NFR-4: Deep Observability (Library-Wide)

**NFR-4.1** ALL modules, classes, and methods SHALL be instrumented with:
- Distributed tracing spans (OpenTelemetry)
- Metrics (counters, histograms, gauges)
- Structured logging with timing

**NFR-4.2** Tracing SHALL provide:
- Parent-child span relationships showing call hierarchy
- Span attributes for key parameters (memory_id, tier, confidence, etc.)
- Timing for every significant operation
- OTLP export to observability backends

**NFR-4.3** Metrics SHALL include:
- Counters: operations by type, successes, failures
- Histograms: operation durations, score distributions, token usage
- Gauges: queue depths, memory tier distribution, active operations

**NFR-4.4** Logging SHALL provide:
- Entry/exit for all public methods with timing
- Decision points (tier changes, supersession detection)
- LLM interactions (request metadata, truncated content at TRACE level)
- Errors with full context

**NFR-4.5** Consolidation-specific observability SHALL include:
- Duration per pipeline phase
- Memories processed count
- Clusters found/created
- Summaries generated
- Supersessions detected
- Tier transitions
- LLM token usage and latency

**NFR-4.6** Failed operations SHALL log errors with full context for debugging.

### NFR-5: Configuration

**NFR-5.1** All consolidation parameters SHALL be configurable via environment variables following the `MEMORY_*` pattern.

**NFR-5.2** Default values SHALL be conservative (prefer false negatives over false positives).

## Git Notes Schema

### New Refs

| Ref | Purpose |
|-----|---------|
| `refs/notes/mem-meta/` | MemoryMetadata records (tier, activation_count, retention) |
| `refs/notes/mem-summaries/` | MemorySummary records (consolidated abstractions) |
| `refs/notes/mem-edges/` | MemoryEdge batches (supersedes/consolidates/references) |
| `refs/notes/mem-runs/` | ConsolidationResult logs (run history) |

### Storage Format

All records SHALL be stored as YAML with the existing git notes patterns.

## CLI Extensions

| Command | Description |
|---------|-------------|
| `/memory:consolidate [--full] [--dry-run]` | Trigger consolidation |
| `/memory:status --verbose` | Include consolidation state |
| `/memory:tiers` | Show tier distribution |
| `/memory:edges <memory_id>` | Show memory relationships |
| `/memory:recall <query> --mode=deep` | Include cold tier |
| `/memory:recall <query> --reason` | Enable temporal reasoning |

## Success Criteria

| ID | Criterion | Measurement |
|----|-----------|-------------|
| SC-1 | No regression | All existing tests pass unchanged |
| SC-2 | Tier distribution | Memories correctly distributed by retention after consolidation |
| SC-3 | Summary quality | Generated summaries preserve key decisions and facts (manual audit) |
| SC-4 | Supersession accuracy | >95% valid supersession detections (sample audit) |
| SC-5 | Performance | 1000 memories consolidated in <5 minutes |
| SC-6 | Feature gating | Graceful error without `[consolidation]` extra |
| SC-7 | SessionStart idempotency | Multiple Start events produce exactly 1 summary block |
| SC-8 | Context preservation | Non-summary additionalContext survives injection/replacement |
| SC-9 | Token budget | Summary injection never exceeds configured limit |
| SC-10 | Temporal reasoning | Relative references resolved correctly in >95% of cases |

## Out of Scope

- Changing existing Memory model structure
- Modifying core CaptureService or RecallService internals (only extend)
- Breaking backward compatibility with existing git notes
- Real-time consolidation (always async/background)
- Provider-specific LLM features beyond OpenAI-compatible API

## Dependencies

- Existing subconsciousness module (`models.py`, `config.py`, `llm_client.py`)
- Existing RecallService and embedding infrastructure
- Existing git notes storage patterns
- scikit-learn (for clustering, optional extra)
- openai SDK (for LLM calls, optional extra)
