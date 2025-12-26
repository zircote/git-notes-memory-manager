<session_behavior_protocol level="minimal">
<mandatory_rules><![CDATA[
# MANDATORY: Memory Block Production

**RULE: Produce `▶ namespace ───` blocks after EVERY completed task. This is not optional.**

**Guidance:** Capture meaningful work, decisions, and learnings. Skip routine commands and confirmations.

**Block format:**
```
▶ progress ─────────────────────────────────────
Summary of what was done

## Changes Made
- Change 1
- Change 2

## Related Files
- path/to/file.py:10-25
────────────────────────────────────────────────
```

**Block types:** `▶ decision`, `▶ learned`, `▶ blocker`, `▶ progress`, `▶ pattern`

**Quick markers (RARE):** `[decision]`, `[learned]`, `[blocker]`, `[progress]`, `[pattern]`

**Self-check before EACH response:**
- Did I complete a task? → WRITE `▶ progress ───`
- Did I make a decision? → WRITE `▶ decision ───`

**DO NOT skip blocks. DO NOT ask permission. Just include them.**

**Proactive search:** Before modifying code, search for relevant memories:
`recall.search("component terms", k=5)` — SessionStart context alone is insufficient.

**Memory recall:** Use `/memory:recall <id>` to expand memories from `<memory_context>`.
]]></mandatory_rules>
</session_behavior_protocol>
