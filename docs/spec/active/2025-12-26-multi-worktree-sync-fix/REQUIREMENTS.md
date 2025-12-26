---
document_type: requirements
project_id: SPEC-2025-12-26-001
version: 1.0.0
last_updated: 2025-12-26T14:23:00Z
status: draft
---

# Multi-Worktree Sync Fix - Product Requirements Document

## Executive Summary

This is a bug fix addressing race conditions in multi-worktree environments where concurrent Claude sessions experience git notes ref conflicts despite auto-sync hooks being enabled. The fix replaces a direct push operation with a proper fetch→merge→push workflow that already exists in the codebase.

**GitHub Issue**: [#28](https://github.com/zircote/git-notes-memory/issues/28)

## Problem Statement

### The Problem

When multiple Claude Code sessions run concurrently in different git worktrees (all sharing the same repository's `.git/` directory), the SessionStop hook's push operation can fail or cause conflicts because it doesn't fetch and merge remote changes before pushing.

### Impact

- **Who**: Developers using multiple worktrees with auto-sync enabled
- **Severity**: Medium - requires manual intervention via `/memory:sync --remote`
- **Frequency**: Occurs whenever two or more sessions are active and one pushes before another

### Current State

The SessionStop hook calls `push_notes_to_remote()` which pushes directly:

```python
# stop_handler.py:482
if git_ops.push_notes_to_remote():  # Direct push, no fetch first
    logger.debug("Pushed notes to remote on session stop")
```

### Race Condition Timeline

```
Worktree A              Worktree B              Worktree C
───────────────────────────────────────────────────────────────
SessionStart: fetch ──►
                        SessionStart: fetch ──►
Capture memory ──►
                        Capture memory ──►
                                                SessionStart ──►
                        SessionStop: PUSH ──►   (remote updated)
SessionStop: PUSH ──►   CONFLICT!               Capture ──►
                        (local refs stale)
───────────────────────────────────────────────────────────────
```

## Goals and Success Criteria

### Primary Goal

Eliminate notes ref conflicts in multi-worktree environments by ensuring the Stop hook performs a proper sync before pushing.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Conflict rate | 0% | Manual testing with concurrent sessions |
| Test coverage | 90%+ | pytest coverage report |
| Behavioral change | Transparent | No user-facing workflow changes |

### Non-Goals (Explicit Exclusions)

- Implementing distributed locking mechanisms
- Adding retry logic for transient failures
- Adding user notifications for sync operations
- Changing the SessionStart behavior
- Supporting non-origin remotes

## User Analysis

### Primary Users

- **Who**: Developers using git-notes-memory plugin with multiple active worktrees
- **Needs**: Seamless memory sync without manual intervention
- **Context**: Multi-worktree development workflows with `HOOK_STOP_PUSH_REMOTE=true`

### User Stories

1. As a developer with multiple worktrees, I want my memories to sync automatically so that I don't have to run manual sync commands.
2. As a developer, I want concurrent sessions to not conflict so that my workflow isn't interrupted.

## Functional Requirements

### Must Have (P0)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | Stop hook uses sync_notes_with_remote() instead of push_notes_to_remote() | Ensures fetch→merge→push workflow | stop_handler.py calls sync_notes_with_remote(push=True) |
| FR-002 | Sync failures are logged but don't block session end | Maintains current non-blocking behavior | Exception handling preserved, logs written |
| FR-003 | Existing tests pass | No regression | All tests in test_stop_handler.py pass |

## Non-Functional Requirements

### Performance

- Sync operation may take slightly longer due to fetch+merge
- This is acceptable as it happens at session end (non-blocking)

### Reliability

- Must not block session termination on sync failures
- Must log sync results for debugging

### Backward Compatibility

- No changes to environment variables
- No changes to user-facing behavior
- Existing workflows continue to work

## Technical Constraints

- Must use existing `sync_notes_with_remote()` method
- Must preserve current exception handling pattern
- Must work with all configured namespaces

## Dependencies

### Internal Dependencies

- `GitOps.sync_notes_with_remote()` - Already implemented, proven working
- `HookConfig.stop_push_remote` - Existing configuration

### External Dependencies

- None - fix uses existing infrastructure

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Sync takes longer than push | Low | Low | Acceptable trade-off; happens at session end |
| Merge conflicts in cat_sort_uniq | Low | Low | cat_sort_uniq strategy handles gracefully |
| Network failures during sync | Medium | Low | Current exception handling preserves behavior |

## Open Questions

- None - fix is well-defined in issue #28

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| Worktree | Git worktree allowing multiple working directories for same repo |
| cat_sort_uniq | Git notes merge strategy that concatenates, sorts, and deduplicates |
| Notes refs | Git references under refs/notes/mem/* storing memory data |

### References

- [GitHub Issue #28](https://github.com/zircote/git-notes-memory/issues/28)
- [Issue #18](https://github.com/zircote/git-notes-memory/issues/18) - Implemented sync_notes_with_remote()
