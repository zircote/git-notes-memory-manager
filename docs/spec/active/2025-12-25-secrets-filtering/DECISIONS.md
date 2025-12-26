# Architecture Decision Records: Secrets Filtering

This document contains all Architecture Decision Records (ADRs) for the Secrets Filtering and Sensitive Data Protection feature.

---

## ADR-001: Pure Python Implementation

**Status**: Accepted
**Date**: 2025-12-25

### Context
We need to decide whether to use external dependencies for secrets detection or implement everything in pure Python.

### Options Considered
1. **Pure Python**: Implement using only stdlib and existing dependencies
2. **detect-secrets**: Use Yelp's detect-secrets library
3. **truffleHog**: Use truffleHog for git-based scanning
4. **gitleaks**: Use gitleaks binary

### Decision
Use **pure Python** implementation with no additional dependencies.

### Rationale
- Reduces supply chain attack surface
- No binary dependencies to manage
- Simpler deployment (pip install only)
- Full control over detection patterns
- Existing patterns are well-documented

### Consequences
- More initial implementation work
- Must maintain patterns ourselves
- May miss some edge cases that mature tools catch

---

## ADR-002: Default REDACT Strategy

**Status**: Accepted
**Date**: 2025-12-25

### Context
We need a default filtering strategy that balances security and usability.

### Options Considered
1. **REDACT**: Replace secrets with markers
2. **BLOCK**: Reject content entirely
3. **WARN**: Allow but log warning
4. **MASK**: Partial visibility

### Decision
Default to **REDACT** strategy.

### Rationale
- Preserves memory context while removing secrets
- Non-disruptive to user workflow
- Clear markers indicate filtering occurred
- Users can configure stricter if needed

### Consequences
- Some information loss (secret type visible, not value)
- Requires clear documentation about markers
- Per-namespace overrides needed for sensitive namespaces

---

## ADR-003: Filter Before Embedding Generation

**Status**: Accepted
**Date**: 2025-12-25

### Context
Where in the capture pipeline should filtering occur?

### Options Considered
1. **Before validation**: Earliest possible
2. **After validation, before serialize**: Before git storage
3. **After serialize, before embed**: Before vector generation
4. **After embed, before index**: Latest possible

### Decision
Filter **after validation, before serialize_note()**.

### Rationale
- Filtered content is stored in git (permanent record)
- Filtered content is embedded (search won't surface secrets)
- Validation ensures content is valid before filtering
- Single point of filtering (DRY)

### Consequences
- Validation sees original content (may fail on secrets)
- Git notes contain redacted content
- Search indexes redacted content
- Hook-based pre-capture could filter earlier if needed

---

## ADR-004: Entropy Thresholds

**Status**: Accepted
**Date**: 2025-12-25

### Context
What entropy thresholds balance detection rate vs false positives?

### Research
- Random base64: ~5.17 bits per character
- Random hex: ~4.0 bits per character
- English text: ~1.5-2.0 bits per character
- Code: ~2.5-4.0 bits per character
- UUIDs: ~3.8 bits per character

### Decision
- **Base64 threshold**: 4.5
- **Hex threshold**: 3.0
- **Minimum length**: 16 characters

### Rationale
- 4.5 catches most base64 secrets (API keys typically >5.0)
- 3.0 catches hex secrets while avoiding short hashes
- 16 chars minimum avoids short UUIDs and common hashes
- Thresholds configurable via environment variables

### Consequences
- Some high-entropy code may false positive (mitigated by allowlist)
- Very short secrets may evade detection
- Encoded secrets (base64 of secret) may evade

---

## ADR-005: Hash-Based Allowlist

**Status**: Accepted
**Date**: 2025-12-25

### Context
How should we store allowlisted values?

### Options Considered
1. **Plaintext**: Store actual values in config
2. **Encrypted**: Encrypt values with user key
3. **Hash-based**: Store SHA-256 hashes only

### Decision
Use **SHA-256 hashes** for allowlist storage.

### Rationale
- Never stores plaintext secrets in config files
- Hash comparison is fast (O(1) lookup)
- Hashes can be safely shared/versioned
- Matches security best practices

### Consequences
- Cannot list actual values (only hashes)
- Requires exact match (no fuzzy matching)
- User must remember what values they allowlisted
- Reason field helps document purpose

---

## ADR-006: Full Audit Logging

**Status**: Accepted
**Date**: 2025-12-25

### Context
What level of audit logging is needed for compliance?

### Options Considered
1. **Minimal**: Just counts
2. **Summary**: Counts + types
3. **Full**: Every detection with metadata
4. **Verbose**: Full + original content hash

### Decision
Use **full audit logging** with content hashes.

### Rationale
- SOC2 requires demonstrable controls
- GDPR requires data processing records
- Hash of original enables forensics without storing secrets
- JSON Lines format enables log aggregation

### Consequences
- More disk usage (rotation needed)
- Performance overhead (async logging recommended)
- Log files contain sensitive metadata (access control needed)

---

## ADR-007: Include PII Detection in v1

**Status**: Accepted
**Date**: 2025-12-25

### Context
Should PII detection (SSN, credit cards, phones) be in v1 or deferred?

### Options Considered
1. **Include**: Ship with PII detection
2. **Defer**: Focus on technical secrets first
3. **Optional**: Ship disabled by default

### Decision
**Include** PII detection in v1, enabled by default.

### Rationale
- GDPR/CCPA compliance requires PII protection
- Same filtering pipeline can handle PII
- Credit card detection with Luhn is low false-positive
- SSN pattern is specific enough
- User requested inclusion

### Consequences
- Additional patterns to maintain
- Phone number detection may have false positives
- Need configurable PII categories

---

## ADR-008: Retrospective Scanning with Remediation

**Status**: Accepted
**Date**: 2025-12-25

### Context
How should we handle secrets in existing memories?

### Options Considered
1. **Report only**: Just list findings
2. **Delete**: Remove affected memories
3. **Remediate**: Rewrite with redaction
4. **Quarantine**: Move to separate namespace

### Decision
Support **remediation** via `/memory:scan-secrets --fix`.

### Rationale
- Preserves memory structure and context
- Applies same redaction as capture-time
- Maintains audit trail of changes
- Git notes history tracks original (for admins)
- User explicitly requested full remediation

### Consequences
- Git history contains original secrets
- Need to communicate this to users
- May need git history rewriting for truly sensitive data (out of scope)

---

## ADR-009: Defer ML-Based Detection

**Status**: Accepted
**Date**: 2025-12-25

### Context
Should v1 include ML-based secret detection?

### Options Considered
1. **Include**: Use transformer-based model
2. **Defer**: Provide extension points only
3. **Skip**: Not needed

### Decision
**Defer** ML detection, provide extension points.

### Rationale
- Pattern + entropy covers >95% of cases
- ML adds significant complexity and dependencies
- Model inference has performance implications
- Extension points allow future addition
- User confirmed deferral

### Consequences
- May miss novel secret formats
- Extension interface must be well-designed
- Documentation should explain limitation

---

## ADR-010: Defer Contextual Analysis

**Status**: Accepted
**Date**: 2025-12-25

### Context
Should v1 analyze variable names and file context?

### Options Considered
1. **Include**: Check variable names like `password = `
2. **Defer**: Focus on content patterns
3. **Skip**: Too complex

### Decision
**Defer** contextual analysis.

### Rationale
- Content patterns are more reliable
- Variable name analysis requires parsing
- File type hints need heuristics
- Adds complexity without proportional benefit
- Can be added in v2 if needed

### Consequences
- May miss secrets assigned to obviously-named variables
- `password = "weak"` won't trigger without pattern match
- Extension points should support context in future

---

## ADR-011: Security Module Structure

**Status**: Accepted
**Date**: 2025-12-25

### Context
How should the security module be organized?

### Options Considered
1. **Single file**: All in security.py
2. **Module directory**: security/ with submodules
3. **Separate package**: git_notes_memory_security

### Decision
Use **module directory** structure: `security/`

### Rationale
- Follows existing patterns (hooks/, commands/)
- Each component in separate file (SRP)
- Single __init__.py for public exports
- Lazy loading to avoid import overhead
- Keeps related code together

### Consequences
- More files to navigate
- Need clear public/private boundaries
- __init__.py manages exports

---

## ADR-012: Redact File Content, Don't Skip Files

**Status**: Accepted
**Date**: 2025-12-25

### Context
When memories reference files with secrets, what should we do?

### Options Considered
1. **Skip file**: Don't include file content
2. **Redact content**: Apply filtering to file content
3. **Reference only**: Include path, not content

### Decision
**Redact content** - apply same filtering to file content.

### Rationale
- Consistent behavior across all content
- Preserves file context and structure
- Users expect filtering to work uniformly
- Skip/reference-only loses valuable information

### Consequences
- File content must be passed through filter
- Redaction markers appear in file content
- Performance overhead for large files

---

## Decision Log

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| ADR-001 | Pure Python Implementation | Accepted | 2025-12-25 |
| ADR-002 | Default REDACT Strategy | Accepted | 2025-12-25 |
| ADR-003 | Filter Before Embedding Generation | Accepted | 2025-12-25 |
| ADR-004 | Entropy Thresholds | Accepted | 2025-12-25 |
| ADR-005 | Hash-Based Allowlist | Accepted | 2025-12-25 |
| ADR-006 | Full Audit Logging | Accepted | 2025-12-25 |
| ADR-007 | Include PII Detection in v1 | Accepted | 2025-12-25 |
| ADR-008 | Retrospective Scanning with Remediation | Accepted | 2025-12-25 |
| ADR-009 | Defer ML-Based Detection | Accepted | 2025-12-25 |
| ADR-010 | Defer Contextual Analysis | Accepted | 2025-12-25 |
| ADR-011 | Security Module Structure | Accepted | 2025-12-25 |
| ADR-012 | Redact File Content | Accepted | 2025-12-25 |
