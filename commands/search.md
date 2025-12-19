---
description: Search memories with advanced filtering options
argument-hint: "<query> [--type=semantic|text] [--namespace=ns] [--limit=n]"
allowed-tools: ["Bash", "Read"]
---

# /memory:search - Advanced Memory Search

Search memories with advanced filtering and search options.

## Your Task

You will help the user search memories with precise control over search behavior.

### Step 1: Parse Arguments

**Arguments format**: `$ARGUMENTS`

Parse the arguments:
1. Extract `--type=<type>` if present: `semantic` (default) or `text`
2. Extract `--namespace=<ns>` if present
3. Extract `--spec=<spec>` if present
4. Extract `--limit=<n>` if present (default: 10)
5. Extract `--verbose` flag if present
6. Everything else is the search query

If query is missing, use AskUserQuestion to prompt for it.

### Step 2: Execute Search

Use Bash to invoke the Python library:

**Semantic Search** (default - vector similarity):
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory import get_recall_service

recall = get_recall_service()
results = recall.search(
    query='''$QUERY''',
    k=$LIMIT,
    namespace=$NAMESPACE,
    spec=$SPEC,
)

print(f'## Search Results for \"{'''$QUERY'''}\" ({len(results)} found)\n')
if results:
    print('| # | Namespace | Summary | Score | Date |')
    print('|---|-----------|---------|-------|------|')
    for i, r in enumerate(results, 1):
        summary = r.summary[:40].replace('|', '\\|')
        date = r.timestamp.strftime('%Y-%m-%d')
        print(f'| {i} | {r.namespace} | {summary} | {r.score:.2f} | {date} |')
else:
    print('No results found.')
"
```

**Text Search** (keyword/FTS matching):
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory import get_recall_service

recall = get_recall_service()
results = recall.search_text(
    query='''$QUERY''',
    limit=$LIMIT,
    namespace=$NAMESPACE,
    spec=$SPEC,
)

print(f'## Text Search Results for \"{'''$QUERY'''}\" ({len(results)} found)\n')
if results:
    print('| # | Namespace | Summary | Date |')
    print('|---|-----------|---------|------|')
    for i, m in enumerate(results, 1):
        summary = m.summary[:40].replace('|', '\\|')
        date = m.timestamp.strftime('%Y-%m-%d')
        print(f'| {i} | {m.namespace} | {summary} | {date} |')
else:
    print('No results found.')
"
```

Replace:
- `$QUERY` with the search query
- `$LIMIT` with limit (default 10)
- `$NAMESPACE` with `'ns'` or `None`
- `$SPEC` with `'spec'` or `None`

### Step 3: Present Results

**Standard output** (table format):
```
## Search Results for "authentication" (5 found)

| # | Namespace | Summary | Score | Date |
|---|-----------|---------|-------|------|
| 1 | decisions | Use JWT for API auth | 0.94 | 2024-01-15 |
| 2 | learnings | OAuth2 flow patterns | 0.89 | 2024-01-12 |
| 3 | blockers | Auth middleware issue | 0.82 | 2024-01-10 |
| 4 | patterns | Token refresh pattern | 0.75 | 2024-01-05 |
```

**Verbose output** (includes full content):
```
### 1. Decisions: Use JWT for API auth
**Score**: 0.94 | **Date**: 2024-01-15 | **Tags**: auth, api

> We decided to use JWT tokens for API authentication because:
> - Stateless authentication reduces server load
> - Easy to validate without database lookup
> - Built-in expiration support
```

## Search Types Explained

| Type | Description | Best For |
|------|-------------|----------|
| `semantic` | Vector similarity search | Conceptual queries, finding related ideas |
| `text` | Traditional text matching (FTS) | Exact terms, specific identifiers |

## Examples

**User**: `/memory:search "authentication patterns" --type=semantic`
**Action**: Find conceptually similar memories about authentication

**User**: `/memory:search pytest --namespace=learnings`
**Action**: Find learnings containing "pytest"

**User**: `/memory:search database --spec=my-project --verbose`
**Action**: Find memories for specific spec with full content

**User**: `/memory:search "API design" --limit=20`
**Action**: Return up to 20 results for API design

## Memory Capture Reminder

After search results, if patterns emerge or insights are gained from reviewing memories, suggest:

```
💡 **Capture tip**: Did you notice a pattern or gain an insight? Use:
- `[remember] <pattern or insight>` - Inline capture
- `/memory:capture patterns <description>` - Capture a pattern
```

Search results often reveal connections worth preserving as new memories.
