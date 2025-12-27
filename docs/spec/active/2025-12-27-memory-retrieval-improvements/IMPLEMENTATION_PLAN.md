---
document_type: implementation_plan
project_id: SPEC-2025-12-27-002
version: 1.0.0
last_updated: 2025-12-27T18:00:00Z
status: draft
---

# Memory Retrieval Performance Improvements - Implementation Plan

## Overview

This implementation plan breaks down the retrieval improvements into 5 phases, prioritizing the highest-impact changes first. Each phase is independently deployable and testable, following the codebase's established patterns for schema migrations, service composition, and observability integration.

## Team & Resources

| Role | Responsibility | Allocation |
|------|----------------|------------|
| Claude Code Agent | All implementation | 100% |
| User | Review, approval, benchmark validation | As needed |

## Phase Summary

| Phase | Focus | Key Deliverables | Dependencies |
|-------|-------|------------------|--------------|
| Phase 1: Foundation | Schema + RRF | Schema v5, RRF fusion engine | None |
| Phase 2: Hybrid Search | BM25 + Vector fusion | HybridSearchEngine, RecallService extension | Phase 1 |
| Phase 3: Entity Indexing | NER + Entity tables | EntityExtractor, entity-memory mapping | Phase 1 |
| Phase 4: Temporal Indexing | Date parsing + filtering | TemporalExtractor, date-range search | Phase 1 |
| Phase 5: Query Expansion | LLM-powered expansion | QueryExpander, caching | Phase 2 |

---

## Phase 1: Foundation

**Goal**: Establish schema v5 and core RRF fusion algorithm
**Prerequisites**: None
**Exit Criteria**: Schema migration works, RRF produces correct rankings

### Tasks

#### Task 1.1: Schema v5 Migration

- **Description**: Add new tables (entities, memory_entities, temporal_refs) via schema migration
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] Schema version bumped to 5
  - [ ] `entities` table created with indexes
  - [ ] `memory_entities` table created with foreign keys
  - [ ] `temporal_refs` table created with date indexes
  - [ ] Migration runs on fresh and existing databases
  - [ ] Rollback tested (tables can be dropped without breaking v4)
- **Files**:
  - `src/git_notes_memory/index/schema_manager.py` - Add v5 migrations

#### Task 1.2: RRF Fusion Engine

- **Description**: Implement Reciprocal Rank Fusion algorithm
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] `RRFFusionEngine` class with `fuse()` method
  - [ ] Configurable k parameter (default 60)
  - [ ] Configurable weights per source
  - [ ] Unit tests with known rankings
  - [ ] Edge cases: empty lists, single source, ties
- **Files**:
  - `src/git_notes_memory/index/rrf_fusion.py` - New file
  - `tests/index/test_rrf_fusion.py` - New test file

#### Task 1.3: HybridSearchConfig Dataclass

- **Description**: Create configuration dataclass for hybrid search
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] Frozen dataclass with all config parameters
  - [ ] Environment variable loading
  - [ ] Sensible defaults
  - [ ] Integration with observability config pattern
- **Files**:
  - `src/git_notes_memory/retrieval/__init__.py` - New module
  - `src/git_notes_memory/retrieval/config.py` - Config classes

#### Task 1.4: Retrieval Module Scaffold

- **Description**: Create the new `retrieval/` module structure
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] Module with `__init__.py` and lazy imports
  - [ ] Factory functions for services
  - [ ] Export in main `__init__.py`
- **Files**:
  - `src/git_notes_memory/retrieval/__init__.py`
  - `src/git_notes_memory/retrieval/config.py`

### Phase 1 Deliverables

- [ ] Schema v5 migration in `schema_manager.py`
- [ ] `RRFFusionEngine` with tests
- [ ] `HybridSearchConfig` dataclass
- [ ] `retrieval/` module scaffold

### Phase 1 Exit Criteria

- [ ] `make test` passes
- [ ] Schema migration creates new tables
- [ ] RRF fusion produces correct rankings for test data

---

## Phase 2: Hybrid Search

**Goal**: Combine existing BM25 and vector search using RRF
**Prerequisites**: Phase 1 complete
**Exit Criteria**: Hybrid search returns combined rankings

### Tasks

#### Task 2.1: HybridSearchEngine

- **Description**: Orchestrate vector + BM25 searches and combine with RRF
- **Dependencies**: Task 1.2 (RRF)
- **Acceptance Criteria**:
  - [ ] `HybridSearchEngine` class with `search()` method
  - [ ] Parallel execution of vector and BM25 searches
  - [ ] RRF fusion of results
  - [ ] Observability: latency metrics per strategy
  - [ ] Mode selection: "hybrid", "vector", "bm25"
- **Files**:
  - `src/git_notes_memory/index/hybrid_search.py` - New file
  - `tests/index/test_hybrid_search.py` - New test file

#### Task 2.2: Extend SearchEngine

- **Description**: Add method to return rankings (not just results) for RRF
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] `search_vector_ranked()` returns (memory, rank, score)
  - [ ] `search_text_ranked()` returns (memory, rank, score)
  - [ ] Existing methods unchanged (backward compatible)
- **Files**:
  - `src/git_notes_memory/index/search_engine.py` - Extend

#### Task 2.3: Extend RecallService

- **Description**: Add hybrid search parameters to RecallService.search()
- **Dependencies**: Task 2.1
- **Acceptance Criteria**:
  - [ ] New parameters: `mode`, `rrf_config`
  - [ ] Default mode: "hybrid" (or configurable via env)
  - [ ] Backward compatible: existing calls work unchanged
  - [ ] Telemetry: search mode in spans
- **Files**:
  - `src/git_notes_memory/recall.py` - Extend search()

#### Task 2.4: Benchmark Validation

- **Description**: Run benchmark harness to measure improvement
- **Dependencies**: Task 2.3
- **Acceptance Criteria**:
  - [ ] Run memory-benchmark-harness
  - [ ] Compare hybrid vs vector-only accuracy
  - [ ] Document results in PROGRESS.md
- **Files**:
  - None (validation only)

### Phase 2 Deliverables

- [ ] `HybridSearchEngine` with RRF fusion
- [ ] Extended `SearchEngine` with ranking methods
- [ ] Extended `RecallService` with hybrid parameters
- [ ] Benchmark comparison: vector-only vs hybrid

### Phase 2 Exit Criteria

- [ ] Hybrid search produces different (better) rankings than vector-only
- [ ] All existing tests pass
- [ ] Benchmark accuracy improved

---

## Phase 3: Entity Indexing

**Goal**: Extract and index named entities for entity-aware search
**Prerequisites**: Phase 1 complete
**Exit Criteria**: Entities indexed during capture, entity boost in search

### Tasks

#### Task 3.1: EntityExtractor Base

- **Description**: Create entity extraction framework with regex fallback
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] `EntityExtractor` class with `extract()` method
  - [ ] Entity types: PERSON, PROJECT, TECHNOLOGY, FILE, ORG
  - [ ] Regex patterns for file paths, URLs, @mentions
  - [ ] Works without spaCy (pure regex mode)
- **Files**:
  - `src/git_notes_memory/retrieval/entity_extractor.py`
  - `tests/retrieval/test_entity_extractor.py`

#### Task 3.2: spaCy Integration

- **Description**: Add spaCy NER for higher-quality entity extraction
- **Dependencies**: Task 3.1
- **Acceptance Criteria**:
  - [ ] Lazy load spaCy model (avoid import-time cost)
  - [ ] Graceful degradation if spaCy unavailable
  - [ ] Map spaCy entity types to our types
  - [ ] Combine spaCy + regex results
- **Files**:
  - `src/git_notes_memory/retrieval/entity_extractor.py` - Extend
  - `pyproject.toml` - Add spacy to [consolidation] extra

#### Task 3.3: Entity Persistence

- **Description**: Store entities and entity-memory mappings in SQLite
- **Dependencies**: Task 1.1 (schema), Task 3.1
- **Acceptance Criteria**:
  - [ ] `EntityStore` class for CRUD operations
  - [ ] Deduplication: same entity text+type = single row
  - [ ] Bulk insert for efficiency
  - [ ] Query by entity text or type
- **Files**:
  - `src/git_notes_memory/retrieval/entity_store.py`
  - `tests/retrieval/test_entity_store.py`

#### Task 3.4: Capture Integration

- **Description**: Extract and store entities during memory capture
- **Dependencies**: Task 3.3
- **Acceptance Criteria**:
  - [ ] `CaptureService.capture()` triggers entity extraction
  - [ ] Entities stored after successful capture
  - [ ] Extraction failure doesn't block capture
  - [ ] Telemetry: entity count per capture
- **Files**:
  - `src/git_notes_memory/capture.py` - Extend

#### Task 3.5: Entity Matcher

- **Description**: Match query entities and boost results
- **Dependencies**: Task 3.3
- **Acceptance Criteria**:
  - [ ] `EntityMatcher` class with `match_query()` method
  - [ ] Extract entities from query
  - [ ] Find memories mentioning matched entities
  - [ ] Return entity boost scores for RRF
- **Files**:
  - `src/git_notes_memory/retrieval/entity_matcher.py`
  - `tests/retrieval/test_entity_matcher.py`

#### Task 3.6: Entity Boost in Hybrid Search

- **Description**: Add entity matching as RRF source
- **Dependencies**: Task 2.1, Task 3.5
- **Acceptance Criteria**:
  - [ ] Entity matcher integrated into HybridSearchEngine
  - [ ] `entity_boost` parameter controls behavior
  - [ ] Entity matches added to RRF fusion
- **Files**:
  - `src/git_notes_memory/index/hybrid_search.py` - Extend

### Phase 3 Deliverables

- [ ] `EntityExtractor` with regex + spaCy
- [ ] `EntityStore` for persistence
- [ ] `EntityMatcher` for query-time matching
- [ ] Entity extraction in capture pipeline
- [ ] Entity boost in hybrid search

### Phase 3 Exit Criteria

- [ ] Entities extracted and stored during capture
- [ ] Entity-specific queries show improved accuracy
- [ ] All tests pass

---

## Phase 4: Temporal Indexing

**Goal**: Parse temporal references and enable date-range filtering
**Prerequisites**: Phase 1 complete
**Exit Criteria**: Temporal queries ("when did we") return date-aware results

### Tasks

#### Task 4.1: TemporalExtractor

- **Description**: Extract and normalize temporal references from content
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] `TemporalExtractor` class with `extract()` method
  - [ ] Parse absolute dates ("December 15, 2025")
  - [ ] Parse relative dates ("last week", "yesterday")
  - [ ] Graceful degradation without dateparser
- **Files**:
  - `src/git_notes_memory/retrieval/temporal_extractor.py`
  - `tests/retrieval/test_temporal_extractor.py`
  - `pyproject.toml` - Add dateparser to [consolidation] extra

#### Task 4.2: Temporal Persistence

- **Description**: Store temporal references in SQLite
- **Dependencies**: Task 1.1 (schema), Task 4.1
- **Acceptance Criteria**:
  - [ ] Store start_date, end_date, granularity
  - [ ] Index on dates for range queries
  - [ ] Bulk insert support
- **Files**:
  - `src/git_notes_memory/retrieval/temporal_store.py`
  - `tests/retrieval/test_temporal_store.py`

#### Task 4.3: Capture Integration

- **Description**: Extract and store temporal refs during capture
- **Dependencies**: Task 4.2
- **Acceptance Criteria**:
  - [ ] Temporal extraction in capture pipeline
  - [ ] Extraction failure doesn't block capture
  - [ ] Telemetry: temporal ref count
- **Files**:
  - `src/git_notes_memory/capture.py` - Extend

#### Task 4.4: Query Temporal Resolution

- **Description**: Resolve temporal expressions in queries
- **Dependencies**: Task 4.1
- **Acceptance Criteria**:
  - [ ] `resolve_query()` method for query-time parsing
  - [ ] Handle "when did we", "last month", etc.
  - [ ] Return date range for filtering
- **Files**:
  - `src/git_notes_memory/retrieval/temporal_extractor.py` - Extend

#### Task 4.5: Date-Range Filtering

- **Description**: Add date_from/date_to parameters to search
- **Dependencies**: Task 4.4
- **Acceptance Criteria**:
  - [ ] `RecallService.search(date_from=, date_to=)` parameters
  - [ ] Filter applied after RRF fusion
  - [ ] Natural language dates resolved automatically
- **Files**:
  - `src/git_notes_memory/recall.py` - Extend
  - `src/git_notes_memory/index/hybrid_search.py` - Extend

### Phase 4 Deliverables

- [ ] `TemporalExtractor` with dateparser
- [ ] Temporal reference storage
- [ ] Query temporal resolution
- [ ] Date-range filtering in search

### Phase 4 Exit Criteria

- [ ] Temporal refs extracted during capture
- [ ] "When did we" queries return chronologically relevant results
- [ ] Date range filters work correctly

---

## Phase 5: Query Expansion

**Goal**: LLM-powered query expansion for better recall
**Prerequisites**: Phase 2 complete
**Exit Criteria**: Ambiguous queries return improved results with expansion

### Tasks

#### Task 5.1: QueryExpander

- **Description**: Use LLMClient to expand queries
- **Dependencies**: None (uses existing LLMClient)
- **Acceptance Criteria**:
  - [ ] `QueryExpander` class with `expand()` method
  - [ ] Uses existing subconsciousness LLMClient
  - [ ] Configurable prompt template
  - [ ] Returns expanded terms, synonyms, entity hints
- **Files**:
  - `src/git_notes_memory/retrieval/query_expander.py`
  - `tests/retrieval/test_query_expander.py`

#### Task 5.2: Expansion Caching

- **Description**: Cache query expansions to avoid repeated LLM calls
- **Dependencies**: Task 5.1
- **Acceptance Criteria**:
  - [ ] LRU cache with configurable TTL
  - [ ] Cache key: normalized query
  - [ ] Telemetry: cache hit rate
- **Files**:
  - `src/git_notes_memory/retrieval/query_expander.py` - Extend

#### Task 5.3: Search Integration

- **Description**: Add `expand_query` parameter to RecallService
- **Dependencies**: Task 5.1
- **Acceptance Criteria**:
  - [ ] `expand_query=True` triggers LLM expansion
  - [ ] Expanded terms used in BM25 search
  - [ ] Default: False (opt-in)
  - [ ] Telemetry: expansion latency
- **Files**:
  - `src/git_notes_memory/recall.py` - Extend
  - `src/git_notes_memory/index/hybrid_search.py` - Extend

#### Task 5.4: Expansion Prompt Tuning

- **Description**: Optimize expansion prompt for memory retrieval
- **Dependencies**: Task 5.3
- **Acceptance Criteria**:
  - [ ] Test different prompt templates
  - [ ] Measure impact on benchmark accuracy
  - [ ] Document optimal prompt
- **Files**:
  - `src/git_notes_memory/retrieval/prompts/` - Prompt templates

### Phase 5 Deliverables

- [ ] `QueryExpander` with LLM integration
- [ ] Expansion caching
- [ ] `expand_query` parameter in search
- [ ] Optimized expansion prompt

### Phase 5 Exit Criteria

- [ ] Query expansion improves recall for ambiguous queries
- [ ] Cache prevents redundant LLM calls
- [ ] Latency within targets (<200ms P95)

---

## Dependency Graph

```
Phase 1: Foundation (no deps)
├── Task 1.1: Schema v5 ────────────────────────────┐
├── Task 1.2: RRF Fusion ───────────┐               │
├── Task 1.3: HybridSearchConfig    │               │
└── Task 1.4: Retrieval scaffold    │               │
                                    │               │
Phase 2: Hybrid Search              │               │
├── Task 2.1: HybridSearchEngine ◄──┘               │
├── Task 2.2: Extend SearchEngine                   │
├── Task 2.3: Extend RecallService ◄─ Task 2.1      │
└── Task 2.4: Benchmark validation                  │
                                                    │
Phase 3: Entity Indexing                            │
├── Task 3.1: EntityExtractor base                  │
├── Task 3.2: spaCy integration ◄─── Task 3.1       │
├── Task 3.3: Entity persistence ◄── Task 1.1 ──────┤
├── Task 3.4: Capture integration ◄─ Task 3.3       │
├── Task 3.5: Entity matcher ◄────── Task 3.3       │
└── Task 3.6: Entity boost ◄──────── Task 2.1, 3.5  │
                                                    │
Phase 4: Temporal Indexing                          │
├── Task 4.1: TemporalExtractor                     │
├── Task 4.2: Temporal persistence ◄─ Task 1.1 ─────┘
├── Task 4.3: Capture integration ◄── Task 4.2
├── Task 4.4: Query resolution ◄───── Task 4.1
└── Task 4.5: Date-range filter ◄──── Task 4.4

Phase 5: Query Expansion
├── Task 5.1: QueryExpander
├── Task 5.2: Expansion caching ◄─── Task 5.1
├── Task 5.3: Search integration ◄── Task 5.1, 2.1
└── Task 5.4: Prompt tuning
```

## Risk Mitigation Tasks

| Risk | Mitigation Task | Phase |
|------|-----------------|-------|
| spaCy model size | Use en_core_web_sm (12MB), document optional install | Phase 3 |
| LLM latency | Implement caching, make opt-in | Phase 5 |
| RRF parameter tuning | Benchmark with multiple k values | Phase 2 |
| Schema migration | Test on copy of production index | Phase 1 |

## Testing Checklist

- [ ] Unit tests for RRF fusion
- [ ] Unit tests for EntityExtractor (regex + spaCy)
- [ ] Unit tests for TemporalExtractor
- [ ] Unit tests for QueryExpander (mock LLM)
- [ ] Integration tests for HybridSearchEngine
- [ ] Integration tests for entity capture pipeline
- [ ] Integration tests for temporal capture pipeline
- [ ] E2E test: benchmark harness regression
- [ ] Performance test: latency at 1K, 10K memories

## Documentation Tasks

- [ ] Update CLAUDE.md with new env vars
- [ ] Update README.md with retrieval section
- [ ] Add retrieval module docstrings
- [ ] Document entity extraction patterns

## Launch Checklist

- [ ] All tests passing (>85% coverage)
- [ ] Schema migration tested on real data
- [ ] Benchmark shows improvement (target: 90%+)
- [ ] Telemetry verified in Grafana
- [ ] Feature flags tested
- [ ] Rollback procedure documented

## Post-Launch

- [ ] Monitor search latency P50/P95
- [ ] Track entity extraction accuracy
- [ ] Gather user feedback on result quality
- [ ] Tune RRF parameters based on real usage
- [ ] Consider entity disambiguation (future)
