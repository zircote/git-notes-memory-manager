---
description: Recall relevant memories for the current context or a specific query
argument-hint: "[query] [--namespace=ns] [--limit=n]"
allowed-tools: ["Bash", "Read"]
---

# /memory:recall - Recall Relevant Memories

Retrieve relevant memories from the git-backed memory system.

## Your Task

You will help the user recall memories relevant to their current context or query.

### Step 1: Parse Arguments

**Arguments format**: `$ARGUMENTS`

Parse the arguments:
1. Extract `--namespace=<ns>` if present (one of: `decisions`, `learnings`, `blockers`, `progress`, `reviews`, `patterns`, `retrospective`, `inception`, `elicitation`, `research`)
2. Extract `--limit=<n>` if present (default: 5)
3. Everything else is the search query
4. If no query provided, use recent conversation context

### Step 2: Build Search Context

If query is empty:
- Extract key concepts from recent conversation (last 5-10 messages)
- Look for: file names, function names, error messages, technology terms
- Combine into a search query

### Step 3: Execute Search

Use Bash to invoke the Python library:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory import get_recall_service

recall = get_recall_service()
results = recall.search(
    query='''$QUERY''',
    namespace=$NAMESPACE,  # None for all namespaces
    k=$LIMIT,
)

if not results:
    print('No relevant memories found.')
else:
    print(f'## Recalled Memories ({len(results)} results)\n')
    for i, r in enumerate(results, 1):
        # Use summary (not title) and timestamp (not created_at)
        print(f'### {i}. {r.namespace.title()}: {r.summary[:50]}')
        print(f'**Relevance**: {r.score:.2f} | **Captured**: {r.timestamp.strftime(\"%Y-%m-%d\")}')
        print(f'> {r.content[:200]}...\n')
"
```

Replace:
- `$QUERY` with the search query
- `$NAMESPACE` with `'$ns'` or `None`
- `$LIMIT` with the limit number (default 5)

### Step 4: Present Results

Format the output as:

```
## Recalled Memories (3 results)

### 1. Decisions: Use PostgreSQL for main database
**Relevance**: 0.92 | **Captured**: 2024-01-15
> Due to JSONB support and strong ecosystem for Python...

### 2. Learnings: Connection pooling best practices
**Relevance**: 0.85 | **Captured**: 2024-01-10
> Always use connection pooling in production to prevent...

### 3. Progress: Database schema completed
**Relevance**: 0.78 | **Captured**: 2024-01-08
> Database migrations are in migrations/ directory...
```

If no results found:
```
No relevant memories found for your query.

**Tips**:
- Try a broader search term
- Use `/memory:search` for more options
- Check `/memory:status` to verify memories exist
```

## Namespace Reference

| Namespace | Contains |
|-----------|----------|
| `decisions` | Architectural and design decisions |
| `learnings` | Knowledge and discoveries |
| `blockers` | Obstacles and impediments |
| `progress` | Milestones and completions |
| `reviews` | Code review findings |
| `patterns` | Recurring patterns and idioms |

## Examples

**User**: `/memory:recall database configuration`
**Action**: Search all namespaces for "database configuration"

**User**: `/memory:recall --namespace=decisions`
**Action**: Return recent decisions without specific query

**User**: `/memory:recall --limit=10 authentication`
**Action**: Search for "authentication" with 10 result limit

**User**: `/memory:recall`
**Action**: Extract context from recent conversation and search

## Memory Capture Reminder

After showing recalled memories, if the conversation reveals new insights worth preserving, remind the user:

```
💡 **Capture tip**: If you discover something worth remembering, use:
- `[remember] <insight>` - Inline capture of learnings
- `/memory:capture <namespace> <content>` - Explicit capture with namespace
```

Consider whether the current context or findings should be captured for future recall.
