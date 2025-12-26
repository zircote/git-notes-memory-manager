# Remediation Tasks

**Generated:** 2025-12-26
**Mode:** MAXALL (automatic remediation enabled)

---

## Critical Priority (Immediate)

- [ ] **CRIT-001**: Fix SQLite connection leak in index.py:217-250
  - Add try/finally to close connection on initialization failure
  - File: `src/git_notes_memory/index.py`

- [ ] **MED-001**: Fix SQLite connection in session hook
  - Add try/finally to `_get_memory_count()`
  - File: `src/git_notes_memory/hooks/session_start_handler.py:86-90`

---

## High Priority (Short-term)

- [ ] **HIGH-005**: Add Quick Start section to README.md
  - Minimal capture/recall example

- [ ] **HIGH-006**: Create docs/ENV.md
  - Consolidate all environment variables from config, hooks, security, observability

- [ ] **HIGH-007**: Add CHANGELOG v0.12.0 entry
  - Document changes since v0.11.0

- [ ] **MED-013**: Fix deprecated exception reference in DEVELOPER_GUIDE.md
  - Change `MemoryError` to `MemoryPluginError`
  - File: `docs/DEVELOPER_GUIDE.md:511-523`

---

## Medium Priority

- [ ] **HIGH-002**: Add strict audit mode option
  - Add `SECRETS_FILTER_AUDIT_STRICT` environment variable
  - File: `src/git_notes_memory/security/audit.py`

- [ ] **MED-005**: Wire secrets filtering in default capture service
  - Or document explicit opt-in requirement
  - File: `src/git_notes_memory/capture.py`

- [ ] **LOW-004**: Add status+timestamp composite index
  - `idx_memories_status_timestamp`
  - File: `src/git_notes_memory/index.py`

- [ ] **LOW-010**: Add warning log for batch fetch fallback
  - Log exception details when falling back to sequential
  - File: `src/git_notes_memory/git_ops.py:552-554`

---

## Observability Verification

- [ ] Verify metrics collection functional
- [ ] Verify tracing spans created correctly
- [ ] Verify health check endpoints working
- [ ] Test CLI commands: /health, /metrics, /traces

---

## Documentation Updates

- [ ] **MED-014**: Update DEVELOPER_GUIDE.md package structure
- [ ] **LOW-011**: Create security/README.md
- [ ] **LOW-012**: Add observability env vars to CLAUDE.md

---

## Backlog (Low Priority)

- [ ] HIGH-001: Git retry logic with exponential backoff
- [ ] HIGH-004: Circuit breaker for remote operations
- [ ] MED-002: Evaluate FTS5 for text search
- [ ] MED-004: Optimize batch insert with executemany
- [ ] MED-006: Per-migration transaction handling
- [ ] MED-007: Detect-secrets fallback pattern matching
- [ ] MED-008: Explicit timeout for session start fetch
- [ ] MED-009: Git note write verification
- [ ] MED-010: Query length limit for recall
- [ ] MED-011: Chunked reindex for memory efficiency
- [ ] MED-012: Rate limiting for user prompt handler
- [ ] LOW-005: Explicit database file permissions
- [ ] LOW-006: Extend path sanitization coverage
- [ ] LOW-007: Config float bounds checking
- [ ] LOW-008: Label cardinality limit in metrics
- [ ] LOW-009: Graceful shutdown signal handlers
