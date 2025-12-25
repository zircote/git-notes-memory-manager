---
document_type: implementation_plan
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T21:35:00Z
status: draft
estimated_effort: 5-7 hours
---

# Fix Git Notes Fetch Refspec - Implementation Plan

## Overview

This implementation fixes the git notes fetch refspec issue (#18) by:
1. Changing the fetch pattern to use remote tracking refs
2. Adding migration for existing installations
3. Implementing a proper fetch→merge→push sync workflow
4. Updating commands to support remote sync

## Phase Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Phase 1: Core Fix | 1-2 hours | Fix refspec, add migration |
| Phase 2: Remote Sync | 1-2 hours | fetch→merge→push workflow |
| Phase 3: Commands | 1 hour | Update sync and validate commands |
| Phase 4: Hook Auto-Sync | 1 hour | Fetch on start, push on stop |
| Phase 5: Tests & Polish | 1 hour | Test coverage, edge cases |

---

## Phase 1: Core Fix

**Goal**: Fix the refspec configuration and add migration capability

**Prerequisites**: None - this is the first phase

### Tasks

#### Task 1.1: Update `configure_sync()` fetch refspec

- **Description**: Change the fetch refspec from direct-to-local to remote tracking refs pattern
- **File**: `src/git_notes_memory/git_ops.py`
- **Lines**: 731-742
- **Estimated Effort**: 15 minutes
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] Fetch refspec uses `+{base}/*:refs/notes/origin/mem/*` pattern
  - [ ] Force prefix (`+`) is included
  - [ ] Existing tests pass (may need updates)

**Code Change**:
```python
# Line 738 - change from:
f"{base}/*:{base}/*",
# to:
f"+{base}/*:refs/notes/origin/mem/*",
```

#### Task 1.2: Update `is_sync_configured()` to detect both patterns

- **Description**: Modify detection to recognize both old and new fetch patterns
- **File**: `src/git_notes_memory/git_ops.py`
- **Lines**: 675-681
- **Estimated Effort**: 20 minutes
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] Detects old pattern: `refs/notes/mem/*:refs/notes/mem/*`
  - [ ] Detects new pattern: `+refs/notes/mem/*:refs/notes/origin/mem/*`
  - [ ] Returns dict with `fetch_old` and `fetch_new` keys for migration detection

**Code Change**:
```python
# Add detection for both patterns:
# Old: {base}/*:{base}/*
# New: +{base}/*:refs/notes/origin/mem/*
```

#### Task 1.3: Add `migrate_fetch_config()` method

- **Description**: New method to migrate from old to new fetch refspec
- **File**: `src/git_notes_memory/git_ops.py`
- **Location**: After `configure_sync()` method (~line 765)
- **Estimated Effort**: 30 minutes
- **Dependencies**: Task 1.2
- **Acceptance Criteria**:
  - [ ] Detects old pattern and removes it
  - [ ] Adds new pattern if not present
  - [ ] Returns bool indicating if migration occurred
  - [ ] Idempotent - safe to call multiple times

**New Method**:
```python
def migrate_fetch_config(self) -> bool:
    """Migrate from direct fetch to tracking refs pattern.

    Returns:
        True if migration occurred, False if already migrated or no config.
    """
    base = get_git_namespace()
    old_pattern = f"{base}/*:{base}/*"
    new_pattern = f"+{base}/*:refs/notes/origin/mem/*"

    # Check current fetch configs
    result = self._run_git(
        ["config", "--get-all", "remote.origin.fetch"],
        check=False,
    )

    if result.returncode != 0:
        # No fetch config at all
        return False

    configs = result.stdout.strip().split("\n")

    # Check if old pattern exists
    has_old = any(old_pattern in c for c in configs)
    has_new = any(new_pattern in c for c in configs)

    if not has_old:
        # Already migrated or never had old config
        return False

    if has_new:
        # New config already exists, just remove old
        self._run_git(
            ["config", "--unset", "remote.origin.fetch", old_pattern],
            check=False,
        )
        return True

    # Remove old, add new
    self._run_git(
        ["config", "--unset", "remote.origin.fetch", old_pattern],
        check=False,
    )
    self._run_git(
        ["config", "--add", "remote.origin.fetch", new_pattern],
        check=False,
    )
    return True
```

#### Task 1.4: Call migration from SessionStart handler

- **Description**: Auto-migrate existing installations on session start
- **File**: `src/git_notes_memory/hooks/session_start_handler.py`
- **Location**: After `ensure_sync_configured()` call (~line 175)
- **Estimated Effort**: 15 minutes
- **Dependencies**: Task 1.3
- **Acceptance Criteria**:
  - [ ] Migration called after sync configuration
  - [ ] Logs migration status at debug level
  - [ ] Does not block session start on failure

**Code Change**:
```python
# After ensure_sync_configured():
try:
    if git_ops.migrate_fetch_config():
        logger.debug("Migrated git notes fetch refspec to tracking refs pattern")
except Exception as e:
    logger.debug("Fetch refspec migration skipped: %s", e)
```

### Phase 1 Deliverables

- [ ] Updated `configure_sync()` with new refspec
- [ ] Updated `is_sync_configured()` with pattern detection
- [ ] New `migrate_fetch_config()` method
- [ ] SessionStart auto-migration

### Phase 1 Exit Criteria

- [ ] `git fetch origin` succeeds with diverged notes (manual test)
- [ ] Existing tests pass or are updated
- [ ] Migration runs without errors

---

## Phase 2: Remote Sync Workflow

**Goal**: Implement full fetch → merge → push workflow

**Prerequisites**: Phase 1 complete

### Tasks

#### Task 2.1: Add `fetch_notes_from_remote()` method

- **Description**: Fetch notes from origin to tracking refs
- **File**: `src/git_notes_memory/git_ops.py`
- **Location**: New method after sync configuration methods
- **Estimated Effort**: 20 minutes
- **Dependencies**: Phase 1
- **Acceptance Criteria**:
  - [ ] Fetches notes to `refs/notes/origin/mem/*`
  - [ ] Returns success status
  - [ ] Handles remote unavailable gracefully

**New Method**:
```python
def fetch_notes_from_remote(
    self,
    namespaces: list[str] | None = None,
) -> dict[str, bool]:
    """Fetch notes from origin to tracking refs.

    Args:
        namespaces: Specific namespaces to fetch, or None for all.

    Returns:
        Dict mapping namespace to fetch success.
    """
    base = get_git_namespace()
    namespaces = namespaces or list(NAMESPACES)
    results: dict[str, bool] = {}

    for ns in namespaces:
        try:
            local_ref = f"{base}/{ns}"
            tracking_ref = f"refs/notes/origin/mem/{ns}"
            result = self._run_git(
                ["fetch", "origin", f"+{local_ref}:{tracking_ref}"],
                check=False,
            )
            results[ns] = result.returncode == 0
        except Exception:
            results[ns] = False

    return results
```

#### Task 2.2: Add `merge_notes_from_tracking()` method

- **Description**: Merge tracking refs into local refs using cat_sort_uniq
- **File**: `src/git_notes_memory/git_ops.py`
- **Estimated Effort**: 25 minutes
- **Dependencies**: Task 2.1
- **Acceptance Criteria**:
  - [ ] Merges using `git notes merge -s cat_sort_uniq`
  - [ ] Handles empty tracking refs gracefully
  - [ ] Returns merge success status

**New Method**:
```python
def merge_notes_from_tracking(
    self,
    namespace: str,
) -> bool:
    """Merge tracking refs into local notes.

    Args:
        namespace: Namespace to merge.

    Returns:
        True if merge succeeded, False otherwise.
    """
    self._validate_namespace(namespace)
    tracking_ref = f"refs/notes/origin/mem/{namespace}"

    # Check if tracking ref exists
    result = self._run_git(
        ["rev-parse", tracking_ref],
        check=False,
    )
    if result.returncode != 0:
        # No tracking ref to merge
        return True  # Not an error

    # Merge using configured strategy
    result = self._run_git(
        ["notes", f"--ref=mem/{namespace}", "merge", "-s", "cat_sort_uniq", tracking_ref],
        check=False,
    )
    return result.returncode == 0
```

#### Task 2.3: Add `push_notes_to_remote()` method

- **Description**: Push local notes to origin
- **File**: `src/git_notes_memory/git_ops.py`
- **Estimated Effort**: 15 minutes
- **Dependencies**: Task 2.2
- **Acceptance Criteria**:
  - [ ] Pushes all namespaces in single push
  - [ ] Handles push rejection gracefully
  - [ ] Returns push success status

**New Method**:
```python
def push_notes_to_remote(self) -> bool:
    """Push all notes to origin.

    Returns:
        True if push succeeded, False otherwise.
    """
    base = get_git_namespace()
    result = self._run_git(
        ["push", "origin", f"{base}/*:{base}/*"],
        check=False,
    )
    return result.returncode == 0
```

#### Task 2.4: Add `sync_notes_with_remote()` method

- **Description**: Orchestrate full fetch → merge → push workflow
- **File**: `src/git_notes_memory/git_ops.py`
- **Estimated Effort**: 25 minutes
- **Dependencies**: Tasks 2.1, 2.2, 2.3
- **Acceptance Criteria**:
  - [ ] Calls fetch, merge, push in sequence
  - [ ] Returns structured result
  - [ ] Supports optional push skip

**New Method**:
```python
def sync_notes_with_remote(
    self,
    namespaces: list[str] | None = None,
    *,
    push: bool = True,
) -> dict[str, bool]:
    """Sync notes with remote using fetch → merge → push workflow.

    Args:
        namespaces: Specific namespaces to sync, or None for all.
        push: Whether to push after merging.

    Returns:
        Dict mapping namespace to sync success.
    """
    namespaces = namespaces or list(NAMESPACES)
    results: dict[str, bool] = {}

    # Step 1: Fetch
    fetch_results = self.fetch_notes_from_remote(namespaces)

    # Step 2: Merge each namespace
    for ns in namespaces:
        if fetch_results.get(ns, False):
            results[ns] = self.merge_notes_from_tracking(ns)
        else:
            # Fetch failed, but might still have local notes to push
            results[ns] = False

    # Step 3: Push (if requested)
    if push:
        push_success = self.push_notes_to_remote()
        if not push_success:
            # Mark all as partial failure
            for ns in results:
                if results[ns]:
                    results[ns] = True  # Merge worked, push didn't

    return results
```

#### Task 2.5: Add `sync_with_remote()` to SyncService

- **Description**: Expose remote sync via SyncService with reindexing
- **File**: `src/git_notes_memory/sync.py`
- **Location**: New method after `repair()` method
- **Estimated Effort**: 20 minutes
- **Dependencies**: Task 2.4
- **Acceptance Criteria**:
  - [ ] Orchestrates GitOps.sync_notes_with_remote()
  - [ ] Reindexes SQLite after successful merge
  - [ ] Returns structured result

**New Method**:
```python
def sync_with_remote(
    self,
    *,
    namespaces: list[str] | None = None,
    push: bool = True,
) -> dict[str, bool]:
    """Synchronize notes with remote and reindex.

    Args:
        namespaces: Specific namespaces to sync, or None for all.
        push: Whether to push changes to remote.

    Returns:
        Dict mapping namespace to sync success.
    """
    git_ops = self._get_git_ops()

    # Perform remote sync
    results = git_ops.sync_notes_with_remote(namespaces, push=push)

    # Reindex after successful sync
    if any(results.values()):
        self.reindex()

    return results
```

### Phase 2 Deliverables

- [ ] `fetch_notes_from_remote()` method
- [ ] `merge_notes_from_tracking()` method
- [ ] `push_notes_to_remote()` method
- [ ] `sync_notes_with_remote()` orchestration method
- [ ] `SyncService.sync_with_remote()` wrapper

### Phase 2 Exit Criteria

- [ ] Full sync workflow works end-to-end
- [ ] Notes merge correctly with cat_sort_uniq
- [ ] No note loss during sync

---

## Phase 3: Command Updates

**Goal**: Update CLI commands to support remote sync

**Prerequisites**: Phase 2 complete

### Tasks

#### Task 3.1: Update `/memory:sync` command for remote mode

- **Description**: Add `--remote` flag to sync command
- **File**: `commands/sync.md`
- **Estimated Effort**: 25 minutes
- **Dependencies**: Task 2.5
- **Acceptance Criteria**:
  - [ ] `--remote` flag triggers `sync_with_remote()`
  - [ ] Clear output showing sync status per namespace
  - [ ] `--remote --dry-run` supported (report only)

#### Task 3.2: Add refspec validation to `/memory:validate`

- **Description**: Check for correct fetch refspec configuration
- **File**: `commands/validate.md`
- **Estimated Effort**: 20 minutes
- **Dependencies**: Task 1.2
- **Acceptance Criteria**:
  - [ ] Reports "incorrect fetch refspec" if old pattern found
  - [ ] `--fix` triggers `migrate_fetch_config()`
  - [ ] Shows current refspec configuration

### Phase 3 Deliverables

- [ ] Updated `/memory:sync` with remote mode
- [ ] Updated `/memory:validate` with refspec check

### Phase 3 Exit Criteria

- [ ] `/memory:sync --remote` works correctly
- [ ] `/memory:validate` detects old refspec
- [ ] `/memory:validate --fix` migrates correctly

---

## Phase 4: Hook Auto-Sync

**Goal**: Implement automatic fetch on session start and push on session stop

**Prerequisites**: Phase 2 complete (remote sync methods available)

### Tasks

#### Task 4.1: Add config options for auto-sync

- **Description**: Add environment variables for hook-based auto-sync
- **File**: `src/git_notes_memory/hooks/config_loader.py`
- **Estimated Effort**: 15 minutes
- **Dependencies**: None
- **Acceptance Criteria**:
  - [ ] `HOOK_SESSION_START_FETCH_REMOTE` config option (default: false)
  - [ ] `HOOK_STOP_PUSH_REMOTE` config option (default: false)
  - [ ] Documented in CLAUDE.md

**Code Change**:
```python
# Add to HookConfig dataclass:
session_start_fetch_remote: bool = False
stop_push_remote: bool = False

# Add to load_config():
session_start_fetch_remote=os.getenv("HOOK_SESSION_START_FETCH_REMOTE", "false").lower() == "true",
stop_push_remote=os.getenv("HOOK_STOP_PUSH_REMOTE", "false").lower() == "true",
```

#### Task 4.2: Add fetch+merge to SessionStart hook

- **Description**: Fetch and merge notes from remote when session starts (opt-in)
- **File**: `src/git_notes_memory/hooks/session_start_handler.py`
- **Location**: After `migrate_fetch_config()` call
- **Estimated Effort**: 25 minutes
- **Dependencies**: Task 4.1, Phase 2 (fetch/merge methods)
- **Acceptance Criteria**:
  - [ ] Fetches notes when `HOOK_SESSION_START_FETCH_REMOTE=true`
  - [ ] Merges each namespace using `cat_sort_uniq`
  - [ ] Reindexes SQLite after merge
  - [ ] Graceful degradation if remote unavailable
  - [ ] Non-blocking (errors logged, session continues)

**Code Change**:
```python
# After migrate_fetch_config():
if config.session_start_fetch_remote:
    try:
        fetch_results = git_ops.fetch_notes_from_remote()
        for ns, success in fetch_results.items():
            if success:
                git_ops.merge_notes_from_tracking(ns)
        # Reindex to include fetched memories
        from git_notes_memory import get_sync_service
        sync_service = get_sync_service(repo_path=cwd)
        sync_service.reindex()
        logger.debug("Fetched and merged remote notes on session start")
    except Exception as e:
        logger.debug("Remote fetch on start skipped: %s", e)
```

#### Task 4.3: Add push to Stop hook

- **Description**: Push notes to remote when session ends (opt-in)
- **File**: `src/git_notes_memory/hooks/stop_handler.py`
- **Location**: At end of handler, after session analysis
- **Estimated Effort**: 20 minutes
- **Dependencies**: Task 4.1, Phase 2 (push method)
- **Acceptance Criteria**:
  - [ ] Pushes notes when `HOOK_STOP_PUSH_REMOTE=true`
  - [ ] Graceful degradation if remote unavailable
  - [ ] Non-blocking (errors logged, session ends normally)

**Code Change**:
```python
# At end of main():
if config.stop_push_remote:
    try:
        git_ops = GitOps(repo_path=cwd)
        if git_ops.push_notes_to_remote():
            logger.debug("Pushed notes to remote on session stop")
        else:
            logger.debug("Push to remote failed (will retry next session)")
    except Exception as e:
        logger.debug("Remote push on stop skipped: %s", e)
```

#### Task 4.4: Update CLAUDE.md with new config options

- **Description**: Document the new environment variables
- **File**: `CLAUDE.md`
- **Location**: Environment Variables section
- **Estimated Effort**: 10 minutes
- **Dependencies**: Task 4.1
- **Acceptance Criteria**:
  - [ ] Both new env vars documented with descriptions
  - [ ] Default values noted (false)
  - [ ] Use case explained

### Phase 4 Deliverables

- [ ] Config options for auto-sync
- [ ] Fetch+merge on SessionStart hook
- [ ] Push on Stop hook
- [ ] Documentation updated

### Phase 4 Exit Criteria

- [ ] `HOOK_SESSION_START_FETCH_REMOTE=true` fetches notes on start
- [ ] `HOOK_STOP_PUSH_REMOTE=true` pushes notes on stop
- [ ] Both work correctly when remote is unavailable
- [ ] Session start/stop not blocked by failures

---

## Phase 5: Tests & Polish

**Goal**: Ensure comprehensive test coverage and polish

**Prerequisites**: Phases 1-4 complete

### Tasks

#### Task 5.1: Add unit tests for migration

- **Description**: Test migrate_fetch_config() with various states
- **File**: `tests/test_git_ops.py`
- **Estimated Effort**: 20 minutes
- **Dependencies**: Phase 1
- **Acceptance Criteria**:
  - [ ] Test: no config → returns False
  - [ ] Test: old config → migrates to new
  - [ ] Test: new config → returns False (no-op)
  - [ ] Test: both configs → removes old

#### Task 5.2: Add unit tests for remote sync

- **Description**: Test sync_notes_with_remote() workflow
- **File**: `tests/test_git_ops.py`
- **Estimated Effort**: 25 minutes
- **Dependencies**: Phase 2
- **Acceptance Criteria**:
  - [ ] Test: successful fetch → merge → push
  - [ ] Test: fetch fails gracefully
  - [ ] Test: push=False skips push

#### Task 5.3: Add integration tests for diverged notes

- **Description**: Test end-to-end with actual diverged repos
- **File**: `tests/test_sync_integration.py` (new file)
- **Estimated Effort**: 30 minutes
- **Dependencies**: Phases 1-2
- **Acceptance Criteria**:
  - [ ] Test: local-only notes push correctly
  - [ ] Test: remote-only notes fetch correctly
  - [ ] Test: diverged notes merge correctly

#### Task 5.4: Add tests for hook auto-sync

- **Description**: Test SessionStart fetch and Stop push
- **File**: `tests/test_hooks.py`
- **Estimated Effort**: 25 minutes
- **Dependencies**: Phase 4
- **Acceptance Criteria**:
  - [ ] Test: SessionStart fetches when config enabled
  - [ ] Test: Stop pushes when config enabled
  - [ ] Test: graceful degradation when remote unavailable

#### Task 5.5: Update existing tests for new patterns

- **Description**: Fix any tests broken by refspec changes
- **File**: `tests/test_git_ops.py`
- **Estimated Effort**: 15 minutes
- **Dependencies**: Phase 1
- **Acceptance Criteria**:
  - [ ] All existing sync tests pass
  - [ ] Mocks updated for new refspec pattern

### Phase 5 Deliverables

- [ ] Migration unit tests
- [ ] Remote sync unit tests
- [ ] Integration tests for diverged notes
- [ ] Hook auto-sync tests
- [ ] Updated existing tests

### Phase 5 Exit Criteria

- [ ] All tests pass
- [ ] Coverage maintained at 80%+
- [ ] `make quality` passes

---

## Dependency Graph

```
Phase 1:
  Task 1.1 ──────────────────┐
           (configure_sync)  │
                             │
  Task 1.2 ──────┐           │
    (is_sync)    │           │
                 ▼           ▼
  Task 1.3 ◀────────── Patterns Ready
    (migrate)
         │
         ▼
  Task 1.4
    (SessionStart)


Phase 2 (requires Phase 1):

  Task 2.1 ─────────▶ Task 2.4 ─────────▶ Task 2.5
    (fetch)              │                  (SyncService)
                         │
  Task 2.2 ─────────────┘
    (merge)              │
                         │
  Task 2.3 ─────────────┘
    (push)


Phase 3 (requires Phase 2):

  Task 3.1                Task 3.2
    (sync cmd)              (validate cmd)


Phase 4 (requires Phase 2):

  Task 4.1 ──────────▶ Task 4.2
    (config)              (SessionStart fetch)
         │
         └───────────▶ Task 4.3
                          (Stop push)
         │
         └───────────▶ Task 4.4
                          (docs)


Phase 5 (requires Phases 1-4):

  Task 5.1    Task 5.2    Task 5.3    Task 5.4    Task 5.5
    (tests)     (tests)     (tests)     (tests)     (tests)
```

## Testing Checklist

- [ ] Unit tests for `migrate_fetch_config()`
- [ ] Unit tests for `fetch_notes_from_remote()`
- [ ] Unit tests for `merge_notes_from_tracking()`
- [ ] Unit tests for `push_notes_to_remote()`
- [ ] Unit tests for `sync_notes_with_remote()`
- [ ] Integration test: local-only notes
- [ ] Integration test: remote-only notes
- [ ] Integration test: diverged notes
- [ ] Integration test: migration from old config
- [ ] Manual test: multi-machine sync

## Documentation Tasks

- [ ] Update README.md with remote sync info (if applicable)
- [ ] Update command help text in sync.md
- [ ] Update command help text in validate.md
- [ ] Add migration notes to CHANGELOG

## Launch Checklist

- [ ] All tests passing (`make test`)
- [ ] Quality checks passing (`make quality`)
- [ ] Type checks passing (`make typecheck`)
- [ ] Manual verification with diverged repos
- [ ] Documentation updated
- [ ] CHANGELOG updated
- [ ] PR created with issue #18 reference

## Post-Launch

- [ ] Monitor for issues after release
- [ ] Gather feedback on migration experience
- [ ] Consider background sync for future enhancement
