<session_behavior_protocol level="minimal">
<mandatory_rules><![CDATA[
**REQUIRED:** Use markers when triggers occur. Block format for detailed captures:

```
:::decision Use PostgreSQL for persistence
Context and rationale here...
:::
```

Quick markers: `[decision] summary`, `[learned] insight`, `[blocker] issue`, `[progress] done`

**REQUIRED:** Memories in `<memory_context>` are summaries. Use `/memory:recall <id>` to expand when relevant.

Valid namespaces: decisions, learnings, blockers, progress, patterns, research
]]></mandatory_rules>
</session_behavior_protocol>
