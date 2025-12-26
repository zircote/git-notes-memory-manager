---
document_type: requirements
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T23:55:00Z
status: draft
github_issue: 11
---

# LLM-Powered Subconsciousness for Intelligent Memory Management

## Product Requirements Document

## Executive Summary

This document specifies the requirements for implementing an LLM-powered "subconsciousness" layer in the git-notes-memory system. The subconsciousness acts as an intelligent intermediary between raw memory storage and the consuming agent (Claude Code), providing automated memory capture, consolidation, intelligent forgetting, proactive surfacing, and semantic linking.

The design is grounded in cognitive science (Dual-Process Theory, SOAR/ACT-R architectures) and validated by industry prior art (MemGPT/Letta, A-MEM, mem0). The key differentiator is the integration of adversarial robustness and confidence scoring—features largely missing from existing memory systems.

**Key outcomes:**
1. **Implicit Capture**: Auto-detect memorable content from transcripts without explicit markers
2. **Memory Consolidation**: Merge related memories into higher-level abstractions
3. **Intelligent Forgetting**: Archive/forget stale memories based on access patterns and relevance
4. **Proactive Surfacing**: Surface relevant memories before they're explicitly requested
5. **Semantic Linking**: Create bidirectional relationships between related memories

## Problem Statement

### The Problem

Current memory management in git-notes-memory is **explicit and manual**:

- Users must explicitly capture memories with markers (`[decision]`, `[learned]`, `▶ progress`, etc.)
- Recall requires explicit search queries or context injection
- No automatic consolidation of related memories
- No intelligent forgetting of stale/redundant information
- No proactive surfacing of relevant memories
- Memory context injection is rule-based, not context-aware

### Impact

This results in five critical user pain points:

| Pain Point | Impact | Frequency |
|------------|--------|-----------|
| **Capture fatigue** | Important decisions go unrecorded because users forget markers | High |
| **Information overload** | Old, redundant memories accumulate without cleanup | Medium |
| **Missed connections** | Related memories are not linked, context is lost | High |
| **Stale context** | Outdated information persists indefinitely, polluting recall | Medium |
| **Reactive only** | System waits for queries instead of proactively helping | High |

### Current State

The existing hooks subsystem provides foundational capabilities:
- `SessionAnalyzer` already analyzes transcripts for signals
- `_auto_capture_signals()` captures high-confidence content
- `NoveltyChecker` prevents duplicate captures
- Vector search enables semantic retrieval

However, these are **heuristic-based** rather than LLM-powered, limiting their intelligence and adaptability.

## Goals and Success Criteria

### Primary Goal

Create a cognitive memory layer that autonomously manages the memory lifecycle—capture, enrich, link, surface, consolidate, and forget—reducing user burden while improving memory quality and relevance.

### Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Implicit capture acceptance rate | >70% | Percentage of auto-captured memories user accepts |
| Memory redundancy reduction | >30% | Duplicate/similar memories consolidated |
| Proactive surfacing usefulness | >50% | User rates surfaced memories as "useful" |
| Stale memory archival accuracy | >90% | Important memories not accidentally archived |
| Capture fatigue reduction | >60% | User satisfaction survey pre/post |

### Non-Goals (Explicit Exclusions)

- **Real-time LLM inference during capture**: All LLM calls are async/batched
- **Cloud dependency**: Local-only mode must function (degraded but operational)
- **Automatic memory deletion**: Forget = soft-delete/archive, not hard delete
- **Cross-repository memory sharing**: Memories scoped to single repo (future work)
- **Training/fine-tuning models**: Uses pre-trained models only

## User Analysis

### Primary Users

| User Type | Needs | Context |
|-----------|-------|---------|
| **Solo developer** | Reduce capture overhead, get relevant context automatically | Daily coding sessions |
| **Team developer** | Share learnings across sessions, maintain decision history | Collaborative projects |
| **Claude Code agent** | Accurate, relevant context for coding assistance | Every interaction |

### User Stories

#### Implicit Capture (Dream Harvesting)

1. As a **developer**, I want important decisions captured automatically so that I don't lose critical context when I forget to add markers.

2. As a **team member**, I want lessons learned from debugging sessions captured so that the team benefits from individual discoveries.

3. As a **Claude Code user**, I want session transcripts analyzed for memory-worthy content so that my interaction history becomes searchable knowledge.

#### Memory Consolidation (Sleep Cycle)

4. As a **developer**, I want related memories merged into abstractions so that I see patterns rather than scattered data points.

5. As a **long-term user**, I want duplicate memories consolidated so that recall isn't cluttered with redundant information.

#### Intelligent Forgetting (Memory Decay)

6. As a **developer**, I want stale, superseded decisions archived so that current context isn't polluted by outdated information.

7. As a **project maintainer**, I want completed project memories to decay gracefully so that active projects get priority.

#### Proactive Surfacing (Intuition)

8. As a **developer**, I want relevant memories surfaced when I open files so that I have context before I ask for it.

9. As a **debugger**, I want past blocker resolutions surfaced when similar errors occur so that I solve problems faster.

#### Semantic Linking (Association)

10. As a **developer**, I want related memories linked so that I can explore connections between decisions, learnings, and patterns.

11. As a **architect**, I want contradiction links flagged so that conflicting decisions are surfaced for resolution.

## Functional Requirements

### Must Have (P0)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-001 | LLM client abstraction supporting Anthropic Claude and OpenAI | Provider-agnostic design enables flexibility | Claude and OpenAI both work interchangeably |
| FR-002 | Implicit capture via LLM transcript analysis | Core value proposition: reduce capture burden | >70% of auto-captured memories accepted |
| FR-003 | Confidence scoring (0.0-1.0) for all LLM operations | Enables threshold-based decisions | All operations return confidence score |
| FR-004 | Confidence-threshold auto-capture (>0.9 auto, <0.9 review) | Balance automation with human oversight | High-confidence captured, low queued for review |
| FR-005 | Memory linking with typed relationships | Enable knowledge graph traversal | SUPPORTS, CONTRADICTS, SUPERSEDES, EXTENDS, REQUIRES |
| FR-006 | Decay scoring based on access patterns | Foundation for intelligent forgetting | Score incorporates recency, frequency, relevance |
| FR-007 | Index schema extensions for links and decay metadata | Database must support new data model | Schema migration works cleanly |
| FR-008 | Proactive surfacing in PostToolUse hook | Surface memories when files are opened | Relevant memories appear in context |
| FR-009 | Memory consolidation algorithm | Reduce redundancy via clustering | Related memories merged into meta-memories |
| FR-010 | Batch LLM processing to minimize API costs | Cost control for production usage | Single batch call processes multiple items |

### Should Have (P1)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-101 | `/memory:review` command for implicit capture approval | Human-in-the-loop for uncertain captures | UI shows pending captures with accept/reject |
| FR-102 | `/memory:graph <memory-id>` command | Visualize memory relationships | Outputs linked memories with relationship types |
| FR-103 | `/memory:decay --threshold=X` command | Inspect memories at risk of archival | Lists memories below threshold |
| FR-104 | `/memory:consolidate` command | Manual consolidation trigger | Runs consolidation cycle, shows merge proposals |
| FR-105 | `/memory:intuition` command | Force proactive surfacing | Shows relevant memories for current context |
| FR-106 | Local LLM support via Ollama | Offline capability | Works without internet connection |
| FR-107 | Adversarial content detection | Security for memory poisoning | Injection patterns blocked, warnings surfaced |
| FR-108 | Session-end LLM analysis in Stop hook | Enhanced implicit capture | Session transcript analyzed on stop |

### Nice to Have (P2)

| ID | Requirement | Rationale | Acceptance Criteria |
|----|-------------|-----------|---------------------|
| FR-201 | Memory graph visualization (ASCII or Mermaid) | Better understanding of connections | Graph rendered in terminal or markdown |
| FR-202 | Reinforcement learning from user feedback | Improve confidence calibration | Accepted/rejected feedback updates thresholds |
| FR-203 | Scheduled consolidation (cron-like) | Background optimization | Runs automatically on schedule |
| FR-204 | Cross-session memory context | Multi-session continuity | Memories from previous sessions surfaced |
| FR-205 | Embedding re-generation on model change | Handle model upgrades | Migration script regenerates embeddings |

## Non-Functional Requirements

### Performance

| Requirement | Target |
|-------------|--------|
| LLM call latency (async) | <5s for batch operations |
| Implicit capture overhead | <100ms added to Stop hook |
| Proactive surfacing latency | <50ms added to PostToolUse hook |
| Consolidation batch processing | <10s for 100 memories |
| Decay evaluation | <1s for 1000 memories |

### Security

| Requirement | Description |
|-------------|-------------|
| Adversarial detection | Block prompt injection patterns in memory content |
| API key management | Secure storage via environment variables |
| PII filtering | Configurable filter for sensitive content before LLM |
| Audit trail | Log all subconsciousness actions |
| Rate limiting | Prevent API cost overruns |

### Scalability

| Requirement | Target |
|-------------|--------|
| Memory corpus size | 10,000+ memories per repository |
| Concurrent operations | Thread-safe service layer |
| Batch processing | 100+ items per LLM call |

### Reliability

| Requirement | Description |
|-------------|-------------|
| Graceful degradation | All features work without LLM (reduced intelligence) |
| Offline mode | Core capture/recall functions work offline |
| Error recovery | Transient LLM failures don't block operations |
| Index consistency | Recovery from partial updates |

### Maintainability

| Requirement | Description |
|-------------|-------------|
| Type safety | Full mypy strict compliance |
| Test coverage | 80% minimum coverage |
| Documentation | Docstrings for all public APIs |
| Configuration | All thresholds configurable via environment |

## Technical Constraints

### Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| LLM Client (Primary) | Anthropic Claude API | Aligns with Claude Code ecosystem |
| LLM Client (Secondary) | OpenAI API | Broader adoption, fallback option |
| LLM Client (Local) | Ollama | Offline capability |
| Embedding Model | all-MiniLM-L6-v2 | Already used, proven performance |
| Database | SQLite + sqlite-vec | Already used, proven pattern |
| Python Version | 3.11+ | Project requirement |

### Integration Requirements

- Must integrate with existing `CaptureService`, `RecallService`, `IndexService`
- Must extend existing hooks subsystem (Stop, PostToolUse, SessionStart)
- Must follow frozen dataclass pattern for all models
- Must use `ServiceRegistry` singleton pattern

### Compatibility Requirements

- Backward compatible with existing memory format
- Schema migrations must be reversible
- Environment variable configuration pattern maintained

## Dependencies

### Internal Dependencies

| Dependency | Purpose |
|------------|---------|
| `git_notes_memory.capture` | Memory capture operations |
| `git_notes_memory.recall` | Memory retrieval operations |
| `git_notes_memory.index` | SQLite + vector search |
| `git_notes_memory.embedding` | Embedding generation |
| `git_notes_memory.hooks` | Hook handlers |

### External Dependencies

| Dependency | Version | Purpose | Optional |
|------------|---------|---------|----------|
| `anthropic` | >=0.18.0 | Claude API client | Yes (for Claude provider) |
| `openai` | >=1.0.0 | OpenAI API client | Yes (for OpenAI provider) |
| `ollama` | >=0.1.0 | Local LLM client | Yes (for local mode) |
| `networkx` | >=3.0 | Memory graph algorithms | Yes (for graph features) |

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| High LLM API costs | Medium | High | Batching, caching, token limits |
| Poor implicit capture accuracy | Medium | Medium | Confidence thresholds, human review |
| Memory poisoning attacks | Low | High | Adversarial detection, provenance tracking |
| Performance degradation | Low | Medium | Async processing, timeouts |
| Provider API changes | Low | Medium | Provider abstraction layer |
| Model hallucination | Medium | Medium | Confidence scoring, multi-signal validation |

## Open Questions

- [ ] **Q1**: What's the minimum confidence threshold for auto-capture in production?
  - Proposed: 0.9 for auto, 0.7-0.9 for review queue
- [ ] **Q2**: Should consolidation require user approval for merges?
  - Proposed: Show proposals, auto-merge only identical content
- [ ] **Q3**: What decay score triggers archival vs. deletion?
  - Proposed: <0.3 archived, never deleted (audit trail)
- [ ] **Q4**: How long should implicit capture candidates remain pending?
  - Proposed: 7 days, then auto-decline
- [ ] **Q5**: Should adversarial warnings block capture or just flag?
  - Proposed: Flag with confidence penalty, block only high-confidence threats

## Appendix

### Glossary

| Term | Definition |
|------|------------|
| Subconsciousness | The LLM-powered cognitive layer that manages memory autonomously |
| Implicit Capture | Auto-detection of memory-worthy content without explicit markers |
| Dream Harvesting | Analysis of session transcripts for implicit memories |
| Consolidation | Merging related memories into higher-level abstractions |
| Decay | Reduction in memory relevance score over time without access |
| Surfacing | Proactively presenting relevant memories to the user |
| Meta-memory | A synthesized memory created from a cluster of related memories |
| Memory Link | A typed bidirectional relationship between two memories |

### References

1. Kahneman, D. (2011). *Thinking, Fast and Slow* - Dual-Process Theory
2. Laird, J.E. (2022). "Analysis of ACT-R and Soar" - Cognitive architectures
3. Packer et al. (2023). "MemGPT: Towards LLMs as Operating Systems" - Memory management
4. Xu et al. (2025). "A-MEM: Agentic Memory for LLM Agents" - Zettelkasten patterns
5. Zhang et al. (2025). "Benchmarking Poisoning Attacks against RAG" - Security
6. GitHub Issue #11 - Feature specification

### Related Documents

- [ARCHITECTURE.md](./ARCHITECTURE.md) - Technical architecture
- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) - Phased implementation
- [DECISIONS.md](./DECISIONS.md) - Architecture Decision Records
- [CognitiveSubstrate/ARCHITECTURE_BRIEF.md](../../../research/CognitiveSubstrate/ARCHITECTURE_BRIEF.md) - Research foundation
