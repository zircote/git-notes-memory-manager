---
description: Recall relevant memories for the current context or a specific query
argument-hint: "[query] [--namespace=ns] [--limit=n] [--domain=all|user|project]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
RECALL(1)                                            User Commands                                            RECALL(1)

NAME
    recall - Recall relevant memories for the current context or a s...

SYNOPSIS
    /memory:recall [query] [--namespace=ns] [--limit=n] [--domain=all|user|project]

DESCRIPTION
    Recall relevant memories for the current context or a specific query.
    Supports searching across domains: user (global) and project (repo-scoped).

OPTIONS
    --namespace=ns            Filter by namespace (decisions, learnings, etc.)
    --limit=n                 Maximum results to return (default: 5)
    --domain=DOMAIN           Search scope: all (default), user, or project
    --help, -h                Show this help message

DOMAIN VALUES
    all       Search both user (global) and project (repo-scoped) memories
    user      Search only user memories (cross-project, global)
    project   Search only project memories (repo-scoped)

EXAMPLES
    /memory:recall
    /memory:recall <query>
    /memory:recall --domain=user database patterns
    /memory:recall --domain=project --namespace=decisions
    /memory:recall --help

SEE ALSO
    /memory:* for related commands

                                                                      RECALL(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:recall - Recall Relevant Memories

Retrieve relevant memories from the git-backed memory system.

## Your Task

You will help the user recall memories relevant to their current context or query.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Parse the arguments:
1. Extract `--namespace=<ns>` if present (one of: `decisions`, `learnings`, `blockers`, `progress`, `reviews`, `patterns`, `retrospective`, `inception`, `elicitation`, `research`)
2. Extract `--limit=<n>` if present (default: 5)
3. Extract `--domain=<domain>` if present (one of: `all`, `user`, `project`; default: `all`)
4. Everything else is the search query
5. If no query provided, use recent conversation context

**Domain values:**
- `all` - Search both user (global) and project (repo-scoped) memories (default)
- `user` - Search only user memories (cross-project, global)
- `project` - Search only project memories (repo-scoped, current repository)

</step>

<step number="2" name="Build Search Context">

If query is empty:
- Extract key concepts from recent conversation (last 5-10 messages)
- Look for: file names, function names, error messages, technology terms
- Combine into a search query

</step>

<step number="3" name="Execute Search">

Use Bash to invoke the Python library:

```bash
uv run python3 -c "
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
    namespace=$NAMESPACE,  # None for all namespaces
    k=$LIMIT,
    domain=domain,  # None searches both domains
)

if not results:
    print('No relevant memories found.')
else:
    domain_label = {'user': '(user)', 'project': '(project)', 'all': ''}[domain_str or 'all']
    print(f'## Recalled Memories ({len(results)} results) {domain_label}\n')
    for i, r in enumerate(results, 1):
        # Show domain indicator for multi-domain results
        domain_icon = '🌐' if hasattr(r, 'domain') and r.domain == Domain.USER else '📁'
        print(f'### {i}. {domain_icon} {r.namespace.title()}: {r.summary[:50]}')
        print(f'**Relevance**: {r.score:.2f} | **Captured**: {r.timestamp.strftime(\"%Y-%m-%d\")}')
        print(f'> {r.content[:200]}...\n')
"
```

Replace:
- `$QUERY` with the search query
- `$NAMESPACE` with `'$ns'` or `None`
- `$LIMIT` with the limit number (default 5)
- `$DOMAIN` with `'all'`, `'user'`, or `'project'` (default: `'all'`)

</step>

<step number="4" name="Present Results">

Format the output as:

```
## Recalled Memories (3 results)

### 1. 📁 Decisions: Use PostgreSQL for main database
**Relevance**: 0.92 | **Captured**: 2024-01-15
> Due to JSONB support and strong ecosystem for Python...

### 2. 🌐 Learnings: Connection pooling best practices
**Relevance**: 0.85 | **Captured**: 2024-01-10
> Always use connection pooling in production to prevent...

### 3. 📁 Progress: Database schema completed
**Relevance**: 0.78 | **Captured**: 2024-01-08
> Database migrations are in migrations/ directory...
```

**Domain indicators:**
- 🌐 = User memory (global, cross-project)
- 📁 = Project memory (repo-scoped)

If no results found:
```
No relevant memories found for your query.

**Tips**:
- Try a broader search term
- Try `--domain=all` to search both user and project memories
- Use `/memory:search` for more options
- Check `/memory:status` to verify memories exist
```

</step>

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
**Action**: Search all namespaces in both domains for "database configuration"

**User**: `/memory:recall --namespace=decisions`
**Action**: Return recent decisions from both domains without specific query

**User**: `/memory:recall --domain=user`
**Action**: Search only user (global) memories using conversation context

**User**: `/memory:recall --domain=project --namespace=decisions`
**Action**: Return decisions only from the current project

**User**: `/memory:recall --domain=user database patterns`
**Action**: Search user memories for cross-project database patterns

**User**: `/memory:recall --limit=10 authentication`
**Action**: Search for "authentication" with 10 result limit in both domains

**User**: `/memory:recall`
**Action**: Extract context from recent conversation and search both domains

## Memory Capture Reminder

After showing recalled memories, if the conversation reveals new insights worth preserving, remind the user:

```
**Capture tip**: If you discover something worth remembering, use:
- `[remember] <insight>` - Inline capture to project (repo-scoped)
- `[global] <insight>` - Inline capture to user memories (cross-project)
- `/memory:capture <namespace> <content>` - Project capture with namespace
- `/memory:capture --global <namespace> <content>` - User capture with namespace
```

Consider whether the current context or findings should be captured for future recall.
- Project-specific insights → project memories (default)
- Cross-project patterns, preferences → user memories (`--global`)

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:capture` | Capture a new memory to the system |
| `/memory:search` | Advanced search with type and filter options |
| `/memory:status` | View memory counts and index health |
| `/memory:sync` | Synchronize index if memories seem stale |
| `/memory:validate` | Validate the memory system is working |
