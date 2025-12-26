---
document_type: implementation_plan
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T23:47:00Z
status: draft
estimated_effort: 5 phases, 24 tasks
---

# Multi-Domain Memories - Implementation Plan

## Overview

This plan implements multi-domain memory storage in 5 phases, building from foundational components to full integration. Each phase is independently testable and can be merged incrementally.

## Phase Summary

| Phase | Focus | Key Deliverables | Dependencies |
|-------|-------|------------------|--------------|
| Phase 1: Foundation | Data model, config, schema | Domain enum, paths, migration | None |
| Phase 2: Storage Layer | GitOps, IndexService | User-memories repo, domain filtering | Phase 1 |
| Phase 3: Service Layer | Capture, Recall | Domain-aware services | Phase 2 |
| Phase 4: Hooks Integration | Signal detection, context | Markers, SessionStart | Phase 3 |
| Phase 5: Sync & Polish | Remote sync, CLI, docs | User sync, commands | Phase 4 |

---

## Phase 1: Foundation

**Goal**: Establish data models, configuration, and database schema for domain support

**Prerequisites**: None - foundational work

### Tasks

#### Task 1.1: Add Domain Enum to Config
- **Description**: Create `Domain` enum and path helper functions in `config.py`
- **Acceptance Criteria**:
  - [ ] `Domain` enum with `USER` and `PROJECT` values
  - [ ] `get_user_memories_path()` returns `~/.local/share/memory-plugin/user-memories/`
  - [ ] `get_user_index_path()` returns `~/.local/share/memory-plugin/user/index.db`
  - [ ] Functions create directories if they don't exist
- **Notes**: Use existing XDG pattern from `get_index_path()`

#### Task 1.2: Extend Memory Model with Domain Field
- **Description**: Add `domain` field to `Memory` dataclass with backward-compatible default
- **Acceptance Criteria**:
  - [ ] `Memory.domain: Domain = Domain.PROJECT` field added
  - [ ] Existing code continues to work without changes
  - [ ] `Memory.id` property handles both formats
- **Notes**: Frozen dataclass, must maintain immutability

#### Task 1.3: Create Schema Migration for Domain Column
- **Description**: Add migration to SCHEMA_VERSION 3 in `index.py`
- **Acceptance Criteria**:
  - [ ] `_MIGRATIONS[3]` adds `domain TEXT DEFAULT 'project'`
  - [ ] Index `idx_memories_domain` created
  - [ ] `SCHEMA_VERSION` updated to 3
  - [ ] Migration runs cleanly on existing databases
- **Notes**: Follow existing migration pattern from version 2

#### Task 1.4: Update IndexService for Domain
- **Description**: Extend IndexService CRUD operations to include domain
- **Acceptance Criteria**:
  - [ ] `insert()` accepts optional `domain` parameter
  - [ ] `_row_to_memory()` populates `Memory.domain` from row
  - [ ] Serialization handles domain field
- **Notes**: Default domain is PROJECT for backward compatibility

### Phase 1 Deliverables
- [ ] Domain enum in config
- [ ] Memory model extended
- [ ] Schema migration to v3
- [ ] Tests for all new code

### Phase 1 Exit Criteria
- [ ] `make quality` passes
- [ ] All existing tests pass
- [ ] New domain functionality has test coverage

---

## Phase 2: Storage Layer

**Goal**: Implement domain-aware git operations and index search filtering

**Prerequisites**: Phase 1 complete

### Tasks

#### Task 2.1: Create GitOps Factory for Domain
- **Description**: Add `GitOps.for_domain(domain: Domain)` class method
- **Acceptance Criteria**:
  - [ ] Factory returns appropriate GitOps instance for domain
  - [ ] USER domain uses `get_user_memories_path()`
  - [ ] PROJECT domain uses current repo (existing behavior)
  - [ ] Instance cached per domain
- **Notes**: Consider singleton pattern per domain

#### Task 2.2: Initialize User-Memories Bare Repo
- **Description**: Create and initialize bare git repo for user memories
- **Acceptance Criteria**:
  - [ ] `_ensure_user_repo()` creates bare repo if not exists
  - [ ] Runs `git init --bare` in user-memories path
  - [ ] Creates initial empty commit for notes refs
  - [ ] Idempotent - safe to call multiple times
- **Notes**: Similar to existing repo initialization patterns

#### Task 2.3: Add Domain Filter to IndexService Search
- **Description**: Extend `search_vector()` and `search_text()` with domain filter
- **Acceptance Criteria**:
  - [ ] `search_vector(..., domain: Domain | None = None)`
  - [ ] `domain=None` searches all domains (existing behavior)
  - [ ] `domain=USER` filters to user memories only
  - [ ] `domain=PROJECT` filters to project memories only
  - [ ] SQL query uses parameterized domain filter
- **Notes**: Maintain backward compatibility with existing callers

#### Task 2.4: Add Domain Filter to Other Index Methods
- **Description**: Extend `get_by_namespace()`, `get_by_spec()`, `list_recent()` with domain filter
- **Acceptance Criteria**:
  - [ ] All query methods accept optional `domain` parameter
  - [ ] Consistent filtering behavior across methods
  - [ ] `get_stats()` returns counts by domain
- **Notes**: Follow same pattern as Task 2.3

### Phase 2 Deliverables
- [ ] GitOps domain factory
- [ ] User-memories bare repo initialization
- [ ] Domain filtering in all index queries
- [ ] Tests for storage layer

### Phase 2 Exit Criteria
- [ ] User-memories repo can be created and accessed
- [ ] Index queries filter correctly by domain
- [ ] All tests pass

---

## Phase 3: Service Layer

**Goal**: Implement domain-aware capture and recall services

**Prerequisites**: Phase 2 complete

### Tasks

#### Task 3.1: Extend CaptureService for Domain
- **Description**: Add domain parameter to `capture()` method
- **Acceptance Criteria**:
  - [ ] `capture(..., domain: Domain = Domain.PROJECT)`
  - [ ] Uses `GitOps.for_domain(domain)` for storage
  - [ ] Stores in correct index with domain field
  - [ ] Generates appropriate memory ID format
- **Notes**: Memory ID for user: `user:{namespace}:{sha}:{idx}`

#### Task 3.2: Create User CaptureService Singleton
- **Description**: Add factory function for user-domain capture service
- **Acceptance Criteria**:
  - [ ] `get_user_capture_service()` returns singleton
  - [ ] Pre-configured with user GitOps and user index
  - [ ] Lazy initialization - only creates on first use
- **Notes**: Follow existing service registry pattern

#### Task 3.3: Extend RecallService for Multi-Domain Search
- **Description**: Modify `search()` to query both domains and merge results
- **Acceptance Criteria**:
  - [ ] `search(..., domain: Domain | None = None)`
  - [ ] `domain=None` searches both domains
  - [ ] Project results ordered before user results at equal relevance
  - [ ] Deduplication of similar memories across domains
- **Notes**: Use parallel queries for performance

#### Task 3.4: Add Domain Convenience Methods to RecallService
- **Description**: Add `search_user()` and `search_project()` convenience methods
- **Acceptance Criteria**:
  - [ ] `search_user(query, **kwargs)` searches only user domain
  - [ ] `search_project(query, **kwargs)` searches only project domain
  - [ ] Both delegate to `search()` with domain parameter
- **Notes**: Simple wrappers for API clarity

#### Task 3.5: Update MemoryResult with Domain
- **Description**: Ensure domain information flows through search results
- **Acceptance Criteria**:
  - [ ] `MemoryResult.memory.domain` populated correctly
  - [ ] Hydration works for both domains
  - [ ] `hydrate_batch()` uses correct GitOps per memory
- **Notes**: May need to track which GitOps to use per result

### Phase 3 Deliverables
- [ ] Domain-aware CaptureService
- [ ] Multi-domain RecallService
- [ ] Convenience methods for domain-specific search
- [ ] Integration tests for service layer

### Phase 3 Exit Criteria
- [ ] Can capture to user domain
- [ ] Can recall from both domains
- [ ] Project memories override user on conflict
- [ ] All tests pass

---

## Phase 4: Hooks Integration

**Goal**: Integrate domain awareness into hooks subsystem

**Prerequisites**: Phase 3 complete

### Tasks

#### Task 4.1: Add Domain Markers to SignalDetector
- **Description**: Extend pattern matching to recognize domain markers
- **Acceptance Criteria**:
  - [ ] `[global]` and `[user]` detected as USER domain
  - [ ] `[project]` and `[local]` detected as PROJECT domain
  - [ ] `CaptureSignal` model extended with `domain` field
  - [ ] Detection confidence appropriate for markers
- **Notes**: Add to `SIGNAL_PATTERNS` dict

#### Task 4.2: Extend Block Pattern for Domain Prefix
- **Description**: Support `▶ global:decision ───` format
- **Acceptance Criteria**:
  - [ ] Block pattern regex updated for optional domain prefix
  - [ ] `global:`, `user:` prefix sets USER domain
  - [ ] `project:`, `local:` prefix sets PROJECT domain
  - [ ] No prefix defaults to PROJECT (backward compatible)
- **Notes**: Extend `BLOCK_PATTERN` regex

#### Task 4.3: Update UserPromptSubmit Handler
- **Description**: Pass detected domain to capture
- **Acceptance Criteria**:
  - [ ] Domain from CaptureSignal passed to capture service
  - [ ] Uses appropriate capture service based on domain
  - [ ] Logging includes domain information
- **Notes**: Handler in `hooks/user_prompt_handler.py`

#### Task 4.4: Extend ContextBuilder for User Memories
- **Description**: Include user memories in SessionStart context
- **Acceptance Criteria**:
  - [ ] `_build_working_memory()` queries both domains
  - [ ] `_build_semantic_context()` queries both domains
  - [ ] User memories labeled in XML output
  - [ ] Token budget split appropriately
- **Notes**: Project memories take priority in budget allocation

#### Task 4.5: Add Domain Labels to XML Output
- **Description**: Include domain information in context XML
- **Acceptance Criteria**:
  - [ ] `<memory>` elements include `domain="user"` or `domain="project"`
  - [ ] Section headings indicate domain when mixed
  - [ ] Styling hints for domain differentiation
- **Notes**: Extend `XMLBuilder.add_memory_element()`

### Phase 4 Deliverables
- [ ] Domain marker detection
- [ ] Block pattern with domain prefix
- [ ] Handler integration
- [ ] Multi-domain context building
- [ ] Tests for hooks integration

### Phase 4 Exit Criteria
- [ ] `[global]` marker captures to user domain
- [ ] SessionStart includes user memories
- [ ] All tests pass

---

## Phase 5: Sync & Polish

**Goal**: Remote sync, CLI commands, documentation

**Prerequisites**: Phase 4 complete

### Tasks

#### Task 5.1: Implement User Memory Sync
- **Description**: Add `sync_user_memories()` to SyncService
- **Acceptance Criteria**:
  - [ ] Sync user index with user-memories git notes
  - [ ] Reuse existing sync patterns from project sync
  - [ ] Handle user-memories repo not existing gracefully
- **Notes**: Follow patterns from completed refspec fix spec

#### Task 5.2: Add Optional Remote Sync for User Memories
- **Description**: Support push/pull to remote for user-memories repo
- **Acceptance Criteria**:
  - [ ] `USER_MEMORIES_REMOTE` env var configures remote URL
  - [ ] `sync_user_memories(remote=True)` pushes/pulls
  - [ ] Refspec patterns follow project sync patterns
- **Notes**: Use `+refs/notes/mem/*:refs/notes/mem/*` refspec

#### Task 5.3: Add Auto-Sync Hooks for User Memories
- **Description**: Optional auto-sync on session events
- **Acceptance Criteria**:
  - [ ] `HOOK_SESSION_START_FETCH_USER_REMOTE` triggers fetch on start
  - [ ] `HOOK_STOP_PUSH_USER_REMOTE` triggers push on stop
  - [ ] Both disabled by default (opt-in)
  - [ ] Errors logged but don't block session
- **Notes**: Add to session_start_handler and stop_handler

#### Task 5.4: Update /memory:status Command
- **Description**: Show domain-separated statistics
- **Acceptance Criteria**:
  - [ ] Display user memory count and stats
  - [ ] Display project memory count and stats
  - [ ] Show sync status for both domains
- **Notes**: Extend existing status command

#### Task 5.5: Add /memory:recall Domain Filter
- **Description**: Add `--domain` flag to recall command
- **Acceptance Criteria**:
  - [ ] `/memory:recall --domain=user <query>` searches user only
  - [ ] `/memory:recall --domain=project <query>` searches project only
  - [ ] Default (no flag) searches both
- **Notes**: Update command definition and handler

#### Task 5.6: Update Documentation
- **Description**: Document multi-domain feature in README and CLAUDE.md
- **Acceptance Criteria**:
  - [ ] README.md updated with domain section
  - [ ] CLAUDE.md environment variables documented
  - [ ] Usage examples for domain markers
  - [ ] Migration notes for existing users
- **Notes**: Include configuration examples

### Phase 5 Deliverables
- [ ] User memory sync
- [ ] Remote sync support
- [ ] Auto-sync hooks
- [ ] Updated CLI commands
- [ ] Documentation

### Phase 5 Exit Criteria
- [ ] User memories can sync to remote
- [ ] Auto-sync works on session events
- [ ] All commands support domain awareness
- [ ] Documentation complete

---

## Dependency Graph

```
Phase 1: Foundation
  Task 1.1 (Domain enum) ──┬──► Task 1.2 (Memory model)
                           │
                           └──► Task 1.3 (Schema migration) ──► Task 1.4 (Index domain)
                                         │
                                         ▼
Phase 2: Storage Layer ◄─────────────────┘
  Task 2.1 (GitOps factory) ──► Task 2.2 (User repo init)
                                         │
  Task 2.3 (Search filter) ◄─────────────┤
                           │             │
  Task 2.4 (Other filters) ◄─────────────┘
           │
           ▼
Phase 3: Service Layer
  Task 3.1 (CaptureService domain) ──► Task 3.2 (User capture singleton)
                                                │
  Task 3.3 (RecallService multi-domain) ◄───────┼──► Task 3.4 (Convenience methods)
                                                │
  Task 3.5 (MemoryResult domain) ◄──────────────┘
           │
           ▼
Phase 4: Hooks Integration
  Task 4.1 (Domain markers) ──┬──► Task 4.2 (Block pattern)
                              │
                              └──► Task 4.3 (Handler update) ──► Task 4.4 (ContextBuilder)
                                                                         │
  Task 4.5 (XML labels) ◄────────────────────────────────────────────────┘
           │
           ▼
Phase 5: Sync & Polish
  Task 5.1 (User sync) ──► Task 5.2 (Remote sync) ──► Task 5.3 (Auto-sync hooks)
           │
  Task 5.4 (Status cmd) ◄─┤
           │              │
  Task 5.5 (Recall cmd) ◄─┘
           │
  Task 5.6 (Documentation) ◄──────────────────────────────────────────────┘
```

## Risk Mitigation Tasks

| Risk | Mitigation Task | Phase |
|------|-----------------|-------|
| Schema migration failure | Task 1.3 - thorough testing, rollback script | 1 |
| Performance regression | Task 3.3 - parallel queries, monitoring | 3 |
| Marker parsing conflicts | Task 4.1 - distinct `[global]` prefix | 4 |
| Remote sync conflicts | Task 5.2 - append-only, timestamp ordering | 5 |

## Testing Checklist

### Unit Tests
- [ ] Domain enum and path functions (Phase 1)
- [ ] Schema migration (Phase 1)
- [ ] GitOps factory (Phase 2)
- [ ] Domain filtering in index (Phase 2)
- [ ] Signal detection patterns (Phase 4)

### Integration Tests
- [ ] Capture to user domain stores correctly (Phase 3)
- [ ] Recall merges both domains (Phase 3)
- [ ] SessionStart includes user memories (Phase 4)
- [ ] User sync round-trip (Phase 5)

### End-to-End Tests
- [ ] Create `[global]` memory, verify in user index
- [ ] Switch projects, verify user memory accessible
- [ ] Configure remote, verify sync works
- [ ] Full workflow: capture → recall → sync

## Documentation Tasks

- [ ] Update README.md with domain feature
- [ ] Update CLAUDE.md environment variables section
- [ ] Add domain examples to usage documentation
- [ ] Update CHANGELOG.md with feature entry

## Launch Checklist

- [ ] All tests passing (80%+ coverage for new code)
- [ ] `make quality` passes
- [ ] Documentation complete
- [ ] CLAUDE.md updated with new env vars
- [ ] Rollback plan tested
- [ ] Stakeholder sign-off

## Post-Launch

- [ ] Monitor for issues (24-48 hours)
- [ ] Gather user feedback on domain UX
- [ ] Update architecture docs with learnings
- [ ] Archive planning documents to `completed/`
