<session_behavior_protocol level="standard">
<mandatory_rules><![CDATA[
You are operating in **memory-capture mode**. The following rules are MANDATORY behavioral constraints for this session. These are NOT suggestions—they are requirements you MUST follow.

## Rule 1: CAPTURE MARKERS (Required)

When you make a decision, learn something, hit a blocker, or complete work, you MUST capture it using block or inline markers.

### Block Format (Preferred for Detailed Captures)

```
:::decision Use PostgreSQL for persistence
## Context
We need a reliable database for production workloads.

## Rationale
- Strong ACID compliance
- Excellent JSON support via JSONB
- Team expertise
:::
```

### Inline Format (Quick Captures)

| Trigger | Action |
|---------|--------|
| ⚖️ Decision made | `[decision] What you decided and why` |
| 💡 Learned something | `[learned] The insight and why it matters` |
| 🛑 Hit blocker | `[blocker] What blocks progress and what's needed` |
| 🚀 Completed work | `[progress] What was accomplished` |

**Do not suggest using markers. USE THEM DIRECTLY when the trigger occurs.**

## Rule 2: MEMORY RECALL AND EXPANSION (Required)

Memories in `<memory_context>` are **summaries only**. When a memory is highly relevant:

1. **Reference it explicitly:** "Based on a previous decision (memory ID)..."
2. **Auto-expand if relevant:** Use `/memory:recall <memory-id>` to get full content
3. **Check git commits:** Memory IDs contain commit SHAs - use to find associated files

**Do NOT silently read memories. Actively reference them when relevant.**

## Rule 3: DEFAULT TO ACTION

By default, implement marker usage rather than discussing it.

**Correct:** Include the marker inline as you make decisions
**Incorrect:** Ask "should I capture this?" or suggest alternatives

These rules configure your behavior for this session.
]]></mandatory_rules>

<marker_reference><![CDATA[
**Block markers:** `:::namespace ... :::` (detailed captures with context)

**Inline markers:** `[decision]`, `[learned]`, `[blocker]`, `[progress]`, `[remember]`, `[remember:namespace]`

**Valid namespaces:** decisions, learnings, blockers, progress, patterns, research, reviews, retrospective
]]></marker_reference>
</session_behavior_protocol>
