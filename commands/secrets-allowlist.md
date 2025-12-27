---
description: Manage the secrets filtering allowlist
argument-hint: "<add|remove|list> [--hash <hash>] [--namespace <ns>] [--reason <reason>]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
SECRETS-ALLOWLIST(1)                             User Commands                             SECRETS-ALLOWLIST(1)

NAME
    secrets-allowlist - Manage the secrets filtering allowlist

SYNOPSIS
    /memory:secrets-allowlist <add|remove|list> [OPTIONS]

DESCRIPTION
    Manage the allowlist of approved secrets. Allowlisted secrets bypass filtering.
    This is useful for false positives or intentionally included values.

SUBCOMMANDS
    add         Add a secret hash to the allowlist
    remove      Remove a secret hash from the allowlist
    list        List all allowlisted entries

OPTIONS
    --hash <hash>         The secret hash (from scan-secrets output)
    --namespace <ns>      Limit allowlist entry to specific namespace
    --reason <reason>     Reason for allowlisting (required for add)
    --help, -h            Show this help message

EXAMPLES
    /memory:secrets-allowlist list
        Show all allowlisted entries

    /memory:secrets-allowlist add --hash abc123 --reason "False positive - example code"
        Add a hash to global allowlist

    /memory:secrets-allowlist add --hash def456 --namespace decisions --reason "Intentional"
        Add a namespace-scoped allowlist entry

    /memory:secrets-allowlist remove --hash abc123
        Remove an entry from allowlist

SEE ALSO
    /memory:scan-secrets - Scan memories for secrets
    /memory:test-secret - Test if value is detected
    /memory:audit-log - View allowlist changes in audit log

                                                                                        SECRETS-ALLOWLIST(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:secrets-allowlist - Manage Secrets Allowlist

Manage the allowlist of approved secrets that bypass filtering.

## Your Task

You will manage the secrets allowlist based on the subcommand provided.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Parse the subcommand and flags:
- Subcommand: `add`, `remove`, or `list`
- `--hash <hash>`: The secret hash to add/remove
- `--namespace <ns>`: Optional namespace scope
- `--reason <reason>`: Reason for allowlisting (required for add)

</step>

<step number="2a" name="List Allowlist" if="subcommand is 'list'">

**Show all allowlisted entries**:

```bash
uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
from git_notes_memory.security import get_allowlist_manager

manager = get_allowlist_manager()
entries = list(manager.list_entries())

print('## Secrets Allowlist\n')

if not entries:
    print('*No entries in allowlist.*')
    print()
    print('Use \`/memory:secrets-allowlist add\` to add entries.')
else:
    print('| Hash (truncated) | Namespace | Reason | Added By | Added At |')
    print('|------------------|-----------|--------|----------|----------|')
    for entry in entries:
        ns = entry.namespace or '(global)'
        hash_short = entry.secret_hash[:16] + '...'
        added_at = entry.added_at.strftime('%Y-%m-%d') if entry.added_at else 'Unknown'
        print(f'| {hash_short} | {ns} | {entry.reason} | {entry.added_by or \"system\"} | {added_at} |')

print(f'\n**Total entries:** {len(entries)}')
"
```

</step>

<step number="2b" name="Add to Allowlist" if="subcommand is 'add'">

**Add a new allowlist entry**:

```bash
HASH="${HASH}"       # From --hash argument
NAMESPACE="${NAMESPACE:-}"  # From --namespace argument or empty
REASON="${REASON}"   # From --reason argument

uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
import sys
from git_notes_memory.security import get_allowlist_manager, get_audit_logger

hash_val = '${HASH}'
namespace = '${NAMESPACE}' or None
reason = '${REASON}'

if not hash_val:
    print('❌ Error: --hash is required')
    sys.exit(1)

if not reason:
    print('❌ Error: --reason is required for add')
    sys.exit(1)

manager = get_allowlist_manager()
audit = get_audit_logger()

try:
    entry = manager.add(
        secret_hash=hash_val,
        reason=reason,
        namespace=namespace,
        added_by='user',
    )

    # Log to audit
    audit.log_allowlist_change(
        action='add',
        secret_hash=hash_val,
        reason=reason,
        namespace=namespace or '',
        added_by='user',
    )

    print('## Entry Added\n')
    print(f'✅ Added to allowlist:')
    print(f'  - **Hash:** {hash_val[:16]}...')
    print(f'  - **Namespace:** {namespace or \"(global)\"}')
    print(f'  - **Reason:** {reason}')
    print()
    print('Future captures/scans will skip this secret.')

except Exception as e:
    print(f'❌ Error: {e}')
    sys.exit(1)
"
```

</step>

<step number="2c" name="Remove from Allowlist" if="subcommand is 'remove'">

**Remove an allowlist entry**:

```bash
HASH="${HASH}"  # From --hash argument

uv run --directory "${CLAUDE_PLUGIN_ROOT:-.}" python3 -c "
import sys
from git_notes_memory.security import get_allowlist_manager, get_audit_logger

hash_val = '${HASH}'

if not hash_val:
    print('❌ Error: --hash is required')
    sys.exit(1)

manager = get_allowlist_manager()
audit = get_audit_logger()

try:
    removed = manager.remove(secret_hash=hash_val)

    if removed:
        audit.log_allowlist_change(
            action='remove',
            secret_hash=hash_val,
            reason='User requested removal',
            added_by='user',
        )
        print('## Entry Removed\n')
        print(f'✅ Removed from allowlist: {hash_val[:16]}...')
        print()
        print('This secret will now be detected and filtered.')
    else:
        print(f'⚠️  Hash not found in allowlist: {hash_val[:16]}...')

except Exception as e:
    print(f'❌ Error: {e}')
    sys.exit(1)
"
```

</step>

## Output Sections

| Section | Description |
|---------|-------------|
| List | Table of all allowlist entries |
| Add Confirmation | Details of added entry |
| Remove Confirmation | Confirmation of removal |

## Examples

**User**: `/memory:secrets-allowlist list`
**Action**: Show all allowlisted secrets

**User**: `/memory:secrets-allowlist add --hash abc123def456 --reason "Example API key in docs"`
**Action**: Add hash to global allowlist

**User**: `/memory:secrets-allowlist remove --hash abc123def456`
**Action**: Remove hash from allowlist

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:scan-secrets` | Scan memories for secrets |
| `/memory:test-secret` | Test if value is detected |
| `/memory:audit-log` | View allowlist changes |
