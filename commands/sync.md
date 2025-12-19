---
description: Synchronize the memory index with git notes
argument-hint: "[full|verify|repair] [--dry-run]"
allowed-tools: ["Bash", "Read"]
---

# /memory:sync - Synchronize Memory Index

Synchronize the local search index with git notes storage.

## Your Task

You will help the user synchronize or repair the memory index.

### Step 1: Parse Arguments

**Arguments format**: `$ARGUMENTS`

Parse the arguments:
1. First positional argument is mode: `incremental` (default), `full`, `verify`, or `repair`
2. Extract `--dry-run` flag if present

### Step 2: Execute Sync

Use Bash to invoke the Python library based on mode:

**Incremental Sync** (default):
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
import time
from git_notes_memory import get_sync_service

sync = get_sync_service()
start = time.time()
count = sync.reindex(full=False)
duration = time.time() - start

print('## Sync Complete (Incremental)\n')
print('| Metric | Value |')
print('|--------|-------|')
print(f'| Memories indexed | {count} |')
print(f'| Duration | {duration:.2f}s |')
"
```

**Full Reindex**:
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
import time
from git_notes_memory import get_sync_service

sync = get_sync_service()
start = time.time()
count = sync.reindex(full=True)
duration = time.time() - start

print('## Sync Complete (Full Reindex)\n')
print('| Metric | Value |')
print('|--------|-------|')
print(f'| Memories indexed | {count} |')
print(f'| Duration | {duration:.2f}s |')
"
```

**Verify Consistency**:
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory import get_sync_service

sync = get_sync_service()
result = sync.verify_consistency()

if result.is_consistent:
    print('## Verification: Consistent\n')
    print('Index and git notes are in sync.')
else:
    print('## Verification: Inconsistencies Found\n')
    print('| Issue | Count |')
    print('|-------|-------|')
    print(f'| Missing from index | {len(result.missing_in_index)} |')
    print(f'| Orphaned in index | {len(result.orphaned_in_index)} |')
    print(f'| Content mismatch | {len(result.mismatched)} |')
    print('')
    print('Run \`/memory:sync repair\` to fix issues.')
"
```

**Repair**:
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory import get_sync_service

sync = get_sync_service()

# First verify to get current state
verification = sync.verify_consistency()
if verification.is_consistent:
    print('## No Repair Needed\n')
    print('Index is already consistent with git notes.')
else:
    # Perform repair
    repaired = sync.repair(verification)
    print('## Repair Complete\n')
    print('| Action | Count |')
    print('|--------|-------|')
    print(f'| Issues fixed | {repaired} |')
    print('')
    print('Index is now consistent with git notes.')
"
```

### Step 3: Handle Dry Run

If `--dry-run` is specified, show what would happen without making changes:
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory import get_sync_service

sync = get_sync_service()
result = sync.verify_consistency()

print('## Dry Run - No Changes Made\n')
print('**Would perform:**')
print(f'- Add {len(result.missing_in_index)} memories to index')
print(f'- Remove {len(result.orphaned_in_index)} orphaned entries')
print(f'- Update {len(result.mismatched)} mismatched entries')
print('')
print('Run without --dry-run to apply changes.')
"
```

## When to Use Each Mode

| Mode | When to Use |
|------|-------------|
| `incremental` | After normal use, quick sync of new changes (default) |
| `full` | After major changes, index seems corrupted |
| `verify` | To check consistency without changes |
| `repair` | To fix detected inconsistencies |

## Examples

**User**: `/memory:sync`
**Action**: Run incremental sync (default)

**User**: `/memory:sync full`
**Action**: Complete reindex from scratch

**User**: `/memory:sync verify`
**Action**: Check for inconsistencies

**User**: `/memory:sync repair`
**Action**: Fix any inconsistencies found

**User**: `/memory:sync full --dry-run`
**Action**: Show what full reindex would do

## Memory Capture Reminder

After a sync operation, remind the user that new memories are immediately available:

```
💡 **Ready to capture**: Your memory index is now synced. Use:
- `[remember] <learning>` - Quick inline capture
- `/memory:capture <namespace> <content>` - Explicit capture
```
