# User Guide

This guide covers how to use `git-notes-memory` as both a Python library and a Claude Code plugin.

## Table of Contents

- [Concepts](#concepts)
- [Installation](#installation)
- [Python Library Usage](#python-library-usage)
- [Claude Code Plugin](#claude-code-plugin)
- [Memory Namespaces](#memory-namespaces)
- [Searching Memories](#searching-memories)
- [Configuration](#configuration)
- [Hooks Integration](#hooks-integration)
- [Debugging, Discovery & Memory Review](#debugging-discovery--memory-review)
- [Troubleshooting](#troubleshooting)

---

## Concepts

### What are Memories?

Memories are structured pieces of context attached to git commits. They capture:

- **Decisions** made during development
- **Learnings** and technical insights
- **Progress** milestones
- **Blockers** and their resolutions
- **Research** findings

### How Storage Works

Memories are stored as **git notes** - a built-in git feature that attaches metadata to commits without modifying commit history. This means:

- Memories sync when you `git push`/`git pull`
- No impact on commit SHAs or history
- Separate from code changes
- Supports team collaboration

### Semantic Search

The library creates vector embeddings of your memories using sentence-transformers. This enables:

- Finding memories by meaning, not just keywords
- "What did we decide about caching?" finds memories about Redis, Memcached, etc.
- Similarity scoring for relevance ranking

---

## Installation

### Requirements

- Python 3.11 or higher
- Git 2.25 or higher
- ~500MB disk space for the embedding model (downloaded on first use)

### Install via pip

```bash
pip install git-notes-memory
```

### Install via uv (recommended)

```bash
uv add git-notes-memory
```

### Verify Installation

```python
from git_notes_memory import get_capture_service, get_recall_service
print("Installation successful!")
```

---

## Python Library Usage

### Capturing Memories

```python
from git_notes_memory import get_capture_service

# Get the capture service (singleton)
capture = get_capture_service()

# Basic capture
result = capture.capture(
    namespace="decisions",
    summary="Chose PostgreSQL over SQLite",
    content="""
    ## Context
    Need persistent storage for user data.

    ## Decision
    PostgreSQL for production, SQLite for testing.

    ## Rationale
    - Better concurrent write support
    - Rich query capabilities
    - Team familiarity
    """
)

print(f"Captured memory: {result.memory_id}")
print(f"At commit: {result.commit}")
```

### Capture with Metadata

```python
result = capture.capture(
    namespace="decisions",
    summary="API authentication strategy",
    content="Using JWT with refresh tokens...",
    spec="AUTH-2024-001",           # Link to a spec/project
    tags=["security", "api"],       # Searchable tags
    phase="implementation",         # Development phase
    relates_to=["ARCH-001"],        # Related memories/specs
)
```

### Namespace-Specific Captures

```python
# Capture a blocker
capture.capture_blocker(
    summary="CI pipeline timeout",
    content="Tests exceed 30-minute limit...",
    resolution="Split into parallel jobs"
)

# Capture a learning
capture.capture_learning(
    summary="pytest-asyncio fixture scope",
    content="Use session scope for expensive async fixtures..."
)

# Capture a decision (ADR style)
capture.capture_decision(
    summary="Use pydantic for validation",
    content="## Context\n...\n## Decision\n...",
    spec="PROJ-001"
)
```

### Recalling Memories

```python
from git_notes_memory import get_recall_service

recall = get_recall_service()

# Semantic search
results = recall.search("authentication strategy")
for mem in results:
    print(f"[{mem.similarity:.2f}] {mem.memory.summary}")

# Filter by namespace
decisions = recall.search(
    "database choice",
    namespace="decisions",
    k=5  # Return top 5 results
)

# Filter by spec
project_memories = recall.search(
    "performance issues",
    spec="PROJ-001"
)

# Set minimum similarity threshold
relevant = recall.search(
    "caching strategy",
    min_similarity=0.5  # Only results with >50% similarity
)
```

### Text Search (Keyword-Based)

```python
# Full-text search (FTS5) instead of semantic
results = recall.search_text("PostgreSQL", limit=10)
```

### Getting Specific Memories

```python
# Get by ID
memory = recall.get("decisions:abc1234:0")

# Get batch
memories = recall.get_batch(["decisions:abc1234:0", "learnings:def5678:1"])

# Get all in namespace
all_decisions = recall.get_by_namespace("decisions")

# Get for specific spec
spec_memories = recall.get_by_spec("PROJ-001")
```

### Proactive Recall

```python
# Get relevant memories for current context
context = """
Working on adding Redis caching to the API layer.
Need to decide on cache invalidation strategy.
"""

suggestions = recall.proactive_recall(context, max_suggestions=5)
for mem in suggestions:
    print(f"Relevant: {mem.summary}")
```

### Hydration Levels

Control how much data is loaded:

```python
from git_notes_memory import HydrationLevel

# Summary only (fast, minimal)
light = recall.hydrate(memory_id, level=HydrationLevel.SUMMARY)

# Full content
full = recall.hydrate(memory_id, level=HydrationLevel.FULL)

# With file snapshots from commit
detailed = recall.hydrate(memory_id, level=HydrationLevel.FILES)
```

### Index Management

```python
from git_notes_memory import get_sync_service

sync = get_sync_service()

# Full reindex (rebuilds from scratch)
count = sync.reindex(full=True)
print(f"Indexed {count} memories")

# Incremental sync
count = sync.reindex(full=False)

# Verify consistency
result = sync.verify_consistency()
if not result.is_consistent:
    print(f"Missing: {result.missing_in_index}")
    print(f"Orphaned: {result.orphaned_in_index}")

    # Auto-repair
    sync.repair(result)
```

---

## Claude Code Plugin

When installed as a Claude Code plugin, these slash commands are available:

### `/memory:capture <namespace> <summary>`

Capture a memory in the current conversation.

```
/memory:capture decisions Chose React over Vue for the frontend
```

### `/memory:recall <query>`

Search for relevant memories.

```
/memory:recall database migration strategy
```

### `/memory:search <query>`

Advanced search with filtering options.

```
/memory:search PostgreSQL --type=text --namespace=decisions
```

### `/memory:sync`

Synchronize the index with git notes.

```
/memory:sync          # Incremental
/memory:sync full     # Full rebuild
/memory:sync verify   # Check consistency
/memory:sync repair   # Fix inconsistencies
```

### `/memory:status`

Show index statistics and health.

```
/memory:status
/memory:status --verbose
```

Output:
```
Memory Index Status
===================
Total Memories: 47
By Namespace:
  decisions: 12
  learnings: 15
  progress: 8
  blockers: 5
  research: 7

Index Size: 2.3 MB
Last Sync: 2024-01-15 10:30:00
```

---

## Memory Namespaces

The system supports 10 predefined namespaces, each for a specific purpose:

| Namespace | Purpose | Example |
|-----------|---------|---------|
| `inception` | Problem statements, scope, success criteria | "Building a CLI for ADR management" |
| `elicitation` | Requirements clarifications, constraints | "Must support Git 2.25+" |
| `research` | External findings, technology evaluations | "Compared sqlite-vec vs pgvector" |
| `decisions` | Architecture Decision Records | "Chose YAML over JSON for config" |
| `progress` | Task completions, milestones | "Completed Phase 1: Foundation" |
| `blockers` | Obstacles and resolutions | "CI timeout - fixed with parallelization" |
| `reviews` | Code review findings | "Security: validate all git refs" |
| `learnings` | Technical insights, patterns | "pytest fixtures need session scope" |
| `retrospective` | Post-mortems | "MVP delivered, 90% coverage achieved" |
| `patterns` | Cross-project generalizations | "Always use frozen dataclasses" |

---

## Searching Memories

### Semantic Search Tips

Semantic search finds memories by meaning. Tips for better results:

1. **Use natural language**: "How did we handle user authentication?" works better than "auth"
2. **Include context**: "caching for API responses" beats just "caching"
3. **Combine with filters**: Use `namespace=` and `spec=` to narrow scope

### Search Operators

```python
# Namespace filter
recall.search("performance", namespace="learnings")

# Spec filter
recall.search("security", spec="AUTH-2024")

# Combined
recall.search("database", namespace="decisions", spec="PROJ-001")

# Similarity threshold
recall.search("api design", min_similarity=0.6)

# Result limit
recall.search("testing strategy", k=3)
```

---

## Configuration

### Environment Variables

All environment variables are optional. Defaults are shown below.

#### Core Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PLUGIN_DATA_DIR` | Data directory path | `~/.local/share/memory-plugin/` |
| `MEMORY_PLUGIN_GIT_NAMESPACE` | Git notes ref | `refs/notes/mem` |
| `MEMORY_PLUGIN_EMBEDDING_MODEL` | Model name | `all-MiniLM-L6-v2` |
| `MEMORY_PLUGIN_AUTO_CAPTURE` | Auto-capture hook | `false` |

#### Hook Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_ENABLED` | Master switch for hooks | `true` |
| `HOOK_SESSION_START_ENABLED` | Enable SessionStart hook | `true` |
| `HOOK_USER_PROMPT_ENABLED` | Enable UserPromptSubmit hook | `false` |
| `HOOK_POST_TOOL_USE_ENABLED` | Enable PostToolUse hook | `true` |
| `HOOK_PRE_COMPACT_ENABLED` | Enable PreCompact hook | `true` |
| `HOOK_STOP_ENABLED` | Enable Stop hook | `true` |
| `HOOK_DEBUG` | Enable debug logging | `false` |
| `HOOK_TIMEOUT` | Hook timeout in seconds | `30` |

#### SessionStart Hook Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_SESSION_START_BUDGET_MODE` | Budget mode: adaptive, fixed, full, minimal | `adaptive` |
| `HOOK_SESSION_START_FIXED_BUDGET` | Fixed budget (when mode=fixed) | `1000` |
| `HOOK_SESSION_START_MAX_BUDGET` | Maximum budget cap | `3000` |
| `HOOK_SESSION_START_INCLUDE_GUIDANCE` | Include response guidance in context | `true` |
| `HOOK_SESSION_START_GUIDANCE_DETAIL` | Guidance detail: minimal, standard, detailed | `standard` |

#### Capture Detection Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE` | Minimum confidence for suggestions | `0.7` |
| `HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD` | Threshold for auto-capture | `0.95` |
| `HOOK_CAPTURE_DETECTION_NOVELTY_THRESHOLD` | Minimum novelty score | `0.3` |

### Custom Data Directory

```bash
export MEMORY_PLUGIN_DATA_DIR=/path/to/custom/data
```

### Storage Locations

- **Index database**: `$DATA_DIR/index.db` (SQLite + sqlite-vec)
- **Embedding model**: `$DATA_DIR/models/` (downloaded once)
- **Lock file**: `$DATA_DIR/.capture.lock`

### Using .env Files

You can create a `.env` file in your project root. See `.env.example` for all available options:

```bash
# Copy the example
cp .env.example .env

# Edit as needed
vim .env
```

---

## Hooks Integration

The memory plugin includes hooks that integrate with Claude Code's hook system for automatic memory context injection and capture assistance.

### Overview

Five hooks are available:

| Hook | Event | Purpose | Default |
|------|-------|---------|---------|
| SessionStart | Session begins | Inject project memories and response guidance | Enabled |
| UserPromptSubmit | User sends prompt | Detect capture signals and inline markers | Disabled |
| PostToolUse | After Read/Write/Edit | Surface related memories for files | Enabled |
| PreCompact | Before context compaction | Auto-capture high-confidence content | Enabled |
| Stop | Session ends | Prompt for uncaptured content, sync index | Enabled |

### SessionStart Hook

Automatically injects relevant memories at the start of each Claude Code session.

**What it does:**
1. Detects the current project (from git repo, package.json, pyproject.toml)
2. Identifies the active spec (from CLAUDE.md or docs/spec/active/)
3. Builds context within a token budget
4. Injects XML-formatted memory context

**Context includes:**
- Working memory: pending actions, recent decisions, active blockers
- Semantic context: learnings and patterns relevant to the project
- Available commands: quick reference for memory operations

**Configuration:**

```bash
# Disable SessionStart hook
export HOOK_SESSION_START_ENABLED=false

# Budget modes: adaptive (default), fixed, full, minimal
export HOOK_SESSION_START_BUDGET_MODE=adaptive

# Fixed budget (when mode=fixed)
export HOOK_SESSION_START_FIXED_BUDGET=1000

# Maximum budget cap
export HOOK_SESSION_START_MAX_BUDGET=3000
```

### UserPromptSubmit Hook

Analyzes user prompts for capture-worthy content and suggests or auto-captures memories.

**What it detects:**
- **Decisions**: "I decided to use...", "we're going with..."
- **Learnings**: "I learned that...", "TIL:", "turns out..."
- **Blockers**: "blocked by...", "stuck on...", "can't because..."
- **Progress**: "completed...", "finished...", "done with..."

**Capture actions:**
- **AUTO**: High-confidence signals (>=95%) are captured automatically
- **SUGGEST**: Medium-confidence signals (70-95%) show suggestions
- **SKIP**: Low-confidence or duplicate content is ignored

**Configuration:**

```bash
# Enable signal detection (disabled by default)
export HOOK_USER_PROMPT_ENABLED=true

# Minimum confidence for suggestions (0.0-1.0)
export HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE=0.7

# Threshold for auto-capture (0.0-1.0)
export HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD=0.95

# Novelty threshold (how different from existing memories)
export HOOK_CAPTURE_DETECTION_NOVELTY_THRESHOLD=0.3
```

### PostToolUse Hook

Surfaces related memories after file operations to provide contextual information.

**What it does:**
1. Triggers after Read, Write, Edit, or MultiEdit operations
2. Extracts domain terms from the file path (e.g., `src/auth/jwt.py` → auth, jwt)
3. Searches for memories related to those domains
4. Injects relevant memories as additional context

**Example output:**
When you read or edit `src/auth/oauth_handler.py`, the hook may inject:
```xml
<related_memories>
  <memory namespace="decisions" confidence="0.82">
    Chose OAuth 2.0 with PKCE for authentication flow
  </memory>
  <memory namespace="learnings" confidence="0.75">
    Token refresh must happen before expiry to avoid race conditions
  </memory>
</related_memories>
```

**Configuration:**

```bash
# Disable PostToolUse hook
export HOOK_POST_TOOL_USE_ENABLED=false

# Minimum similarity threshold (0.0-1.0)
export HOOK_POST_TOOL_USE_MIN_SIMILARITY=0.6

# Maximum memories to inject
export HOOK_POST_TOOL_USE_MAX_RESULTS=3

# Timeout in seconds
export HOOK_POST_TOOL_USE_TIMEOUT=5
```

### PreCompact Hook

Auto-captures high-confidence content before Claude Code compacts the context.

**What it does:**
1. Triggers before context compaction (automatic or manual)
2. Analyzes the conversation transcript for uncaptured signals
3. Filters to high-confidence items (≥85% by default)
4. Auto-captures up to 3 memories to prevent information loss
5. Reports captures via stderr (visible in terminal)

**Example stderr output:**
```
Auto-captured 2 memories before compaction:
  - [decisions] Chose PostgreSQL for JSONB support
  - [learnings] pytest fixtures need session scope for DB connections
```

**Configuration:**

```bash
# Disable PreCompact hook
export HOOK_PRE_COMPACT_ENABLED=false

# Enable auto-capture (captures without prompting)
export HOOK_PRE_COMPACT_AUTO_CAPTURE=true

# Enable suggestion mode (prompts before capturing)
export HOOK_PRE_COMPACT_PROMPT_FIRST=false

# Minimum confidence for auto-capture (0.0-1.0)
export HOOK_PRE_COMPACT_MIN_CONFIDENCE=0.85

# Maximum memories to auto-capture
export HOOK_PRE_COMPACT_MAX_CAPTURES=3

# Timeout in seconds
export HOOK_PRE_COMPACT_TIMEOUT=15
```

### Stop Hook

Performs session-end cleanup and memory assistance.

**What it does:**
1. Analyzes session transcript for uncaptured memorable content
2. Prompts user with suggestions if valuable content found
3. Synchronizes the memory search index

**Configuration:**

```bash
# Disable Stop hook
export HOOK_STOP_ENABLED=false

# Disable uncaptured content prompts
export HOOK_STOP_PROMPT_UNCAPTURED=false

# Disable index sync on session end
export HOOK_STOP_SYNC_INDEX=false
```

### Global Hook Configuration

```bash
# Master switch - disable all hooks
export HOOK_ENABLED=false

# Enable debug logging to stderr
export HOOK_DEBUG=true

# Hook timeout in seconds (default: 30)
export HOOK_TIMEOUT=30
```

### Hook Installation

The hooks are installed automatically when you configure the plugin in Claude Code. The hook scripts are in the `hooks/` directory:

- `hooks/sessionstart.py` - SessionStart event handler
- `hooks/userpromptsubmit.py` - UserPromptSubmit event handler
- `hooks/posttooluse.py` - PostToolUse event handler
- `hooks/precompact.py` - PreCompact event handler
- `hooks/stop.py` - Stop event handler
- `hooks/hooks.json` - Hook registration configuration

### Inline Capture Markers

You can capture memories inline in your prompts using special markers:

```
[remember] pytest fixtures with scope="module" persist across tests
[capture] We decided to use PostgreSQL for JSONB support
@memory The API rate limit is 1000 requests per minute
```

These markers are processed by the UserPromptSubmit hook when enabled.

### Troubleshooting Hooks

**Hook not triggering:**
1. Check if hooks are enabled: `echo $HOOK_ENABLED`
2. Verify hook registration in `hooks/hooks.json`
3. Enable debug mode: `export HOOK_DEBUG=true`

**Slow session start:**
1. Reduce budget: `export HOOK_SESSION_START_BUDGET_MODE=minimal`
2. Check index size with `/memory:status`
3. Run incremental reindex: `/memory:sync`

**Too many capture suggestions:**
1. Increase confidence threshold: `export HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE=0.8`
2. Disable auto-capture: `export HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD=1.0`
3. Disable hook entirely: `export HOOK_USER_PROMPT_ENABLED=false`

---

## Debugging, Discovery & Memory Review

This section covers how to explore, audit, and debug your memory system.

### Discovering What Memories Exist

**Quick status check:**
```bash
# Plugin command
/memory:status --verbose

# Python
from git_notes_memory import get_sync_service
sync = get_sync_service()
stats = sync.get_stats()
print(f"Total memories: {stats.total_count}")
print(f"Namespaces: {stats.by_namespace}")
```

**List memories by namespace:**
```python
from git_notes_memory import get_recall_service

recall = get_recall_service()

# Get all decisions
decisions = recall.get_by_namespace("decisions")
for mem in decisions:
    print(f"{mem.id}: {mem.summary}")

# Get all blockers (to check unresolved issues)
blockers = recall.get_by_namespace("blockers")
for mem in blockers:
    status = "Resolved" if mem.status == "resolved" else "ACTIVE"
    print(f"[{status}] {mem.summary}")
```

**Browse by spec/project:**
```python
# Get all memories for a specific spec
spec_memories = recall.get_by_spec("PROJ-001")
print(f"Found {len(spec_memories)} memories for PROJ-001")
```

### Searching Strategies

**Semantic search (by meaning):**
```python
# Find decisions about databases without knowing exact keywords
results = recall.search("persistent storage choice")

# Find learnings about testing
results = recall.search("how to test async code", namespace="learnings")

# Find patterns applicable across projects
results = recall.search("error handling best practices", namespace="patterns")
```

**Text search (exact keywords):**
```python
# Find exact term matches
results = recall.search_text("PostgreSQL")
results = recall.search_text("pytest fixture")
```

**Combined strategies:**
```python
# First try semantic, then fall back to text
semantic = recall.search("database migration", namespace="decisions", k=5)
if not semantic:
    text = recall.search_text("migration", limit=10)
```

### Reviewing Memory Quality

**Check for duplicates:**
```python
from git_notes_memory import get_recall_service

recall = get_recall_service()

# Get all memories
all_memories = []
for ns in ["decisions", "learnings", "blockers", "patterns"]:
    all_memories.extend(recall.get_by_namespace(ns))

# Check each for similar existing memories
for mem in all_memories:
    similar = recall.search(mem.summary, k=3, min_similarity=0.8)
    if len(similar) > 1:  # More than self
        print(f"Potential duplicates for: {mem.summary}")
        for s in similar:
            if s.memory.id != mem.id:
                print(f"  - [{s.similarity:.2f}] {s.memory.summary}")
```

**Audit memory content:**
```python
from git_notes_memory import HydrationLevel

# Full content review
memory = recall.get("decisions:abc1234:0")
hydrated = recall.hydrate(memory.id, level=HydrationLevel.FULL)
print(f"Summary: {hydrated.summary}")
print(f"Content:\n{hydrated.content}")
print(f"Tags: {hydrated.tags}")
print(f"Created: {hydrated.timestamp}")
```

**Check namespace distribution:**
```python
from collections import Counter

all_memories = []
for ns in recall.get_all_namespaces():
    all_memories.extend(recall.get_by_namespace(ns))

distribution = Counter(m.namespace for m in all_memories)
print("Memory distribution:")
for ns, count in distribution.most_common():
    print(f"  {ns}: {count}")
```

### Debugging Memory Issues

**Enable debug logging:**
```bash
# For hooks
export HOOK_DEBUG=true

# Check hook output in stderr
```

**Verify git notes storage:**
```bash
# List all memory notes
git notes --ref=refs/notes/mem list

# View a specific note
git notes --ref=refs/notes/mem/decisions show HEAD

# Check notes refs exist
git for-each-ref refs/notes/mem
```

**Check index consistency:**
```python
from git_notes_memory import get_sync_service

sync = get_sync_service()

# Verify index matches git notes
result = sync.verify_consistency()
print(f"Consistent: {result.is_consistent}")
print(f"In git but not index: {len(result.missing_in_index)}")
print(f"In index but not git: {len(result.orphaned_in_index)}")

# Auto-repair if needed
if not result.is_consistent:
    sync.repair(result)
    print("Repaired!")
```

**Inspect raw git notes:**
```bash
# See what's actually stored
git notes --ref=refs/notes/mem/decisions list | while read sha commit; do
    echo "=== Note on $commit ==="
    git notes --ref=refs/notes/mem/decisions show $commit
done
```

**Check embedding quality:**
```python
from git_notes_memory import get_embedding_service

embed = get_embedding_service()

# Test embedding generation
test_text = "PostgreSQL database migration"
embedding = embed.embed(test_text)
print(f"Embedding dimensions: {len(embedding)}")
print(f"First 5 values: {embedding[:5]}")

# Test similarity
text1 = "database schema migration"
text2 = "PostgreSQL table changes"
text3 = "completely unrelated topic"

e1, e2, e3 = embed.embed(text1), embed.embed(text2), embed.embed(text3)

def cosine_similarity(a, b):
    import numpy as np
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

print(f"Similarity (related): {cosine_similarity(e1, e2):.3f}")
print(f"Similarity (unrelated): {cosine_similarity(e1, e3):.3f}")
```

### Memory Maintenance Tasks

**Full reindex (rebuild search index):**
```python
from git_notes_memory import get_sync_service

sync = get_sync_service()
count = sync.reindex(full=True)
print(f"Reindexed {count} memories")
```

**Clean up orphaned index entries:**
```python
result = sync.verify_consistency()
if result.orphaned_in_index:
    print(f"Removing {len(result.orphaned_in_index)} orphaned entries")
    sync.repair(result)
```

**Export memories for backup:**
```python
import json
from git_notes_memory import get_recall_service, HydrationLevel

recall = get_recall_service()
export = []

for ns in ["decisions", "learnings", "blockers", "patterns", "progress"]:
    for mem in recall.get_by_namespace(ns):
        hydrated = recall.hydrate(mem.id, level=HydrationLevel.FULL)
        export.append({
            "id": mem.id,
            "namespace": mem.namespace,
            "summary": mem.summary,
            "content": hydrated.content,
            "tags": list(mem.tags),
            "timestamp": mem.timestamp.isoformat(),
        })

with open("memories_backup.json", "w") as f:
    json.dump(export, f, indent=2)
print(f"Exported {len(export)} memories")
```

### Common Debugging Scenarios

**Memory not appearing in search:**
1. Check if memory was captured: `git notes --ref=refs/notes/mem list`
2. Verify it's indexed: `/memory:sync verify`
3. Run reindex: `/memory:sync full`
4. Check namespace filter in search

**Duplicate memories:**
1. Check novelty threshold: `HOOK_CAPTURE_DETECTION_NOVELTY_THRESHOLD`
2. Run duplicate detection script (above)
3. Manually remove duplicates from git notes

**Slow search performance:**
1. Check index size: `/memory:status`
2. Reduce result count: `k=5` instead of `k=20`
3. Add namespace filter to narrow scope
4. Consider rebuilding index: `/memory:sync full`

**Hook not capturing:**
1. Verify hook enabled: `echo $HOOK_USER_PROMPT_ENABLED`
2. Check confidence thresholds
3. Enable debug: `export HOOK_DEBUG=true`
4. Review debug output in stderr

---

## Troubleshooting

### "No memories found"

1. Check if memories are indexed: `sync.verify_consistency()`
2. Run full reindex: `sync.reindex(full=True)`
3. Verify git notes exist: `git notes --ref=mem list`

### "Model download slow"

The embedding model (~90MB) downloads on first use. After that, it's cached locally.

### "Permission denied on lock file"

Another process may be capturing. Wait or delete `.capture.lock` manually.

### "Index corruption"

Run a full reindex to rebuild:

```python
from git_notes_memory import get_sync_service
sync = get_sync_service()
sync.reindex(full=True)
```

### "Git notes not syncing"

Git notes require explicit push/pull:

```bash
git push origin refs/notes/mem
git fetch origin refs/notes/mem:refs/notes/mem
```

---

## Next Steps

- See [Developer Guide](DEVELOPER_GUIDE.md) for API reference
- Check [CHANGELOG](../CHANGELOG.md) for version history
