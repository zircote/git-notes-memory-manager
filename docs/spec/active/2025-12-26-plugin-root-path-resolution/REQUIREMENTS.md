---
document_type: requirements
project_id: SPEC-2025-12-26-002
version: 1.0.0
last_updated: 2025-12-26T21:00:00Z
status: draft
---

# PLUGIN_ROOT Path Resolution Fix - Product Requirements Document

## Executive Summary

The plugin's command files use a hardcoded path pattern for resolving `PLUGIN_ROOT` that fails when the plugin is installed from a marketplace. This affects 12+ commands across the plugin, rendering them non-functional for marketplace users. The fix will replace filesystem-based script execution with Python module imports, providing installation-agnostic command execution.

## Problem Statement

### The Problem

When `CLAUDE_PLUGIN_ROOT` environment variable is not set, command files fall back to a glob pattern that hardcodes `git-notes-memory/memory-capture` in the path. Marketplace installations use `{marketplace-name}/memory-capture` structure, causing the glob to fail and leaving `PLUGIN_ROOT` empty.

### Impact

- **All marketplace users** cannot use 12+ commands
- Commands fail with: `error: a value is required for '--directory <DIRECTORY>' but none was supplied`
- Users must manually set `CLAUDE_PLUGIN_ROOT` as workaround

### Current State

```bash
# Current (broken) pattern in commands:
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"

# Actual marketplace path:
~/.claude/plugins/cache/zircote-claude-marketplace/memory-capture/

# Pattern mismatch → PLUGIN_ROOT="" → command fails
```

## Goals and Success Criteria

### Primary Goal

Enable all commands to work regardless of plugin installation method (marketplace, direct, or source).

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Commands working from marketplace | 100% | Manual test all 12+ commands |
| Path resolution failures | 0 | No directory errors in command output |
| Backwards compatibility | 100% | Existing installations continue working |

### Non-Goals (Explicit Exclusions)

- Adding new commands
- Changing command behavior/output (only fixing path resolution)
- Modifying plugin packaging structure

## Affected Commands

| Command | File | Lines | Script Called |
|---------|------|-------|---------------|
| `/memory:metrics` | `commands/metrics.md` | 76-77 | `scripts/metrics.py` |
| `/memory:health` | `commands/health.md` | 76-77 | `scripts/health.py` |
| `/memory:traces` | `commands/traces.md` | 79-80 | `scripts/traces.py` |
| `/memory:audit-log` | `commands/audit-log.md` | 95, 208 | Multiple scripts |
| `/memory:capture` | `commands/capture.md` | 90 | Capture logic |
| `/memory:recall` | `commands/recall.md` | 81 | Recall logic |
| `/memory:scan-secrets` | `commands/scan-secrets.md` | 85, 160 | Secrets scanning |
| `/memory:search` | `commands/search.md` | 76, 103 | Search logic |
| `/memory:secrets-allowlist` | `commands/secrets-allowlist.md` | 91, 125, 187 | Allowlist management |
| `/memory:status` | `commands/status.md` | 67, 107 | Status display |
| `/memory:sync` | `commands/sync.md` | 87, 107, 127, 151, 180, 205, 234 | Sync operations |
| `/memory:test-secret` | `commands/test-secret.md` | 87 | Secret testing |
| `/memory:validate` | `commands/validate.md` | 69 | Validation |

## Functional Requirements

### Must Have (P0)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | Commands work from marketplace install | Core bug fix | All 12+ commands execute without path errors |
| FR-002 | Commands work from direct install | Backwards compat | Existing installs continue working |
| FR-003 | Commands work from source repo | Dev experience | Running from source works |
| FR-004 | No environment variable required | User experience | Works without setting CLAUDE_PLUGIN_ROOT |

### Should Have (P1)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-101 | Graceful error messages | UX | Clear error if module import fails |
| FR-102 | Consistent pattern across all commands | Maintainability | All commands use same resolution approach |

## Non-Functional Requirements

### Maintainability

- Single pattern used across all commands (no variations)
- No filesystem assumptions in command logic
- Module imports follow Python best practices

### Reliability

- Commands work without any environment setup
- No silent failures - errors are reported clearly

## Technical Constraints

- Must use existing Python module structure (`git_notes_memory.*`)
- Must work with `uv run` execution model
- Cannot change plugin.json or marketplace structure

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Module import path differences | Low | High | Test all installation scenarios |
| Missing module exports | Medium | Medium | Verify all needed functions are exported |
| uv caching issues | Low | Low | Test with clean cache |

## Open Questions

- [x] Which option is best? → Option 2 (Python module imports) per issue recommendation

## Appendix

### Root Cause Analysis

1. **Hardcoded namespace**: Path pattern hardcodes `git-notes-memory/` but marketplace uses `zircote-claude-marketplace/`
2. **Distribution gap**: `scripts/` directory may not be included in plugin packaging
3. **Fragile fallback**: Glob pattern is too specific and doesn't handle all installation scenarios

### Workaround (Current)

```bash
export CLAUDE_PLUGIN_ROOT="$HOME/.claude/plugins/cache/zircote-claude-marketplace/memory-capture"
```
