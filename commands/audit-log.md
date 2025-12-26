---
description: View the secrets filtering audit log
argument-hint: "[--since <time>] [--namespace <ns>] [--type <type>] [--json] [--limit <n>]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
AUDIT-LOG(1)                                     User Commands                                     AUDIT-LOG(1)

NAME
    audit-log - View the secrets filtering audit log

SYNOPSIS
    /memory:audit-log [OPTIONS]

DESCRIPTION
    View the audit log of secrets filtering operations. The audit log records
    all detections, filtering actions, and allowlist changes for compliance.

OPTIONS
    --since <time>        Show entries after this time (e.g., "1h", "24h", "7d")
    --namespace <ns>      Filter to specific namespace
    --type <type>         Filter by event type: detection, filter, scan, allowlist
    --json                Output in JSON format (one entry per line)
    --limit <n>           Maximum entries to show (default: 50)
    --help, -h            Show this help message

TIME FORMATS
    Relative: 1h (1 hour), 24h (24 hours), 7d (7 days), 30d (30 days)
    Absolute: 2024-01-15 or 2024-01-15T10:30:00

EXAMPLES
    /memory:audit-log
        Show recent audit entries (last 50)

    /memory:audit-log --since 24h
        Show entries from the last 24 hours

    /memory:audit-log --type detection --limit 100
        Show last 100 detection events

    /memory:audit-log --namespace decisions --json
        JSON output for decisions namespace

    /memory:audit-log --type allowlist
        Show allowlist changes only

SEE ALSO
    /memory:scan-secrets - Scan memories for secrets
    /memory:secrets-allowlist - Manage allowlist

                                                                                                 AUDIT-LOG(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:audit-log - View Secrets Audit Log

View the audit log of secrets filtering operations for compliance and debugging.

## Your Task

You will query and display the audit log based on the provided filters.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Parse the following flags:
- `--since <time>`: Time filter (e.g., "1h", "24h", "7d")
- `--namespace <ns>`: Namespace filter
- `--type <type>`: Event type filter (detection, filter, scan, allowlist)
- `--json`: Output as JSON Lines
- `--limit <n>`: Maximum entries (default: 50)

</step>

<step number="2" name="Query Audit Log">

**Query with filters**:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
SINCE="${SINCE:-}"        # e.g., "24h"
NAMESPACE="${NAMESPACE:-}"
EVENT_TYPE="${EVENT_TYPE:-}"
JSON_OUTPUT="${JSON_OUTPUT:-false}"
LIMIT="${LIMIT:-50}"

uv run --directory "$PLUGIN_ROOT" python3 -c "
import json
import sys
from datetime import UTC, datetime, timedelta
from git_notes_memory.security import get_audit_logger

since_str = '${SINCE}'
namespace = '${NAMESPACE}' or None
event_type = '${EVENT_TYPE}' or None
json_output = '${JSON_OUTPUT}' == 'true'
limit = int('${LIMIT}' or 50)

# Parse since time
since = None
if since_str:
    if since_str.endswith('h'):
        hours = int(since_str[:-1])
        since = datetime.now(UTC) - timedelta(hours=hours)
    elif since_str.endswith('d'):
        days = int(since_str[:-1])
        since = datetime.now(UTC) - timedelta(days=days)
    elif 'T' in since_str or '-' in since_str:
        # Try ISO format
        try:
            since = datetime.fromisoformat(since_str.replace('Z', '+00:00'))
        except:
            print(f'⚠️  Could not parse time: {since_str}')

logger = get_audit_logger()

entries = list(logger.query(
    since=since,
    namespace=namespace,
    event_type=event_type,
    limit=limit,
))

if json_output:
    for entry in entries:
        print(json.dumps(entry.to_dict()))
else:
    print('## Secrets Audit Log\n')

    if not entries:
        print('*No entries found matching filters.*')
        print()
        if since_str:
            print(f'Filters applied: since={since_str}', end='')
            if namespace:
                print(f', namespace={namespace}', end='')
            if event_type:
                print(f', type={event_type}', end='')
            print()
    else:
        # Group by event type for summary
        by_type = {}
        for e in entries:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1

        print('### Summary')
        print(f'Showing **{len(entries)}** entries')
        if since_str:
            print(f' since {since_str}')
        print()

        print('| Event Type | Count |')
        print('|------------|-------|')
        for t, c in sorted(by_type.items()):
            print(f'| {t} | {c} |')
        print()

        print('### Entries\n')
        print('| Timestamp | Type | Namespace | Secrets | Action | Details |')
        print('|-----------|------|-----------|---------|--------|---------|')

        for entry in entries:
            ts = entry.timestamp[:19]  # Truncate to seconds
            types = ', '.join(entry.secret_types[:2])
            if len(entry.secret_types) > 2:
                types += f' +{len(entry.secret_types) - 2}'

            # Truncate details for display
            details = ''
            if entry.details:
                if 'reason' in entry.details:
                    details = str(entry.details['reason'])[:30]
                elif 'had_secrets' in entry.details:
                    details = f\"had_secrets={entry.details['had_secrets']}\"
                elif 'original_length' in entry.details:
                    details = f\"{entry.details['original_length']}→{entry.details['filtered_length']} chars\"

            print(f'| {ts} | {entry.event_type} | {entry.namespace or \"-\"} | {types or \"-\"} | {entry.action} | {details} |')

        print()
        if len(entries) == limit:
            print(f'*Showing first {limit} entries. Use --limit for more.*')
"
```

</step>

<step number="3" name="Show Statistics" if="no entries or --stats flag">

**Show overall statistics**:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"

uv run --directory "$PLUGIN_ROOT" python3 -c "
from git_notes_memory.security import get_audit_logger

logger = get_audit_logger()
stats = logger.get_stats()

print('### Overall Statistics\n')
print('| Metric | Value |')
print('|--------|-------|')
print(f'| Total Events | {stats[\"total_events\"]} |')
print(f'| Detections | {stats.get(\"detections\", 0)} |')
print(f'| Filters Applied | {stats.get(\"filters\", 0)} |')
print(f'| Scans | {stats.get(\"scans\", 0)} |')
print(f'| Allowlist Changes | {stats.get(\"allowlist_changes\", 0)} |')

if stats.get('by_namespace'):
    print()
    print('### By Namespace')
    print('| Namespace | Events |')
    print('|-----------|--------|')
    for ns, count in stats['by_namespace'].items():
        print(f'| {ns} | {count} |')

if stats.get('by_type'):
    print()
    print('### By Secret Type')
    print('| Type | Detections |')
    print('|------|------------|')
    for t, count in sorted(stats['by_type'].items(), key=lambda x: -x[1])[:10]:
        print(f'| {t} | {count} |')
"
```

</step>

## Output Sections

| Section | Description |
|---------|-------------|
| Summary | Entry counts by type |
| Entries | Table of audit log entries |
| Statistics | Overall statistics (if requested) |

## Output Formats

- **Human readable** (default): Formatted tables
- **JSON** (--json): One JSON object per line, suitable for processing

## Examples

**User**: `/memory:audit-log`
**Action**: Show last 50 entries

**User**: `/memory:audit-log --since 24h --type detection`
**Action**: Show detections from last 24 hours

**User**: `/memory:audit-log --json --limit 1000`
**Action**: Export last 1000 entries as JSON

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:scan-secrets` | Scan memories for secrets |
| `/memory:secrets-allowlist` | Manage allowlist |
| `/memory:test-secret` | Test secret detection |
