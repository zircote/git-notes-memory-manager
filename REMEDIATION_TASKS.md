# Remediation Tasks

Generated from code review on 2025-12-20. Use this as a checklist for addressing findings.

---

## Critical (Do Immediately)

- [ ] **PERF-001** `index.py:1006-1022` - Fix N+1 query pattern in `search_vector()` with single JOIN query
- [ ] **PERF-002** `novelty_checker.py:99-113` - Add `is_loaded` check to skip novelty check when embedding model not loaded

---

## High Priority (This Sprint)

### Performance
- [ ] **PERF-003** `config.py:219-225` - Cache project identifier or read .git/config directly
- [ ] **PERF-004** `project_detector.py:146-176` - Add `@lru_cache` to `detect_project()`
- [ ] **PERF-005** `session_start_handler.py:67-83` - Use lightweight COUNT query without full index init

### Test Coverage
- [ ] **TEST-001** Create `tests/test_signal_detector.py` with parameterized tests for all signal types
- [ ] **TEST-002** Create `tests/test_capture_decider.py` testing threshold-based action selection
- [ ] **TEST-003** Create `tests/test_context_builder.py` testing budget calculation and XML output

### Code Quality
- [ ] **QUAL-001** `hooks/*.py` (7 files) - Add error logging to bare exception handlers

### Documentation
- [ ] **DOC-001** `CHANGELOG.md` - Add v0.3.1 entry with bump-my-version, emoji markers, namespace styling

---

## Medium Priority (Next 2-3 Sprints)

### Architecture
- [ ] **ARCH-001** `capture.py` - Extract validation logic to `CaptureValidator` class
- [ ] **ARCH-002** `signal_detector.py` - Allow pattern registration instead of hardcoded `SIGNAL_PATTERNS`
- [ ] **ARCH-003** All services - Define Protocol interfaces (`CaptureServiceProtocol`, `RecallServiceProtocol`, `StorageBackend`)
- [ ] **ARCH-004** `conftest.py` - Add `reset()` functions to service APIs or use central registry
- [ ] **ARCH-005** `capture.py:908-923` - Have `get_default_service()` return fully initialized service
- [ ] **ARCH-006** Hook handlers - Inject services via HookConfig or service container
- [ ] **ARCH-007** `hooks/models.py:120-122` - Change `similar_memory_ids: list[str]` to `tuple[str, ...]`

### Performance
- [ ] **PERF-006** `context_builder.py:375-409` - Consider parallel semantic searches with concurrent.futures
- [ ] **PERF-007** `novelty_checker.py:253-278` - Batch embedding and search for multiple signals
- [ ] **PERF-008** `index.py:677-685` - Add LIMIT to `get_all_ids()` or document unbounded nature

### Code Quality
- [ ] **QUAL-002** `hooks/*.py` - Extract common handler boilerplate to `run_handler()` utility
- [ ] **QUAL-003** Handler classes - Create lazy service loader decorator/mixin
- [ ] **QUAL-004** `signal_detector.py:254-299` - Refactor `_extract_context()` into smaller methods
- [ ] **QUAL-005** `capture_decider.py:128-232` - Split `decide()` into `_determine_action()`, `_generate_suggestions()`
- [ ] **QUAL-006** `novelty_checker.py:210-218` - Log error type before assuming novel

### Test Coverage
- [ ] **TEST-004** Create tests for `session_start_handler.py`
- [ ] **TEST-005** Create tests for `user_prompt_handler.py`
- [ ] **TEST-006** Create tests for `stop_handler.py`
- [ ] **TEST-007** Create tests for `hooks/models.py` validation
- [ ] **TEST-008** Add end-to-end hook pipeline integration test
- [ ] **TEST-009** Add performance test asserting signal detection <50ms

### Documentation
- [ ] **DOC-002** `README.md` - Add troubleshooting section for common issues
- [ ] **DOC-003** `docs/` - Document hooks.json matchers and timeouts
- [ ] **DOC-004** Create `CONTRIBUTING.md` file
- [ ] **DOC-005** Create `SECURITY.md` file

---

## Low Priority (Backlog)

### Security
- [ ] **SEC-001** `capture.py:81` - Change lock file permissions from 0o644 to 0o600

### Code Quality
- [ ] Remove unused `escape_xml_text()` in `xml_formatter.py:220-244`
- [ ] Remove or document unused `classify()` in `signal_detector.py:385-398`
- [ ] Replace single-letter `s` with `signal` in comprehensions
- [ ] Rename ambiguous `result` variable to `parsed_data` in `hook_utils.py:173`
- [ ] Define constants for thresholds: `AUTO_CAPTURE_THRESHOLD = 0.95`, etc.
- [ ] Define `MAX_SUMMARY_LENGTH = 200` constant
- [ ] Define `CONTENT_PREVIEW_LENGTH = 200` constant
- [ ] Standardize singleton variable naming to `_default_service`
- [ ] Refactor CaptureDecider.__init__ to use config dataclass
- [ ] Extract `_match_tech_keywords()` from nested loop in `_extract_tags()`

### Architecture
- [ ] Split HookConfig into hook-specific config classes
- [ ] Consolidate test file naming: `test_hooks_unit.py`, `test_hooks_integration.py`, `test_hooks_e2e.py`
- [ ] Extract ContextBuilder XML serialization to `ContextSerializer` class

### Test Coverage
- [ ] Add parameterized fixture for shorthand marker tests
- [ ] Create JSON hook input fixtures for all hook types
- [ ] Create CaptureSignal factory fixture
- [ ] Replace `time.sleep()` with threading events in lock tests
- [ ] Use `freezegun` for time-dependent tests
- [ ] Verify all environment variables reset after embedding tests

---

## Metrics

| Priority | Count | Effort Estimate |
|----------|-------|-----------------|
| Critical | 2 | 2-4 hours |
| High | 10 | 2-3 days |
| Medium | 25 | 1-2 weeks |
| Low | 20+ | Ongoing |

---

## Notes

- All findings are documented in detail in `CODE_REVIEW.md`
- Tasks are organized by priority, then by category within priority
- Effort estimates assume familiarity with the codebase
- Consider addressing related tasks together (e.g., all ARCH-* items)
