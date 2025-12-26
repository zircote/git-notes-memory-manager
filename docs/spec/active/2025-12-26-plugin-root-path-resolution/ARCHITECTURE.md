---
document_type: architecture
project_id: SPEC-2025-12-26-002
version: 1.0.0
last_updated: 2025-12-26T21:00:00Z
status: draft
---

# PLUGIN_ROOT Path Resolution Fix - Technical Architecture

## System Overview

This fix replaces filesystem-based script execution with Python module imports across all affected command files. Instead of resolving `PLUGIN_ROOT` and executing external scripts, commands will import and call functions directly from the `git_notes_memory` package.

### Architecture Change

```
BEFORE (Broken Pattern):
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Command File    │────▶│ PLUGIN_ROOT Glob │────▶│ scripts/*.py    │
│ (metrics.md)    │     │ (filesystem)     │     │ (external file) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼ FAILS for marketplace installs
                        PLUGIN_ROOT=""

AFTER (Fixed Pattern):
┌─────────────────┐     ┌──────────────────┐
│ Command File    │────▶│ Python Module    │
│ (metrics.md)    │     │ Import           │
└─────────────────┘     └──────────────────┘
                               │
                               ▼ Works for ALL installations
                        from git_notes_memory.observability import ...
```

### Key Design Decisions

1. **Direct module imports** instead of script execution
2. **No filesystem assumptions** in command logic
3. **Inline Python** via `python3 -c "..."` for simple operations
4. **uv run** continues to manage dependencies

## Module Mapping

### Available Functions for Commands

| Command | Current Script | Module Function |
|---------|---------------|-----------------|
| `/memory:metrics` | `scripts/metrics.py` | `git_notes_memory.observability.metrics.get_metrics()` |
| `/memory:health` | `scripts/health.py` | `git_notes_memory.observability.health.*` |
| `/memory:traces` | `scripts/traces.py` | `git_notes_memory.observability.traces.*` |
| `/memory:capture` | inline | `git_notes_memory.capture.*` |
| `/memory:recall` | inline | `git_notes_memory.recall.*` |
| `/memory:search` | inline | `git_notes_memory.recall.*` |
| `/memory:sync` | inline | `git_notes_memory.sync.*` |
| `/memory:status` | inline | `git_notes_memory.*` (various) |
| `/memory:scan-secrets` | inline | `git_notes_memory.security.*` |
| `/memory:secrets-allowlist` | inline | `git_notes_memory.security.allowlist.*` |
| `/memory:test-secret` | inline | `git_notes_memory.security.*` |
| `/memory:audit-log` | inline | `git_notes_memory.security.audit.*` |
| `/memory:validate` | inline | `git_notes_memory.*` (validation) |

## Code Patterns

### Pattern 1: Simple Function Call

**Before:**
```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 "$PLUGIN_ROOT/scripts/metrics.py" $ARGUMENTS
```

**After:**
```bash
uv run python3 -c "
from git_notes_memory.observability.metrics import get_metrics
import sys

format_arg = 'text'
filter_arg = None

for arg in sys.argv[1:]:
    if arg.startswith('--format='):
        format_arg = arg.split('=')[1]
    elif arg.startswith('--filter='):
        filter_arg = arg.split('=')[1]

metrics = get_metrics()
if format_arg == 'json':
    print(metrics.export_json())
elif format_arg == 'prometheus':
    from git_notes_memory.observability.exporters.prometheus import export_prometheus_text
    print(export_prometheus_text())
else:
    print(metrics.export_text())
" $ARGUMENTS
```

### Pattern 2: Complex Operations

For commands with complex logic, use a dedicated entry point if available or inline the logic:

```bash
uv run python3 << 'PYTHON_SCRIPT'
import sys
from git_notes_memory import get_capture_service

# Parse arguments
args = sys.argv[1:]
# ... operation logic ...

PYTHON_SCRIPT
```

### Pattern 3: Current Working Directory

For commands that need repository context:

```bash
uv run python3 -c "
import os
from git_notes_memory import get_sync_service

cwd = os.getcwd()
sync = get_sync_service(repo_path=cwd)
# ... operation ...
"
```

## Integration Points

### Python Package Requirements

The `git_notes_memory` package must export:

| Module Path | Required Exports |
|-------------|-----------------|
| `git_notes_memory.observability.metrics` | `get_metrics()`, `MetricsCollector` |
| `git_notes_memory.observability.health` | Health check functions |
| `git_notes_memory.observability.traces` | Trace export functions |
| `git_notes_memory.observability.exporters.prometheus` | `export_prometheus_text()` |
| `git_notes_memory.observability.exporters.json_exporter` | `export_json()` |
| `git_notes_memory.capture` | `get_capture_service()` |
| `git_notes_memory.recall` | `get_recall_service()` |
| `git_notes_memory.sync` | `get_sync_service()` |
| `git_notes_memory.security` | Various security functions |

### Verified Exports

From codebase analysis:

```python
# git_notes_memory.observability.metrics
get_metrics() -> MetricsCollector  # Line 491
MetricsCollector.export_json() -> str  # Line 298
MetricsCollector.export_text() -> str  # Line 365

# git_notes_memory.observability.exporters.prometheus
export_prometheus_text() -> str  # Line 45

# git_notes_memory.observability.exporters.json_exporter
export_json() -> dict  # Line 26
```

## Testing Strategy

### Unit Testing

Not applicable - this is a command file refactor, not Python code change.

### Integration Testing

| Test Case | Verification |
|-----------|--------------|
| Marketplace install | Commands work without CLAUDE_PLUGIN_ROOT |
| Direct install | Commands continue working |
| Source repo | Commands work when run from source |
| Missing uv | Clear error message |

### Manual Test Script

```bash
#!/bin/bash
# Test all affected commands

commands=(
  "/memory:metrics"
  "/memory:metrics --format=json"
  "/memory:health"
  "/memory:traces"
  "/memory:status"
)

for cmd in "${commands[@]}"; do
  echo "Testing: $cmd"
  # Execute and verify no "directory" error
done
```

## Deployment Considerations

### Rollout Strategy

1. Update all command files in single PR
2. Test in marketplace installation
3. Verify backwards compatibility
4. Release as patch version

### Rollback Plan

Revert command file changes (no Python code affected).

## Future Considerations

- Consider adding `--directory` fallback for edge cases
- Could create dedicated CLI entry points in pyproject.toml
- May want to add `git-notes-memory` CLI command in future
