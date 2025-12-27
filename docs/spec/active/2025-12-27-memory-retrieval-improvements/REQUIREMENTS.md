---
document_type: requirements
project_id: SPEC-2025-12-27-002
version: 1.0.0
last_updated: 2025-12-27T18:00:00Z
status: draft
---

# Memory Retrieval Performance Improvements - Product Requirements Document

## Executive Summary

This specification defines improvements to the git-notes-memory library's retrieval system to increase benchmark accuracy from 65% to 90%+. The improvements include hybrid search (combining existing BM25 and vector search), entity-aware indexing, temporal query handling, and LLM-powered query expansion. All improvements are additive, maintaining backward compatibility with existing APIs while providing new capabilities for precision recall.

## Problem Statement

### The Problem

The current memory retrieval system achieves 65% accuracy (13/20 correct) on the memory-benchmark-harness validation suite. Seven question types fail completely:

1. **Entity-specific queries**: "What did John say about X?" - Vector search doesn't prioritize named entity matches
2. **Temporal queries**: "When did we decide X?" - No temporal parsing or filtering
3. **Exact term matching**: "What's our policy on ABC?" - Pure semantic search misses keyword relevance
4. **Specificity queries**: Questions requiring precise term matching alongside semantic understanding

### Impact

- **Library users**: Cannot reliably retrieve specific memories, reducing trust and adoption
- **Claude plugin users**: Contextual memory injection has gaps, limiting AI assistant effectiveness
- **Benchmark credibility**: 65% accuracy is below competitive alternatives

### Current State

The codebase has foundational components that are underutilized:
- **FTS5 with BM25**: Already exists in `search_engine.py` (PERF-H-005) but used as fallback, not combined with vector search
- **Vector search**: sqlite-vec KNN search works well for semantic similarity
- **LLM client**: Consolidation module has `LLMClient` for Anthropic/OpenAI/Ollama
- **Schema migrations**: Version 4 infrastructure supports additive changes

The problem is not missing components but missing **orchestration** - combining these capabilities for precision retrieval.

## Goals and Success Criteria

### Primary Goal

Improve retrieval accuracy from 65% to 90%+ on the memory-benchmark-harness while maintaining sub-100ms average latency for typical queries.

### Success Metrics

| Metric | Current | Target | Measurement Method |
|--------|---------|--------|-------------------|
| Benchmark accuracy | 65% (13/20) | 90%+ (18/20) | memory-benchmark-harness validation |
| Entity query recall | ~20% | 85%+ | Entity-specific question subset |
| Temporal query recall | ~10% | 80%+ | Temporal question subset |
| Exact term matching | ~40% | 90%+ | Keyword-critical question subset |
| Average query latency | <50ms | <100ms | P50 latency in telemetry |
| P95 query latency | <100ms | <200ms | P95 latency in telemetry |

### Non-Goals (Explicit Exclusions)

- **Graph-based retrieval**: Not adding full knowledge graph capabilities in v1
- **Summarization during retrieval**: Consolidation handles this; retrieval returns raw memories
- **Multi-modal search**: No image/audio memory support
- **Real-time streaming**: Batch search only
- **Breaking API changes**: All improvements are additive

## User Analysis

### Primary Users

1. **Library Consumers (Python developers)**
   - **Who**: Developers using git-notes-memory as a Python library
   - **Needs**: Accurate, fast memory retrieval for application logic
   - **Context**: Integration into larger applications, benchmarks, testing

2. **Claude Plugin Users (via hooks)**
   - **Who**: Claude Code users with the memory plugin installed
   - **Needs**: Reliable context injection during coding sessions
   - **Context**: Hook-triggered retrieval with tight latency budgets (<10ms hook overhead)

3. **Benchmark Harness**
   - **Who**: Automated validation suite
   - **Needs**: Consistent, measurable retrieval accuracy
   - **Context**: CI/CD validation, performance regression detection

### User Stories

1. **US-001**: As a library consumer, I want to search for memories about a specific person or project so that I can retrieve decisions and context related to that entity.

2. **US-002**: As a library consumer, I want to ask "when did we decide X" and get temporally-relevant results so that I can understand the timeline of decisions.

3. **US-003**: As a library consumer, I want exact term matching to take priority when my query contains specific identifiers so that I don't miss relevant memories.

4. **US-004**: As a library consumer, I want the system to understand my query intent and expand it intelligently so that I get relevant results even when my query is ambiguous.

5. **US-005**: As a Claude plugin user, I want retrieval to be fast enough that it doesn't noticeably slow down my coding session.

6. **US-006**: As a library consumer, I want to configure the balance between speed and accuracy so that I can optimize for my use case.

## Functional Requirements

### Must Have (P0)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | **Hybrid Search (BM25 + Vector)**: Combine existing FTS5 BM25 scores with vector similarity using Reciprocal Rank Fusion (RRF) | Improves exact term matching while preserving semantic understanding | - Given a query with both keywords and semantic meaning, When search is executed, Then results combine BM25 and vector rankings<br>- RRF k parameter configurable (default 60)<br>- Relative weighting configurable (default 0.5/0.5) |
| FR-002 | **Entity-Aware Indexing**: Extract and index named entities (people, projects, technologies, files) from memory content | Enables entity-specific queries to filter or boost results | - Entities extracted on memory insertion<br>- Entity types: PERSON, PROJECT, TECHNOLOGY, FILE, ORG<br>- Entity-to-memory mapping stored in new table<br>- Query-time entity matching boosts relevance |
| FR-003 | **Temporal Indexing**: Parse and normalize temporal references in memories and queries | Enables "when did we" queries and date-range filtering | - Dates extracted from memory content and timestamp<br>- Relative date queries ("last week", "in December") resolved<br>- New `search(..., date_from=, date_to=)` parameters |
| FR-004 | **Query Expansion with LLM**: Use existing LLMClient to expand ambiguous queries before search | Improves recall for underspecified queries | - Optional, disabled by default (opt-in)<br>- Uses existing subconsciousness LLMClient<br>- Configurable expansion prompt<br>- Caches expansions for repeated queries |

### Should Have (P1)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-101 | **Entity Boost Mode**: Query-time option to boost results containing query-mentioned entities | Fine-grained control over entity influence | - `search(..., entity_boost=True)` parameter<br>- Boost factor configurable |
| FR-102 | **Search Mode Selection**: API to select search strategy (vector-only, bm25-only, hybrid) | Allows users to optimize for their use case | - `search(..., mode="hybrid"|"vector"|"bm25")` parameter<br>- Default: "hybrid" |
| FR-103 | **Temporal Reasoning Mode**: LLM-powered answering for complex temporal queries | Handles "when" questions that need reasoning | - `search(..., mode="temporal")` for specialized handling<br>- Returns structured temporal response |
| FR-104 | **Search Telemetry**: Metrics and traces for search operations | Debugging and optimization | - Latency histograms per search component<br>- Entity/temporal match rates<br>- RRF score distributions |

### Nice to Have (P2)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-201 | **Entity Autocomplete**: Suggest entities as user types query | UX improvement for entity discovery | - Return entity suggestions for partial matches |
| FR-202 | **Semantic Entity Linking**: Link entity mentions to canonical forms | Reduces entity fragmentation | - "John", "John Smith", "@johnsmith" → same entity |
| FR-203 | **Hierarchical Entity Search**: Search by entity category | Browse memories by entity type | - `search(entity_type="PERSON")` filter |

## Non-Functional Requirements

### Performance

- **P50 latency**: <100ms for hybrid search (vector + BM25 + entity boost)
- **P95 latency**: <200ms for complex queries with LLM expansion
- **Memory overhead**: <50MB additional for entity index on 10K memories
- **Index build time**: <5ms per memory for entity/temporal extraction

### Security

- Entity extraction must not leak sensitive data (PII filtered per existing security subsystem)
- LLM query expansion must not include raw memory content in prompts

### Scalability

- Index size linear with memory count (no exponential growth)
- Entity index should support 100K+ entities efficiently

### Reliability

- Graceful degradation: if entity extraction fails, fall back to vector-only
- Graceful degradation: if LLM unavailable, skip query expansion
- All new features behind feature flags for rollback

### Maintainability

- New schema version (v5) with forward migration
- All new tables follow existing naming conventions
- Comprehensive test coverage (>85%)

## Technical Constraints

- **Python 3.11+**: Required by existing codebase
- **SQLite + sqlite-vec**: Must use existing database, no new database dependencies
- **Optional dependencies**: spaCy/dateparser added to `[consolidation]` extra per user preference
- **LLM providers**: Use existing `LLMClient` (Anthropic, OpenAI, Ollama)
- **Backward compatibility**: Existing `recall.search()` API unchanged; new parameters optional

## Dependencies

### Internal Dependencies

- `git_notes_memory.index` - Search engine, schema manager
- `git_notes_memory.embedding` - Embedding service
- `git_notes_memory.subconsciousness.llm_client` - LLM integration
- `git_notes_memory.security` - Secrets filtering for entity extraction

### External Dependencies (New)

| Package | Purpose | Extra |
|---------|---------|-------|
| `spacy>=3.7` | Named entity recognition | `[consolidation]` |
| `en_core_web_sm` | spaCy model (lightweight) | Manual install |
| `dateparser>=1.2` | Natural language date parsing | `[consolidation]` |
| `rank_bm25>=0.2` | BM25 implementation (if needed beyond FTS5) | Optional |

### Existing Dependencies (Already Available)

- `sqlite-vec` - Vector similarity search
- `sentence-transformers` - Embedding generation
- FTS5 - Built into SQLite, already configured

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| spaCy model size (100MB+) | High | Medium | Use `en_core_web_sm` (12MB); provide instructions for minimal install |
| LLM latency for query expansion | Medium | Medium | Cache expansions; make opt-in; async prefetch option |
| Entity extraction accuracy | Medium | Medium | Supplement spaCy with regex patterns for technical entities |
| RRF parameter tuning | Medium | Low | Provide sensible defaults; expose config for power users |
| Schema migration complexity | Low | High | Test migration thoroughly; provide rollback script |
| Temporal parsing edge cases | Medium | Low | Fall back to timestamp-only filtering on parse failure |

## Open Questions

- [ ] Should entity extraction run synchronously during capture or in background?
- [ ] What's the optimal RRF k parameter for our use case? (Research suggests 60)
- [ ] Should we support spaCy transformer models for higher accuracy? (Much larger)
- [ ] How to handle entity disambiguation? (e.g., multiple "John"s)

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| BM25 | Best Matching 25 - probabilistic ranking function for keyword search |
| RRF | Reciprocal Rank Fusion - algorithm to combine rankings from multiple sources |
| NER | Named Entity Recognition - extracting entities (people, places, orgs) from text |
| FTS5 | Full-Text Search 5 - SQLite's built-in full-text search engine |
| sqlite-vec | SQLite extension for vector similarity search |

### References

- [sqlite-vec hybrid search](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html)
- [Reciprocal Rank Fusion paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [spaCy NER documentation](https://spacy.io/usage/linguistic-features#named-entities)
- [dateparser documentation](https://dateparser.readthedocs.io/)
- [Existing FTS5 implementation](src/git_notes_memory/index/search_engine.py:163-236)

### Benchmark Baseline Data

```
Validation run: 2025-12-27
Adapter: git-notes-memory v1.0.0
Results: 13/20 correct (65%)

Failed question types:
- Entity-specific: 4/5 failed
- Temporal: 3/3 failed
- Exact term: 2/4 failed
- Complex reasoning: 2/8 failed
```
