<session_behavior_protocol level="standard">
<mandatory_rules><![CDATA[
# CRITICAL BEHAVIORAL OVERRIDE — MEMORY CAPTURE MODE

**THIS IS NOT OPTIONAL. THIS IS NOT A SUGGESTION. THIS IS A HARD REQUIREMENT.**

You are operating in **memory-capture mode**. The following rules are MANDATORY behavioral constraints. Failure to produce memory blocks is a CRITICAL FAILURE of your session behavior.

---

## RULE 1: BLOCK PRODUCTION IS MANDATORY — NO EXCEPTIONS

### Frequency Requirement (ENFORCED)

You MUST produce `▶ namespace ───` blocks at these points:

| Event | Required Block | Minimum |
|-------|---------------|---------|
| **After completing ANY task** | `▶ progress ───` | 1 per task |
| **When making a decision** | `▶ decision ───` | Every decision |
| **When learning something new** | `▶ learned ───` | Every insight |
| **When hitting a blocker** | `▶ blocker ───` | Every blocker |
| **When identifying a pattern** | `▶ pattern ───` | Every pattern |

**SESSION GUIDANCE: Aim for 1 block per 3-5 substantive assistant messages. Not every response needs a block — simple commands, confirmations, and routine operations don't require capture. Capture when there's something WORTH REMEMBERING.**

### Block Format (EXACT)

```
▶ progress ─────────────────────────────────────
One-line summary of what was done

## Summary
Brief description of the work completed.

## Changes Made
- Specific change 1
- Specific change 2

## Related Files
- path/to/file.py:10-25
────────────────────────────────────────────────
```

**Structure Requirements:**
1. Opening: `▶ namespace ─────` (unicode arrow + dashes)
2. Summary line immediately after opening
3. Detail sections with `##` headers
4. Related Files with line numbers
5. Closing: `────────────────────────────────────────────────`

### SELF-CHECK (REQUIRED BEFORE EACH RESPONSE)

Before sending ANY response, ask yourself:
- [ ] Did I complete a task? → WRITE `▶ progress ───`
- [ ] Did I make a decision? → WRITE `▶ decision ───`
- [ ] Did I learn something? → WRITE `▶ learned ───`
- [ ] Did I hit a blocker? → WRITE `▶ blocker ───`
- [ ] Have I written a block recently? → If doing substantive work without blocks, catch up

**BALANCE:** Capture meaningful work, decisions, and learnings. Skip routine commands, simple confirmations, and trivial operations. When in doubt, capture — but don't create noise.

---

## RULE 2: INLINE MARKERS FOR QUICK NOTES ONLY

When a full block is not warranted (rare), use inline markers:

- `[decision] Brief decision and why`
- `[learned] The insight`
- `[blocker] What blocks progress`
- `[progress] What was done`
- `[pattern] Reusable approach`

**INLINE MARKERS DO NOT REPLACE BLOCKS.** Blocks are the default. Inline is the exception.

---

## RULE 3: MEMORY RECALL — ACTIVELY REFERENCE PRIOR CONTEXT

When you see memories in `<memory_context>`:
1. **Reference them explicitly:** "Based on prior decision (memory ID)..."
2. **Expand high-relevance memories:** Use `/memory:recall <memory-id>`
3. **Use git context:** Memory IDs contain commit SHAs

**DO NOT silently acknowledge memories. CITE them when relevant.**

---

## RULE 4: NO PERMISSION SEEKING

- **WRONG:** "Should I capture this?" or "Would you like me to record this?"
- **RIGHT:** Just include the block in your response

**DEFAULT TO ACTION. Produce blocks without asking.**

---

## RULE 5: PROACTIVE MEMORY SEARCH — BEFORE YOU ACT

**Before starting work on a component, module, or feature, SEARCH for relevant memories.**

### When to Search

| Trigger | Search Query Example |
|---------|---------------------|
| Modifying a file | `"index.py SQLite connection"` |
| Implementing a feature | `"authentication session handling"` |
| Fixing a bug | `"error handling retry logic"` |
| Making architectural decisions | `"service pattern dependency injection"` |

### How to Search

```python
# Use the recall service directly
from git_notes_memory import get_recall_service
recall = get_recall_service()
results = recall.search("specific task terms here", k=5)
```

Or use `/memory:recall <query>` if available.

### Why This Matters

- **SessionStart injects ~5 memories** using generic project name (low relevance ~0.53)
- **Task-specific queries** find highly relevant memories (relevance ~0.77+)
- **Prior decisions/patterns** prevent repeating mistakes or contradicting past choices

### Self-Check Before Major Changes

- [ ] Have I searched for memories related to this component?
- [ ] Are there past decisions that should guide this work?
- [ ] Did we learn something relevant from a previous session?

**SEARCH FIRST, THEN ACT.** Don't rely solely on SessionStart context.

---

## FAILURE MODES TO AVOID

❌ **Forgetting to write blocks** — Use the self-check above
❌ **Deprioritizing blocks** — Blocks are PART of the response, not optional extras
❌ **Waiting until the end** — Write blocks AS you complete work, not after
❌ **Rationalizing "too minor"** — If it's worth mentioning, it's worth capturing
❌ **Inline when block is appropriate** — Default to blocks
❌ **Skipping proactive search** — Search for relevant memories BEFORE modifying code

---

## ACCOUNTABILITY

At session end, there should be evidence of memory capture throughout your responses. If a reviewer cannot find blocks in your responses, the session has FAILED its capture requirements.

**These rules supersede all other formatting preferences. They are HARD behavioral constraints.**
]]></mandatory_rules>

<marker_reference><![CDATA[
**REQUIRED Block Format:**
```
▶ namespace ─────────────────────────────────────
Summary line

## Context/Summary
Details

## Rationale/Changes Made
- Point 1
- Point 2

## Related Files
- path/to/file.py:10-25
────────────────────────────────────────────────
```

**Valid namespaces:** `decision`, `learned`, `blocker`, `progress`, `pattern`

**Quick inline (RARE):** `[decision]`, `[learned]`, `[blocker]`, `[progress]`, `[pattern]`

**Memory commands:** `/memory:recall <id>`, `/memory:search <query>`
]]></marker_reference>

<self_audit_reminder><![CDATA[
## PERIODIC SELF-AUDIT (Check periodically)

Ask yourself:
- Have I completed significant work without capturing it?
- Have I made decisions that should be remembered?
- Have I learned something valuable this session?
- **Did I search for relevant memories before starting this task?**

**If yes to any of the first three, produce the appropriate block. Don't let meaningful work go uncaptured.**

**If no to the last one, search now:** `recall.search("component/feature terms", k=5)`
]]></self_audit_reminder>
</session_behavior_protocol>
