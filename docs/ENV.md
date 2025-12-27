# Environment Variables Reference

This document provides a comprehensive reference for all environment variables used by git-notes-memory.

## Core Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PLUGIN_DATA_DIR` | Base directory for plugin data and indexes | `~/.local/share/memory-plugin/` |
| `MEMORY_PLUGIN_GIT_NAMESPACE` | Git notes ref prefix | `refs/notes/mem` |
| `MEMORY_PLUGIN_EMBEDDING_MODEL` | Sentence-transformer model for embeddings | `all-MiniLM-L6-v2` |

## User Memories (Cross-Repository)

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PLUGIN_USER_MEMORIES_PATH` | Path to user memories bare git repository | `~/.local/share/memory-plugin/user-memories.git` |
| `MEMORY_PLUGIN_USER_MEMORIES_REMOTE` | Remote URL for syncing user memories | (none) |

## Hook Configuration

### Master Switches

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_ENABLED` | Master switch for all hooks | `true` |
| `HOOK_DEBUG` | Enable debug logging to stderr | `false` |
| `HOOK_TIMEOUT` | Global timeout for hooks in seconds | `30` |

### SessionStart Hook

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_SESSION_START_ENABLED` | Enable SessionStart context injection | `true` |
| `HOOK_SESSION_START_FETCH_REMOTE` | Fetch notes from remote on session start | `false` |
| `HOOK_SESSION_START_FETCH_USER_REMOTE` | Fetch user memories from remote | `false` |
| `HOOK_SESSION_START_INCLUDE_GUIDANCE` | Include response guidance templates | `true` |
| `HOOK_SESSION_START_GUIDANCE_DETAIL` | Guidance level: `minimal`, `standard`, `detailed` | `standard` |

### UserPromptSubmit Hook

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_USER_PROMPT_ENABLED` | Enable capture marker detection | `false` |

### PostToolUse Hook

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_POST_TOOL_USE_ENABLED` | Enable file-contextual memory injection | `true` |

### PreCompact Hook

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_PRE_COMPACT_ENABLED` | Enable auto-capture before compaction | `true` |

### Stop Hook

| Variable | Description | Default |
|----------|-------------|---------|
| `HOOK_STOP_ENABLED` | Enable Stop hook processing | `true` |
| `HOOK_STOP_PROMPT_UNCAPTURED` | Prompt for uncaptured content | `true` |
| `HOOK_STOP_SYNC_INDEX` | Sync index on session end | `true` |
| `HOOK_STOP_PUSH_REMOTE` | Push notes to remote on session stop | `false` |
| `HOOK_STOP_PUSH_USER_REMOTE` | Push user memories to remote | `false` |
| `HOOK_STOP_AUTO_CAPTURE` | Auto-capture high-confidence signals | `false` |
| `HOOK_STOP_AUTO_CAPTURE_MIN_CONFIDENCE` | Minimum confidence for auto-capture | `0.9` |
| `HOOK_STOP_MAX_CAPTURES` | Maximum signals to auto-capture | `5` |

## Secrets Filtering Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRETS_FILTER_ENABLED` | Enable/disable secrets filtering | `true` |
| `SECRETS_FILTER_STRATEGY` | Default strategy: `redact`, `mask`, `block`, `warn` | `redact` |
| `SECRETS_FILTER_ENTROPY_ENABLED` | Enable entropy-based detection | `true` |
| `SECRETS_FILTER_PII_ENABLED` | Enable PII detection (SSN, credit cards, phones) | `true` |
| `SECRETS_FILTER_CONFIDENCE_THRESHOLD` | Minimum confidence for detection (0.0-1.0) | `0.8` |
| `SECRETS_FILTER_AUDIT_ENABLED` | Enable audit logging | `true` |
| `SECRETS_FILTER_AUDIT_DIR` | Audit log directory | `~/.local/share/memory-plugin/audit/` |
| `SECRETS_FILTER_AUDIT_MAX_SIZE` | Maximum log file size in bytes | `10485760` (10MB) |
| `SECRETS_FILTER_AUDIT_MAX_FILES` | Maximum number of rotated log files | `5` |

## Observability Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PLUGIN_OBSERVABILITY_ENABLED` | Enable observability subsystem | `true` |
| `MEMORY_PLUGIN_METRICS_ENABLED` | Enable metrics collection | `true` |
| `MEMORY_PLUGIN_TRACING_ENABLED` | Enable distributed tracing | `true` |
| `MEMORY_PLUGIN_LOG_LEVEL` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `MEMORY_PLUGIN_LOG_FORMAT` | Log format: `text`, `json` | `text` |
| `MEMORY_PLUGIN_LOG_DIR` | Directory for log files | `~/.local/share/memory-plugin/logs/` |
| `MEMORY_PLUGIN_SERVICE_NAME` | Service name for tracing | `git-notes-memory` |
| `MEMORY_PLUGIN_OTLP_ENDPOINT` | OpenTelemetry collector endpoint | (none) |

## Team Collaboration (Remote Sync)

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

## Development/Testing

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PLUGIN_TEST_MODE` | Enable test mode (skips some validations) | `false` |
| `MEMORY_PLUGIN_SKIP_EMBEDDING` | Skip embedding generation (for testing) | `false` |

## Example Configuration

### Minimal (Default)
```bash
# No configuration needed - sensible defaults
```

### Team Collaboration
```bash
export HOOK_SESSION_START_FETCH_REMOTE=true
export HOOK_STOP_PUSH_REMOTE=true
```

### High Security
```bash
export SECRETS_FILTER_STRATEGY=block
export SECRETS_FILTER_AUDIT_ENABLED=true
export HOOK_STOP_AUTO_CAPTURE=false
```

### Debug Mode
```bash
export HOOK_DEBUG=true
export MEMORY_PLUGIN_LOG_LEVEL=DEBUG
export MEMORY_PLUGIN_LOG_FORMAT=json
```

### Observability with OpenTelemetry
```bash
export MEMORY_PLUGIN_OBSERVABILITY_ENABLED=true
export MEMORY_PLUGIN_TRACING_ENABLED=true
export MEMORY_PLUGIN_OTLP_ENDPOINT=http://localhost:4317
export MEMORY_PLUGIN_SERVICE_NAME=my-project-memory
```
