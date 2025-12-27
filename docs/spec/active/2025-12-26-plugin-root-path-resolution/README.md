---
project_id: SPEC-2025-12-26-002
project_name: "PLUGIN_ROOT Path Resolution Fix"
slug: plugin-root-path-resolution
status: in-review
created: 2025-12-26T21:00:00Z
approved: null
started: null
completed: null
expires: 2026-03-26T21:00:00Z
superseded_by: null
tags: [bug-fix, plugin, path-resolution, marketplace, commands]
stakeholders: []
github_issue: https://github.com/zircote/git-notes-memory/issues/31
---

# PLUGIN_ROOT Path Resolution Fix

**Project ID**: SPEC-2025-12-26-002
**GitHub Issue**: [#31](https://github.com/zircote/git-notes-memory/issues/31)
**Status**: In Review

## Summary

Fix the PLUGIN_ROOT path resolution logic in all command files that fails when the plugin is installed from a marketplace (e.g., `zircote-claude-marketplace`) instead of directly. Currently causes 12+ commands to fail with directory resolution errors.

## Problem

Commands hardcode `git-notes-memory/memory-capture` in path resolution fallback, but marketplace installations use `{marketplace-name}/memory-capture` structure, causing empty PLUGIN_ROOT and command failures.

## Solution

Replace filesystem-based script execution with Python module imports, eliminating path resolution complexity entirely.

## Scope

| Metric | Count |
|--------|-------|
| Affected Commands | 12+ |
| Tasks | 16 |
| Phases | 5 |
| Estimated Effort | 2-3 hours |

## Documents

- [REQUIREMENTS.md](./REQUIREMENTS.md) - Product requirements
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Technical design  
- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) - Task breakdown
- [DECISIONS.md](./DECISIONS.md) - Architecture decisions (5 ADRs)
- [CHANGELOG.md](./CHANGELOG.md) - Spec history

## Next Steps

Run `/claude-spec:approve plugin-root-path-resolution` to approve for implementation.
