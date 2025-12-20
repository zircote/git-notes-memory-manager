# git-notes-memory

Git-native, semantically-searchable memory storage for Claude Code.

<p align="center">
  <img src="docs/_assets/infograph-git-notes-memory-project-memory.png" alt="Git Notes Memory Architecture" width="800"/>
</p>

<!-- Badges -->
[![CI](https://github.com/zircote/git-notes-memory-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/zircote/git-notes-memory-manager/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/git-notes-memory.svg)](https://pypi.org/project/git-notes-memory/)
[![PyPI Downloads](https://img.shields.io/pypi/dm/git-notes-memory.svg)](https://pypi.org/project/git-notes-memory/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)](https://github.com/zircote/git-notes-memory-manager)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code Plugin](https://img.shields.io/badge/Claude%20Code-Plugin-blueviolet.svg)](https://claude.ai/code)

## Overview

`git-notes-memory` provides a memory capture and recall system that stores memories as git notes with semantic search capabilities via sqlite-vec embeddings. It's designed to work as both a standalone Python library and a Claude Code plugin.

### Features

- **Git-native storage**: Memories stored as git notes that sync with push/pull
- **Semantic search**: Find relevant memories via sentence-transformer embeddings
- **10 memory namespaces**: inception, elicitation, research, decisions, progress, blockers, reviews, learnings, retrospective, patterns
- **Progressive hydration**: Load memory content incrementally (SUMMARY -> FULL -> FILES)
- **Concurrent-safe**: File locking prevents corruption from parallel captures
- **XDG-compliant**: Standard paths on all platforms

## Installation

```bash
# Using uv (recommended)
uv add git-notes-memory

# Using pip
pip install git-notes-memory
```

## Quick Start

```python
from git_notes_memory import get_capture_service, get_recall_service

# Capture a memory
capture = get_capture_service()
result = capture.capture(
    namespace="decisions",
    summary="Chose PostgreSQL for persistence",
    content="Evaluated SQLite vs PostgreSQL. PostgreSQL wins for concurrency."
)

# Recall memories
recall = get_recall_service()
memories = recall.search("database choice", namespace="decisions", limit=5)
```

## Claude Code Plugin

When used as a Claude Code plugin, the following slash commands are available:

| Command | Description |
|---------|-------------|
| `/memory:capture <namespace> <summary>` | Capture a memory |
| `/memory:recall <query>` | Search memories semantically |
| `/memory:search <query>` | Advanced search with filters |
| `/memory:sync [full\|verify\|repair]` | Synchronize or repair the index |
| `/memory:status [--verbose]` | Show index statistics |

### Hooks Integration

The plugin includes hooks that integrate with Claude Code's hook system for automatic memory context:

| Hook | Description |
|------|-------------|
| **SessionStart** | Injects relevant project memories and response guidance at session start |
| **UserPromptSubmit** | Detects capture markers like `[remember]` and `@memory` in prompts |
| **PostToolUse** | Surfaces related memories after file operations (Read/Write/Edit) |
| **PreCompact** | Auto-captures high-confidence content before context compaction |
| **Stop** | Prompts for uncaptured content and syncs the search index |

See [User Guide](docs/USER_GUIDE.md#hooks-integration) for configuration options.

## Development

```bash
# Clone the repository
git clone https://github.com/zircote/git-notes-memory.git
cd git-notes-memory

# Install with dev dependencies
uv sync

# Run tests
make test

# Run all quality checks
make quality
```

## Configuration

Environment variables (see `.env.example` for all options):

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PLUGIN_DATA_DIR` | Data directory path | `~/.local/share/memory-plugin/` |
| `MEMORY_PLUGIN_GIT_NAMESPACE` | Git notes namespace | `refs/notes/mem` |
| `MEMORY_PLUGIN_EMBEDDING_MODEL` | Embedding model name | `all-MiniLM-L6-v2` |
| `MEMORY_PLUGIN_AUTO_CAPTURE` | Enable auto-capture hook | `false` |

### Hook Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_ENABLED` | Master switch for hooks | `true` |
| `HOOK_SESSION_START_ENABLED` | Enable SessionStart context injection | `true` |
| `HOOK_USER_PROMPT_ENABLED` | Enable signal detection in prompts | `false` |
| `HOOK_POST_TOOL_USE_ENABLED` | Enable file-contextual memory injection | `true` |
| `HOOK_PRE_COMPACT_ENABLED` | Enable auto-capture before compaction | `true` |
| `HOOK_STOP_ENABLED` | Enable Stop hook processing | `true` |
| `HOOK_DEBUG` | Enable debug logging to stderr | `false` |

## Requirements

- Python 3.11+
- Git 2.25+ (for git notes features)
- ~500MB disk space (for embedding model on first use)

## Documentation

- [User Guide](docs/USER_GUIDE.md) - Complete usage guide with examples
- [Developer Guide](docs/DEVELOPER_GUIDE.md) - API reference for library users
- [Changelog](CHANGELOG.md) - Version history

## License

MIT
