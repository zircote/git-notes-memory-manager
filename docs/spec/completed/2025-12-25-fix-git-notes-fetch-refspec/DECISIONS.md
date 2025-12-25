---
document_type: decisions
project_id: SPEC-2025-12-25-001
---

# Fix Git Notes Fetch Refspec - Architecture Decision Records

## ADR-001: Use Remote Tracking Refs for Fetch

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude Code / Project Maintainers

### Context

The current fetch refspec `refs/notes/mem/*:refs/notes/mem/*` writes directly to local refs. When notes diverge between local and remote (common in multi-machine scenarios), Git cannot fast-forward the local ref and rejects the fetch with a "non-fast-forward" error.

Git's standard pattern for branches is to fetch to remote tracking refs first (`refs/remotes/origin/*`), then merge or rebase. Notes should follow this pattern.

### Decision

Change the fetch refspec from:
```
refs/notes/mem/*:refs/notes/mem/*
```
to:
```
+refs/notes/mem/*:refs/notes/origin/mem/*
```

This fetches notes to tracking refs under `refs/notes/origin/mem/`, mirroring Git's branch tracking pattern.

### Consequences

**Positive:**
- Fetch never fails due to divergence
- Enables proper merge workflow (fetch → merge → push)
- Follows Git's established patterns
- Compatible with existing `cat_sort_uniq` merge strategy

**Negative:**
- Additional disk space for tracking refs (negligible)
- Requires migration for existing installations
- More complex configuration to understand

**Neutral:**
- Push refspec remains unchanged (`refs/notes/mem/*:refs/notes/mem/*`)

### Alternatives Considered

1. **Force fetch directly to local refs (`+refs/notes/mem/*:refs/notes/mem/*`)**:
   - Why not chosen: Would overwrite local notes, causing data loss

2. **Fetch and auto-merge in one step**:
   - Why not chosen: Git doesn't support this; need two-step process

3. **Don't configure fetch at all, manual sync only**:
   - Why not chosen: Poor user experience; current behavior already configures fetch

---

## ADR-002: Use Force Prefix (+) in Fetch Refspec

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude Code / Project Maintainers

### Context

The `+` prefix in a Git refspec tells Git to update the reference even if it isn't a fast-forward. This is necessary for tracking refs because:
1. Remote notes may be rewritten (rebase, amend)
2. Tracking refs should always reflect remote state exactly

### Decision

Use the `+` prefix in the fetch refspec: `+refs/notes/mem/*:refs/notes/origin/mem/*`

### Consequences

**Positive:**
- Tracking refs always match remote state
- No fetch failures due to non-fast-forward
- Standard practice for tracking refs

**Negative:**
- History in tracking refs may be lost (expected for tracking refs)

**Neutral:**
- Local refs are not affected by force updates

### Alternatives Considered

1. **No force prefix**:
   - Why not chosen: Would still fail on non-fast-forward, defeating the purpose

---

## ADR-003: Naming Convention for Tracking Refs

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude Code / Project Maintainers

### Context

We need a namespace for remote tracking refs for notes. Options considered:
- `refs/notes/origin/mem/*` - mirrors "origin" remote naming
- `refs/notes/remotes/origin/mem/*` - mirrors branch remotes path
- `refs/notes/tracking/mem/*` - generic tracking namespace

### Decision

Use `refs/notes/origin/mem/*` as the tracking namespace.

### Consequences

**Positive:**
- Simple and intuitive (includes "origin" directly)
- Shorter paths
- Easy to understand relationship to remote

**Negative:**
- Hardcoded to "origin" remote (multi-remote would need extension)

**Neutral:**
- Other refs under `refs/notes/` are unaffected

### Alternatives Considered

1. **`refs/notes/remotes/origin/mem/*`**:
   - Why not chosen: Longer path, adds unnecessary nesting

2. **`refs/notes/tracking/mem/*`**:
   - Why not chosen: Doesn't indicate which remote, less intuitive

---

## ADR-004: Auto-Migration on Session Start

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude Code / Project Maintainers

### Context

Existing installations have the old fetch refspec configured. We need to migrate them to the new pattern without requiring manual intervention.

### Decision

Call `migrate_fetch_config()` from the SessionStart hook, immediately after `ensure_sync_configured()`.

### Consequences

**Positive:**
- Zero user intervention required
- Migration happens transparently
- First session after upgrade automatically fixes the issue

**Negative:**
- Adds slight overhead to session start (negligible)
- Users may not realize migration happened

**Neutral:**
- Migration is idempotent; safe to call repeatedly

### Alternatives Considered

1. **Manual migration only via `/memory:validate --fix`**:
   - Why not chosen: Users may not know to run this, continued failures

2. **Migration on first sync command**:
   - Why not chosen: User may not run sync; issue persists

3. **Breaking change in major version**:
   - Why not chosen: Unnecessary complexity; auto-migration is safe

---

## ADR-005: Merge Strategy for Notes

**Date**: 2025-12-25
**Status**: Accepted (Reaffirmed - existing decision)
**Deciders**: Original project architects

### Context

When merging diverged notes, we need a strategy that:
- Preserves all content from both sides
- Handles duplicate entries gracefully
- Doesn't require manual conflict resolution

### Decision

Continue using Git's built-in `cat_sort_uniq` merge strategy for notes.

This strategy:
1. Concatenates notes from both sides
2. Sorts lines
3. Removes duplicate lines

### Consequences

**Positive:**
- All notes are preserved (no data loss)
- Automatic conflict resolution
- Already configured in existing installations

**Negative:**
- Line order may change after merge
- Duplicate detection is line-based only

**Neutral:**
- YAML front matter is unaffected (parsed before line comparison)

### Alternatives Considered

1. **`theirs` or `ours` strategies**:
   - Why not chosen: Would lose notes from one side

2. **`union` strategy**:
   - Why not chosen: Similar to cat_sort_uniq but without sorting

3. **Custom merge driver**:
   - Why not chosen: Over-engineering; cat_sort_uniq works well

---

## ADR-007: Hook-Based Auto-Sync (Opt-In)

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: User / Claude Code

### Context

With remote sync capability available, users asked whether sync should happen automatically at session boundaries (start/stop) rather than requiring manual `/memory:sync --remote` invocation.

Automatic sync would:
- Fetch latest memories from other machines on session start
- Push local memories to remote on session stop

However, network operations add latency and may fail if offline.

### Decision

Implement hook-based auto-sync as **opt-in** via environment variables:
- `HOOK_SESSION_START_FETCH_REMOTE=true` - Fetch+merge on start
- `HOOK_STOP_PUSH_REMOTE=true` - Push on stop

Default: Both disabled (manual sync via `/memory:sync --remote`)

### Consequences

**Positive:**
- Seamless multi-machine sync for users who enable it
- No breaking changes (opt-in, defaults off)
- Memories automatically backed up on session end

**Negative:**
- Adds latency to session start/stop when enabled
- May fail silently if remote unavailable (by design)
- Users may not know to enable it

**Neutral:**
- Manual sync still available for one-off operations

### Alternatives Considered

1. **On by default**:
   - Why not chosen: Could surprise users with network activity; may cause issues if offline

2. **Only one direction (fetch-only or push-only)**:
   - Why not chosen: User expressed preference for both directions

3. **Sync on every capture**:
   - Why not chosen: Too much network overhead; batch at session boundaries is more efficient

---

## ADR-006: SyncService as Orchestration Layer

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Claude Code / Project Maintainers

### Context

Remote sync involves multiple operations: fetch, merge, push, reindex. We need to decide where this orchestration logic lives.

### Decision

Add `sync_with_remote()` to `SyncService` as the primary entry point for remote sync. It delegates git operations to `GitOps` and handles reindexing.

### Consequences

**Positive:**
- Consistent with existing `SyncService` pattern
- Separation of concerns (GitOps = git, SyncService = orchestration)
- Easy to test via dependency injection

**Negative:**
- Another layer of indirection

**Neutral:**
- Commands call SyncService, not GitOps directly

### Alternatives Considered

1. **All logic in GitOps**:
   - Why not chosen: GitOps is for git operations only; reindexing is not git

2. **Separate RemoteSyncService**:
   - Why not chosen: Over-engineering; SyncService already handles sync

3. **Logic in command handler**:
   - Why not chosen: Not reusable; harder to test
