# Changelog

All notable changes to this specification will be documented in this file.

## [1.0.0] - 2025-12-26

### Added
- **REQUIREMENTS.md**: Complete Product Requirements Document
  - 10 P0 (must-have) requirements
  - 8 P1 (should-have) requirements
  - 5 P2 (nice-to-have) requirements
  - User stories for 5 core capabilities
  - Success metrics with measurable targets
  - Non-functional requirements (performance, security, reliability)

- **ARCHITECTURE.md**: Technical Architecture Design
  - System overview with ASCII architecture diagram
  - 7 component designs with Python code examples
  - Data models and database schema extensions
  - API design for SubconsciousnessService
  - Hook integration points
  - Security, performance, and deployment considerations

- **IMPLEMENTATION_PLAN.md**: 6-Phase Implementation Roadmap
  - Phase 1: LLM Foundation (15 tasks)
  - Phase 2: Implicit Capture (15 tasks)
  - Phase 3: Semantic Linking (12 tasks)
  - Phase 4: Memory Decay (12 tasks)
  - Phase 5: Consolidation (14 tasks)
  - Phase 6: Proactive Surfacing (17 tasks)
  - 85 total tasks with acceptance criteria
  - Verification gates per phase

- **DECISIONS.md**: 13 Architecture Decision Records
  - ADR-001: Provider-agnostic LLM client abstraction
  - ADR-002: Confidence-based auto-capture with review queue
  - ADR-003: Bidirectional memory links
  - ADR-004: Archive instead of delete for forgetting
  - ADR-005: Async LLM calls with non-blocking hooks
  - ADR-006: Typed relationship links with five core types
  - ADR-007: SQLite schema versioning with additive migrations
  - ADR-008: Decay score formula with weighted factors
  - ADR-009: Adversarial detection with pattern matching first
  - ADR-010: Proactive surfacing rate limiting
  - ADR-011: Meta-memory for consolidation results
  - ADR-012: Batch LLM requests for cost optimization
  - ADR-013: Local-first with optional cloud

### Research Foundation
- Incorporated CognitiveSubstrate research (Dual-Process Theory, SOAR/ACT-R)
- Validated against MemGPT/Letta, A-MEM, mem0 prior art
- Security analysis from RAG poisoning research

### Source Reference
- GitHub Issue: [#11 - feat: LLM-powered subconsciousness pattern](https://github.com/zircote/git-notes-memory/issues/11)

## [0.1.0] - 2025-12-25

### Added
- Initial project creation from GitHub Issue #11
- Project scaffold with README, CHANGELOG
- Requirements elicitation begun
