---
description: Synchronize the memory index with git notes (local or remote)
argument-hint: "[full|verify|repair|--remote] [--dry-run]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
SYNC(1)                                              User Commands                                              SYNC(1)

NAME
    sync - Synchronize the memory index with git notes (local or remote)

SYNOPSIS
    /memory:sync [full|verify|repair|--remote] [--dry-run]

DESCRIPTION
    Synchronize the memory index with git notes. Supports both local index
    synchronization and remote sync with origin repository.

OPTIONS
    --help, -h                Show this help message
    --remote                  Sync with remote (fetch→merge→push workflow)
    --dry-run                 Preview changes without applying

MODES
    (default)                 Incremental local index sync
    full                      Complete reindex from git notes
    verify                    Check consistency without changes
    repair                    Fix detected inconsistencies
    --remote                  Sync with remote origin repository

EXAMPLES
    /memory:sync              Incremental local sync
    /memory:sync full         Full reindex
    /memory:sync verify       Check consistency
    /memory:sync repair       Fix inconsistencies
    /memory:sync --remote     Fetch, merge, and push with origin
    /memory:sync --dry-run    Preview what would change

SEE ALSO
    /memory:* for related commands

                                                                      SYNC(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:sync - Synchronize Memory Index

Synchronize the local search index with git notes storage.

## Your Task

You will help the user synchronize or repair the memory index.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Parse the arguments:
1. Check for `--remote` flag (triggers remote sync mode)
2. First positional argument is mode: `incremental` (default), `full`, `verify`, or `repair`
3. Extract `--dry-run` flag if present

**If `--remote` is present, skip to Step 4 (Remote Sync).**

</step>

<step number="2" name="Execute Sync">

Use Bash to invoke the Python library based on mode:

**Incremental Sync** (default):
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
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
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
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
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
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
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
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

</step>

<step number="3" name="Handle Dry Run">

If `--dry-run` is specified, show what would happen without making changes:
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
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

</step>

<step number="4" name="Remote Sync">

If `--remote` flag is present, synchronize with the remote origin repository.

**Remote Sync** (fetch → merge → push):
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
import time
from git_notes_memory import get_sync_service

sync = get_sync_service()
start = time.time()

# Sync with remote (fetch → merge → push)
results = sync.sync_with_remote()
duration = time.time() - start

# Count successes
success_count = sum(1 for v in results.values() if v)
total_count = len(results)

print('## Remote Sync Complete\n')
print('| Namespace | Status |')
print('|-----------|--------|')
for ns, success in sorted(results.items()):
    status = '✓ synced' if success else '⚠ no changes'
    print(f'| {ns} | {status} |')
print('')
print(f'**Summary**: {success_count}/{total_count} namespaces synced in {duration:.2f}s')
"
```

**Remote Sync Dry Run** (fetch only, no merge/push):
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
from git_notes_memory.git_ops import GitOps

git_ops = GitOps()

# Check what would be fetched (without merging or pushing)
print('## Remote Sync Dry Run - No Changes Made\n')
print('**Would perform:**')
print('1. Fetch notes from origin to tracking refs')
print('2. Merge tracking refs into local notes (cat_sort_uniq strategy)')
print('3. Push merged notes back to origin')
print('4. Reindex local SQLite index')
print('')

# Check if sync is configured
status = git_ops.is_sync_configured()
if status.get('fetch') and status.get('push'):
    print('**Status**: Remote sync is configured ✓')
    if status.get('fetch_old') and not status.get('fetch_new'):
        print('**Note**: Old fetch pattern detected. Will be migrated on next session start.')
else:
    print('**Status**: Remote sync not configured. Run in a git repo with origin remote.')
print('')
print('Run without --dry-run to apply changes.')
"
```

</step>

## When to Use Each Mode

| Mode | When to Use |
|------|-------------|
| `incremental` | After normal use, quick sync of new changes (default) |
| `full` | After major changes, index seems corrupted |
| `verify` | To check consistency without changes |
| `repair` | To fix detected inconsistencies |
| `--remote` | Sync with collaborators, pull remote memories, push local memories |

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

**User**: `/memory:sync --remote`
**Action**: Fetch, merge, and push notes with origin repository

**User**: `/memory:sync --remote --dry-run`
**Action**: Show what remote sync would do without making changes

## Memory Capture Reminder

After a sync operation, remind the user that new memories are immediately available:

```
**Ready to capture**: Your memory index is now synced. Use:
- `[remember] <learning>` - Quick inline capture
- `/memory:capture <namespace> <content>` - Explicit capture
```

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:status` | View index statistics and last sync time |
| `/memory:validate` | Full validation of hooks and pipeline |
| `/memory:recall` | Search memories after syncing |
| `/memory:capture` | Capture new memories |
| `/memory:search` | Advanced search with filters |
