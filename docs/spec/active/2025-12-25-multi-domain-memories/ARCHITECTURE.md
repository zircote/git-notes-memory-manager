---
document_type: architecture
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T23:47:00Z
status: draft
---

# Multi-Domain Memories - Technical Architecture

## System Overview

This architecture extends the existing git-notes-memory system to support two memory domains: **user** (global, cross-project) and **project** (repository-scoped, existing behavior). The design maintains backward compatibility while adding a parallel storage and retrieval path for user-level memories.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CAPTURE FLOW                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  User Input: "[global] I prefer tabs over spaces"                           │
│       │                                                                     │
│       ▼                                                                     │
│  ┌──────────────────┐                                                       │
│  │  SignalDetector  │───────────────────────────────────────────────┐       │
│  │  (domain marker) │                                               │       │
│  └────────┬─────────┘                                               │       │
│           │ domain = "user"                                         │       │
│           ▼                                                         ▼       │
│  ┌──────────────────┐                              ┌──────────────────────┐ │
│  │  CaptureService  │                              │  CaptureService      │ │
│  │  (user domain)   │                              │  (project domain)    │ │
│  └────────┬─────────┘                              └──────────┬───────────┘ │
│           │                                                   │             │
│           ▼                                                   ▼             │
│  ┌──────────────────┐                              ┌──────────────────────┐ │
│  │  UserGitOps      │                              │  ProjectGitOps       │ │
│  │  ~/.local/share/ │                              │  (current repo)      │ │
│  │  memory-plugin/  │                              │  refs/notes/mem/     │ │
│  │  user-memories/  │                              └──────────┬───────────┘ │
│  └────────┬─────────┘                                         │             │
│           │                                                   │             │
│           ▼                                                   ▼             │
│  ┌──────────────────┐                              ┌──────────────────────┐ │
│  │  UserIndex       │                              │  ProjectIndex        │ │
│  │  (user/index.db) │                              │  ({repo}/index.db)   │ │
│  └──────────────────┘                              └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                            RECALL FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Search Query: "coding preferences"                                         │
│       │                                                                     │
│       ▼                                                                     │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │                      RecallService                                │      │
│  │  ┌────────────────┐              ┌─────────────────────┐          │      │
│  │  │ UserIndex      │              │ ProjectIndex        │          │      │
│  │  │ search()       │              │ search()            │          │      │
│  │  └───────┬────────┘              └──────────┬──────────┘          │      │
│  │          │                                  │                     │      │
│  │          │    ┌─────────────────────┐       │                     │      │
│  │          └───►│   Merge & Rank      │◄──────┘                     │      │
│  │               │   (project first)   │                             │      │
│  │               └──────────┬──────────┘                             │      │
│  └──────────────────────────┼────────────────────────────────────────┘      │
│                             │                                               │
│                             ▼                                               │
│                    ┌─────────────────┐                                      │
│                    │ MemoryResult[]  │                                      │
│                    │ with domain tag │                                      │
│                    └─────────────────┘                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

1. **Separate Bare Git Repo**: User memories stored in a dedicated bare git repository rather than a shared location. This maintains git-native semantics for both domains.

2. **Parallel Index Pattern**: Two IndexService instances (user + project) rather than a single unified index. This keeps schemas simple and allows independent sync.

3. **Domain as First-Class Concept**: Added `domain` field to Memory model and index schema, enabling filtering at both capture and recall.

4. **Lazy Initialization**: User-memory infrastructure is only created when first accessed, avoiding overhead for users who don't use global memories.

5. **Project Precedence**: When merging results, project memories appear before user memories at equal relevance, honoring local context.

## Component Design

### Component 1: Domain Configuration (`config.py`)

- **Purpose**: Centralize domain-related paths and settings
- **Responsibilities**:
  - Define `get_user_memories_path()` returning `~/.local/share/memory-plugin/user-memories/`
  - Define `get_user_index_path()` returning `~/.local/share/memory-plugin/user/index.db`
  - Provide `Domain` enum: `USER`, `PROJECT`
- **Interfaces**: Pure functions, no dependencies
- **Technology**: Python stdlib, `pathlib.Path`

### Component 2: Domain-Aware GitOps (`git_ops.py`)

- **Purpose**: Extended git notes operations for user domain
- **Responsibilities**:
  - Initialize bare repo at user-memories path if not exists
  - Support both project (existing) and user repo operations
  - Manage user-memories refs: `refs/notes/mem/{namespace}`
- **Interfaces**:
  - New class method `GitOps.for_domain(domain: Domain) -> GitOps`
  - Factory creates appropriate instance for domain
- **Dependencies**: `config.py` for paths, `git` CLI
- **Technology**: subprocess for git commands

### Component 3: Extended Memory Model (`models.py`)

- **Purpose**: Add domain field to Memory dataclass
- **Responsibilities**:
  - Add `domain: Domain = Domain.PROJECT` field (backward compatible default)
  - Update `Memory.id` format to include domain for user memories: `user:{namespace}:{commit_sha}:{index}`
- **Interfaces**: Frozen dataclass, immutable
- **Technology**: Python dataclasses

### Component 4: Domain-Aware IndexService (`index.py`)

- **Purpose**: Schema migration and domain filtering
- **Responsibilities**:
  - Migrate schema to version 3 adding `domain` column
  - Extend search methods with `domain` filter parameter
  - Support get/insert operations with domain awareness
- **Interfaces**:
  - `search_vector(..., domain: Domain | None = None)`
  - `insert(memory, embedding, domain=Domain.PROJECT)`
- **Dependencies**: SQLite, sqlite-vec
- **Technology**: SQLite DDL for migration

### Component 5: Domain-Aware CaptureService (`capture.py`)

- **Purpose**: Route captures to appropriate domain
- **Responsibilities**:
  - Parse domain from capture request (explicit or marker-detected)
  - Use appropriate GitOps instance for domain
  - Store in correct index with domain field
- **Interfaces**:
  - `capture(..., domain: Domain = Domain.PROJECT)`
- **Dependencies**: `git_ops.py`, `index.py`, `embedding.py`
- **Technology**: Existing service pattern

### Component 6: Domain-Aware RecallService (`recall.py`)

- **Purpose**: Merge search results from both domains
- **Responsibilities**:
  - Query both user and project indices (if user memories exist)
  - Merge results with project memories prioritized
  - Support domain filtering for targeted searches
- **Interfaces**:
  - `search(..., domain: Domain | None = None)` - None searches both
  - `search_user(...)` - convenience for user-only
  - `search_project(...)` - convenience for project-only
- **Dependencies**: Two IndexService instances, EmbeddingService
- **Technology**: Parallel queries, result merging

### Component 7: Extended SignalDetector (`hooks/signal_detector.py`)

- **Purpose**: Detect domain markers in user input
- **Responsibilities**:
  - Recognize `[global]` and `[user]` inline markers
  - Support `▶ global:decision ───` block format
  - Return detected domain with capture signal
- **Interfaces**:
  - Extended `CaptureSignal` model with `domain` field
  - Updated patterns in `SIGNAL_PATTERNS`
- **Technology**: Regex patterns

### Component 8: Extended ContextBuilder (`hooks/context_builder.py`)

- **Purpose**: Merge user and project memories for session context
- **Responsibilities**:
  - Query both domains during SessionStart
  - Build unified XML context with domain labels
  - Apply token budgeting across both domains
- **Interfaces**:
  - `build_context(...)` returns combined context
  - Internal `_build_user_context()` and `_build_project_context()`
- **Dependencies**: RecallService, IndexService (both domains)
- **Technology**: XML generation

### Component 9: User Memory Sync (`sync.py`)

- **Purpose**: Extend sync for user-memories repo
- **Responsibilities**:
  - Sync user index with user-memories git notes
  - Support optional remote sync for user domain
  - Reuse existing refspec fix patterns (from completed spec)
- **Interfaces**:
  - `sync_user_memories(remote: bool = False)`
  - Environment: `HOOK_SESSION_START_FETCH_USER_REMOTE`, `HOOK_STOP_PUSH_USER_REMOTE`
- **Dependencies**: GitOps (user), IndexService (user)
- **Technology**: Git remote operations

## Data Design

### Data Models

```python
# Extended Domain enum
from enum import Enum

class Domain(Enum):
    USER = "user"      # Global, cross-project
    PROJECT = "project"  # Repository-scoped

# Extended Memory model
@dataclass(frozen=True)
class Memory:
    id: str
    commit_sha: str
    namespace: str
    summary: str
    content: str
    timestamp: datetime
    domain: Domain = Domain.PROJECT  # NEW: backward compatible default
    spec: str | None = None
    phase: str | None = None
    tags: tuple[str, ...] = ()
    status: str = "active"
    relates_to: tuple[str, ...] = ()
    repo_path: str | None = None  # existing field

# Extended CaptureSignal
@dataclass(frozen=True)
class CaptureSignal:
    type: SignalType
    match: str
    confidence: float
    context: str
    suggested_namespace: str
    position: int
    domain: Domain = Domain.PROJECT  # NEW: detected domain
```

### Database Schema Migration

```sql
-- Migration from SCHEMA_VERSION 2 to 3
ALTER TABLE memories ADD COLUMN domain TEXT DEFAULT 'project';
CREATE INDEX IF NOT EXISTS idx_memories_domain ON memories(domain);

-- Update search query pattern
SELECT m.*, v.distance
FROM vec_memories v
JOIN memories m ON v.id = m.id
WHERE v.embedding MATCH ?
  AND k = ?
  AND (m.domain = ? OR ? IS NULL)  -- Domain filter
  AND (m.namespace = ? OR ? IS NULL)
  AND (m.spec = ? OR ? IS NULL)
ORDER BY v.distance
LIMIT ?;
```

### Data Flow

```
CAPTURE (User Domain):
  1. SignalDetector detects [global] marker → domain=USER
  2. CaptureService.capture(domain=USER) called
  3. GitOps.for_domain(USER) returns user-memories GitOps
  4. Note appended to user-memories/refs/notes/mem/{namespace}
  5. UserIndexService.insert(memory, embedding, domain=USER)
  6. Commit SHA from user-memories repo stored in memory.id

RECALL (Both Domains):
  1. RecallService.search(query) called (domain=None)
  2. Parallel queries: user_index.search(), project_index.search()
  3. Results merged: project results first, then user results
  4. Deduplication if same content exists in both (keep project)
  5. MemoryResult list returned with domain field populated
```

### Storage Strategy

**User Memories Location**:

```
~/.local/share/memory-plugin/
├── user-memories/           # Bare git repo for user notes
│   ├── refs/
│   │   └── notes/
│   │       └── mem/
│   │           ├── decisions
│   │           ├── learnings
│   │           ├── patterns
│   │           └── ...
│   ├── objects/
│   └── HEAD
├── user/
│   └── index.db             # SQLite index for user memories
├── {repo-hash-1}/
│   └── index.db             # Project index (existing)
└── {repo-hash-2}/
    └── index.db             # Another project index
```

**Memory ID Format**:

- Project: `{namespace}:{commit_sha}:{index}` (existing)
- User: `user:{namespace}:{commit_sha}:{index}` (new prefix)

## API Design

### Capture API

```python
# Extended capture function
def capture(
    namespace: str,
    summary: str,
    content: str,
    *,
    domain: Domain = Domain.PROJECT,  # NEW
    tags: tuple[str, ...] = (),
    spec: str | None = None,
) -> CaptureResult:
    """Capture a memory to the specified domain."""
```

### Recall API

```python
# Extended search function
def search(
    query: str,
    k: int = 10,
    *,
    domain: Domain | None = None,  # NEW: None searches both
    namespace: str | None = None,
    spec: str | None = None,
    min_similarity: float | None = None,
) -> list[MemoryResult]:
    """Search memories, optionally filtered by domain."""

# Convenience methods
def search_user(query: str, **kwargs) -> list[MemoryResult]:
    """Search only user-level memories."""
    return search(query, domain=Domain.USER, **kwargs)

def search_project(query: str, **kwargs) -> list[MemoryResult]:
    """Search only project-level memories."""
    return search(query, domain=Domain.PROJECT, **kwargs)
```

### Hook Integration

```python
# Extended signal patterns
DOMAIN_MARKERS = {
    r"\[global\]": Domain.USER,
    r"\[user\]": Domain.USER,
    r"\[project\]": Domain.PROJECT,
    r"\[local\]": Domain.PROJECT,
}

# Block pattern extension
# ▶ global:decision ─────
# or
# ▶ user:learned ─────
BLOCK_PATTERN_WITH_DOMAIN = re.compile(
    r"▶\s+(?:(global|user|project|local):)?"
    r"(decision|learned|learning|blocker|progress|pattern|remember)\s+─+"
    r"(?:\s+([^\n]+))?"
    r"\n(.*?)"
    r"^─+$",
    re.MULTILINE | re.DOTALL,
)
```

## Integration Points

### Internal Integrations

| System         | Integration Type | Purpose                                             |
| -------------- | ---------------- | --------------------------------------------------- |
| CaptureService | Method extension | Add `domain` parameter to `capture()`               |
| RecallService  | Method extension | Add `domain` parameter to `search()`, merge results |
| IndexService   | Schema migration | Add `domain` column, extend search filters          |
| GitOps         | Factory method   | `for_domain()` creates appropriate instance         |
| SignalDetector | Pattern addition | Recognize `[global]`, `[user]` markers              |
| ContextBuilder | Query extension  | Fetch from both indices, merge context              |
| SyncService    | New method       | `sync_user_memories()` for user repo                |

### External Integrations

| Service    | Integration Type | Purpose                            |
| ---------- | ---------------- | ---------------------------------- |
| Git CLI    | subprocess       | User-memories bare repo operations |
| Remote Git | git push/pull    | Optional sync for user memories    |

## Security Design

### Path Validation

All paths must be validated to prevent traversal attacks:

```python
def validate_user_path(path: Path) -> Path:
    """Ensure path is within allowed user data directory."""
    base = Path.home() / ".local/share/memory-plugin"
    resolved = path.resolve()
    if not resolved.is_relative_to(base):
        raise SecurityError(f"Path {path} outside allowed directory")
    return resolved
```

### Git Command Safety

All git commands use parameterized execution:

```python
# CORRECT: Parameterized
subprocess.run(["git", "notes", "add", "-m", message, commit], ...)

# WRONG: Shell interpolation (never do this)
subprocess.run(f"git notes add -m '{message}' {commit}", shell=True, ...)
```

### Credential Handling

- No credentials stored by plugin
- Remote sync uses existing git credential helpers
- No SSH key management

## Performance Considerations

### Expected Load

- User memories: 1-10,000 memories per user
- Queries per session: 10-50 searches
- Concurrent sessions: 1 (single-user tool)

### Performance Targets

| Metric                     | Target       | Rationale                         |
| -------------------------- | ------------ | --------------------------------- |
| User index initialization  | <100ms       | One-time lazy load per session    |
| Dual-domain search         | <200ms       | Parallel queries, merge overhead  |
| SessionStart context build | <500ms       | Already budgeted in existing code |
| User memory sync           | <5s for 1000 | Background, not blocking          |

### Optimization Strategies

1. **Lazy User Index**: Only initialize user index when first accessed
2. **Parallel Queries**: Search user and project indices concurrently
3. **Result Caching**: Cache user search results within session (they change less frequently)
4. **Index Pre-warming**: Load user index during SessionStart async

## Reliability & Operations

### Failure Modes

| Failure                    | Impact                      | Recovery                           |
| -------------------------- | --------------------------- | ---------------------------------- |
| User-memories repo missing | Cannot access user memories | Auto-create on first capture       |
| User index corruption      | Search fails                | Rebuild from git notes via sync    |
| Remote sync fails          | User memories not synced    | Retry on next session, log warning |
| Schema migration fails     | Index unusable              | Delete and rebuild from git notes  |

### Graceful Degradation

```python
def _get_user_index(self) -> IndexService | None:
    """Get user index, returning None if unavailable."""
    try:
        if not self._user_index_path.exists():
            return None
        return IndexService(self._user_index_path)
    except Exception as e:
        logger.warning("User index unavailable: %s", e)
        return None

def search(self, query: str, domain: Domain | None = None) -> list[MemoryResult]:
    """Search with graceful fallback if user index unavailable."""
    results = []

    if domain in (None, Domain.PROJECT):
        results.extend(self._search_project(query))

    if domain in (None, Domain.USER):
        user_index = self._get_user_index()
        if user_index:
            results.extend(self._search_user(query, user_index))

    return self._merge_results(results)
```

## Testing Strategy

### Unit Testing

- Test `Domain` enum and path functions
- Test `GitOps.for_domain()` factory
- Test schema migration to v3
- Test domain filtering in IndexService
- Test domain marker detection in SignalDetector

### Integration Testing

- Test capture to user domain stores in correct repo
- Test recall merges both domains correctly
- Test project memories override user on conflict
- Test SessionStart context includes both domains

### End-to-End Testing

- Create memory with `[global]` marker, verify in user index
- Switch projects, verify user memory still accessible
- Configure remote, verify sync round-trip

## Deployment Considerations

### Migration Path

1. **Schema Migration**: Run automatically on IndexService initialization
2. **Backward Compatibility**: Default `domain=PROJECT` ensures existing code works
3. **Progressive Adoption**: Users opt-in to global memories via markers

### Configuration

New environment variables:

| Variable                               | Description                              | Default |
| -------------------------------------- | ---------------------------------------- | ------- |
| `HOOK_SESSION_START_FETCH_USER_REMOTE` | Fetch user memories from remote on start | `false` |
| `HOOK_STOP_PUSH_USER_REMOTE`           | Push user memories to remote on stop     | `false` |
| `USER_MEMORIES_REMOTE`                 | Git remote URL for user memories         | (none)  |

### Rollback Plan

1. Set all domain env vars to `false`
2. User memories become dormant but not deleted
3. Remove domain markers from prompts
4. System operates in project-only mode
