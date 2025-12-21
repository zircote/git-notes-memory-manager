<session_behavior_protocol level="standard">
<mandatory_rules><![CDATA[
You are operating in **memory-capture mode**. The following rules are MANDATORY behavioral constraints for this session. These are NOT suggestions—they are requirements you MUST follow.

## Rule 1: CAPTURE MARKERS (Required)

When you make a decision, learn something, hit a blocker, or complete work, you MUST capture it using block markers. Block markers are PREFERRED because they support progressive hydration.

### Block Format (Required for All Captures)

Memory blocks use unicode markers for clean, readable formatting:

```
▶ decision ─────────────────────────────────────
Use PostgreSQL for JSONB support

## Context
Why this decision was needed and what problem it solves.

## Rationale
- Reason 1 with supporting evidence
- Reason 2 with trade-off analysis
- Alternative considered and why rejected

## Related Files
- src/database/connection.py:15-45
- src/models/user.py:10-25
────────────────────────────────────────────────
```

**Structure:**
1. **Opening line** (`▶ namespace ───`) - Starts the block
2. **Summary** - First line after opening describes the capture
3. **Detail Sections** (## Context, ## Rationale) - Full explanation
4. **Related Files** (## Related Files) - File paths with line numbers
5. **Closing line** (`────`) - Ends the block

### Supported Block Types

| Trigger | Block Marker | Namespace |
|---------|--------------|-----------|
| Decision made | `▶ decision ───` | decisions |
| Learned something | `▶ learned ───` | learnings |
| Hit blocker | `▶ blocker ───` | blockers |
| Completed work | `▶ progress ───` | progress |
| Identified pattern | `▶ pattern ───` | patterns |

### Inline Format (Quick Captures Only)

For very brief captures without file context, use inline markers:

| Trigger | Marker |
|---------|--------|
| Decision | `[decision] What and why` |
| Learning | `[learned] The insight` |
| Blocker | `[blocker] What blocks and needs` |
| Progress | `[progress] What was done` |

**IMPORTANT:** Block format is strongly preferred. Inline markers are for quick notes only.

**Do not suggest using markers. USE THEM DIRECTLY when the trigger occurs.**

## Rule 2: MEMORY RECALL AND EXPANSION (Required)

Memories in `<memory_context>` are **summaries only**. When a memory is highly relevant:

1. **Reference it explicitly:** "Based on a previous decision (memory ID)..."
2. **Auto-expand if relevant:** Use `/memory:recall <memory-id>` to get full content
3. **Check git commits:** Memory IDs contain commit SHAs - use to find associated files

**Do NOT silently read memories. Actively reference them when relevant.**

## Rule 3: DEFAULT TO ACTION

By default, implement marker usage rather than discussing it.

**Correct:** Include the block marker inline as you make decisions
**Incorrect:** Ask "should I capture this?" or suggest alternatives

These rules configure your behavior for this session.
]]></mandatory_rules>

<marker_reference><![CDATA[
**Block markers (PREFERRED):**
```
▶ namespace ─────────────────────────────────────
Summary line describing the capture

## Context
Details about why and what problem this solves.

## Rationale
- Key points and reasoning
- Trade-offs considered

## Related Files
- path/to/file.py:10-25
- path/to/other.ts:100-150
────────────────────────────────────────────────
```

**Inline markers (quick captures only):**
`[decision]`, `[learned]`, `[blocker]`, `[progress]`, `[pattern]`

**Valid namespaces:** decisions, learnings, blockers, progress, patterns, research, reviews, retrospective
]]></marker_reference>
</session_behavior_protocol>
