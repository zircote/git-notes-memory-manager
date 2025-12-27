---
document_type: implementation_plan
project_id: SPEC-2025-12-26-002
version: 1.0.0
last_updated: 2025-12-26T21:00:00Z
status: draft
estimated_effort: 2-3 hours
---

# PLUGIN_ROOT Path Resolution Fix - Implementation Plan

## Overview

Refactor all 12+ command files to use Python module imports instead of filesystem-based script execution. This is a targeted bug fix with minimal risk.

## Phase Summary

| Phase | Description | Tasks |
|-------|-------------|-------|
| Phase 1: Observability Commands | Fix metrics, health, traces | 3 tasks |
| Phase 2: Core Commands | Fix capture, recall, search, status | 4 tasks |
| Phase 3: Security Commands | Fix secrets-related commands | 4 tasks |
| Phase 4: Sync & Validation | Fix sync, validate, audit-log | 3 tasks |
| Phase 5: Testing & Verification | Test all installation scenarios | 2 tasks |

---

## Phase 1: Observability Commands

**Goal**: Fix `/memory:metrics`, `/memory:health`, `/memory:traces`
**Prerequisites**: None

### Task 1.1: Update metrics.md

- **Description**: Replace PLUGIN_ROOT script pattern with module import
- **File**: `commands/metrics.md:76-78`
- **Change**:
  ```bash
  # FROM:
  PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-...}"
  uv run --directory "$PLUGIN_ROOT" python3 "$PLUGIN_ROOT/scripts/metrics.py" $ARGUMENTS
  
  # TO:
  uv run python3 -c "
  from git_notes_memory.observability.metrics import get_metrics
  from git_notes_memory.observability.exporters.prometheus import export_prometheus_text
  import sys
  
  format_arg = 'text'
  for arg in sys.argv[1:]:
      if arg.startswith('--format='):
          format_arg = arg.split('=')[1]
  
  metrics = get_metrics()
  if format_arg == 'json':
      print(metrics.export_json())
  elif format_arg == 'prometheus':
      print(export_prometheus_text())
  else:
      print(metrics.export_text())
  " $ARGUMENTS
  ```
- **Acceptance Criteria**:
  - [ ] Command works without CLAUDE_PLUGIN_ROOT set
  - [ ] All format options work (text, json, prometheus)

### Task 1.2: Update health.md

- **Description**: Replace PLUGIN_ROOT script pattern with module import
- **File**: `commands/health.md:76-77`
- **Acceptance Criteria**:
  - [ ] Command works without CLAUDE_PLUGIN_ROOT set
  - [ ] Health checks display correctly

### Task 1.3: Update traces.md

- **Description**: Replace PLUGIN_ROOT script pattern with module import
- **File**: `commands/traces.md:79-80`
- **Acceptance Criteria**:
  - [ ] Command works without CLAUDE_PLUGIN_ROOT set
  - [ ] Trace data displays correctly

---

## Phase 2: Core Commands

**Goal**: Fix `/memory:capture`, `/memory:recall`, `/memory:search`, `/memory:status`
**Prerequisites**: None (can run in parallel with Phase 1)

### Task 2.1: Update capture.md

- **Description**: Replace any PLUGIN_ROOT patterns with module imports
- **File**: `commands/capture.md:90`
- **Acceptance Criteria**:
  - [ ] Capture command works from marketplace install

### Task 2.2: Update recall.md

- **Description**: Replace any PLUGIN_ROOT patterns with module imports
- **File**: `commands/recall.md:81`
- **Acceptance Criteria**:
  - [ ] Recall command works from marketplace install

### Task 2.3: Update search.md

- **Description**: Replace PLUGIN_ROOT patterns at lines 76 and 103
- **File**: `commands/search.md:76, 103`
- **Acceptance Criteria**:
  - [ ] Search command works from marketplace install

### Task 2.4: Update status.md

- **Description**: Replace PLUGIN_ROOT patterns at lines 67 and 107
- **File**: `commands/status.md:67, 107`
- **Acceptance Criteria**:
  - [ ] Status command works from marketplace install

---

## Phase 3: Security Commands

**Goal**: Fix secrets-related commands
**Prerequisites**: None (can run in parallel with Phases 1-2)

### Task 3.1: Update scan-secrets.md

- **Description**: Replace PLUGIN_ROOT patterns at lines 85 and 160
- **File**: `commands/scan-secrets.md:85, 160`
- **Acceptance Criteria**:
  - [ ] Scan secrets command works from marketplace install

### Task 3.2: Update secrets-allowlist.md

- **Description**: Replace PLUGIN_ROOT patterns at lines 91, 125, and 187
- **File**: `commands/secrets-allowlist.md:91, 125, 187`
- **Acceptance Criteria**:
  - [ ] All allowlist operations work from marketplace install

### Task 3.3: Update test-secret.md

- **Description**: Replace PLUGIN_ROOT pattern at line 87
- **File**: `commands/test-secret.md:87`
- **Acceptance Criteria**:
  - [ ] Test secret command works from marketplace install

### Task 3.4: Update audit-log.md

- **Description**: Replace PLUGIN_ROOT patterns at lines 95 and 208
- **File**: `commands/audit-log.md:95, 208`
- **Acceptance Criteria**:
  - [ ] Audit log command works from marketplace install

---

## Phase 4: Sync & Validation

**Goal**: Fix remaining commands
**Prerequisites**: None (can run in parallel)

### Task 4.1: Update sync.md

- **Description**: Replace PLUGIN_ROOT patterns at 7 locations (lines 87, 107, 127, 151, 180, 205, 234)
- **File**: `commands/sync.md`
- **Acceptance Criteria**:
  - [ ] All sync operations work from marketplace install

### Task 4.2: Update validate.md

- **Description**: Replace PLUGIN_ROOT pattern at line 69
- **File**: `commands/validate.md:69`
- **Acceptance Criteria**:
  - [ ] Validate command works from marketplace install

### Task 4.3: Review for any missed files

- **Description**: Grep for any remaining PLUGIN_ROOT patterns
- **Command**: `grep -r "PLUGIN_ROOT" commands/`
- **Acceptance Criteria**:
  - [ ] No PLUGIN_ROOT patterns remain in command files

---

## Phase 5: Testing & Verification

**Goal**: Verify fix across all installation scenarios
**Prerequisites**: Phases 1-4 complete

### Task 5.1: Test marketplace installation

- **Description**: Install plugin from marketplace and test all commands
- **Steps**:
  1. Unset CLAUDE_PLUGIN_ROOT
  2. Run each affected command
  3. Verify no "directory" errors
- **Acceptance Criteria**:
  - [ ] All 12+ commands work without errors

### Task 5.2: Test source repository

- **Description**: Run commands from source to verify backwards compatibility
- **Steps**:
  1. Run from git-notes-memory source directory
  2. Test all affected commands
- **Acceptance Criteria**:
  - [ ] All commands continue working from source

---

## Dependency Graph

```
Phase 1 ──┬──> Phase 5 (Testing)
Phase 2 ──┤
Phase 3 ──┤
Phase 4 ──┘
```

All implementation phases can run in parallel. Testing must wait for all phases.

## Risk Mitigation

| Risk | Mitigation Task | Phase |
|------|-----------------|-------|
| Missing module export | Verify exports exist before changing command | Each task |
| Breaking existing installs | Test from source repo | Phase 5 |

## Launch Checklist

- [ ] All command files updated
- [ ] No PLUGIN_ROOT patterns remain
- [ ] Tested from marketplace install
- [ ] Tested from source repo
- [ ] PR created and reviewed
- [ ] Issue #31 closed with commit reference
