# Code Review Report

## Metadata
- **Project**: git-notes-memory
- **Review Date**: 2025-12-20
- **Reviewer**: Claude Code Review Agent (6 Specialist Subagents)
- **Scope**: Full codebase - `src/`, `hooks/`, `tests/`
- **Branch**: feature/hook-enhancement-v2

---

## Executive Summary

### Overall Health Score: 7.5/10

| Dimension | Score | Critical | High | Medium | Low |
|-----------|-------|----------|------|--------|-----|
| Security | 9/10 | 0 | 0 | 0 | 1 |
| Performance | 6/10 | 2 | 3 | 3 | 4 |
| Architecture | 7/10 | 0 | 0 | 7 | 10 |
| Code Quality | 7/10 | 0 | 1 | 5 | 17 |
| Test Coverage | 6/10 | 4 | 12 | 10 | 0 |
| Documentation | 8/10 | 2 | 5 | 6 | 0 |

### Key Findings
1. **CRITICAL**: N+1 query pattern in `IndexService.search_vector()` causes latency to scale linearly with results
2. **CRITICAL**: Novelty check can trigger 2-5 second embedding model load during hook execution, violating <50ms target
3. **HIGH**: Major test coverage gaps in hooks subsystem (7 source files with no tests)
4. **HIGH**: Missing v0.3.1 entry in CHANGELOG.md
5. **HIGH**: Bare exception handlers in hook entry points swallow errors silently

### Recommended Action Plan
1. **Immediate** (before next deploy): Fix N+1 query, add model-loaded check in novelty checker
2. **This Sprint**: Add tests for signal_detector, capture_decider, context_builder; update CHANGELOG
3. **Next Sprint**: Cache project detection, simplify session start memory count, add Protocol interfaces
4. **Backlog**: DRY up handler boilerplate, define named constants for magic numbers

---

## Critical Findings (2)

### PERF-001: N+1 Query Pattern in Vector Search
- **Location**: `src/git_notes_memory/index.py:1006-1022`
- **Category**: Performance
- **Severity**: CRITICAL

**Description**: Each vector match triggers a separate `self.get(memory_id)` query inside a loop, causing latency to scale O(n) with result count.

**Impact**: Vector search with 10 results executes 11 queries instead of 1. At 50ms per query, this adds 500ms latency.

**Evidence**:
```python
for row in cursor.fetchall():
    memory_id = row[0]
    distance = row[1]
    memory = self.get(memory_id)  # N+1: Separate query per result
```

**Remediation**:
```python
# Use single JOIN query
sql = """
    SELECT m.*, v.distance
    FROM vec_memories v
    JOIN memories m ON v.id = m.id
    WHERE v.embedding MATCH ? AND k = ?
    ORDER BY v.distance LIMIT ?
"""
```

---

### PERF-002: Novelty Check Triggers Full Model Load in Hook Path
- **Location**: `src/git_notes_memory/hooks/novelty_checker.py:99-113, 151-158`
- **Category**: Performance
- **Severity**: CRITICAL

**Description**: First novelty check during hook execution loads the sentence-transformer model (2-5 seconds), violating the <50ms hook target.

**Impact**: First session with novelty checking enabled blocks Claude Code for several seconds.

**Evidence**:
```python
def check_novelty(self, text: str, ...) -> NoveltyResult:
    recall = self._get_recall_service()  # Triggers model load
    results = recall.search(text, ...)   # Blocks on embedding
```

**Remediation**:
```python
def check_novelty(self, text: str, ...) -> NoveltyResult:
    embedding = self._get_embedding_service()
    if not embedding.is_loaded:
        # Model not loaded - skip expensive check, assume novel
        return NoveltyResult(novelty_score=1.0, is_novel=True, ...)
    # Model loaded - safe to proceed
    ...
```

---

## High Priority Findings (8)

### PERF-003: Subprocess in Project Detection
- **Location**: `src/git_notes_memory/config.py:219-225`
- **Category**: Performance
- **Severity**: HIGH

**Description**: Each `get_project_identifier()` call spawns a subprocess (`git config --get`), adding 50-200ms latency.

**Remediation**: Add LRU cache or read `.git/config` file directly without subprocess.

---

### PERF-004: Uncached File Reads in Project Detector
- **Location**: `src/git_notes_memory/hooks/project_detector.py:146-176`
- **Category**: Performance
- **Severity**: HIGH

**Description**: Each `detect_project()` reads up to 5 files without caching.

**Remediation**: Add `@lru_cache(maxsize=16)` decorator.

---

### PERF-005: Session Start Initializes Full Index
- **Location**: `src/git_notes_memory/hooks/session_start_handler.py:67-83`
- **Category**: Performance
- **Severity**: HIGH

**Description**: Every session start runs `IndexService.initialize()` and multiple COUNT queries just for a status message.

**Remediation**: Use lightweight `SELECT COUNT(*)` without full initialization.

---

### TEST-001: Missing Tests for signal_detector.py
- **Location**: `src/git_notes_memory/hooks/signal_detector.py`
- **Category**: Test Coverage
- **Severity**: HIGH

**Description**: Core signal detection logic (600+ lines) has no dedicated test file.

**Remediation**: Create `tests/test_signal_detector.py` with parameterized tests for all signal types.

---

### TEST-002: Missing Tests for capture_decider.py
- **Location**: `src/git_notes_memory/hooks/capture_decider.py`
- **Category**: Test Coverage
- **Severity**: HIGH

**Description**: Capture decision logic (350+ lines) has no dedicated test file.

**Remediation**: Create `tests/test_capture_decider.py` testing threshold-based action selection.

---

### TEST-003: Missing Tests for context_builder.py
- **Location**: `src/git_notes_memory/hooks/context_builder.py`
- **Category**: Test Coverage
- **Severity**: HIGH

**Description**: Context building logic (400+ lines) has no dedicated test file.

**Remediation**: Create `tests/test_context_builder.py` testing budget calculation and XML output.

---

### DOC-001: CHANGELOG Missing v0.3.1 Entry
- **Location**: `CHANGELOG.md`
- **Category**: Documentation
- **Severity**: HIGH

**Description**: Current version is 0.3.1 (per pyproject.toml) but CHANGELOG only documents up to 0.3.0.

**Remediation**: Add 0.3.1 entry with bump-my-version, emoji markers, namespace styling features.

---

### QUAL-001: Bare Exception Handlers in Hook Entry Points
- **Location**: `hooks/session_start.py:38-40`, `hooks/user_prompt.py:41-46`, `hooks/stop.py:47-50`
- **Category**: Code Quality
- **Severity**: HIGH

**Description**: Bare `except Exception:` without logging masks potential bugs.

**Remediation**:
```python
except Exception as e:
    print(f"[memory-hook] Unexpected error: {e}", file=sys.stderr)
    print(json.dumps({"continue": True}))
    sys.exit(0)
```

---

## Medium Priority Findings (25)

### Architecture (7)

| ID | Location | Issue |
|----|----------|-------|
| ARCH-001 | `capture.py:176-898` | CaptureService has too many responsibilities (validation, locking, git ops, indexing, 8 capture types) |
| ARCH-002 | `signal_detector.py:36-107` | Signal patterns hardcoded - violates Open/Closed principle |
| ARCH-003 | All services | No Protocol/ABC interfaces for services - limits testability |
| ARCH-004 | `tests/conftest.py:17-96` | Singleton reset accesses private module attributes directly |
| ARCH-005 | `capture.py:908-923` | Default CaptureService lacks index/embedding services |
| ARCH-006 | Hook handlers | Direct service instantiation instead of dependency injection |
| ARCH-007 | `hooks/models.py:120-122` | `NoveltyResult.similar_memory_ids` uses mutable list in frozen dataclass |

### Performance (3)

| ID | Location | Issue |
|----|----------|-------|
| PERF-006 | `context_builder.py:375-409` | Sequential semantic searches (learnings + patterns) when parallel possible |
| PERF-007 | `novelty_checker.py:253-278` | Batch novelty check is sequential |
| PERF-008 | `index.py:677-685` | `get_all_ids()` uses unbounded fetchall() |

### Code Quality (5)

| ID | Location | Issue |
|----|----------|-------|
| QUAL-002 | `hooks/*.py` (7 files) | Duplicated hook entry point pattern (~100 lines repeated) |
| QUAL-003 | 8+ handler classes | Duplicated lazy `_get_*_service()` pattern |
| QUAL-004 | `signal_detector.py:254-299` | `_extract_context()` has cyclomatic complexity ~11 |
| QUAL-005 | `capture_decider.py:128-232` | `decide()` method has ~12 cyclomatic complexity |
| QUAL-006 | `novelty_checker.py:210-218` | Swallowed exception assumes novel without logging context |

### Test Coverage (6)

| ID | Location | Issue |
|----|----------|-------|
| TEST-004 | `session_start_handler.py` | No dedicated test file |
| TEST-005 | `user_prompt_handler.py` | No dedicated test file |
| TEST-006 | `stop_handler.py` | No dedicated test file |
| TEST-007 | `hooks/models.py` | No dedicated test file for model validation |
| TEST-008 | All hook handlers | End-to-end hook pipeline integration test missing |
| TEST-009 | `signal_detector.py` | Performance test for <50ms requirement missing |

### Documentation (4)

| ID | Location | Issue |
|----|----------|-------|
| DOC-002 | `README.md` | Missing troubleshooting section |
| DOC-003 | `hooks/hooks.json` | Matchers and timeouts undocumented |
| DOC-004 | Repository | No CONTRIBUTING.md file |
| DOC-005 | Repository | No SECURITY.md file |

---

## Low Priority Findings (32)

### Security (1)
- **SEC-001**: Lock file permissions 0o644 could be 0o600 (`capture.py:81`)

### Architecture (10)
- Inconsistent singleton variable naming across modules
- Large IndexService (1115 lines) but well-organized
- SyncService.reindex() is 79 lines
- HookConfig has 25+ configuration fields
- Test file naming confusion (test_hook_integration.py vs test_hooks_integration.py)
- Missing hook handler Protocol/ABC
- Context XML serialization mixed with data gathering
- Config parsing duplication between core and hooks

### Performance (4)
- Import of `json` inside functions (minor lookup overhead)
- Config loader creates default HookConfig for every load
- `dotenv.load_dotenv()` at module import (5-10ms)
- Signal detector compiles patterns on first use (5-10ms, but cached)

### Code Quality (17)
- Unused `escape_xml_text()` function
- Unused `classify()` method
- Single-letter variable 's' in comprehensions
- Ambiguous variable name 'result'
- Hardcoded thresholds 0.95, 0.7, 0.3 without constants
- Hardcoded summary length 200
- Hardcoded context window lengths
- Inconsistent import organization
- CaptureDecider.__init__ has 6 parameters
- Deep nesting in `_extract_tags()`

---

## Positive Observations

### Security Strengths
- All subprocess calls avoid `shell=True` - no command injection
- Proper `yaml.safe_load()` - no deserialization vulnerabilities
- Comprehensive path validation with symlink resolution
- Parameterized SQL queries - no SQL injection
- Input size limits prevent DoS
- Timeout protection on all hooks

### Architecture Strengths
- Consistent lazy initialization via `_get_*()` methods
- Services support dependency injection via constructors
- Clean configuration separation (`config.py`, `config_loader.py`)
- Excellent exception design with `recovery_action` hints
- Frozen dataclasses for immutability

### Code Quality Strengths
- 100% type hint coverage (mypy strict mode)
- Google-style docstrings consistently applied
- Graceful degradation - hooks never block Claude Code

### Test Strengths
- Proper pytest fixtures with autouse singleton reset
- Good test naming conventions
- Core services (capture, recall, index) well tested

### Documentation Strengths
- Excellent CLAUDE.md with complete environment variables
- Comprehensive USER_GUIDE.md and DEVELOPER_GUIDE.md
- All public APIs have docstrings

---

## Appendix

### Files Reviewed
- 17 core library modules (`src/git_notes_memory/`)
- 18 hook modules (`src/git_notes_memory/hooks/`)
- 8 hook entry scripts (`hooks/`)
- 30 test files (`tests/`)
- Configuration files (`pyproject.toml`, `plugin.json`, `hooks.json`)
- Documentation (`README.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/`)

### Specialist Agents Deployed
1. Security Analyst
2. Performance Engineer
3. Architecture Reviewer
4. Code Quality Analyst
5. Test Coverage Analyst
6. Documentation & Standards Reviewer

### Review Methodology
- Static analysis patterns
- OWASP Top 10 security checklist
- SOLID principles assessment
- Cyclomatic complexity estimation
- Test coverage gap analysis
