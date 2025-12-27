# Memory Consolidation: Implementation Plan

**Spec ID:** SPEC-2025-12-27-001
**Status:** Draft
**Estimated Effort:** ~85 tasks across 6 phases

## Implementation Principles

1. **No deferrals** - All tasks are completed, none skipped or pushed to future work
2. **Deep observability** - Every module, method, and class is instrumented with tracing, metrics, and logging
3. **Test-first** - Each component has unit tests before integration
4. **Backward compatible** - Existing functionality remains unchanged

---

## Phase 1: Foundation - Models, Config, and Observability

**Goal:** Establish data models, configuration, and observability infrastructure

### 1.1 New Models (`models.py`)
- [ ] 1.1.1 Add `MemoryTier` enum (HOT, WARM, COLD, ARCHIVED)
- [ ] 1.1.2 Add `RetentionScore` frozen dataclass with validation
- [ ] 1.1.3 Add `MemoryMetadata` frozen dataclass
- [ ] 1.1.4 Add `SummaryDecision` frozen dataclass
- [ ] 1.1.5 Add `SupersededFact` frozen dataclass
- [ ] 1.1.6 Add `MemorySummary` frozen dataclass with `to_dict()`
- [ ] 1.1.7 Add `EdgeType` enum (SUPERSEDES, CONSOLIDATES, REFERENCES)
- [ ] 1.1.8 Add `MemoryEdge` frozen dataclass with `to_dict()`
- [ ] 1.1.9 Add `ConsolidationPhase` enum
- [ ] 1.1.10 Add `TierTransition` frozen dataclass
- [ ] 1.1.11 Add `ConsolidationResult` frozen dataclass with `success` property
- [ ] 1.1.12 Add `TemporalReference` frozen dataclass
- [ ] 1.1.13 Add `ReasonedAnswer` frozen dataclass
- [ ] 1.1.14 Add `MemoryCluster` frozen dataclass for clustering output
- [ ] 1.1.15 Unit tests for all new models (validation, serialization)

### 1.2 Config Extensions (`config.py`)
- [ ] 1.2.1 Add retention config defaults (half_life, activation_boost, weights)
- [ ] 1.2.2 Add tier threshold defaults (hot, warm, archive)
- [ ] 1.2.3 Add clustering config defaults (min/max size, threshold, batch_size)
- [ ] 1.2.4 Add consolidation interval config
- [ ] 1.2.5 Add SessionStart summary injection config defaults
- [ ] 1.2.6 Add consolidation hook config defaults
- [ ] 1.2.7 Add LLM provider config for consolidation
- [ ] 1.2.8 Extend `SubconsciousnessConfig` dataclass with all new fields
- [ ] 1.2.9 Add environment variable parsing for all new config
- [ ] 1.2.10 Unit tests for config loading from env

### 1.3 Observability Infrastructure
- [ ] 1.3.1 Create `consolidation/observability.py` with tracer, metrics, logger factories
- [ ] 1.3.2 Define span names and attributes constants
- [ ] 1.3.3 Define metric names and labels constants
- [ ] 1.3.4 Create `@traced` decorator for method instrumentation
- [ ] 1.3.5 Create `@timed_histogram` decorator for duration metrics
- [ ] 1.3.6 Unit tests for observability decorators

---

## Phase 2: Storage Layer

**Goal:** Implement git notes stores for metadata, summaries, edges, and run logs

### 2.1 Metadata Store (`stores/metadata_store.py`)
- [ ] 2.1.1 Create `MetadataStore` class with git notes backend
- [ ] 2.1.2 Implement `get(memory_id)` → `MemoryMetadata | None`
- [ ] 2.1.3 Implement `get_batch(memory_ids)` → `dict[str, MemoryMetadata]`
- [ ] 2.1.4 Implement `save(metadata)` with YAML serialization
- [ ] 2.1.5 Implement `save_batch(metadata_list)` for bulk writes
- [ ] 2.1.6 Implement `increment_activation(memory_ids)` for activation tracking
- [ ] 2.1.7 Implement `get_by_tier(tier)` → `list[MemoryMetadata]`
- [ ] 2.1.8 Add tracing spans for all methods
- [ ] 2.1.9 Add metrics (reads, writes, batch sizes)
- [ ] 2.1.10 Add structured logging
- [ ] 2.1.11 Unit tests with mock git backend
- [ ] 2.1.12 Integration tests with real git repo

### 2.2 Summary Store (`stores/summary_store.py`)
- [ ] 2.2.1 Create `SummaryStore` class with git notes backend
- [ ] 2.2.2 Implement `get(summary_id)` → `MemorySummary | None`
- [ ] 2.2.3 Implement `save(summary)` with YAML serialization
- [ ] 2.2.4 Implement `get_by_tier(tier)` → `list[MemorySummary]`
- [ ] 2.2.5 Implement `search(query, limit)` with embedding similarity
- [ ] 2.2.6 Implement `get_by_source_memory(memory_id)` for provenance
- [ ] 2.2.7 Add tracing spans for all methods
- [ ] 2.2.8 Add metrics (reads, writes, searches)
- [ ] 2.2.9 Add structured logging
- [ ] 2.2.10 Unit tests with mock git backend
- [ ] 2.2.11 Integration tests with real git repo

### 2.3 Edge Store (`stores/edge_store.py`)
- [ ] 2.3.1 Create `EdgeStore` class with git notes backend
- [ ] 2.3.2 Implement `save(edge)` with YAML serialization
- [ ] 2.3.3 Implement `save_batch(edges)` for bulk writes
- [ ] 2.3.4 Implement `get_outgoing(source_id)` → `list[MemoryEdge]`
- [ ] 2.3.5 Implement `get_incoming(target_id)` → `list[MemoryEdge]`
- [ ] 2.3.6 Implement `get_by_type(edge_type)` → `list[MemoryEdge]`
- [ ] 2.3.7 Add tracing spans for all methods
- [ ] 2.3.8 Add metrics (writes by edge type)
- [ ] 2.3.9 Add structured logging
- [ ] 2.3.10 Unit tests with mock git backend
- [ ] 2.3.11 Integration tests with real git repo

### 2.4 Run Log Store (`stores/run_store.py`)
- [ ] 2.4.1 Create `RunStore` class for consolidation run logs
- [ ] 2.4.2 Implement `log_run(result)` append-only
- [ ] 2.4.3 Implement `get_last_run()` → `ConsolidationResult | None`
- [ ] 2.4.4 Implement `get_runs(limit)` → `list[ConsolidationResult]`
- [ ] 2.4.5 Add tracing spans for all methods
- [ ] 2.4.6 Add metrics (runs logged)
- [ ] 2.4.7 Add structured logging
- [ ] 2.4.8 Unit tests

### 2.5 SQLite Index Extensions
- [ ] 2.5.1 Add `tier` column to memories table
- [ ] 2.5.2 Add `activation_count` column to memories table
- [ ] 2.5.3 Add `last_accessed` column to memories table
- [ ] 2.5.4 Create `mem_summaries` table for summary indexing
- [ ] 2.5.5 Create `mem_edges` table for edge indexing
- [ ] 2.5.6 Create `consolidation_runs` table for run history
- [ ] 2.5.7 Add migration script for existing indexes
- [ ] 2.5.8 Unit tests for schema changes
- [ ] 2.5.9 Integration tests for migration

---

## Phase 3: Retention and Clustering

**Goal:** Implement retention score calculation and semantic clustering

### 3.1 Retention Calculation (`consolidation/retention.py`)
- [ ] 3.1.1 Create `NAMESPACE_IMPORTANCE` mapping
- [ ] 3.1.2 Create `RetentionConfig` dataclass with defaults
- [ ] 3.1.3 Implement `compute_recency_factor(memory, now, config)` with exponential decay
- [ ] 3.1.4 Implement `compute_activation_factor(metadata)` with log scale
- [ ] 3.1.5 Implement `compute_importance_factor(memory)` from namespace
- [ ] 3.1.6 Implement `compute_retention_score(memory, metadata, config, now)` with weighted combination
- [ ] 3.1.7 Implement superseded penalty (0.2x multiplier)
- [ ] 3.1.8 Implement `assign_tier(score, config)` → `MemoryTier`
- [ ] 3.1.9 Add tracing span for `compute_retention_score`
- [ ] 3.1.10 Add histogram metric for score distribution
- [ ] 3.1.11 Add structured logging for tier assignments
- [ ] 3.1.12 Unit tests for score calculation (boundary conditions)
- [ ] 3.1.13 Unit tests for tier assignment
- [ ] 3.1.14 Property tests: score always in [0, 1]

### 3.2 Semantic Clustering (`consolidation/clustering.py`)
- [ ] 3.2.1 Implement `cluster_memories(memories, embeddings, config)` with AgglomerativeClustering
- [ ] 3.2.2 Implement `compute_distance_matrix(embeddings)` using cosine distance
- [ ] 3.2.3 Implement size filtering (min/max cluster size)
- [ ] 3.2.4 Create `MemoryCluster` output model
- [ ] 3.2.5 Add tracing spans for clustering operations
- [ ] 3.2.6 Add histogram metrics for cluster sizes
- [ ] 3.2.7 Add structured logging for cluster assignments
- [ ] 3.2.8 Unit tests with mock embeddings
- [ ] 3.2.9 Unit tests for size constraints
- [ ] 3.2.10 Integration test with real embeddings

---

## Phase 4: LLM Integration

**Goal:** Implement LLM-powered summarization, supersession detection, and temporal reasoning

### 4.1 Consolidation Prompts (`consolidation/prompts.py`)
- [ ] 4.1.1 Create `SUMMARY_SYSTEM_PROMPT` for cluster summarization
- [ ] 4.1.2 Create `SUMMARY_USER_PROMPT` template
- [ ] 4.1.3 Create `SUPERSESSION_SYSTEM_PROMPT` for contradiction detection
- [ ] 4.1.4 Create `SUPERSESSION_USER_PROMPT` template
- [ ] 4.1.5 Create response parsers with validation
- [ ] 4.1.6 Unit tests for prompt formatting
- [ ] 4.1.7 Unit tests for response parsing (valid and malformed)

### 4.2 Reasoning Prompts (`reasoning/prompts.py`)
- [ ] 4.2.1 Create `REASONING_SYSTEM_PROMPT` for temporal reasoning
- [ ] 4.2.2 Create `REASONING_USER_PROMPT` template
- [ ] 4.2.3 Create response parser for `ReasonedAnswer`
- [ ] 4.2.4 Unit tests for prompt formatting
- [ ] 4.2.5 Unit tests for response parsing

### 4.3 Temporal Resolution (`reasoning/temporal.py`)
- [ ] 4.3.1 Create `TEMPORAL_PATTERNS` mapping (yesterday, last week, etc.)
- [ ] 4.3.2 Implement `detect_temporal_references(content)` → `list[str]`
- [ ] 4.3.3 Implement `resolve_temporal_reference(reference, memory_timestamp)` → `datetime`
- [ ] 4.3.4 Handle edge cases (month boundaries, year boundaries)
- [ ] 4.3.5 Add tracing for resolution operations
- [ ] 4.3.6 Add metrics for temporal patterns detected
- [ ] 4.3.7 Unit tests for all temporal patterns
- [ ] 4.3.8 Unit tests for edge cases (month/year boundaries)

### 4.4 LLM Client Extension
- [ ] 4.4.1 Add consolidation-specific LLM provider config
- [ ] 4.4.2 Implement `get_consolidation_llm_client()` factory
- [ ] 4.4.3 Add tracing spans for LLM calls
- [ ] 4.4.4 Add metrics (requests, tokens, latency)
- [ ] 4.4.5 Add structured logging (model, provider, truncated content)
- [ ] 4.4.6 Unit tests with mock LLM client

---

## Phase 5: Core Services

**Goal:** Implement ConsolidationService, ReasonedRecallService, and extended RecallService

### 5.1 Consolidation Service (`consolidation/service.py`)
- [ ] 5.1.1 Create `ConsolidationService` dataclass with dependencies
- [ ] 5.1.2 Implement `run_consolidation(full, dry_run, checkpoint_id)` orchestrator
- [ ] 5.1.3 Implement `_phase_scan()` - load memories, compute retention
- [ ] 5.1.4 Implement `_phase_cluster()` - semantic clustering
- [ ] 5.1.5 Implement `_phase_summarize()` - LLM summary generation
- [ ] 5.1.6 Implement `_phase_supersession()` - LLM contradiction detection
- [ ] 5.1.7 Implement `_phase_tier()` - assign tiers from scores
- [ ] 5.1.8 Implement `_phase_persist()` - write to stores
- [ ] 5.1.9 Implement `incremental_consolidation()` - since last run
- [ ] 5.1.10 Implement checkpoint/resume logic
- [ ] 5.1.11 Implement dry-run mode (compute without persist)
- [ ] 5.1.12 Implement `get_status()` for status reporting
- [ ] 5.1.13 Add tracing spans for each phase
- [ ] 5.1.14 Add metrics for each phase (duration, counts)
- [ ] 5.1.15 Add structured logging for phase transitions
- [ ] 5.1.16 Create `get_consolidation_service()` factory
- [ ] 5.1.17 Create `reset_consolidation_service()` for testing
- [ ] 5.1.18 Unit tests with mocked dependencies
- [ ] 5.1.19 Integration tests for full pipeline
- [ ] 5.1.20 Property tests: consolidation is idempotent

### 5.2 Reasoned Recall Service (`reasoning/service.py`)
- [ ] 5.2.1 Create `ReasonedRecallService` dataclass with dependencies
- [ ] 5.2.2 Implement `recall_with_reasoning(query, mode, require_temporal)` main method
- [ ] 5.2.3 Implement `_format_memories_with_timestamps(memories)` for LLM context
- [ ] 5.2.4 Implement `_reason_over_memories(query, context)` LLM call
- [ ] 5.2.5 Implement `_parse_reasoning_response(response)` → `ReasonedAnswer`
- [ ] 5.2.6 Add tracing spans for reasoning operations
- [ ] 5.2.7 Add metrics (reasoned recalls, temporal resolutions, confidence histogram)
- [ ] 5.2.8 Add structured logging
- [ ] 5.2.9 Create `get_reasoned_recall_service()` factory
- [ ] 5.2.10 Create `reset_reasoned_recall_service()` for testing
- [ ] 5.2.11 Unit tests with mock LLM
- [ ] 5.2.12 Integration tests for temporal resolution accuracy

### 5.3 RecallService Extension
- [ ] 5.3.1 Add `RetrievalMode` enum to models
- [ ] 5.3.2 Extend `search()` with `mode` parameter
- [ ] 5.3.3 Implement tier filtering by retrieval mode
- [ ] 5.3.4 Extend `search()` with `include_summaries` parameter
- [ ] 5.3.5 Implement summary result merging
- [ ] 5.3.6 Implement activation count increment on retrieval
- [ ] 5.3.7 Add `_query_needs_reasoning(query)` heuristic
- [ ] 5.3.8 Add tracing spans for tier filtering
- [ ] 5.3.9 Add metrics (recalls by mode, activation increments)
- [ ] 5.3.10 Add structured logging
- [ ] 5.3.11 Unit tests for tier filtering
- [ ] 5.3.12 Unit tests for activation tracking
- [ ] 5.3.13 Integration tests with real index

---

## Phase 6: Hook Integration and CLI

**Goal:** Implement SessionStart injection, background consolidation hook, and CLI commands

### 6.1 Session Summary Injector (`session/summary_injector.py`)
- [ ] 6.1.1 Define context encapsulation tags (`<memory_consolidated_summaries>`)
- [ ] 6.1.2 Create `SummaryInjectionConfig` dataclass
- [ ] 6.1.3 Create `SummaryInjectionResult` dataclass
- [ ] 6.1.4 Create `SessionStartSummaryInjector` class
- [ ] 6.1.5 Implement `inject_summaries(existing_context, session_context)` main method
- [ ] 6.1.6 Implement `_remove_existing_block(context)` regex-based removal
- [ ] 6.1.7 Implement `_select_summaries(session_context)` with scoring
- [ ] 6.1.8 Implement `_compute_session_relevance(summary, context)` scoring
- [ ] 6.1.9 Implement `_compute_recency_score(summary)` scoring
- [ ] 6.1.10 Implement `_format_summary_block(summaries)` with token budget
- [ ] 6.1.11 Implement `_format_single_summary(summary)` formatting
- [ ] 6.1.12 Implement `_estimate_tokens(text)` for budget enforcement
- [ ] 6.1.13 Add tracing spans for injection operations
- [ ] 6.1.14 Add metrics (injections, replacements, tokens used)
- [ ] 6.1.15 Add structured logging
- [ ] 6.1.16 Create `get_summary_injector()` factory
- [ ] 6.1.17 Unit tests for block removal (idempotency)
- [ ] 6.1.18 Unit tests for summary selection
- [ ] 6.1.19 Unit tests for token budget enforcement
- [ ] 6.1.20 Integration tests: multiple Start events don't accumulate
- [ ] 6.1.21 Integration tests: non-summary context preserved

### 6.2 Hook Integration (`hook_integration.py` extension)
- [ ] 6.2.1 Add `is_consolidation_available()` feature detection
- [ ] 6.2.2 Extend SessionStart handler to call summary injector
- [ ] 6.2.3 Create `SessionContext` from SessionStart event
- [ ] 6.2.4 Implement `get_session_start_additional_context()` helper
- [ ] 6.2.5 Add tracing for hook integration
- [ ] 6.2.6 Add metrics for hook execution
- [ ] 6.2.7 Add structured logging
- [ ] 6.2.8 Unit tests for feature gating
- [ ] 6.2.9 Integration tests for hook flow

### 6.3 Background Consolidation Hook (`consolidation/hook.py`)
- [ ] 6.3.1 Create `ConsolidationHook` class
- [ ] 6.3.2 Implement `should_trigger()` based on conditions
- [ ] 6.3.3 Implement idle time check
- [ ] 6.3.4 Implement memory count threshold check
- [ ] 6.3.5 Implement interval since last run check
- [ ] 6.3.6 Implement `execute()` → `ConsolidationResult`
- [ ] 6.3.7 Add tracing spans for trigger checks
- [ ] 6.3.8 Add metrics for trigger conditions
- [ ] 6.3.9 Add structured logging
- [ ] 6.3.10 Unit tests for trigger conditions
- [ ] 6.3.11 Integration tests for hook execution

### 6.4 CLI Commands
- [ ] 6.4.1 Create `/memory:consolidate` command handler
- [ ] 6.4.2 Implement `--full` flag for full consolidation
- [ ] 6.4.3 Implement `--dry-run` flag
- [ ] 6.4.4 Extend `/memory:status` with consolidation status
- [ ] 6.4.5 Create `/memory:tiers` command for tier distribution
- [ ] 6.4.6 Create `/memory:edges` command for relationship display
- [ ] 6.4.7 Extend `/memory:recall` with `--mode` flag
- [ ] 6.4.8 Extend `/memory:recall` with `--reason` flag
- [ ] 6.4.9 Update command markdown documentation
- [ ] 6.4.10 Add tracing for CLI command execution
- [ ] 6.4.11 Add metrics for command usage
- [ ] 6.4.12 Unit tests for command handlers
- [ ] 6.4.13 Integration tests for CLI flow

### 6.5 Feature Gating (`pyproject.toml`)
- [ ] 6.5.1 Add `[consolidation]` optional dependencies
- [ ] 6.5.2 Implement lazy import pattern for consolidation module
- [ ] 6.5.3 Implement `NotImplementedError` with helpful message
- [ ] 6.5.4 Unit tests for import without extra
- [ ] 6.5.5 Integration tests with extra installed

---

## Phase 7: Documentation and Finalization

**Goal:** Complete documentation, Grafana dashboards, and final testing

### 7.1 Documentation
- [ ] 7.1.1 Update CLAUDE.md with consolidation commands
- [ ] 7.1.2 Update CLAUDE.md with new environment variables
- [ ] 7.1.3 Add consolidation section to README
- [ ] 7.1.4 Create DECISIONS.md with ADRs for key decisions
- [ ] 7.1.5 Update architecture diagrams

### 7.2 Grafana Dashboards
- [ ] 7.2.1 Create Memory Consolidation dashboard
- [ ] 7.2.2 Add consolidation run metrics panel
- [ ] 7.2.3 Add tier distribution gauge panel
- [ ] 7.2.4 Add LLM usage metrics panel
- [ ] 7.2.5 Add clustering metrics panel
- [ ] 7.2.6 Create Tempo trace search for consolidation spans

### 7.3 Final Testing
- [ ] 7.3.1 Run full test suite
- [ ] 7.3.2 Verify 80%+ coverage
- [ ] 7.3.3 Manual end-to-end testing
- [ ] 7.3.4 Performance testing (1000 memories < 5 min)
- [ ] 7.3.5 Idempotency verification

---

## Task Summary

| Phase | Task Count | Focus |
|-------|------------|-------|
| Phase 1 | 31 | Models, Config, Observability Infrastructure |
| Phase 2 | 43 | Storage Layer (Metadata, Summary, Edge, Run stores) |
| Phase 3 | 24 | Retention Calculation, Semantic Clustering |
| Phase 4 | 26 | LLM Prompts, Temporal Resolution, LLM Client |
| Phase 5 | 33 | ConsolidationService, ReasonedRecallService, RecallService |
| Phase 6 | 47 | Session Injection, Hooks, CLI Commands, Feature Gating |
| Phase 7 | 16 | Documentation, Dashboards, Final Testing |
| **Total** | **220** | - |

## Dependencies

### External (pip extras `[consolidation]`)
- `scikit-learn>=1.3` - AgglomerativeClustering for semantic grouping
- `openai>=1.0` - OpenAI SDK for LLM calls
- `httpx>=0.25` - HTTP client for LM Studio

### Internal
- Existing `subconsciousness` module (models, config, llm_client)
- Existing `RecallService` and `EmbeddingService`
- Existing `git_ops` module for notes CRUD
- Existing `observability` module (tracer, metrics, logger)

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM rate limiting | Circuit breaker and fallback chain (OpenAI → LM Studio → Ollama) |
| Clustering performance | Batch processing, pre-computed embeddings |
| Git notes bloat | Run log retention limits, summary pruning |
| Feature gating confusion | Clear error messages, documentation |
| SessionStart accumulation | Strict regex replacement, idempotency tests |

## Success Criteria Mapping

| Criterion | Verified By |
|-----------|-------------|
| SC-1: No regression | Phase 7.3.1 - Full test suite |
| SC-2: Tier distribution | Phase 5.1.19 - Integration tests |
| SC-3: Summary quality | Manual audit |
| SC-4: Supersession accuracy | Phase 5.1.18 - Unit tests |
| SC-5: Performance | Phase 7.3.4 - Performance testing |
| SC-6: Feature gating | Phase 6.5.4-5 - Feature gate tests |
| SC-7: SessionStart idempotency | Phase 6.1.20 - Integration tests |
| SC-8: Context preservation | Phase 6.1.21 - Integration tests |
| SC-9: Token budget | Phase 6.1.19 - Unit tests |
| SC-10: Temporal reasoning | Phase 5.2.12 - Integration tests |
