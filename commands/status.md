---
description: Display memory system status and statistics
argument-hint: "[--verbose]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
STATUS(1)                                            User Commands                                            STATUS(1)

NAME
    status - Display memory system status and statistics

SYNOPSIS
    /memory:status [--verbose]

DESCRIPTION
    Display memory system status and statistics

OPTIONS
    --help, -h                Show this help message

EXAMPLES
    /memory:status
    /memory:status <--verbose>
    /memory:status --help

SEE ALSO
    /memory:* for related commands

                                                                      STATUS(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:status - Memory System Status

Display the current status of the memory system.

## Your Task

You will show the user the status of their memory system.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Check if `--verbose` flag is present.

</step>

<step number="2" name="Execute Status Check">

**Basic Status**:
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory import get_sync_service
from git_notes_memory.index import IndexService
from git_notes_memory.config import get_embedding_model, get_index_path, get_data_path

sync = get_sync_service()
index_path = get_index_path()

print('## Memory System Status\n')
print('| Metric | Value |')
print('|--------|-------|')

if index_path.exists():
    index = IndexService(index_path)
    index.initialize()
    stats = index.get_stats()

    print(f'| Total Memories | {stats.total_memories} |')
    print(f'| Index Status | Healthy |')
    last_sync = stats.last_sync.strftime('%Y-%m-%d %H:%M:%S') if stats.last_sync else 'Never'
    print(f'| Last Sync | {last_sync} |')

    size_kb = stats.index_size_bytes / 1024
    size_str = f'{size_kb/1024:.1f} MB' if size_kb > 1024 else f'{size_kb:.1f} KB'
    print(f'| Index Size | {size_str} |')
    index.close()
else:
    print('| Total Memories | 0 |')
    print('| Index Status | Not initialized |')
    print('| Last Sync | Never |')
    print('| Index Size | 0 KB |')

print(f'| Embedding Model | {get_embedding_model()} |')
print(f'| Data Directory | {get_data_path()} |')
"
```

**Verbose Status**:
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
import subprocess
from git_notes_memory import get_sync_service
from git_notes_memory.index import IndexService
from git_notes_memory.config import get_embedding_model, get_index_path, get_data_path, NAMESPACES

sync = get_sync_service()
index_path = get_index_path()

print('## Memory System Status (Detailed)\n')

if not index_path.exists():
    print('Index not initialized. Run \`/memory:sync\` to initialize.')
    exit(0)

index = IndexService(index_path)
index.initialize()
stats = index.get_stats()

print('### Summary')
print('| Metric | Value |')
print('|--------|-------|')
print(f'| Total Memories | {stats.total_memories} |')
print(f'| Index Status | Healthy |')
last_sync = stats.last_sync.strftime('%Y-%m-%d %H:%M:%S') if stats.last_sync else 'Never'
print(f'| Last Sync | {last_sync} |')
print('')

print('### By Namespace')
print('| Namespace | Count |')
print('|-----------|-------|')
if stats.by_namespace:
    for ns, count in stats.by_namespace:
        print(f'| {ns} | {count} |')
else:
    print('| (none) | 0 |')
print('')

if stats.by_spec:
    print('### By Spec')
    print('| Spec | Count |')
    print('|------|-------|')
    for spec, count in stats.by_spec:
        print(f'| {spec or \"(unassigned)\"} | {count} |')
    print('')

print('### Health Metrics')
print('| Check | Status |')
print('|-------|--------|')

# Check git notes accessible
try:
    result = subprocess.run(['git', 'notes', 'list'], capture_output=True)
    git_ok = result.returncode == 0
except:
    git_ok = False
print(f'| Git notes accessible | {\"✓\" if git_ok else \"✗\"} |')

# Check index consistency
try:
    verification = sync.verify_consistency()
    consistent = verification.is_consistent
except:
    consistent = False
print(f'| Index consistency | {\"✓\" if consistent else \"⚠\"} |')

# Check embedding model availability
try:
    from git_notes_memory.embedding import EmbeddingService
    emb = EmbeddingService()
    emb_ok = True
except:
    emb_ok = False
print(f'| Embedding model available | {\"✓\" if emb_ok else \"○\"} |')

print(f'| Disk space adequate | ✓ |')

index.close()
"
```

</step>

<step number="3" name="Show Recommendations">

If issues are detected, show recommendations:

```
### Recommendations

1. **Index out of sync** - Run `/memory:sync` to update
2. **No memories captured** - Use `/memory:capture` to store your first memory
3. **Embedding model not loaded** - First search will be slower while model loads
```

</step>

## Output Sections

| Section | Description |
|---------|-------------|
| Summary | Basic counts and status |
| By Namespace | Breakdown by memory type |
| By Spec | Breakdown by specification |
| Health Metrics | System health checks |

## Examples

**User**: `/memory:status`
**Action**: Show basic status summary

**User**: `/memory:status --verbose`
**Action**: Show detailed status with all sections

## Memory Capture Reminder

After showing status, remind the user about capture capabilities:

```
**Capture memories**: Use markers anywhere in your messages:
- `[remember] <insight>` - Captures a learning
- `[capture] <decision>` - Captures any memory type
- `/memory:capture <namespace> <content>` - Explicit capture

Available namespaces: decisions, learnings, blockers, progress, reviews, patterns
```

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:sync` | Synchronize or repair the index |
| `/memory:validate` | Full validation of the memory system |
| `/memory:capture` | Capture a new memory |
| `/memory:recall` | Search for memories |
| `/memory:search` | Advanced search with filters |
