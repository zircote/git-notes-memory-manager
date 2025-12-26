---
description: Review and approve/reject pending implicit memories
argument-hint: "[--list | --approve <id> | --reject <id> | --approve-all | --cleanup]"
allowed-tools: ["Bash", "Read", "AskUserQuestion"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
REVIEW(1)                                            User Commands                                            REVIEW(1)

NAME
    review - Review and approve/reject pending implicit memories

SYNOPSIS
    /memory:review [--list] [--approve <id>] [--reject <id>] [--approve-all] [--cleanup]

DESCRIPTION
    Review pending implicit memories captured by the subconsciousness layer.
    These are memories auto-extracted from your sessions that need human approval.

    Without arguments, shows an interactive review interface.

OPTIONS
    --help, -h            Show this help message
    --list                List all pending captures without interaction
    --approve <id>        Approve a specific capture by ID
    --reject <id>         Reject a specific capture by ID
    --approve-all         Approve all pending captures
    --cleanup             Remove expired/rejected captures and show stats

EXAMPLES
    /memory:review                    Interactive review of pending memories
    /memory:review --list             Show pending captures
    /memory:review --approve abc123   Approve capture with ID abc123
    /memory:review --reject abc123    Reject capture with ID abc123
    /memory:review --approve-all      Approve all pending captures
    /memory:review --cleanup          Clean up old captures

SEE ALSO
    /memory:status for system status
    /memory:capture for explicit memory capture

                                                                      REVIEW(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:review - Review Pending Implicit Memories

Review and approve/reject memories captured by the subconsciousness layer.

## Your Task

Help the user review pending implicit captures and decide which to keep.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Determine the action:
- No args or `--list`: List pending captures
- `--approve <id>`: Approve specific capture
- `--reject <id>`: Reject specific capture
- `--approve-all`: Approve all pending
- `--cleanup`: Remove old captures

</step>

<step number="2" name="Check Subconsciousness Status">

First check if subconsciousness is enabled:

```bash
uv run python3 -c "
from git_notes_memory.subconsciousness import is_subconsciousness_enabled

if not is_subconsciousness_enabled():
    print('## Subconsciousness Not Enabled')
    print('')
    print('The subconsciousness layer is not enabled. To enable it:')
    print('')
    print('\`\`\`bash')
    print('export MEMORY_SUBCONSCIOUSNESS_ENABLED=true')
    print('export MEMORY_LLM_PROVIDER=anthropic  # or openai, ollama')
    print('export ANTHROPIC_API_KEY=your-key    # if using anthropic')
    print('\`\`\`')
    exit(1)
else:
    print('Subconsciousness enabled')
"
```

If not enabled, show the message and stop.

</step>

<step number="3" name="Execute Review Action">

**For --list or no args (list pending captures)**:

```bash
uv run python3 -c "
from git_notes_memory.subconsciousness.implicit_capture_service import get_implicit_capture_service

service = get_implicit_capture_service()
pending = service.get_pending_captures(limit=20)
stats = service.get_capture_stats()

print('## Pending Implicit Memories')
print('')

if not pending:
    print('No pending memories to review.')
    print('')
    print('Pending memories are auto-captured from your sessions when:')
    print('- Subconsciousness is enabled')
    print('- Memory-worthy content is detected')
    print('- Confidence is medium (0.7-0.9)')
    print('')
    print('High confidence captures (>0.9) are auto-approved.')
    exit(0)

print(f'**{len(pending)} pending** | {stats.get(\"approved\", 0)} approved | {stats.get(\"rejected\", 0)} rejected | {stats.get(\"expired\", 0)} expired')
print('')

for i, cap in enumerate(pending, 1):
    mem = cap.memory
    conf = mem.confidence.overall

    # Truncate summary if too long
    summary = mem.summary[:80] + '...' if len(mem.summary) > 80 else mem.summary

    print(f'### {i}. [{cap.id[:8]}] {summary}')
    print(f'- **Namespace**: {mem.namespace}')
    print(f'- **Confidence**: {conf:.0%}')

    # Show expiration
    import datetime
    if cap.expires_at:
        days_left = (cap.expires_at - datetime.datetime.now(datetime.timezone.utc)).days
        if days_left > 0:
            print(f'- **Expires in**: {days_left} days')
        else:
            print(f'- **Expires**: Today')

    # Show threat info if any
    if cap.threat_detection.level.value != 'none':
        print(f'- **Threat Level**: {cap.threat_detection.level.value}')

    print('')
    print(f'> {mem.content[:200]}...' if len(mem.content) > 200 else f'> {mem.content}')
    print('')
"
```

After showing the list, ask the user what they want to do using AskUserQuestion.

**For --approve <id>**:

```bash
CAPTURE_ID="$1"  # Extract from arguments
# Pass via environment variable to prevent shell injection
export MEMORY_CAPTURE_ID="$CAPTURE_ID"
uv run python3 -c "
import os
import sys
from git_notes_memory.subconsciousness.implicit_capture_service import get_implicit_capture_service
from git_notes_memory import get_capture_service

capture_id = os.environ.get('MEMORY_CAPTURE_ID', '')
if not capture_id:
    print('Error: Please provide a capture ID')
    sys.exit(1)

service = get_implicit_capture_service()

# Find the capture (might be partial ID)
pending = service.get_pending_captures(limit=100)
matches = [c for c in pending if c.id.startswith(capture_id)]

if not matches:
    print(f'No pending capture found with ID starting with: {capture_id}')
    sys.exit(1)

if len(matches) > 1:
    print(f'Multiple captures match \"{capture_id}\". Please be more specific:')
    for m in matches:
        print(f'  - {m.id}')
    sys.exit(1)

cap = matches[0]

# Approve it
if service.approve_capture(cap.id):
    # Now actually capture it to the memory system
    mem = cap.memory
    capture = get_capture_service()
    result = capture.capture(
        namespace=mem.namespace,
        summary=mem.summary,
        content=mem.content,
        spec=None,  # Could be set from session context
        tags=('implicit', 'approved'),
    )

    if result.success:
        print(f'Approved and captured: {mem.summary[:60]}...')
        print(f'Memory ID: {result.memory_id}')
    else:
        print(f'Approved but capture failed: {result.warning or result.error}')
else:
    print(f'Failed to approve capture {capture_id}')
"
```

**For --reject <id>**:

```bash
CAPTURE_ID="$1"
# Pass via environment variable to prevent shell injection
export MEMORY_CAPTURE_ID="$CAPTURE_ID"
uv run python3 -c "
import os
import sys
from git_notes_memory.subconsciousness.implicit_capture_service import get_implicit_capture_service

capture_id = os.environ.get('MEMORY_CAPTURE_ID', '')
if not capture_id:
    print('Error: Please provide a capture ID')
    sys.exit(1)

service = get_implicit_capture_service()

# Find the capture
pending = service.get_pending_captures(limit=100)
matches = [c for c in pending if c.id.startswith(capture_id)]

if not matches:
    print(f'No pending capture found with ID starting with: {capture_id}')
    sys.exit(1)

if len(matches) > 1:
    print(f'Multiple captures match \"{capture_id}\". Please be more specific:')
    for m in matches:
        print(f'  - {m.id}')
    sys.exit(1)

cap = matches[0]

if service.reject_capture(cap.id):
    print(f'Rejected: {cap.memory.summary[:60]}...')
else:
    print(f'Failed to reject capture {capture_id}')
"
```

**For --approve-all**:

```bash
uv run python3 -c "
from git_notes_memory.subconsciousness.implicit_capture_service import get_implicit_capture_service
from git_notes_memory import get_capture_service

service = get_implicit_capture_service()
capture = get_capture_service()
pending = service.get_pending_captures(limit=100)

if not pending:
    print('No pending captures to approve.')
    exit(0)

print(f'Approving {len(pending)} pending captures...')
print('')

approved = 0
failed = 0

for cap in pending:
    if service.approve_capture(cap.id):
        mem = cap.memory
        result = capture.capture(
            namespace=mem.namespace,
            summary=mem.summary,
            content=mem.content,
            tags=('implicit', 'approved'),
        )
        if result.success:
            approved += 1
            print(f'[OK] {mem.summary[:50]}...')
        else:
            failed += 1
            print(f'[WARN] {mem.summary[:50]}... (capture failed)')
    else:
        failed += 1
        print(f'[FAIL] {cap.id[:8]}')

print('')
print(f'Approved: {approved} | Failed: {failed}')
"
```

**For --cleanup**:

```bash
uv run python3 -c "
from git_notes_memory.subconsciousness.implicit_capture_service import get_implicit_capture_service

service = get_implicit_capture_service()

# Expire old pending
expired = service.expire_pending_captures()

# Cleanup reviewed (30 days old)
cleaned = service.cleanup_old_captures(older_than_days=30)

# Get current stats
stats = service.get_capture_stats()

print('## Cleanup Complete')
print('')
print(f'- Expired {expired} old pending captures')
print(f'- Removed {cleaned} old reviewed captures')
print('')
print('### Current Stats')
print('| Status | Count |')
print('|--------|-------|')
for status, count in sorted(stats.items()):
    print(f'| {status} | {count} |')
"
```

</step>

<step number="4" name="Interactive Review">

If `--list` was used or no arguments, after showing pending captures, use AskUserQuestion to let the user decide:

```json
{
  "questions": [
    {
      "header": "Review Action",
      "question": "What would you like to do with these pending memories?",
      "options": [
        {"label": "Review individually", "description": "Go through each pending memory and decide"},
        {"label": "Approve all", "description": "Approve all pending memories at once"},
        {"label": "Do nothing", "description": "Leave them pending for later review"},
        {"label": "Cleanup", "description": "Remove expired and old captures"}
      ],
      "multiSelect": false
    }
  ]
}
```

Based on the response:
- "Review individually": Show each memory and ask approve/reject
- "Approve all": Run the --approve-all logic
- "Do nothing": End the command
- "Cleanup": Run the --cleanup logic

</step>

## Output Sections

| Section | Description |
|---------|-------------|
| Status | Whether subconsciousness is enabled |
| Pending List | Memories awaiting review |
| Stats | Counts by status |

## Examples

**User**: `/memory:review`
**Action**: Show pending captures and ask for action

**User**: `/memory:review --list`
**Action**: Just list pending captures without interaction

**User**: `/memory:review --approve abc123`
**Action**: Approve and capture the memory with ID starting with abc123

**User**: `/memory:review --reject abc123`
**Action**: Reject the memory

**User**: `/memory:review --approve-all`
**Action**: Approve all pending captures

**User**: `/memory:review --cleanup`
**Action**: Remove expired/old captures

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:status` | Check if subconsciousness is enabled |
| `/memory:capture` | Manually capture a memory |
| `/memory:recall` | Search existing memories |
