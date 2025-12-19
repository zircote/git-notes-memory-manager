---
description: Capture a memory (decision, learning, blocker, progress, etc.) to the git-backed memory system
argument-hint: "[namespace] <summary> -- <content>"
allowed-tools: ["Bash", "Write", "Read", "AskUserQuestion"]
---

# /memory:capture - Capture a Memory

Capture information to the git-backed memory system for later retrieval.

## Your Task

You will help the user capture a memory. The memory will be stored as a git note and indexed for semantic search.

### Step 1: Parse the Arguments

**Arguments format**: `$ARGUMENTS`

Parse the arguments:
1. If first word matches a known namespace, use it as the namespace
2. Look for `--` separator: text before is summary, text after is content
3. If no `--` separator, use the entire text as both summary (truncated) and content

**Valid namespaces**: `decisions`, `learnings`, `blockers`, `progress`, `reviews`, `patterns`, `retrospective`, `inception`, `elicitation`, `research`

If no namespace specified, auto-detect based on content patterns:
- Contains "decided", "chose", "will use" → `decisions`
- Contains "learned", "discovered", "TIL", "found out" → `learnings`
- Contains "blocked", "stuck", "cannot", "impediment" → `blockers`
- Contains "completed", "finished", "milestone" → `progress`
- Contains "pattern", "recurring", "often" → `patterns`
- Default → `learnings`

### Step 2: Validate Content

If `$ARGUMENTS` is empty or very short (< 10 characters):
- Use AskUserQuestion to prompt for the memory content
- Question: "What would you like to capture?"
- Provide examples for each memory type

### Step 3: Capture the Memory

Use Bash to invoke the Python library:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory import get_capture_service

capture = get_capture_service()
result = capture.capture(
    namespace='$NAMESPACE',
    summary='''$SUMMARY''',
    content='''$CONTENT''',
)

if result.success:
    print(f'Captured as {result.memory.namespace}: {result.memory.id[:16]}...')
    print(f'Summary: {result.memory.summary}')
    if result.warning:
        print(f'Warning: {result.warning}')
else:
    print(f'Capture failed')
"
```

Replace:
- `$NAMESPACE` with the detected namespace
- `$SUMMARY` with a one-line summary (max 100 chars, escape quotes)
- `$CONTENT` with the full content (escape quotes)

### Step 4: Confirm to User

Show the result:
```
Memory captured!

**Namespace**: decisions
**ID**: decisions:abc123:0
**Summary**: Use PostgreSQL for the main database...

This memory will be available for recall in future sessions.
Use `/memory:recall` to retrieve it.
```

## Namespace Reference

| Namespace | Use For | Example |
|-----------|---------|---------|
| `decisions` | Architectural or design decisions | "Use PostgreSQL for JSONB support" |
| `learnings` | New knowledge or discoveries | "pytest fixtures can be module-scoped" |
| `blockers` | Obstacles and impediments | "API rate limiting blocking progress" |
| `progress` | Milestones and completions | "Completed Phase 1 implementation" |
| `reviews` | Code review findings | "Found SQL injection in auth module" |
| `patterns` | Recurring patterns | "Error handling follows Result pattern" |
| `retrospective` | Post-mortems and retrospectives | "Project completed successfully" |
| `inception` | Problem statements and scope | "Building a memory plugin for Claude" |
| `elicitation` | Requirements clarifications | "Must support offline mode" |
| `research` | External findings | "Evaluated 3 embedding models" |

## Convenience Methods

For structured captures, the library also provides:
- `capture_decision(spec, summary, context, rationale, alternatives)` - Decisions with rationale
- `capture_blocker(spec, summary, description, impact)` - Blockers with impact
- `capture_learning(summary, insight, context)` - Learnings with context
- `capture_progress(spec, summary, milestone, details)` - Progress updates
- `capture_pattern(summary, pattern_type, evidence, confidence)` - Patterns
- `capture_review(spec, summary, findings, verdict)` - Code reviews

## Error Handling

If the capture fails:
1. Check if we're in a git repository: `git rev-parse --git-dir`
2. Check if the library is installed: `uv run python3 -c "import git_notes_memory"`
3. Show helpful error message with recovery action

## Examples

**User**: `/memory:capture decisions Use Redis for session storage -- Due to built-in expiration and cluster support`
**Action**: Capture as decisions namespace with structured content

**User**: `/memory:capture TIL you can use pytest -k to filter tests by name`
**Action**: Auto-detect as learnings (contains "TIL"), content becomes both summary and body

**User**: `/memory:capture This project requires Python 3.10+`
**Action**: Auto-detect as learnings (general information)

## Memory Capture Reminder

After successfully capturing a memory, remind the user:

```
💡 **Pro tip**: You can capture memories inline using markers:
- `[remember] <insight>` - Captures a learning
- `[capture] <decision>` - Captures any type of memory
- `@memory <content>` - Same as [capture]

These markers work anywhere in your message and are automatically processed.
