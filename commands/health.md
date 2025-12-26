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
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 "$PLUGIN_ROOT/scripts/health.py" $ARGUMENTS
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
