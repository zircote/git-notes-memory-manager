---
document_type: requirements
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T23:47:00Z
status: draft
github_issue: https://github.com/zircote/git-notes-memory/issues/13
---

# Multi-Domain Memories - Product Requirements Document

## Executive Summary

Implement multi-domain memory storage to distinguish between user-level (global) preferences and project-level context. User-level memories persist across all projects and capture universal learnings, preferences, and practices. Project-level memories (existing behavior) remain scoped to the current repository. Both domains are stored as git notes, indexed separately, and merged seamlessly during recall.

The solution uses a separate bare git repository at `~/.local/share/memory-plugin/user-memories/` for user-level storage, with optional remote sync for cross-machine portability. When memories from both domains are relevant, project memories take precedence (local context overrides global).

## Problem Statement

### The Problem

Currently, all memories are scoped to the current git repository under `refs/notes/mem/{namespace}`. This creates knowledge silos where:

1. **Learnings don't transfer** - When a user discovers a useful pattern or best practice, that knowledge is trapped in a single project and must be re-captured in each new repository.

2. **Preferences reset each project** - User-specific preferences (coding style, tool choices, review criteria) don't carry over, forcing repetitive re-expression of the same requirements.

3. **Cross-project patterns are lost** - Universal patterns (error handling approaches, testing strategies, documentation standards) that apply across all work are not persisted globally.

4. **New project cold starts** - Starting a new project means starting with zero memory context, even for an experienced user with extensive prior learnings.

### Impact

- **Knowledge Loss**: Valuable insights captured in one project are inaccessible in others
- **Repetitive Context**: Users must repeatedly explain the same preferences across projects
- **Slower Ramp-up**: Each new project starts without the benefit of prior experience
- **Fragmented Learning**: No single source of truth for user's accumulated knowledge

### Current State

All memories are stored in:
- **Git notes**: `refs/notes/mem/{namespace}` in the current repository
- **SQLite index**: Project-specific at `~/.local/share/memory-plugin/{repo-hash}/index.db`

There is no mechanism to share memories across repositories or distinguish between project-specific and universal knowledge.

## Goals and Success Criteria

### Primary Goal

Enable memories to be captured and recalled across two distinct domains:
- **User domain**: Global memories accessible from any project
- **Project domain**: Repository-scoped memories (existing behavior)

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| User memories accessible cross-project | 100% | Memory captured in Project A is recallable in Project B |
| No regression in project memory isolation | 0 cross-bleed | Project memories remain scoped to their repository |
| Recall performance | <100ms additional latency | Timing comparison before/after |
| User memory sync round-trip | <5s for 1000 memories | Remote push/pull timing |

### Non-Goals (Explicit Exclusions)

- **Team/Organization domain**: A shared team memory layer is out of scope for v1 (deferred to v2)
- **Memory migration between domains**: Converting existing project memories to user-level is not supported
- **Automatic domain inference**: Users must explicitly mark memories as global; no AI-based classification
- **Conflict resolution UI**: Conflicts are resolved by "project overrides user" rule, no interactive merge

## User Analysis

### Primary Users

**Claude Code Users** - Developers using the memory plugin to enhance Claude's context
- **Needs**: Persistent learnings that apply across all their projects
- **Context**: May work on 5-20 active projects simultaneously
- **Pain Point**: Re-expressing the same preferences and patterns repeatedly

### User Stories

1. As a **developer working on multiple projects**, I want my coding style preferences (formatting, naming conventions, review criteria) to be remembered globally so that Claude applies them consistently everywhere.

2. As a **user who learns a new pattern**, I want to mark it as a "global learning" so that it's available in all my future projects, not just the current one.

3. As a **developer starting a new project**, I want Claude to have access to my accumulated learnings and preferences from prior work so that I don't start from scratch.

4. As a **user switching machines**, I want to sync my global memories so that my preferences follow me across development environments.

5. As a **developer on a specific project**, I want project-specific decisions and context to stay scoped to that project and not pollute my global memory.

## Functional Requirements

### Must Have (P0)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | Capture memories with explicit domain selection | Users must control where memories are stored | Capture with `[global]` marker stores in user domain; default stores in project domain |
| FR-002 | Recall merges user and project memories | Both domains should be searchable together | Search returns results from both domains, labeled by source |
| FR-003 | Project memories override user memories on conflict | Local context is more specific | When same-topic memories exist in both, project appears first/higher priority |
| FR-004 | User memories stored in separate bare git repo | Clean separation, portable, git-native | Bare repo at `~/.local/share/memory-plugin/user-memories/` with standard git notes structure |
| FR-005 | Domain-aware signal detection | Hook system must recognize domain markers | `[global]` inline marker and `▶ global:namespace ───` block format supported |
| FR-006 | SessionStart injects both domains | Context should include user preferences | ContextBuilder fetches from both user and project indices, merges with precedence |

### Should Have (P1)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-101 | Optional remote sync for user memories | Cross-machine portability | Configure remote origin, sync via `/memory:sync --user --remote` |
| FR-102 | Auto-sync on session events | Seamless cross-machine experience | With env vars set, fetch on SessionStart, push on Stop |
| FR-103 | Status command shows both domains | Visibility into memory state | `/memory:status` displays counts for user and project domains separately |
| FR-104 | Domain filtering in recall | Targeted searches | `/memory:recall --domain=user` searches only user memories |

### Nice to Have (P2)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-201 | Memory domain migration utility | Allow moving memories between domains | CLI command to copy/move a memory from project to user domain |
| FR-202 | Domain-specific namespaces | Some namespaces may be user-only | Configure namespaces like `preferences` as user-domain-default |
| FR-203 | Bulk import from existing memories | Bootstrap global memories | Script to scan all indexed projects and promote common patterns |

## Non-Functional Requirements

### Performance

- **Recall latency**: Adding user domain search should add <100ms to recall operations
- **SessionStart injection**: Combined context building should complete in <500ms
- **Sync operations**: Full user-memory sync (1000 memories) should complete in <5s

### Security

- **Path traversal**: User memories path must be validated to stay within XDG data directory
- **Git injection**: All git commands must use parameterized arguments, never shell interpolation
- **No credential storage**: Remote sync uses existing git credential helpers, plugin stores no secrets

### Scalability

- **User memory count**: Support up to 10,000 user-level memories without degradation
- **Index size**: User index should remain performant up to 50MB
- **Concurrent access**: User and project operations should be thread-safe

### Reliability

- **Graceful degradation**: If user-memories repo is unavailable, fall back to project-only mode
- **Index sync recovery**: If user index drifts from git notes, sync command rebuilds it
- **Atomic operations**: Capture to either domain should be atomic (file locking)

### Maintainability

- **Existing test coverage maintained**: No regression in test suite
- **New code covered**: New domain functionality at 80%+ coverage
- **Type annotations**: All new code fully typed (mypy strict)

## Technical Constraints

### Technology Stack Requirements

- Python 3.11+ (existing project requirement)
- SQLite + sqlite-vec for indexing (existing)
- Git notes for storage (existing)
- sentence-transformers for embeddings (existing)

### Integration Requirements

- Must integrate with existing `CaptureService`, `RecallService`, `IndexService`
- Must extend `SignalDetector` for domain markers
- Must extend `ContextBuilder` for multi-domain context
- Must work with existing hooks subsystem

### Compatibility Requirements

- **Backward compatible**: Existing project memories continue working unchanged
- **Index migration**: Add `domain` column to memories table via migration
- **No breaking API changes**: Existing function signatures remain valid, new domain parameter optional

## Dependencies

### Internal Dependencies

- `git_notes_memory.capture` - Extend for domain-aware capture
- `git_notes_memory.recall` - Extend for multi-domain search
- `git_notes_memory.index` - Add domain column, search filtering
- `git_notes_memory.hooks.signal_detector` - Add domain markers
- `git_notes_memory.hooks.context_builder` - Merge both domain contexts
- `git_notes_memory.sync` - Extend for user-memory repo sync

### External Dependencies

- `git` CLI - Already required, no new dependency
- No new PyPI packages required

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| User-memory repo corruption | Low | High | Implement verification on sync, auto-rebuild index from git notes |
| Performance regression from dual-index queries | Medium | Medium | Use parallel queries, cache user index, lazy-load on first use |
| Domain marker confusion with existing syntax | Low | Medium | Use distinct prefix `[global]` that doesn't conflict with `[decision]` etc |
| Cross-machine sync conflicts | Medium | Medium | Append-only storage with timestamp ordering, no merge conflicts |
| Index schema migration failure | Low | High | Graceful migration with fallback, test extensively |

## Open Questions

All open questions from GitHub Issue #13 have been answered via elicitation:

- [x] **Storage approach**: Separate bare git repo at `~/.local/share/memory-plugin/user-memories/`
- [x] **Conflict resolution**: Project memories override user memories
- [x] **Team domain**: Deferred to v2
- [x] **Sync mechanism**: Optional remote auto-sync (opt-in via env vars)

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| Domain | Storage scope for memories: either "user" (global) or "project" (repo-scoped) |
| User memories | Memories stored in the user-level bare git repo, accessible from all projects |
| Project memories | Memories stored in the current git repository, existing behavior |
| Bare repo | A git repository without a working tree, just the `.git` contents |

### References

- [GitHub Issue #13](https://github.com/zircote/git-notes-memory/issues/13) - Original feature request
- [Git Notes Documentation](https://git-scm.com/docs/git-notes) - Git notes storage format
- [XDG Base Directory Spec](https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html) - For data directory placement
