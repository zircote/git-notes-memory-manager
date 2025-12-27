---
description: Health check with optional timing percentiles
argument-hint: "[--timing] [--verbose]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
HEALTH(1)                                            User Commands                                            HEALTH(1)

NAME
    health - Health check with optional timing percentiles

SYNOPSIS
    /memory:health [--timing] [--verbose]

DESCRIPTION
    Perform a quick health check of the memory system. Shows component status
    and optionally includes latency percentiles from collected metrics.

OPTIONS
    --help, -h       Show this help message
    --timing         Include latency percentiles from metrics
    --verbose        Show detailed component status

EXAMPLES
    /memory:health
    /memory:health --timing
    /memory:health --verbose
    /memory:health --timing --verbose
    /memory:health --help

SEE ALSO
    /memory:status for detailed system status
    /memory:metrics for all collected metrics
    /memory:traces for recent operation traces

                                                                      HEALTH(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:health - System Health Check

Quick health check of the memory system with optional timing information.

## Your Task

You will check the health of the memory system components.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Parse the following options:
- `--timing` - Include latency percentiles
- `--verbose` - Show detailed component status

</step>

<step number="2" name="Run Health Check">

**Execute the health check**:
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
import subprocess
import sys

# Parse args
show_timing = '--timing' in sys.argv
verbose = '--verbose' in sys.argv

print('## Memory System Health\n')
checks = []

# Git repository check
try:
    result = subprocess.run(['git', 'rev-parse', '--git-dir'], capture_output=True, text=True, timeout=10)
    git_ok = result.returncode == 0
    checks.append(('Git Repository', git_ok, 'Accessible' if git_ok else 'Not found'))
except Exception as e:
    checks.append(('Git Repository', False, str(e)))

# Git notes check
try:
    result = subprocess.run(['git', 'notes', 'list'], capture_output=True, text=True, timeout=10)
    notes_ok = result.returncode == 0
    checks.append(('Git Notes', notes_ok, 'Accessible' if notes_ok else 'Not configured'))
except Exception as e:
    checks.append(('Git Notes', False, str(e)))

# Index check
try:
    from git_notes_memory.config import get_project_index_path
    index_path = get_project_index_path()
    index_ok = index_path.exists()
    checks.append(('Index', index_ok, 'Initialized' if index_ok else 'Not initialized'))
except Exception as e:
    checks.append(('Index', False, str(e)))

# Embedding model check
try:
    from git_notes_memory.embedding import EmbeddingService
    _ = EmbeddingService()
    checks.append(('Embedding Model', True, 'Available'))
except Exception:
    checks.append(('Embedding Model', False, 'Not loaded'))

# Hook system check
try:
    from git_notes_memory.hooks.config_loader import load_hook_config
    config = load_hook_config()
    hooks_ok = config.enabled
    checks.append(('Hook System', hooks_ok, 'Enabled' if hooks_ok else 'Disabled'))
except Exception as e:
    checks.append(('Hook System', False, str(e)))

# Display results
print('| Component | Status | Details |')
print('|-----------|--------|---------|')
all_ok = True
for name, ok, details in checks:
    status = '✓' if ok else '✗'
    if not ok:
        all_ok = False
    print(f'| {name} | {status} | {details} |')

print()
if all_ok:
    print('**Overall**: ✓ Healthy')
else:
    print('**Overall**: ⚠ Issues detected')
print()

# Timing section
if show_timing:
    print('### Latency Percentiles\n')
    from git_notes_memory.observability.metrics import get_metrics
    metrics = get_metrics()
    with metrics._lock:
        histograms = list(metrics._histograms.items())
    if not histograms:
        print('No timing data collected yet.')
    else:
        print('| Metric | p50 | p95 | p99 | Avg |')
        print('|--------|-----|-----|-----|-----|')
        for hist_name, hist_label_values in sorted(histograms):
            for labels, histogram in hist_label_values.items():
                if histogram.count == 0:
                    continue
                samples = histogram.samples
                if samples:
                    sorted_samples = sorted(samples)
                    n = len(sorted_samples)
                    p50 = sorted_samples[int(n * 0.5)] if n > 0 else 0
                    p95 = sorted_samples[int(n * 0.95)] if n > 0 else 0
                    p99 = sorted_samples[int(n * 0.99)] if n > 0 else 0
                    avg = histogram.sum_value / histogram.count if histogram.count > 0 else 0
                    print(f'| {hist_name} | {p50:.1f}ms | {p95:.1f}ms | {p99:.1f}ms | {avg:.1f}ms |')
    print()
" $ARGUMENTS
```

</step>

<step number="3" name="Provide Recommendations">

If issues are detected, show recommendations:

```
### Recommendations

- **Index not initialized** - Run `/memory:sync` to create the index
- **Embedding model not loaded** - First search may be slow while model loads
- **Git notes not configured** - Run `/memory:capture` to create first memory
- **High timeout rate** - Consider increasing hook timeouts in environment
```

</step>

## Output Sections

| Section | Description |
|---------|-------------|
| Components | Status of each system component |
| Latency Percentiles | Timing metrics (with --timing) |
| Hook Timeout Rate | Percentage of timed-out hooks |
| Component Details | Detailed stats (with --verbose) |

## Status Indicators

| Symbol | Meaning |
|--------|---------|
| ✓ | Healthy/OK |
| ✗ | Error/Failed |
| ⚠ | Warning/Issues |

## Examples

**User**: `/memory:health`
**Action**: Quick health check of all components

**User**: `/memory:health --timing`
**Action**: Health check with latency percentiles

**User**: `/memory:health --verbose`
**Action**: Health check with detailed component info

**User**: `/memory:health --timing --verbose`
**Action**: Full health check with all details

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:status` | Detailed system status |
| `/memory:metrics` | View all metrics |
| `/memory:traces` | Recent operation traces |
| `/memory:validate` | Full validation |
