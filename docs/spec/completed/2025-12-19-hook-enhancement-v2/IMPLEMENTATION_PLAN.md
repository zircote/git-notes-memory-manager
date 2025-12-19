---
document_type: implementation_plan
project_id: SPEC-2025-12-19-002
version: 1.0.0
last_updated: 2025-12-19T00:00:00Z
status: draft
estimated_effort: 16-24 hours
---

# Hook Enhancement v2 - Implementation Plan

## Overview

Implementation proceeds in 5 phases, prioritized by user value and risk:

1. **Phase 1**: SessionStart Response Guidance (highest value, lowest risk)
2. **Phase 2**: Namespace-Aware Markers (extends existing, low risk)
3. **Phase 3**: PostToolUse Hook (new hook, medium risk)
4. **Phase 4**: PreCompact Hook (new hook, medium risk)
5. **Phase 5**: Testing & Documentation

## Phase Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| Phase 1: Guidance | 3-4h | GuidanceBuilder, SessionStart integration |
| Phase 2: Namespace | 2-3h | NamespaceParser, UserPromptSubmit integration |
| Phase 3: PostToolUse | 4-5h | Handler, DomainExtractor, hooks.json |
| Phase 4: PreCompact | 4-5h | Handler, SessionAnalyzer integration |
| Phase 5: Testing | 3-5h | Unit/integration tests, documentation |

---

## Phase 1: SessionStart Response Guidance

**Goal**: Inject XML guidance into SessionStart additionalContext to improve signal detection reliability

**Prerequisites**: None (extends existing infrastructure)

### Task 1.1: Create GuidanceBuilder

- **Description**: Create new module for generating response guidance XML
- **File**: `src/git_notes_memory/hooks/guidance_builder.py`
- **Acceptance Criteria**:
  - [ ] `build_guidance(detail_level)` returns valid XML string
  - [ ] Supports "minimal", "standard", "detailed" levels
  - [ ] Includes capture_patterns section with decision/learning/blocker/progress templates
  - [ ] Includes inline_markers section with namespace syntax
  - [ ] Includes best_practices section

### Task 1.2: Add Configuration Options

- **Description**: Add guidance-related config to config_loader
- **File**: `src/git_notes_memory/hooks/config_loader.py`
- **Acceptance Criteria**:
  - [ ] `HOOK_SESSION_START_INCLUDE_GUIDANCE` (bool, default: true)
  - [ ] `HOOK_SESSION_START_GUIDANCE_DETAIL` (enum, default: "standard")
  - [ ] Config validated on load

### Task 1.3: Integrate with SessionStart Handler

- **Description**: Modify session_start_handler to include guidance
- **File**: `src/git_notes_memory/hooks/session_start_handler.py`
- **Acceptance Criteria**:
  - [ ] Imports GuidanceBuilder
  - [ ] Calls build_guidance() when enabled
  - [ ] Prepends guidance to existing additionalContext
  - [ ] Respects HOOK_SESSION_START_INCLUDE_GUIDANCE setting

### Task 1.4: Unit Tests for GuidanceBuilder

- **Description**: Comprehensive tests for guidance generation
- **File**: `tests/hooks/test_guidance_builder.py`
- **Acceptance Criteria**:
  - [ ] Tests all three detail levels
  - [ ] Tests XML structure validity
  - [ ] Tests presence of required sections
  - [ ] Coverage ≥90%

### Phase 1 Deliverables

- [ ] `src/git_notes_memory/hooks/guidance_builder.py`
- [ ] Updated `config_loader.py`
- [ ] Updated `session_start_handler.py`
- [ ] `tests/hooks/test_guidance_builder.py`

### Phase 1 Exit Criteria

- [ ] All tests passing
- [ ] SessionStart hook returns guidance in additionalContext
- [ ] Configuration options work as documented

---

## Phase 2: Namespace-Aware Markers

**Goal**: Support `[remember:namespace]` and `@memory:namespace` syntax in UserPromptSubmit

**Prerequisites**: Phase 1 complete (guidance teaches the syntax)

### Task 2.1: Create NamespaceParser

- **Description**: Create module for parsing namespace-aware inline markers
- **File**: `src/git_notes_memory/hooks/namespace_parser.py`
- **Acceptance Criteria**:
  - [ ] `parse_inline_marker(text)` returns ParsedMarker or None
  - [ ] Parses `[remember:namespace]` pattern
  - [ ] Parses `[remember]` pattern (namespace=None)
  - [ ] Parses `[capture:namespace]` pattern
  - [ ] Parses `[capture]` pattern (namespace=None, auto-detect)
  - [ ] Parses `@memory:namespace` pattern
  - [ ] Parses `@memory` pattern (namespace=None, auto-detect)
  - [ ] Validates namespace against VALID_NAMESPACES
  - [ ] Invalid namespace falls back to None (auto-detect)

### Task 2.2: Integrate with UserPromptHandler

- **Description**: Replace simple marker detection with namespace-aware parsing
- **File**: `src/git_notes_memory/hooks/user_prompt_handler.py`
- **Acceptance Criteria**:
  - [ ] Uses NamespaceParser for marker detection
  - [ ] Explicit namespace overrides auto-detection
  - [ ] Auto-detect uses SignalDetector when namespace=None
  - [ ] Falls back to "learnings" when auto-detect fails
  - [ ] Backward compatible with existing markers

### Task 2.3: Unit Tests for NamespaceParser

- **Description**: Comprehensive tests for namespace parsing
- **File**: `tests/hooks/test_namespace_parser.py`
- **Acceptance Criteria**:
  - [ ] Tests all marker patterns with namespace
  - [ ] Tests all marker patterns without namespace
  - [ ] Tests invalid namespace handling
  - [ ] Tests edge cases (empty, whitespace, special chars)
  - [ ] Coverage ≥95%

### Phase 2 Deliverables

- [ ] `src/git_notes_memory/hooks/namespace_parser.py`
- [ ] Updated `user_prompt_handler.py`
- [ ] `tests/hooks/test_namespace_parser.py`

### Phase 2 Exit Criteria

- [ ] All tests passing
- [ ] `[remember:decisions]` captures to decisions namespace
- [ ] Existing `[remember]` behavior unchanged

---

## Phase 3: PostToolUse Hook

**Goal**: Inject relevant memories after file writes based on file domain

**Prerequisites**: RecallService functional

### Task 3.1: Create DomainExtractor

- **Description**: Create module for extracting searchable terms from file paths
- **File**: `src/git_notes_memory/hooks/domain_extractor.py`
- **Acceptance Criteria**:
  - [ ] `extract_domain_terms(file_path)` returns list of strings
  - [ ] Filters common directories (src, lib, tests, app, spec)
  - [ ] Splits filename on separators (_, -, .)
  - [ ] Filters short terms (<3 chars)
  - [ ] Limits to 5 terms

### Task 3.2: Create PostToolUse Handler

- **Description**: Create handler for PostToolUse hook
- **File**: `src/git_notes_memory/hooks/post_tool_use_handler.py`
- **Acceptance Criteria**:
  - [ ] Reads JSON from stdin
  - [ ] Only processes Write/Edit/MultiEdit tools
  - [ ] Extracts domain terms from file_path
  - [ ] Searches RecallService with terms
  - [ ] Formats results as XML additionalContext
  - [ ] Returns valid hookSpecificOutput JSON
  - [ ] Handles errors gracefully (returns continue: true)
  - [ ] Respects timeout configuration

### Task 3.3: Create PostToolUse Entry Script

- **Description**: Create entry point script for hooks directory
- **File**: `hooks/posttooluse.py`
- **Acceptance Criteria**:
  - [ ] Thin wrapper calling handler
  - [ ] Handles ImportError gracefully
  - [ ] Always exits 0 (non-blocking)

### Task 3.4: Add Configuration Options

- **Description**: Add PostToolUse config to config_loader
- **File**: `src/git_notes_memory/hooks/config_loader.py`
- **Acceptance Criteria**:
  - [ ] `HOOK_POST_TOOL_USE_ENABLED` (bool, default: true)
  - [ ] `HOOK_POST_TOOL_USE_MIN_SIMILARITY` (float, default: 0.6)
  - [ ] `HOOK_POST_TOOL_USE_MAX_RESULTS` (int, default: 3)
  - [ ] `HOOK_POST_TOOL_USE_TIMEOUT` (int, default: 5)

### Task 3.5: Update hooks.json

- **Description**: Register PostToolUse hook
- **File**: `hooks/hooks.json`
- **Acceptance Criteria**:
  - [ ] PostToolUse entry with matcher "Write|Edit|MultiEdit"
  - [ ] Timeout set to 5 seconds
  - [ ] Command points to posttooluse.py

### Task 3.6: Unit Tests for PostToolUse

- **Description**: Comprehensive tests for PostToolUse handler
- **Files**: `tests/hooks/test_domain_extractor.py`, `tests/hooks/test_post_tool_use_handler.py`
- **Acceptance Criteria**:
  - [ ] DomainExtractor tests for various paths
  - [ ] Handler input validation tests
  - [ ] Handler output format tests
  - [ ] Integration with mock RecallService
  - [ ] Error handling tests
  - [ ] Performance test (<100ms)
  - [ ] Coverage ≥85%

### Phase 3 Deliverables

- [ ] `src/git_notes_memory/hooks/domain_extractor.py`
- [ ] `src/git_notes_memory/hooks/post_tool_use_handler.py`
- [ ] `hooks/posttooluse.py`
- [ ] Updated `config_loader.py`
- [ ] Updated `hooks/hooks.json`
- [ ] `tests/hooks/test_domain_extractor.py`
- [ ] `tests/hooks/test_post_tool_use_handler.py`

### Phase 3 Exit Criteria

- [ ] All tests passing
- [ ] PostToolUse hook fires on Write/Edit/MultiEdit
- [ ] Related memories appear in Claude's context
- [ ] Latency <100ms

---

## Phase 4: PreCompact Hook

**Goal**: Auto-capture high-confidence uncaptured content before context compaction

**Prerequisites**: CaptureService and SessionAnalyzer functional

### Task 4.1: Create PreCompact Handler

- **Description**: Create handler for PreCompact hook
- **File**: `src/git_notes_memory/hooks/pre_compact_handler.py`
- **Acceptance Criteria**:
  - [ ] Reads JSON from stdin
  - [ ] Reads transcript from transcript_path
  - [ ] Analyzes transcript for uncaptured signals
  - [ ] Filters signals by confidence (≥0.85)
  - [ ] Captures top N signals (configurable, default 3)
  - [ ] Writes summary to stderr
  - [ ] Returns empty JSON (side-effects only)
  - [ ] Handles errors gracefully
  - [ ] Respects timeout configuration

### Task 4.2: Create PreCompact Entry Script

- **Description**: Create entry point script for hooks directory
- **File**: `hooks/precompact.py`
- **Acceptance Criteria**:
  - [ ] Thin wrapper calling handler
  - [ ] Handles ImportError gracefully
  - [ ] Always exits 0 (non-blocking)

### Task 4.3: Add Configuration Options

- **Description**: Add PreCompact config to config_loader
- **File**: `src/git_notes_memory/hooks/config_loader.py`
- **Acceptance Criteria**:
  - [ ] `HOOK_PRE_COMPACT_ENABLED` (bool, default: true)
  - [ ] `HOOK_PRE_COMPACT_AUTO_CAPTURE` (bool, default: true)
  - [ ] `HOOK_PRE_COMPACT_MIN_CONFIDENCE` (float, default: 0.85)
  - [ ] `HOOK_PRE_COMPACT_MAX_CAPTURES` (int, default: 3)
  - [ ] `HOOK_PRE_COMPACT_TIMEOUT` (int, default: 15)

### Task 4.4: Update hooks.json

- **Description**: Register PreCompact hook
- **File**: `hooks/hooks.json`
- **Acceptance Criteria**:
  - [ ] PreCompact entry with matcher "manual|auto"
  - [ ] Timeout set to 15 seconds
  - [ ] Command points to precompact.py

### Task 4.5: Unit Tests for PreCompact

- **Description**: Comprehensive tests for PreCompact handler
- **File**: `tests/hooks/test_pre_compact_handler.py`
- **Acceptance Criteria**:
  - [ ] Handler input validation tests
  - [ ] Transcript reading tests
  - [ ] Signal filtering tests
  - [ ] Capture execution tests
  - [ ] stderr output tests
  - [ ] Error handling tests
  - [ ] Configuration tests
  - [ ] Coverage ≥85%

### Phase 4 Deliverables

- [ ] `src/git_notes_memory/hooks/pre_compact_handler.py`
- [ ] `hooks/precompact.py`
- [ ] Updated `config_loader.py`
- [ ] Updated `hooks/hooks.json`
- [ ] `tests/hooks/test_pre_compact_handler.py`

### Phase 4 Exit Criteria

- [ ] All tests passing
- [ ] PreCompact hook fires on compaction
- [ ] High-confidence signals captured automatically
- [ ] User sees stderr notification

---

## Phase 5: Testing & Documentation

**Goal**: Comprehensive testing and documentation updates

**Prerequisites**: Phases 1-4 complete

### Task 5.1: Integration Tests

- **Description**: End-to-end tests for all new functionality
- **File**: `tests/hooks/test_hook_enhancement_integration.py`
- **Acceptance Criteria**:
  - [ ] SessionStart with guidance integration
  - [ ] Namespace marker capture flow
  - [ ] PostToolUse with real RecallService
  - [ ] PreCompact with real CaptureService
  - [ ] Multi-hook interaction tests

### Task 5.2: Performance Tests

- **Description**: Performance validation for new hooks
- **File**: `tests/hooks/test_hook_enhancement_performance.py`
- **Acceptance Criteria**:
  - [ ] PostToolUse <100ms p99
  - [ ] PreCompact <15s with 3 captures
  - [ ] SessionStart guidance <10ms additional

### Task 5.3: Update Documentation

- **Description**: Update user-facing documentation
- **Files**: `docs/USER_GUIDE.md`, `README.md`
- **Acceptance Criteria**:
  - [ ] Document response structuring best practices
  - [ ] Document namespace marker syntax
  - [ ] Document PostToolUse behavior
  - [ ] Document PreCompact behavior
  - [ ] Document configuration options

### Task 5.4: Update Skills Documentation

- **Description**: Update memory-assistant skill with new hook integration
- **File**: `skills/memory-assistant/SKILL.md`
- **Acceptance Criteria**:
  - [ ] Document namespace markers in inline capture section
  - [ ] Update hook integration section

### Phase 5 Deliverables

- [ ] `tests/hooks/test_hook_enhancement_integration.py`
- [ ] `tests/hooks/test_hook_enhancement_performance.py`
- [ ] Updated `docs/USER_GUIDE.md`
- [ ] Updated `README.md`
- [ ] Updated `skills/memory-assistant/SKILL.md`

### Phase 5 Exit Criteria

- [ ] All tests passing (≥80% coverage on new code)
- [ ] Documentation complete
- [ ] `make quality` passes

---

## Dependency Graph

```
Phase 1: SessionStart Guidance
  Task 1.1 (GuidanceBuilder) ──┬──> Task 1.3 (Integration)
  Task 1.2 (Config) ───────────┘
  Task 1.4 (Tests) ← depends on 1.1

Phase 2: Namespace Markers (depends on Phase 1)
  Task 2.1 (NamespaceParser) ──> Task 2.2 (Integration)
  Task 2.3 (Tests) ← depends on 2.1

Phase 3: PostToolUse (independent)
  Task 3.1 (DomainExtractor) ──┬──> Task 3.2 (Handler)
  Task 3.4 (Config) ───────────┘
  Task 3.3 (Entry) ← depends on 3.2
  Task 3.5 (hooks.json) ← depends on 3.3
  Task 3.6 (Tests) ← depends on 3.1, 3.2

Phase 4: PreCompact (independent of Phase 3)
  Task 4.1 (Handler) ──> Task 4.2 (Entry)
  Task 4.3 (Config) ← parallel with 4.1
  Task 4.4 (hooks.json) ← depends on 4.2
  Task 4.5 (Tests) ← depends on 4.1

Phase 5: Testing & Documentation (depends on all phases)
  Task 5.1 (Integration) ← depends on Phases 1-4
  Task 5.2 (Performance) ← depends on Phases 1-4
  Task 5.3, 5.4 (Docs) ← can start after Phases 1-4
```

---

## Launch Checklist

- [ ] All tests passing (`make test`)
- [ ] Coverage ≥80% on new code (`make coverage`)
- [ ] Quality checks pass (`make quality`)
- [ ] Documentation updated
- [ ] hooks.json updated with new hooks
- [ ] Configuration documented
- [ ] Rollback plan tested (disable via env vars)

## Post-Launch

- [ ] Monitor for performance issues (check stderr logs)
- [ ] Gather user feedback on capture reliability
- [ ] Tune confidence thresholds if needed
- [ ] Consider P2 features based on feedback
