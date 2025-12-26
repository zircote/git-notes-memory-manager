# Remediation Tasks

**Project**: git-notes-memory
**Generated**: 2025-12-25
**Mode**: MAXALL (All severities will be addressed)

---

## Critical Priority (Immediate)

- [ ] **CRIT-001**: Implement circuit breaker for LLM provider calls
  - File: `src/git_notes_memory/subconsciousness/llm_client.py:322-344`
  - Action: Add CircuitBreaker class with failure_threshold=5, recovery_timeout=60s
  - Test: Add test_circuit_breaker.py with failure injection tests

- [ ] **CRIT-002**: Replace global mutable state with ServiceRegistry
  - Files: `subconsciousness/__init__.py`, `llm_client.py`, `implicit_capture_service.py`, `adversarial_detector.py`, `capture_store.py`
  - Action: Replace all `global _variable` patterns with ServiceRegistry.get()
  - Test: Verify thread safety and test isolation

---

## High Priority (This Sprint)

### Performance

- [ ] **HIGH-001**: Add term limit to pattern matching
  - File: `src/git_notes_memory/patterns.py:700-800`
  - Action: Limit to top 100 terms, add early termination
  - Test: Add benchmark test with 1000+ unique terms

- [ ] **HIGH-002**: Replace N+1 pattern with UPSERT
  - File: `src/git_notes_memory/index.py:865-889`
  - Action: Use INSERT...ON CONFLICT DO UPDATE
  - Test: Verify batch operations use single query

- [ ] **HIGH-005**: Pre-warm embedding model
  - File: `src/git_notes_memory/embedding.py:180-218`
  - Action: Trigger model load in hook initialization
  - Test: Measure first-call latency

### Database

- [ ] **HIGH-003**: Add composite index for common query
  - File: `src/git_notes_memory/index.py:94-101`
  - Action: `CREATE INDEX idx_memories_ns_spec_ts ON memories(namespace, spec, timestamp DESC)`
  - Test: EXPLAIN QUERY PLAN shows index usage

### Architecture

- [ ] **HIGH-004**: Decouple hooks from capture service
  - Files: `hooks/stop_handler.py`, `post_tool_use_handler.py`, `user_prompt_handler.py`
  - Action: Extract hook coordination layer with event/signal pattern
  - Test: Verify hooks don't directly import capture

### Test Coverage

- [ ] **HIGH-006**: Create missing test files
  - Create: `test_xml_formatter.py`
  - Create: `test_batcher.py`
  - Create: `test_llm_client.py`
  - Create: `test_project_detector.py`
  - Create: `test_namespace_styles.py`

### Resilience

- [ ] **HIGH-007**: Add jitter to exponential backoff
  - File: `src/git_notes_memory/subconsciousness/providers/anthropic.py:327-417`
  - Action: Add random jitter factor (0.5 + random())
  - Test: Verify retry timing variability

### Compliance

- [ ] **HIGH-008**: Implement PII scrubbing for logs
  - File: `src/git_notes_memory/hooks/hook_utils.py:162-178`
  - Action: Scrub user prompts and sensitive content before logging
  - Test: Verify log output contains no PII patterns

- [ ] **HIGH-009**: Document SQLite encryption approach
  - File: `src/git_notes_memory/index.py:191-199`
  - Action: Add SQLCipher integration or document encryption decision
  - Note: May defer to backlog if scope too large

---

## Medium Priority (Next Sprint)

### Architecture

- [ ] **MED-001**: Refactor IndexService (1247 lines)
  - File: `src/git_notes_memory/index.py`
  - Action: Split into IndexSchemaManager, MemoryRepository, VectorSearch, etc.

- [ ] **MED-002**: Refactor GitOps (1169 lines)
  - File: `src/git_notes_memory/git_ops.py`
  - Action: Split into GitNotes, GitRefs, GitCommands

- [ ] **MED-003**: Refactor LLMClient (519 lines)
  - File: `src/git_notes_memory/subconsciousness/llm_client.py`
  - Action: Extract ProviderManager, ResponseParser

### Database

- [ ] **MED-004**: Add ANALYZE after schema changes
  - File: `src/git_notes_memory/index.py:1200-1207`
  - Action: Add ANALYZE statement in vacuum() method

- [ ] **MED-005**: Fix connection leak in session_start_handler
  - File: `src/git_notes_memory/hooks/session_start_handler.py:78-91`
  - Action: Use `with closing(conn)` context manager

### Code Quality

- [ ] **MED-006**: Reduce parameter count in _do_capture
  - File: `src/git_notes_memory/capture.py:456-470`
  - Action: Group into CaptureConfig dataclass

- [ ] **MED-007**: Extract magic numbers to named constants
  - Files: patterns.py, multiple
  - Action: Create constants module for weights, timeouts

### Resilience

- [ ] **MED-008**: Add stale lock detection
  - File: `src/git_notes_memory/capture.py:58-123`
  - Action: Check lock age, clear if older than 5 minutes

- [ ] **MED-009**: Add partial failure recovery to implicit capture
  - File: `src/git_notes_memory/subconsciousness/implicit_capture_service.py:183-267`
  - Action: Persist already-processed memories before failure

### Compliance

- [ ] **MED-010**: Implement retention policy
  - File: `src/git_notes_memory/index.py`
  - Action: Add age-based cleanup with configurable policy

- [ ] **MED-011**: Add consent mechanism for auto-capture
  - File: `src/git_notes_memory/hooks/config_loader.py`
  - Action: Require explicit opt-in for PreCompact capture

### Documentation

- [ ] **MED-012**: Document subconsciousness layer
  - File: `docs/DEVELOPER_GUIDE.md`
  - Action: Add architecture section for LLM provider abstraction

- [ ] **MED-013**: Add missing API references
  - File: `docs/DEVELOPER_GUIDE.md`
  - Action: Document SyncService, LifecycleManager, PatternManager, SearchOptimizer

---

## Low Priority (Backlog)

### Performance

- [ ] **LOW-001**: Add embedding cache eviction
  - File: `src/git_notes_memory/index.py:40-54`

- [ ] **LOW-002**: Cache parsed timestamps
  - File: `src/git_notes_memory/index.py:728-762`

- [ ] **LOW-003**: Cache index statistics
  - File: `src/git_notes_memory/index.py:1105-1155`

### Code Quality

- [ ] **LOW-004**: Run dead code detection
  - Action: Use vulture or similar tool

### Test Coverage

- [ ] **LOW-005**: Add edge case tests
  - Action: Test boundary conditions, empty inputs

### Resilience

- [ ] **LOW-006**: Add health check endpoint
  - File: `src/git_notes_memory/sync.py`

### Documentation

- [ ] **LOW-007**: Add CLI documentation
  - File: `src/git_notes_memory/main.py`

### Compliance

- [ ] **LOW-008**: Add time-based log rotation
  - File: `src/git_notes_memory/hooks/hook_utils.py:124-131`

---

## Verification Checklist

After remediation:

- [ ] All 315+ tests pass
- [ ] mypy --strict clean
- [ ] ruff check clean
- [ ] bandit security scan clean
- [ ] Coverage ≥80%
- [ ] No new lint warnings introduced
