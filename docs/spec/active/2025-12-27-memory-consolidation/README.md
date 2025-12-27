# Memory Consolidation

**Spec ID:** SPEC-2025-12-27-001
**Status:** Draft
**Created:** 2025-12-27

## Summary

Extends the `git_notes_memory.subconsciousness` module with cognitive-inspired memory consolidation that manages memory lifecycle through tiered storage, semantic clustering, LLM-powered summarization, and temporal reasoning.

## Problem

Without consolidation:
1. Unbounded memory growth pollutes search results
2. No temporal decay - old obsolete decisions equal fresh ones
3. No abstraction - 50 related memories cost 50x retrieval
4. Contradictions unresolved - superseded info returned with current

## Solution

A 6-phase background pipeline:
1. **SCAN** - Load memories, compute retention scores
2. **CLUSTER** - Group by semantic similarity (ignore time)
3. **SUMMARIZE** - LLM-generated consolidated summaries
4. **SUPERSESSION** - LLM detects when newer invalidates older
5. **TIER** - Assign HOT/WARM/COLD/ARCHIVED tiers
6. **PERSIST** - Write to git notes, update index

## Key Features

| Feature | Description |
|---------|-------------|
| **Tiered Retrieval** | HOT → WARM → COLD → ARCHIVED, configurable modes |
| **Retention Scoring** | Recency + activation + importance, exponential decay |
| **Semantic Clustering** | Related memories consolidated regardless of time |
| **LLM Summarization** | Preserves decisions, facts, superseded info |
| **Temporal Reasoning** | Resolves "yesterday" in memories to actual dates |
| **SessionStart Injection** | Idempotent summary context (replace, not accumulate) |
| **Deep Observability** | Tracing, metrics, logging at every level |

## Documents

| Document | Description |
|----------|-------------|
| [REQUIREMENTS.md](./REQUIREMENTS.md) | Functional and non-functional requirements |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Technical architecture and design decisions |
| [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) | 220 tasks across 7 phases |

## Scope

### In Scope
- Memory tier system (HOT/WARM/COLD/ARCHIVED)
- Retention score calculation with configurable decay
- Semantic clustering with AgglomerativeClustering
- LLM-powered summarization and supersession detection
- Temporal reasoning for explicit recall queries
- SessionStart idempotent summary injection
- Background consolidation hook
- CLI commands (`/memory:consolidate`, `/memory:tiers`, `/memory:edges`)
- Full observability (tracing, metrics, logging) at every module/method level
- Feature gating via pip extras `[consolidation]`

### Out of Scope
- Changing existing Memory model structure
- Modifying core CaptureService internals
- Breaking backward compatibility
- Real-time consolidation (always async)

## Dependencies

### pip extras `[consolidation]`
```toml
consolidation = [
    "scikit-learn>=1.3",
    "openai>=1.0",
    "httpx>=0.25",
]
```

### Internal
- Existing subconsciousness module
- Existing RecallService and EmbeddingService
- Existing observability module

## Effort Estimate

| Phase | Tasks | Focus |
|-------|-------|-------|
| Phase 1 | 31 | Models, Config, Observability |
| Phase 2 | 43 | Storage Layer |
| Phase 3 | 24 | Retention, Clustering |
| Phase 4 | 26 | LLM Prompts, Temporal |
| Phase 5 | 33 | Core Services |
| Phase 6 | 47 | Hooks, CLI |
| Phase 7 | 16 | Docs, Testing |
| **Total** | **220** | - |

## Success Criteria

1. No regression - existing tests pass
2. Tier distribution correct after consolidation
3. Summaries preserve decisions and key facts
4. Supersession detection >95% accurate
5. 1000 memories in <5 minutes
6. Feature-gated with helpful error
7. SessionStart idempotent (1 block, no accumulation)
8. Context preserved during injection
9. Token budget enforced
10. Temporal reasoning >95% accurate

## Related

- Research: `docs/research/CognitiveSubstrate/memory-consolidation-*.md`
- Completed: `docs/spec/completed/2025-12-25-llm-subconsciousness/` (LLM foundation)
- Completed: `docs/spec/completed/2025-12-25-observability-instrumentation/` (Observability)
