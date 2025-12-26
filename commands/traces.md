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
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 "$PLUGIN_ROOT/scripts/traces.py" $ARGUMENTS
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
