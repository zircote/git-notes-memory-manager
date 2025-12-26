# Changelog: Secrets Filtering

All notable changes to this project specification will be documented in this file.

## [Unreleased]

### Added
- Initial specification created from GitHub Issue #12
- REQUIREMENTS.md with 14 P0, 6 P1, 5 P2 requirements
- ARCHITECTURE.md with 7 components
- IMPLEMENTATION_PLAN.md with 5 phases, 31 tasks
- DECISIONS.md with 12 ADRs

### Decisions Made
- ADR-001: Pure Python implementation (no external dependencies)
- ADR-002: Default REDACT strategy
- ADR-003: Filter before embedding generation
- ADR-004: Entropy thresholds (4.5 base64, 3.0 hex)
- ADR-005: Hash-based allowlist storage
- ADR-006: Full audit logging for SOC2 compliance
- ADR-007: Include PII detection in v1
- ADR-008: Retrospective scanning with full remediation
- ADR-009: Defer ML-based detection (extension points provided)
- ADR-010: Defer contextual analysis
- ADR-011: Security module structure (security/ directory)
- ADR-012: Redact file content (don't skip files)

### Requirements Elicitation
- Confirmed detection layers: Pattern + Entropy (ML extension points for future)
- Confirmed default strategy: REDACT
- Confirmed retrospective scanning with full remediation
- Confirmed pure Python implementation
- Confirmed PII detection inclusion
- Confirmed full audit trail for compliance
- Confirmed CLI + config file for allowlist management
- Confirmed file content redaction (not skipping)
