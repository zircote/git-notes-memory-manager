# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`git-notes-memory` is a Python library and Claude Code plugin that provides git-native, semantically-searchable memory storage. Memories are stored as git notes with YAML front matter and indexed in SQLite with sqlite-vec for vector similarity search.

## Development Commands

```bash
# Install with dev dependencies
uv sync

# Run all tests
make test

# Run tests with coverage (80% minimum required)
make coverage

# Run a specific test file
uv run pytest tests/test_capture.py -v

# Run a single test
uv run pytest tests/test_capture.py::TestCaptureService::test_capture_basic -v

# Skip slow tests
uv run pytest -m "not slow"

# Run all quality checks (format, lint, typecheck, security, tests)
make quality

# Individual quality checks
make format     # Auto-fix formatting
make lint       # Ruff linting
make typecheck  # mypy strict mode
make security   # bandit security scan

# Version management
make version    # Show current version
make bump       # Bump patch version (0.3.1 → 0.3.2)
make bump-minor # Bump minor version (0.3.1 → 0.4.0)
make bump-major # Bump major version (0.3.1 → 1.0.0)
make bump-dry   # Preview version bump changes
```

## Architecture

### Service Layer Pattern

The codebase uses a singleton service factory pattern with lazy initialization:

```
__init__.py          # Lazy imports via __getattr__ to avoid loading embedding model at import
    └── get_capture_service()  → CaptureService
    └── get_recall_service()   → RecallService
    └── get_sync_service()     → SyncService
```

Services are exposed through factory functions (`get_*_service()`) that return singleton instances. Internal modules use `get_default_service()` naming.

### Core Data Flow

```
Capture:
  CaptureService.capture()
      → validate (namespace, summary ≤100 chars, content ≤100KB)
      → serialize_note() (YAML front matter + body)
      → GitOps.append_note() (atomic append to refs/notes/mem/{namespace})
      → EmbeddingService.embed() (sentence-transformers, graceful degradation)
      → IndexService.insert() (SQLite + sqlite-vec)

Recall:
  RecallService.search()
      → EmbeddingService.embed(query)
      → IndexService.search_vector() (KNN via sqlite-vec)
      → Memory objects with distance scores
```

### Git Notes Storage

Memories are stored under `refs/notes/mem/{namespace}` where namespace is one of:
`inception`, `elicitation`, `research`, `decisions`, `progress`, `blockers`, `reviews`, `learnings`, `retrospective`, `patterns`

Each note has YAML front matter:
```yaml
---
type: decisions
timestamp: 2024-01-15T10:30:00Z
summary: Use PostgreSQL for persistence
spec: my-project
tags: [database, architecture]
---
## Context
...
```

### Key Modules

| Module | Responsibility |
|--------|---------------|
| `capture.py` | Memory capture with file locking (`fcntl`) for concurrency |
| `recall.py` | Search and retrieval with progressive hydration |
| `index.py` | SQLite + sqlite-vec for metadata and vector search |
| `embedding.py` | Sentence-transformer embeddings (all-MiniLM-L6-v2) |
| `git_ops.py` | Git notes operations with security validation |
| `note_parser.py` | YAML front matter parsing/serialization |
| `models.py` | Frozen dataclasses for all domain objects |
| `sync.py` | Index synchronization with git notes |

### Hooks Subsystem

The `hooks/` module provides Claude Code hook handlers:

| Handler | Hook Event | Purpose |
|---------|------------|---------|
| `session_start_handler.py` | SessionStart | Injects memory context and response guidance |
| `user_prompt_handler.py` | UserPromptSubmit | Detects capture markers (`[decision]`, `[learned]`, etc.) |
| `post_tool_use_handler.py` | PostToolUse | Surfaces related memories after file operations |
| `pre_compact_handler.py` | PreCompact | Auto-captures content before context compaction |
| `stop_handler.py` | Stop | Session analysis and index sync |

Supporting modules:
- `context_builder.py` - Builds XML memory context with token budgeting
- `guidance_builder.py` - Loads response guidance templates from `templates/`
- `signal_detector.py` - Pattern matching for capture markers
- `config_loader.py` - Environment-based hook configuration
- `namespace_styles.py` - ANSI colors and emojis for namespace display

### Models

All models are immutable (`@dataclass(frozen=True)`):
- `Memory` - Core entity with id format `{namespace}:{commit_sha}:{index}`
- `MemoryResult` - Memory + distance score from vector search
- `CaptureResult` - Operation result with success/warning status
- `HydrationLevel` - SUMMARY → FULL → FILES progressive loading

### Claude Code Plugin Integration

The `plugin.json` and hooks in `hooks/` directory define the plugin:
- Commands: `/memory:capture`, `/memory:recall`, `/memory:search`, `/memory:sync`, `/memory:status`
- Hooks: SessionStart, UserPromptSubmit, PostToolUse, PreCompact, Stop
- Skills: `memory-recall` for semantic search

## Code Conventions

- Python 3.11+ with full type annotations (mypy strict)
- Google-style docstrings
- Frozen dataclasses for all models (immutability)
- Tuple over list for immutable collections in models
- Factory functions expose services; internal modules use `get_default_service()`
- Graceful degradation: embedding failures don't block capture

## Testing

The test suite uses pytest with automatic singleton reset via `conftest.py`. Each test gets isolated service instances to prevent cross-test pollution.

```python
# Tests automatically reset singletons via autouse fixture
# For manual isolation, use tmp_path and monkeypatch:
@pytest.fixture
def capture_service(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_PLUGIN_DATA_DIR", str(tmp_path))
    return get_capture_service(repo_path=tmp_path)
```

## Environment Variables

### Core Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PLUGIN_DATA_DIR` | Data/index directory | `~/.local/share/memory-plugin/` |
| `MEMORY_PLUGIN_GIT_NAMESPACE` | Git notes ref prefix | `refs/notes/mem` |
| `MEMORY_PLUGIN_EMBEDDING_MODEL` | Embedding model | `all-MiniLM-L6-v2` |

### Hook Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_ENABLED` | Master switch for all hooks | `true` |
| `HOOK_SESSION_START_ENABLED` | Enable SessionStart context injection | `true` |
| `HOOK_USER_PROMPT_ENABLED` | Enable capture marker detection | `false` |
| `HOOK_POST_TOOL_USE_ENABLED` | Enable file-contextual memory injection | `true` |
| `HOOK_PRE_COMPACT_ENABLED` | Enable auto-capture before compaction | `true` |
| `HOOK_STOP_ENABLED` | Enable Stop hook processing | `true` |
| `HOOK_DEBUG` | Enable debug logging to stderr | `false` |
| `HOOK_SESSION_START_INCLUDE_GUIDANCE` | Include response guidance templates | `true` |
| `HOOK_SESSION_START_GUIDANCE_DETAIL` | Guidance level: minimal/standard/detailed | `standard` |
