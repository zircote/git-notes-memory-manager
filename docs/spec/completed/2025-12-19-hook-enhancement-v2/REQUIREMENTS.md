---
document_type: requirements
project_id: SPEC-2025-12-19-002
version: 1.0.0
last_updated: 2025-12-19T00:00:00Z
status: draft
---

# Hook Enhancement v2 - Product Requirements Document

## Executive Summary

Enhance the git-notes-memory plugin's hook system to improve memory capture reliability through response structuring guidance, namespace-aware markers, file-contextual memory injection, and pre-compaction preservation. These enhancements increase the value users get from the memory system by reducing missed captures and improving namespace targeting accuracy.

## Problem Statement

### The Problem

The current hook-based memory capture system has three limitations:

1. **Inconsistent signal detection**: Claude structures responses variably, making regex-based signal detection unreliable (~70% accuracy)
2. **Single namespace limitation**: All inline marker captures go to `learnings` namespace regardless of content type
3. **Context gaps**: Users don't receive relevant memories when editing files in domains they've previously captured knowledge about
4. **Context loss**: Valuable decisions and learnings are lost during context compaction without explicit capture

### Impact

- Users miss capturing ~30% of valuable decisions and learnings
- 90% of inline captures go to wrong namespace (`learnings` instead of `decisions`, `patterns`, etc.)
- Developers repeatedly solve problems they've previously documented
- Long sessions lose important context during automatic compaction

### Current State

| Feature | Current | Desired |
|---------|---------|---------|
| Signal detection accuracy | ~70% | ~85%+ |
| Namespace targeting accuracy | ~10% | ~60%+ |
| File-contextual recall | None | Automatic |
| Pre-compaction preservation | None | Auto-capture |

## Goals and Success Criteria

### Primary Goal

Increase memory capture reliability and namespace accuracy through intelligent hook enhancements.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Signal detection accuracy | ≥85% | Test suite with known-good prompts |
| Namespace targeting (when specified) | 100% | Unit tests on marker parsing |
| Namespace auto-detection | ≥60% | Integration tests with signal types |
| PostToolUse latency | <100ms | Performance tests |
| PreCompact capture success | ≥90% | Integration tests |
| Test coverage (new code) | ≥80% | pytest-cov |

### Non-Goals (Explicit Exclusions)

- Changing existing capture command behavior
- Modifying git notes storage format
- Adding new memory namespaces
- Implementing memory expiration/cleanup
- Supporting hooks other than PostToolUse and PreCompact

## User Analysis

### Primary Users

1. **Claude Code Users** - Developers using Claude Code with the memory plugin
   - Need: Automatic preservation of decisions and learnings without manual intervention
   - Context: Working in long sessions across multiple files

2. **Power Users** - Developers who actively use inline markers
   - Need: Control over which namespace receives their captures
   - Context: Already familiar with `[remember]` and `@memory` syntax

### User Stories

1. As a developer, I want Claude to structure decisions consistently so the signal detector captures them reliably
2. As a power user, I want to specify `[remember:decisions]` to capture directly to the decisions namespace
3. As a developer, I want relevant memories surfaced when I edit a file in a domain I've previously worked on
4. As a developer, I want important uncaptured content preserved before context compaction

## Functional Requirements

### Must Have (P0)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | SessionStart injects response structuring guidance | Improves signal detection by teaching Claude consistent patterns | Guidance XML present in additionalContext; signal detection accuracy ≥85% |
| FR-002 | UserPromptSubmit supports `[remember:namespace]` syntax | Enables namespace targeting | Marker with namespace routes to specified namespace |
| FR-003 | UserPromptSubmit supports `@memory:namespace` syntax | Alternative syntax for namespace targeting | Same as FR-002 |
| FR-004 | PostToolUse injects relevant memories after Write/Edit/MultiEdit | Surfaces contextual knowledge automatically | Memories injected within 100ms; relevance ≥0.6 |
| FR-005 | PreCompact captures high-confidence uncaptured content | Preserves valuable context before compaction | Confidence ≥0.85 signals captured |

### Should Have (P1)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-101 | Auto-detect namespace from content when `[capture]` used without namespace | Leverages existing signal detection | Namespace matches primary signal type |
| FR-102 | Configurable guidance detail level (minimal/standard/detailed) | Different users need different verbosity | Config option respected |
| FR-103 | PostToolUse domain extraction from file paths | Enables relevant memory search | Common dirs filtered; terms extracted |

### Nice to Have (P2)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-201 | PreCompact prompt-before-capture mode | Users who want explicit approval | Config option `HOOK_PRE_COMPACT_PROMPT_FIRST` |
| FR-202 | PostToolUse configurable similarity threshold | Tuning for different codebases | Config option respected |

## Non-Functional Requirements

### Performance

- PostToolUse hook must complete within 100ms (p99)
- PreCompact hook must complete within 15 seconds (including captures)
- SessionStart guidance injection adds <10ms to existing hook

### Security

- No new attack vectors introduced
- File paths in PostToolUse remain local (no remote disclosure)
- PreCompact operates on transcript_path provided by Claude Code (trusted)

### Reliability

- All hooks fail-open (return `continue: true` on any error)
- Capture failures don't block session flow
- Invalid namespace in marker falls back to `learnings`

### Maintainability

- New handlers follow existing patterns (see `session_start_handler.py`)
- Test coverage ≥80% for all new code
- Configuration via environment variables (consistent with existing)

## Technical Constraints

- Must use Claude Code hooks API (PostToolUse, PreCompact)
- PreCompact is side-effects only (no context injection, stderr output only)
- Must integrate with existing SignalDetector and CaptureService
- Python 3.11+ with type annotations

## Dependencies

### Internal Dependencies

- `SignalDetector` - Signal detection for namespace auto-detection
- `CaptureService` - Memory capture operations
- `RecallService` - Memory search for PostToolUse
- `ContextBuilder` - XML context formatting

### External Dependencies

- Claude Code hooks API (PostToolUse, PreCompact events)
- sqlite-vec for vector similarity search

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| PreCompact auto-capture creates unwanted memories | Medium | Medium | Enable by default but configurable; high confidence threshold (0.85) |
| PostToolUse adds latency to file operations | Low | Medium | 100ms timeout; async-friendly design |
| Response guidance bloats context | Low | Low | Configurable detail level; minimal mode available |
| Namespace markers confuse existing users | Low | Low | Backward compatible; existing syntax unchanged |

## Open Questions

- [x] Does PreCompact support additionalContext? → **No, side-effects only**
- [x] What timeout should PreCompact use? → **15 seconds (default 60 too long)**
- [ ] Should PostToolUse trigger on Read operations? → **Deferred to P2**

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| Hook | Claude Code lifecycle event handler |
| Namespace | Category for memory storage (decisions, learnings, etc.) |
| Signal | Detected pattern indicating capture-worthy content |
| additionalContext | JSON field for injecting context into Claude's awareness |

### References

- `docs/claude-code-hooks-reference.md` - Claude Code hooks API
- `docs/spec/completed/2025-12-19-hook-based-memory-capture/` - Predecessor spec
- `docs/HOOK_ENHANCEMENT_PLAN.md` - Initial planning document
