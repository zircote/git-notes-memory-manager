---
description: Search memories with advanced filtering options
argument-hint: "<query> [--type=semantic|text] [--namespace=ns] [--limit=n] [--domain=all|user|project]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
SEARCH(1)                                            User Commands                                            SEARCH(1)

NAME
    search - Search memories with advanced filtering options

SYNOPSIS
    /memory:search <query> [--type=semantic|text] [--namespace=ns] [--limit=n] [--domain=all|user|project]

DESCRIPTION
    Search memories with advanced filtering options.
    Supports searching across domains: user (global) and project (repo-scoped).

OPTIONS
    --type=TYPE               Search type: semantic (default) or text
    --namespace=ns            Filter by namespace (decisions, learnings, etc.)
    --spec=SPEC               Filter by specification ID
    --limit=n                 Maximum results to return (default: 10)
    --domain=DOMAIN           Search scope: all (default), user, or project
    --verbose                 Show full content in results
    --help, -h                Show this help message

DOMAIN VALUES
    all       Search both user (global) and project (repo-scoped) memories
    user      Search only user memories (cross-project, global)
    project   Search only project memories (repo-scoped)

EXAMPLES
    /memory:search "authentication patterns" --type=semantic
    /memory:search pytest --namespace=learnings
    /memory:search --domain=user database patterns
    /memory:search --domain=project --namespace=decisions
    /memory:search --help

SEE ALSO
    /memory:* for related commands

                                                                      SEARCH(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:search - Advanced Memory Search

Search memories with advanced filtering and search options.

## Your Task

You will help the user search memories with precise control over search behavior.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Parse the arguments:
1. Extract `--type=<type>` if present: `semantic` (default) or `text`
2. Extract `--namespace=<ns>` if present
3. Extract `--spec=<spec>` if present
4. Extract `--limit=<n>` if present (default: 10)
5. Extract `--domain=<domain>` if present (one of: `all`, `user`, `project`; default: `all`)
6. Extract `--verbose` flag if present
7. Everything else is the search query

If query is missing, use AskUserQuestion to prompt for it.

**Domain values:**
- `all` - Search both user (global) and project (repo-scoped) memories (default)
- `user` - Search only user memories (cross-project, global)
- `project` - Search only project memories (repo-scoped, current repository)

</step>

<step number="2" name="Execute Search">

Use Bash to invoke the Python library:

**Semantic Search** (default - vector similarity):
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python3 -c "
from git_notes_memory import get_recall_service
from git_notes_memory.config import Domain

recall = get_recall_service()

# Map domain string to Domain enum (None means search all)
domain_str = '''$DOMAIN'''
if domain_str == 'user':
    domain = Domain.USER
elif domain_str == 'project':
    domain = Domain.PROJECT
else:
    domain = None  # 'all' or default - search both domains

results = recall.search(
    query='''$QUERY''',
    k=$LIMIT,
    namespace=$NAMESPACE,
    spec=$SPEC,
    domain=domain,
)

domain_label = {'user': '(user)', 'project': '(project)', 'all': ''}[domain_str or 'all']
print(f'## Search Results for \"{'''$QUERY'''}\" ({len(results)} found) {domain_label}\n')
if results:
    print('| # | Domain | Namespace | Summary | Score | Date |')
    print('|---|--------|-----------|---------|-------|------|')
    for i, r in enumerate(results, 1):
        d_icon = '🌐' if hasattr(r, 'domain') and r.domain == Domain.USER else '📁'
        summary = r.summary[:35].replace('|', '\\|')
        date = r.timestamp.strftime('%Y-%m-%d')
        print(f'| {i} | {d_icon} | {r.namespace} | {summary} | {r.score:.2f} | {date} |')
else:
    print('No results found.')
"
```

**Text Search** (keyword/FTS matching):
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT}" python3 -c "
from git_notes_memory import get_recall_service
from git_notes_memory.config import Domain

recall = get_recall_service()

# Map domain string to Domain enum (None means search all)
domain_str = '''$DOMAIN'''
if domain_str == 'user':
    domain = Domain.USER
elif domain_str == 'project':
    domain = Domain.PROJECT
else:
    domain = None  # 'all' or default - search both domains

results = recall.search_text(
    query='''$QUERY''',
    limit=$LIMIT,
    namespace=$NAMESPACE,
    spec=$SPEC,
    domain=domain,
)

domain_label = {'user': '(user)', 'project': '(project)', 'all': ''}[domain_str or 'all']
print(f'## Text Search Results for \"{'''$QUERY'''}\" ({len(results)} found) {domain_label}\n')
if results:
    print('| # | Domain | Namespace | Summary | Date |')
    print('|---|--------|-----------|---------|------|')
    for i, m in enumerate(results, 1):
        d_icon = '🌐' if hasattr(m, 'domain') and m.domain == Domain.USER else '📁'
        summary = m.summary[:35].replace('|', '\\|')
        date = m.timestamp.strftime('%Y-%m-%d')
        print(f'| {i} | {d_icon} | {m.namespace} | {summary} | {date} |')
else:
    print('No results found.')
"
```

Replace:
- `$QUERY` with the search query
- `$LIMIT` with limit (default 10)
- `$NAMESPACE` with `'ns'` or `None`
- `$SPEC` with `'spec'` or `None`
- `$DOMAIN` with `'all'`, `'user'`, or `'project'` (default: `'all'`)

</step>

<step number="3" name="Present Results">

**Standard output** (table format):
```
## Search Results for "authentication" (5 found)

| # | Domain | Namespace | Summary | Score | Date |
|---|--------|-----------|---------|-------|------|
| 1 | 📁 | decisions | Use JWT for API auth | 0.94 | 2024-01-15 |
| 2 | 🌐 | learnings | OAuth2 flow patterns | 0.89 | 2024-01-12 |
| 3 | 📁 | blockers | Auth middleware issue | 0.82 | 2024-01-10 |
| 4 | 🌐 | patterns | Token refresh pattern | 0.75 | 2024-01-05 |
```

**Domain indicators:**
- 🌐 = User memory (global, cross-project)
- 📁 = Project memory (repo-scoped)

**Verbose output** (includes full content):
```
### 1. 📁 Decisions: Use JWT for API auth
**Score**: 0.94 | **Date**: 2024-01-15 | **Tags**: auth, api

> We decided to use JWT tokens for API authentication because:
> - Stateless authentication reduces server load
> - Easy to validate without database lookup
> - Built-in expiration support
```

</step>

## Search Types Explained

| Type | Description | Best For |
|------|-------------|----------|
| `semantic` | Vector similarity search | Conceptual queries, finding related ideas |
| `text` | Traditional text matching (FTS) | Exact terms, specific identifiers |

## Examples

**User**: `/memory:search "authentication patterns" --type=semantic`
**Action**: Find conceptually similar memories about authentication in both domains

**User**: `/memory:search pytest --namespace=learnings`
**Action**: Find learnings containing "pytest" in both domains

**User**: `/memory:search --domain=user database patterns`
**Action**: Search only user (global) memories for database patterns

**User**: `/memory:search --domain=project --namespace=decisions`
**Action**: Search only project memories for decisions

**User**: `/memory:search database --spec=my-project --verbose`
**Action**: Find project memories for specific spec with full content

**User**: `/memory:search "API design" --limit=20`
**Action**: Return up to 20 results for API design in both domains

## Memory Capture Reminder

After search results, if patterns emerge or insights are gained from reviewing memories, suggest:

```
**Capture tip**: Did you notice a pattern or gain an insight? Use:
- `[remember] <pattern or insight>` - Inline capture to project
- `[global] <pattern or insight>` - Inline capture to user (cross-project)
- `/memory:capture patterns <description>` - Project pattern
- `/memory:capture --global patterns <description>` - User pattern (cross-project)
```

Search results often reveal connections worth preserving as new memories.
- Project-specific patterns → project memories (default)
- Cross-project patterns → user memories (`--global`)

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:recall` | Quick semantic search with context inference |
| `/memory:capture` | Capture insights discovered during search |
| `/memory:status` | View memory counts by namespace |
| `/memory:sync` | Synchronize if search results seem incomplete |
| `/memory:validate` | Validate search pipeline is working |
