# Remediation Tasks

Generated from code review on 2025-12-24.

---

## Critical (Do Immediately)

*No critical findings*

---

## High Priority (This Sprint)

### Performance

- [ ] `sync.py:280-332` Batch git subprocess calls in reindex - PERF-001
- [ ] `sync.py:303-313` Use embed_batch() instead of sequential embed() - PERF-002
- [ ] `recall.py:497-515` Implement batch hydration to reduce N+1 git calls - PERF-003

### Architecture

- [ ] `capture.py:905-928` Refactor singleton pattern to service registry - ARCH-001
- [ ] `tests/conftest.py:46-95` Remove direct access to private module variables - ARCH-002

### Test Coverage

- [ ] `hooks/hook_utils.py` Create tests/test_hook_utils.py - TEST-001
- [ ] `hooks/session_analyzer.py` Create tests/test_session_analyzer.py - TEST-002

### Documentation

- [ ] `hooks/post_tool_use_handler.py` Add module docstring - DOC-001
- [ ] `hooks/pre_compact_handler.py` Add module docstring - DOC-001
- [ ] `hooks/stop_handler.py` Add module docstring - DOC-001
- [ ] `hooks/user_prompt_handler.py` Add module docstring - DOC-001
- [ ] `index.py` Add method docstrings to IndexService - DOC-002
- [ ] `README.md` Add API Reference section - DOC-003

---

## Medium Priority (Next 2-3 Sprints)

### Performance

- [ ] `embedding.py:180-218` Add embedding model pre-warming - PERF-004
- [ ] `hooks/session_start_handler.py:195-196` Use lightweight SQL for metadata - PERF-005
- [ ] `recall.py:598-628` Use generator for token estimation - PERF-006
- [ ] `index.py:512-518` Cache struct format with @lru_cache - PERF-007
- [ ] `index.py:167-171` Add thread-local connection pooling - PERF-008

### Architecture

- [ ] `hooks/config_loader.py:80-183` Extract hook-specific config classes - ARCH-003
- [ ] `hooks/config_loader.py:67-78` Consolidate enum definitions - ARCH-004
- [ ] `hooks/signal_detector.py` Use instance-level pattern caching - ARCH-005
- [ ] `recall.py:107-130` Standardize dependency injection - ARCH-006
- [ ] `capture.py:260-372` Extract methods from capture() - ARCH-007
- [ ] `index.py:386-388` Store tags as JSON arrays - ARCH-008

### Code Quality

- [ ] `hooks/stop_handler.py:58-74` Use hook_utils.read_json_input() - QUAL-001
- [ ] `hooks/context_builder.py:558-561` Catch specific exceptions - QUAL-002

### Documentation

- [ ] `git_ops.py` Add complete method docstrings - DOC-004
- [ ] `README.md` Document all environment variables - DOC-005
- [ ] `exceptions.py` Add exception handling guide - DOC-006
- [ ] Create CHANGELOG.md if missing - DOC-007

---

## Low Priority (Backlog)

### Security

- [ ] `hooks/signal_detector.py:36-139` Add input length limit before regex - SEC-001
- [ ] `git_ops.py:147-165` Sanitize paths in error messages - SEC-002

### Performance

- [ ] `note_parser.py:209-220` Consider fast-path YAML parsing - PERF-009
- [ ] `hooks/signal_detector.py:461-465` Remove redundant sort - PERF-010
- [ ] `hooks/stop_handler.py:66-74` Remove dict() wrapper - PERF-011
- [ ] `index.py:77` Add composite index for ns+timestamp - PERF-012
- [ ] `hooks/context_builder.py:366-388` Batch database queries - PERF-013

### Architecture

- [ ] `hooks/hook_utils.py:75` Standardize cache naming - ARCH-009
- [ ] `hooks/config_loader.py:175-183` Document budget tier values - ARCH-010
- [ ] `hooks/hook_utils.py:380-384` Simplify path validation - ARCH-011
- [ ] `models.py:146-204` Consider __getattr__ for MemoryResult - ARCH-012
- [ ] `models.py:287-348` Move CaptureAccumulator to builders module - ARCH-013

### Code Quality

- [ ] Multiple hooks files - Extract shared service loader - QUAL-003
- [ ] `hooks/capture_decider.py:305` Use MAX_SUMMARY_CHARS constant - QUAL-004
- [ ] `hooks/signal_detector.py:202-206` Extract context window constant - QUAL-005
- [ ] Multiple files - Standardize service getter naming - QUAL-006
- [ ] `capture.py:58` Remove or implement _timeout parameter - QUAL-007
- [ ] `hooks/signal_detector.py:310-340` Extract pattern matching methods - QUAL-008
- [ ] `hooks/session_analyzer.py:145` Use PathLike type hint - QUAL-009
- [ ] `hooks/hook_utils.py:355-357` Check whitespace-only paths - QUAL-010
- [ ] `hooks/namespace_styles.py:47-68` Add return description to docstring - QUAL-011
- [ ] `tests/conftest.py:118-121` Replace sample fixture placeholder - QUAL-012

### Documentation

- [ ] `commands/*.md` Add consistent Related Commands sections - DOC-008
- [ ] `embedding.py` Add usage examples to class docstring - DOC-009
- [ ] `models.py` Add property docstrings - DOC-010

---

## Summary

| Priority | Count | Categories |
|----------|-------|------------|
| Critical | 0 | - |
| High | 13 | Performance (3), Architecture (2), Test Coverage (2), Documentation (6) |
| Medium | 17 | Performance (5), Architecture (6), Code Quality (2), Documentation (4) |
| Low | 23 | Security (2), Performance (5), Architecture (5), Code Quality (10), Documentation (3) |
| **Total** | **53** | |
