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
| `security/` | Secrets filtering and PII protection subsystem |

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

### Security Subsystem

The `security/` module provides secrets filtering and PII protection:

| Module | Responsibility |
|--------|---------------|
| `config.py` | Environment-based configuration for filtering behavior |
| `detector.py` | `DetectSecretsAdapter` wrapping detect-secrets library |
| `pii.py` | `PIIDetector` for SSN, credit cards, phone numbers |
| `redactor.py` | `Redactor` applies strategies (redact/mask/block/warn) |
| `allowlist.py` | `AllowlistManager` for false positive management |
| `service.py` | `SecretsFilteringService` orchestrating the pipeline |
| `audit.py` | `AuditLogger` for compliance logging (SOC2/GDPR) |
| `models.py` | `SecretDetection`, `FilterResult`, `FilterAction` types |

**Filtering Strategies**:
- `REDACT`: Replace with `[REDACTED:type]`
- `MASK`: Show partial content `abc...xyz`
- `BLOCK`: Raise `BlockedContentError`
- `WARN`: Log but pass through unchanged

**Detection Flow**:
```
Content → PIIDetector → DetectSecretsAdapter → Deduplicate → AllowlistCheck → Redactor → FilterResult
```

### Models

All models are immutable (`@dataclass(frozen=True)`):
- `Memory` - Core entity with id format `{namespace}:{commit_sha}:{index}`
- `MemoryResult` - Memory + distance score from vector search
- `CaptureResult` - Operation result with success/warning status
- `HydrationLevel` - SUMMARY → FULL → FILES progressive loading

### Claude Code Plugin Integration

The `plugin.json` and hooks in `hooks/` directory define the plugin:
- Commands: `/memory:capture`, `/memory:recall`, `/memory:search`, `/memory:sync`, `/memory:status`
- Secrets Commands: `/memory:scan-secrets`, `/memory:secrets-allowlist`, `/memory:test-secret`, `/memory:audit-log`
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
| `HOOK_SESSION_START_FETCH_REMOTE` | Fetch notes from remote on session start | `false` |
| `HOOK_USER_PROMPT_ENABLED` | Enable capture marker detection | `false` |
| `HOOK_POST_TOOL_USE_ENABLED` | Enable file-contextual memory injection | `true` |
| `HOOK_PRE_COMPACT_ENABLED` | Enable auto-capture before compaction | `true` |
| `HOOK_STOP_ENABLED` | Enable Stop hook processing | `true` |
| `HOOK_STOP_PUSH_REMOTE` | Push notes to remote on session stop | `false` |
| `HOOK_DEBUG` | Enable debug logging to stderr | `false` |
| `HOOK_SESSION_START_INCLUDE_GUIDANCE` | Include response guidance templates | `true` |
| `HOOK_SESSION_START_GUIDANCE_DETAIL` | Guidance level: minimal/standard/detailed | `standard` |

### Secrets Filtering Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRETS_FILTER_ENABLED` | Enable/disable secrets filtering | `true` |
| `SECRETS_FILTER_STRATEGY` | Default strategy: redact, mask, block, warn | `redact` |
| `SECRETS_FILTER_ENTROPY_ENABLED` | Enable entropy-based detection | `true` |
| `SECRETS_FILTER_PII_ENABLED` | Enable PII detection (SSN, credit cards, phones) | `true` |
| `SECRETS_FILTER_AUDIT_ENABLED` | Enable audit logging | `true` |
| `SECRETS_FILTER_AUDIT_DIR` | Audit log directory | `~/.local/share/memory-plugin/audit/` |

### Remote Sync (Team Collaboration)

For team environments where multiple developers share memories:

```bash
# Enable automatic sync with remote (opt-in)
export HOOK_SESSION_START_FETCH_REMOTE=true  # Fetch from remote on session start
export HOOK_STOP_PUSH_REMOTE=true            # Push to remote on session stop
```

With these enabled, memories are automatically synchronized with the origin repository:
- **Session start**: Fetches and merges remote notes using `cat_sort_uniq` strategy
- **Session stop**: Pushes local notes to remote

Manual sync is always available via `/memory:sync --remote`.

## Code Intelligence (LSP)

LSP hooks are configured in `.claude/hooks.json` for immediate feedback on Python edits.

### Installed Hooks

| Hook | Trigger | Action |
|------|---------|--------|
| `format-on-edit` | PostToolUse (Write/Edit) | Runs `ruff format` on changed files |
| `lint-check-on-edit` | PostToolUse (Write/Edit) | Runs `ruff check` on changed files |
| `typecheck-on-edit` | PostToolUse (Write/Edit) | Runs `mypy` on changed files |
| `pre-commit-quality-gate` | PreToolUse (git commit) | Runs full `make quality` before commit |

### Navigation & Understanding

- Use LSP `goToDefinition` before modifying unfamiliar functions, classes, or modules
- Use LSP `findReferences` before refactoring any symbol to understand full impact
- Use LSP `documentSymbol` to get file structure overview before major edits
- Prefer LSP navigation over grep—it resolves through imports and re-exports

### Verification Workflow

1. After each edit, check hook output for lint/type errors
2. Fix errors immediately before proceeding
3. Run `make quality` before committing

### Pre-Edit Checklist

- [ ] Navigate to definition to understand implementation
- [ ] Find all references to assess change impact
- [ ] Review type annotations via hover before modifying function signatures

### Error Handling

- If hooks report errors, fix them before proceeding to the next task
- Type errors are blocking in this project (mypy strict mode)
- Use hook output to guide fixes, not guesswork


## Completed Spec Projects

- `docs/spec/completed/2025-12-25-observability-instrumentation/` - Observability Instrumentation
  - Completed: 2025-12-26
  - Outcome: success
  - GitHub Issue: [#10](https://github.com/zircote/git-notes-memory/issues/10)
  - Features: Metrics collection, distributed tracing, structured logging, CLI commands (/metrics, /traces, /health)
  - Deliverables: 115+ tests, 4 phases completed (6 total, 2 optional skipped), 20 tasks, 11 ADRs
  - Note: Phases 5-6 (OpenTelemetry, Docker stack) skipped as optional Tier 3 enhancements
  - Key docs: REQUIREMENTS.md, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, DECISIONS.md, PROGRESS.md

- `docs/spec/completed/2025-12-25-fix-git-notes-fetch-refspec/` - Fix Git Notes Fetch Refspec
  - Completed: 2025-12-25
  - Outcome: success
  - GitHub Issue: [#18](https://github.com/zircote/git-notes-memory/issues/18)
  - Features: Remote tracking refs pattern, idempotent migration, hook-based auto-sync, proper fetch→merge→push workflow
  - Deliverables: 26 tests, 5 phases, 20 tasks, 7 ADRs, complete documentation (2,648 lines)
  - Key docs: REQUIREMENTS.md, ARCHITECTURE.md, IMPLEMENTATION_PLAN.md, DECISIONS.md, RETROSPECTIVE.md
