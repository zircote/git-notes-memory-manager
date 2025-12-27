# Memory Consolidation: Architecture

**Spec ID:** SPEC-2025-12-27-001
**Status:** Draft

## Overview

Memory consolidation extends the existing `subconsciousness` module with cognitive-inspired memory lifecycle management. The architecture follows the established service patterns and integrates with existing infrastructure.

## System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                       Claude Code Session                        │
├─────────────────────────────────────────────────────────────────┤
│  SessionStart Hook                                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  SessionStartSummaryInjector                             │   │
│  │  - Injects consolidated summaries to additionalContext    │   │
│  │  - Replaces existing blocks (idempotent)                 │   │
│  └──────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│  /memory:recall Command                                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  RecallService (extended)                                 │   │
│  │  - Tier-filtered retrieval                               │   │
│  │  - Activation tracking                                   │   │
│  │  - Summary inclusion                                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  ReasonedRecallService                                    │   │
│  │  - Temporal reference resolution                         │   │
│  │  - LLM-powered reasoning                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Consolidation Service                         │
│                    (Background Process)                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────┐   ┌─────────┐   ┌───────────┐   ┌─────────────┐     │
│  │ SCAN  │──▶│ CLUSTER │──▶│ SUMMARIZE │──▶│ SUPERSESSION│     │
│  └───────┘   └─────────┘   └───────────┘   └─────────────┘     │
│       │                                           │              │
│       ▼                                           ▼              │
│  ┌───────┐                                  ┌─────────┐         │
│  │ TIER  │◀─────────────────────────────────│ PERSIST │         │
│  └───────┘                                  └─────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Storage Layer                             │
├────────────────────────┬────────────────────────────────────────┤
│     Git Notes          │           SQLite Index                  │
│  ┌──────────────────┐  │  ┌────────────────────────────────┐   │
│  │ refs/notes/mem/  │  │  │ memories table                 │   │
│  │ (unchanged)      │  │  │ + tier column                  │   │
│  ├──────────────────┤  │  │ + activation_count column      │   │
│  │ refs/notes/      │  │  │ + last_accessed column         │   │
│  │   mem-meta/      │  │  ├────────────────────────────────┤   │
│  ├──────────────────┤  │  │ mem_summaries table            │   │
│  │ refs/notes/      │  │  ├────────────────────────────────┤   │
│  │   mem-summaries/ │  │  │ mem_edges table                │   │
│  ├──────────────────┤  │  ├────────────────────────────────┤   │
│  │ refs/notes/      │  │  │ consolidation_runs table       │   │
│  │   mem-edges/     │  │  └────────────────────────────────┘   │
│  ├──────────────────┤  │                                        │
│  │ refs/notes/      │  │                                        │
│  │   mem-runs/      │  │                                        │
│  └──────────────────┘  │                                        │
└────────────────────────┴────────────────────────────────────────┘
```

## Component Architecture

### New Components

```
src/git_notes_memory/subconsciousness/
├── models.py                  # EXTEND: New consolidation models
├── config.py                  # EXTEND: Consolidation config params
├── llm_client.py              # REUSE: Existing LLM infrastructure
├── consolidation/
│   ├── __init__.py
│   ├── service.py             # ConsolidationService (pipeline orchestrator)
│   ├── retention.py           # RetentionScore calculation
│   ├── clustering.py          # Semantic clustering with sklearn
│   ├── prompts.py             # LLM prompts for summarization/supersession
│   ├── stores/
│   │   ├── __init__.py
│   │   ├── metadata_store.py  # MemoryMetadata CRUD
│   │   ├── summary_store.py   # MemorySummary CRUD
│   │   ├── edge_store.py      # MemoryEdge CRUD
│   │   └── run_store.py       # ConsolidationResult logging
│   └── hook.py                # Background trigger hook
├── reasoning/
│   ├── __init__.py
│   ├── service.py             # ReasonedRecallService
│   ├── temporal.py            # Temporal reference patterns and resolution
│   └── prompts.py             # Reasoning prompts
└── session/
    ├── __init__.py
    └── summary_injector.py    # SessionStartSummaryInjector
```

### Model Additions (`models.py`)

```python
# Memory Tier Enum
class MemoryTier(str, Enum):
    HOT = "hot"       # Active, high retention
    WARM = "warm"     # Summaries, moderate retention
    COLD = "cold"     # Historical, low retention
    ARCHIVED = "archived"  # Superseded, minimal retention

# Retention Score (follows CaptureConfidence pattern)
@dataclass(frozen=True)
class RetentionScore:
    overall: float      # 0.0-1.0, weighted combination
    recency: float      # Time-based decay factor
    activation: float   # Retrieval frequency factor
    importance: float   # Namespace-based weight
    relevance: float | None = None  # Contextual, computed on-demand

# Memory Metadata (stored separately from Memory)
@dataclass(frozen=True)
class MemoryMetadata:
    memory_id: str
    tier: MemoryTier
    activation_count: int
    last_accessed: datetime | None
    retention: RetentionScore
    superseded_by: str | None
    consolidated_into: str | None
    created_at: datetime
    updated_at: datetime

# Summary Components
@dataclass(frozen=True)
class SummaryDecision:
    decision: str
    rationale: str
    outcome: str | None
    confidence: str  # high|medium|low

@dataclass(frozen=True)
class SupersededFact:
    original_fact: str
    superseded_by: str
    source_memory_id: str

# Consolidated Summary
@dataclass(frozen=True)
class MemorySummary:
    id: str  # sum_<ulid>
    namespace: str
    created_at: datetime
    temporal_range: tuple[datetime, datetime]
    summary: str
    key_facts: tuple[str, ...]
    decisions: tuple[SummaryDecision, ...]
    superseded_facts: tuple[SupersededFact, ...]
    source_memory_ids: tuple[str, ...]
    consolidation_run_id: str
    confidence: CaptureConfidence
    tier: MemoryTier = MemoryTier.WARM
    activation_count: int = 0

# Memory Edges
class EdgeType(str, Enum):
    SUPERSEDES = "supersedes"
    CONSOLIDATES = "consolidates"
    REFERENCES = "references"

@dataclass(frozen=True)
class MemoryEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float
    reason: str | None
    created_at: datetime
    consolidation_run_id: str | None

# Consolidation Pipeline
class ConsolidationPhase(str, Enum):
    SCAN = "scan"
    CLUSTER = "cluster"
    SUMMARIZE = "summarize"
    SUPERSESSION = "supersession"
    TIER = "tier"
    PERSIST = "persist"
    COMPLETED = "completed"

@dataclass(frozen=True)
class TierTransition:
    memory_id: str
    from_tier: MemoryTier
    to_tier: MemoryTier
    reason: str
    retention_score: float

@dataclass(frozen=True)
class ConsolidationResult:
    run_id: str
    started_at: datetime
    completed_at: datetime | None
    phase: ConsolidationPhase
    memories_processed: int
    clusters_found: int
    summaries_created: int
    supersessions_detected: int
    tier_transitions: tuple[TierTransition, ...]
    errors: tuple[str, ...]

# Reasoning Models
@dataclass(frozen=True)
class TemporalReference:
    original_text: str          # "yesterday"
    memory_timestamp: datetime  # When memory was created
    resolved_date: datetime     # Computed absolute date
    confidence: float

@dataclass(frozen=True)
class ReasonedAnswer:
    answer: str
    confidence: float
    reasoning: str
    temporal_resolutions: tuple[TemporalReference, ...]
    source_memories: tuple[MemoryResult, ...]
    requires_inference: bool
```

### Config Extensions (`config.py`)

```python
# New defaults
DEFAULT_RETENTION_HALF_LIFE_DAYS = 30.0
DEFAULT_ACTIVATION_BOOST = 0.1
DEFAULT_MIN_CLUSTER_SIZE = 3
DEFAULT_MAX_CLUSTER_SIZE = 20
DEFAULT_CONSOLIDATION_BATCH_SIZE = 50
DEFAULT_CONSOLIDATION_INTERVAL_HOURS = 24

# Tier thresholds
DEFAULT_HOT_THRESHOLD = 0.6
DEFAULT_WARM_THRESHOLD = 0.3

# SessionStart summary config
DEFAULT_SUMMARIES_MAX = 10
DEFAULT_SUMMARIES_TOKEN_BUDGET = 2000
DEFAULT_SUMMARIES_MIN_CONFIDENCE = 0.7
DEFAULT_SUMMARIES_PRIORITIZE = "relevance"

# Environment variables
MEMORY_CONSOLIDATION_LLM_PROVIDER      # openai|lmstudio|ollama
MEMORY_CONSOLIDATION_LLM_MODEL         # gpt-4o-mini
MEMORY_CONSOLIDATION_LLM_BASE_URL      # For LM Studio

HOOK_SESSION_START_SUMMARIES_ENABLED   # true/false
HOOK_SESSION_START_SUMMARIES_MAX       # 10
HOOK_SESSION_START_SUMMARIES_TOKEN_BUDGET  # 2000
HOOK_SESSION_START_SUMMARIES_MIN_CONFIDENCE  # 0.7
HOOK_SESSION_START_SUMMARIES_PRIORITIZE     # relevance|recency|activation

HOOK_CONSOLIDATION_ENABLED             # true/false
HOOK_CONSOLIDATION_IDLE_MINUTES        # 30
HOOK_CONSOLIDATION_MEMORY_THRESHOLD    # 50
HOOK_CONSOLIDATION_MIN_INTERVAL_HOURS  # 24
```

## Retention Score Algorithm

```python
def compute_retention_score(
    memory: Memory,
    metadata: MemoryMetadata,
    config: RetentionConfig,
    now: datetime,
) -> RetentionScore:
    # Recency: exponential decay
    age_days = (now - memory.timestamp).total_seconds() / 86400
    access_age = (now - metadata.last_accessed).total_seconds() / 86400 \
        if metadata.last_accessed else age_days
    effective_age = min(age_days, access_age)
    recency = math.exp(-effective_age / config.half_life_days * math.log(2))

    # Activation: log scale with diminishing returns
    activation = min(1.0, math.log1p(metadata.activation_count) / math.log1p(20))

    # Importance: by namespace
    importance = NAMESPACE_IMPORTANCE.get(memory.namespace, 0.5)

    # Combined score
    overall = (
        config.recency_weight * recency +
        config.activation_weight * activation +
        config.importance_weight * importance
    )

    # Superseded penalty
    if metadata.superseded_by:
        overall *= 0.2

    return RetentionScore(
        overall=min(1.0, max(0.0, overall)),
        recency=recency,
        activation=activation,
        importance=importance,
    )

# Namespace importance weights
NAMESPACE_IMPORTANCE = {
    "decisions": 1.0,
    "learnings": 0.9,
    "patterns": 0.85,
    "retrospective": 0.8,
    "inception": 0.7,
    "blockers": 0.7,
    "research": 0.6,
    "elicitation": 0.6,
    "progress": 0.5,
    "reviews": 0.5,
}
```

## Semantic Clustering

Clusters by embedding similarity only - time is NOT a factor:

```python
async def cluster_memories(
    memories: list[Memory],
    embeddings: dict[str, np.ndarray],
    config: SubconsciousnessConfig,
) -> list[MemoryCluster]:
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics.pairwise import cosine_distances

    # Build embedding matrix
    ids = list(embeddings.keys())
    X = np.array([embeddings[id] for id in ids])

    # Cluster using cosine distance
    distance_matrix = cosine_distances(X)
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1 - config.consolidation_threshold,
        metric="precomputed",
        linkage="average",
    )
    labels = clustering.fit_predict(distance_matrix)

    # Group by cluster label
    clusters: dict[int, list[str]] = {}
    for idx, label in enumerate(labels):
        clusters.setdefault(label, []).append(ids[idx])

    # Filter by size constraints
    return [
        MemoryCluster(memory_ids=tuple(ids), label=label)
        for label, ids in clusters.items()
        if config.min_cluster_size <= len(ids) <= config.max_cluster_size
    ]
```

## LLM Prompts

### Summarization Prompt

```python
SUMMARY_SYSTEM_PROMPT = """You are a memory consolidation agent. Create a concise summary of related memories from a software project.

Guidelines:
- Preserve key decisions and their rationale
- Note outcomes and lessons learned
- Identify superseded or outdated information
- Be concise but complete
- Focus on actionable knowledge

Output JSON:
{
  "summary": "2-3 sentence summary",
  "key_facts": ["fact1", "fact2"],
  "decisions": [{"decision": "...", "rationale": "...", "outcome": "...", "confidence": "high|medium|low"}],
  "superseded_facts": [{"original_fact": "...", "superseded_by": "...", "source_memory_id": "..."}]
}
"""
```

### Supersession Detection Prompt

```python
SUPERSESSION_SYSTEM_PROMPT = """Analyze two memories to determine if the newer supersedes the older.

Supersession means the newer memory:
1. Directly contradicts the older (decision changed)
2. Replaces the older (updated version of same info)
3. Makes the older obsolete (topic no longer relevant)

Be conservative - only mark as superseded with clear evidence.

Output JSON:
{
  "supersedes": true|false,
  "confidence": "high|medium|low",
  "reason": "explanation if supersedes is true, null otherwise"
}
"""
```

### Temporal Reasoning Prompt

```python
REASONING_SYSTEM_PROMPT = """You are a memory reasoning assistant. Answer questions by reasoning over retrieved memories.

CRITICAL: Pay attention to TIMESTAMPS. When memories contain relative temporal references like "yesterday", "last week", resolve them relative to the memory's recorded timestamp.

Example:
- Memory recorded: 2023-05-08 14:30:00
- Memory content: "Caroline said she went to the support group yesterday"
- Resolved: "yesterday" relative to 2023-05-08 = 2023-05-07

Output JSON:
{
  "answer": "Direct answer",
  "confidence": 0.0-1.0,
  "reasoning": "Step-by-step explanation",
  "temporal_resolutions": [{"original_text": "...", "memory_timestamp": "...", "resolved_date": "...", "confidence": 0.0-1.0}],
  "source_memory_indices": [1, 3],
  "requires_inference": true
}
"""
```

## SessionStart Summary Injection

### Encapsulation Format

```xml
<memory_consolidated_summaries version="a1b2c3d4" generated_at="2025-01-20T10:30:00Z">
<!-- Memory Consolidation Context - Auto-generated, do not edit -->
<!-- This block is replaced on each session start -->

## Project Memory Context

The following summarizes key decisions, learnings, and context from this project's history:

### Decisions (2025-01-10 - 2025-01-17)

Selected FastAPI as the primary web framework due to native async support...

**Key facts:**
- FastAPI selected as primary web framework
- Async support was deciding factor

**Decisions:**
- Use FastAPI over Flask
  - Rationale: Native async, OpenAPI generation, performance

**Note - superseded information:**
- ~~Initial estimate of 2x improvement~~ → Measured 3x improvement

</memory_consolidated_summaries>
```

### Idempotency Implementation

```python
class SessionStartSummaryInjector:
    def inject_summaries(
        self,
        existing_context: str | None,
        session_context: SessionContext,
    ) -> SummaryInjectionResult:
        # Step 1: Remove existing summary block
        clean_context, had_existing = self._remove_existing_block(existing_context)

        # Step 2: Select summaries based on relevance
        summaries = self._select_summaries(session_context)

        # Step 3: Format within token budget
        summary_block = self._format_summary_block(summaries)

        return SummaryInjectionResult(
            summaries_injected=len(summaries),
            tokens_used=self._estimate_tokens(summary_block),
            context_block=summary_block,
            replaced_existing=had_existing,
        )

    def _remove_existing_block(self, context: str | None) -> tuple[str, bool]:
        if not context:
            return "", False
        pattern = rf"<memory_consolidated_summaries.*?>.*?</memory_consolidated_summaries>"
        cleaned, count = re.subn(pattern, "", context, flags=re.DOTALL)
        return cleaned.strip(), count > 0
```

## RecallService Extension

```python
class RetrievalMode(str, Enum):
    REFLEXIVE = "reflexive"    # Hot only
    STANDARD = "standard"      # Hot + Warm
    DEEP = "deep"              # Hot + Warm + Cold
    EXHAUSTIVE = "exhaustive"  # All tiers

# Extended search method
def search(
    self,
    query: str,
    *,
    namespace: str | None = None,
    limit: int = 10,
    min_similarity: float = 0.5,
    mode: RetrievalMode = RetrievalMode.STANDARD,
    include_summaries: bool = True,
) -> list[MemoryResult]:
    # 1. Filter by tier based on mode
    allowed_tiers = self._get_allowed_tiers(mode)

    # 2. Query with tier filter
    results = self._index.search_vector(
        embedding=self._embed(query),
        k=limit,
        tiers=allowed_tiers,
    )

    # 3. Include summaries if enabled
    if include_summaries:
        summary_results = self._summary_store.search(query, limit=limit // 2)
        results = self._merge_results(results, summary_results)

    # 4. Increment activation count
    self._metadata_store.increment_activation(
        memory_ids=[r.memory.id for r in results]
    )

    return results
```

## Feature Gating

### pyproject.toml

```toml
[project.optional-dependencies]
consolidation = [
    "scikit-learn>=1.3",
    "openai>=1.0",
    "httpx>=0.25",
]
```

### Lazy Import Pattern

```python
def get_consolidation_service() -> ConsolidationService:
    try:
        from .consolidation.service import ConsolidationService
        # ... initialization
    except ImportError as e:
        raise NotImplementedError(
            "Consolidation requires: pip install git-notes-memory[consolidation]"
        ) from e
```

## Data Flow

### Consolidation Pipeline

```
1. SCAN Phase
   - Load all memories from index
   - Load/create MemoryMetadata for each
   - Compute RetentionScore for each
   - Output: List[tuple[Memory, MemoryMetadata, RetentionScore]]

2. CLUSTER Phase
   - Retrieve embeddings from index
   - Run AgglomerativeClustering
   - Filter by size constraints
   - Output: List[MemoryCluster]

3. SUMMARIZE Phase
   - For each cluster:
     - Format memory contents
     - Call LLM with SUMMARY_SYSTEM_PROMPT
     - Parse response into MemorySummary
   - Output: List[MemorySummary]

4. SUPERSESSION Phase
   - For pairs of potentially conflicting memories:
     - Call LLM with SUPERSESSION_SYSTEM_PROMPT
     - Create MemoryEdge if supersession detected
   - Output: List[MemoryEdge]

5. TIER Phase
   - For each memory:
     - Map RetentionScore to MemoryTier
     - Create TierTransition if tier changed
   - Output: List[TierTransition]

6. PERSIST Phase
   - Write MemoryMetadata to refs/notes/mem-meta/
   - Write MemorySummary to refs/notes/mem-summaries/
   - Write MemoryEdge to refs/notes/mem-edges/
   - Update SQLite index with tiers
   - Log ConsolidationResult to refs/notes/mem-runs/
```

### SessionStart Injection Flow

```
1. Hook receives SessionStart event
2. Check if consolidation available (feature gating)
3. Build SessionContext from event
4. Call SessionStartSummaryInjector.inject_summaries()
   a. Remove existing summary block (regex)
   b. Select relevant summaries by score
   c. Format within token budget
5. Combine clean context + new summary block
6. Return via additionalContext field
```

### Temporal Reasoning Flow

```
1. Query received (e.g., "When did X happen?")
2. Check if reasoning needed (pattern match or --reason flag)
3. Retrieve memories with RecallService
4. Format memories with explicit timestamps
5. Call LLM with REASONING_SYSTEM_PROMPT
6. Parse response into ReasonedAnswer
7. Return answer with temporal resolutions and provenance
```

## Deep Observability Architecture

Observability is integrated throughout the entire library - every module, method, and class - not just the hooks. This provides full visibility into operations at every level.

### Observability Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                       Observability Stack                        │
├─────────────────────────────────────────────────────────────────┤
│  Structured Logging                                              │
│  - Every public method logs entry/exit with timing               │
│  - Log levels: TRACE (all spans), DEBUG (detailed), INFO (key)  │
│  - JSON format with correlation IDs for request tracing         │
├─────────────────────────────────────────────────────────────────┤
│  Metrics Collection                                              │
│  - Counters: operations, successes, failures by type            │
│  - Histograms: operation duration distributions                 │
│  - Gauges: queue depths, active operations, memory tiers        │
├─────────────────────────────────────────────────────────────────┤
│  Distributed Tracing (OpenTelemetry)                             │
│  - Spans for every service method call                          │
│  - Parent-child span relationships                              │
│  - Span attributes: memory_id, namespace, tier, etc.            │
│  - OTLP export to collector/Grafana Tempo                       │
├─────────────────────────────────────────────────────────────────┤
│  Health Checks                                                   │
│  - Component readiness (LLM, index, git)                        │
│  - Degradation detection                                        │
└─────────────────────────────────────────────────────────────────┘
```

### Instrumentation by Module

| Module | Metrics | Traces | Logs |
|--------|---------|--------|------|
| **ConsolidationService** | run_duration, memories_processed, clusters_created, summaries_generated, supersessions_detected, tier_transitions | `consolidation.run`, `consolidation.scan`, `consolidation.cluster`, `consolidation.summarize`, `consolidation.supersession`, `consolidation.tier`, `consolidation.persist` | Phase transitions, errors, batch progress |
| **RetentionCalculator** | score_calculations, score_distribution (histogram) | `retention.compute` | Score breakdown factors |
| **SemanticClustering** | clustering_duration, cluster_sizes (histogram), clusters_found | `clustering.execute`, `clustering.compute_distances` | Cluster assignments |
| **LLM Calls** | llm_requests, llm_tokens_used, llm_latency (histogram), llm_errors | `llm.summarize`, `llm.detect_supersession`, `llm.reason` | Request/response (truncated), provider, model |
| **RecallService (extended)** | recalls_by_mode, activation_increments, tier_filtered_results | `recall.search`, `recall.filter_by_tier`, `recall.increment_activation` | Query, mode, result count |
| **ReasonedRecallService** | reasoned_recalls, temporal_resolutions, reasoning_confidence (histogram) | `reasoning.recall`, `reasoning.resolve_temporal`, `reasoning.synthesize` | Query, resolutions, confidence |
| **SessionStartSummaryInjector** | injections, replacements, tokens_used (histogram), summaries_selected | `session.inject_summaries`, `session.select_summaries`, `session.format_block` | Selection scores, token budget |
| **MetadataStore** | metadata_reads, metadata_writes | `store.metadata.read`, `store.metadata.write` | Memory ID, tier |
| **SummaryStore** | summary_reads, summary_writes, summary_searches | `store.summary.read`, `store.summary.write`, `store.summary.search` | Summary ID, source count |
| **EdgeStore** | edge_writes, edges_by_type | `store.edge.write`, `store.edge.read` | Edge type, source/target |

### Trace Hierarchy Example

```
consolidation.run (10.5s)
├── consolidation.scan (2.1s)
│   ├── store.metadata.read (0.3s, count=500)
│   └── retention.compute (1.5s, batch)
├── consolidation.cluster (1.2s)
│   ├── clustering.compute_distances (0.8s)
│   └── clustering.execute (0.4s)
├── consolidation.summarize (5.0s)
│   ├── llm.summarize (1.2s, cluster_0)
│   ├── llm.summarize (1.1s, cluster_1)
│   ├── llm.summarize (1.3s, cluster_2)
│   └── store.summary.write (0.4s)
├── consolidation.supersession (1.5s)
│   ├── llm.detect_supersession (0.3s, pair_0)
│   ├── llm.detect_supersession (0.4s, pair_1)
│   └── store.edge.write (0.2s)
├── consolidation.tier (0.2s)
└── consolidation.persist (0.5s)
    ├── store.metadata.write (0.2s)
    └── git.notes.sync (0.3s)
```

### Instrumentation Implementation

```python
from git_notes_memory.observability import get_tracer, get_metrics, get_logger

tracer = get_tracer(__name__)
metrics = get_metrics(__name__)
logger = get_logger(__name__)

class ConsolidationService:
    @tracer.start_as_current_span("consolidation.run")
    async def run_consolidation(self, *, full: bool = False, dry_run: bool = False) -> ConsolidationResult:
        span = trace.get_current_span()
        span.set_attribute("consolidation.mode", "full" if full else "incremental")
        span.set_attribute("consolidation.dry_run", dry_run)

        start_time = time.perf_counter()
        logger.info("Starting consolidation", mode="full" if full else "incremental")

        try:
            result = await self._execute_pipeline(full=full, dry_run=dry_run)
            metrics.counter("consolidation.runs", 1, {"status": "success"})
            return result
        except Exception as e:
            metrics.counter("consolidation.runs", 1, {"status": "error"})
            span.record_exception(e)
            span.set_status(StatusCode.ERROR)
            logger.error("Consolidation failed", error=str(e))
            raise
        finally:
            duration = time.perf_counter() - start_time
            metrics.histogram("consolidation.duration_seconds", duration)
            logger.info("Consolidation completed", duration_seconds=duration)

    @tracer.start_as_current_span("consolidation.scan")
    async def _phase_scan(self, ...) -> ...:
        span = trace.get_current_span()
        ...
        span.set_attribute("scan.memories_count", len(memories))
        metrics.histogram("consolidation.scan.memories", len(memories))
        ...
```

### Span Attributes by Operation

| Operation | Attributes |
|-----------|------------|
| `consolidation.run` | mode, dry_run, checkpoint_id |
| `consolidation.scan` | memories_count, metadata_loaded |
| `consolidation.cluster` | clusters_found, min_size, max_size, threshold |
| `consolidation.summarize` | cluster_id, source_count, tokens_used |
| `llm.summarize` | model, provider, prompt_tokens, completion_tokens |
| `llm.detect_supersession` | older_id, newer_id, result, confidence |
| `retention.compute` | memory_id, recency, activation, importance, overall |
| `recall.search` | query_length, mode, limit, result_count |
| `reasoning.recall` | query, temporal_patterns_found, confidence |
| `session.inject_summaries` | existing_replaced, summaries_count, tokens_used |

### Logging Guidelines

Every significant operation logs with structured context:

```python
# Method entry (DEBUG level)
logger.debug("Computing retention score", memory_id=memory.id, age_days=age_days)

# Key decisions (INFO level)
logger.info("Memory tier changed",
    memory_id=memory.id,
    from_tier=old_tier.value,
    to_tier=new_tier.value,
    retention_score=score.overall
)

# LLM interactions (DEBUG with TRACE for full content)
logger.debug("LLM summarization request",
    cluster_id=cluster.id,
    source_count=len(cluster.memory_ids),
    model=config.model
)
logger.trace("LLM prompt", prompt=prompt[:1000])  # Truncate at TRACE

# Errors (ERROR level with context)
logger.error("Supersession detection failed",
    older_id=older.id,
    newer_id=newer.id,
    error=str(e),
    exc_info=True
)
```

### Configuration

```python
# Full observability config
MEMORY_PLUGIN_OBSERVABILITY_ENABLED=true
MEMORY_PLUGIN_LOG_LEVEL=debug      # quiet|info|debug|trace
MEMORY_PLUGIN_LOG_FORMAT=json      # json|text
MEMORY_PLUGIN_TRACING_ENABLED=true
MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4317
MEMORY_PLUGIN_METRICS_ENABLED=true
MEMORY_PLUGIN_METRICS_RETENTION=3600

# Consolidation-specific observability
MEMORY_CONSOLIDATION_TRACE_LLM_CONTENT=false  # Log full prompts/responses
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Observability** | Deep instrumentation at every level | User requirement: need to see what's happening at every level - methods, classes, modules |
| LLM Provider | OpenAI → LM Studio → Ollama | Cheap cloud + local fallback per user requirement |
| Decay Parameters | Conservative defaults, all tunable | Start safe, let users adjust based on usage patterns |
| Clustering | Semantic only, ignore time | Related memories from different sessions should consolidate together |
| Supersession | LLM judgment | Heuristics miss nuance; LLM can explain reasoning for auditability |
| Edge Storage | Separate git notes ref | Clean separation, doesn't pollute existing memory refs |
| Hook Trigger | Observability module installed | User requirement to tie to optional observability extra |
| Feature Gating | pip extras `[consolidation]` | Works without impeding base functionality, activates on install |
| Context Injection | XML-style tags | Unique wrapper enables reliable find/replace for idempotency |

## Testing Strategy

### Unit Tests
- Retention score calculation (boundary conditions, edge cases)
- Tier assignment logic (threshold boundaries)
- Clustering algorithm (mock embeddings)
- LLM response parsing (mock client, malformed responses)
- Summary block formatting (token budget, truncation)
- Context replacement logic (idempotency)
- Temporal reference detection (all patterns)
- Temporal resolution against timestamps (edge cases)

### Integration Tests
- Full consolidation pipeline (end-to-end)
- Git notes read/write for new refs
- RecallService with tier filtering
- Summary injection into SessionStart
- ReasonedRecallService end-to-end

### Property-Based Tests
- Retention score always in [0, 1]
- Tier transitions follow hierarchy (hot→warm→cold→archived)
- Consolidation is idempotent
- Multiple SessionStart events produce exactly 1 summary block

### Idempotency Tests
```python
def test_summary_injection_replaces_not_accumulates():
    # First injection
    result1 = injector.inject_summaries(None, session_context)
    # Second injection with existing context
    result2 = injector.inject_summaries(result1.context_block, session_context)
    # Must have exactly 1 block
    assert result2.context_block.count("<memory_consolidated_summaries") == 1
    assert result2.replaced_existing is True
```

### Temporal Reasoning Tests
```python
def test_temporal_resolution_yesterday():
    memory_timestamp = datetime(2023, 5, 8, 14, 30, tzinfo=UTC)
    resolved = resolve_temporal_reference("yesterday", memory_timestamp)
    assert resolved.date() == date(2023, 5, 7)
```
