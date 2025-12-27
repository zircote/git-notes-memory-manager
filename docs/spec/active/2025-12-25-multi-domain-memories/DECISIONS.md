---
document_type: decisions
project_id: SPEC-2025-12-25-001
---

# Multi-Domain Memories - Architecture Decision Records

## ADR-001: Separate Bare Git Repo for User Memories

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: User (via elicitation)

### Context

User memories need to be stored separately from project memories. Three approaches were considered:
1. Separate bare git repo at `~/.local/share/memory-plugin/user-memories/`
2. Single index with domain column (user memories not in git)
3. Symlinked notes refs (central repo symlinked into projects)

### Decision

Use a separate bare git repository for user-level memories.

### Consequences

**Positive:**
- Maintains git-native semantics for both domains
- Clean separation - user repo can be synced independently
- Familiar git notes workflow applies to both domains
- Portable - entire user-memories directory can be backed up/restored

**Negative:**
- Two git repos to manage (complexity)
- Separate indices required
- More disk space usage

**Neutral:**
- Memory IDs need domain prefix to disambiguate

---

## ADR-002: Project Memories Override User Memories

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: User (via elicitation)

### Context

When memories from both domains are relevant to a query, we need a conflict resolution strategy:
1. Project overrides user (local context is more specific)
2. User overrides project (global preferences always apply)
3. Show both with labels (user decides in context)
4. Merge with recency (most recent wins)

### Decision

Project memories override user memories - local context takes precedence.

### Consequences

**Positive:**
- Honors the principle that local context is more specific
- Project-specific decisions correctly override general preferences
- Intuitive behavior for most use cases

**Negative:**
- User may need to explicitly reference global memory if project overrides
- Could mask important global learnings in some cases

**Neutral:**
- Requires careful result merging in RecallService

---

## ADR-003: Team Domain Deferred to v2

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: User (via elicitation)

### Context

A team/organization domain could enable shared team practices:
1. Include team domain in v1
2. Defer to v2 (keep scope focused)

### Decision

Defer team domain to v2.

### Consequences

**Positive:**
- Reduced v1 scope and complexity
- Can learn from user+project implementation before adding team
- Ship faster with focused feature set

**Negative:**
- Teams cannot share memories in v1
- May need architectural changes in v2 if not planned for

**Neutral:**
- Two-domain architecture should extend to three without major refactoring

---

## ADR-004: Optional Remote Auto-Sync

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: User (via elicitation)

### Context

User memories should be syncable across machines. Options:
1. Manual git push/pull only
2. Optional remote auto-sync (fetch on start, push on stop)
3. No sync, local only

### Decision

Implement optional remote auto-sync, disabled by default (opt-in via env vars).

### Consequences

**Positive:**
- Users who want cross-machine sync get seamless experience
- Users who don't want remote have no additional overhead
- Follows existing project sync patterns

**Negative:**
- Session start/stop slightly slower when enabled
- Network failures could delay session start

**Neutral:**
- Requires remote URL configuration (`USER_MEMORIES_REMOTE`)

---

## ADR-005: Memory ID Format with Domain Prefix

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Technical necessity

### Context

Memory IDs must be unique across both domains. Current format is `{namespace}:{commit_sha}:{index}`. Options:
1. Add domain prefix: `user:{namespace}:{sha}:{idx}`
2. Use different separator for user: `{namespace}@{sha}:{idx}`
3. Store domain separately, ID unchanged

### Decision

Use `user:` prefix for user-domain memories: `user:{namespace}:{commit_sha}:{index}`. Project memories keep existing format for backward compatibility.

### Consequences

**Positive:**
- Backward compatible - existing IDs unchanged
- Clear visual distinction between domains
- Easy to parse domain from ID

**Negative:**
- Asymmetric format (project has no prefix, user has prefix)
- Parsing logic needs to handle both formats

**Neutral:**
- Consistent with other ID schemes that use prefixes

---

## ADR-006: Lazy Initialization of User Infrastructure

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Technical necessity

### Context

User-memories repo and index may never be used if user doesn't capture global memories. Options:
1. Eager initialization - create on plugin install
2. Lazy initialization - create on first use
3. Manual initialization - user runs setup command

### Decision

Use lazy initialization - create user-memories repo and index on first global capture.

### Consequences

**Positive:**
- No overhead for users who don't use global memories
- Simpler installation - no setup step required
- Resources only created when needed

**Negative:**
- First global capture slightly slower (repo creation)
- Need to handle "not yet initialized" state in queries

**Neutral:**
- Follows existing lazy patterns in codebase

---

## ADR-007: Domain as Enum Rather Than String

**Date**: 2025-12-25
**Status**: Accepted
**Deciders**: Code quality considerations

### Context

Domain could be represented as:
1. String literals ("user", "project")
2. Enum class with typed values
3. Class constants

### Decision

Use Python Enum class for Domain with `USER` and `PROJECT` values.

### Consequences

**Positive:**
- Type safety - mypy catches invalid domain values
- IDE autocomplete support
- Single source of truth for valid values
- Easy to extend for team domain in v2

**Negative:**
- Slight serialization overhead (enum to/from string)
- More code than simple strings

**Neutral:**
- Consistent with existing patterns (e.g., `SignalType` enum)
