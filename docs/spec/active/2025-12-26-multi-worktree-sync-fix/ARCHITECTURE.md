---
document_type: architecture
project_id: SPEC-2025-12-26-001
version: 1.0.0
last_updated: 2025-12-26T14:23:00Z
status: draft
---

# Multi-Worktree Sync Fix - Architecture Document

## Overview

This document describes the minimal architectural change needed to fix race conditions in multi-worktree environments. The fix replaces a direct push operation with an existing sync method that implements proper fetch→merge→push workflow.

## Current Architecture (Buggy)

### Stop Hook Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     SessionStop Hook                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Session analysis (extract memories)                      │
│  2. Index sync                                               │
│  3. IF config.stop_push_remote:                             │
│     └── git_ops.push_notes_to_remote()  ← PROBLEM           │
│         └── git push origin refs/notes/mem/*:refs/notes/mem/*│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Race Condition Scenario

```
Time    Worktree A              Worktree B              Remote
────────────────────────────────────────────────────────────────
t0      SessionStart            SessionStart
        fetch ─────────────────────────────────────────► (v1)
                                fetch ──────────────────► (v1)

t1      capture memory
        local notes = v2

t2                              capture memory
                                local notes = v2'

t3                              SessionStop
                                push v2' ──────────────► (v2')

t4      SessionStop
        push v2 ────────────────────────────────────────► REJECTED!
        (remote is v2', local is v2, conflict!)
────────────────────────────────────────────────────────────────
```

### Problem Analysis

| Component | Issue |
|-----------|-------|
| `push_notes_to_remote()` | Direct push without fetch |
| No merge step | Stale local refs cause rejection |
| No retry logic | Single push attempt fails |

## Target Architecture (Fixed)

### Stop Hook Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     SessionStop Hook                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Session analysis (extract memories)                      │
│  2. Index sync                                               │
│  3. IF config.stop_push_remote:                             │
│     └── git_ops.sync_notes_with_remote(push=True)  ← FIX   │
│         ├── 1. fetch origin refs/notes/mem/*                │
│         ├── 2. merge tracking refs (cat_sort_uniq)          │
│         └── 3. push merged notes to origin                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Fixed Race Condition Handling

```
Time    Worktree A              Worktree B              Remote
────────────────────────────────────────────────────────────────
t0      SessionStart            SessionStart
        fetch ─────────────────────────────────────────► (v1)
                                fetch ──────────────────► (v1)

t1      capture memory
        local notes = v2

t2                              capture memory
                                local notes = v2'

t3                              SessionStop
                                sync_notes_with_remote(push=True)
                                ├── fetch (v1, no change)
                                ├── merge (trivial)
                                └── push v2' ──────────► (v2')

t4      SessionStop
        sync_notes_with_remote(push=True)
        ├── fetch ◄──────────────────────────────────── (v2')
        ├── merge v2 + v2' = v3 (cat_sort_uniq)
        └── push v3 ───────────────────────────────────► (v3)
        ✓ SUCCESS - memories from both sessions preserved
────────────────────────────────────────────────────────────────
```

## Component Details

### `sync_notes_with_remote()` Method

Located in `src/git_notes_memory/git_ops.py:1238-1281`

```python
def sync_notes_with_remote(
    self,
    namespaces: list[str] | None = None,
    *,
    push: bool = True,
) -> dict[str, bool]:
    """Sync notes with remote using fetch → merge → push workflow.

    Args:
        namespaces: Specific namespaces to sync, or None for all
        push: Whether to push after merge (default True)

    Returns:
        Dict mapping namespace to sync success status
    """
```

Key features:
1. **Fetch**: Gets remote notes to tracking refs (`refs/notes/mem-tracking/*`)
2. **Merge**: Uses `cat_sort_uniq` strategy to combine local + remote
3. **Push**: Pushes merged result back to origin

### `cat_sort_uniq` Merge Strategy

The merge strategy (configured in Issue #18) handles conflicts by:
1. Concatenating both versions
2. Sorting lines
3. Removing duplicates

This ensures no memory is lost during concurrent sessions.

## Changes Required

### File: `src/git_notes_memory/hooks/stop_handler.py`

| Line | Current | Fixed |
|------|---------|-------|
| 482 | `git_ops.push_notes_to_remote()` | `git_ops.sync_notes_with_remote(push=True)` |

### Code Change

```python
# Before (line 482)
if git_ops.push_notes_to_remote():
    logger.debug("Pushed notes to remote on session stop")

# After
result = git_ops.sync_notes_with_remote(push=True)
if any(result.values()):
    logger.debug("Synced notes with remote on session stop: %s", result)
```

## Testing Strategy

### Unit Tests

| Test | Purpose |
|------|---------|
| `test_stop_handler_calls_sync_not_push` | Verify correct method called |
| `test_stop_handler_sync_failure_non_blocking` | Ensure failures don't block session end |
| `test_stop_handler_sync_logs_result` | Verify logging behavior |

### Integration Tests

| Test | Purpose |
|------|---------|
| `test_concurrent_sessions_no_conflict` | Two sessions pushing simultaneously |
| `test_stale_local_refs_merged` | Session with outdated refs syncs correctly |

### Manual Test Procedure

1. Start two Claude sessions in different worktrees
2. Capture memories in both
3. End both sessions within seconds of each other
4. Verify both memories appear in remote

## Security Considerations

No changes - `sync_notes_with_remote()` has the same security profile as `push_notes_to_remote()`:
- Uses same git remote authentication
- Operates on same refs namespace
- No new attack surface

## Performance Impact

| Aspect | Impact |
|--------|--------|
| Time | +100-500ms (fetch + merge overhead) |
| Network | +1 fetch operation |
| Blocking | None - happens at session end |

This is acceptable because:
1. Session end is non-interactive
2. User doesn't wait for completion
3. Reliability gain outweighs minor delay

## Rollback Plan

If issues arise, revert by changing line 482 back to:
```python
if git_ops.push_notes_to_remote():
```

No data migration needed - both methods operate on the same refs.
