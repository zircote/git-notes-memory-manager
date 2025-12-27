# Memory Consolidation Extension: claude-spec Prompt

## Overview

You are extending the **existing** `git_notes_memory.subconsciousness` module to implement memory consolidation - an asynchronous background process that reviews historical memories, generates summaries, detects supersessions, and manages memory tiers.

This feature implements cognitive-inspired memory consolidation (similar to human sleep cycles) where:

- Recent/frequently-accessed memories stay "hot"
- Older memories decay unless reinforced through retrieval
- Related memories are clustered and summarized
- Superseded memories are linked to their replacements
- Original memories are never deleted, only deprioritized

## Existing Architecture (DO NOT MODIFY)

The subconsciousness module already exists with these components:

### Existing Models (`models.py`)

```python
# Already implemented - extend, don't replace
- LLMMessage, LLMRequest, LLMResponse, LLMUsage, LLMConfig
- CaptureConfidence (with factor breakdown: relevance, actionability, novelty, specificity, coherence)
- ImplicitMemory, ImplicitCapture
- ReviewStatus, ThreatLevel, ThreatDetection
- LLMError hierarchy (LLMRateLimitError, LLMAuthenticationError, etc.)
```

### Existing Config (`config.py`)

```python
# These toggles exist but features are NOT implemented yet:
consolidation_enabled: bool = True
consolidation_threshold: float = 0.85  # Similarity threshold for clustering
forgetting_enabled: bool = True
archive_threshold: float = 0.3  # Retention score below this → archive
surfacing_enabled: bool = True
linking_enabled: bool = True
```

### Existing LLM Client (`llm_client.py`)

```python
# Already implemented - reuse for consolidation LLM calls
- LLMClient with primary_provider + fallback_provider (Ollama)
- CircuitBreaker, RateLimiter, UsageTracker
- Secrets filtering via SecretsFilteringService
- get_default_llm_client() factory
```

### Existing Service Pattern (`implicit_capture_service.py`)

```python
# Follow this pattern for ConsolidationService:
@dataclass
class ImplicitCaptureService:
    capture_agent: ImplicitCaptureAgent
    detector: AdversarialDetector
    store: CaptureStore
    # ... config fields with defaults

    async def capture_from_transcript(...) -> CaptureServiceResult:
        # Main entry point

# Factory with singleton:
_service: ImplicitCaptureService | None = None

def get_implicit_capture_service() -> ImplicitCaptureService:
    global _service
    if _service is None:
        _service = ImplicitCaptureService(...)
    return _service

def reset_implicit_capture_service() -> None:
    global _service
    _service = None
```

## Requirements

### 1. LLM Provider Configuration

Support multiple backends for summary generation and supersession detection:

**Provider Priority (user's requirement):**

1. OpenAI GPT-5-nano or GPT-5-mini (when available, fall back to gpt-4o-mini)
2. LM Studio (OpenAI-compatible local endpoint)
3. Ollama (local)

**New Environment Variables:**

```bash
# Extend existing MEMORY_LLM_* pattern
MEMORY_CONSOLIDATION_LLM_PROVIDER=openai|lmstudio|ollama  # default: inherit from MEMORY_LLM_PROVIDER
MEMORY_CONSOLIDATION_LLM_MODEL=gpt-4o-mini               # default model
MEMORY_CONSOLIDATION_LLM_BASE_URL=http://localhost:1234/v1  # for lmstudio
```

**Implementation:** Reuse existing `LLMClient` infrastructure. Create a separate client instance for consolidation if provider differs from main config, otherwise share the client.

### 2. New Models (add to `models.py`)

```python
# =============================================================================
# Memory Tier and Lifecycle Models
# =============================================================================

class MemoryTier(str, Enum):
    """Memory retrieval tier based on retention score.

    Tiers control which memories appear in search results:
    - HOT: Default search includes, low retrieval cost
    - WARM: Default search includes, summaries live here
    - COLD: Deep recall only, excluded from default search
    - ARCHIVED: Exhaustive search only, superseded or very old
    """
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class RetentionScore:
    """Retention score with factor breakdown for explainability.

    Similar to CaptureConfidence pattern - overall score is weighted
    combination of individual factors.

    Attributes:
        overall: Combined retention score (0.0-1.0).
        recency: Time-based decay factor.
        activation: Retrieval frequency factor.
        importance: Namespace/type-based weight.
        relevance: Semantic relevance to current project (optional, computed on-demand).
    """
    overall: float
    recency: float = 0.0
    activation: float = 0.0
    importance: float = 0.0
    relevance: float | None = None  # Computed contextually, not stored

    def __post_init__(self) -> None:
        for field_name in ("overall", "recency", "activation", "importance"):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{field_name} must be between 0.0 and 1.0")


@dataclass(frozen=True)
class MemoryMetadata:
    """Consolidation metadata for a memory.

    Stored separately from core Memory model to avoid breaking
    existing interfaces. Persisted in refs/notes/mem-meta/.

    Attributes:
        memory_id: Reference to the Memory.
        tier: Current retrieval tier.
        activation_count: Number of times retrieved.
        last_accessed: Timestamp of last retrieval.
        retention: Current retention score with factors.
        superseded_by: Memory ID that supersedes this (if any).
        consolidated_into: Summary ID if this memory was consolidated.
        created_at: When metadata was created.
        updated_at: When metadata was last updated.
    """
    memory_id: str
    tier: MemoryTier = MemoryTier.HOT
    activation_count: int = 0
    last_accessed: datetime | None = None
    retention: RetentionScore = field(default_factory=lambda: RetentionScore(overall=1.0))
    superseded_by: str | None = None
    consolidated_into: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Memory Summary Models
# =============================================================================

@dataclass(frozen=True)
class SummaryDecision:
    """A decision extracted from consolidated memories."""
    decision: str
    rationale: str
    outcome: str | None = None
    confidence: str = "medium"  # high|medium|low


@dataclass(frozen=True)
class SupersededFact:
    """A fact that was superseded by newer information."""
    original_fact: str
    superseded_by: str
    source_memory_id: str


@dataclass(frozen=True)
class MemorySummary:
    """Consolidated summary of related memories.

    Represents an abstraction over multiple episodic memories.
    Stored in refs/notes/mem-summaries/.

    Attributes:
        id: Unique identifier (sum_<ulid>).
        namespace: Inherited from dominant source namespace.
        created_at: When summary was created.
        temporal_range: Time span of source memories.
        summary: Generated summary text.
        key_facts: Extracted facts still valid.
        decisions: Decisions with rationale and outcomes.
        superseded_facts: Facts known to be outdated.
        source_memory_ids: IDs of memories this summarizes.
        consolidation_run_id: Which run created this.
        confidence: Confidence in summary quality.
        tier: Always WARM for summaries.
        activation_count: Retrieval count.
    """
    id: str
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize for git notes storage."""
        return {
            "id": self.id,
            "namespace": self.namespace,
            "created_at": self.created_at.isoformat(),
            "temporal_range": {
                "start": self.temporal_range[0].isoformat(),
                "end": self.temporal_range[1].isoformat(),
            },
            "summary": self.summary,
            "key_facts": list(self.key_facts),
            "decisions": [
                {
                    "decision": d.decision,
                    "rationale": d.rationale,
                    "outcome": d.outcome,
                    "confidence": d.confidence,
                }
                for d in self.decisions
            ],
            "superseded_facts": [
                {
                    "original_fact": f.original_fact,
                    "superseded_by": f.superseded_by,
                    "source_memory_id": f.source_memory_id,
                }
                for f in self.superseded_facts
            ],
            "source_memory_ids": list(self.source_memory_ids),
            "consolidation_run_id": self.consolidation_run_id,
            "confidence": {
                "overall": self.confidence.overall,
                "relevance": self.confidence.relevance,
                "actionability": self.confidence.actionability,
                "novelty": self.confidence.novelty,
                "specificity": self.confidence.specificity,
                "coherence": self.confidence.coherence,
            },
            "tier": self.tier.value,
            "activation_count": self.activation_count,
        }


# =============================================================================
# Memory Edge Models
# =============================================================================

class EdgeType(str, Enum):
    """Type of relationship between memories."""
    SUPERSEDES = "supersedes"      # Newer invalidates older
    CONSOLIDATES = "consolidates"  # Summary abstracts sources
    REFERENCES = "references"      # Explicit causal/contextual link


@dataclass(frozen=True)
class MemoryEdge:
    """Relationship edge between memories or summaries.

    Stored in refs/notes/mem-edges/.

    Attributes:
        source_id: Memory or summary ID (the "from" node).
        target_id: Memory or summary ID (the "to" node).
        edge_type: Type of relationship.
        weight: Edge strength (0.0-1.0).
        reason: LLM-provided explanation (for supersession).
        created_at: When edge was created.
        consolidation_run_id: Which run created this edge.
    """
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    consolidation_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "consolidation_run_id": self.consolidation_run_id,
        }


# =============================================================================
# Consolidation Result Models
# =============================================================================

class ConsolidationPhase(str, Enum):
    """Phases of the consolidation pipeline."""
    SCAN = "scan"
    CLUSTER = "cluster"
    SUMMARIZE = "summarize"
    SUPERSESSION = "supersession"
    TIER = "tier"
    PERSIST = "persist"
    COMPLETED = "completed"


@dataclass(frozen=True)
class TierTransition:
    """Record of a memory tier change."""
    memory_id: str
    from_tier: MemoryTier
    to_tier: MemoryTier
    reason: str
    retention_score: float


@dataclass(frozen=True)
class ConsolidationResult:
    """Result of a consolidation run.

    Attributes:
        run_id: Unique identifier for this run.
        started_at: When consolidation started.
        completed_at: When consolidation finished (None if failed/interrupted).
        phase: Final phase reached.
        memories_processed: Total memories scanned.
        clusters_found: Semantic clusters identified.
        summaries_created: New summaries generated.
        supersessions_detected: Supersession edges created.
        tier_transitions: Memory tier changes.
        errors: Any errors encountered.
    """
    run_id: str
    started_at: datetime
    completed_at: datetime | None
    phase: ConsolidationPhase
    memories_processed: int = 0
    clusters_found: int = 0
    summaries_created: int = 0
    supersessions_detected: int = 0
    tier_transitions: tuple[TierTransition, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def success(self) -> bool:
        return self.phase == ConsolidationPhase.COMPLETED and len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "phase": self.phase.value,
            "memories_processed": self.memories_processed,
            "clusters_found": self.clusters_found,
            "summaries_created": self.summaries_created,
            "supersessions_detected": self.supersessions_detected,
            "tier_transitions": [
                {
                    "memory_id": t.memory_id,
                    "from_tier": t.from_tier.value,
                    "to_tier": t.to_tier.value,
                    "reason": t.reason,
                    "retention_score": t.retention_score,
                }
                for t in self.tier_transitions
            ],
            "errors": list(self.errors),
        }
```

### 3. Extend Config (`config.py`)

Add new configuration options following existing pattern:

```python
# New defaults
DEFAULT_RETENTION_HALF_LIFE_DAYS = 30.0
DEFAULT_ACTIVATION_BOOST = 0.1
DEFAULT_MIN_CLUSTER_SIZE = 3
DEFAULT_MAX_CLUSTER_SIZE = 20
DEFAULT_CONSOLIDATION_BATCH_SIZE = 50
DEFAULT_CONSOLIDATION_INTERVAL_HOURS = 24

# Add to SubconsciousnessConfig dataclass:
@dataclass(frozen=True)
class SubconsciousnessConfig:
    # ... existing fields ...

    # Consolidation settings (NEW)
    retention_half_life_days: float = DEFAULT_RETENTION_HALF_LIFE_DAYS
    activation_boost: float = DEFAULT_ACTIVATION_BOOST
    min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE
    max_cluster_size: int = DEFAULT_MAX_CLUSTER_SIZE
    consolidation_batch_size: int = DEFAULT_CONSOLIDATION_BATCH_SIZE
    consolidation_interval_hours: int = DEFAULT_CONSOLIDATION_INTERVAL_HOURS

    # Tier thresholds (NEW)
    hot_threshold: float = 0.6   # >= this stays hot
    warm_threshold: float = 0.3  # >= this stays warm (or archive_threshold)
    # cold_threshold is implicit: >= archive_threshold and < warm_threshold
    # archived: < archive_threshold (already exists)
```

### 4. New Service: `consolidation_service.py`

```python
"""Memory consolidation service.

Implements cognitive-inspired memory consolidation:
1. SCAN: Load memories, compute retention scores
2. CLUSTER: Group by semantic similarity (regardless of time)
3. SUMMARIZE: Generate summaries via LLM
4. SUPERSESSION: Detect contradictions via LLM judgment
5. TIER: Assign tiers based on retention scores
6. PERSIST: Write to git notes, update sqlite index

Runs asynchronously, triggered by:
- Subconscious hook (when installed)
- Manual /memory:consolidate command
- Memory pressure signal
"""

@dataclass
class ConsolidationService:
    """Service for background memory consolidation.

    Attributes:
        llm_client: LLM client for summaries and supersession detection.
        recall_service: For loading memories and embeddings.
        sync_service: For persisting to git notes.
        config: Consolidation configuration.
    """
    llm_client: LLMClient
    recall_service: RecallService  # Existing service
    sync_service: SyncService      # Existing service
    config: SubconsciousnessConfig

    # Internal state
    _metadata_store: MetadataStore = field(default_factory=...)
    _summary_store: SummaryStore = field(default_factory=...)
    _edge_store: EdgeStore = field(default_factory=...)

    async def run_consolidation(
        self,
        *,
        full: bool = False,
        dry_run: bool = False,
        checkpoint_id: str | None = None,
    ) -> ConsolidationResult:
        """Execute consolidation pipeline.

        Args:
            full: Process all memories (vs incremental since last run).
            dry_run: Compute but don't persist changes.
            checkpoint_id: Resume from checkpoint.

        Returns:
            ConsolidationResult with statistics.
        """
        ...

    async def incremental_consolidation(self) -> ConsolidationResult:
        """Consolidate memories since last run."""
        ...

    # Pipeline phases
    async def _phase_scan(self, ...) -> ...:
        """Load memories and compute retention scores."""
        ...

    async def _phase_cluster(self, ...) -> ...:
        """Cluster memories by semantic similarity."""
        # Use sklearn AgglomerativeClustering or HDBSCAN
        # Cluster by embedding distance, NOT by time
        ...

    async def _phase_summarize(self, clusters: ...) -> ...:
        """Generate summaries for each cluster via LLM."""
        ...

    async def _phase_supersession(self, ...) -> ...:
        """Detect superseded memories via LLM judgment."""
        ...

    async def _phase_tier(self, ...) -> ...:
        """Assign tiers based on retention scores."""
        ...

    async def _phase_persist(self, ...) -> ...:
        """Write results to git notes and sqlite."""
        ...

    def get_status(self) -> dict[str, Any]:
        """Get consolidation status for /memory:status."""
        ...
```

### 5. Retention Score Calculation

Follow `CaptureConfidence.from_factors()` pattern:

```python
@dataclass(frozen=True)
class RetentionConfig:
    """Tunable retention parameters. Conservative defaults."""
    half_life_days: float = 30.0
    activation_boost: float = 0.1
    recency_weight: float = 0.4
    activation_weight: float = 0.2
    importance_weight: float = 0.4

    # Tier thresholds
    hot_threshold: float = 0.6
    warm_threshold: float = 0.3
    archive_threshold: float = 0.1  # From existing config

# Importance weights by namespace (from existing 10 namespaces)
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

def compute_retention_score(
    memory: Memory,
    metadata: MemoryMetadata,
    config: RetentionConfig,
    now: datetime,
) -> RetentionScore:
    """Compute retention score for tier assignment."""
    # Recency: exponential decay
    age_days = (now - memory.timestamp).total_seconds() / 86400
    access_age = (now - metadata.last_accessed).total_seconds() / 86400 if metadata.last_accessed else age_days
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
```

### 6. Semantic Clustering

Cluster by embedding similarity, **regardless of time**:

```python
async def cluster_memories(
    memories: list[Memory],
    embeddings: dict[str, np.ndarray],  # memory_id -> embedding
    config: SubconsciousnessConfig,
) -> list[MemoryCluster]:
    """Cluster memories using agglomerative clustering.

    Groups memories by semantic similarity only - time is NOT a factor.
    This allows related memories from different sessions/dates to be
    consolidated together.
    """
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics.pairwise import cosine_distances

    # Build embedding matrix
    ids = list(embeddings.keys())
    X = np.array([embeddings[id] for id in ids])

    # Cluster using cosine distance
    distance_matrix = cosine_distances(X)
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1 - config.consolidation_threshold,  # Convert similarity to distance
        metric="precomputed",
        linkage="average",
    )
    labels = clustering.fit_predict(distance_matrix)

    # Group by cluster label
    clusters: dict[int, list[str]] = {}
    for idx, label in enumerate(labels):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(ids[idx])

    # Filter by size constraints
    return [
        MemoryCluster(memory_ids=tuple(ids), label=label)
        for label, ids in clusters.items()
        if config.min_cluster_size <= len(ids) <= config.max_cluster_size
    ]
```

### 7. LLM Prompts for Summarization and Supersession

Create `consolidation_prompts.py`:

```python
SUMMARY_SYSTEM_PROMPT = """You are a memory consolidation agent. Your task is to create a concise summary of related memories from a software project.

Guidelines:
- Preserve key decisions and their rationale
- Note outcomes and lessons learned
- Identify any superseded or outdated information
- Be concise but complete
- Focus on actionable knowledge

Output JSON with this structure:
{
  "summary": "2-3 sentence summary",
  "key_facts": ["fact1", "fact2"],
  "decisions": [{"decision": "...", "rationale": "...", "outcome": "...", "confidence": "high|medium|low"}],
  "superseded_facts": [{"original_fact": "...", "superseded_by": "...", "source_memory_id": "..."}]
}
"""

SUPERSESSION_SYSTEM_PROMPT = """You are analyzing two memories from a software project to determine if the newer one supersedes the older.

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

### 8. Git Notes Schema

**New ref namespaces:**

```
refs/notes/mem-meta/       # MemoryMetadata records
refs/notes/mem-summaries/  # MemorySummary records
refs/notes/mem-edges/      # MemoryEdge batches
refs/notes/mem-runs/       # ConsolidationResult logs
```

**Storage format:** YAML (following existing git notes patterns)

Create `consolidation_store.py` with:

- `MetadataStore` - CRUD for MemoryMetadata
- `SummaryStore` - CRUD for MemorySummary
- `EdgeStore` - CRUD for MemoryEdge
- `RunLogStore` - append-only for ConsolidationResult

### 9. Extend RecallService

Add tier-based filtering and activation tracking:

```python
class RetrievalMode(str, Enum):
    """Retrieval modes with different tier coverage."""
    REFLEXIVE = "reflexive"    # Hot only
    STANDARD = "standard"      # Hot + Warm (default)
    DEEP = "deep"              # Hot + Warm + Cold
    EXHAUSTIVE = "exhaustive"  # All tiers

# Extend RecallService.search():
def search(
    self,
    query: str,
    *,
    namespace: str | None = None,
    limit: int = 10,
    min_similarity: float = 0.5,
    mode: RetrievalMode = RetrievalMode.STANDARD,  # NEW
    include_summaries: bool = True,  # NEW
) -> list[MemoryResult]:
    """Search with tier filtering and activation tracking."""
    # 1. Filter by tier based on mode
    # 2. Include MemorySummary results if enabled
    # 3. Increment activation_count for returned memories
    ...
```

### 9.1 Reasoning Layer for Explicit Recall

**Problem:** Raw memory retrieval returns content with relative temporal references ("yesterday", "last week") that cannot be resolved without reasoning over memory timestamps.

Example failure:

```
Q: When did Caroline go to the LGBTQ support group?
Expected: 7 May 2023
Retrieved: "She said she went 'yesterday'" (memory from 8 May 2023)
Returned: "I cannot find this information" ❌
```

The memories ARE retrieved but the system fails to reason: "yesterday" relative to memory timestamp (8 May 2023) = 7 May 2023.

**Solution:** Add an LLM-powered reasoning layer for explicit recall queries that:

1. Retrieves relevant memories with their timestamps
2. Resolves relative temporal references against memory creation dates
3. Synthesizes a reasoned answer
4. Provides provenance (which memories support the answer)

#### ReasonedRecallService

```python
"""Reasoning layer for explicit memory recall.

Sits on top of RecallService to provide:
- Temporal reasoning (resolve "yesterday", "last week", etc.)
- Multi-memory synthesis (combine facts from multiple memories)
- Confidence scoring (how certain is the answer)
- Provenance tracking (which memories support the answer)
"""

@dataclass(frozen=True)
class TemporalReference:
    """A resolved temporal reference from memory content."""
    original_text: str          # "yesterday", "last week"
    memory_timestamp: datetime  # When the memory was created
    resolved_date: datetime     # Computed absolute date
    confidence: float           # How confident in the resolution


@dataclass(frozen=True)
class ReasonedAnswer:
    """Answer with reasoning chain and provenance."""
    answer: str
    confidence: float  # 0.0-1.0
    reasoning: str     # Explanation of how answer was derived
    temporal_resolutions: tuple[TemporalReference, ...]
    source_memories: tuple[MemoryResult, ...]
    requires_inference: bool  # True if answer required reasoning beyond retrieval


@dataclass
class ReasonedRecallService:
    """LLM-powered reasoning over retrieved memories.

    Use for explicit recall queries where the user expects
    a specific answer, not just relevant context.
    """

    recall_service: RecallService
    llm_client: LLMClient
    config: SubconsciousnessConfig

    async def recall_with_reasoning(
        self,
        query: str,
        *,
        mode: RetrievalMode = RetrievalMode.STANDARD,
        require_temporal_reasoning: bool = True,
    ) -> ReasonedAnswer:
        """Retrieve memories and reason over them to answer query.

        Pipeline:
        1. Retrieve relevant memories with timestamps
        2. Detect temporal references in memory content
        3. Resolve temporal references against memory timestamps
        4. Use LLM to synthesize answer from resolved memories
        5. Return answer with provenance and confidence
        """
        # Step 1: Retrieve memories
        memories = self.recall_service.search(
            query,
            mode=mode,
            include_summaries=True,
        )

        if not memories:
            return ReasonedAnswer(
                answer="No relevant memories found.",
                confidence=0.0,
                reasoning="No memories matched the query.",
                temporal_resolutions=(),
                source_memories=(),
                requires_inference=False,
            )

        # Step 2: Prepare context with timestamps for LLM
        memory_context = self._format_memories_with_timestamps(memories)

        # Step 3: Use LLM to reason and answer
        response = await self._reason_over_memories(query, memory_context)

        return response

    def _format_memories_with_timestamps(
        self,
        memories: list[MemoryResult],
    ) -> str:
        """Format memories with explicit timestamps for LLM reasoning."""
        lines = []
        for i, mem in enumerate(memories, 1):
            timestamp = mem.memory.timestamp.strftime("%Y-%m-%d %H:%M:%S %Z")
            lines.append(f"[Memory {i}] (recorded: {timestamp})")
            lines.append(f"Content: {mem.memory.content}")
            lines.append("")
        return "\n".join(lines)

    async def _reason_over_memories(
        self,
        query: str,
        memory_context: str,
    ) -> ReasonedAnswer:
        """Use LLM to reason over memories and answer query."""
        response = await self.llm_client.complete(
            prompt=REASONING_USER_PROMPT.format(
                query=query,
                memories=memory_context,
            ),
            system=REASONING_SYSTEM_PROMPT,
            json_mode=True,
        )

        # Parse response
        return self._parse_reasoning_response(response)


# Prompts for reasoning
REASONING_SYSTEM_PROMPT = """You are a memory reasoning assistant. Your task is to answer questions by reasoning over retrieved memories.

CRITICAL: Pay attention to TIMESTAMPS on each memory. When memories contain relative temporal references like "yesterday", "last week", "this morning", "a few days ago", you MUST resolve them relative to the memory's recorded timestamp.

Example:
- Memory recorded: 2023-05-08 14:30:00
- Memory content: "Caroline said she went to the support group yesterday"
- Resolved: "yesterday" relative to 2023-05-08 = 2023-05-07

Reasoning steps:
1. Identify relevant memories for the query
2. Extract temporal references and resolve them against memory timestamps
3. Synthesize facts from multiple memories if needed
4. Provide confidence level based on evidence strength

Output JSON:
{
  "answer": "The direct answer to the question",
  "confidence": 0.0-1.0,
  "reasoning": "Step-by-step explanation of how you derived the answer",
  "temporal_resolutions": [
    {
      "original_text": "yesterday",
      "memory_timestamp": "2023-05-08T14:30:00Z",
      "resolved_date": "2023-05-07",
      "confidence": 0.95
    }
  ],
  "source_memory_indices": [1, 3],
  "requires_inference": true
}
"""

REASONING_USER_PROMPT = """Question: {query}

Retrieved memories (with timestamps):
{memories}

Analyze these memories and answer the question. Remember to resolve any relative temporal references against the memory timestamps."""
```

#### Temporal Reference Patterns

```python
"""Patterns for detecting and resolving temporal references."""

TEMPORAL_PATTERNS = {
    # Relative days
    "yesterday": lambda ts: ts - timedelta(days=1),
    "today": lambda ts: ts,
    "tomorrow": lambda ts: ts + timedelta(days=1),
    "the day before": lambda ts: ts - timedelta(days=1),
    "the day after": lambda ts: ts + timedelta(days=1),
    "two days ago": lambda ts: ts - timedelta(days=2),
    "a few days ago": lambda ts: ts - timedelta(days=3),  # Approximate

    # Relative weeks
    "last week": lambda ts: ts - timedelta(weeks=1),
    "this week": lambda ts: ts,
    "next week": lambda ts: ts + timedelta(weeks=1),
    "a week ago": lambda ts: ts - timedelta(weeks=1),

    # Relative months
    "last month": lambda ts: ts - timedelta(days=30),  # Approximate
    "this month": lambda ts: ts,
    "a month ago": lambda ts: ts - timedelta(days=30),

    # Time of day (same day as memory)
    "this morning": lambda ts: ts.replace(hour=9, minute=0),
    "this afternoon": lambda ts: ts.replace(hour=14, minute=0),
    "this evening": lambda ts: ts.replace(hour=18, minute=0),
    "tonight": lambda ts: ts.replace(hour=20, minute=0),
    "last night": lambda ts: (ts - timedelta(days=1)).replace(hour=22, minute=0),
}

def detect_temporal_references(content: str) -> list[str]:
    """Detect temporal reference phrases in content."""
    found = []
    content_lower = content.lower()
    for pattern in TEMPORAL_PATTERNS:
        if pattern in content_lower:
            found.append(pattern)
    return found

def resolve_temporal_reference(
    reference: str,
    memory_timestamp: datetime,
) -> datetime | None:
    """Resolve a temporal reference against memory timestamp."""
    resolver = TEMPORAL_PATTERNS.get(reference.lower())
    if resolver:
        return resolver(memory_timestamp)
    return None
```

#### Integration with Recall Commands

```python
# Extend /memory:recall to use reasoning when appropriate

async def handle_recall_command(
    query: str,
    *,
    mode: str = "standard",
    reason: bool = False,  # NEW: Enable reasoning mode
) -> RecallResult:
    """Handle /memory:recall command.

    Args:
        query: The recall query.
        mode: Retrieval mode (reflexive|standard|deep|exhaustive).
        reason: If True, use LLM reasoning over retrieved memories.
    """
    if reason or _query_needs_reasoning(query):
        # Use reasoning service for explicit factual queries
        reasoned_service = get_reasoned_recall_service()
        answer = await reasoned_service.recall_with_reasoning(
            query,
            mode=RetrievalMode(mode),
        )
        return RecallResult(
            answer=answer.answer,
            confidence=answer.confidence,
            reasoning=answer.reasoning,
            memories=answer.source_memories,
        )
    else:
        # Standard retrieval
        recall_service = get_recall_service()
        memories = recall_service.search(query, mode=RetrievalMode(mode))
        return RecallResult(memories=memories)

def _query_needs_reasoning(query: str) -> bool:
    """Heuristic to detect queries that need reasoning."""
    # Questions starting with when/what date/how long ago
    temporal_patterns = [
        r"\bwhen\b",
        r"\bwhat date\b",
        r"\bwhat time\b",
        r"\bhow long ago\b",
        r"\bhow many days\b",
        r"\bwhat day\b",
    ]
    query_lower = query.lower()
    return any(re.search(p, query_lower) for p in temporal_patterns)
```

#### CLI Extension

```bash
# New flag for reasoning mode
/memory:recall "When did Caroline go to the support group?" --reason

# Auto-detect reasoning need for temporal queries
/memory:recall "What date was the deployment?"  # Auto-enables reasoning
```

````

### 10. Hook Integration

#### 10.1 Background Consolidation Hook

The consolidation hook is activated when:
1. The `consolidation` pip extra is installed
2. An observability module is present (you mentioned this as the trigger)

Create `consolidation_hook.py`:

```python
"""Consolidation hook for background memory processing.

Activated when:
- pip install git-notes-memory[consolidation]
- Observability module is installed/detected

Trigger conditions:
- Session idle for N minutes
- Memory count exceeds threshold since last run
- Scheduled interval elapsed
"""

HOOK_CONFIG = {
    "HOOK_CONSOLIDATION_ENABLED": True,
    "HOOK_CONSOLIDATION_IDLE_MINUTES": 30,
    "HOOK_CONSOLIDATION_MEMORY_THRESHOLD": 50,
    "HOOK_CONSOLIDATION_MIN_INTERVAL_HOURS": 24,
}

class ConsolidationHook:
    """Background consolidation hook."""

    async def should_trigger(self) -> bool:
        """Check if consolidation should run."""
        ...

    async def execute(self) -> ConsolidationResult:
        """Run incremental consolidation."""
        ...
````

#### 10.2 SessionStart Hook: Summary Injection

**Critical Requirement:** Consolidated summaries must be injected into Claude Code sessions via the SessionStart hook's `additionalContext` field. The injection must be **idempotent** - new summaries replace old ones, never accumulate.

##### Context Encapsulation Strategy

Use a unique, identifiable wrapper tag that can be detected and replaced:

```python
# Encapsulation tags - MUST be unique and detectable
SUMMARY_CONTEXT_TAG = "memory_consolidated_summaries"
SUMMARY_CONTEXT_START = f"<{SUMMARY_CONTEXT_TAG}>"
SUMMARY_CONTEXT_END = f"</{SUMMARY_CONTEXT_TAG}>"

# Version/timestamp for staleness detection
SUMMARY_CONTEXT_HEADER = """<{tag} version="{version}" generated_at="{timestamp}">
<!-- Memory Consolidation Context - Auto-generated, do not edit -->
<!-- This block is replaced on each session start -->
"""
```

##### SessionStart Hook Extension

Extend the existing `hook_integration.py` SessionStart handling:

```python
@dataclass(frozen=True)
class SummaryInjectionConfig:
    """Configuration for summary injection into sessions."""
    enabled: bool = True
    max_summaries: int = 10
    token_budget: int = 2000  # Max tokens for summary context
    min_confidence: float = 0.7
    prioritize_by: str = "relevance"  # relevance|recency|activation
    include_supersession_context: bool = True


@dataclass(frozen=True)
class SummaryInjectionResult:
    """Result of summary injection."""
    summaries_injected: int
    tokens_used: int
    context_block: str
    replaced_existing: bool


class SessionStartSummaryInjector:
    """Injects consolidated summaries into SessionStart additionalContext.

    Key behaviors:
    1. Detects existing summary block in context and REPLACES it
    2. Never accumulates - one summary block per session
    3. Respects token budget
    4. Prioritizes most relevant summaries
    """

    def __init__(
        self,
        summary_store: SummaryStore,
        recall_service: RecallService,
        config: SummaryInjectionConfig,
    ):
        self.summary_store = summary_store
        self.recall_service = recall_service
        self.config = config

    def inject_summaries(
        self,
        existing_context: str | None,
        session_context: SessionContext,  # Project info, recent files, etc.
    ) -> SummaryInjectionResult:
        """Inject summaries into context, replacing any existing block.

        Args:
            existing_context: Current additionalContext (may contain old summaries).
            session_context: Context about the current session for relevance.

        Returns:
            SummaryInjectionResult with the new context block.
        """
        # Step 1: Remove existing summary block if present
        clean_context, had_existing = self._remove_existing_block(existing_context)

        # Step 2: Select summaries based on relevance to session
        summaries = self._select_summaries(session_context)

        # Step 3: Format summary block within token budget
        summary_block = self._format_summary_block(summaries)

        # Step 4: Return result (caller appends to context)
        return SummaryInjectionResult(
            summaries_injected=len(summaries),
            tokens_used=self._estimate_tokens(summary_block),
            context_block=summary_block,
            replaced_existing=had_existing,
        )

    def _remove_existing_block(
        self,
        context: str | None,
    ) -> tuple[str, bool]:
        """Remove existing summary block from context.

        Returns:
            Tuple of (cleaned context, whether block was found).
        """
        if not context:
            return "", False

        # Find and remove the tagged block
        import re
        pattern = rf"{re.escape(SUMMARY_CONTEXT_START)}.*?{re.escape(SUMMARY_CONTEXT_END)}"
        cleaned, count = re.subn(pattern, "", context, flags=re.DOTALL)

        return cleaned.strip(), count > 0

    def _select_summaries(
        self,
        session_context: SessionContext,
    ) -> list[MemorySummary]:
        """Select most relevant summaries for this session.

        Priority factors:
        1. Semantic relevance to session context (files, project)
        2. Recency of the summary
        3. Activation count (frequently accessed = important)
        4. Confidence score of the summary
        """
        # Get all warm-tier summaries
        all_summaries = self.summary_store.get_by_tier(MemoryTier.WARM)

        if not all_summaries:
            return []

        # Score each summary for relevance
        scored = []
        for summary in all_summaries:
            if summary.confidence.overall < self.config.min_confidence:
                continue

            relevance = self._compute_session_relevance(summary, session_context)
            recency = self._compute_recency_score(summary)
            activation = min(1.0, summary.activation_count / 10)

            # Weighted combination
            if self.config.prioritize_by == "relevance":
                score = 0.5 * relevance + 0.3 * recency + 0.2 * activation
            elif self.config.prioritize_by == "recency":
                score = 0.3 * relevance + 0.5 * recency + 0.2 * activation
            else:  # activation
                score = 0.3 * relevance + 0.2 * recency + 0.5 * activation

            scored.append((summary, score))

        # Sort by score descending, take top N
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:self.config.max_summaries]]

    def _compute_session_relevance(
        self,
        summary: MemorySummary,
        session_context: SessionContext,
    ) -> float:
        """Compute relevance of summary to current session."""
        # Use embedding similarity if available
        if session_context.embedding and summary.embedding:
            return cosine_similarity(session_context.embedding, summary.embedding)

        # Fallback: namespace matching, keyword overlap
        relevance = 0.0
        if session_context.active_namespaces:
            if summary.namespace in session_context.active_namespaces:
                relevance += 0.5

        # Keyword overlap with recent files/context
        if session_context.keywords:
            summary_keywords = set(summary.key_facts)  # Simplified
            overlap = len(summary_keywords & session_context.keywords)
            relevance += min(0.5, overlap * 0.1)

        return min(1.0, relevance)

    def _format_summary_block(
        self,
        summaries: list[MemorySummary],
    ) -> str:
        """Format summaries into injectable context block.

        Stays within token budget by truncating if necessary.
        """
        if not summaries:
            return ""

        timestamp = datetime.now(UTC).isoformat()
        version = hashlib.sha256(
            "".join(s.id for s in summaries).encode()
        ).hexdigest()[:8]

        lines = [
            SUMMARY_CONTEXT_HEADER.format(
                tag=SUMMARY_CONTEXT_TAG,
                version=version,
                timestamp=timestamp,
            ),
            "",
            "## Project Memory Context",
            "",
            "The following summarizes key decisions, learnings, and context from this project's history:",
            "",
        ]

        tokens_used = self._estimate_tokens("\n".join(lines))

        for summary in summaries:
            summary_text = self._format_single_summary(summary)
            summary_tokens = self._estimate_tokens(summary_text)

            if tokens_used + summary_tokens > self.config.token_budget:
                # Add truncation notice and stop
                lines.append("<!-- Additional summaries truncated due to token budget -->")
                break

            lines.append(summary_text)
            lines.append("")
            tokens_used += summary_tokens

        lines.append(SUMMARY_CONTEXT_END)

        return "\n".join(lines)

    def _format_single_summary(self, summary: MemorySummary) -> str:
        """Format a single summary for context injection."""
        parts = [
            f"### {summary.namespace.title()} ({summary.temporal_range[0].strftime('%Y-%m-%d')} - {summary.temporal_range[1].strftime('%Y-%m-%d')})",
            "",
            summary.summary,
            "",
        ]

        if summary.key_facts:
            parts.append("**Key facts:**")
            for fact in summary.key_facts[:5]:  # Limit facts
                parts.append(f"- {fact}")
            parts.append("")

        if summary.decisions:
            parts.append("**Decisions:**")
            for decision in summary.decisions[:3]:  # Limit decisions
                parts.append(f"- {decision.decision}")
                if decision.rationale:
                    parts.append(f"  - Rationale: {decision.rationale}")
            parts.append("")

        if summary.superseded_facts:
            parts.append("**Note - superseded information:**")
            for sf in summary.superseded_facts[:2]:
                parts.append(f"- ~~{sf.original_fact}~~ → {sf.superseded_by}")
            parts.append("")

        return "\n".join(parts)

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token)."""
        return len(text) // 4


# Integration with existing SessionStart hook
def get_session_start_additional_context(
    session_context: SessionContext,
    existing_context: str | None = None,
) -> str:
    """Get additionalContext for SessionStart hook.

    This is called by the existing hook_integration.py SessionStart handler.
    It ensures summary context is properly injected/replaced.
    """
    # Check if consolidation is available
    if not is_consolidation_available():
        return existing_context or ""

    try:
        injector = get_summary_injector()
        result = injector.inject_summaries(existing_context, session_context)

        if result.replaced_existing:
            logger.debug(
                "Replaced existing summary block with %d summaries (%d tokens)",
                result.summaries_injected,
                result.tokens_used,
            )
        else:
            logger.debug(
                "Injected %d summaries (%d tokens)",
                result.summaries_injected,
                result.tokens_used,
            )

        # Combine: clean existing context + new summary block
        clean_existing = injector._remove_existing_block(existing_context)[0]
        if clean_existing:
            return f"{clean_existing}\n\n{result.context_block}"
        return result.context_block

    except Exception as e:
        logger.warning("Failed to inject summaries: %s", e)
        return existing_context or ""
```

##### Hook Configuration

```python
# Add to HOOK_CONFIG
HOOK_CONFIG.update({
    "HOOK_SESSION_START_SUMMARIES_ENABLED": True,
    "HOOK_SESSION_START_SUMMARIES_MAX": 10,
    "HOOK_SESSION_START_SUMMARIES_TOKEN_BUDGET": 2000,
    "HOOK_SESSION_START_SUMMARIES_MIN_CONFIDENCE": 0.7,
    "HOOK_SESSION_START_SUMMARIES_PRIORITIZE": "relevance",  # relevance|recency|activation
})
```

##### Context Block Format Example

```markdown
<memory_consolidated_summaries version="a1b2c3d4" generated_at="2025-01-20T10:30:00Z">

<!-- Memory Consolidation Context - Auto-generated, do not edit -->
<!-- This block is replaced on each session start -->

## Project Memory Context

The following summarizes key decisions, learnings, and context from this project's history:

### Decisions (2025-01-10 - 2025-01-17)

Selected FastAPI as the primary web framework due to native async support and automatic OpenAPI generation. Performance testing confirmed 3x throughput improvement over Flask baseline.

**Key facts:**

- FastAPI selected as primary web framework
- Async support was deciding factor
- 3x throughput improvement measured

**Decisions:**

- Use FastAPI over Flask
  - Rationale: Native async, OpenAPI generation, performance

**Note - superseded information:**

- ~~Initial estimate of 2x improvement~~ → Measured 3x improvement

### Learnings (2025-01-05 - 2025-01-15)

Database connection pooling requires careful tuning for async workloads. SQLAlchemy 2.0 async support works well with asyncpg but requires explicit session management.

**Key facts:**

- asyncpg preferred for PostgreSQL async
- Connection pool size should match worker count
- Session-per-request pattern recommended

</memory_consolidated_summaries>
```

##### Idempotency Guarantees

1. **Tag-based detection**: The `<memory_consolidated_summaries>` wrapper is unique and detectable
2. **Full replacement**: Entire block is removed before new one is added
3. **Version tracking**: Hash of summary IDs enables staleness detection
4. **Timestamp**: `generated_at` shows when context was created
5. **No accumulation**: Regex removal ensures only one block exists

##### Integration Point

The existing `hook_integration.py` has a SessionStart handler. Modify it to call the summary injector:

```python
# In hook_integration.py, modify the SessionStart handler:

async def handle_session_start(event: SessionStartEvent) -> HookResult:
    """Handle SessionStart hook event."""

    # ... existing memory injection logic ...

    # NEW: Inject consolidated summaries
    if is_consolidation_available():
        session_context = SessionContext(
            project_path=event.project_path,
            recent_files=event.recent_files,
            # ... extract context from event
        )

        additional_context = get_session_start_additional_context(
            session_context=session_context,
            existing_context=event.additional_context,
        )

        return HookResult(
            additional_context=additional_context,
            # ... other fields
        )

    # ... fallback to existing behavior ...
```

### 11. Feature Gating (pip extras)

In `pyproject.toml`:

```toml
[project.optional-dependencies]
consolidation = [
    "scikit-learn>=1.3",  # For clustering
    "openai>=1.0",        # For GPT-5-nano/mini
    "httpx>=0.25",        # For LM Studio HTTP calls
]
```

Lazy import pattern:

```python
def get_consolidation_service() -> ConsolidationService:
    try:
        from .consolidation_service import ConsolidationService
        # ... initialization
    except ImportError as e:
        raise NotImplementedError(
            "Consolidation requires: pip install git-notes-memory[consolidation]"
        ) from e
```

When the extra is NOT installed:

- All consolidation imports succeed (lazy)
- Service factory raises `NotImplementedError`
- Existing functionality unimpeded
- No sklearn/openai loaded

### 12. CLI Commands

Extend existing `/memory:*` commands:

```
/memory:consolidate [--full] [--dry-run]  # Trigger consolidation
/memory:status --verbose                   # Include consolidation state
/memory:tiers                              # Show tier distribution
/memory:edges <memory_id>                  # Show memory relationships
/memory:recall <query> --mode=deep         # Include cold tier
```

### 14. Testing Requirements

1. **Unit tests:**

   - Retention score calculation
   - Tier assignment logic
   - Clustering algorithm (mock embeddings)
   - LLM response parsing (mock client)
   - Summary block formatting
   - Context replacement logic
   - Temporal reference detection
   - Temporal resolution against timestamps

2. **Integration tests:**

   - Full consolidation pipeline
   - Git notes read/write for new refs
   - RecallService with tier filtering
   - Summary injection into SessionStart
   - ReasonedRecallService end-to-end

3. **Property-based tests:**

   - Retention score always in [0, 1]
   - Tier transitions follow hierarchy (hot→warm→cold→archived)
   - Consolidation is idempotent

4. **Idempotency tests for SessionStart:**

   ```python
   def test_summary_injection_replaces_not_accumulates():
       """Multiple SessionStart events must not accumulate context."""
       injector = get_summary_injector()

       # First injection
       result1 = injector.inject_summaries(None, session_context)
       context1 = result1.context_block

       # Second injection with existing context
       result2 = injector.inject_summaries(context1, session_context)
       context2 = result2.context_block

       # Count summary blocks - must be exactly 1
       block_count = context2.count(SUMMARY_CONTEXT_START)
       assert block_count == 1, f"Expected 1 block, found {block_count}"
       assert result2.replaced_existing is True

       # Third injection
       result3 = injector.inject_summaries(context2, session_context)
       context3 = result3.context_block

       block_count = context3.count(SUMMARY_CONTEXT_START)
       assert block_count == 1

   def test_summary_injection_preserves_other_context():
       """Injection must preserve non-summary context."""
       existing = "Some other context\n\nMore stuff"
       result = injector.inject_summaries(existing, session_context)

       # Original context preserved
       assert "Some other context" in result.context_block
       assert "More stuff" in result.context_block
       # Summary block added
       assert SUMMARY_CONTEXT_START in result.context_block
   ```

5. **Temporal reasoning tests:**

   ```python
   def test_temporal_resolution_yesterday():
       """'Yesterday' resolves correctly against memory timestamp."""
       memory_timestamp = datetime(2023, 5, 8, 14, 30, 0, tzinfo=UTC)
       resolved = resolve_temporal_reference("yesterday", memory_timestamp)
       assert resolved.date() == date(2023, 5, 7)

   def test_temporal_resolution_last_week():
       """'Last week' resolves to ~7 days before memory timestamp."""
       memory_timestamp = datetime(2023, 5, 15, 10, 0, 0, tzinfo=UTC)
       resolved = resolve_temporal_reference("last week", memory_timestamp)
       assert resolved.date() == date(2023, 5, 8)

   def test_reasoned_recall_temporal_query():
       """Temporal query correctly resolves relative references."""
       # Memory: "Caroline went to support group yesterday" (recorded 2023-05-08)
       memory = Memory(
           content="Caroline said she went to the LGBTQ support group yesterday",
           timestamp=datetime(2023, 5, 8, 14, 30, tzinfo=UTC),
           ...
       )

       service = get_reasoned_recall_service()
       answer = await service.recall_with_reasoning(
           "When did Caroline go to the LGBTQ support group?"
       )

       assert "2023-05-07" in answer.answer or "7 May 2023" in answer.answer
       assert answer.confidence > 0.8
       assert len(answer.temporal_resolutions) > 0
       assert answer.temporal_resolutions[0].original_text == "yesterday"
       assert answer.temporal_resolutions[0].resolved_date.date() == date(2023, 5, 7)
   ```

6. **Mock LLM fixture:**
   ```python
   @pytest.fixture
   def mock_consolidation_llm(mocker):
       """Return deterministic LLM responses."""
       ...
   ```

### 15. Implementation Order

**Phase 1: Models and Config** (no LLM)

- [ ] Add new models to `models.py`
- [ ] Extend `SubconsciousnessConfig`
- [ ] Create git notes stores for metadata/summaries/edges
- [ ] Implement retention score calculation
- [ ] Add tier assignment logic
- [ ] Unit tests for scoring

**Phase 2: Clustering and Storage**

- [ ] Implement semantic clustering
- [ ] Create `MetadataStore`, `SummaryStore`, `EdgeStore`
- [ ] Extend sqlite schema for tiers
- [ ] Integration tests for storage

**Phase 3: LLM Integration - Consolidation**

- [ ] Create summarization prompts
- [ ] Create supersession detection prompts
- [ ] Implement `ConsolidationService` pipeline
- [ ] Tests with mock LLM

**Phase 4: RecallService Extension**

- [ ] Add `RetrievalMode` enum
- [ ] Implement tier filtering
- [ ] Add activation tracking
- [ ] Include summaries in search results

**Phase 4.1: Reasoning Layer for Explicit Recall**

- [ ] Create `ReasonedRecallService`
- [ ] Implement temporal reference detection
- [ ] Implement temporal resolution against memory timestamps
- [ ] Create reasoning prompts (REASONING_SYSTEM_PROMPT, REASONING_USER_PROMPT)
- [ ] Add `ReasonedAnswer` model with provenance tracking
- [ ] Auto-detection heuristic for queries needing reasoning
- [ ] Add `--reason` flag to `/memory:recall`
- [ ] Tests for temporal resolution accuracy

**Phase 5: SessionStart Hook Integration**

- [ ] Create `SessionStartSummaryInjector`
- [ ] Implement context block encapsulation (tag-based)
- [ ] Implement replacement logic (remove existing + add new)
- [ ] Add summary selection/prioritization
- [ ] Token budget enforcement
- [ ] Wire into existing `hook_integration.py` SessionStart handler
- [ ] Tests for idempotency (multiple Start events don't accumulate)

**Phase 6: Background Hook and CLI**

- [ ] Create `ConsolidationHook` for background processing
- [ ] Wire up trigger conditions (observability module detection)
- [ ] Add CLI commands
- [ ] End-to-end tests

## Non-Goals (Out of Scope)

- Changing existing Memory model structure
- Modifying how CaptureService or RecallService work (only extend)
- Breaking backward compatibility with existing git notes
- Implementing real-time consolidation (always async/background)
- Supporting provider-specific features beyond OpenAI-compatible API

## Success Criteria

1. **No regression**: Existing tests pass, functionality unchanged
2. **Tier distribution**: After consolidation, memories correctly distributed by retention
3. **Summary quality**: Generated summaries preserve key decisions and facts
4. **Supersession accuracy**: >95% valid (manual audit sample)
5. **Performance**: Consolidation of 1000 memories < 5 minutes
6. **Feature gating**: Works without extras, fails gracefully with helpful message
7. **SessionStart idempotency**: Multiple Start events produce exactly 1 summary block (no accumulation)
8. **Context preservation**: Non-summary additionalContext survives injection/replacement
9. **Token budget compliance**: Summary injection never exceeds configured limit
10. **Temporal reasoning accuracy**: Relative temporal references ("yesterday", "last week") correctly resolved against memory timestamps in >95% of cases
