---
description: Display recent trace spans for debugging
argument-hint: "[--operation=<name>] [--status=ok|error] [--limit=<n>]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
TRACES(1)                                            User Commands                                            TRACES(1)

NAME
    traces - Display recent trace spans for debugging

SYNOPSIS
    /memory:traces [--operation=<name>] [--status=ok|error] [--limit=<n>]

DESCRIPTION
    Display completed trace spans from memory operations. Useful for debugging
    performance issues and understanding operation flow. Shows timing, status,
    and context for each traced operation.

OPTIONS
    --help, -h            Show this help message
    --operation=NAME      Filter by operation name (e.g., "capture", "recall")
    --status=STATUS       Filter by status: ok, error
    --limit=N             Maximum traces to show (default: 10)

EXAMPLES
    /memory:traces
    /memory:traces --limit=20
    /memory:traces --operation=capture
    /memory:traces --status=error
    /memory:traces --operation=recall --limit=5
    /memory:traces --help

SEE ALSO
    /memory:metrics for collected metrics
    /memory:health for health status with timing

                                                                      TRACES(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:traces - Recent Trace Spans

Display recent trace spans for debugging memory operations.

## Your Task

You will display completed traces from the observability system.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Parse the following options:
- `--operation=<name>` - Filter by operation name
- `--status=ok|error` - Filter by status
- `--limit=<n>` - Maximum traces to show (default: 10)

</step>

<step number="2" name="Collect and Display Traces">

**Execute the traces collection**:
```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
import sys

# Parse arguments safely
operation_filter = None
status_filter = None
limit = 10

for arg in sys.argv[1:]:
    if arg.startswith('--operation='):
        operation_filter = arg.split('=')[1]
    elif arg.startswith('--status='):
        status_filter = arg.split('=')[1]
    elif arg.startswith('--limit='):
        limit = int(arg.split('=')[1])

from git_notes_memory.observability.tracing import get_completed_spans

spans = get_completed_spans()

# Apply filters
if operation_filter:
    spans = [s for s in spans if operation_filter.lower() in s.operation.lower()]
if status_filter:
    spans = [s for s in spans if s.status == status_filter]

# Sort by end time (most recent first) and apply limit
spans = sorted(spans, key=lambda s: s.end_time or s.start_time, reverse=True)[:limit]

if not spans:
    print('## Recent Traces
')
    print('No traces recorded yet. Traces are captured during:')
    print('- /memory:capture operations')
    print('- /memory:recall searches')
    print('- Hook executions')
    print('- Index operations')
    print()
    print('Run some memory commands to generate traces.')
else:
    print('## Recent Traces
')
    filter_msg = ' (filtered)' if operation_filter or status_filter else ''
    print(f'Showing {len(spans)} trace(s){filter_msg}')
    print()
    print('| Operation | Duration | Status | Time | Details |')
    print('|-----------|----------|--------|------|---------|')
    for span in spans:
        duration = f'{span.duration_ms:.1f}ms' if span.duration_ms else '-'
        if span.status == 'ok':
            status = '✓'
        elif span.status == 'error':
            status = '✗'
        else:
            status = '○'
        time_str = span.start_datetime.strftime('%H:%M:%S') if span.start_datetime else '-'
        details = []
        for key, value in sorted(span.tags.items()):
            if len(str(value)) > 20:
                value = str(value)[:17] + '...'
            details.append(f'{key}={value}')
        details_str = ', '.join(details[:3]) if details else '-'
        print(f'| {span.operation} | {duration} | {status} | {time_str} | {details_str} |')
    print()
    total_duration = sum(s.duration_ms or 0 for s in spans)
    error_count = sum(1 for s in spans if s.status == 'error')
    print('### Summary')
    print(f'- Total traces: {len(spans)}')
    print(f'- Total duration: {total_duration:.1f}ms')
    if error_count:
        print(f'- Errors: {error_count}')
" \$ARGUMENTS
```

</step>

<step number="3" name="Provide Context">

After displaying traces, explain what they show:

```
### Understanding Traces

Traces capture the timing and context of operations:
- **Operation**: The operation name (capture, recall, embed, index, etc.)
- **Duration**: How long the operation took in milliseconds
- **Status**: ✓ success, ✗ error, ○ pending
- **Details**: Context tags like namespace, memory_id, file paths

Use `--operation=capture` to focus on specific operation types.
Use `--status=error` to investigate failures.
```

</step>

## Output Format

| Column | Description |
|--------|-------------|
| Operation | Name of the traced operation |
| Duration | Execution time in milliseconds |
| Status | ✓ ok, ✗ error, ○ unknown |
| Time | When the operation started (HH:MM:SS) |
| Details | Key context tags (max 3) |

## Available Operations

| Operation | Description |
|-----------|-------------|
| capture | Memory capture operations |
| recall | Search and recall operations |
| embed | Embedding generation |
| index_insert | Index write operations |
| index_search | Index query operations |
| git_append | Git notes append operations |
| hook_* | Hook handler executions |

## Examples

**User**: `/memory:traces`
**Action**: Show last 10 traces

**User**: `/memory:traces --limit=20`
**Action**: Show last 20 traces

**User**: `/memory:traces --operation=capture`
**Action**: Show only capture-related traces

**User**: `/memory:traces --status=error`
**Action**: Show only failed operations

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:metrics` | View collected metrics |
| `/memory:health` | Health checks with timing |
| `/memory:status` | System status |
