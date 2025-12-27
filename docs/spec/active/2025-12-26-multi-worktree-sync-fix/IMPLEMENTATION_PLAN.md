---
document_type: implementation_plan
project_id: SPEC-2025-12-26-001
version: 1.0.0
last_updated: 2025-12-26T14:23:00Z
status: draft
---

# Multi-Worktree Sync Fix - Implementation Plan

## Overview

This is a minimal bug fix with a single code change. The implementation is straightforward since we're replacing one method call with another that already exists and is proven to work.

## Phase 1: Implementation (Single Task)

### Task 1.1: Replace push with sync in Stop handler

**File**: `src/git_notes_memory/hooks/stop_handler.py`
**Lines**: 480-487

**Current Code**:
```python
if config.stop_push_remote:
    cwd = input_data.get("cwd")
    if cwd:
        try:
            from git_notes_memory.git_ops import GitOps

            git_ops = GitOps(repo_path=cwd)
            if git_ops.push_notes_to_remote():
                logger.debug("Pushed notes to remote on session stop")
            else:
                logger.debug("Push to remote failed (will retry next session)")
        except Exception as e:
            logger.debug("Remote push on stop skipped: %s", e)
```

**Fixed Code**:
```python
if config.stop_push_remote:
    cwd = input_data.get("cwd")
    if cwd:
        try:
            from git_notes_memory.git_ops import GitOps

            git_ops = GitOps(repo_path=cwd)
            result = git_ops.sync_notes_with_remote(push=True)
            if any(result.values()):
                logger.debug("Synced notes with remote on session stop: %s", result)
            else:
                logger.debug("Sync with remote had no changes")
        except Exception as e:
            logger.debug("Remote sync on stop skipped: %s", e)
```

**Checklist**:
- [ ] Replace `push_notes_to_remote()` with `sync_notes_with_remote(push=True)`
- [ ] Update success logging to show sync result dict
- [ ] Update failure logging message
- [ ] Update exception logging message

## Phase 2: Testing

### Task 2.1: Update existing tests

**File**: `tests/hooks/test_stop_handler.py`

Update any mocks that expect `push_notes_to_remote` to instead expect `sync_notes_with_remote`.

**Checklist**:
- [ ] Find tests mocking `push_notes_to_remote`
- [ ] Update mocks to use `sync_notes_with_remote`
- [ ] Verify return value handling (dict vs bool)

### Task 2.2: Add sync-specific tests

**File**: `tests/hooks/test_stop_handler.py`

**New Tests**:
- [ ] `test_stop_handler_uses_sync_with_push_true` - Verify sync called with push=True
- [ ] `test_stop_handler_sync_partial_success` - Some namespaces succeed, some fail
- [ ] `test_stop_handler_sync_all_fail_non_blocking` - Complete failure doesn't block

## Phase 3: Verification

### Task 3.1: Run test suite

```bash
uv run pytest tests/hooks/test_stop_handler.py -v
```

**Checklist**:
- [ ] All existing tests pass
- [ ] New tests pass
- [ ] No regressions in other test files

### Task 3.2: Run full quality checks

```bash
make quality
```

**Checklist**:
- [ ] Formatting passes
- [ ] Linting passes
- [ ] Type checking passes
- [ ] Security scan passes
- [ ] All tests pass with coverage ≥80%

### Task 3.3: Manual verification

1. Create two worktrees
2. Start Claude sessions in both
3. Capture memories in both sessions
4. End sessions within seconds of each other
5. Verify both memories appear in git notes

**Checklist**:
- [ ] No conflict errors in session output
- [ ] Both memories preserved in remote
- [ ] `git notes --ref=refs/notes/mem/progress list` shows both

## Timeline Summary

| Phase | Tasks | Estimated Effort |
|-------|-------|------------------|
| Phase 1: Implementation | 1 task | Minimal |
| Phase 2: Testing | 2 tasks | Small |
| Phase 3: Verification | 3 tasks | Small |

**Total**: 6 tasks, minimal effort

## Dependencies

- `sync_notes_with_remote()` already implemented (Issue #18)
- `cat_sort_uniq` merge strategy already configured (Issue #18)
- No external dependencies

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Sync slower than push | Acceptable - happens at session end |
| Merge conflicts | cat_sort_uniq handles gracefully |
| Network failures | Same exception handling as before |

## Rollback

Single-line revert:
```python
# Revert to:
if git_ops.push_notes_to_remote():
```
