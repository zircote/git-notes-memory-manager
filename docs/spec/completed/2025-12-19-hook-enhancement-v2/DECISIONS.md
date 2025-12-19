---
document_type: decisions
project_id: SPEC-2025-12-19-002
---

# Hook Enhancement v2 - Architecture Decision Records

## ADR-001: PreCompact Uses stderr for User Feedback

**Date**: 2025-12-19
**Status**: Accepted
**Deciders**: Development team

### Context

The PreCompact hook needs to inform users when memories are auto-captured before context compaction. The original plan assumed PreCompact could use `additionalContext` in hookSpecificOutput for this purpose.

However, research into the Claude Code hooks API revealed that PreCompact is **side-effects only** - it does not process JSON output. Only stderr is shown to users.

### Decision

PreCompact will:
1. Capture memories as side effects (writing to git notes)
2. Output a summary message to stderr for user visibility
3. Return an empty JSON object `{}` to stdout

### Consequences

**Positive:**
- Works within API constraints
- Users still see notification of auto-captured memories
- No need for workaround or API extension request

**Negative:**
- Less structured feedback than additionalContext would provide
- stderr messages are less prominent in Claude Code UI
- Cannot inject captured memory summaries into Claude's context

**Neutral:**
- Aligns with PreCompact's intended use case (backup/logging)

### Alternatives Considered

1. **Request Claude Code API change**: Too slow; creates external dependency
2. **Skip user notification**: Poor UX; users wouldn't know what was captured
3. **Use Stop hook instead**: Wrong lifecycle point; compaction already occurred

---

## ADR-002: Namespace Marker Syntax Design

**Date**: 2025-12-19
**Status**: Accepted
**Deciders**: Development team

### Context

Users need to specify which namespace their inline captures should target. The existing syntax (`[remember]`, `@memory`) always routes to `learnings` namespace.

### Decision

Support two syntaxes for namespace specification:

1. **Bracket syntax**: `[remember:namespace]` and `[capture:namespace]`
2. **At-sign syntax**: `@memory:namespace`

Examples:
- `[remember:decisions] Use PostgreSQL for database`
- `[capture:patterns] API error handling approach`
- `@memory:blockers CORS issue with frontend`

Existing syntax without namespace remains valid and auto-detects or defaults to `learnings`.

### Consequences

**Positive:**
- Intuitive extension of existing syntax
- Backward compatible (existing markers unchanged)
- Namespace clearly visible in the marker
- Consistent with common annotation patterns

**Negative:**
- More regex patterns to maintain
- Users need to learn new syntax

**Neutral:**
- Namespace validation needed (invalid namespace falls back to auto-detect)

### Alternatives Considered

1. **Separate markers per namespace**: `[decision]`, `[learning]`, etc. - Too many new markers
2. **Namespace as parameter**: `[remember namespace=decisions]` - Verbose, less readable
3. **Hashtag syntax**: `[remember #decisions]` - Conflicts with potential tag syntax

---

## ADR-003: Auto-Capture Enabled by Default

**Date**: 2025-12-19
**Status**: Accepted
**Deciders**: Development team, User validation

### Context

PreCompact hook can auto-capture high-confidence uncaptured content before context compaction. This is a new behavior that writes to git notes without explicit user action.

Options considered:
1. Enabled by default, users can opt-out
2. Disabled by default, users must opt-in
3. Prompt user before each capture

### Decision

Auto-capture enabled by default (`HOOK_PRE_COMPACT_AUTO_CAPTURE=true`) with high confidence threshold (0.85).

Rationale: Most users will benefit from automatic preservation of valuable content. Power users who want control can disable via environment variable.

### Consequences

**Positive:**
- Maximum value for majority of users
- Prevents loss of valuable context during compaction
- Fail-safe: captured memories are tagged `["auto-captured", "pre-compact"]` for filtering

**Negative:**
- Some users may be surprised by automatic captures
- Could create memories users didn't intend to save
- May need tuning of confidence threshold over time

**Neutral:**
- High confidence threshold (0.85) limits false positives
- Maximum 3 captures per compaction event

### Alternatives Considered

1. **Opt-in only**: Lower adoption, users who need it most won't enable it
2. **Prompt first**: Interrupts compaction flow, poor UX

---

## ADR-004: Response Guidance as XML in additionalContext

**Date**: 2025-12-19
**Status**: Accepted
**Deciders**: Development team

### Context

To improve signal detection accuracy, we need to teach Claude how to structure responses. The guidance must be injected into Claude's context at session start.

Options:
1. XML in additionalContext (existing pattern)
2. Markdown in additionalContext
3. System prompt modification
4. Separate skill file

### Decision

Use XML format in SessionStart additionalContext, consistent with existing memory context injection.

Structure:
```xml
<response_guidance>
  <capture_patterns>
    <pattern type="decision">...</pattern>
    <pattern type="learning">...</pattern>
  </capture_patterns>
  <inline_markers>...</inline_markers>
  <best_practices>...</best_practices>
</response_guidance>
```

### Consequences

**Positive:**
- Consistent with existing ContextBuilder patterns
- Claude parses XML well
- Structured data is easy to maintain and test
- Can control verbosity via detail_level config

**Negative:**
- Adds tokens to context budget
- XML is more verbose than markdown

**Neutral:**
- Configurable: users can disable if context budget is critical

### Alternatives Considered

1. **Markdown**: Less structured, harder to parse programmatically
2. **System prompt**: Requires user to modify their config
3. **Skill file**: Only works when skill is invoked, not always-on

---

## ADR-005: PostToolUse Matcher Pattern

**Date**: 2025-12-19
**Status**: Accepted
**Deciders**: Development team

### Context

PostToolUse hook requires a matcher to filter which tools trigger the hook. Options:
1. Match all tools (`.*`)
2. Match specific write tools (`Write|Edit|MultiEdit`)
3. Match all file operations (including Read)

### Decision

Match only write operations: `Write|Edit|MultiEdit`

Rationale:
- Read operations don't modify files, no memory context needed
- Bash operations are too varied (could be reads or writes)
- Write/Edit/MultiEdit indicate active development on a file domain

### Consequences

**Positive:**
- Focused triggering reduces hook invocations
- Lower latency impact (fewer hook calls)
- Relevant memories surfaced at editing time

**Negative:**
- Won't inject memories when user reads a file
- Bash file modifications not captured

**Neutral:**
- Can expand matcher later if needed (backward compatible)

### Alternatives Considered

1. **Match all (`.*`)**: Too noisy, hooks fire constantly
2. **Include Read**: Context useful but may be overwhelming
3. **Include Bash**: Hard to determine if Bash is file-related
