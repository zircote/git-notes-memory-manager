# Memory Consolidation: Requirements Summary

## Problem

The subconsciousness module has config toggles for consolidation, forgetting, surfacing, and linking - but these features aren't implemented. Without them:

1. Memory growth is unbounded - early memories pollute search results
2. No temporal decay - 6-month-old obsolete decision equals yesterday's
3. No abstraction - 50 related memories consume 50x the retrieval cost
4. Contradictions unresolved - superseded info returned alongside current

## Solution

Extend the existing subconsciousness module with memory consolidation that runs asynchronously to:

- **Decay**: Compute retention scores, demote stale memories to cold/archived tiers
- **Cluster**: Group semantically similar memories (regardless of time)
- **Summarize**: Generate consolidated summaries via LLM
- **Supersede**: Detect when newer memories invalidate older via LLM judgment
- **Link**: Create edges between related memories

## Key Design Decisions

| Decision         | Choice                               | Rationale                                                   |
| ---------------- | ------------------------------------ | ----------------------------------------------------------- |
| LLM Provider     | GPT-5-nano/mini → LM Studio → Ollama | User requirement: cheap cloud + local fallback              |
| Decay parameters | Conservative defaults, all tunable   | Start safe, let users adjust                                |
| Clustering       | Semantic similarity, ignore time     | Related memories from different sessions should consolidate |
| Supersession     | LLM judgment                         | Heuristics miss nuance, LLM can explain reasoning           |
| Edge storage     | Separate git notes ref               | Clean separation, doesn't pollute existing refs             |
| Hook trigger     | Observability module installed       | User requirement: tied to optional observability extra      |
| Feature gating   | pip extras `[consolidation]`         | Works without unimpeded, activates on install               |

## New Components

```
subconsciousness/
├── models.py              # ADD: MemoryTier, RetentionScore, MemoryMetadata,
│                          #      MemorySummary, MemoryEdge, ConsolidationResult,
│                          #      ReasonedAnswer, TemporalReference
├── config.py              # EXTEND: retention params, tier thresholds,
│                          #         session start summary config
├── consolidation_service.py       # NEW: main consolidation pipeline
├── consolidation_prompts.py       # NEW: LLM prompts for summarization/supersession
├── consolidation_store.py         # NEW: git notes CRUD for meta/summaries/edges
├── consolidation_hook.py          # NEW: background trigger
├── session_summary_injector.py    # NEW: SessionStart context injection
├── reasoned_recall_service.py     # NEW: LLM reasoning over retrieved memories
├── reasoning_prompts.py           # NEW: temporal reasoning prompts
├── temporal_resolver.py           # NEW: resolve "yesterday" etc. against timestamps
├── retention.py                   # NEW: score calculation
└── hook_integration.py            # EXTEND: wire in summary injection
```

## Git Notes Schema

```
refs/notes/mem/            # EXISTING - raw memories (unchanged)
refs/notes/mem-meta/       # NEW - tier, activation_count, retention scores
refs/notes/mem-summaries/  # NEW - consolidated summaries
refs/notes/mem-edges/      # NEW - supersedes/consolidates/references edges
refs/notes/mem-runs/       # NEW - consolidation run logs
```

## Config Additions

```python
# Already exist but not wired up:
consolidation_enabled: bool = True
consolidation_threshold: float = 0.85
forgetting_enabled: bool = True
archive_threshold: float = 0.3

# New:
retention_half_life_days: float = 30.0
activation_boost: float = 0.1
hot_threshold: float = 0.6
warm_threshold: float = 0.3
min_cluster_size: int = 3
max_cluster_size: int = 20
consolidation_interval_hours: int = 24
```

## RecallService Extension

```python
class RetrievalMode(str, Enum):
    REFLEXIVE = "reflexive"    # Hot only (auto-injection)
    STANDARD = "standard"      # Hot + Warm (default search)
    DEEP = "deep"              # + Cold (explicit historical)
    EXHAUSTIVE = "exhaustive"  # + Archived (audit/debug)

# Each retrieval increments activation_count (spaced repetition)
```

## Reasoning Layer for Explicit Recall

**Problem:** Raw retrieval returns memories with relative temporal references ("yesterday", "last week") that can't be resolved without reasoning over timestamps.

```
Q: When did Caroline go to the LGBTQ support group?
Expected: 7 May 2023
Retrieved: "She said she went 'yesterday'" (memory from 8 May 2023)
Returned: "I cannot find this information" ❌
```

**Solution:** LLM-powered `ReasonedRecallService` that:

1. Retrieves memories WITH timestamps
2. Detects temporal references ("yesterday", "last week", "this morning")
3. Resolves them against memory creation dates
4. Synthesizes reasoned answer with provenance

### ReasonedAnswer Model

```python
@dataclass(frozen=True)
class ReasonedAnswer:
    answer: str                    # Direct answer
    confidence: float              # 0.0-1.0
    reasoning: str                 # How answer was derived
    temporal_resolutions: tuple[TemporalReference, ...]
    source_memories: tuple[MemoryResult, ...]
    requires_inference: bool       # True if reasoning was needed
```

### Auto-Detection

Queries starting with temporal patterns auto-enable reasoning:

- "when did...", "what date...", "how long ago...", "what day..."

### CLI

```bash
/memory:recall "When did X happen?" --reason  # Explicit reasoning
/memory:recall "What date was the deployment?" # Auto-detects need
```

## SessionStart Hook: Summary Injection

**Critical:** Summaries must be injected into Claude Code sessions via `additionalContext` - but must **replace, not accumulate**.

### Encapsulation Strategy

```xml
<memory_consolidated_summaries version="a1b2c3d4" generated_at="2025-01-20T10:30:00Z">
<!-- Auto-generated, replaced on each session start -->

## Project Memory Context
...summaries here...

</memory_consolidated_summaries>
```

### Idempotency Guarantees

1. **Tag-based detection** - unique wrapper enables find/replace
2. **Full replacement** - regex removes entire block before adding new
3. **Version hash** - detects if summaries changed
4. **Token budget** - won't exceed configured limit (default 2000)
5. **No accumulation** - guaranteed single block per context

### Config

```python
HOOK_SESSION_START_SUMMARIES_ENABLED = True
HOOK_SESSION_START_SUMMARIES_MAX = 10
HOOK_SESSION_START_SUMMARIES_TOKEN_BUDGET = 2000
HOOK_SESSION_START_SUMMARIES_MIN_CONFIDENCE = 0.7
HOOK_SESSION_START_SUMMARIES_PRIORITIZE = "relevance"  # relevance|recency|activation
```

### Selection Priority

Summaries selected based on:

1. Semantic relevance to current session (files, project)
2. Recency of the summary
3. Activation count (frequently accessed)
4. Confidence score

## Success Criteria

1. Existing tests pass unchanged
2. Tier distribution reflects retention scores after consolidation
3. Summaries preserve decisions and key facts
4. Supersession detection >95% accurate
5. 1000 memories consolidated in <5 minutes
6. Feature-gated: graceful error without `[consolidation]` extra
7. **SessionStart idempotency**: Multiple Start events produce exactly 1 summary block
8. **Context preservation**: Non-summary context survives injection/replacement
9. **Token budget**: Summary injection never exceeds configured limit
10. **Temporal reasoning**: Relative references ("yesterday") correctly resolved >95% of cases
