# Requirements: Secrets Filtering and Sensitive Data Protection

## Overview

This document defines the product requirements for implementing secrets filtering and sensitive data protection in the git-notes-memory system.

## User Stories

### US-1: Automatic Secret Detection
As a developer, I want the memory system to automatically detect and filter secrets so that sensitive data is never stored in memories.

### US-2: Configurable Filtering
As a security administrator, I want to configure filtering strategies per namespace so that I can balance security with usability.

### US-3: Allowlist Management
As a developer, I want to allowlist known-safe values (like example API keys in documentation) so that legitimate content isn't incorrectly filtered.

### US-4: Audit Trail
As a compliance officer, I want a complete audit log of all detected and filtered secrets so that I can demonstrate SOC2/GDPR compliance.

### US-5: Retrospective Scanning
As a security administrator, I want to scan existing memories for secrets so that I can remediate historical data.

---

## Requirements

### P0 - Must Have

#### REQ-P0-001: Pattern-Based Secret Detection
**Description**: Detect secrets using regex patterns for known formats.
**Acceptance Criteria**:
- Detect OpenAI API keys (`sk-proj-*`, `sk-*`)
- Detect Anthropic API keys (`sk-ant-*`)
- Detect GitHub tokens (`ghp_*`, `gho_*`, `ghu_*`, `ghs_*`, `ghr_*`)
- Detect AWS credentials (`AKIA*` access keys)
- Detect private keys (RSA, DSA, EC, OpenSSH headers)
- Detect generic passwords in common formats
- Detect connection strings with embedded credentials
- Detection runs in <5ms for typical content

#### REQ-P0-002: Entropy-Based Detection
**Description**: Detect high-entropy strings that may be secrets.
**Acceptance Criteria**:
- Calculate Shannon entropy for candidate strings
- Use threshold 4.5 for base64-like strings
- Use threshold 3.0 for hex strings
- Configurable thresholds via environment variables
- Skip short strings (<16 characters)

#### REQ-P0-003: PII Detection
**Description**: Detect personally identifiable information.
**Acceptance Criteria**:
- Detect SSN patterns (XXX-XX-XXXX)
- Detect credit card numbers with Luhn validation
- Detect phone numbers (US formats)
- Configurable PII categories

#### REQ-P0-004: REDACT Strategy
**Description**: Replace detected secrets with redaction markers.
**Acceptance Criteria**:
- Replace secret with `[REDACTED:{type}]` marker
- Preserve surrounding context
- Include secret type in marker (e.g., `[REDACTED:api_key]`)

#### REQ-P0-005: MASK Strategy
**Description**: Partially mask secrets while preserving some visibility.
**Acceptance Criteria**:
- Show first 4 and last 4 characters
- Replace middle with asterisks
- Example: `sk-proj-****-****-abc123` → `sk-p****3`

#### REQ-P0-006: BLOCK Strategy
**Description**: Reject content containing secrets entirely.
**Acceptance Criteria**:
- Return error when secret detected
- Include helpful message about what was detected
- Do not store any part of the content

#### REQ-P0-007: WARN Strategy
**Description**: Allow content but emit warning.
**Acceptance Criteria**:
- Store content unchanged
- Emit warning to stderr
- Log to audit trail with warning status

#### REQ-P0-008: Default Configuration
**Description**: Sensible defaults for out-of-box security.
**Acceptance Criteria**:
- Default strategy: REDACT
- All pattern detectors enabled by default
- Entropy detection enabled by default
- PII detection enabled by default

#### REQ-P0-009: Audit Logging
**Description**: Log all secret detection events for compliance.
**Acceptance Criteria**:
- Log to JSON Lines format file
- Include: timestamp, namespace, detection type, action taken, hash of original
- Never log the actual secret content
- Configurable log location
- Log rotation support

#### REQ-P0-010: Hash-Based Allowlist
**Description**: Allow known-safe values to bypass filtering.
**Acceptance Criteria**:
- Store SHA-256 hash of allowed values (never plaintext)
- YAML configuration file for allowlist
- Per-namespace allowlist support
- CLI command to add/remove entries

#### REQ-P0-011: Integration with Capture Pipeline
**Description**: Filter content before embedding generation.
**Acceptance Criteria**:
- Filter summary field
- Filter content field
- Apply filtering before serialize_note()
- Apply filtering before embedding generation
- Preserve memory structure

#### REQ-P0-012: Retrospective Scanning Command
**Description**: Scan existing memories for secrets.
**Acceptance Criteria**:
- `/memory:scan-secrets` command
- Report mode (list findings without changes)
- Fix mode (apply configured strategy)
- Dry-run support
- Progress reporting

#### REQ-P0-013: Performance Requirements
**Description**: Filtering must not significantly impact capture latency.
**Acceptance Criteria**:
- <10ms added latency per capture operation
- Lazy loading of patterns
- Compiled regex caching

#### REQ-P0-014: File Content Handling
**Description**: Handle secrets in file references within memories.
**Acceptance Criteria**:
- Scan file content included in memories
- Apply same filtering strategies
- Preserve file references while redacting content

---

### P1 - Should Have

#### REQ-P1-001: Test Secret Command
**Description**: Test if a value would be detected as a secret.
**Acceptance Criteria**:
- `/memory:test-secret <value>` command
- Show detection type and strategy that would apply
- Useful for debugging false positives

#### REQ-P1-002: Audit Log Viewer
**Description**: View and query audit logs.
**Acceptance Criteria**:
- `/memory:audit-log [--since] [--namespace] [--type]` command
- Human-readable output
- JSON output option

#### REQ-P1-003: Per-Namespace Strategy
**Description**: Configure different strategies per namespace.
**Acceptance Criteria**:
- Configuration file with namespace overrides
- Environment variable overrides
- Example: decisions namespace uses BLOCK, progress uses REDACT

#### REQ-P1-004: Secret Detection Statistics
**Description**: Report on detection patterns and trends.
**Acceptance Criteria**:
- Include in `/memory:status` output
- Count by type, namespace, action
- Time-based trending

#### REQ-P1-005: Allowlist via CLI
**Description**: Manage allowlist via CLI commands.
**Acceptance Criteria**:
- `/memory:secrets-allowlist add <value>` command
- `/memory:secrets-allowlist remove <hash>` command
- `/memory:secrets-allowlist list` command

#### REQ-P1-006: Custom Pattern Support
**Description**: Add organization-specific patterns.
**Acceptance Criteria**:
- Configuration file for custom patterns
- Named patterns with descriptions
- Regex validation on load

---

### P2 - Nice to Have

#### REQ-P2-001: ML Extension Points
**Description**: Provide extension points for ML-based detection.
**Acceptance Criteria**:
- Abstract detector interface
- Plugin registration mechanism
- Async detection support for expensive operations

#### REQ-P2-002: Contextual Analysis Extension
**Description**: Extension points for context-aware detection.
**Acceptance Criteria**:
- Variable name analysis interface
- File type hints
- Surrounding code context

#### REQ-P2-003: Secret Rotation Alerts
**Description**: Alert when previously-seen secrets appear.
**Acceptance Criteria**:
- Hash-based secret tracking
- Alert when same secret seen multiple times
- Configurable alert threshold

#### REQ-P2-004: Compliance Report Generation
**Description**: Generate compliance reports for auditors.
**Acceptance Criteria**:
- SOC2 format report
- Date range selection
- PDF/HTML output

#### REQ-P2-005: Webhook Notifications
**Description**: Send alerts for critical detections.
**Acceptance Criteria**:
- Configurable webhook URL
- Payload includes detection metadata
- Retry logic

---

## Non-Functional Requirements

### NFR-001: Pure Python Implementation
No external dependencies beyond the Python standard library and existing project dependencies. Must work with Python 3.11+.

### NFR-002: Graceful Degradation
If filtering fails, capture should still succeed with warning. Never block legitimate memory capture due to filter errors.

### NFR-003: Thread Safety
All components must be thread-safe for concurrent capture operations.

### NFR-004: Testability
All detection patterns must have comprehensive test coverage. Minimum 90% code coverage for security module.

### NFR-005: Documentation
All secret patterns must be documented with examples and false positive guidance.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Pattern Coverage | >95% | Detected / Known secret types |
| False Positive Rate | <5% | False detections / Total detections |
| Performance Impact | <10ms | Added latency per capture |
| Test Coverage | >90% | Line coverage for security module |
| Audit Compliance | 100% | All detections logged |
