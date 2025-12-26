---
document_type: implementation_plan
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-26T00:05:00Z
status: draft
---

# LLM-Powered Subconsciousness - Implementation Plan

## Overview

This document defines the phased implementation of the LLM-powered subconsciousness layer. The implementation follows a bottom-up approach, building foundational infrastructure first, then layering cognitive capabilities on top.

**Total Phases**: 6
**Estimated Tasks**: 85
**Priority**: All phases required for appreciable value (user-confirmed)

## Phase Summary

| Phase | Name | Tasks | Dependencies | Focus |
|-------|------|-------|--------------|-------|
| 1 | LLM Foundation | 15 | None | Provider abstraction, rate limiting, batching |
| 2 | Implicit Capture | 15 | Phase 1 | Dream harvesting, confidence scoring |
| 3 | Semantic Linking | 12 | Phase 1 | Memory graph, relationship discovery |
| 4 | Memory Decay | 12 | Phase 3 | Access tracking, intelligent forgetting |
| 5 | Consolidation | 14 | Phases 3, 4 | Clustering, meta-memory synthesis |
| 6 | Proactive Surfacing | 17 | Phases 3, 4, 5 | Context analysis, intuition ranking |

## Phase 1: LLM Foundation

**Goal**: Build provider-agnostic LLM client with rate limiting and batching.

**Prerequisites**: None

**Deliverables**:
- `src/git_notes_memory/subconsciousness/llm_client.py`
- `src/git_notes_memory/subconsciousness/providers/`
- Unit tests with mocked LLM responses

### Tasks

#### 1.1 Create subconsciousness module structure
- [ ] Create `src/git_notes_memory/subconsciousness/__init__.py`
- [ ] Create `src/git_notes_memory/subconsciousness/models.py` for shared models
- [ ] Create `src/git_notes_memory/subconsciousness/config.py` for configuration
- [ ] Create `src/git_notes_memory/subconsciousness/providers/__init__.py`

**Acceptance Criteria**:
- Module imports cleanly
- Configuration loads from environment
- mypy passes with strict mode

#### 1.2 Implement LLM response models
- [ ] Define `LLMResponse` frozen dataclass (content, model, usage, latency_ms)
- [ ] Define `LLMError` exceptions with retry hints
- [ ] Define `LLMConfig` for provider-specific settings
- [ ] Add comprehensive docstrings

**Acceptance Criteria**:
- All models frozen and immutable
- JSON serialization works
- Type annotations complete

#### 1.3 Implement LLMProvider protocol
- [ ] Define `LLMProvider` Protocol class
- [ ] Add `complete()` async method signature
- [ ] Add `complete_batch()` async method signature
- [ ] Document expected behavior and error handling

**Acceptance Criteria**:
- Protocol is runtime-checkable
- Supports async/await pattern
- Clear interface documentation

#### 1.4 Implement Anthropic provider
- [ ] Create `src/git_notes_memory/subconsciousness/providers/anthropic.py`
- [ ] Implement `AnthropicProvider(LLMProvider)`
- [ ] Handle API key from environment
- [ ] Implement retry with exponential backoff
- [ ] Support JSON mode via tool_use pattern

**Acceptance Criteria**:
- Works with `anthropic` SDK
- Graceful degradation if SDK not installed
- Proper error messages for missing API key

#### 1.5 Implement OpenAI provider
- [ ] Create `src/git_notes_memory/subconsciousness/providers/openai.py`
- [ ] Implement `OpenAIProvider(LLMProvider)`
- [ ] Handle API key from environment
- [ ] Implement retry with exponential backoff
- [ ] Support JSON mode natively

**Acceptance Criteria**:
- Works with `openai` SDK
- Graceful degradation if SDK not installed
- Proper error messages for missing API key

#### 1.6 Implement Ollama provider
- [ ] Create `src/git_notes_memory/subconsciousness/providers/ollama.py`
- [ ] Implement `OllamaProvider(LLMProvider)`
- [ ] Support local model selection
- [ ] Handle connection errors gracefully
- [ ] Implement basic JSON parsing (no native JSON mode)

**Acceptance Criteria**:
- Works without network access
- Detects when Ollama not running
- Clear setup instructions in errors

#### 1.7 Implement rate limiter
- [ ] Create rate limiter with configurable RPM
- [ ] Support per-provider limits
- [ ] Implement token bucket algorithm
- [ ] Add async-compatible locking

**Acceptance Criteria**:
- Prevents API rate limit errors
- Works correctly with concurrent requests
- Configurable via environment

#### 1.8 Implement request batcher
- [ ] Create batcher for combining multiple requests
- [ ] Implement timeout-based flush
- [ ] Implement size-based flush
- [ ] Handle partial batch failures

**Acceptance Criteria**:
- Reduces API call count
- Maintains request order
- Graceful handling of failures

#### 1.9 Implement LLMClient unified interface
- [ ] Create `LLMClient` class
- [ ] Implement provider selection logic
- [ ] Implement fallback chain (primary → fallback)
- [ ] Integrate rate limiter and batcher
- [ ] Add comprehensive logging

**Acceptance Criteria**:
- Single entry point for all LLM calls
- Transparent provider switching
- Configurable via environment

#### 1.10 Implement timeout and cancellation
- [ ] Add configurable timeout per request
- [ ] Support request cancellation
- [ ] Handle timeout gracefully
- [ ] Report timeout in metrics

**Acceptance Criteria**:
- Requests don't hang indefinitely
- Cancelled requests clean up properly
- Timeout configurable

#### 1.11 Add usage tracking
- [ ] Track tokens per request
- [ ] Track cost per provider
- [ ] Implement daily/session limits
- [ ] Add warning thresholds

**Acceptance Criteria**:
- Usage visible in logs
- Warnings before limits hit
- Cost estimation accurate

#### 1.12 Write unit tests for providers
- [ ] Test Anthropic provider with mocked SDK
- [ ] Test OpenAI provider with mocked SDK
- [ ] Test Ollama provider with mocked HTTP
- [ ] Test fallback scenarios

**Acceptance Criteria**:
- 90% coverage for providers
- All error paths tested
- Mock responses realistic

#### 1.13 Write unit tests for LLMClient
- [ ] Test provider selection
- [ ] Test rate limiting
- [ ] Test batching
- [ ] Test fallback chain

**Acceptance Criteria**:
- 90% coverage for client
- Concurrent scenarios tested
- Edge cases covered

#### 1.14 Write integration tests
- [ ] Test with real Anthropic API (optional, CI-skip)
- [ ] Test with real OpenAI API (optional, CI-skip)
- [ ] Test with local Ollama (optional)

**Acceptance Criteria**:
- Tests pass with real APIs
- Marked as slow/optional
- Clear skip conditions

#### 1.15 Documentation and examples
- [ ] Document environment variables
- [ ] Add usage examples
- [ ] Document error handling
- [ ] Add troubleshooting guide

**Acceptance Criteria**:
- All config documented
- Examples copy-pasteable
- Common issues addressed

---

## Phase 2: Implicit Capture (Dream Harvesting)

**Goal**: LLM-powered transcript analysis to identify memory-worthy content.

**Prerequisites**: Phase 1 (LLM Foundation)

**Deliverables**:
- `src/git_notes_memory/subconsciousness/implicit_capture.py`
- `src/git_notes_memory/subconsciousness/adversarial.py`
- Schema extension for `implicit_captures` table
- `/memory:review` command

### Tasks

#### 2.1 Define implicit capture models
- [ ] Create `ImplicitMemory` frozen dataclass
- [ ] Create `ImplicitCapture` frozen dataclass (with review status)
- [ ] Create `CaptureConfidence` with factor breakdown
- [ ] Add source hash for deduplication

**Acceptance Criteria**:
- Models immutable
- Confidence 0.0-1.0 normalized
- Source hash deterministic

#### 2.2 Implement schema migration
- [ ] Increment SCHEMA_VERSION to 3
- [ ] Add `implicit_captures` table
- [ ] Add indexes for pending review query
- [ ] Write migration test

**Acceptance Criteria**:
- Migration idempotent
- Rollback works
- Indexes optimize queries

#### 2.3 Implement transcript chunking
- [ ] Split transcripts by turn boundary
- [ ] Handle large transcripts (>100k tokens)
- [ ] Preserve context across chunks
- [ ] Mark chunk boundaries

**Acceptance Criteria**:
- No information loss
- Chunk size configurable
- Context preserved

#### 2.4 Implement LLM analysis prompts
- [ ] Design extraction prompt for decisions
- [ ] Design extraction prompt for learnings
- [ ] Design extraction prompt for patterns
- [ ] Design extraction prompt for blockers
- [ ] Implement JSON schema for responses

**Acceptance Criteria**:
- Prompts tested with multiple models
- JSON output parseable
- Clear instructions for confidence

#### 2.5 Implement ImplicitCaptureAgent
- [ ] Create agent class with LLM client
- [ ] Implement `analyze_transcript()` method
- [ ] Implement confidence scoring
- [ ] Implement deduplication against existing memories

**Acceptance Criteria**:
- Returns ordered by confidence
- Deduplication works
- Rationale included

#### 2.6 Implement adversarial detection (basic)
- [ ] Create `AdversarialDetector` class
- [ ] Implement regex patterns for prompt injection
- [ ] Implement authority claim detection
- [ ] Return `ThreatDetection` results

**Acceptance Criteria**:
- Common patterns caught
- False positive rate <5%
- Fast (regex-based)

#### 2.7 Integrate adversarial screening
- [ ] Screen captures before queuing
- [ ] Reduce confidence for flagged content
- [ ] Block high-confidence threats
- [ ] Log all detections

**Acceptance Criteria**:
- Threats blocked or flagged
- Audit trail complete
- Non-blocking for clean content

#### 2.8 Implement capture queue storage
- [ ] Add repository methods for implicit_captures
- [ ] Implement `queue_for_review()`
- [ ] Implement `get_pending()`
- [ ] Implement `update_review_status()`

**Acceptance Criteria**:
- CRUD operations work
- Pending query efficient
- Status transitions correct

#### 2.9 Implement auto-capture logic
- [ ] Add threshold configuration
- [ ] Auto-approve above threshold
- [ ] Queue for review below threshold
- [ ] Expire old pending captures

**Acceptance Criteria**:
- Thresholds configurable
- Auto-capture works
- Expiration runs

#### 2.10 Integrate with Stop hook
- [ ] Add subconsciousness analysis call
- [ ] Handle async completion
- [ ] Add timeout protection
- [ ] Report captures in summary

**Acceptance Criteria**:
- Analysis runs at session end
- Doesn't block exit
- Summary shows captures

#### 2.11 Implement /memory:review command
- [ ] List pending captures with confidence
- [ ] Accept/reject individual
- [ ] Batch accept above threshold
- [ ] Show rationale

**Acceptance Criteria**:
- Command works in Claude Code
- Clear UI for decisions
- Batch operations work

#### 2.12 Write unit tests
- [ ] Test transcript analysis with mocked LLM
- [ ] Test confidence scoring
- [ ] Test deduplication
- [ ] Test adversarial detection

**Acceptance Criteria**:
- 80% coverage
- Mock responses cover variety
- Edge cases tested

#### 2.13 Write integration tests
- [ ] Test full capture → queue → review flow
- [ ] Test schema migration
- [ ] Test hook integration

**Acceptance Criteria**:
- End-to-end flow works
- Database state correct
- Hook triggers properly

#### 2.14 Write adversarial test suite
- [ ] Test known injection patterns
- [ ] Test authority claim patterns
- [ ] Test false positive scenarios
- [ ] Document coverage

**Acceptance Criteria**:
- Known attacks caught
- Clean content passes
- Coverage documented

#### 2.15 Documentation
- [ ] Document configuration
- [ ] Document prompt engineering
- [ ] Add review workflow guide
- [ ] Add troubleshooting

**Acceptance Criteria**:
- All config documented
- Prompts explained
- Workflow clear

---

## Phase 3: Semantic Linking

**Goal**: Create bidirectional relationships between memories.

**Prerequisites**: Phase 1 (LLM Foundation)

**Deliverables**:
- `src/git_notes_memory/subconsciousness/linking.py`
- Schema extension for `memory_links` table
- `/memory:graph` command

### Tasks

#### 3.1 Define linking models
- [ ] Create `LinkType` enum (SUPPORTS, CONTRADICTS, SUPERSEDES, EXTENDS, REQUIRES)
- [ ] Create `MemoryLink` frozen dataclass
- [ ] Create `LinkDiscoveryResult` with confidence

**Acceptance Criteria**:
- Types cover relationship space
- Links immutable
- Confidence normalized

#### 3.2 Implement schema migration
- [ ] Add `memory_links` table
- [ ] Add foreign key constraints
- [ ] Add indexes for traversal
- [ ] Add unique constraint on (source, target, type)

**Acceptance Criteria**:
- Migration idempotent
- Constraints work
- Indexes optimize traversal

#### 3.3 Implement link repository
- [ ] Add CRUD for memory_links
- [ ] Implement `get_links_for_memory()`
- [ ] Implement `get_linked_memories()`
- [ ] Implement bidirectional query

**Acceptance Criteria**:
- Bidirectional works
- Efficient queries
- Cascade delete works

#### 3.4 Implement LLM relationship discovery
- [ ] Design prompt for relationship detection
- [ ] Implement `discover_links()` method
- [ ] Parse LLM output to links
- [ ] Handle multi-target relationships

**Acceptance Criteria**:
- Prompt produces valid links
- Multiple relationships detected
- Confidence calibrated

#### 3.5 Implement SemanticLinkingAgent
- [ ] Create agent class
- [ ] Implement on-capture linking
- [ ] Implement batch discovery
- [ ] Implement contradiction detection

**Acceptance Criteria**:
- Links created on capture
- Batch mode efficient
- Contradictions flagged

#### 3.6 Implement graph traversal
- [ ] Implement BFS traversal
- [ ] Add depth limiting
- [ ] Add link type filtering
- [ ] Return ordered by relevance

**Acceptance Criteria**:
- Traversal correct
- Depth works
- Filtering works

#### 3.7 Integrate with capture flow
- [ ] Discover links on new capture
- [ ] Add links to existing memories
- [ ] Update reverse links
- [ ] Log link creation

**Acceptance Criteria**:
- Links created automatically
- Reverse links maintained
- Audit trail exists

#### 3.8 Implement /memory:graph command
- [ ] Show linked memories
- [ ] Display relationship types
- [ ] Support depth parameter
- [ ] Format for terminal

**Acceptance Criteria**:
- Command works
- Output readable
- Depth configurable

#### 3.9 Implement graph visualization (optional)
- [ ] Generate Mermaid diagram
- [ ] Generate ASCII art fallback
- [ ] Color by link type
- [ ] Handle large graphs

**Acceptance Criteria**:
- Diagrams render
- Fallback works
- Large graphs handled

#### 3.10 Write unit tests
- [ ] Test link creation
- [ ] Test traversal
- [ ] Test relationship detection
- [ ] Test contradiction detection

**Acceptance Criteria**:
- 80% coverage
- All link types tested
- Edge cases covered

#### 3.11 Write integration tests
- [ ] Test capture → link flow
- [ ] Test schema migration
- [ ] Test graph command

**Acceptance Criteria**:
- End-to-end works
- Migration works
- Command works

#### 3.12 Documentation
- [ ] Document link types
- [ ] Document discovery prompts
- [ ] Add usage examples
- [ ] Document graph command

**Acceptance Criteria**:
- Types explained
- Examples work
- Command documented

---

## Phase 4: Memory Decay and Forgetting

**Goal**: Track access patterns and archive stale memories.

**Prerequisites**: Phase 3 (Semantic Linking) for supersession handling

**Deliverables**:
- `src/git_notes_memory/subconsciousness/forgetting.py`
- Schema extension for `memory_decay` table
- `/memory:decay` command

### Tasks

#### 4.1 Define decay models
- [ ] Create `DecayMetadata` frozen dataclass
- [ ] Create `DecayScore` with factor breakdown
- [ ] Create `DecayFactor` enum

**Acceptance Criteria**:
- Models immutable
- Score 0.0-1.0 normalized
- Factors enumerated

#### 4.2 Implement schema migration
- [ ] Add `memory_decay` table
- [ ] Add foreign key to memories
- [ ] Add indexes for score queries
- [ ] Initialize decay records for existing memories

**Acceptance Criteria**:
- Migration idempotent
- Existing memories tracked
- Indexes work

#### 4.3 Implement access tracking
- [ ] Update last_accessed_at on recall
- [ ] Increment access_count
- [ ] Track access source (search, link, surfaced)
- [ ] Handle concurrent updates

**Acceptance Criteria**:
- Every access tracked
- Thread-safe
- Source captured

#### 4.4 Integrate tracking with RecallService
- [ ] Add tracking call to search()
- [ ] Add tracking call to get_memory()
- [ ] Add tracking to graph traversal
- [ ] Make tracking non-blocking

**Acceptance Criteria**:
- All access paths tracked
- No performance impact
- Non-blocking

#### 4.5 Implement decay calculation
- [ ] Implement recency factor (days since access)
- [ ] Implement frequency factor (access count)
- [ ] Implement relevance factor (project active?)
- [ ] Implement supersession factor (SUPERSEDES links)
- [ ] Combine factors with weights

**Acceptance Criteria**:
- Formula documented
- Weights configurable
- Score reasonable

#### 4.6 Implement ForgettingAgent
- [ ] Create agent class
- [ ] Implement `calculate_decay()` for single memory
- [ ] Implement `evaluate_batch()` for all memories
- [ ] Implement scheduling (weekly by default)

**Acceptance Criteria**:
- Batch efficient
- Scheduling works
- Configurable

#### 4.7 Implement archive workflow
- [ ] Set archived_at timestamp
- [ ] Remove from active index (keep in SQLite)
- [ ] Preserve in git notes
- [ ] Update linked memories

**Acceptance Criteria**:
- Archive reversible
- Git notes preserved
- Links updated

#### 4.8 Implement /memory:decay command
- [ ] List memories below threshold
- [ ] Show decay factors
- [ ] Preview archive candidates
- [ ] Confirm before archive

**Acceptance Criteria**:
- Command works
- Factors visible
- Confirmation required

#### 4.9 Write unit tests
- [ ] Test decay calculation
- [ ] Test access tracking
- [ ] Test archive workflow
- [ ] Test factor weights

**Acceptance Criteria**:
- 80% coverage
- Formula tested
- Edge cases covered

#### 4.10 Write integration tests
- [ ] Test recall → track → decay flow
- [ ] Test archive workflow
- [ ] Test supersession handling

**Acceptance Criteria**:
- Flow works
- Archive works
- Supersession works

#### 4.11 Write scheduled job tests
- [ ] Test batch evaluation
- [ ] Test scheduling
- [ ] Test concurrent execution

**Acceptance Criteria**:
- Batch works
- Schedule fires
- No race conditions

#### 4.12 Documentation
- [ ] Document decay formula
- [ ] Document archive vs delete
- [ ] Add tuning guide
- [ ] Document command

**Acceptance Criteria**:
- Formula explained
- Difference clear
- Tuning possible

---

## Phase 5: Memory Consolidation

**Goal**: Cluster and merge related memories into abstractions.

**Prerequisites**: Phases 3 (Linking), 4 (Decay) for relationship and decay awareness

**Deliverables**:
- `src/git_notes_memory/subconsciousness/consolidation.py`
- `/memory:consolidate` command

### Tasks

#### 5.1 Define consolidation models
- [ ] Create `ConsolidationProposal` frozen dataclass
- [ ] Create `ConsolidationResult` for executed merges
- [ ] Create `ClusterMetadata` for cluster analysis

**Acceptance Criteria**:
- Models immutable
- Proposals reviewable
- Results traceable

#### 5.2 Implement clustering algorithm
- [ ] Use embedding similarity for initial clusters
- [ ] Apply agglomerative clustering
- [ ] Set minimum cluster size (2)
- [ ] Set maximum cluster size (10)

**Acceptance Criteria**:
- Clusters make sense
- Size limits enforced
- Fast for 1000 memories

#### 5.3 Implement LLM abstraction synthesis
- [ ] Design prompt for meta-memory generation
- [ ] Generate unified summary
- [ ] Generate synthesized content
- [ ] Preserve key details from originals

**Acceptance Criteria**:
- Abstractions useful
- Key details preserved
- Readable output

#### 5.4 Implement ConsolidationAgent
- [ ] Create agent class
- [ ] Implement `find_clusters()`
- [ ] Implement `propose_consolidation()`
- [ ] Implement `execute_consolidation()`

**Acceptance Criteria**:
- Full workflow works
- Proposals generated
- Execution atomic

#### 5.5 Implement meta-memory creation
- [ ] Create new memory in "meta" namespace
- [ ] Link to source memories with CONSOLIDATES type
- [ ] Update source decay (accelerate)
- [ ] Preserve provenance

**Acceptance Criteria**:
- Meta-memory created
- Links correct
- Provenance clear

#### 5.6 Implement proposal storage
- [ ] Store pending proposals
- [ ] Support approval/rejection
- [ ] Track execution status
- [ ] Expire old proposals

**Acceptance Criteria**:
- Proposals persist
- Status tracks
- Expiration works

#### 5.7 Implement /memory:consolidate command
- [ ] Run consolidation cycle
- [ ] Show proposals with clusters
- [ ] Accept/reject proposals
- [ ] Show execution results

**Acceptance Criteria**:
- Command works
- Proposals readable
- Execution confirmed

#### 5.8 Implement auto-consolidation
- [ ] Schedule weekly cycle
- [ ] Auto-execute high-confidence (>0.95)
- [ ] Queue others for review
- [ ] Report results

**Acceptance Criteria**:
- Schedule works
- Auto-execute works
- Queue works

#### 5.9 Write unit tests
- [ ] Test clustering algorithm
- [ ] Test abstraction synthesis
- [ ] Test meta-memory creation
- [ ] Test link management

**Acceptance Criteria**:
- 80% coverage
- Algorithm tested
- Edge cases covered

#### 5.10 Write integration tests
- [ ] Test full consolidation flow
- [ ] Test with real clusters
- [ ] Test proposal workflow

**Acceptance Criteria**:
- Flow works
- Clusters reasonable
- Workflow works

#### 5.11 Write performance tests
- [ ] Test with 1000 memories
- [ ] Test cluster detection time
- [ ] Test LLM batch efficiency

**Acceptance Criteria**:
- <10s for 100 memories
- Batching efficient
- No timeouts

#### 5.12 Write quality tests
- [ ] Test abstraction quality
- [ ] Test information preservation
- [ ] Test readability

**Acceptance Criteria**:
- Abstractions useful
- No info loss
- Human-readable

#### 5.13 Implement safety guards
- [ ] Require minimum cluster size
- [ ] Limit daily auto-consolidations
- [ ] Preserve original memories (archived, not deleted)
- [ ] Audit log all operations

**Acceptance Criteria**:
- Guards work
- Limits enforced
- Audit complete

#### 5.14 Documentation
- [ ] Document clustering algorithm
- [ ] Document abstraction prompts
- [ ] Add tuning guide
- [ ] Document command

**Acceptance Criteria**:
- Algorithm explained
- Prompts documented
- Tuning possible

---

## Phase 6: Proactive Surfacing (Intuition)

**Goal**: Surface relevant memories before explicit queries.

**Prerequisites**: Phases 3-5 for full context (links, decay, consolidation)

**Deliverables**:
- `src/git_notes_memory/subconsciousness/surfacing.py`
- Enhanced PostToolUse hook
- `/memory:intuition` command

### Tasks

#### 6.1 Define surfacing models
- [ ] Create `SurfacedMemory` frozen dataclass
- [ ] Create `SurfacingContext` for trigger information
- [ ] Create `SurfacingResult` for batch results

**Acceptance Criteria**:
- Models immutable
- Triggers captured
- Results traceable

#### 6.2 Implement context extraction
- [ ] Extract from file paths
- [ ] Extract from file content (read)
- [ ] Extract from error messages
- [ ] Extract from conversation history

**Acceptance Criteria**:
- Multiple sources
- Context rich
- Extraction fast

#### 6.3 Implement vector-based candidate retrieval
- [ ] Generate embedding from context
- [ ] Find top-k similar memories
- [ ] Apply decay filter (exclude archived)
- [ ] Apply recency boost

**Acceptance Criteria**:
- Candidates relevant
- Archived excluded
- Recency considered

#### 6.4 Implement LLM intuition ranking
- [ ] Design ranking prompt
- [ ] Score candidates for current relevance
- [ ] Generate explanation for each
- [ ] Return top-n with reasons

**Acceptance Criteria**:
- Ranking improves relevance
- Explanations useful
- Top-n limited

#### 6.5 Implement ProactiveSurfacingAgent
- [ ] Create agent class
- [ ] Implement `analyze_context()`
- [ ] Implement `rank_by_intuition()`
- [ ] Implement caching for repeat contexts

**Acceptance Criteria**:
- Full workflow works
- Ranking works
- Caching efficient

#### 6.6 Integrate with PostToolUse hook
- [ ] Trigger on file read/edit
- [ ] Extract context from tool result
- [ ] Surface relevant memories
- [ ] Format for additionalContext

**Acceptance Criteria**:
- Hook triggers
- Context extracted
- Output formatted

#### 6.7 Implement surfacing triggers
- [ ] File access trigger
- [ ] Error message trigger
- [ ] Topic mention trigger
- [ ] Pattern match trigger

**Acceptance Criteria**:
- Multiple triggers
- Configurable
- Fast detection

#### 6.8 Implement rate limiting for surfacing
- [ ] Limit surfaces per session
- [ ] Limit surfaces per file
- [ ] Prevent surfacing same memory twice
- [ ] Cooldown between surfaces

**Acceptance Criteria**:
- Limits work
- No spam
- Cooldown enforced

#### 6.9 Implement /memory:intuition command
- [ ] Force proactive surfacing
- [ ] Show relevance scores
- [ ] Explain connections
- [ ] Support context override

**Acceptance Criteria**:
- Command works
- Scores visible
- Explanations clear

#### 6.10 Implement feedback loop
- [ ] Track when surfaced memories are accessed
- [ ] Track when surfaced memories are dismissed
- [ ] Adjust confidence based on feedback
- [ ] Learn trigger effectiveness

**Acceptance Criteria**:
- Feedback captured
- Adjustments made
- Learning works

#### 6.11 Write unit tests
- [ ] Test context extraction
- [ ] Test candidate retrieval
- [ ] Test intuition ranking
- [ ] Test trigger detection

**Acceptance Criteria**:
- 80% coverage
- Extraction tested
- Ranking tested

#### 6.12 Write integration tests
- [ ] Test hook integration
- [ ] Test full surfacing flow
- [ ] Test rate limiting

**Acceptance Criteria**:
- Hook works
- Flow works
- Limits work

#### 6.13 Write performance tests
- [ ] Test surfacing latency (<50ms target)
- [ ] Test with large memory corpus
- [ ] Test caching effectiveness

**Acceptance Criteria**:
- <50ms overhead
- Scales to 10k memories
- Caching helps

#### 6.14 Write quality tests
- [ ] Test relevance of surfaced memories
- [ ] Test explanation quality
- [ ] Test trigger accuracy

**Acceptance Criteria**:
- Surfacing useful
- Explanations helpful
- Triggers accurate

#### 6.15 Implement confidence display
- [ ] Show confidence scores
- [ ] Show contributing factors
- [ ] Show source triggers
- [ ] Visual confidence indicator

**Acceptance Criteria**:
- Confidence visible
- Factors shown
- Clear visualization

#### 6.16 Implement user preferences
- [ ] Allow surfacing disable per namespace
- [ ] Allow threshold adjustment
- [ ] Allow trigger selection
- [ ] Persist preferences

**Acceptance Criteria**:
- Preferences work
- Persistence works
- UI for settings

#### 6.17 Documentation
- [ ] Document triggers
- [ ] Document ranking algorithm
- [ ] Add tuning guide
- [ ] Document command

**Acceptance Criteria**:
- Triggers documented
- Algorithm explained
- Tuning possible

---

## Cross-Cutting Concerns

### Configuration

All phases require consistent configuration management:

```bash
# Master switch
MEMORY_SUBCONSCIOUSNESS_ENABLED=true

# Provider selection
MEMORY_LLM_PROVIDER=anthropic  # anthropic, openai, ollama
MEMORY_LLM_MODEL=claude-sonnet-4-20250514

# Feature toggles (all default true when subconsciousness enabled)
MEMORY_IMPLICIT_CAPTURE_ENABLED=true
MEMORY_CONSOLIDATION_ENABLED=true
MEMORY_FORGETTING_ENABLED=true
MEMORY_SURFACING_ENABLED=true
MEMORY_LINKING_ENABLED=true

# Thresholds
MEMORY_AUTO_CAPTURE_THRESHOLD=0.9
MEMORY_REVIEW_THRESHOLD=0.7
MEMORY_ARCHIVE_THRESHOLD=0.3
MEMORY_SURFACING_THRESHOLD=0.6
MEMORY_CONSOLIDATION_THRESHOLD=0.85
```

### Testing Strategy

| Type | Coverage Target | Scope |
|------|-----------------|-------|
| Unit | 80% | Individual functions and classes |
| Integration | Key flows | Cross-component interactions |
| Performance | Critical paths | Latency and throughput |
| Quality | Subjective | LLM output usefulness |

### Documentation Requirements

Each phase must include:
- Configuration documentation
- API documentation (docstrings)
- Usage examples
- Troubleshooting guide

### Migration Strategy

- Schema migrations are additive only
- Migrations must be idempotent
- Rollback scripts for each migration
- Data preservation (no deletes)

---

## Verification Gates

### Phase 1 Completion
- [ ] All providers implemented and tested
- [ ] Rate limiting verified under load
- [ ] Batching reduces API calls by >50%
- [ ] Fallback chain works

### Phase 2 Completion
- [ ] Implicit capture accuracy >70%
- [ ] Adversarial detection blocks known patterns
- [ ] Auto-capture threshold calibrated
- [ ] /memory:review command functional

### Phase 3 Completion
- [ ] Links discovered with >60% accuracy
- [ ] Contradictions detected
- [ ] Graph traversal works to depth 3
- [ ] /memory:graph command functional

### Phase 4 Completion
- [ ] Access tracking complete
- [ ] Decay formula calibrated
- [ ] Archive workflow preserves data
- [ ] /memory:decay command functional

### Phase 5 Completion
- [ ] Clustering groups related memories
- [ ] Abstractions preserve key information
- [ ] Auto-consolidation safe (no data loss)
- [ ] /memory:consolidate command functional

### Phase 6 Completion
- [ ] Surfacing latency <50ms
- [ ] Surfaced memories >50% useful
- [ ] Rate limiting prevents spam
- [ ] /memory:intuition command functional

---

## Risk Register

| Risk | Phase | Mitigation |
|------|-------|------------|
| LLM API costs | 1 | Batching, caching, rate limiting |
| Poor implicit capture accuracy | 2 | Confidence thresholds, human review |
| Link quality issues | 3 | LLM-based validation, user feedback |
| Decay formula too aggressive | 4 | Conservative defaults, easy tuning |
| Consolidation loses information | 5 | Preserve originals, preview first |
| Surfacing spam | 6 | Rate limiting, cooldowns |

---

## Related Documents

- [REQUIREMENTS.md](./REQUIREMENTS.md) - Product Requirements Document
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Technical Architecture
- [DECISIONS.md](./DECISIONS.md) - Architecture Decision Records
