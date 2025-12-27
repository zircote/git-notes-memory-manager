---
document_type: decisions
project_id: SPEC-2025-12-26-001
version: 1.0.0
last_updated: 2025-12-26T14:23:00Z
status: draft
---

# Multi-Worktree Sync Fix - Architecture Decision Records

## ADR-001: Use existing sync_notes_with_remote() instead of new implementation

### Status
Accepted

### Context
The Stop hook currently calls `push_notes_to_remote()` which pushes directly without fetching first, causing race conditions in multi-worktree environments. We need to implement a fetch→merge→push workflow.

### Decision
Use the existing `sync_notes_with_remote(push=True)` method from `git_ops.py` that was implemented for Issue #18.

### Rationale
1. **Already proven**: The method has been tested and used via `/memory:sync --remote`
2. **No new code**: Reduces risk of introducing bugs
3. **cat_sort_uniq integration**: Already configured for merge conflicts
4. **Consistent behavior**: Same workflow as manual sync command

### Consequences
- **Positive**: Minimal code change, proven reliability
- **Negative**: None identified

---

## ADR-002: Accept increased latency at session end

### Status
Accepted

### Context
The sync operation (fetch→merge→push) takes longer than a direct push. This happens at session end when `HOOK_STOP_PUSH_REMOTE=true`.

### Decision
Accept the additional 100-500ms latency.

### Rationale
1. **Non-interactive**: User doesn't wait for session end
2. **Reliability > speed**: Correct sync more important than speed
3. **Happens once**: Only at session end, not during work

### Consequences
- **Positive**: Eliminates race conditions
- **Negative**: Slightly longer session teardown (imperceptible to user)

---

## ADR-003: Maintain non-blocking exception handling

### Status
Accepted

### Context
The current exception handling ensures push failures don't block session termination. We need to maintain this behavior.

### Decision
Keep the existing try/except pattern that logs failures but doesn't raise.

### Rationale
1. **User experience**: Session should end cleanly regardless of network issues
2. **Retry semantics**: Next session will attempt sync again
3. **Debugging**: Failures are logged for troubleshooting

### Code Pattern
```python
try:
    result = git_ops.sync_notes_with_remote(push=True)
    if any(result.values()):
        logger.debug("Synced notes with remote on session stop: %s", result)
except Exception as e:
    logger.debug("Remote sync on stop skipped: %s", e)
# Session continues regardless
```

### Consequences
- **Positive**: Consistent behavior with current implementation
- **Negative**: Sync failures may go unnoticed (mitigated by logging)

---

## ADR-004: Log sync results per namespace

### Status
Accepted

### Context
`sync_notes_with_remote()` returns a dict mapping namespace to success boolean, unlike `push_notes_to_remote()` which returns a single boolean.

### Decision
Log the full result dict for debugging visibility.

### Rationale
1. **Granular debugging**: See which namespaces succeeded/failed
2. **Troubleshooting**: Helps identify namespace-specific issues
3. **Minimal overhead**: Just logging, no behavioral change

### Log Format
```
DEBUG: Synced notes with remote on session stop: {'progress': True, 'decisions': True}
```

### Consequences
- **Positive**: Better observability
- **Negative**: Slightly more verbose logs

---

## ADR-005: No retry logic for sync failures

### Status
Accepted

### Context
We considered adding retry logic for transient network failures during sync.

### Decision
Do not implement retry logic in this fix.

### Rationale
1. **Scope discipline**: Fix addresses race condition, not reliability
2. **Next session retry**: Sync will be attempted on next SessionStart
3. **Manual fallback**: User can run `/memory:sync --remote` if needed
4. **YAGNI**: Simple fix preferred over complex retry logic

### Consequences
- **Positive**: Minimal code change, reduced complexity
- **Negative**: Transient failures may require manual intervention

---

## Decision Summary

| ADR | Decision | Impact |
|-----|----------|--------|
| ADR-001 | Use existing sync method | Minimal code change |
| ADR-002 | Accept latency increase | Imperceptible |
| ADR-003 | Keep non-blocking exceptions | Consistent behavior |
| ADR-004 | Log per-namespace results | Better debugging |
| ADR-005 | No retry logic | Scope discipline |
