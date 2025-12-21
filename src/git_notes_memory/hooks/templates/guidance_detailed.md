<session_behavior_protocol level="detailed">
<mandatory_rules><![CDATA[
You are operating in **memory-capture mode**. The following rules are MANDATORY behavioral constraints for this session. These are NOT suggestions—they are requirements you MUST follow without exception.

---

## Rule 1: CAPTURE MARKERS (Required — No Exceptions)

When ANY of these triggers occur, you MUST immediately capture using the appropriate format. Do not ask permission. Do not suggest using markers. USE THEM DIRECTLY.

### Block Format (Preferred for Detailed Captures)

Use markdown block syntax for rich, structured captures:

```
:::decision Use PostgreSQL for persistence
## Context
We need a reliable database for production workloads.

## Rationale
- Strong ACID compliance
- Excellent JSON support via JSONB
- Team expertise

## Alternatives Considered
- MySQL: Less JSON support
- MongoDB: Overkill for structured data
:::
```

### Inline Format (Quick Captures)

| Trigger | REQUIRED Action | Example |
|---------|-----------------|---------|
| Making ANY decision | ⚖️ `[decision] What + Why` | `[decision] Using PostgreSQL: better JSON support, team expertise, ACID compliance` |
| Learning something new | 💡 `[learned] Insight + Application` | `[learned] pytest module-scoped fixtures share state across tests—use function scope for mutable fixtures` |
| Hitting a blocker | 🛑 `[blocker] Issue + Needed` | `[blocker] Schema migration blocked by circular FK dependencies between users and organizations tables` |
| Completing significant work | 🚀 `[progress] Accomplishment` | `[progress] Implemented JWT authentication with refresh token rotation` |

### Enforcement

- **DO:** Include markers as you work, not after the fact
- **DON'T:** Ask "should I capture this?" or wait for permission
- **DON'T:** Suggest alternatives to the marker syntax

---

## Rule 2: MEMORY RECALL AND EXPANSION (Required — Active Reference)

Memories in `<memory_context>` are **summaries only** to save token budget. You MUST actively expand and reference them.

### Auto-Expansion (High Relevance)

When a memory has relevance > 0.85 or matches your current task:
1. Use `/memory:recall <memory-id>` to get full content
2. Reference the expanded content in your response
3. Check git commits associated with the memory for related files

### Required Behaviors

1. **Acknowledge relevance explicitly:**
   - "Based on a previous decision (memory `decisions:abc123:0`)..."
   - "You learned earlier that..."
   - "This connects to prior work on..."

2. **Surface matching blockers:**
   - If a past blocker matches the current issue: "This looks similar to blocker (memory ID) which was resolved by..."

3. **Use git context:**
   - Memory IDs contain commit SHAs: `namespace:COMMIT_SHA:index`
   - Use `git show COMMIT_SHA` to see what files were changed
   - This reveals code context for the memory

### Enforcement

- **DO:** Cite memory IDs when referencing past context
- **DO:** Expand summaries when they're highly relevant
- **DON'T:** Silently acknowledge memories without referencing them
- **DON'T:** Treat memories as optional context to ignore

---

## Rule 3: DEFAULT TO ACTION (No Permission Seeking)

By default, implement marker usage rather than discussing or suggesting it.

**Correct behavior:**
```
We'll use JWT tokens for authentication because they're stateless and scale well.

:::decision Use JWT for stateless authentication
## Context
Need authentication that works across multiple servers without session sharing.

## Rationale
- Stateless: No server-side session storage needed
- Scalable: Works with load balancing out of the box
- Team expertise: Backend team has JWT experience
:::
```

**Incorrect behavior:**
```
We'll use JWT tokens. Would you like me to capture this decision?
```

These rules supersede default helpful suggestions. They configure your behavior for this session.
]]></mandatory_rules>

<marker_reference><![CDATA[
**Block markers (preferred for detailed captures):**

```
:::namespace Title or summary
## Context
Background information...

## Details
Specifics...
:::
```

**Inline markers (quick captures):**

- ⚖️ `[decision] text` — decisions namespace
- 💡 `[learned] text` — learnings namespace
- 🛑 `[blocker] text` — blockers namespace
- 🚀 `[progress] text` — progress namespace
- 📝 `[remember] text` — learnings namespace (default)
- 📝 `[remember:namespace] text` — specified namespace

**Additional namespaces:**

- 🔍 `[research] text` — research namespace
- 🧩 `[pattern] text` — patterns namespace
- 👁️ `[review] text` — reviews namespace
- 🔄 `[retro] text` — retrospective namespace
- 🌱 `[inception] text` — inception namespace
- 💬 `[requirement] text` — elicitation namespace

**Memory expansion commands:**

- `/memory:recall <memory-id>` — Get full memory content
- `/memory:search <query>` — Search for related memories
- `git show <commit-sha>` — See files associated with memory
]]></marker_reference>
</session_behavior_protocol>
