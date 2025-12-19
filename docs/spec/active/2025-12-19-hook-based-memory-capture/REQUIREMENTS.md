---
document_type: requirements
project_id: SPEC-2025-12-19-001
version: 1.0.0
last_updated: 2025-12-19T00:00:00Z
status: draft
---

# Hook-Based Memory Capture - Product Requirements Document

## Executive Summary

Enhance the existing Memory Capture Plugin (git-notes-memory) with sophisticated hook-based integration for automatic memory capture and context injection. This project adds SessionStart context loading, intelligent capture detection via prompt-type hooks, and XML-structured memory prompts for seamless, non-intrusive memory operations in Claude Code sessions.

## Problem Statement

### The Problem

The Memory Capture Plugin currently requires **manual invocation** of `/remember` and `/recall` commands. Users must:
1. Remember to capture important decisions/learnings during work
2. Know when to search for relevant context
3. Manually manage what context to load at session start

This creates friction and missed capture opportunities.

### Impact

- Important decisions are lost when users forget to `/remember`
- Relevant context isn't surfaced at session start
- Context from previous sessions doesn't automatically inform current work
- The full value of semantic memory isn't realized without automation

### Desired State

Memories are automatically:
- **Injected** at session start (relevant context surfaces immediately)
- **Detected** during work (memorable moments are identified and captured)
- **Captured** with minimal user friction (confirm or auto-capture based on confidence)
- **Organized** with XML structure for clear, parseable context

## Goals and Success Criteria

### Primary Goal

Add hook-based integration to the Memory Capture Plugin that enables automatic context injection at session start and intelligent memory capture detection during work sessions.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Session context injection | 100% of sessions | SessionStart hook fires successfully |
| Capture detection accuracy | ≥80% precision | Manual review of captured vs suggested |
| Context injection latency | ≤2s | Hook execution time |
| User override rate | ≤20% | Auto-captures rejected by user |
| Memory utilization | ≥50% sessions use injected context | Claude references injected memories |

### Non-Goals (Explicit Exclusions)

- Replacing manual `/remember` and `/recall` commands (enhancement only)
- Cross-repository memory sharing (future enhancement)
- LLM-based summarization of old memories (future enhancement)
- Web UI for memory browsing (future enhancement)
- Modifying core capture/recall service architecture

## User Analysis

### Primary Users

| User Type | Description | Primary Needs |
|-----------|-------------|---------------|
| Claude Code Daily Users | Developers using Claude Code for coding tasks | Automatic context without remembering to search |
| Project-Based Workers | Users working on multi-session projects | Continuity across sessions |
| Knowledge Capturers | Users who want to build a personal knowledge base | Frictionless capture of insights |

### User Stories

1. **As a Claude Code user**, I want relevant memories automatically loaded when I start a session so that I have context from previous work without manually searching.

2. **As a developer**, I want Claude to notice when I make important decisions and offer to capture them so that I don't have to remember to manually record everything.

3. **As a project lead**, I want memories scoped to my current project so that unrelated context doesn't pollute my session.

4. **As a power user**, I want to configure capture sensitivity so that I can balance automation with control.

5. **As a privacy-conscious user**, I want to review auto-detected captures before they're saved so that I maintain control over what's stored.

## Functional Requirements

### Must Have (P0) - Hook Infrastructure

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | SessionStart hook for context injection | Automatic context loading | Hook fires on every session start |
| FR-002 | XML-structured memory context format | Parseable, hierarchical context | Valid XML with schema |
| FR-003 | Project-scoped memory filtering | Relevance and isolation | Only current project memories injected |
| FR-004 | Adaptive token budget | Avoid context overload | Budget adjusts based on project complexity |
| FR-005 | Stop hook for session capture prompts | Capture learnings before exit | Hook prompts for memorable content |

### Must Have (P0) - Capture Detection

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-010 | Signal detection for memorable moments | Identify what to capture | Detects decisions, learnings, blockers, explicit markers |
| FR-011 | Prompt-type hook for LLM-assisted decisions | Context-aware capture assessment | LLM evaluates capture worthiness |
| FR-012 | Confidence-based capture behavior | Balance automation with control | Auto-capture (high), suggest (medium), skip (low) |
| FR-013 | Duplicate detection before capture | Avoid memory bloat | Semantic similarity check before capture |

### Should Have (P1) - Enhanced Capture

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-101 | UserPromptSubmit hook for inline detection | Real-time capture opportunities | Hook analyzes prompts for signals |
| FR-102 | PostToolUse hook for change tracking | Track significant modifications | Hook detects architecture/config changes |
| FR-103 | Capture confirmation notifications | User awareness | Clear feedback when memory captured |
| FR-104 | Capture override/edit before save | User control | Option to modify suggested capture |

### Should Have (P1) - Context Intelligence

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-110 | Relevance scoring for context injection | Quality over quantity | Higher relevance = priority injection |
| FR-111 | Recency boost in scoring | Fresh context preferred | Recent memories score higher |
| FR-112 | Namespace priority configuration | Customize by use case | User can weight namespaces |
| FR-113 | Active blockers section in context | Unresolved issues visible | Blockers prominently displayed |

### Nice to Have (P2)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-201 | SubagentStop hook for task completion | Capture subagent learnings | Hook fires when subagents complete |
| FR-202 | Session summary generation | End-of-session digest | Summarize session captures |
| FR-203 | Memory access tracking | Inform decay scoring | Track which memories Claude references |
| FR-204 | Interactive capture wizard | Guided capture for complex memories | Multi-step capture flow |

## Non-Functional Requirements

### Performance

| Requirement | Target |
|-------------|--------|
| SessionStart hook execution | ≤2000ms |
| Capture signal detection | ≤500ms |
| Stop hook execution | ≤1000ms |
| Context injection size | ≤3000 tokens |

### Security

- **SEC-001**: No sensitive data auto-captured (user responsibility + warnings)
- **SEC-002**: Hook scripts validated before execution
- **SEC-003**: Transcript access read-only
- **SEC-004**: Memory content not sent to external services (local LLM for prompt hooks)

### Reliability

- **REL-001**: Hooks fail gracefully (session continues without memory context)
- **REL-002**: Hook timeouts enforced (60s default, configurable)
- **REL-003**: Capture failures don't block session
- **REL-004**: Index rebuilds don't affect active sessions

### Usability

- **USA-001**: Zero configuration for basic functionality
- **USA-002**: Clear feedback when context injected
- **USA-003**: Capture suggestions non-intrusive
- **USA-004**: Easy opt-out for auto-capture

## Technical Constraints

### Claude Code Hooks

- Hook events: SessionStart, UserPromptSubmit, PostToolUse, Stop, SubagentStop
- Hook types: command (bash/python scripts), prompt (LLM-assisted)
- Hook output: JSON with `hookSpecificOutput.additionalContext` for injection
- Hook timeout: 60s default, configurable

### Integration with Memory Capture Plugin

- Reuse existing services: CaptureService, RecallService, IndexService
- Extend configuration for hook-specific settings
- Add new hook handler scripts to `hooks/` directory
- Update plugin.json with hook registrations

### Python Environment

- Python 3.11+ (match base plugin)
- Dependencies: pyyaml, sentence-transformers, sqlite-vec (from base plugin)
- No new external dependencies for hooks

## Dependencies

### Internal Dependencies

| Dependency | Type | Purpose |
|------------|------|---------|
| git-notes-memory | Library | Core capture/recall functionality |
| Memory Capture Plugin | Plugin | Base plugin structure and commands |

### External Dependencies

None additional beyond base plugin requirements.

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Hook execution delays session start | Medium | High | Async context loading, timeout enforcement |
| False positive capture suggestions | Medium | Medium | Confidence thresholds, easy dismiss |
| Context overload (too many memories) | Low | Medium | Token budget limits, relevance scoring |
| Prompt-type hook cost (LLM usage) | Medium | Low | Local model option, configurable |
| Privacy concerns with auto-capture | Medium | High | Clear documentation, easy disable, confirmation |

## Open Questions

- [x] Integration approach: **Add to existing plugin** (not new plugin)
- [x] Capture triggers: **All events** (UserPromptSubmit, PostToolUse, Stop)
- [x] Capture intelligence: **LLM-assisted** (prompt-type hooks)
- [x] Context budget: **Adaptive** (based on project complexity)
- [ ] Local vs cloud LLM for prompt hooks?
- [ ] Cache strategy for repeated SessionStart calls (resume)?

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| Hook | Claude Code mechanism for custom code execution at lifecycle events |
| Prompt-type hook | Hook that uses LLM to make decisions |
| Context injection | Adding information to Claude's context via hook output |
| Capture signal | Pattern indicating a memorable moment (decision, learning, etc.) |
| Token budget | Maximum tokens allocated for memory context |
| Working memory | Currently relevant, high-priority memories |
| Semantic context | Memories retrieved by similarity to current work |

### XML Schema Reference

See RESEARCH_NOTES.md section 3 for full XML schema definitions.

### Hook Event Reference

See RESEARCH_NOTES.md section 2 for complete Claude Code hooks documentation.
