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
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
from git_notes_memory import get_sync_service
from git_notes_memory.index import IndexService
from git_notes_memory.config import (
    get_embedding_model, get_project_index_path, get_user_index_path,
    get_data_path, get_user_memories_path, get_user_memories_remote
)

print('## Memory System Status\n')

# Project memories
print('### Project Memories (repo-scoped)\n')
print('| Metric | Value |')
print('|--------|-------|')

index_path = get_project_index_path()
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

print('')

# User memories (global, cross-project)
print('### User Memories (global)\n')
print('| Metric | Value |')
print('|--------|-------|')

user_index_path = get_user_index_path()
user_repo_path = get_user_memories_path()

if user_index_path.exists():
    user_index = IndexService(user_index_path)
    user_index.initialize()
    user_stats = user_index.get_stats()

    print(f'| Total Memories | {user_stats.total_memories} |')
    print(f'| Index Status | Healthy |')
    user_last_sync = user_stats.last_sync.strftime('%Y-%m-%d %H:%M:%S') if user_stats.last_sync else 'Never'
    print(f'| Last Sync | {user_last_sync} |')

    user_size_kb = user_stats.index_size_bytes / 1024
    user_size_str = f'{user_size_kb/1024:.1f} MB' if user_size_kb > 1024 else f'{user_size_kb:.1f} KB'
    print(f'| Index Size | {user_size_str} |')
    user_index.close()
else:
    print('| Total Memories | 0 |')
    print('| Index Status | Not initialized |')
    print('| Last Sync | Never |')
    print('| Index Size | 0 KB |')

repo_status = '✓ Initialized' if user_repo_path.exists() else '○ Not initialized'
print(f'| Bare Repo | {repo_status} |')

remote_url = get_user_memories_remote()
remote_status = f'✓ {remote_url[:30]}...' if remote_url and len(remote_url) > 30 else (remote_url or '○ Not configured')
print(f'| Remote Sync | {remote_status} |')

print('')
print('### Configuration\n')
print('| Setting | Value |')
print('|---------|-------|')
print(f'| Embedding Model | {get_embedding_model()} |')
print(f'| Data Directory | {get_data_path()} |')
"
```

**Verbose Status**:
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
import subprocess
from git_notes_memory import get_sync_service
from git_notes_memory.index import IndexService
from git_notes_memory.config import (
    get_embedding_model, get_project_index_path, get_user_index_path,
    get_data_path, get_user_memories_path, get_user_memories_remote, NAMESPACES
)

sync = get_sync_service()
project_index_path = get_project_index_path()
user_index_path = get_user_index_path()

print('## Memory System Status (Detailed)\n')

# Project Memories Section
print('### Project Memories (repo-scoped)\n')

if not project_index_path.exists():
    print('Index not initialized. Run \`/memory:sync\` to initialize.\n')
else:
    project_index = IndexService(project_index_path)
    project_index.initialize()
    project_stats = project_index.get_stats()

    print('#### Summary')
    print('| Metric | Value |')
    print('|--------|-------|')
    print(f'| Total Memories | {project_stats.total_memories} |')
    print(f'| Index Status | Healthy |')
    last_sync = project_stats.last_sync.strftime('%Y-%m-%d %H:%M:%S') if project_stats.last_sync else 'Never'
    print(f'| Last Sync | {last_sync} |')
    print('')

    print('#### By Namespace')
    print('| Namespace | Count |')
    print('|-----------|-------|')
    if project_stats.by_namespace:
        for ns, count in project_stats.by_namespace:
            print(f'| {ns} | {count} |')
    else:
        print('| (none) | 0 |')
    print('')

    if project_stats.by_spec:
        print('#### By Spec')
        print('| Spec | Count |')
        print('|------|-------|')
        for spec, count in project_stats.by_spec:
            print(f'| {spec or \"(unassigned)\"} | {count} |')
        print('')

    project_index.close()

# User Memories Section
print('### User Memories (global)\n')

user_repo_path = get_user_memories_path()
if not user_index_path.exists():
    print('Index not initialized.\n')
else:
    user_index = IndexService(user_index_path)
    user_index.initialize()
    user_stats = user_index.get_stats()

    print('#### Summary')
    print('| Metric | Value |')
    print('|--------|-------|')
    print(f'| Total Memories | {user_stats.total_memories} |')
    print(f'| Index Status | Healthy |')
    user_last_sync = user_stats.last_sync.strftime('%Y-%m-%d %H:%M:%S') if user_stats.last_sync else 'Never'
    print(f'| Last Sync | {user_last_sync} |')
    print('')

    print('#### By Namespace')
    print('| Namespace | Count |')
    print('|-----------|-------|')
    if user_stats.by_namespace:
        for ns, count in user_stats.by_namespace:
            print(f'| {ns} | {count} |')
    else:
        print('| (none) | 0 |')
    print('')

    user_index.close()

# Storage info
print('#### Storage')
print('| Setting | Value |')
print('|---------|-------|')
repo_status = '✓ Initialized' if user_repo_path.exists() else '○ Not initialized'
print(f'| Bare Repo | {repo_status} |')
remote_url = get_user_memories_remote()
remote_status = f'✓ {remote_url[:30]}...' if remote_url and len(remote_url) > 30 else (remote_url or '○ Not configured')
print(f'| Remote Sync | {remote_status} |')
print('')

# Health Metrics
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

# Check project index consistency
try:
    verification = sync.verify_consistency()
    consistent = verification.is_consistent
except:
    consistent = False
print(f'| Project index consistency | {\"✓\" if consistent else \"⚠\"} |')

# Check user repo accessible
try:
    user_repo_ok = user_repo_path.exists()
except:
    user_repo_ok = False
print(f'| User repo accessible | {\"✓\" if user_repo_ok else \"○\"} |')

# Check embedding model availability
try:
    from git_notes_memory.embedding import EmbeddingService
    emb = EmbeddingService()
    emb_ok = True
except:
    emb_ok = False
print(f'| Embedding model available | {\"✓\" if emb_ok else \"○\"} |')

print(f'| Disk space adequate | ✓ |')
"
```

</step>

<step number="3" name="Show Recommendations">

If issues are detected, show recommendations:

```
### Recommendations

1. **Project index out of sync** - Run `/memory:sync` to update project memories
2. **User memories not initialized** - User memories will be created on first global capture
3. **No memories captured** - Use `/memory:capture` to store your first memory
4. **User remote not configured** - Set `USER_MEMORIES_REMOTE` to sync global memories across machines
5. **Embedding model not loaded** - First search will be slower while model loads
```

</step>

## Output Sections

| Section | Description |
|---------|-------------|
| Project Memories | Repo-scoped memory counts and status |
| User Memories | Global cross-project memory counts and status |
| By Namespace | Breakdown by memory type (per domain) |
| By Spec | Breakdown by specification (project only) |
| Storage | User bare repo and remote sync configuration |
| Health Metrics | System health checks for both domains |

## Examples

**User**: `/memory:status`
**Action**: Show basic status summary

**User**: `/memory:status --verbose`
**Action**: Show detailed status with all sections

## Memory Capture Reminder

After showing status, remind the user about capture capabilities:

```
**Capture memories**: Use markers anywhere in your messages:
- `[remember] <insight>` - Captures a learning (project-scoped)
- `[global] <insight>` - Captures to user memories (cross-project)
- `[user] <insight>` - Captures to user memories (cross-project)
- `/memory:capture <namespace> <content>` - Explicit project capture
- `/memory:capture --global <namespace> <content>` - Explicit user capture

**Domain prefixes for block captures:**
- `global:decision` or `user:learned` - Captures to user memories
- `project:decision` or `local:learned` - Captures to project memories (default)

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
