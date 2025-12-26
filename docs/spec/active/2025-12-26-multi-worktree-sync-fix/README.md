---
project_id: SPEC-2025-12-26-001
project_name: "Multi-Worktree Sync Fix"
slug: multi-worktree-sync-fix
status: completed
created: 2025-12-26T14:23:00Z
approved: 2025-12-26T19:52:59Z
approved_by: "Robert Allen <zircote@gmail.com>"
started: 2025-12-26T20:10:00Z
completed: 2025-12-26T20:30:00Z
expires: 2026-03-26T14:23:00Z
superseded_by: null
tags: [bug-fix, git-notes, hooks, multi-worktree, concurrency]
stakeholders: []
github_issue: https://github.com/zircote/git-notes-memory/issues/28
github_pr: https://github.com/zircote/git-notes-memory/pull/34
---

# Multi-Worktree Sync Fix

**Project ID**: SPEC-2025-12-26-001
**GitHub Issue**: [#28](https://github.com/zircote/git-notes-memory/issues/28)
**GitHub PR**: [#34](https://github.com/zircote/git-notes-memory/pull/34)
**Status**: Completed

## Summary

Fix race condition in multi-worktree environments where concurrent Claude sessions experience notes ref conflicts despite auto-sync hooks being enabled. The Stop hook currently uses `push_notes_to_remote()` which pushes without fetching first, causing conflicts when other worktrees have pushed since the session started.

## Problem

With `HOOK_SESSION_START_FETCH_REMOTE=true` and `HOOK_STOP_PUSH_REMOTE=true` enabled, notes refs can diverge between worktrees because:

1. SessionStart fetches at session beginning
2. SessionStop pushes directly without re-fetching
3. If another worktree pushed between start and stop, the push fails/conflicts

## Solution

Replace `push_notes_to_remote()` with `sync_notes_with_remote(push=True)` in the Stop hook. The `sync_notes_with_remote()` method already implements the correct fetch→merge→push workflow.

## Key Files

| File | Change |
|------|--------|
| `src/git_notes_memory/hooks/stop_handler.py:482` | Replace `push_notes_to_remote()` with `sync_notes_with_remote(push=True)` |

## Documents

- [REQUIREMENTS.md](./REQUIREMENTS.md) - Product requirements
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Technical design
- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) - Task breakdown
- [DECISIONS.md](./DECISIONS.md) - Architecture decisions
- [PROGRESS.md](./PROGRESS.md) - Implementation tracking
