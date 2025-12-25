---
document_type: requirements
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T21:35:00Z
status: draft
---

# Fix Git Notes Fetch Refspec - Product Requirements Document

## Executive Summary

The git-notes-memory plugin's sync configuration has a fundamental flaw: it configures fetch to write directly to local refs (`refs/notes/mem/*:refs/notes/mem/*`), which causes "non-fast-forward rejected" errors when notes diverge between local and remote (common in multi-machine or multi-session scenarios). This fix will change the fetch pattern to use remote tracking refs and implement a proper fetch→merge→push workflow, enabling seamless multi-machine memory synchronization.

## Problem Statement

### The Problem

When users work across multiple machines or Claude Code sessions, git notes can diverge:
- Machine A creates notes and pushes
- Machine B (which started earlier) creates different notes
- Machine B's `git fetch` fails with "non-fast-forward rejected" because both have new notes

The error manifests as:
```
! [rejected]  refs/notes/mem/decisions -> refs/notes/mem/decisions  (non-fast-forward)
! [rejected]  refs/notes/mem/patterns  -> refs/notes/mem/patterns   (non-fast-forward)
! [rejected]  refs/notes/mem/progress  -> refs/notes/mem/progress   (non-fast-forward)
```

### Impact

| User Segment | Impact |
|--------------|--------|
| Multi-machine users | Cannot sync memories between machines |
| Team collaboration | Notes fail to merge properly |
| Long-running sessions | Divergence accumulates over time |
| All users | Silent failures during fetch operations |

### Current State

The plugin auto-configures sync at session start (`session_start_handler.py:169-179`) using `ensure_sync_configured()`. This sets:
- Push refspec: `refs/notes/mem/*:refs/notes/mem/*` (works fine)
- Fetch refspec: `refs/notes/mem/*:refs/notes/mem/*` (problematic)
- Merge strategy: `cat_sort_uniq` (correct, but never invoked)

The fetch refspec attempts to write directly to local refs, bypassing Git's merge machinery.

## Goals and Success Criteria

### Primary Goal

Enable reliable git notes synchronization across multiple machines and sessions by implementing the standard remote tracking refs pattern for fetch operations.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Fetch success rate | 100% (no non-fast-forward errors) | Manual testing across diverged repos |
| Merge completeness | All notes preserved after sync | Verify no note loss during merges |
| Migration success | Existing installs auto-migrate | `/memory:validate` reports healthy |
| Backward compatibility | No breaking changes for users | Existing workflows continue to work |

### Non-Goals (Explicit Exclusions)

- **Conflict resolution UI**: The `cat_sort_uniq` strategy handles merges automatically; no UI needed
- **Manual merge intervention**: Notes are append-only; conflicts are resolved by concatenation
- **Multi-remote support**: Only `origin` is supported (consistent with current implementation)
- **Partial namespace sync**: All namespaces sync together (simpler, matches current behavior)

## User Analysis

### Primary Users

- **Who**: Developers using git-notes-memory across multiple machines or sessions
- **Needs**: Seamless memory synchronization without manual intervention
- **Context**: They push/pull code and expect notes to follow automatically

### User Stories

1. As a developer with multiple machines, I want my memories to sync automatically so that I have full context everywhere
2. As a team collaborator, I want to fetch teammates' memories without errors so that we share knowledge
3. As a user with diverged notes, I want them to merge cleanly so that no memories are lost
4. As an existing user, I want my configuration to migrate automatically so that I don't need manual intervention

## Functional Requirements

### Must Have (P0)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | Use remote tracking refs for fetch | Avoids non-fast-forward rejection | Fetch refspec: `+refs/notes/mem/*:refs/notes/origin/mem/*` |
| FR-002 | Implement fetch→merge→push workflow | Enables proper note merging | `sync_notes_with_remote()` function available |
| FR-003 | Update `/memory:sync` for remote sync | User-facing sync command | Command syncs with origin when requested |
| FR-004 | Migrate existing fetch configuration | Existing users don't break | Old refspec replaced with new pattern |

### Should Have (P1)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-101 | Add refspec validation to `/memory:validate` | Detect misconfigured installs | Reports "incorrect fetch refspec" if old pattern found |
| FR-102 | Auto-migrate on session start | Seamless upgrade path | SessionStart hook detects and migrates old config |
| FR-103 | Add `--remote` flag to `/memory:sync` | Explicit remote sync option | `/memory:sync --remote` triggers full sync |
| FR-104 | Auto-fetch on SessionStart (opt-in) | Get latest memories from other machines | `HOOK_SESSION_START_FETCH_REMOTE=true` triggers fetch+merge |
| FR-105 | Auto-push on Stop (opt-in) | Backup memories when session ends | `HOOK_STOP_PUSH_REMOTE=true` triggers push |

### Nice to Have (P2)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-201 | Dry-run mode for remote sync | Preview before changing | `/memory:sync --remote --dry-run` shows changes |
| FR-202 | Per-namespace sync option | Partial sync if needed | `/memory:sync --remote --namespace=decisions` |

## Non-Functional Requirements

### Performance

- Sync operation should complete in < 5 seconds for typical note volumes (< 1000 notes)
- Batch operations for multi-namespace sync (existing `PERF-001` pattern)

### Security

- No change to existing security model
- All git operations continue to use subprocess (no shell=True)
- Refs validated via existing `_validate_git_ref()` (SEC-001)

### Reliability

- Graceful degradation if remote is unavailable
- Clear error messages for sync failures
- Idempotent operations (safe to run multiple times)

### Maintainability

- Follow existing code patterns (`GitOps` class methods)
- Comprehensive test coverage (match existing 80%+ standard)
- Type hints throughout (mypy strict compliance)

## Technical Constraints

- Must work with existing `cat_sort_uniq` merge strategy
- Must maintain backward compatibility with notes created before this fix
- Must not require user intervention for migration
- Must work with standard Git (no external dependencies)

## Dependencies

### Internal Dependencies

- `GitOps` class in `git_ops.py` (primary modification target)
- `SyncService` class in `sync.py` (extend for remote sync)
- `session_start_handler.py` (add migration check)
- `/memory:sync` command (add remote sync mode)
- `/memory:validate` command (add refspec validation)

### External Dependencies

- Git CLI (existing dependency, no changes)
- No new external dependencies required

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Old config not detected for migration | Low | High | Check for both old and new patterns in `is_sync_configured()` |
| Merge conflicts with complex note structures | Low | Medium | `cat_sort_uniq` handles this; test with edge cases |
| Breaking change for existing workflows | Medium | High | Extensive testing with existing repos; phased rollout |
| Remote not available during sync | Medium | Low | Graceful error handling; offline mode works unchanged |

## Open Questions

- [x] ~~Should we use `+` (force) prefix in fetch refspec?~~ **Yes**, required for non-fast-forward updates
- [x] ~~What remote tracking ref namespace to use?~~ **`refs/notes/origin/mem/*`** - mirrors origin naming

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| Refspec | A pattern that tells Git how to map refs between local and remote |
| Remote tracking ref | A ref that mirrors a remote ref (e.g., `refs/notes/origin/mem/decisions`) |
| Fast-forward | A merge where the target ref is a direct ancestor of the source |
| `cat_sort_uniq` | Git notes merge strategy that concatenates, sorts, and deduplicates |

### References

- [Git Refspec Documentation](https://git-scm.com/book/en/v2/Git-Internals-The-Refspec)
- [GitHub Issue #18](https://github.com/zircote/git-notes-memory/issues/18)
- [Dealing with non-fast-forward errors](https://docs.github.com/en/get-started/using-git/dealing-with-non-fast-forward-errors)
