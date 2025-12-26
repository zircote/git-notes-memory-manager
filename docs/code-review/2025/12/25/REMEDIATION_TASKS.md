# Remediation Tasks

**Project**: git-notes-memory
**Date**: 2025-12-25
**Mode**: MAXALL - All findings will be addressed

---

## 🔴 Critical (4 tasks)

- [ ] **CRIT-001** [Performance] Add exponential backoff to lock acquisition in `capture.py:89-102`
- [ ] **CRIT-002** [Resilience] Add timeout to subprocess calls in `git_ops.py:67-85`
- [ ] **CRIT-003** [Resilience] Fix connection leak in error paths in `index.py:156-180`
- [ ] **CRIT-004** [Resilience] Replace SIGALRM with threading.Timer in `hook_utils.py:45-62`

---

## 🟠 High (21 tasks)

### Resource Management
- [ ] **HIGH-001** [Performance] Add subprocess cleanup in `git_ops.py`
- [ ] **HIGH-002** [Database] Fix N+1 query pattern in `lifecycle.py:45-78`
- [ ] **HIGH-003** [Database] Fix N+1 query pattern in `patterns.py:34-56`
- [ ] **HIGH-004** [Database] Add composite index on (namespace, timestamp)

### Architecture
- [ ] **HIGH-005** [Architecture] Refactor IndexService god class (defer - major refactor)
- [ ] **HIGH-006** [Architecture] Refactor GitOps god class (defer - major refactor)
- [ ] **HIGH-007** [Architecture] Address circular import risk (defer - needs interface design)
- [ ] **HIGH-008** [Architecture] Add storage backend abstraction (defer - roadmap item)

### Code Quality
- [ ] **HIGH-009** [Quality] Replace bare exception in `embedding.py:89-95`
- [ ] **HIGH-010** [Quality] Replace bare exception in `git_ops.py:245-252`
- [ ] **HIGH-011** [Quality] Extract FileLock class to reduce duplication

### Test Coverage
- [ ] **HIGH-012** [Testing] Improve `observability/__init__.py` coverage (42% → 80%)
- [ ] **HIGH-013** [Testing] Improve `novelty_checker.py` coverage (51% → 80%)

### Documentation
- [ ] **HIGH-014** [Docs] Create `docs/observability.md`
- [ ] **HIGH-015** [Docs] Add API reference generation (defer - needs tooling)
- [ ] **HIGH-016** [Docs] Expand CLI command help
- [ ] **HIGH-017** [Docs] Update CHANGELOG with 0.4.0 features

### Compliance
- [ ] **HIGH-018** [Compliance] Sanitize sensitive data in debug logs
- [ ] **HIGH-019** [Compliance] Redact git URL credentials in logs

### Resilience
- [ ] **HIGH-020** [Resilience] Add circuit breaker for embedding service
- [ ] **HIGH-021** [Resilience] Enhance /memory:health diagnostics

---

## 🟡 Medium (36 tasks)

### Performance (MED-001 to MED-002)
- [ ] Add query result limits with pagination
- [ ] Implement lazy hydration for memory results

### Architecture (MED-003 to MED-008)
- [ ] Reduce handler coupling to context builder
- [ ] Add dataclass validation
- [ ] Reduce environment coupling in config
- [ ] Add YAML schema validation
- [ ] Separate sync logic from IO
- [ ] Clarify lifecycle state machine

### Code Quality (MED-009 to MED-013)
- [ ] Replace magic numbers with named constants
- [ ] Standardize error messages in hooks
- [ ] Break down long methods
- [ ] Simplify complex conditionals
- [ ] Flatten nested try-except blocks

### Test Coverage (MED-014 to MED-016)
- [ ] Improve project_detector.py coverage (63% → 80%)
- [ ] Improve session_analyzer.py coverage (68% → 80%)
- [ ] Add novelty_checker edge case tests

### Documentation (MED-017 to MED-026)
- [ ] Add handler module docstrings
- [ ] Add observability module docstrings
- [ ] Document template format
- [ ] Create environment variable reference
- [ ] Expand model docstrings
- [ ] Document custom exceptions
- [ ] Add hook configuration to README
- [ ] Add observability section to README
- [ ] Update CLAUDE.md with missing env vars
- [ ] Add test guidelines to CONTRIBUTING.md

### Database (MED-027 to MED-029)
- [ ] Add VACUUM schedule
- [ ] Configure WAL checkpointing
- [ ] Monitor index fragmentation

### Resilience (MED-030 to MED-032)
- [ ] Add model load retry
- [ ] Add fallback for empty search results
- [ ] Implement partial sync recovery

### Compliance (MED-033 to MED-034)
- [ ] Complete audit trail
- [ ] Adjust query logging level

### Security (MED-035 to MED-036)
- [ ] Review command injection surface
- [ ] Verify YAML safe_load usage ✓

---

## 🟢 Low (29 tasks)

### Performance (LOW-001 to LOW-006)
- [ ] Cache logger instances
- [ ] Optimize dataclass copying
- [ ] Add model warmup
- [ ] Tune connection pool size
- [ ] Cache hook config
- [ ] Move sorting to SQL

### Architecture (LOW-007 to LOW-011)
- [ ] Create exception hierarchy
- [ ] Add config validation
- [ ] Organize imports consistently
- [ ] Remove hardcoded template paths
- [ ] Standardize command naming

### Code Quality (LOW-012 to LOW-015)
- [ ] Resolve TODOs
- [ ] Standardize test naming
- [ ] Use consistent string quotes
- [ ] Normalize line lengths

### Test Coverage (LOW-016 to LOW-017)
- [ ] Improve exporters.py coverage (72% → 80%)
- [ ] Improve tracing.py coverage (78% → 80%)

### Documentation (LOW-018 to LOW-022)
- [ ] Add test docstrings
- [ ] Complete pyproject.toml metadata
- [ ] Update LICENSE year
- [ ] Create SECURITY.md
- [ ] Create CODE_OF_CONDUCT.md

### Database (LOW-023 to LOW-024)
- [ ] Add schema version tracking
- [ ] Add backup before migration

### Resilience (LOW-025 to LOW-026)
- [ ] Add retry on transient git failures
- [ ] Handle graceful shutdown

### Compliance (LOW-027 to LOW-029)
- [ ] Configure log rotation
- [ ] Add session ID to all logs
- [ ] Check for dependency advisories

---

## Remediation Strategy

### MAXALL Mode Contract

Per MAXALL mode, remediation will proceed as follows:

1. **Critical**: Fix all 4 immediately
2. **High**: Fix 13 actionable items (defer 8 that require major refactoring)
3. **Medium**: Fix 25 actionable items
4. **Low**: Fix 20 actionable items

### Deferred Items (Roadmap)

| Finding | Reason | Target |
|---------|--------|--------|
| HIGH-005 | God class refactor needs design | v0.5.0 |
| HIGH-006 | God class refactor needs design | v0.5.0 |
| HIGH-007 | Circular imports need interface design | v0.5.0 |
| HIGH-008 | Storage abstraction is architectural | v0.6.0 |
| HIGH-015 | API docs need sphinx/mkdocs setup | v0.5.0 |
| MED-003 | Handler coupling needs refactor | v0.5.0 |
| MED-007 | Sync separation needs refactor | v0.5.0 |
| MED-008 | Lifecycle state machine needs design | v0.5.0 |

---

*Generated by claude-spec:deep-clean MAXALL mode*
