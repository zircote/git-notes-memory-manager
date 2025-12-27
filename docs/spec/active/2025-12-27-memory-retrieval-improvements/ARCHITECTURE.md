---
document_type: architecture
project_id: SPEC-2025-12-27-002
version: 1.0.0
last_updated: 2025-12-27T18:00:00Z
status: draft
---

# Memory Retrieval Performance Improvements - Technical Architecture

## System Overview

This architecture extends the existing git-notes-memory retrieval system with four new capabilities: hybrid search, entity indexing, temporal indexing, and query expansion. The design follows the established patterns of the codebase (service layer, schema migrations, observability integration) while adding new components that compose with existing infrastructure.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              RecallService (Extended)                            │
│  ┌─────────────┐   ┌─────────────────┐   ┌──────────────┐   ┌───────────────┐  │
│  │ Query       │──▶│  Query          │──▶│ Retrieval    │──▶│ Result        │  │
│  │ Parser      │   │  Expander       │   │ Orchestrator │   │ Merger        │  │
│  └─────────────┘   │  (LLM, opt-in)  │   └──────────────┘   └───────────────┘  │
│                    └─────────────────┘          │                   ▲          │
│                                                 │                   │          │
│                    ┌────────────────────────────┼───────────────────┘          │
│                    ▼                            ▼                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         Search Strategy Layer                            │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │   │
│  │  │ Vector       │  │ BM25         │  │ Entity       │  │ Temporal    │  │   │
│  │  │ Search       │  │ Search       │  │ Matcher      │  │ Filter      │  │   │
│  │  │ (existing)   │  │ (existing)   │  │ (NEW)        │  │ (NEW)       │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                    │                            │                               │
│                    ▼                            ▼                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         RRF Fusion Engine (NEW)                          │   │
│  │  - Combines rankings from Vector, BM25, Entity                           │   │
│  │  - Configurable k parameter and weights                                  │   │
│  │  - Observability: latency, score distributions                           │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              Index Layer (Extended)                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ memories        │  │ vec_memories    │  │ memories_fts    │                  │
│  │ (existing)      │  │ (existing)      │  │ (existing)      │                  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                  │
│                                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ entities        │  │ memory_entities │  │ temporal_refs   │                  │
│  │ (NEW)           │  │ (NEW)           │  │ (NEW)           │                  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Additive Extension**: All new components are additive; no changes to existing APIs
2. **Composition over Modification**: New strategies compose with existing search engines
3. **Graceful Degradation**: Each new capability degrades gracefully if dependencies unavailable
4. **Schema Migration**: New tables added via migration v5, following existing pattern
5. **Opt-in LLM**: Query expansion requires explicit enablement to avoid latency impact

## Component Design

### Component 1: HybridSearchEngine

- **Purpose**: Orchestrate multiple search strategies and combine results using RRF
- **Responsibilities**:
  - Execute vector and BM25 searches in parallel
  - Apply entity and temporal boosting/filtering
  - Combine rankings using Reciprocal Rank Fusion
- **Interfaces**:
  - `search(query, k, mode, entity_boost, date_from, date_to) -> List[MemoryResult]`
- **Dependencies**: SearchEngine (existing), EntityMatcher, TemporalFilter
- **Technology**: Python, asyncio for parallel execution
- **Location**: `src/git_notes_memory/index/hybrid_search.py`

```python
@dataclass(frozen=True)
class HybridSearchConfig:
    """Configuration for hybrid search behavior."""
    rrf_k: int = 60  # RRF constant (higher = less aggressive rank fusion)
    vector_weight: float = 0.5  # Weight for vector search (0-1)
    bm25_weight: float = 0.5  # Weight for BM25 search (0-1)
    entity_boost: float = 1.5  # Multiplier for entity matches
    enable_parallel: bool = True  # Parallel execution of strategies
```

### Component 2: EntityExtractor

- **Purpose**: Extract named entities from memory content during ingestion
- **Responsibilities**:
  - Parse memory content for entities (PERSON, PROJECT, TECHNOLOGY, FILE, ORG)
  - Store entity-memory mappings
  - Provide query-time entity matching
- **Interfaces**:
  - `extract(content: str) -> List[Entity]`
  - `match_query(query: str) -> List[Entity]`
- **Dependencies**: spaCy (optional), regex fallbacks
- **Technology**: spaCy `en_core_web_sm`, custom regex patterns
- **Location**: `src/git_notes_memory/retrieval/entity_extractor.py`

```python
class Entity:
    """Extracted entity with type and span information."""
    text: str  # Normalized entity text
    type: EntityType  # PERSON, PROJECT, TECHNOLOGY, FILE, ORG
    start: int  # Character offset in source
    end: int  # Character offset end
    confidence: float  # Extraction confidence (0-1)
```

**Entity Detection Strategy**:
1. **spaCy NER** (if available): PERSON, ORG, GPE, PRODUCT
2. **Regex patterns** (always): File paths, URLs, code references, @mentions
3. **Keyword lists** (configurable): Technology names, project identifiers

### Component 3: TemporalExtractor

- **Purpose**: Parse and normalize temporal references in content and queries
- **Responsibilities**:
  - Extract dates from memory content
  - Resolve relative dates ("last week", "in December")
  - Provide date-range filtering
- **Interfaces**:
  - `extract(content: str) -> List[TemporalRef]`
  - `resolve_query(query: str, reference_date: datetime) -> DateRange`
- **Dependencies**: dateparser
- **Technology**: dateparser library, custom parsing
- **Location**: `src/git_notes_memory/retrieval/temporal_extractor.py`

```python
@dataclass(frozen=True)
class TemporalRef:
    """Extracted temporal reference with normalized dates."""
    text: str  # Original text ("last week", "December 15th")
    start_date: datetime | None  # Normalized start
    end_date: datetime | None  # Normalized end (for ranges)
    granularity: str  # "day", "week", "month", "year"
    confidence: float  # Parsing confidence
```

### Component 4: QueryExpander

- **Purpose**: Use LLM to expand ambiguous queries for better recall
- **Responsibilities**:
  - Detect when expansion is beneficial
  - Generate expanded query terms using LLM
  - Cache expansions for repeated queries
- **Interfaces**:
  - `expand(query: str, context: Optional[str]) -> ExpandedQuery`
- **Dependencies**: LLMClient (existing subconsciousness module)
- **Technology**: Existing LLM infrastructure (Anthropic/OpenAI/Ollama)
- **Location**: `src/git_notes_memory/retrieval/query_expander.py`

```python
@dataclass(frozen=True)
class ExpandedQuery:
    """Query with LLM-generated expansions."""
    original: str
    expanded_terms: tuple[str, ...]  # Additional search terms
    synonyms: tuple[str, ...]  # Alternative phrasings
    entities_mentioned: tuple[str, ...]  # Extracted entity hints
    intent: str  # Detected query intent
```

### Component 5: RRFFusionEngine

- **Purpose**: Combine rankings from multiple search strategies
- **Responsibilities**:
  - Implement Reciprocal Rank Fusion algorithm
  - Support weighted combination of sources
  - Provide score normalization
- **Interfaces**:
  - `fuse(rankings: List[List[MemoryResult]], weights: List[float]) -> List[MemoryResult]`
- **Dependencies**: None (pure algorithm)
- **Location**: `src/git_notes_memory/index/rrf_fusion.py`

**RRF Algorithm**:
```
RRF_score(d) = Σ (weight_i / (k + rank_i(d)))
```
Where:
- `d` is a document (memory)
- `k` is the fusion constant (default 60)
- `rank_i(d)` is the rank of d in source i
- `weight_i` is the weight of source i

## Data Design

### Data Models

#### New Tables (Schema v5)

```sql
-- Entity registry: canonical entities across all memories
CREATE TABLE entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,           -- Normalized entity text
    type TEXT NOT NULL,           -- PERSON, PROJECT, TECHNOLOGY, FILE, ORG
    canonical_form TEXT,          -- Canonical version (for linking)
    first_seen TEXT NOT NULL,     -- ISO timestamp
    mention_count INTEGER DEFAULT 1,
    UNIQUE(text, type)
);
CREATE INDEX idx_entities_text ON entities(text);
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_canonical ON entities(canonical_form);

-- Entity-to-memory mapping (many-to-many)
CREATE TABLE memory_entities (
    memory_id TEXT NOT NULL REFERENCES memories(id),
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    span_start INTEGER,           -- Character offset
    span_end INTEGER,             -- Character offset
    confidence REAL DEFAULT 1.0,
    PRIMARY KEY (memory_id, entity_id, span_start)
);
CREATE INDEX idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX idx_memory_entities_entity ON memory_entities(entity_id);

-- Temporal references in memories
CREATE TABLE temporal_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES memories(id),
    text TEXT NOT NULL,           -- Original text ("last week")
    start_date TEXT,              -- ISO date (nullable for fuzzy refs)
    end_date TEXT,                -- ISO date (nullable for points)
    granularity TEXT,             -- day, week, month, year
    span_start INTEGER,           -- Character offset
    span_end INTEGER,             -- Character offset
    confidence REAL DEFAULT 1.0
);
CREATE INDEX idx_temporal_refs_memory ON temporal_refs(memory_id);
CREATE INDEX idx_temporal_refs_dates ON temporal_refs(start_date, end_date);
```

### Data Flow

```
CAPTURE FLOW (Extended):
┌──────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────────┐
│ Memory   │───▶│ Entity      │───▶│ Temporal    │───▶│ Index        │
│ Content  │    │ Extractor   │    │ Extractor   │    │ Service      │
└──────────┘    └─────────────┘    └─────────────┘    └──────────────┘
                     │                   │                   │
                     ▼                   ▼                   ▼
              ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
              │ entities     │    │ temporal_refs│    │ memories     │
              │ memory_ents  │    │              │    │ vec_memories │
              └──────────────┘    └──────────────┘    └──────────────┘

SEARCH FLOW (Hybrid):
┌──────────┐    ┌─────────────┐    ┌─────────────────────────────────────┐
│ Query    │───▶│ Query       │───▶│ Parallel Strategy Execution         │
│          │    │ Parser      │    │ ┌─────────┬─────────┬─────────────┐ │
└──────────┘    │ + Expander  │    │ │ Vector  │ BM25    │ Entity      │ │
                │ (optional)  │    │ │ Search  │ Search  │ Matcher     │ │
                └─────────────┘    │ └─────────┴─────────┴─────────────┘ │
                                   └─────────────────────────────────────┘
                                                    │
                                                    ▼
                                   ┌─────────────────────────────────────┐
                                   │ RRF Fusion + Temporal Filter        │
                                   └─────────────────────────────────────┘
                                                    │
                                                    ▼
                                   ┌─────────────────────────────────────┐
                                   │ Ranked Results                       │
                                   └─────────────────────────────────────┘
```

### Storage Strategy

- **Primary Store**: SQLite (existing index.db)
- **Entity Index**: New tables in same database
- **Temporal Index**: New table in same database
- **Query Expansion Cache**: LRU cache in memory (TTL-based eviction)
- **No new files**: All data in existing index.db

## API Design

### API Overview

- **Style**: Python API (no REST/GraphQL)
- **Backward Compatible**: All new parameters are optional with sensible defaults
- **Configuration**: Environment variables + runtime config objects

### Extended RecallService API

```python
class RecallService:
    """Extended recall service with hybrid search capabilities."""

    def search(
        self,
        query: str,
        k: int = 10,
        namespace: str | None = None,
        spec: str | None = None,
        domain: str | None = None,
        min_similarity: float | None = None,
        # NEW: Hybrid search parameters
        mode: Literal["hybrid", "vector", "bm25"] = "hybrid",
        entity_boost: bool = True,
        date_from: datetime | str | None = None,
        date_to: datetime | str | None = None,
        expand_query: bool = False,  # Opt-in LLM expansion
        rrf_config: HybridSearchConfig | None = None,
    ) -> list[MemoryResult]:
        """Search memories with hybrid retrieval.

        Args:
            query: Search query (natural language)
            k: Maximum results to return
            namespace: Filter by namespace
            spec: Filter by spec
            domain: Filter by domain ("user" or "project")
            min_similarity: Minimum similarity threshold (vector mode)
            mode: Search strategy ("hybrid", "vector", "bm25")
            entity_boost: Boost results matching query entities
            date_from: Filter to memories after this date
            date_to: Filter to memories before this date
            expand_query: Use LLM to expand query (adds latency)
            rrf_config: Custom RRF configuration

        Returns:
            List of MemoryResult with combined relevance scores
        """
```

### New Configuration Classes

```python
@dataclass(frozen=True)
class HybridSearchConfig:
    """Configuration for hybrid search behavior."""
    rrf_k: int = 60
    vector_weight: float = 0.5
    bm25_weight: float = 0.5
    entity_boost_factor: float = 1.5
    enable_parallel: bool = True
    expansion_cache_ttl: int = 3600  # seconds


@dataclass(frozen=True)
class EntityExtractorConfig:
    """Configuration for entity extraction."""
    use_spacy: bool = True  # Fall back to regex if False/unavailable
    spacy_model: str = "en_core_web_sm"
    custom_patterns: dict[str, list[str]] = field(default_factory=dict)
    min_confidence: float = 0.5


@dataclass(frozen=True)
class QueryExpansionConfig:
    """Configuration for LLM query expansion."""
    enabled: bool = False  # Opt-in
    llm_provider: str = "anthropic"  # or "openai", "ollama"
    model: str | None = None  # Uses provider default
    max_expansions: int = 5
    cache_enabled: bool = True
```

## Integration Points

### Internal Integrations

| System | Integration Type | Purpose |
|--------|-----------------|---------|
| IndexService | Direct call | Access existing search methods |
| SearchEngine | Direct call | Existing vector/text search |
| EmbeddingService | Direct call | Query embedding generation |
| LLMClient | Direct call | Query expansion (subconsciousness) |
| SchemaManager | Direct call | Schema v5 migration |
| MetricsCollector | Direct call | Telemetry |

### External Integrations

| Service | Integration Type | Purpose |
|---------|-----------------|---------|
| spaCy | Library import | NER for entity extraction |
| dateparser | Library import | Temporal parsing |

## Security Design

### Entity Extraction Security

- Entity extraction runs AFTER security filtering (secrets, PII)
- Extracted entities are from already-sanitized content
- No raw content in entity tables (just normalized text)

### LLM Query Expansion Security

- Queries sent to LLM contain no memory content
- Only the query text is sent
- No PII leakage risk (queries are user-provided)

### Data Protection

- All new tables follow existing access patterns
- No additional encryption needed (same security model as existing tables)

## Performance Considerations

### Expected Load

- **Queries per session**: 10-100 (typical Claude session)
- **Concurrent queries**: 1 (single-threaded Claude)
- **Memory count**: 100-10,000 (typical repo)
- **Entity count**: 10-100× memory count

### Performance Targets

| Metric | Target | Strategy |
|--------|--------|----------|
| Vector search | <30ms | Existing (no change) |
| BM25 search | <10ms | FTS5 (existing) |
| Entity lookup | <5ms | Indexed by entity_id |
| RRF fusion | <1ms | In-memory algorithm |
| Total hybrid | <50ms | Parallel execution |
| With expansion | <200ms | LLM latency dominated |

### Optimization Strategies

1. **Parallel Execution**: Vector and BM25 searches run concurrently
2. **Early Termination**: Stop BM25 at k×3 results for fusion
3. **Entity Index**: B-tree index on entity text for fast lookup
4. **Expansion Cache**: LRU cache with TTL for repeated queries
5. **Lazy spaCy Load**: Load spaCy model on first use, not import

## Reliability & Operations

### Failure Modes

| Failure | Impact | Recovery |
|---------|--------|----------|
| spaCy unavailable | Reduced entity accuracy | Fall back to regex patterns |
| dateparser fails | No temporal filtering | Use timestamp-only |
| LLM unavailable | No query expansion | Skip expansion, use raw query |
| BM25 search fails | Reduced precision | Fall back to vector-only |
| Entity table missing | No entity boost | Skip entity matching |

### Monitoring & Alerting

New metrics (via existing observability):
- `retrieval_search_latency_ms{strategy=hybrid|vector|bm25}`
- `retrieval_entity_matches_total`
- `retrieval_temporal_filters_total`
- `retrieval_query_expansions_total`
- `retrieval_rrf_fusion_latency_ms`

### Graceful Degradation

```python
# Degradation cascade
if spacy_available:
    entities = spacy_extract(content)
else:
    entities = regex_extract(content)  # Always available

if dateparser_available:
    temporal = dateparser_extract(query)
else:
    temporal = timestamp_only(query)  # Parse ISO dates

if llm_available and expand_query:
    query = llm_expand(query)
# else: use original query (always works)
```

## Testing Strategy

### Unit Testing

- Entity extraction: Test all entity types, edge cases
- Temporal parsing: Test relative dates, ranges, edge cases
- RRF fusion: Test ranking combination, edge cases
- Query expansion: Mock LLM responses

### Integration Testing

- Hybrid search end-to-end
- Schema migration v4 → v5
- Entity indexing during capture
- Benchmark harness regression

### Performance Testing

- Latency benchmarks: 1K, 10K, 100K memories
- Entity index size vs memory count
- Query expansion cache hit rates

## Deployment Considerations

### Environment Requirements

- Python 3.11+
- SQLite with FTS5 support (standard)
- Optional: spaCy model download (~12MB)

### Configuration Management

Environment variables (new):
```bash
# Feature flags
RETRIEVAL_HYBRID_ENABLED=true
RETRIEVAL_ENTITY_EXTRACTION_ENABLED=true
RETRIEVAL_TEMPORAL_ENABLED=true
RETRIEVAL_QUERY_EXPANSION_ENABLED=false  # Opt-in

# Tuning
RETRIEVAL_RRF_K=60
RETRIEVAL_VECTOR_WEIGHT=0.5
RETRIEVAL_BM25_WEIGHT=0.5
RETRIEVAL_ENTITY_BOOST=1.5

# spaCy
RETRIEVAL_SPACY_MODEL=en_core_web_sm
```

### Migration Path

1. Deploy v5 schema migration (additive, safe)
2. Enable entity extraction (captures only)
3. Backfill entities for existing memories (optional, background)
4. Enable hybrid search (default mode)
5. Enable query expansion (opt-in)

### Rollback Plan

- Schema v5 tables can coexist with v4 (additive)
- Set `RETRIEVAL_HYBRID_ENABLED=false` to disable
- Existing `mode="vector"` parameter as escape hatch

## Future Considerations

1. **Graph-based retrieval**: Entity relationships for multi-hop queries
2. **Cross-memory reasoning**: LLM synthesis of related memories
3. **Active learning**: User feedback to improve extraction/ranking
4. **Distributed indexing**: Multi-repo federation
5. **Streaming search**: Progressive result delivery
