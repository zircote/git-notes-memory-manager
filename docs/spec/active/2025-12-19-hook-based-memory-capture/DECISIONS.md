---
document_type: decisions
project_id: SPEC-2025-12-19-001
version: 1.0.0
last_updated: 2025-12-19T00:00:00Z
status: draft
---

# Hook-Based Memory Capture - Architectural Decisions

This document records the key architectural decisions made during the specification of the hook-based memory capture enhancement.

## Decision Log

| ID | Decision | Date | Status |
|----|----------|------|--------|
| ADR-001 | Enhance existing plugin vs new plugin | 2025-12-19 | Accepted |
| ADR-002 | XML-structured context format | 2025-12-19 | Accepted |
| ADR-003 | LLM-assisted capture decisions | 2025-12-19 | Accepted |
| ADR-004 | Adaptive token budget strategy | 2025-12-19 | Accepted |
| ADR-005 | Hook event selection | 2025-12-19 | Accepted |
| ADR-006 | Confidence-based capture behavior | 2025-12-19 | Accepted |
| ADR-007 | Capture detection opt-in by default | 2025-12-19 | Accepted |

---

## ADR-001: Enhance Existing Plugin vs New Plugin

### Status
Accepted

### Context
We need to add hook-based memory capture functionality. Two options exist:
1. Create a new separate plugin for hook integration
2. Enhance the existing memory-capture-plugin with hook capabilities

### Decision
**Enhance the existing memory-capture-plugin** rather than creating a new plugin.

### Rationale
- **Service reuse**: Existing RecallService, CaptureService, IndexService can be directly used
- **Single installation**: Users only need one plugin for all memory functionality
- **Unified configuration**: All memory settings in one place
- **Shared storage**: Same git notes and SQLite index for all operations
- **Consistent experience**: `/remember` and `/recall` commands work alongside hooks

### Consequences
- Plugin complexity increases
- Must maintain backward compatibility with existing functionality
- Testing must cover both manual and automatic capture paths

### Alternatives Considered
- **New plugin**: Would provide cleaner separation but duplicate storage/services
- **Plugin composition**: Hook plugin depends on memory plugin - added complexity

---

## ADR-002: XML-Structured Context Format

### Status
Accepted

### Context
SessionStart hooks inject context into Claude's session. The format must be:
- Parseable by Claude for understanding
- Hierarchical for organizing different memory types
- Extensible for future enhancements

### Decision
Use **XML-structured format** for memory context injection.

### Rationale
- **Clear semantic boundaries**: Tags like `<working_memory>`, `<semantic_context>` provide clear sections
- **Hierarchical organization**: Natural nesting of context → namespace → memory
- **Parseable**: Both humans and LLMs can understand structure
- **Attribute support**: Metadata (priority, count, timestamp) fits naturally
- **Industry precedent**: Anthropic's own documentation uses XML tags for structured prompts

### Consequences
- XML generation code needed (using xml.etree.ElementTree)
- Slightly more verbose than JSON
- Must handle XML escaping properly

### Example
```xml
<memory_context source="SessionStart" timestamp="2025-12-19T10:00:00Z">
  <project_scope>
    <project>hook-based-memory-capture</project>
    <token_budget>1500</token_budget>
  </project_scope>
  <working_memory priority="high">
    <active_blockers count="1">...</active_blockers>
    <recent_decisions count="3">...</recent_decisions>
  </working_memory>
</memory_context>
```

### Alternatives Considered
- **JSON**: Less readable in prompts, harder to scan visually
- **Markdown**: Less structured, harder to parse programmatically
- **Plain text**: No structure, difficult to extend

---

## ADR-003: LLM-Assisted Capture Decisions

### Status
Accepted

### Context
When detecting memorable content, we need to decide whether to capture it. Options:
1. Rule-based only (regex patterns, keywords)
2. LLM-assisted (prompt-type hooks)
3. Always ask user

### Decision
Use **LLM-assisted decisions via prompt-type hooks** for capture decisions.

### Rationale
- **Context awareness**: LLM can understand nuance beyond keyword matching
- **Reduced false positives**: "I decided" in a quote vs actual decision
- **Natural language understanding**: Handles variations in how users express things
- **Claude Code native**: Prompt-type hooks are a built-in feature

### Consequences
- Additional latency for LLM call (~500ms-2s)
- Token cost for each evaluation (small, local context)
- Need fallback for when prompt hooks disabled

### Implementation
```json
{
  "type": "prompt",
  "prompt": "Evaluate if this content is worth capturing as a memory...",
  "timeout": 30
}
```

### Alternatives Considered
- **Rule-based only**: Fast but high false positive rate
- **Always ask user**: Disruptive, breaks flow
- **External LLM API**: Additional setup, cost, privacy concerns

---

## ADR-004: Adaptive Token Budget Strategy

### Status
Accepted

### Context
SessionStart context injection must balance:
- Providing enough context for useful sessions
- Not overwhelming Claude's context window
- Scaling appropriately with project complexity

### Decision
Implement **adaptive token budget** based on project complexity.

### Rationale
- **Right-sized context**: Simple projects don't need 3000 tokens
- **Avoids waste**: Reduces unnecessary context for small projects
- **Scales naturally**: Complex projects get more comprehensive context
- **User configurable**: Can override to fixed budget if preferred

### Budget Tiers
| Complexity | Indicators | Budget |
|------------|------------|--------|
| Simple | 1-2 files, <10 memories | 500 tokens |
| Medium | Module-level, 10-50 memories | 1000 tokens |
| Complex | System-level, 50-100 memories | 2000 tokens |
| Full | Large project, >100 memories | 3000 tokens |

### Consequences
- Need complexity detection heuristics
- Budget calculation adds small overhead
- Must handle edge cases (new project = 0 memories)

### Alternatives Considered
- **Fixed budget**: Simpler but wastes tokens or under-serves
- **Unlimited**: Risk of context overflow
- **User-specified per project**: Too much configuration burden

---

## ADR-005: Hook Event Selection

### Status
Accepted

### Context
Claude Code provides multiple hook events. We must select which to use:
- SessionStart, SessionEnd
- UserPromptSubmit
- PreToolUse, PostToolUse
- Stop, SubagentStop

### Decision
Use **SessionStart, UserPromptSubmit, and Stop** hooks.

### Rationale

| Hook | Purpose | Why Selected |
|------|---------|--------------|
| SessionStart | Context injection | Essential for automatic memory loading |
| UserPromptSubmit | Capture detection | Best place to analyze user intent |
| Stop | Session capture | Natural checkpoint before session ends |

**Not selected**:
- SessionEnd: No context injection possible (session already closing)
- PreToolUse: Too granular, would fire constantly
- PostToolUse: Useful for change tracking but P2 priority
- SubagentStop: Future enhancement (P2)

### Consequences
- Three hook handlers to implement and maintain
- UserPromptSubmit adds latency to every prompt (must be fast)
- Stop hook must not block indefinitely

### Alternatives Considered
- **All hooks**: Too complex, performance impact
- **SessionStart only**: Misses capture opportunities
- **PostToolUse for changes**: Valuable but adds complexity (P2)

---

## ADR-006: Confidence-Based Capture Behavior

### Status
Accepted

### Context
When a memorable moment is detected, we need a behavior model:
- Should we capture automatically?
- Should we always ask the user?
- How do we balance automation with user control?

### Decision
Implement **confidence-based tiered behavior**.

### Tiers
| Confidence | Action | User Experience |
|------------|--------|-----------------|
| ≥0.95 | AUTO | Capture silently, show notification |
| 0.70-0.95 | SUGGEST | Show suggestion, user confirms |
| <0.70 | SKIP | No action unless explicit signal |

**Exception**: Explicit signals ("remember this") always treated as ≥0.95.

### Rationale
- **High confidence = low friction**: Obvious captures shouldn't require confirmation
- **Medium confidence = user control**: Uncertain captures get human judgment
- **Low confidence = no noise**: Avoids suggestion fatigue
- **Configurable**: Thresholds can be adjusted per user preference

### Consequences
- Need confidence scoring algorithm
- Must calibrate thresholds through testing
- User may want to adjust default thresholds

### Alternatives Considered
- **Always auto-capture**: Intrusive, captures unwanted content
- **Always ask**: Disruptive, breaks flow
- **Binary (capture/skip)**: Loses nuance of medium-confidence cases

---

## ADR-007: Capture Detection Opt-In by Default

### Status
Accepted

### Context
UserPromptSubmit capture detection adds latency to every user prompt. Should it be:
- Enabled by default (full experience)
- Disabled by default (opt-in for power users)

### Decision
**Capture detection disabled by default** (opt-in).

### Rationale
- **Performance first**: Users shouldn't experience latency they didn't ask for
- **Progressive disclosure**: Basic functionality (SessionStart) works immediately
- **Explicit consent**: Users consciously enable automatic capture
- **Conservative default**: Aligns with principle of least surprise

### Configuration
```toml
[hooks.capture_detection]
enabled = false  # User must explicitly enable
```

### Consequences
- Users must discover and enable capture detection
- May reduce adoption of capture detection feature
- Need good documentation explaining the feature and how to enable

### Alternatives Considered
- **Enabled by default**: Better discoverability but performance impact
- **Prompt on first use**: Interrupts first session experience
- **Smart default based on memory count**: Complex, unpredictable

---

## Pending Decisions

The following decisions are deferred to implementation:

| Topic | Options | Decision Point |
|-------|---------|----------------|
| Local vs cloud LLM for prompt hooks | Local (Ollama) vs Claude | Phase 3 implementation |
| Cache strategy for SessionStart | TTL-based, invalidation-based | Phase 2 implementation |
| Transcript parsing format | JSON lines, raw text | Phase 4 implementation |

---

## Decision Review Schedule

| Decision | Review Trigger |
|----------|----------------|
| ADR-004 (Token Budget) | After 30 days of usage data |
| ADR-006 (Confidence Tiers) | After user feedback on false positives |
| ADR-007 (Opt-in Default) | After measuring adoption rates |
