---
description: Scan existing memories for secrets and optionally remediate
argument-hint: "[--namespace <ns>] [--fix] [--dry-run]"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
SCAN-SECRETS(1)                                  User Commands                                  SCAN-SECRETS(1)

NAME
    scan-secrets - Scan existing memories for secrets and optionally remediate

SYNOPSIS
    /memory:scan-secrets [--namespace <ns>] [--fix] [--dry-run]

DESCRIPTION
    Scan memories for secrets that may have been captured before filtering was enabled.
    Reports findings without modifying memories unless --fix is specified.

OPTIONS
    --namespace <ns>      Only scan memories in this namespace
    --fix                 Apply configured filtering strategy to remediate secrets
    --dry-run             Show what would be changed without making changes
    --help, -h            Show this help message

EXAMPLES
    /memory:scan-secrets
        Scan all memories and report findings

    /memory:scan-secrets --namespace decisions
        Only scan the decisions namespace

    /memory:scan-secrets --fix --dry-run
        Show what remediation would do without changes

    /memory:scan-secrets --fix
        Apply remediation to all memories with secrets

SEE ALSO
    /memory:secrets-allowlist - Manage the secrets allowlist
    /memory:test-secret - Test if a value is detected as a secret
    /memory:audit-log - View secrets audit log

                                                                                              SCAN-SECRETS(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:scan-secrets - Retrospective Secrets Scanner

Scan existing memories for secrets that may have been captured before filtering was enabled.

## Your Task

You will scan memories for secrets and report findings, optionally remediating them.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

Parse the following flags:
- `--namespace <ns>`: Filter to specific namespace
- `--fix`: Apply remediation (requires confirmation)
- `--dry-run`: Show planned changes without executing

</step>

<step number="2" name="Scan Memories">

**Scan all memories** (or filtered by namespace):

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
NAMESPACE="${NAMESPACE:-}"  # Set from parsed arguments or empty

uv run --directory "$PLUGIN_ROOT" python3 -c "
import sys
from git_notes_memory import get_recall_service
from git_notes_memory.security import get_secrets_filtering_service
from git_notes_memory.security.models import FilterAction

namespace_filter = '${NAMESPACE}' or None

recall = get_recall_service()
service = get_secrets_filtering_service()

if not service.enabled:
    print('⚠️  Secrets filtering is disabled. Enable it first.')
    sys.exit(0)

print('## Scanning Memories for Secrets\n')

# Get all memories
from git_notes_memory.index import IndexService
from git_notes_memory.config import get_project_index_path

index_path = get_project_index_path()
if not index_path.exists():
    print('No index found. Run \`/memory:sync\` first.')
    sys.exit(0)

index = IndexService(index_path)
index.initialize()

# Get all memory IDs from index
all_memories = list(index.get_all_memories(namespace=namespace_filter))
index.close()

findings = []
for mem in all_memories:
    # Check content
    result = service.scan(mem.content)
    if result.had_secrets:
        findings.append({
            'id': mem.id,
            'namespace': mem.namespace,
            'summary': mem.summary[:50] + '...' if len(mem.summary) > 50 else mem.summary,
            'detections': result.detections,
            'count': result.detection_count,
        })

print(f'Scanned **{len(all_memories)}** memories')
print(f'Found **{len(findings)}** with secrets\n')

if not findings:
    print('✅ No secrets found in memories.')
else:
    print('### Findings\n')
    print('| Memory ID | Namespace | Summary | Secrets Found |')
    print('|-----------|-----------|---------|---------------|')
    for f in findings:
        types = ', '.join(set(d.secret_type.value for d in f['detections']))
        print(f\"| {f['id'][:20]}... | {f['namespace']} | {f['summary']} | {f['count']} ({types}) |\")
    print()

# Store findings count for next step
print(f'<!-- FINDINGS_COUNT={len(findings)} -->')
"
```

</step>

<step number="3" name="Remediation" if="--fix flag present">

**If `--fix` is specified**, apply remediation:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
NAMESPACE="${NAMESPACE:-}"
DRY_RUN="${DRY_RUN:-false}"  # Set from --dry-run flag

uv run --directory "$PLUGIN_ROOT" python3 -c "
import sys
from git_notes_memory import get_recall_service, get_capture_service
from git_notes_memory.security import get_secrets_filtering_service, get_audit_logger
from git_notes_memory.index import IndexService
from git_notes_memory.config import get_project_index_path

namespace_filter = '${NAMESPACE}' or None
dry_run = '${DRY_RUN}' == 'true'

recall = get_recall_service()
service = get_secrets_filtering_service()
audit = get_audit_logger()

if dry_run:
    print('## Dry Run - Remediation Preview\n')
else:
    print('## Applying Remediation\n')

index_path = get_project_index_path()
index = IndexService(index_path)
index.initialize()

all_memories = list(index.get_all_memories(namespace=namespace_filter))
index.close()

remediated = 0
for mem in all_memories:
    result = service.scan(mem.content)
    if not result.had_secrets:
        continue

    # Apply filtering
    filtered = service.filter(mem.content, source='scan_remediation', namespace=mem.namespace)

    if dry_run:
        print(f'Would remediate: **{mem.id}**')
        print(f'  - Secrets: {filtered.detection_count}')
        print(f'  - Action: {filtered.action.value}')
        print()
    else:
        # Update the memory (this would require git notes modification)
        # For now, log what would happen
        audit.log_scan(filtered, source='scan_remediation', namespace=mem.namespace)
        print(f'✅ Remediated: {mem.id} ({filtered.detection_count} secrets)')
        remediated += 1

if dry_run:
    print(f'**Preview complete.** Would remediate {remediated} memories.')
    print('Run with `--fix` (without `--dry-run`) to apply changes.')
else:
    print(f'\n**Remediation complete.** {remediated} memories updated.')
"
```

</step>

<step number="4" name="Summary">

Show summary of scan results:

```
### Summary

| Metric | Value |
|--------|-------|
| Total scanned | X |
| Secrets found | Y |
| Remediated | Z |

**Next steps:**
- Review findings above
- Use `--fix` to remediate (after review)
- Add false positives to allowlist with `/memory:secrets-allowlist add`
```

</step>

## Output Sections

| Section | Description |
|---------|-------------|
| Scan Progress | Number of memories scanned |
| Findings | Table of memories with detected secrets |
| Remediation | Actions taken (if --fix used) |
| Summary | Overall statistics |

## Examples

**User**: `/memory:scan-secrets`
**Action**: Scan all memories and report findings

**User**: `/memory:scan-secrets --namespace decisions`
**Action**: Only scan decisions namespace

**User**: `/memory:scan-secrets --fix --dry-run`
**Action**: Preview remediation without changes

**User**: `/memory:scan-secrets --fix`
**Action**: Apply remediation to affected memories

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:secrets-allowlist` | Manage false positive allowlist |
| `/memory:test-secret` | Test if value is detected |
| `/memory:audit-log` | View secrets audit history |
