---
project_id: SPEC-2025-12-19-002
project_name: "Hook Enhancement v2: Response Structuring & Expanded Capture"
slug: hook-enhancement-v2
status: in-review
created: 2025-12-19T00:00:00Z
approved: null
started: null
completed: null
expires: 2026-03-19T00:00:00Z
superseded_by: null
tags: [hooks, memory-capture, claude-code, response-structuring]
stakeholders: []
predecessor: SPEC-2025-12-19-001 (hook-based-memory-capture)
---

# Hook Enhancement v2: Response Structuring & Expanded Capture

## Quick Overview

Enhance the git-notes-memory plugin hooks to improve capture reliability and expand context injection points. This builds on the successful hook-based-memory-capture spec to address namespace targeting, signal detection accuracy, and context preservation.

## Key Features

1. **SessionStart Response Guidance** - Inject XML templates teaching Claude how to structure decisions, learnings, blockers for reliable signal detection (~70% → ~85% accuracy)
2. **Namespace-Aware Markers** - Support `[remember:decisions]`, `@memory:patterns` syntax (~10% → ~60% namespace accuracy)
3. **PostToolUse Hook** - Inject relevant memories after file writes based on file domain
4. **PreCompact Hook** - Auto-capture high-confidence content before context compaction (enabled by default)

## Status

| Phase | Status | Document |
|-------|--------|----------|
| Requirements | Complete | [REQUIREMENTS.md](./REQUIREMENTS.md) |
| Architecture | Complete | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| Implementation Plan | Complete | [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) |
| Decisions | Complete | [DECISIONS.md](./DECISIONS.md) |

**Overall Status**: In Review - Awaiting approval to proceed with implementation

## Estimated Effort

- **Total**: 16-24 hours
- **Phase 1 (Guidance)**: 3-4h
- **Phase 2 (Namespace)**: 2-3h
- **Phase 3 (PostToolUse)**: 4-5h
- **Phase 4 (PreCompact)**: 4-5h
- **Phase 5 (Testing)**: 3-5h

## Key Decisions

| ADR | Decision | Status |
|-----|----------|--------|
| ADR-001 | PreCompact uses stderr (API constraint) | Accepted |
| ADR-002 | Namespace marker syntax `[remember:namespace]` | Accepted |
| ADR-003 | Auto-capture enabled by default | Accepted |
| ADR-004 | Response guidance as XML | Accepted |
| ADR-005 | PostToolUse matcher: Write\|Edit\|MultiEdit | Accepted |

## Source Documents

- `docs/HOOK_ENHANCEMENT_PLAN.md` - Initial planning document
- `docs/spec/completed/2025-12-19-hook-based-memory-capture/` - Predecessor spec
- `docs/claude-code-hooks-reference.md` - Claude Code hooks API reference

## Next Steps

1. **Review**: Stakeholder review of requirements and architecture
2. **Approve**: Approval to proceed with implementation
3. **Implement**: Run `/claude-spec:implement hook-enhancement-v2`
