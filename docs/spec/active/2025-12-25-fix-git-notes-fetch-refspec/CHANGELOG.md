# Changelog

All notable changes to this specification will be documented in this file.

## [1.2.0] - 2025-12-25

### Status Change
- Specification approved for implementation
- Status: `in-review` → `approved`
- Approved: 2025-12-25T22:02:04Z

## [1.1.0] - 2025-12-25

### Added
- Hook-based auto-sync feature (FR-104, FR-105)
- New Phase 4: Hook Auto-Sync in implementation plan
- ADR-007: Hook-Based Auto-Sync (Opt-In) decision record
- Environment variables: `HOOK_SESSION_START_FETCH_REMOTE`, `HOOK_STOP_PUSH_REMOTE`
- Component 6: Hook-Based Auto-Sync in architecture

### Changed
- Updated estimated effort to 5-7 hours (was 4-6 hours)
- Renumbered Phase 4 (Tests) to Phase 5
- Added Task 5.4 for hook auto-sync tests

---

## [1.0.0] - 2025-12-25

### Added
- Initial specification created from GitHub Issue #18
- Complete requirements specification (REQUIREMENTS.md)
- Technical architecture design (ARCHITECTURE.md)
- Implementation plan with 4 phases, 14 tasks (IMPLEMENTATION_PLAN.md)
- Architecture Decision Records (DECISIONS.md) with 6 ADRs:
  - ADR-001: Use remote tracking refs for fetch
  - ADR-002: Use force prefix (+) in fetch refspec
  - ADR-003: Naming convention for tracking refs
  - ADR-004: Auto-migration on session start
  - ADR-005: Merge strategy for notes (reaffirmed)
  - ADR-006: SyncService as orchestration layer

### Research Conducted
- Explored existing sync functionality in git_ops.py and sync.py
- Researched Git refspec best practices and documentation
- Analyzed the root cause of non-fast-forward rejection
- Identified the correct pattern: `+refs/notes/mem/*:refs/notes/origin/mem/*`

### Key Findings
- Root cause: Fetch refspec writes directly to local refs, failing on divergence
- Solution: Use remote tracking refs pattern (standard Git workflow)
- Migration: Auto-migrate on session start via SessionStart hook
- Impact: 4-6 hours estimated implementation effort

### References
- [GitHub Issue #18](https://github.com/zircote/git-notes-memory/issues/18)
- [Git Refspec Documentation](https://git-scm.com/book/en/v2/Git-Internals-The-Refspec)
- [Dealing with non-fast-forward errors](https://docs.github.com/en/get-started/using-git/dealing-with-non-fast-forward-errors)
