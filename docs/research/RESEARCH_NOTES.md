# Research Notes: Git-Notes Memory Manager

## Evidence Collection Date: 2025-12-21

---

## Key Findings

### Finding 1: Git Notes as Distributed Memory Store
**Source**: Core architecture analysis, git_ops.py
**Evidence**:
- Memories stored under `refs/notes/mem/{namespace}`
- 10 namespaces: inception, elicitation, research, decisions, progress, blockers, reviews, learnings, retrospective, patterns
- YAML front matter + markdown body format
- Append-only operations for concurrency safety

**Confidence**: HIGH - Core architectural decision with extensive documentation

### Finding 2: Progressive Hydration Model
**Source**: models.py, recall.py
**Evidence**:
- Three levels: SUMMARY → FULL → FILES
- SUMMARY: Metadata only (sub-millisecond)
- FULL: Complete note content (~10ms git show)
- FILES: File snapshots from commit (variable, max 20 files)

**Real Example from Session**:
```xml
<memory id="decisions:5da308d:19" namespace="decisions" hydration="summary">
  <summary>Lazy loading via __getattr__ to avoid embedding model import penalty</summary>
</memory>
```
When hydrated to FULL, expands to complete ADR with context, rationale, and alternatives.

**Confidence**: HIGH - Observed in actual session context injection

### Finding 3: Hook-Based Capture Pipeline
**Source**: Hook handlers analysis
**Evidence**:
- 5 hook points: SessionStart, UserPromptSubmit, PostToolUse, PreCompact, Stop
- Signal detection via regex patterns with confidence scoring
- Block markers (`▶ namespace ───`) detected at 0.99 confidence
- Auto-capture at session end (Stop hook) captured 5 memories at 00:46:36

**Real Example from Session**:
Stop hook log at 2025-12-21 00:46:36:
```
Found 5 signals in transcript
Auto-capture result: 5 captured, 0 remaining
  Captured: decisions:5da308d:17 - '...memories**: Use markers anywhere...'
  Captured: decisions:5da308d:18 - 'Git notes as source of truth...'
  Captured: decisions:5da308d:19 - 'Lazy loading via __getattr__...'
  Captured: decisions:5da308d:20 - 'Confidence-based tiered capture...'
  Captured: decisions:5da308d:21 - 'Adaptive token budget...'
```

**Confidence**: HIGH - Observed in production logs during debugging session

### Finding 4: Context Injection via additionalContext
**Source**: session_start_handler.py, context_builder.py
**Evidence**:
- SessionStart hook outputs JSON with `hookSpecificOutput.additionalContext`
- Contains `<memory_context>` XML with working memory + semantic context
- Token budget adaptive based on project complexity

**Real Example from This Session**:
```xml
<memory_context project="git-notes-memory" timestamp="2025-12-21T05:52:40.658071+00:00" memories_retrieved="13">
  <recall_notice priority="high">Retrieved 13 memories from prior sessions.</recall_notice>
  <working_memory>
    <blockers title="Active Blockers">
      <memory id="blockers:5da308d:0" namespace="blockers">
        <summary>...markers, and semantic patterns.</summary>
        <tags>auto-captured, post-tool-use, file:userpromptsubmit.py</tags>
      </memory>
    </blockers>
    <decisions title="Recent Decisions">
      <memory id="decisions:5da308d:21">
        <summary>Adaptive token budget based on project complexity</summary>
      </memory>
      <memory id="decisions:5da308d:20">
        <summary>Confidence-based tiered capture behavior (AUTO/SUGGEST/SKIP)</summary>
      </memory>
      <memory id="decisions:5da308d:19">
        <summary>Lazy loading via __getattr__ to avoid embedding model import penalty</summary>
      </memory>
      <memory id="decisions:5da308d:18">
        <summary>Git notes as source of truth, SQLite as derived queryable index</summary>
      </memory>
    </decisions>
  </working_memory>
  <semantic_context>
    <learnings title="Relevant Learnings">
      <memory id="learnings:4c98fec:0" relevance="0.50">
        <summary>Testing plugin functionality after bug fix</summary>
      </memory>
    </learnings>
  </semantic_context>
</memory_context>
```

**Confidence**: HIGH - Direct observation in current session

### Finding 5: Signal Detection Patterns
**Source**: signal_detector.py
**Evidence**:
- 8 signal types with regex patterns and base confidence
- Block markers: `▶ namespace ─────────────────`
- Inline markers: `[decision]`, `[learned]`, `[blocker]`
- Contextual patterns: "I decided", "TIL", "blocked by"

**Real Block Marker Example from Session**:
```
▶ learned ─────────────────────────────────────
Hook-based memory capture works via Stop hook at session end

## Context
Block markers output during a session are NOT immediately captured.
They are detected and captured when the session ends via the Stop
hook's transcript analysis.

## Key Findings
- UserPromptSubmit only scans USER prompts, not assistant responses
- Stop hook analyzes the full transcript at session end
- PreCompact hook triggers on context compaction (manual/auto)

## Related Files
- src/git_notes_memory/hooks/stop_handler.py:398-410
────────────────────────────────────────────────
```

**Confidence**: HIGH - Created and observed in current session

### Finding 6: Novelty Checking Prevents Duplicates
**Source**: novelty_checker.py, session_analyzer.py
**Evidence**:
- Vector similarity against existing memories
- Threshold: 0.3 (30% different from existing = novel)
- Applied before auto-capture in Stop and PreCompact hooks

**Implication**: max_captures limit (now 50) doesn't flood index because duplicates filtered

**Confidence**: HIGH - Code analysis confirmed

### Finding 7: SQLite + sqlite-vec for Vector Search
**Source**: index.py
**Evidence**:
- `memories` table for metadata
- `vec_memories` virtual table for embeddings (384 dimensions, all-MiniLM-L6-v2)
- KNN search via `MATCH` operator
- 116 memories currently indexed in project

**Real Query Example**:
```python
results = svc.search('Lazy loading __getattr__', k=5)
# Returns:
# decisions:5da308d:19: Lazy loading via __getattr__ to avoid embedding model import penalty
# decisions:5da308d:16: ▶ decision ─────...Lazy loading via __ge...
```

**Confidence**: HIGH - Verified during debugging

---

## Open Questions

1. **Q**: Why does PreCompact log show only HOOK INPUT without subsequent processing?
   **Hypothesis**: Handler may exit early on some config check
   **Status**: Added detailed logging to trace flow

2. **Q**: How to capture memories MID-session vs only at session end?
   **Answer**: Currently only Stop/PreCompact capture from assistant responses. UserPromptSubmit only scans user prompts.

3. **Q**: Why was max_captures set to 5 initially?
   **Answer**: Conservative default; novelty checking makes higher limits safe. Changed to 50.

---

## Competing Hypotheses

### Why memories weren't captured during session:

**Hypothesis A** (CONFIRMED): Timing issue - Stop hook fires at session END
- Evidence: Stop hook log shows 5 captures at session end (00:46:36)
- /memory:status run DURING session showed 0 because Stop hadn't fired

**Hypothesis B** (REJECTED): UserPromptSubmit should capture assistant responses
- Evidence: UserPromptSubmit only processes user prompts (by design)
- Assistant responses analyzed by Stop/PreCompact via transcript

**Hypothesis C** (PARTIAL): PreCompact should capture on compaction
- Evidence: PreCompact triggered but logs unclear
- Added detailed logging to verify next compaction

---

## Confidence Assessments

| Finding | Confidence | Evidence Quality |
|---------|------------|------------------|
| Git notes as source of truth | HIGH | Architecture docs + code |
| Progressive hydration | HIGH | Code + session observation |
| Hook-based capture | HIGH | Production logs in session |
| Context injection | HIGH | Direct XML observation |
| Signal detection | HIGH | Code + created examples |
| Novelty checking | HIGH | Code analysis |
| Vector search | HIGH | Query verification |

---

## Novel Use Cases Identified

### 1. Cross-Session Continuity
- Decisions made in session A appear in session B
- Blockers persist until resolved
- Progress tracked across specifications

### 2. Semantic Memory Retrieval
- "What did we decide about databases?" → finds PostgreSQL decision
- Works across namespaces and time periods

### 3. File-Contextual Memory Surfacing
- PostToolUse extracts domain from file paths
- Related memories injected when editing files
- Example: Editing `auth/jwt.py` surfaces authentication learnings

### 4. Compaction-Safe Capture
- PreCompact hook preserves content before context window shrinks
- High-confidence signals auto-captured
- Prevents loss of valuable insights

### 5. Git-Native Distribution
- Memories sync with `git push/pull`
- Team members share learnings via notes refs
- Works with existing git infrastructure

---

## Document Sources

1. Core services: capture.py, recall.py, sync.py, index.py, git_ops.py
2. Hook handlers: session_start_handler.py, user_prompt_handler.py, stop_handler.py, pre_compact_handler.py, post_tool_use_handler.py
3. Models: models.py (core), hooks/models.py (hook-specific)
4. Architecture docs: docs/spec/completed/*/ARCHITECTURE.md
5. ADRs: docs/spec/completed/*/DECISIONS.md
6. Session logs: ~/.local/share/memory-plugin/logs/*.log
