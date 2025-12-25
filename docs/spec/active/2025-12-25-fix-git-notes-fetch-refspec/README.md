---
project_id: SPEC-2025-12-25-001
project_name: "Fix Git Notes Fetch Refspec"
slug: fix-git-notes-fetch-refspec
status: in-progress
created: 2025-12-25T21:35:00Z
approved: 2025-12-25T22:02:04Z
started: 2025-12-25T22:12:11Z
completed: null
expires: 2026-03-25T21:35:00Z
superseded_by: null
tags: [bug-fix, git-notes, sync, multi-machine]
stakeholders: []
github_issue: 18
worktree:
  branch: plan/fix-git-notes-fetch-refspec
  base_branch: main
  created_from_commit: 6f41cab
---

# Fix Git Notes Fetch Refspec

**GitHub Issue**: [#18](https://github.com/zircote/git-notes-memory/issues/18)

## Problem Statement

The current git notes fetch configuration causes repeated "non-fast-forward rejected" errors when local and remote notes have diverged (common with multiple sessions or machines).

## Root Cause

In `src/git_notes_memory/git_ops.py:731-742`, the fetch refspec is configured as:

```python
f"{base}/*:{base}/*"
# Results in: refs/notes/mem/*:refs/notes/mem/*
```

This fetches directly into local refs, which fails when both local and remote have new notes (diverged state). Git cannot fast-forward in this case.

## Proposed Solution

1. Change fetch refspec to use remote tracking refs pattern
2. Add a proper sync workflow (fetch → merge → push)
3. Update `/memory:sync` to handle remote synchronization
4. Add migration for existing installations

## Key Documents

| Document | Description |
|----------|-------------|
| [REQUIREMENTS.md](./REQUIREMENTS.md) | Product Requirements Document |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Technical Architecture |
| [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) | Phased Implementation Tasks |
| [DECISIONS.md](./DECISIONS.md) | Architecture Decision Records |

## Acceptance Criteria

- [ ] `git fetch origin` succeeds even when notes have diverged
- [ ] Notes from multiple sessions/machines are properly merged
- [ ] Existing installations can be migrated with `/memory:validate --fix`
- [ ] `/memory:sync` handles remote sync (not just local index)
