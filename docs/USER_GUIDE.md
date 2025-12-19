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

### `/memory capture <namespace> <summary>`

Capture a memory in the current conversation.

```
/memory capture decisions Chose React over Vue for the frontend
```

### `/memory recall <query>`

Search for relevant memories.

```
/memory recall database migration strategy
```

### `/memory search <query>`

Full-text keyword search.

```
/memory search PostgreSQL
```

### `/memory sync`

Synchronize the index with git notes.

```
/memory sync          # Incremental
/memory sync --full   # Full rebuild
```

### `/memory status`

Show index statistics and health.

```
/memory status
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

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PLUGIN_DATA_DIR` | Data directory path | `~/.local/share/memory-plugin/` |
| `MEMORY_PLUGIN_GIT_NAMESPACE` | Git notes ref | `refs/notes/mem` |
| `MEMORY_PLUGIN_EMBEDDING_MODEL` | Model name | `all-MiniLM-L6-v2` |
| `MEMORY_PLUGIN_AUTO_CAPTURE` | Auto-capture hook | `false` |

### Custom Data Directory

```bash
export MEMORY_PLUGIN_DATA_DIR=/path/to/custom/data
```

### Storage Locations

- **Index database**: `$DATA_DIR/index.db` (SQLite + sqlite-vec)
- **Embedding model**: `$DATA_DIR/models/` (downloaded once)
- **Lock file**: `$DATA_DIR/.capture.lock`

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

## Hooks Integration

The memory plugin includes hooks that integrate with Claude Code's hook system for automatic memory context injection and capture assistance.

### Overview

Three hooks are available:

| Hook | Event | Purpose | Default |
|------|-------|---------|---------|
| SessionStart | Session begins | Inject project memories | Enabled |
| UserPromptSubmit | User sends prompt | Detect capture signals | Disabled |
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
- **AUTO**: High-confidence signals (≥95%) are captured automatically
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

- `hooks/session_start.py` - SessionStart event handler
- `hooks/user_prompt.py` - UserPromptSubmit event handler
- `hooks/stop.py` - Stop event handler
- `hooks/hooks.json` - Hook registration configuration

### Troubleshooting Hooks

**Hook not triggering:**
1. Check if hooks are enabled: `echo $HOOK_ENABLED`
2. Verify hook registration in `hooks/hooks.json`
3. Enable debug mode: `export HOOK_DEBUG=true`

**Slow session start:**
1. Reduce budget: `export HOOK_SESSION_START_BUDGET_MODE=minimal`
2. Check index size with `/memory status`
3. Run incremental reindex: `/memory sync`

**Too many capture suggestions:**
1. Increase confidence threshold: `export HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE=0.8`
2. Disable auto-capture: `export HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD=1.0`
3. Disable hook entirely: `export HOOK_USER_PROMPT_ENABLED=false`

---

## Next Steps

- See [Developer Guide](DEVELOPER_GUIDE.md) for API reference
- Check [CHANGELOG](../CHANGELOG.md) for version history
