---
description: Display observability metrics for the memory system
argument-hint: "[--format=text|json|prometheus] [--filter=<pattern>] [--export]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
METRICS(1)                                           User Commands                                           METRICS(1)

NAME
    metrics - Display observability metrics for the memory system

SYNOPSIS
    /memory:metrics [--format=text|json|prometheus] [--filter=<pattern>] [--export]

DESCRIPTION
    Display collected observability metrics including counters, histograms, and gauges.
    Metrics track operation counts, durations, errors, and system health indicators.

OPTIONS
    --help, -h            Show this help message
    --format=FORMAT       Output format: text (default), json, prometheus
    --filter=PATTERN      Filter metrics by name pattern (e.g., "capture", "hook")
    --export              Export metrics/traces to OTLP endpoint (for Grafana)

EXAMPLES
    /memory:metrics
    /memory:metrics --format=json
    /memory:metrics --format=prometheus
    /memory:metrics --filter=hook
    /memory:metrics --format=json --filter=capture
    /memory:metrics --help

SEE ALSO
    /memory:status for system status
    /memory:health for health checks with timing

                                                                      METRICS(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:metrics - Observability Metrics

Display collected observability metrics for the memory system.

## Your Task

You will display metrics collected by the observability system.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Parse the following options:
- `--format=text|json|prometheus` - Output format (default: text)
- `--filter=<pattern>` - Filter metrics by name pattern

</step>

<step number="2" name="Collect and Display Metrics">

**Execute the metrics collection**:
```bash
uv run python3 -c "
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.exporters.prometheus import export_prometheus_text
import sys

format_arg = 'text'
filter_arg = None
export_flag = False

for arg in sys.argv[1:]:
    if arg.startswith('--format='):
        format_arg = arg.split('=')[1]
    elif arg.startswith('--filter='):
        filter_arg = arg.split('=')[1]
    elif arg == '--export':
        export_flag = True

if export_flag:
    from git_notes_memory.observability.exporters.otlp import export_metrics_if_configured
    if export_metrics_if_configured():
        print('Metrics exported to OTLP endpoint')
    else:
        print('OTLP export not configured (set MEMORY_PLUGIN_OTLP_ENDPOINT)')
else:
    metrics = get_metrics()
    if format_arg == 'json':
        print(metrics.export_json())
    elif format_arg == 'prometheus':
        print(export_prometheus_text())
    else:
        output = metrics.export_text()
        if filter_arg:
            output = '\n'.join(line for line in output.split('\n') if filter_arg.lower() in line.lower())
        print(output)
" \$ARGUMENTS
```

</step>

<step number="3" name="Explain Output">

After displaying metrics, provide context:

**For text format**:
```
### Metric Types

- **Counters**: Cumulative values that only increase (e.g., memories_captured_total)
- **Histograms**: Distribution of values (e.g., capture_duration_ms)
- **Gauges**: Current values that can go up or down (e.g., index_size_bytes)

Use `--format=prometheus` for Prometheus/Grafana scraping.
```

**For JSON format**:
```
### JSON Structure

The output contains:
- `counters`: Name → value pairs
- `histograms`: Name → {count, sum, avg, p50, p95, p99}
- `gauges`: Name → current value
```

**For Prometheus format**:
```
### Prometheus Format

Ready for scraping by Prometheus. Each metric includes:
- TYPE declaration (counter, histogram, gauge)
- HELP description
- Labels in {key="value"} format
```

</step>

## Output Formats

| Format | Use Case |
|--------|----------|
| text | Human-readable output (default) |
| json | Machine parsing, debugging |
| prometheus | Prometheus/Grafana scraping |

## Available Metrics

| Metric | Type | Description |
|--------|------|-------------|
| memories_captured_total | counter | Total memories captured by namespace |
| capture_duration_ms | histogram | Capture operation timing |
| recall_duration_ms | histogram | Search/recall timing |
| hook_execution_duration_ms | histogram | Hook handler timing |
| hook_executions_total | counter | Hook invocations by name and status |
| hook_timeouts_total | counter | Hook timeout events |
| silent_failures_total | counter | Logged silent failures by location |
| embedding_duration_ms | histogram | Embedding generation timing |
| index_operations_total | counter | Index CRUD operations |

## Examples

**User**: `/memory:metrics`
**Action**: Show all metrics in text format

**User**: `/memory:metrics --format=json`
**Action**: Show all metrics as JSON

**User**: `/memory:metrics --filter=hook`
**Action**: Show only hook-related metrics

**User**: `/memory:metrics --format=prometheus`
**Action**: Show Prometheus exposition format for scraping

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:status` | System status and statistics |
| `/memory:health` | Health checks with timing |
| `/memory:validate` | Full system validation |
