---
document_type: decisions
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-26T00:10:00Z
status: draft
---

# Architecture Decision Records

This document captures the key architectural decisions for the LLM-powered subconsciousness feature, following the ADR format.

## ADR-001: Provider-Agnostic LLM Client Abstraction

**Status**: Accepted

**Context**:
The subconsciousness requires LLM capabilities for transcript analysis, relationship discovery, abstraction synthesis, and intuition ranking. Users have different preferences and constraints around LLM providers:
- Some prefer Anthropic Claude for alignment with Claude Code ecosystem
- Some prefer OpenAI for existing API keys or model preferences
- Some require offline capability via local models

**Decision**:
Implement a provider-agnostic LLM client using Python's Protocol pattern:
- `LLMProvider` protocol defines the interface
- `AnthropicProvider`, `OpenAIProvider`, `OllamaProvider` implementations
- `LLMClient` unifies provider selection, fallback, rate limiting, and batching

**Consequences**:
- **Positive**: Users can choose their preferred provider; fallback enables resilience
- **Positive**: New providers can be added without changing agent code
- **Negative**: Must maintain multiple provider implementations
- **Negative**: Provider-specific features (tool use, JSON mode) need abstraction

**Alternatives Considered**:
1. **Anthropic-only**: Simpler but limits user choice
2. **LangChain**: Adds heavy dependency, abstracts too much
3. **LiteLLM**: Good option but adds external dependency

---

## ADR-002: Confidence-Based Auto-Capture with Review Queue

**Status**: Accepted

**Context**:
Implicit capture must balance automation with user control. Capturing everything creates noise; requiring review for everything defeats automation benefits.

The CognitiveSubstrate research recommends: "High-confidence outputs are auto-accepted; low-confidence ones are queued for review."

**Decision**:
Implement a two-threshold system:
- **Auto-capture threshold (0.9)**: Above this, capture automatically
- **Review threshold (0.7)**: Between 0.7-0.9, queue for user review
- **Discard (<0.7)**: Below review threshold, don't capture

Users can adjust thresholds via environment variables.

**Consequences**:
- **Positive**: High-confidence captures happen without friction
- **Positive**: Users maintain control over uncertain captures
- **Positive**: Thresholds are tunable per user preference
- **Negative**: Users must periodically review pending captures
- **Negative**: Initial thresholds may need calibration

**Alternatives Considered**:
1. **Always auto-capture**: Too noisy, users lose trust
2. **Always require review**: Defeats automation benefit
3. **Single threshold**: Less nuanced, binary decision

---

## ADR-003: Bidirectional Memory Links

**Status**: Accepted

**Context**:
Semantic linking must enable graph traversal in both directions. If Memory A "SUPPORTS" Memory B, traversing from B should discover A.

**Decision**:
Implement bidirectional links at the storage layer:
- Links stored once with `source_id` and `target_id`
- Queries include both directions: `WHERE source_id = ? OR target_id = ?`
- Link type semantics are direction-aware (SUPPORTS has different meaning forward vs. reverse)

**Consequences**:
- **Positive**: Single storage, bidirectional access
- **Positive**: Graph traversal works from any starting point
- **Negative**: Query complexity increases slightly
- **Negative**: Link type interpretation requires direction awareness

**Alternatives Considered**:
1. **Store both directions**: Doubles storage, risk of inconsistency
2. **One-way links only**: Limits discovery, graph traversal incomplete
3. **Separate forward/reverse tables**: Overcomplicated

---

## ADR-004: Archive Instead of Delete for Forgetting

**Status**: Accepted

**Context**:
The "forgetting" capability must balance memory hygiene with audit trail preservation. True deletion is irreversible and loses provenance.

The CognitiveSubstrate research emphasizes: "Memories are archived or suppressed, not deleted."

**Decision**:
Implement soft-delete via archival:
- Set `archived_at` timestamp in `memory_decay` table
- Remove from active search index
- Preserve in SQLite and git notes
- Provide unarchive capability if needed

**Consequences**:
- **Positive**: No data loss, audit trail preserved
- **Positive**: Archival is reversible
- **Positive**: Git notes remain for sync/backup
- **Negative**: Storage doesn't decrease (but SQLite handles this fine)
- **Negative**: Archived memories still visible in git notes

**Alternatives Considered**:
1. **Hard delete**: Irreversible, loses history
2. **Move to archive namespace**: Complex, namespace pollution
3. **Tombstone records**: Extra storage, query complexity

---

## ADR-005: Async LLM Calls with Non-Blocking Hooks

**Status**: Accepted

**Context**:
LLM API calls have latency (100ms-5s). Hooks must not block the Claude Code agent's responsiveness.

**Decision**:
All LLM calls are async and non-blocking:
- Use Python `asyncio` for async/await
- Hooks trigger LLM analysis but don't wait for completion
- Results are stored and surfaced in subsequent interactions
- Timeout protection prevents hanging

**Consequences**:
- **Positive**: Hooks remain fast (<50ms overhead)
- **Positive**: LLM latency doesn't impact user experience
- **Negative**: Results may not be immediately available
- **Negative**: Async complexity in hook handlers

**Alternatives Considered**:
1. **Synchronous calls**: Would block agent, poor UX
2. **Background threads**: Less integration with asyncio ecosystem
3. **Fire-and-forget**: No error handling, results lost

---

## ADR-006: Typed Relationship Links with Five Core Types

**Status**: Accepted

**Context**:
Memory relationships need categorization for meaningful graph traversal and conflict detection. Too many types create confusion; too few lose semantic value.

**Decision**:
Define five core link types:
- **SUPPORTS**: Memory A provides evidence for Memory B
- **CONTRADICTS**: Memory A conflicts with Memory B
- **SUPERSEDES**: Memory A replaces Memory B (newer decision)
- **EXTENDS**: Memory A adds detail to Memory B
- **REQUIRES**: Memory A depends on Memory B

**Consequences**:
- **Positive**: Clear semantics for each type
- **Positive**: CONTRADICTS enables conflict detection
- **Positive**: SUPERSEDES enables temporal reasoning
- **Negative**: May not cover all relationship nuances
- **Negative**: LLM must correctly classify relationships

**Alternatives Considered**:
1. **Untyped links**: Lose semantic value
2. **Many types (10+)**: Hard to distinguish, LLM confusion
3. **Hierarchical types**: Overcomplicated for initial implementation

---

## ADR-007: SQLite Schema Versioning with Additive Migrations

**Status**: Accepted

**Context**:
The subconsciousness adds three new tables (`memory_links`, `memory_decay`, `implicit_captures`) requiring schema migration from version 2 to 3.

**Decision**:
Use additive-only migrations:
- Increment `SCHEMA_VERSION` to 3
- Only add tables and columns, never remove
- Migrations are idempotent (re-runnable safely)
- Preserve existing data during migration

**Consequences**:
- **Positive**: Safe migrations, no data loss
- **Positive**: Rollback is trivial (ignore new tables)
- **Positive**: Existing functionality unaffected
- **Negative**: Can't remove deprecated columns
- **Negative**: Schema may accumulate cruft over time

**Alternatives Considered**:
1. **Destructive migrations**: Risk data loss
2. **Separate database**: Complexity, sync issues
3. **No versioning**: Breaks existing installations

---

## ADR-008: Decay Score Formula with Weighted Factors

**Status**: Accepted

**Context**:
Memory decay must balance multiple factors: recency, frequency, project relevance, and supersession. A simple time-based decay is insufficient.

**Decision**:
Implement multi-factor decay with configurable weights:

```
decay_score = (
    w_recency * recency_factor +      # Days since last access
    w_frequency * frequency_factor +   # Access count (log-scaled)
    w_relevance * relevance_factor +   # Project still active?
    w_supersession * supersession_factor  # Has SUPERSEDES link?
)
```

Default weights: recency=0.4, frequency=0.3, relevance=0.2, supersession=0.1

**Consequences**:
- **Positive**: Nuanced decay considering multiple signals
- **Positive**: Weights tunable per use case
- **Negative**: Formula may need calibration
- **Negative**: More complex than simple time decay

**Alternatives Considered**:
1. **Time-only decay**: Ignores frequency, too simplistic
2. **LLM-based decay**: Too expensive, slow
3. **Manual archival only**: No automation benefit

---

## ADR-009: Adversarial Detection with Pattern Matching First

**Status**: Accepted

**Context**:
Memory poisoning is a security concern (per CognitiveSubstrate research). Detection must be fast enough for every capture.

**Decision**:
Implement two-tier adversarial detection:
1. **Fast path (regex)**: Pattern match for known injection patterns
2. **Slow path (LLM)**: Deep analysis for contradictions, authority claims

The fast path runs on every capture; the slow path runs on flagged content or periodically.

**Consequences**:
- **Positive**: Fast path adds negligible latency
- **Positive**: Common attacks blocked immediately
- **Negative**: Regex can't catch novel attacks
- **Negative**: False positives possible with pattern matching

**Alternatives Considered**:
1. **LLM-only**: Too slow for every capture
2. **No detection**: Security risk
3. **Blocklist-only**: Too rigid, misses variations

---

## ADR-010: Proactive Surfacing Rate Limiting

**Status**: Accepted

**Context**:
Proactive surfacing could become annoying if it triggers too frequently. Users need control over surfacing volume.

**Decision**:
Implement multi-level rate limiting:
- **Per-session limit**: Max 10 surfaces per session
- **Per-file limit**: Max 2 surfaces per file per session
- **Cooldown**: 5 minutes between surfaces for same memory
- **Configurable**: All limits adjustable via environment

**Consequences**:
- **Positive**: Prevents surfacing spam
- **Positive**: Users can tune aggressiveness
- **Negative**: May miss relevant memories if limits hit
- **Negative**: Adds complexity to surfacing logic

**Alternatives Considered**:
1. **No limits**: Risk of spam, user frustration
2. **Fixed limits**: No user control
3. **Adaptive limits**: Complex, needs learning phase

---

## ADR-011: Meta-Memory for Consolidation Results

**Status**: Accepted

**Context**:
When memories are consolidated, the result needs a home. Options include updating one of the originals or creating a new synthesized memory.

**Decision**:
Create new meta-memories in a "meta" namespace:
- Meta-memory is a new Memory entity
- Links to source memories with `CONSOLIDATES` relationship
- Source memories are not deleted (just accelerate decay)
- Meta-memory has its own embedding for search

**Consequences**:
- **Positive**: Original memories preserved
- **Positive**: Clear provenance via links
- **Positive**: Meta-memory independently searchable
- **Negative**: Adds more memories (potentially)
- **Negative**: Source decay must be managed

**Alternatives Considered**:
1. **Update one original**: Loses other originals' context
2. **Merge into first**: Arbitrary, loses structure
3. **Delete originals**: Loses provenance

---

## ADR-012: Batch LLM Requests for Cost Optimization

**Status**: Accepted

**Context**:
Multiple LLM operations (transcript analysis, link discovery, consolidation) can happen in sequence or parallel. Individual API calls are costly.

**Decision**:
Implement request batching in LLMClient:
- Batch multiple prompts into single API call where supported
- Use timeout-based flush (100ms) or size-based flush (10 requests)
- Handle partial batch failures gracefully

For providers without native batching, simulate via concurrent requests with rate limiting.

**Consequences**:
- **Positive**: Reduces API call count by 50%+
- **Positive**: Reduces cost proportionally
- **Negative**: Adds latency for first request in batch
- **Negative**: Partial failure handling is complex

**Alternatives Considered**:
1. **No batching**: Higher costs, more API calls
2. **Manual batching only**: User burden
3. **Queue-based**: Adds infrastructure complexity

---

## ADR-013: Local-First with Optional Cloud

**Status**: Accepted

**Context**:
Users have varying connectivity and privacy requirements. The system should work offline but benefit from cloud LLMs when available.

**Decision**:
Implement local-first architecture with cloud enhancement:
- Core functionality (capture, recall, index) works offline
- LLM features enhance but don't block operations
- Ollama provides offline LLM capability
- Graceful degradation when no LLM available

**Consequences**:
- **Positive**: Works without internet
- **Positive**: Works without API keys (basic mode)
- **Positive**: User controls cloud usage
- **Negative**: Offline LLMs less capable
- **Negative**: Feature disparity between modes

**Alternatives Considered**:
1. **Cloud-only**: Requires internet, privacy concerns
2. **Local-only**: Misses cloud LLM capabilities
3. **Hybrid with sync**: Complex, sync conflicts

---

## Decision Log

| ADR | Date | Status | Summary |
|-----|------|--------|---------|
| 001 | 2025-12-26 | Accepted | Provider-agnostic LLM client abstraction |
| 002 | 2025-12-26 | Accepted | Confidence-based auto-capture with review queue |
| 003 | 2025-12-26 | Accepted | Bidirectional memory links |
| 004 | 2025-12-26 | Accepted | Archive instead of delete for forgetting |
| 005 | 2025-12-26 | Accepted | Async LLM calls with non-blocking hooks |
| 006 | 2025-12-26 | Accepted | Typed relationship links with five core types |
| 007 | 2025-12-26 | Accepted | SQLite schema versioning with additive migrations |
| 008 | 2025-12-26 | Accepted | Decay score formula with weighted factors |
| 009 | 2025-12-26 | Accepted | Adversarial detection with pattern matching first |
| 010 | 2025-12-26 | Accepted | Proactive surfacing rate limiting |
| 011 | 2025-12-26 | Accepted | Meta-memory for consolidation results |
| 012 | 2025-12-26 | Accepted | Batch LLM requests for cost optimization |
| 013 | 2025-12-26 | Accepted | Local-first with optional cloud |

---

## Related Documents

- [REQUIREMENTS.md](./REQUIREMENTS.md) - Product Requirements Document
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Technical Architecture
- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) - Phased Implementation
- [CognitiveSubstrate/ARCHITECTURE_BRIEF.md](../../../research/CognitiveSubstrate/ARCHITECTURE_BRIEF.md) - Research Foundation
