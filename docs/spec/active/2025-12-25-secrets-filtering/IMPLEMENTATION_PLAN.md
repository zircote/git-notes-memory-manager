# Implementation Plan: Secrets Filtering and Sensitive Data Protection

## Overview

This document provides the phased implementation plan for secrets filtering. The implementation follows a bottom-up approach, building foundational components first, then integrating them into the capture pipeline.

---

## Phase 1: Foundation

**Goal**: Establish module structure, models, and configuration.

### Task 1.1: Create Security Module Structure
**File**: `src/git_notes_memory/security/__init__.py`
- [ ] Create security/ directory
- [ ] Create __init__.py with public exports
- [ ] Follow existing lazy-loading pattern

### Task 1.2: Define Models
**File**: `src/git_notes_memory/security/models.py`
- [ ] SecretType enum (api_key, password, private_key, connection_string, pii_ssn, pii_credit_card, pii_phone, high_entropy)
- [ ] FilterStrategy enum (REDACT, MASK, BLOCK, WARN)
- [ ] FilterAction enum (REDACTED, MASKED, BLOCKED, WARNED, ALLOWED)
- [ ] SecretDetection dataclass (frozen)
- [ ] FilterResult dataclass (frozen)
- [ ] AllowlistEntry dataclass (frozen)
- [ ] AuditEntry dataclass (frozen)

### Task 1.3: Define Configuration
**File**: `src/git_notes_memory/security/config.py`
- [ ] SecretsConfig dataclass with all settings
- [ ] Environment variable loading
- [ ] YAML config file loading
- [ ] Per-namespace strategy overrides
- [ ] Default configuration values

### Task 1.4: Define Exceptions
**File**: `src/git_notes_memory/security/exceptions.py`
- [ ] SecretsFilteringError base class
- [ ] BlockedContentError with detections
- [ ] AllowlistError
- [ ] AuditLogError

### Task 1.5: Create Factory Function
**File**: `src/git_notes_memory/__init__.py`
- [ ] Add get_secrets_filtering_service() factory
- [ ] Follow singleton pattern
- [ ] Lazy initialization

---

## Phase 2: Core Detection

**Goal**: Implement all detection algorithms.

### Task 2.1: Implement PatternDetector
**File**: `src/git_notes_memory/security/patterns.py`
- [ ] PatternRule dataclass
- [ ] PatternDetector class
- [ ] OpenAI pattern (sk-proj-*, sk-*)
- [ ] Anthropic pattern (sk-ant-*)
- [ ] GitHub patterns (ghp_, gho_, ghu_, ghs_, ghr_)
- [ ] AWS Access Key pattern (AKIA*)
- [ ] AWS Secret Key pattern (40-char after aws_secret)
- [ ] Stripe patterns (sk_live_, pk_live_)
- [ ] Slack patterns (xoxb-, xoxp-, xoxa-)
- [ ] Generic password patterns
- [ ] Basic auth pattern (://user:pass@)
- [ ] Bearer token pattern
- [ ] Private key patterns (RSA, DSA, EC, OpenSSH)
- [ ] Connection string patterns (postgres, mysql, mongodb)
- [ ] Compile all patterns at init
- [ ] detect() method returning tuple[SecretDetection, ...]

### Task 2.2: Write PatternDetector Tests
**File**: `tests/security/test_patterns.py`
- [ ] Test each pattern with valid examples
- [ ] Test patterns don't match false positives
- [ ] Test performance (<3ms for typical content)
- [ ] Test edge cases (partial matches, multiple matches)

### Task 2.3: Implement EntropyAnalyzer
**File**: `src/git_notes_memory/security/entropy.py`
- [ ] shannon_entropy() function
- [ ] EntropyAnalyzer class
- [ ] Token extraction (split by whitespace, punctuation)
- [ ] Character set detection (base64, hex, alphanumeric)
- [ ] Threshold-based detection
- [ ] Minimum length filtering
- [ ] analyze() method returning tuple[SecretDetection, ...]

### Task 2.4: Write EntropyAnalyzer Tests
**File**: `tests/security/test_entropy.py`
- [ ] Test entropy calculation
- [ ] Test threshold detection
- [ ] Test character set detection
- [ ] Test minimum length
- [ ] Test performance (<2ms)

### Task 2.5: Implement PIIDetector
**File**: `src/git_notes_memory/security/pii.py`
- [ ] PIIDetector class
- [ ] SSN pattern (XXX-XX-XXXX)
- [ ] Credit card pattern with Luhn validation
- [ ] Phone number patterns (US formats)
- [ ] luhn_check() static method
- [ ] detect() method returning tuple[SecretDetection, ...]

### Task 2.6: Write PIIDetector Tests
**File**: `tests/security/test_pii.py`
- [ ] Test SSN detection
- [ ] Test credit card detection with Luhn
- [ ] Test phone number detection
- [ ] Test false positive handling

---

## Phase 3: Integration Components

**Goal**: Build integration components for filtering pipeline.

### Task 3.1: Implement Redactor
**File**: `src/git_notes_memory/security/redactor.py`
- [ ] Redactor class
- [ ] REDACT strategy ([REDACTED:{type}])
- [ ] MASK strategy (show first/last 4)
- [ ] BLOCK strategy (raise BlockedContentError)
- [ ] WARN strategy (log, return unchanged)
- [ ] apply() method handling overlapping detections
- [ ] Handle detections in order (longest first)

### Task 3.2: Write Redactor Tests
**File**: `tests/security/test_redactor.py`
- [ ] Test each strategy
- [ ] Test overlapping detections
- [ ] Test empty detections
- [ ] Test long content

### Task 3.3: Implement AllowlistManager
**File**: `src/git_notes_memory/security/allowlist.py`
- [ ] AllowlistManager class
- [ ] YAML file loading
- [ ] SHA-256 hash storage
- [ ] is_allowed() method
- [ ] add() method
- [ ] remove() method
- [ ] list_entries() method
- [ ] Per-namespace allowlists

### Task 3.4: Write AllowlistManager Tests
**File**: `tests/security/test_allowlist.py`
- [ ] Test hash-based storage
- [ ] Test add/remove
- [ ] Test namespace filtering
- [ ] Test persistence

### Task 3.5: Implement SecretsFilteringService
**File**: `src/git_notes_memory/security/service.py`
- [ ] SecretsFilteringService class
- [ ] Compose PatternDetector, EntropyAnalyzer, PIIDetector
- [ ] Integrate AllowlistManager
- [ ] Integrate Redactor
- [ ] filter() method orchestrating all components
- [ ] scan() method for detection only
- [ ] Deduplication of overlapping detections
- [ ] Confidence-based prioritization

### Task 3.6: Write SecretsFilteringService Tests
**File**: `tests/security/test_service.py`
- [ ] Test full filtering pipeline
- [ ] Test allowlist integration
- [ ] Test strategy selection
- [ ] Test namespace overrides

### Task 3.7: Integrate with CaptureService
**File**: `src/git_notes_memory/capture.py`
- [ ] Add _secrets_service attribute
- [ ] Filter summary before processing
- [ ] Filter content before processing
- [ ] Handle BLOCK strategy
- [ ] Include filtering warnings in CaptureResult
- [ ] Update capture() method

### Task 3.8: Write CaptureService Integration Tests
**File**: `tests/test_capture_secrets.py`
- [ ] Test secrets filtered before storage
- [ ] Test secrets filtered before embedding
- [ ] Test BLOCK strategy rejection
- [ ] Test graceful degradation

---

## Phase 4: Commands and Audit

**Goal**: Implement CLI commands and audit logging.

### Task 4.1: Implement AuditLogger
**File**: `src/git_notes_memory/security/audit.py`
- [ ] AuditLogger class
- [ ] JSON Lines format
- [ ] log_detection() method
- [ ] log_scan() method
- [ ] query() method with filters
- [ ] File rotation support
- [ ] Thread-safe writes

### Task 4.2: Write AuditLogger Tests
**File**: `tests/security/test_audit.py`
- [ ] Test log format
- [ ] Test query filtering
- [ ] Test file rotation
- [ ] Test thread safety

### Task 4.3: Implement /memory:scan-secrets Command
**File**: `src/git_notes_memory/commands/scan_secrets.py`
- [ ] Command implementation
- [ ] --namespace filter
- [ ] --fix flag for remediation
- [ ] --dry-run flag
- [ ] Progress reporting
- [ ] Summary output

### Task 4.4: Implement /memory:secrets-allowlist Command
**File**: `src/git_notes_memory/commands/allowlist.py`
- [ ] add subcommand
- [ ] remove subcommand
- [ ] list subcommand
- [ ] --namespace flag

### Task 4.5: Implement /memory:test-secret Command
**File**: `src/git_notes_memory/commands/test_secret.py`
- [ ] Command implementation
- [ ] Show detection type
- [ ] Show strategy that would apply
- [ ] Show confidence score

### Task 4.6: Implement /memory:audit-log Command
**File**: `src/git_notes_memory/commands/audit_log.py`
- [ ] Command implementation
- [ ] --since filter
- [ ] --namespace filter
- [ ] --type filter
- [ ] --json output option
- [ ] Human-readable formatting

### Task 4.7: Update Plugin Commands
**File**: `plugin.json`
- [ ] Add scan-secrets command definition
- [ ] Add secrets-allowlist command definition
- [ ] Add test-secret command definition
- [ ] Add audit-log command definition

### Task 4.8: Write Command Tests
**File**: `tests/commands/test_secrets_commands.py`
- [ ] Test scan-secrets
- [ ] Test allowlist operations
- [ ] Test test-secret
- [ ] Test audit-log

---

## Phase 5: Testing and Documentation

**Goal**: Comprehensive testing and documentation.

### Task 5.1: Integration Tests
**File**: `tests/security/test_integration.py`
- [ ] End-to-end capture with secrets
- [ ] Retrospective scanning
- [ ] Allowlist workflow
- [ ] Audit log verification

### Task 5.2: Performance Tests
**File**: `tests/security/test_performance.py`
- [ ] Benchmark pattern detection
- [ ] Benchmark entropy analysis
- [ ] Benchmark full pipeline
- [ ] Verify <10ms target

### Task 5.3: Update Documentation
**Files**: Various
- [ ] Update README.md with secrets filtering section
- [ ] Update CLAUDE.md with new commands
- [ ] Add secrets filtering to hook documentation
- [ ] Document configuration options

### Task 5.4: Quality Checks
- [ ] Run make quality
- [ ] Verify 90% code coverage for security module
- [ ] Fix any type errors
- [ ] Fix any lint issues

---

## Dependency Graph

```
Phase 1 (Foundation)
    │
    ├── Task 1.1: Module Structure
    ├── Task 1.2: Models
    ├── Task 1.3: Configuration
    ├── Task 1.4: Exceptions
    └── Task 1.5: Factory Function
          │
          ▼
Phase 2 (Core Detection) ─ Can run in parallel
    │
    ├── Task 2.1-2.2: PatternDetector + Tests
    ├── Task 2.3-2.4: EntropyAnalyzer + Tests
    └── Task 2.5-2.6: PIIDetector + Tests
          │
          ▼
Phase 3 (Integration)
    │
    ├── Task 3.1-3.2: Redactor + Tests
    ├── Task 3.3-3.4: AllowlistManager + Tests
    │       │
    │       ▼
    ├── Task 3.5-3.6: SecretsFilteringService + Tests
    │       │
    │       ▼
    └── Task 3.7-3.8: CaptureService Integration + Tests
          │
          ▼
Phase 4 (Commands & Audit)
    │
    ├── Task 4.1-4.2: AuditLogger + Tests
    ├── Task 4.3: scan-secrets Command
    ├── Task 4.4: allowlist Command
    ├── Task 4.5: test-secret Command
    ├── Task 4.6: audit-log Command
    ├── Task 4.7: Plugin Registration
    └── Task 4.8: Command Tests
          │
          ▼
Phase 5 (Testing & Docs)
    │
    ├── Task 5.1: Integration Tests
    ├── Task 5.2: Performance Tests
    ├── Task 5.3: Documentation
    └── Task 5.4: Quality Checks
```

---

## Estimates

| Phase | Tasks | Complexity |
|-------|-------|------------|
| Phase 1: Foundation | 5 | Low |
| Phase 2: Core Detection | 6 | Medium |
| Phase 3: Integration | 8 | High |
| Phase 4: Commands & Audit | 8 | Medium |
| Phase 5: Testing & Docs | 4 | Medium |
| **Total** | **31** | - |

---

## Success Criteria

- [ ] All P0 requirements implemented
- [ ] Pattern detection >95% coverage of known secret types
- [ ] False positive rate <5%
- [ ] Performance <10ms added latency
- [ ] Test coverage >90% for security module
- [ ] All commands functional
- [ ] Audit logging compliant with SOC2 requirements
- [ ] Documentation complete
