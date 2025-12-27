---
document_type: decisions
project_id: SPEC-2025-12-27-002
---

# Memory Retrieval Performance Improvements - Architecture Decision Records

## ADR-001: Use Reciprocal Rank Fusion for Hybrid Search

**Date**: 2025-12-27
**Status**: Proposed
**Deciders**: User, Claude

### Context

We need to combine rankings from multiple search strategies (vector similarity, BM25, entity matching). Several fusion approaches exist: weighted linear combination, CombSUM, CombMNZ, and Reciprocal Rank Fusion (RRF).

### Decision

Use Reciprocal Rank Fusion (RRF) with configurable k parameter (default 60).

```
RRF_score(d) = Σ (weight_i / (k + rank_i(d)))
```

### Consequences

**Positive:**
- RRF is parameter-light (just k and weights)
- Well-studied in IR literature
- Works well when sources have different score distributions
- Easy to add new sources (just another ranking list)

**Negative:**
- Requires computing full rankings from each source
- May not be optimal when one source is clearly better for a query type
- Fixed k may not be ideal for all query types

### Alternatives Considered

1. **Linear Score Combination**: Requires score normalization, sensitive to scale differences
2. **CombSUM/CombMNZ**: More complex, requires tuning multiple parameters
3. **Learning-to-Rank**: Requires training data, adds ML complexity

---

## ADR-002: Add Dependencies to [consolidation] Extra

**Date**: 2025-12-27
**Status**: Accepted (per user preference)
**Deciders**: User

### Context

The new retrieval features require spaCy (for NER) and dateparser (for temporal parsing). These add ~20MB to install size. We could create a new `[retrieval]` extra or add to existing `[consolidation]`.

### Decision

Add spaCy and dateparser to the existing `[consolidation]` extra per user preference.

```toml
[project.optional-dependencies]
consolidation = [
    # ... existing deps ...
    "spacy>=3.7",
    "dateparser>=1.2",
]
```

### Consequences

**Positive:**
- Single extra for advanced features (simpler user experience)
- Users who want consolidation likely want advanced retrieval too
- Fewer combinations to test

**Negative:**
- Users who only want consolidation get retrieval deps
- Install size slightly larger for consolidation-only users

### Alternatives Considered

1. **New [retrieval] extra**: Cleaner separation but more complexity
2. **Core dependencies**: Would bloat minimal install

---

## ADR-003: Graceful Degradation Without Optional Dependencies

**Date**: 2025-12-27
**Status**: Proposed
**Deciders**: Claude

### Context

spaCy and dateparser are optional. The library should work without them, with reduced functionality.

### Decision

Implement graceful degradation with fallbacks:
- spaCy unavailable → use regex-only entity extraction
- dateparser unavailable → use ISO date parsing only
- LLM unavailable → skip query expansion

### Consequences

**Positive:**
- Library always works, even without optional deps
- Clear error messages when features degraded
- Users can install deps as needed

**Negative:**
- Reduced accuracy without spaCy
- More code paths to test
- Need to document degradation behavior

### Alternatives Considered

1. **Hard dependency**: Would break minimal installs
2. **Feature flags only**: Wouldn't catch missing deps gracefully

---

## ADR-004: Parallel Execution of Search Strategies

**Date**: 2025-12-27
**Status**: Proposed
**Deciders**: Claude

### Context

Hybrid search executes multiple strategies (vector, BM25, entity). These could run sequentially or in parallel.

### Decision

Execute vector and BM25 searches in parallel using asyncio or threading, with a fallback to sequential execution.

### Consequences

**Positive:**
- Lower total latency (max(latencies) instead of sum)
- Better utilization of I/O wait time
- Configurable via `enable_parallel` flag

**Negative:**
- More complex error handling
- SQLite connection management needs care
- Debugging more complex

### Alternatives Considered

1. **Sequential only**: Simpler but slower
2. **Always parallel**: No escape hatch for debugging

---

## ADR-005: Use FTS5 BM25 Instead of rank_bm25 Library

**Date**: 2025-12-27
**Status**: Proposed
**Deciders**: Claude

### Context

The codebase already has FTS5 configured (schema v4, PERF-H-005). We could use the existing FTS5 BM25 or add the rank_bm25 Python library.

### Decision

Use existing FTS5 BM25 implementation. No additional dependency.

### Consequences

**Positive:**
- No new dependency
- Already integrated with schema
- Single index (not separate BM25 corpus)
- FTS5 is highly optimized

**Negative:**
- Less control over BM25 parameters (k1, b)
- Can't easily experiment with BM25L, BM25+

### Alternatives Considered

1. **rank_bm25 library**: More control but new dependency, separate index
2. **bm25s (Numba-accelerated)**: Fast but heavy dependency

---

## ADR-006: Entity Extraction at Capture Time

**Date**: 2025-12-27
**Status**: Proposed
**Deciders**: Claude

### Context

Entities could be extracted at capture time (synchronous) or asynchronously (background job). The consolidation module already has background processing.

### Decision

Extract entities synchronously during capture, with timeout protection.

### Consequences

**Positive:**
- Entities immediately available for search
- Simpler architecture (no job queue)
- Consistent with current capture flow

**Negative:**
- Adds latency to capture (~10-50ms)
- spaCy model loaded on first capture

### Alternatives Considered

1. **Async extraction**: Lower capture latency but delayed searchability
2. **Batch extraction**: Good for bulk, but delays individual captures

---

## ADR-007: Opt-In LLM Query Expansion

**Date**: 2025-12-27
**Status**: Proposed
**Deciders**: Claude

### Context

LLM query expansion adds significant latency (100-200ms). It should be optional.

### Decision

Make query expansion opt-in via `expand_query=False` default parameter.

### Consequences

**Positive:**
- Default behavior is fast
- Users explicitly opt into latency
- Can enable globally via env var

**Negative:**
- Users may not discover the feature
- Need good documentation

### Alternatives Considered

1. **Opt-out (on by default)**: Would surprise users with latency
2. **Auto-detect ambiguous queries**: Complex, may misfire

---

## ADR-008: Single SQLite Database for All Tables

**Date**: 2025-12-27
**Status**: Proposed
**Deciders**: Claude

### Context

New tables (entities, memory_entities, temporal_refs) could go in the existing index.db or a separate database.

### Decision

Add new tables to existing index.db with foreign key relationships.

### Consequences

**Positive:**
- Single file to manage
- Atomic transactions across tables
- Simpler backup/restore

**Negative:**
- Larger single file
- All migrations in one sequence

### Alternatives Considered

1. **Separate retrieval.db**: Cleaner separation but complex joins
2. **In-memory for entities**: Fast but no persistence

---

## ADR-009: Regex Fallback for Entity Extraction

**Date**: 2025-12-27
**Status**: Proposed
**Deciders**: Claude

### Context

spaCy is optional. We need a fallback for entity extraction.

### Decision

Implement comprehensive regex patterns for:
- File paths (`/path/to/file.py`, `src/module/file.ts`)
- URLs (`https://example.com`)
- @mentions (`@username`)
- Code references (`` `ClassName.method` ``)
- Technology names (configurable list)

### Consequences

**Positive:**
- Works without spaCy
- Very fast (<1ms)
- Good for technical entities (file paths, code)

**Negative:**
- Lower accuracy for PERSON, ORG
- Needs manual pattern maintenance

### Alternatives Considered

1. **No fallback**: Would disable entity features without spaCy
2. **Simple word tokenization**: Too noisy

---

## ADR-010: dateparser for Temporal Parsing

**Date**: 2025-12-27
**Status**: Proposed
**Deciders**: Claude

### Context

We need to parse natural language dates ("last week", "in December"). Options: dateparser, dateutil, parsedatetime.

### Decision

Use dateparser library for its comprehensive language support and relative date handling.

### Consequences

**Positive:**
- Handles relative dates well
- Multi-language support (future)
- Active maintenance

**Negative:**
- ~5MB dependency
- Can be slow for complex expressions

### Alternatives Considered

1. **dateutil.parser**: Limited relative date support
2. **parsedatetime**: Less maintained
3. **Custom regex**: Limited and brittle
