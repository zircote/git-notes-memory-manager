---
document_type: architecture
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T21:35:00Z
status: draft
---

# Fix Git Notes Fetch Refspec - Technical Architecture

## System Overview

This fix addresses the git notes synchronization architecture by changing from a direct-fetch pattern to a remote-tracking-refs pattern. The change affects how notes are fetched from remotes and subsequently merged with local notes.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CURRENT ARCHITECTURE (BROKEN)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Remote (origin)                    Local                                  │
│   ┌─────────────────┐                ┌─────────────────┐                    │
│   │refs/notes/mem/* │ ──── fetch ───▶│refs/notes/mem/* │                    │
│   └─────────────────┘   (FAILS if    └─────────────────┘                    │
│                          diverged)                                          │
│                                                                             │
│   Problem: Direct write to local refs fails on non-fast-forward             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          NEW ARCHITECTURE (FIXED)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Remote (origin)                 Tracking Refs              Local          │
│   ┌─────────────────┐           ┌─────────────────┐       ┌─────────────┐   │
│   │refs/notes/mem/* │ ─ fetch ─▶│refs/notes/      │─merge▶│refs/notes/  │   │
│   └─────────────────┘   (+force)│origin/mem/*     │       │mem/*        │   │
│                                 └─────────────────┘       └─────────────┘   │
│                                                                             │
│   Solution: Fetch to tracking refs, then merge using cat_sort_uniq          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision       | Choice                     | Rationale                                              |
| -------------- | -------------------------- | ------------------------------------------------------ |
| Fetch target   | `refs/notes/origin/mem/*`  | Mirrors `refs/remotes/origin/*` pattern for branches   |
| Force prefix   | `+` in refspec             | Required for non-fast-forward updates to tracking refs |
| Merge strategy | `cat_sort_uniq` (existing) | Already configured, handles note merging correctly     |
| Sync workflow  | fetch → merge → push       | Standard Git workflow; atomic namespace-by-namespace   |

## Component Design

### Component 1: GitOps Sync Configuration

**Purpose**: Configure git for proper notes sync with remote tracking refs

**Current Code** (`git_ops.py:731-742`):

```python
# CURRENT (PROBLEMATIC)
result = self._run_git(
    [
        "config",
        "--add",
        "remote.origin.fetch",
        f"{base}/*:{base}/*",  # Direct to local refs
    ],
    check=False,
)
```

**New Code**:

```python
# NEW (FIXED)
result = self._run_git(
    [
        "config",
        "--add",
        "remote.origin.fetch",
        f"+{base}/*:refs/notes/origin/mem/*",  # To tracking refs with force
    ],
    check=False,
)
```

**Responsibilities**:

- Configure fetch refspec for remote tracking refs
- Detect and migrate old configuration pattern
- Validate refspec configuration

**Interfaces**:

- `configure_sync(force: bool)` - Set up all sync configuration
- `is_sync_configured()` - Check current configuration status
- `migrate_fetch_config()` - Migrate from old to new pattern

**Dependencies**: None (standalone git operations)

### Component 2: Remote Sync Workflow

**Purpose**: Implement fetch → merge → push workflow for notes

**New Methods in `GitOps`**:

```python
def sync_notes_with_remote(
    self,
    namespaces: list[str] | None = None,
    *,
    push: bool = True,
) -> dict[str, bool]:
    """Sync notes with remote using fetch → merge → push workflow.

    1. Fetch remote notes to tracking refs
    2. Merge each namespace using cat_sort_uniq strategy
    3. Push merged notes back to remote (if push=True)

    Args:
        namespaces: List of namespaces to sync, or None for all.
        push: Whether to push after merging.

    Returns:
        Dict mapping namespace to success status.
    """
```

**Responsibilities**:

- Fetch notes from origin to tracking refs
- Merge tracking refs into local refs using `cat_sort_uniq`
- Push merged notes back to origin

**Interfaces**:

- `sync_notes_with_remote(namespaces, push)` - Full sync workflow
- `fetch_notes_from_remote(namespaces)` - Fetch-only operation
- `merge_notes_from_tracking(namespace)` - Merge single namespace

**Dependencies**:

- Existing `_run_git()` method for git commands
- Existing `NAMESPACES` constant for namespace list

### Component 3: Migration Handler

**Purpose**: Migrate existing installations from old to new refspec pattern

**Location**: New method in `GitOps` class

```python
def migrate_fetch_config(self) -> bool:
    """Migrate from direct fetch to tracking refs pattern.

    Detects old-style refspec and replaces with new pattern.
    Safe to call multiple times (idempotent).

    Returns:
        True if migration occurred, False if already migrated or no config.
    """
```

**Migration Logic**:

1. Read current `remote.origin.fetch` values
2. Check for old pattern: `refs/notes/mem/*:refs/notes/mem/*`
3. If found, remove old pattern
4. Add new pattern: `+refs/notes/mem/*:refs/notes/origin/mem/*`
5. Return migration status

**Responsibilities**:

- Detect old configuration pattern
- Remove old pattern safely
- Add new pattern
- Handle edge cases (missing config, partial config)

**Dependencies**: None (standalone git operations)

### Component 4: SyncService Extension

**Purpose**: Expose remote sync functionality to commands

**New Methods in `SyncService`**:

```python
def sync_with_remote(
    self,
    *,
    namespaces: list[str] | None = None,
    push: bool = True,
    dry_run: bool = False,
) -> RemoteSyncResult:
    """Synchronize with remote repository.

    Performs fetch → merge → push for git notes, then reindexes
    the local SQLite index.

    Args:
        namespaces: Specific namespaces to sync, or None for all.
        push: Whether to push changes to remote.
        dry_run: If True, report what would happen without changes.

    Returns:
        RemoteSyncResult with sync status per namespace.
    """
```

**Responsibilities**:

- Orchestrate remote sync via GitOps
- Reindex local SQLite after merge
- Provide dry-run capability
- Return structured sync results

**Dependencies**:

- `GitOps.sync_notes_with_remote()`
- Existing `reindex()` method

### Component 5: Command Updates

**Purpose**: Expose remote sync via CLI commands

**Files to Modify**:

- `commands/sync.md` - Add `--remote` flag support
- `commands/validate.md` - Add refspec validation check

**Responsibilities**:

- Parse `--remote` flag in sync command
- Display remote sync status
- Report refspec issues in validate command

### Component 6: Hook-Based Auto-Sync

**Purpose**: Automatic remote sync on session boundaries (opt-in)

**Files to Modify**:

- `src/git_notes_memory/hooks/session_start_handler.py` - Add fetch on start
- `src/git_notes_memory/hooks/stop_handler.py` - Add push on stop
- `src/git_notes_memory/hooks/config_loader.py` - Add new config options

**Environment Variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOOK_SESSION_START_FETCH_REMOTE` | `false` | Fetch+merge from remote on session start |
| `HOOK_STOP_PUSH_REMOTE` | `false` | Push to remote on session stop |

**SessionStart Hook Integration**:

```python
# After ensure_sync_configured() and migrate_fetch_config():
if config.session_start_fetch_remote:
    try:
        git_ops = self._get_git_ops()
        fetch_results = git_ops.fetch_notes_from_remote()
        for ns, success in fetch_results.items():
            if success:
                git_ops.merge_notes_from_tracking(ns)
        # Reindex to include fetched memories
        sync_service = get_sync_service()
        sync_service.reindex()
        logger.debug("Fetched and merged remote notes on session start")
    except Exception as e:
        logger.debug("Remote fetch on start skipped: %s", e)
```

**Stop Hook Integration**:

```python
# At end of stop handler:
if config.stop_push_remote:
    try:
        git_ops = GitOps()
        if git_ops.push_notes_to_remote():
            logger.debug("Pushed notes to remote on session stop")
        else:
            logger.debug("Push to remote failed (will retry next session)")
    except Exception as e:
        logger.debug("Remote push on stop skipped: %s", e)
```

**Responsibilities**:

- Fetch and merge notes at session start (opt-in)
- Push notes at session stop (opt-in)
- Graceful degradation if remote unavailable
- Non-blocking (failures don't break session)

**Dependencies**:

- `GitOps.fetch_notes_from_remote()`
- `GitOps.merge_notes_from_tracking()`
- `GitOps.push_notes_to_remote()`
- `SyncService.reindex()`

## Data Design

### New Data Model: RemoteSyncResult

```python
@dataclass(frozen=True)
class RemoteSyncResult:
    """Result of a remote sync operation."""

    success: bool
    namespaces_synced: tuple[str, ...]
    namespaces_failed: tuple[str, ...]
    notes_fetched: int
    notes_merged: int
    notes_pushed: int
    errors: tuple[str, ...]
```

### Data Flow

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                           REMOTE SYNC DATA FLOW                               │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  /memory:sync --remote                                                        │
│         │                                                                     │
│         ▼                                                                     │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌────────────┐   │
│  │ SyncService │ ──▶ │   GitOps    │ ──▶ │  git fetch  │ ──▶ │ Tracking   │   │
│  │ .sync_with_ │     │ .sync_notes │     │   origin    │     │   Refs     │   │
│  │  remote()   │     │ _with_      │     │             │     │            │   │
│  └─────────────┘     │ remote()    │     └─────────────┘     └────────────┘   │
│         │            └─────────────┘            │                    │        │
│         │                   │                   │                    │        │
│         │                   ▼                   ▼                    ▼        │
│         │            ┌─────────────┐     ┌─────────────┐     ┌────────────┐   │
│         │            │  git notes  │ ◀── │   Merge     │ ◀── │ Local Refs │   │
│         │            │   merge     │     │  Decision   │     │            │   │
│         │            └─────────────┘     └─────────────┘     └────────────┘   │
│         │                   │                                                 │
│         │                   ▼                                                 │
│         │            ┌─────────────┐                                          │
│         │            │  git push   │                                          │
│         │            │   origin    │                                          │
│         │            └─────────────┘                                          │
│         │                   │                                                 │
│         ▼                   ▼                                                 │
│  ┌─────────────┐     ┌─────────────┐                                          │
│  │  Reindex    │ ◀── │   Return    │                                          │
│  │  SQLite     │     │   Result    │                                          │
│  └─────────────┘     └─────────────┘                                          │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

## API Design

### GitOps Methods (New/Modified)

| Method                        | Type     | Purpose                          |
| ----------------------------- | -------- | -------------------------------- |
| `configure_sync()`            | Modified | Add new fetch refspec pattern    |
| `is_sync_configured()`        | Modified | Detect both old and new patterns |
| `migrate_fetch_config()`      | New      | Migrate old pattern to new       |
| `sync_notes_with_remote()`    | New      | Full fetch→merge→push workflow   |
| `fetch_notes_from_remote()`   | New      | Fetch to tracking refs only      |
| `merge_notes_from_tracking()` | New      | Merge tracking refs to local     |

### SyncService Methods (New)

| Method               | Type | Purpose                           |
| -------------------- | ---- | --------------------------------- |
| `sync_with_remote()` | New  | Orchestrate remote sync + reindex |

### Command Flags (New)

| Command            | Flag                 | Purpose                      |
| ------------------ | -------------------- | ---------------------------- |
| `/memory:sync`     | `--remote`           | Trigger remote sync workflow |
| `/memory:sync`     | `--remote --dry-run` | Preview remote sync          |
| `/memory:validate` | (no flag)            | Check refspec configuration  |
| `/memory:validate` | `--fix`              | Auto-migrate old refspec     |

## Integration Points

### Internal Integrations

| System                     | Integration Type | Purpose                       |
| -------------------------- | ---------------- | ----------------------------- |
| `session_start_handler.py` | Function call    | Auto-migrate on session start |
| `sync.py` (SyncService)    | Method call      | Orchestrate remote sync       |
| `git_ops.py` (GitOps)      | Method call      | Execute git commands          |

### External Integrations

| Service         | Integration Type | Purpose            |
| --------------- | ---------------- | ------------------ |
| Git CLI         | Subprocess       | All git operations |
| Remote (origin) | Git protocol     | Fetch/push notes   |

## Security Design

### No New Security Concerns

This change does not introduce new security considerations:

- All git operations continue to use subprocess (no shell=True)
- Ref validation via existing `_validate_git_ref()` is maintained
- No new external dependencies or network protocols

### Existing Security Controls

- **SEC-001**: Ref validation prevents injection
- **SEC-002**: Path sanitization in error messages
- Git's own authentication handles remote access

## Performance Considerations

### Expected Load

- Typical: 10-100 notes per namespace
- Maximum tested: 1000 notes per namespace
- Sync operations: Occasional (on-demand or session-based)

### Performance Targets

| Metric        | Target                | Rationale             |
| ------------- | --------------------- | --------------------- |
| Fetch latency | < 2s for 100 notes    | Network-bound         |
| Merge latency | < 100ms per namespace | Local operation       |
| Push latency  | < 2s for 100 notes    | Network-bound         |
| Total sync    | < 5s typical          | User-facing operation |

### Optimization Strategies

- **PERF-001**: Already uses batch git operations
- Merge all namespaces before single push
- Reindex only after successful merge

## Reliability & Operations

### Failure Modes

| Failure            | Impact                           | Recovery                               |
| ------------------ | -------------------------------- | -------------------------------------- |
| Remote unavailable | Fetch fails                      | Graceful error; local notes unaffected |
| Merge conflict     | Should not occur (cat_sort_uniq) | Fall back to full reindex              |
| Push rejected      | Notes not synced to remote       | Retry or manual push                   |
| Index corruption   | SQLite index out of sync         | `/memory:sync repair`                  |

### Idempotency

All operations are designed to be idempotent:

- `configure_sync()` - Safe to call multiple times
- `migrate_fetch_config()` - Detects already-migrated state
- `sync_notes_with_remote()` - Can be interrupted and resumed

## Testing Strategy

### Unit Testing

- Mock git operations for GitOps method tests
- Test configuration detection (old pattern, new pattern, none)
- Test migration logic with various starting states

### Integration Testing

- Create actual git repos with diverged notes
- Test fetch→merge→push workflow end-to-end
- Verify notes are preserved after merge

### Edge Cases to Test

1. Empty local notes, populated remote
2. Populated local notes, empty remote
3. Both have same notes (no-op expected)
4. Both have different notes (merge expected)
5. One namespace diverged, others in sync
6. Remote unreachable during sync

## Deployment Considerations

### Migration Path

1. Update `configure_sync()` in release
2. `session_start_handler.py` calls `migrate_fetch_config()` on start
3. Existing users auto-migrate on next session
4. `/memory:validate --fix` available for manual migration

### Rollback Plan

If issues arise:

1. Revert the code change
2. Users can manually reset fetch refspec:
   ```bash
   git config --unset-all remote.origin.fetch "refs/notes"
   git config --add remote.origin.fetch "refs/notes/mem/*:refs/notes/mem/*"
   ```

## Future Considerations

- **Multi-remote support**: Currently only `origin` is supported
- **Selective namespace sync**: Could allow syncing specific namespaces only
- **Conflict notification**: Could surface merge details to user (informational)
- **Background sync**: Could implement periodic background sync
