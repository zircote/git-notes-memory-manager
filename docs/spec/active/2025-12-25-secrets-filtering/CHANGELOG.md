# Changelog: Secrets Filtering

All notable changes to this project specification will be documented in this file.

## [Unreleased]

### Added
- Initial specification created from GitHub Issue #12
- REQUIREMENTS.md with 14 P0, 6 P1, 5 P2 requirements
- ARCHITECTURE.md with 6 components
- IMPLEMENTATION_PLAN.md with 5 phases, 30 tasks
- DECISIONS.md with 12 ADRs

### Changed
- **ADR-001 Revised**: Switched from pure Python to detect-secrets library
  - Yelp's detect-secrets provides 27+ battle-tested detectors
  - Entropy detection included (Base64/Hex high entropy)
  - Reduces implementation scope by ~70% for detection layer
  - Still pure Python (pip install), no binary dependencies
- **ADR-004 Superseded**: Entropy thresholds now managed by detect-secrets
- Architecture simplified: DetectSecretsAdapter replaces PatternDetector + EntropyAnalyzer
- Implementation plan reduced from 31 to 30 tasks with lower complexity

### Decisions Made
- ADR-001: Use detect-secrets library (revised from pure Python)
- ADR-002: Default REDACT strategy
- ADR-003: Filter before embedding generation
- ADR-004: Entropy thresholds (superseded - detect-secrets handles this)
- ADR-005: Hash-based allowlist storage
- ADR-006: Full audit logging for SOC2 compliance
- ADR-007: Include PII detection in v1
- ADR-008: Retrospective scanning with full remediation
- ADR-009: Defer ML-based detection (extension points provided)
- ADR-010: Defer contextual analysis
- ADR-011: Security module structure (security/ directory)
- ADR-012: Redact file content (don't skip files)

### Requirements Elicitation
- Confirmed detection layers: detect-secrets + custom PII (ML extension points for future)
- Confirmed default strategy: REDACT
- Confirmed retrospective scanning with full remediation
- Confirmed using detect-secrets library (user feedback)
- Confirmed PII detection inclusion
- Confirmed full audit trail for compliance
- Confirmed CLI + config file for allowlist management
- Confirmed file content redaction (not skipping)
