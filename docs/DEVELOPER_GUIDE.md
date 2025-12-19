# Developer Guide

Complete API reference for `git-notes-memory`.

## Table of Contents

- [Package Structure](#package-structure)
- [Core Services](#core-services)
  - [CaptureService](#captureservice)
  - [RecallService](#recallservice)
  - [SyncService](#syncservice)
- [Models](#models)
- [Exceptions](#exceptions)
- [Utilities](#utilities)
- [Configuration](#configuration)
- [Testing](#testing)
- [Contributing](#contributing)

---

## Package Structure

```
git_notes_memory/
├── __init__.py         # Public API exports
├── capture.py          # CaptureService
├── recall.py           # RecallService
├── sync.py             # SyncService
├── index.py            # IndexService (SQLite + sqlite-vec)
├── embedding.py        # EmbeddingService
├── git_ops.py          # Git operations wrapper
├── note_parser.py      # YAML front matter parsing
├── models.py           # Data models
├── config.py           # Configuration constants
├── exceptions.py       # Exception hierarchy
├── utils.py            # Utility functions
├── search.py           # SearchOptimizer
├── patterns.py         # PatternManager
├── lifecycle.py        # LifecycleManager
└── hooks/              # Hook handler modules
    ├── session_start_handler.py
    ├── user_prompt_handler.py
    ├── stop_handler.py
    └── services/       # Hook support services
        ├── context_builder.py
        ├── project_detector.py
        ├── signal_detector.py
        ├── novelty_checker.py
        ├── capture_decider.py
        └── session_analyzer.py
```

---

## Core Services

### CaptureService

Handles memory capture with concurrency-safe file locking.

#### Factory Function

```python
from git_notes_memory import get_capture_service

capture = get_capture_service(repo_path=None)
```

**Parameters:**
- `repo_path` (Path | None): Git repository path. Defaults to current directory.

**Returns:** CaptureService singleton instance.

#### Methods

##### `capture()`

Capture a memory to git notes with optional indexing.

```python
def capture(
    self,
    namespace: str,
    summary: str,
    content: str,
    *,
    spec: str | None = None,
    tags: list[str] | tuple[str, ...] | None = None,
    phase: str | None = None,
    status: str = "active",
    relates_to: list[str] | tuple[str, ...] | None = None,
    commit: str = "HEAD",
    skip_lock: bool = False,
) -> CaptureResult
```

**Parameters:**
- `namespace` (str): Memory category. Must be one of: `inception`, `elicitation`, `research`, `decisions`, `progress`, `blockers`, `reviews`, `learnings`, `retrospective`, `patterns`
- `summary` (str): One-line summary (max 100 characters)
- `content` (str): Full memory content (max 100KB)
- `spec` (str | None): Optional spec/project identifier
- `tags` (list[str] | None): Optional searchable tags
- `phase` (str | None): Optional development phase
- `status` (str): Memory status. Default: "active"
- `relates_to` (list[str] | None): Optional related memory/spec IDs
- `commit` (str): Git commit to attach memory to. Default: "HEAD"
- `skip_lock` (bool): Skip file locking (for internal use). Default: False

**Returns:** `CaptureResult` with memory_id, commit, namespace, and success status.

**Raises:**
- `CaptureError`: If capture fails
- `StorageError`: If git operations fail
- `ValueError`: If namespace invalid or content too large

**Example:**
```python
result = capture.capture(
    namespace="decisions",
    summary="Use frozen dataclasses for immutability",
    content="All models use @dataclass(frozen=True)...",
    spec="PROJ-001",
    tags=["python", "design"],
)
```

##### Namespace-Specific Methods

Convenience methods for common namespaces:

```python
# Inception (problem statements)
capture.capture_inception(summary, content, spec=None)

# Elicitation (requirements)
capture.capture_elicitation(summary, content, spec=None)

# Research (findings)
capture.capture_research(summary, content, spec=None)

# Decisions (ADRs)
capture.capture_decision(summary, content, spec=None)

# Progress (milestones)
capture.capture_progress(summary, content, spec=None)

# Blockers (obstacles)
capture.capture_blocker(summary, content, resolution=None)

# Reviews (code review)
capture.capture_review(summary, content, category=None, severity=None)

# Learnings (insights)
capture.capture_learning(summary, content)

# Retrospective (post-mortems)
capture.capture_retrospective(summary, content, outcome=None)
```

##### `capture_batch()`

Capture multiple memories atomically.

```python
def capture_batch(
    self,
    memories: list[dict[str, Any]],
) -> CaptureAccumulator
```

**Parameters:**
- `memories` (list[dict]): List of memory dicts with same keys as `capture()`

**Returns:** `CaptureAccumulator` with success/failure counts.

---

### RecallService

Handles memory retrieval with semantic search.

#### Factory Function

```python
from git_notes_memory import get_recall_service

recall = get_recall_service(repo_path=None)
```

#### Methods

##### `search()`

Semantic search using vector embeddings.

```python
def search(
    self,
    query: str,
    k: int = 10,
    *,
    namespace: str | None = None,
    spec: str | None = None,
    min_similarity: float | None = None,
) -> list[MemoryResult]
```

**Parameters:**
- `query` (str): Natural language search query
- `k` (int): Maximum results to return. Default: 10
- `namespace` (str | None): Filter by namespace
- `spec` (str | None): Filter by spec identifier
- `min_similarity` (float | None): Minimum similarity threshold (0.0-1.0)

**Returns:** List of `MemoryResult` with memory and similarity score.

**Example:**
```python
results = recall.search(
    "authentication flow",
    k=5,
    namespace="decisions",
    min_similarity=0.5,
)
for r in results:
    print(f"{r.similarity:.2f}: {r.memory.summary}")
```

##### `search_text()`

Full-text keyword search (FTS5).

```python
def search_text(
    self,
    query: str,
    limit: int = 10,
    *,
    namespace: str | None = None,
    spec: str | None = None,
) -> list[Memory]
```

**Parameters:**
- `query` (str): Keyword query (supports FTS5 syntax)
- `limit` (int): Maximum results. Default: 10
- `namespace` (str | None): Filter by namespace
- `spec` (str | None): Filter by spec

**Returns:** List of `Memory` objects.

##### `get()`

Get a specific memory by ID.

```python
def get(self, memory_id: str) -> Memory | None
```

##### `get_batch()`

Get multiple memories by IDs.

```python
def get_batch(self, memory_ids: Sequence[str]) -> list[Memory]
```

##### `get_by_namespace()`

Get all memories in a namespace.

```python
def get_by_namespace(
    self,
    namespace: str,
    *,
    spec: str | None = None,
    limit: int | None = None,
) -> list[Memory]
```

##### `get_by_spec()`

Get all memories for a spec.

```python
def get_by_spec(self, spec: str) -> list[Memory]
```

##### `proactive_recall()`

Get contextually relevant memories without explicit query.

```python
def proactive_recall(
    self,
    context: str,
    max_suggestions: int = 5,
) -> list[Memory]
```

**Parameters:**
- `context` (str): Current working context (e.g., file contents, conversation)
- `max_suggestions` (int): Maximum suggestions. Default: 5

**Returns:** List of relevant `Memory` objects.

##### `hydrate()`

Load additional data for a memory.

```python
def hydrate(
    self,
    memory_id: str,
    level: HydrationLevel = HydrationLevel.FULL,
) -> HydratedMemory
```

**Parameters:**
- `memory_id` (str): Memory identifier
- `level` (HydrationLevel): How much data to load
  - `SUMMARY`: Metadata only
  - `FULL`: Complete content
  - `FILES`: Content + file snapshots

**Returns:** `HydratedMemory` with requested data.

##### `build_context()`

Build grouped context from multiple memories.

```python
def build_context(
    self,
    memories: Sequence[Memory],
    *,
    group_by_namespace: bool = True,
) -> SpecContext
```

---

### SyncService

Keeps the SQLite index synchronized with git notes.

#### Factory Function

```python
from git_notes_memory import get_sync_service

sync = get_sync_service(repo_path=None)
```

#### Methods

##### `reindex()`

Rebuild the index from git notes.

```python
def reindex(self, *, full: bool = False) -> int
```

**Parameters:**
- `full` (bool): If True, clears index first. If False, incremental update.

**Returns:** Number of memories indexed.

##### `verify_consistency()`

Check index against git notes for drift.

```python
def verify_consistency(self) -> VerificationResult
```

**Returns:** `VerificationResult` with:
- `is_consistent` (bool): True if no issues
- `missing_in_index` (tuple[str]): IDs in notes but not index
- `orphaned_in_index` (tuple[str]): IDs in index but not notes
- `mismatched` (tuple[str]): IDs with content differences

##### `repair()`

Fix inconsistencies found by verify.

```python
def repair(self, verification: VerificationResult | None = None) -> int
```

**Returns:** Number of repairs made.

##### `sync_note_to_index()`

Index a single note.

```python
def sync_note_to_index(self, commit: str, namespace: str) -> int
```

##### `collect_notes()`

Gather all notes across namespaces.

```python
def collect_notes(self) -> list[NoteRecord]
```

---

## Models

All models are frozen dataclasses (immutable).

### Memory

```python
@dataclass(frozen=True)
class Memory:
    id: str                     # Unique identifier (namespace:commit:index)
    commit_sha: str             # Git commit this memory is attached to
    namespace: str              # Memory category
    timestamp: datetime         # When captured (UTC)
    summary: str                # One-line summary
    content: str                # Full content
    spec: str | None            # Optional spec identifier
    tags: tuple[str, ...]       # Searchable tags
    phase: str | None           # Development phase
    status: str                 # active, resolved, archived, tombstone
    relates_to: tuple[str, ...] # Related memory/spec IDs
```

### MemoryResult

```python
@dataclass(frozen=True)
class MemoryResult:
    memory: Memory
    similarity: float  # 0.0-1.0 similarity score
```

### HydratedMemory

```python
@dataclass(frozen=True)
class HydratedMemory:
    memory: Memory
    full_content: str | None      # Complete note content
    files: tuple[FileSnapshot, ...] | None  # File contents from commit
```

### CaptureResult

```python
@dataclass(frozen=True)
class CaptureResult:
    success: bool
    memory_id: str
    commit: str
    namespace: str
    message: str | None
```

### VerificationResult

```python
@dataclass(frozen=True)
class VerificationResult:
    is_consistent: bool
    missing_in_index: tuple[str, ...]
    orphaned_in_index: tuple[str, ...]
    mismatched: tuple[str, ...]
```

### HydrationLevel

```python
class HydrationLevel(Enum):
    SUMMARY = 1  # Metadata only
    FULL = 2     # Complete content
    FILES = 3    # Content + file snapshots
```

### PatternType

```python
class PatternType(Enum):
    SUCCESS = "success"
    ANTI_PATTERN = "anti-pattern"
    WORKFLOW = "workflow"
    DECISION = "decision"
    TECHNICAL = "technical"
```

### PatternStatus

```python
class PatternStatus(Enum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    DEPRECATED = "deprecated"
```

---

## Exceptions

All exceptions inherit from `MemoryError`.

```python
from git_notes_memory import (
    MemoryError,      # Base exception
    StorageError,     # Git/index operations
    CaptureError,     # Capture failures
    RecallError,      # Search/retrieval failures
    ConfigError,      # Configuration issues
    ValidationError,  # Input validation
    EmbeddingError,   # Model/embedding failures
)
```

Each exception has:
- `message` (str): Human-readable description
- `recovery_action` (str | None): Suggested fix
- `category` (ErrorCategory): Error classification

**Example:**
```python
from git_notes_memory import CaptureError

try:
    result = capture.capture(...)
except CaptureError as e:
    print(f"Error: {e.message}")
    if e.recovery_action:
        print(f"Try: {e.recovery_action}")
```

---

## Utilities

### Temporal Decay

```python
from git_notes_memory.utils import calculate_temporal_decay, calculate_age_days

# Calculate relevance decay (0.0-1.0)
decay = calculate_temporal_decay(
    timestamp,
    half_life_days=30.0,  # Default
    min_decay=0.1,        # Optional floor
)

# Get age in days
age = calculate_age_days(timestamp)
```

### Timestamp Parsing

```python
from git_notes_memory.utils import parse_iso_timestamp, parse_iso_timestamp_safe

# Strict parsing (raises ValueError)
dt = parse_iso_timestamp("2024-01-15T10:30:00Z")

# Safe parsing (returns None on error)
dt = parse_iso_timestamp_safe("invalid")  # None
```

### Validation

```python
from git_notes_memory.utils import (
    validate_namespace,      # Raises ValueError if invalid
    validate_content_size,   # Raises if > 100KB
    validate_summary_length, # Raises if > 100 chars
    validate_git_ref,        # Raises if unsafe ref
    is_valid_namespace,      # Returns bool
    is_valid_git_ref,        # Returns bool
)
```

---

## Configuration

### Constants

```python
from git_notes_memory.config import (
    # Namespaces
    NAMESPACES,                    # frozenset of valid namespaces

    # Paths
    get_data_path(),               # ~/.local/share/memory-plugin/
    get_index_path(),              # .../index.db
    get_models_path(),             # .../models/

    # Embedding
    DEFAULT_EMBEDDING_MODEL,       # "all-MiniLM-L6-v2"
    EMBEDDING_DIMENSIONS,          # 384

    # Limits
    MAX_CONTENT_BYTES,             # 102400 (100KB)
    MAX_SUMMARY_CHARS,             # 100
    MAX_RECALL_LIMIT,              # 100

    # Timeouts (in milliseconds unless noted)
    SEARCH_TIMEOUT_MS,             # 500
    CAPTURE_TIMEOUT_MS,            # 2000
    LOCK_TIMEOUT_SECONDS,          # 5

    # Lifecycle
    DECAY_HALF_LIFE_DAYS,          # 30
)
```

### Environment Overrides

| Variable | Config Key | Default |
|----------|------------|---------|
| `MEMORY_PLUGIN_DATA_DIR` | Data directory | `~/.local/share/memory-plugin/` |
| `MEMORY_PLUGIN_GIT_NAMESPACE` | Git notes ref | `refs/notes/mem` |
| `MEMORY_PLUGIN_EMBEDDING_MODEL` | Model name | `all-MiniLM-L6-v2` |
| `MEMORY_PLUGIN_AUTO_CAPTURE` | Hook enabled | `false` |

---

## Testing

### Running Tests

```bash
# All tests
make test

# With coverage
make coverage

# Specific module
pytest tests/test_capture.py -v

# Skip slow tests
pytest -m "not slow"
```

### Test Fixtures

```python
import pytest
from git_notes_memory import get_capture_service

@pytest.fixture
def capture_service(tmp_path, monkeypatch):
    """Isolated capture service for testing."""
    monkeypatch.setenv("MEMORY_PLUGIN_DATA_DIR", str(tmp_path))
    return get_capture_service(repo_path=tmp_path)
```

### Mocking Services

```python
from unittest.mock import Mock, patch

# Mock embedding service
with patch("git_notes_memory.capture.EmbeddingService") as mock:
    mock.return_value.embed.return_value = [0.1] * 384
    # ... test code
```

---

## Contributing

### Development Setup

```bash
git clone https://github.com/zircote/git-notes-memory.git
cd git-notes-memory
uv sync
```

### Quality Checks

```bash
make quality  # Runs all checks

# Individual checks
make format   # ruff format
make lint     # ruff check
make typecheck # mypy
make security  # bandit
```

### Code Style

- Python 3.11+ syntax
- Type annotations on all public functions
- Docstrings on all public classes/methods
- Frozen dataclasses for models
- 88 character line length (ruff default)

### Testing Requirements

- 90%+ coverage for new code
- Unit tests for pure functions
- Integration tests with real git repos (marked `@pytest.mark.integration`)
