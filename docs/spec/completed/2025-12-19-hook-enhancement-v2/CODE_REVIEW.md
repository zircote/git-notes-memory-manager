# Code Review Report

## Metadata
- **Project**: git-notes-memory-manager
- **Review Date**: 2025-12-19
- **Reviewer**: Claude Code Review Agent (6 specialist subagents)
- **Scope**: Hook Enhancement v2 implementation (`src/git_notes_memory/hooks/`, `hooks/`, tests)
- **Commit**: feature/hook-enhancement-v2

## Executive Summary

### Overall Health Score: 7.5/10

| Dimension | Score | Critical | High | Medium | Low |
|-----------|-------|----------|------|--------|-----|
| Security | 8/10 | 0 | 0 | 1 | 5 |
| Performance | 6/10 | 1 | 2 | 5 | 4 |
| Architecture | 7/10 | 0 | 0 | 4 | 6 |
| Code Quality | 7/10 | 0 | 1 | 4 | 5 |
| Test Coverage | 8/10 | 0 | 1 | 8 | 6 |
| Documentation | 6/10 | 0 | 3 | 4 | 3 |

### Key Findings

1. **CRITICAL (Performance)**: `DomainExtractor` is instantiated on every call in hot path - creates garbage collection pressure on every file operation
2. **HIGH (Performance)**: `batch_check_novelty()` doesn't actually batch - runs N sequential queries instead of batched
3. **HIGH (Code Quality)**: 200+ lines of duplicated utility functions across 5 handler files
4. **HIGH (Documentation)**: PostToolUse and PreCompact hooks not documented in README or USER_GUIDE
5. **MEDIUM (Security)**: Path traversal risk in `session_analyzer.py` - transcript path not validated

### Recommended Action Plan

1. **Immediate** (before merge):
   - Fix DomainExtractor singleton pattern (CRITICAL performance)
   - Add input size limits to JSON parsing (MEDIUM security)

2. **This Sprint**:
   - Extract common handler utilities to shared module (HIGH code quality)
   - Update README and USER_GUIDE with new hooks (HIGH documentation)
   - Add path validation to session_analyzer.py (MEDIUM security)

3. **Next Sprint**:
   - Implement true batching in NoveltyChecker
   - Consolidate configuration sources
   - Add missing test coverage for PostToolUse config

4. **Backlog**:
   - Refactor config_loader.py to use declarative schema
   - Add async-signal-safe timeout handlers
   - Document hook models in DEVELOPER_GUIDE

---

## Critical Findings (🔴)

### PERF-1: DomainExtractor Instantiated Per Call

**Location**: `src/git_notes_memory/hooks/domain_extractor.py:259-260`

**Description**: The convenience function `extract_domain_terms()` creates a new `DomainExtractor` instance on every invocation. Since `PostToolUse` hook fires on every file Read/Write/Edit operation, this is extremely hot.

**Impact**: CPU overhead, garbage collection pressure, adds ~0.5-1ms per call

**Evidence**:
```python
def extract_domain_terms(file_path: str) -> list[str]:
    extractor = DomainExtractor()  # Created every call
    return extractor.extract(file_path)
```

**Remediation**:
```python
# Module-level singleton
_default_extractor: DomainExtractor | None = None

def extract_domain_terms(file_path: str) -> list[str]:
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = DomainExtractor()
    return _default_extractor.extract(file_path)
```

---

## High Priority Findings (🟠)

### PERF-2: batch_check_novelty Does Not Batch Embeddings

**Location**: `src/git_notes_memory/hooks/novelty_checker.py:253-277`

**Description**: Each signal triggers a separate embedding + search operation. For N signals, this is O(N) database queries when batching could reduce to O(1).

**Impact**: Latency multiplied by number of signals

**Evidence**:
```python
def batch_check_novelty(self, signals: list[CaptureSignal]) -> list[NoveltyResult]:
    return [self.check_signal_novelty(signal) for signal in signals]
```

**Remediation**: Implement batch embedding and search API.

---

### QUAL-1: Duplicated Utility Functions Across Handlers

**Location**:
- `src/git_notes_memory/hooks/pre_compact_handler.py:54-112`
- `src/git_notes_memory/hooks/post_tool_use_handler.py:57-115`
- `src/git_notes_memory/hooks/stop_handler.py:52-108`
- `src/git_notes_memory/hooks/session_start_handler.py:48-104`
- `src/git_notes_memory/hooks/user_prompt_handler.py:56-114`

**Description**: Four utility functions are copied verbatim across 5 handler files: `_setup_logging()`, `_setup_timeout()`, `_cancel_timeout()`, `_read_input()`

**Impact**: 200+ lines of duplicated code. Bug fixes must be applied 5 times.

**Remediation**: Extract to shared `hook_utils.py` module.

---

### DOC-1: PostToolUse and PreCompact Missing from Documentation

**Location**:
- `README.md` (lists only 3 hooks)
- `docs/USER_GUIDE.md` (missing hook sections and config variables)

**Description**: The README and USER_GUIDE only document SessionStart, UserPromptSubmit, and Stop hooks. PostToolUse and PreCompact are implemented but undocumented.

**Impact**: Users cannot discover or configure the new hooks.

**Remediation**: Add comprehensive documentation for both hooks including all configuration options.

---

## Medium Priority Findings (🟡)

### SEC-1: Path Traversal in session_analyzer.py

**Location**: `src/git_notes_memory/hooks/session_analyzer.py:145-152`

**Description**: The `parse_transcript` method accepts a file path without validation. An attacker controlling hook input could read arbitrary files.

**Remediation**: Validate transcript path is within expected directory.

---

### PERF-3: Service Instantiation Per NoveltyChecker

**Location**: `src/git_notes_memory/hooks/novelty_checker.py:99-113`

**Description**: Each `NoveltyChecker` instance may create new service instances.

**Remediation**: Use the existing singleton services directly.

---

### ARCH-1: Missing Abstraction for Hook Response Contract

**Location**: Multiple handler files

**Description**: Each handler manually constructs JSON responses with keys like `"hookSpecificOutput"`. No shared abstraction.

**Remediation**: Create `HookResponse` dataclass.

---

### QUAL-2: Duplicated VALID_NAMESPACES Constant

**Location**:
- `src/git_notes_memory/hooks/guidance_builder.py:119`
- `src/git_notes_memory/hooks/namespace_parser.py:30`

**Description**: Same 10-namespace list defined in two places.

**Remediation**: Create shared `constants.py`.

---

### QUAL-3: Complex load_hook_config() Function

**Location**: `src/git_notes_memory/hooks/config_loader.py:272-418`

**Description**: 146 lines with 30+ if statements. High cyclomatic complexity.

**Remediation**: Use declarative config schema.

---

### TEST-1: Missing Tests for PostToolUse Configuration

**Location**: `tests/test_hooks.py`

**Description**: PostToolUse settings (`HOOK_POST_TOOL_USE_ENABLED`, `HOOK_POST_TOOL_USE_MIN_SIMILARITY`, etc.) not tested.

**Remediation**: Add tests for all PostToolUse environment variables.

---

### DOC-2: SessionStart Guidance Config Not Documented

**Location**: `docs/USER_GUIDE.md`

**Description**: `HOOK_SESSION_START_INCLUDE_GUIDANCE` and `HOOK_SESSION_START_GUIDANCE_DETAIL` not documented.

**Remediation**: Add guidance configuration section.

---

## Low Priority Findings (🟢)

### SEC-2: ReDoS Vulnerability in Signal Patterns
**Location**: `src/git_notes_memory/hooks/signal_detector.py:67`
**Description**: Pattern `r"(?i)\bcan('t| not)\s+.{1,30}\s+because\b"` could cause backtracking.
**Mitigation**: Hook timeout limits impact.

### SEC-3: Signal Handler Safety
**Location**: `src/git_notes_memory/hooks/pre_compact_handler.py:75-80`
**Description**: Timeout handlers call `print()` and `json.dumps()` which are not async-signal-safe.

### SEC-4: JSON Input Size Not Limited
**Location**: `src/git_notes_memory/hooks/pre_compact_handler.py:94-112`
**Description**: `sys.stdin.read()` has no size limit.

### PERF-4: Reinforcers List Created Per Match
**Location**: `src/git_notes_memory/hooks/signal_detector.py:341-343`
**Description**: List recreated on every call.

### PERF-5: Full Transcript Loaded Into Memory
**Location**: `src/git_notes_memory/hooks/session_analyzer.py:151-152`
**Description**: No size limit check before reading.

### QUAL-4: Dead Code in _extract_summary()
**Location**: `src/git_notes_memory/hooks/pre_compact_handler.py:132-135`
**Description**: Prefix stripping loop breaks without modifying text.

### QUAL-5: Magic Numbers
**Location**: Various handler files
**Description**: Values like 20, 100, 97, 50 used without named constants.

### ARCH-2: Inconsistent Dependency Injection
**Location**: Multiple service classes
**Description**: Mix of constructor injection and lazy loading.

### ARCH-3: Entry Points Swallow Exceptions Silently
**Location**: `hooks/session_start.py:36-40`
**Description**: Exceptions caught and exit(0) called silently.

### TEST-2: Missing Timeout Function Tests
**Location**: `tests/test_pre_compact_handler.py`, `tests/test_post_tool_use_handler.py`
**Description**: `_setup_timeout()` and `_cancel_timeout()` not tested.

---

## Positive Findings

1. **Security**: Git command injection properly prevented - no `shell=True`, refs validated
2. **Security**: XML injection prevented via ElementTree escaping
3. **Architecture**: Frozen dataclasses used consistently for immutability
4. **Architecture**: Clean separation of concerns across service classes
5. **Architecture**: Lazy loading in `__init__.py` prevents slow imports
6. **Code Quality**: Consistent type hints throughout
7. **Test Coverage**: Overall test suite is comprehensive (1276 tests, 87% coverage)

---

## Appendix

### Files Reviewed
- `src/git_notes_memory/hooks/*.py` (17 files)
- `hooks/*.py` (7 files)
- `tests/test_*.py` (28 files)
- `docs/*.md` (4 files)
- `README.md`

### Specialist Agents Used
1. Security Analyst (security-engineer)
2. Performance Engineer (performance-engineer)
3. Architecture Reviewer (architect-reviewer)
4. Code Quality Analyst (code-reviewer)
5. Test Coverage Analyst (test-automator)
6. Documentation Reviewer (documentation-engineer)
