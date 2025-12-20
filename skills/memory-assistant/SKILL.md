---
name: memory-assistant
description: >
  Comprehensive memory management skill that guides memory capture and recall throughout sessions.
  Triggers when: user makes architectural decisions ("let's use", "we should", "decided to", "choosing"),
  discovers learnings ("TIL", "learned that", "discovered", "found out", "realized"),
  encounters blockers ("stuck on", "blocked by", "cannot", "impediment"),
  achieves progress ("completed", "finished", "milestone", "done with"),
  identifies patterns ("pattern", "we always", "recurring", "common approach"),
  asks about past work ("what did we decide", "why did we", "how did we solve", "remember when", "previously"),
  requests memory operations ("capture this", "remember this", "save this decision", "recall", "search memories"),
  or starts work on topics with likely stored context ("working on authentication", "implementing database", "debugging").
version: 0.3.0
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# Memory Assistant Skill

A comprehensive skill that facilitates memory capture, recall, and lifecycle management for the git-notes-memory plugin. This skill helps Claude proactively suggest memory captures, surface relevant context, and reinforce persistent memory practices.

## Purpose

This skill serves as an intelligent memory assistant that:
1. **Detects capture opportunities** - Recognizes decisions, learnings, blockers, and patterns worth preserving
2. **Surfaces relevant context** - Proactively recalls memories when working on related topics
3. **Guides best practices** - Helps users get maximum value from the memory system
4. **Maintains memory hygiene** - Suggests reviews, updates, and lifecycle management

## Core Workflows

### Workflow 1: Capture Detection

When the conversation reveals content worth preserving, this skill activates to guide capture.

#### Decision Detection
**Trigger patterns**: "decided to", "choosing", "we'll use", "going with", "selected"

```python
# Detect decision-worthy content
decision_signals = [
    "decided to", "choosing", "we'll use", "going with",
    "selected", "will implement", "the approach is"
]

# If detected, suggest capture:
"""
💡 **Decision detected**: You just made an architectural choice.
Would you like to capture this decision for future reference?

Use: `/memory:capture decisions <summary> -- <rationale>`

Example: `/memory:capture decisions Use PostgreSQL for data layer -- JSONB support and team familiarity outweigh SQLite simplicity`
"""
```

#### Learning Detection
**Trigger patterns**: "TIL", "learned that", "discovered", "found out", "realized", "turns out"

```python
learning_signals = [
    "TIL", "learned that", "discovered", "found out",
    "realized", "turns out", "didn't know", "interesting that"
]

# If detected, suggest capture:
"""
💡 **Learning detected**: You discovered something worth remembering.

Use: `[remember] <insight>` inline, or
     `/memory:capture learnings <summary>`
"""
```

#### Blocker Detection
**Trigger patterns**: "stuck on", "blocked by", "cannot", "impediment", "failing"

```python
blocker_signals = [
    "stuck on", "blocked by", "cannot", "impediment",
    "failing", "doesn't work", "breaking", "prevents"
]

# If detected, suggest capture:
"""
💡 **Blocker identified**: Recording this can help future debugging.

Use: `/memory:capture blockers <issue> -- <impact and context>`
"""
```

### Workflow 2: Proactive Recall

When starting work on a topic, automatically check for relevant memories.

#### Context-Based Recall
**Trigger**: Starting work on a feature, component, or system

```bash
uv run python3 -c "
from git_notes_memory import get_recall_service

recall = get_recall_service()

# Extract key terms from current context
context_terms = '$CONTEXT_TERMS'  # e.g., 'authentication', 'database', 'API'

results = recall.search(
    query=context_terms,
    k=5,
    min_similarity=0.6  # Balance relevance and coverage
)

if results:
    print('## Relevant Memories Found\n')
    for r in results:
        print(f'- **{r.namespace}**: {r.summary} (relevance: {r.score:.0%})')
    print('\nUse `/memory:recall` for details or `/memory:search` for more results.')
else:
    print('No directly relevant memories found for this context.')
"
```

#### Question-Triggered Recall
**Trigger patterns**: "what did we decide", "why did we", "how did we solve", "remember when"

```bash
uv run python3 -c "
from git_notes_memory import get_recall_service

recall = get_recall_service()

# Direct query from user question
results = recall.search(
    query='$USER_QUESTION',
    k=5,
    min_similarity=0.7  # Higher threshold for direct questions
)

if results:
    print('## Memories Matching Your Question\n')
    for i, r in enumerate(results, 1):
        print(f'{i}. **{r.namespace.title()}**: {r.summary}')
        print(f'   Captured: {r.timestamp.strftime(\"%Y-%m-%d\")} | Relevance: {r.score:.0%}')
        print(f'   > {r.content[:150]}...\n')
"
```

### Workflow 3: Session Memory Review

At natural breakpoints, suggest reviewing and capturing session insights.

#### End-of-Task Review
**Trigger**: Task completion, feature implementation, bug resolution

```
## Session Memory Review

Before moving on, consider capturing these potential memories:

### Decisions Made
- [ ] Architectural choices
- [ ] Technology selections
- [ ] Design trade-offs

### Learnings Discovered
- [ ] New techniques learned
- [ ] Gotchas encountered
- [ ] Performance insights

### Patterns Identified
- [ ] Reusable approaches
- [ ] Best practices confirmed
- [ ] Anti-patterns avoided

Use `/memory:capture <namespace> <content>` or inline markers:
- `[remember] <learning>`
- `[capture] <any memory type>`
```

## Namespace Quick Reference

| Namespace | When to Capture | Example Triggers |
|-----------|-----------------|------------------|
| `inception` | Project scope, goals, success criteria | "building a...", "project goals" |
| `elicitation` | Requirements, constraints clarified | "must support", "requirement" |
| `research` | External findings, evaluations | "evaluated", "compared", "benchmark" |
| `decisions` | Architectural/design choices | "decided to", "choosing", "trade-off" |
| `progress` | Milestones, completions | "completed", "finished", "milestone" |
| `blockers` | Obstacles, impediments | "stuck on", "blocked by", "cannot" |
| `reviews` | Code review findings | "found in review", "security issue" |
| `learnings` | Knowledge discoveries | "TIL", "learned", "discovered" |
| `retrospective` | Post-mortems, lessons | "retrospective", "lessons learned" |
| `patterns` | Recurring solutions | "pattern", "common approach", "idiom" |

## Integration with Hooks

This skill complements the plugin's hook system. Understanding their interaction prevents confusion and duplication.

### How Hooks and This Skill Differ

| Aspect | Hooks | This Skill |
|--------|-------|------------|
| **Trigger** | System events (start, prompt, stop) | Conversation patterns |
| **Capture** | Auto-captures with markers | **Suggests only** - never auto-captures |
| **Scope** | Fixed behavior | Context-aware guidance |

### SessionStart Hook
The hook injects:
- Memory system status (count, health)
- Reminder about capture markers

**This skill extends** by:
- Suggesting specific searches based on conversation
- Highlighting memories that may be particularly relevant to current topic

### UserPromptSubmit Hook
The hook:
- Detects explicit markers: `[remember]`, `[capture]`, `@memory`
- Auto-captures to `learnings` namespace
- **Only acts when user explicitly marks content**

**This skill complements** by:
- Recognizing when markers might be appropriate (but doesn't add them)
- Guiding proper namespace selection beyond just `learnings`
- Explaining why something is capture-worthy

### Stop Hook
The hook:
- Analyzes session for uncaptured memorable content
- Shows generic prompt if content detected
- Syncs the index

**This skill reduces redundancy** by:
- Providing specific, in-context suggestions during the session
- Users who follow skill suggestions won't see Stop hook prompts for the same content

### Avoiding Duplication

**No duplicate captures occur** because:
1. Hooks require explicit markers - skill suggestions don't contain markers
2. Skill never auto-captures - only guides the user
3. User maintains full control over what gets captured

**To minimize redundant suggestions:**
- When the skill suggests capture, using `/memory:capture` satisfies both the skill's guidance AND prevents Stop hook from prompting for the same content
- The skill's real-time suggestions are more specific than the Stop hook's end-of-session generic prompt

## Inline Capture Markers

Capture memories without interrupting your flow:

| Marker | Effect | Example |
|--------|--------|---------|
| `[remember] <text>` | Captures as learning | `[remember] pytest -k filters by test name` |
| `[capture] <text>` | Auto-detects namespace | `[capture] Chose Redis for caching` |
| `@memory <text>` | Same as [capture] | `@memory API rate limit is 100 req/min` |

## Command Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `/memory:capture` | Store a memory | `/memory:capture decisions Use JWT -- Stateless auth` |
| `/memory:recall` | Retrieve memories | `/memory:recall authentication` |
| `/memory:search` | Advanced search | `/memory:search --namespace=learnings pytest` |
| `/memory:status` | System health | `/memory:status --verbose` |
| `/memory:sync` | Index maintenance | `/memory:sync verify` |

## Python API Reference

When executing inline captures via bash, use these EXACT API signatures:

### Capture API
```python
from git_notes_memory import get_capture_service

capture = get_capture_service()
result = capture.capture(
    namespace='learnings',  # REQUIRED: one of decisions, learnings, blockers, progress, etc.
    summary='Short description',  # REQUIRED: max 100 chars
    content='Full content here',  # Optional: detailed content
    tags=['tag1', 'tag2'],  # Optional: list of tags
    spec='project-name',  # Optional: project/spec identifier
)

# Result attributes:
if result.success:
    print(f'Namespace: {result.memory.namespace}')  # NOT result.namespace
    print(f'ID: {result.memory.id}')  # NOT result.memory_id
    print(f'Summary: {result.memory.summary}')
else:
    print(f'Warning: {result.warning}')
```

### Recall API
```python
from git_notes_memory import get_recall_service

recall = get_recall_service()
results = recall.search(
    query='search terms',  # REQUIRED
    k=5,  # Optional: number of results (default 5)
    namespace='learnings',  # Optional: filter by namespace (or None for all)
    min_similarity=0.6,  # Optional: minimum similarity threshold
)

# Each result has:
for r in results:
    print(f'{r.namespace}: {r.summary}')
    print(f'Score: {r.score}, Content: {r.content}')
    print(f'Timestamp: {r.timestamp}')
```

### Bash Wrapper Pattern
Always use this pattern when executing Python via bash:
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory import get_capture_service
# ... your code here
"
```

## Best Practices

### When to Capture

**DO capture:**
- Decisions that took deliberation
- Learnings that surprised you
- Blockers and their resolutions
- Patterns you've applied multiple times
- Context that future-you will need

**DON'T capture:**
- Trivial implementation details
- Temporary workarounds (unless as blockers)
- Information easily found in docs
- Sensitive credentials or secrets

### Memory Quality Guidelines

1. **Summaries should be scannable**: Max 100 characters, key insight first
2. **Content should be self-contained**: Include enough context to understand standalone
3. **Use consistent tags**: Enables better cross-namespace search
4. **Link related memories**: Reference decision IDs in patterns/learnings
5. **Update stale memories**: Mark outdated content as archived

## Reference Files

For detailed implementation patterns and guidance:

- **`references/namespace-guide.md`** - Detailed guide for each namespace
- **`references/search-optimization.md`** - Query tuning techniques
- **`references/capture-patterns.md`** - Recognition patterns for capture opportunities
- **`references/recall-strategies.md`** - Context-aware recall strategies
- **`references/memory-workflow.md`** - End-to-end memory lifecycle workflow

## Examples

### Example 1: Decision Capture Flow

**User says**: "Let's use PostgreSQL instead of SQLite for the main database"

**Assistant recognizes**: Decision signal ("Let's use")

**Assistant response**:
```
Good choice for PostgreSQL.

💡 **Capture this decision?** This architectural choice is worth preserving.

Would you like me to capture it? Here's a suggested format:

`/memory:capture decisions Use PostgreSQL over SQLite -- JSONB support, better concurrency, team familiarity. Trade-off: more operational complexity.`
```

### Example 2: Proactive Recall

**User says**: "I'm going to work on the authentication system"

**Assistant action**: Search memories for "authentication"

**Assistant response**:
```
## Relevant Context Found

Before you start, here are related memories:

1. **Decisions**: Use JWT for stateless authentication (2024-01-15, 94% relevant)
2. **Learnings**: Refresh tokens need secure httpOnly storage (2024-01-10, 89% relevant)
3. **Patterns**: Token validation middleware pattern (2024-01-08, 82% relevant)

Would you like me to show the full content of any of these?
```

### Example 3: Learning Recognition

**User says**: "Oh interesting, TIL you can use `pytest -k` to filter tests by name pattern"

**Assistant recognizes**: Learning signal ("TIL")

**Assistant response**:
```
That's a useful discovery!

I'll capture this learning for you:

[remember] pytest -k flag filters tests by name pattern matching, useful for running subsets of tests

Captured to the `learnings` namespace. You'll be reminded of this when working with pytest in the future.
```

## Troubleshooting

### No Memories Recalled

1. Check if memories exist: `/memory:status`
2. Verify index is synced: `/memory:sync verify`
3. Try broader search terms: `/memory:search <broader query>`
4. Check specific namespace: `/memory:recall --namespace=decisions`

### Capture Failures

1. Verify in a git repository: `git rev-parse --git-dir`
2. Check library installation: `uv run python3 -c "import git_notes_memory"`
3. Check disk space and permissions
4. Review error message for specific guidance

### Index Inconsistencies

1. Verify consistency: `/memory:sync verify`
2. Repair if needed: `/memory:sync repair`
3. Full reindex as last resort: `/memory:sync full`
