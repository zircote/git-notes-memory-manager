---
document_type: architecture
project_id: SPEC-2025-12-25-001
version: 1.0.0
last_updated: 2025-12-25T23:58:00Z
status: draft
---

# LLM-Powered Subconsciousness - Technical Architecture

## System Overview

The subconsciousness layer implements a cognitive architecture inspired by Dual-Process Theory (Kahneman) and cognitive architectures (SOAR, ACT-R). It operates as an intelligent intermediary between the memory store (git notes + SQLite index) and the consuming agent (Claude Code).

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CONSCIOUS LAYER (Claude Code Agent)              │
│                                                                     │
│  Receives: Synthesized context, confidence scores, proactive hints │
│  Sends: Capture requests, recall queries, user feedback            │
└─────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Clean, validated context
                              │
┌─────────────────────────────────────────────────────────────────────┐
│                    SUBCONSCIOUSNESS LAYER                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ IMPLICIT        │  │ PROACTIVE       │  │ CONSOLIDATION   │     │
│  │ CAPTURE AGENT   │  │ SURFACING AGENT │  │ AGENT           │     │
│  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤     │
│  │ • Transcript    │  │ • Context       │  │ • Clustering    │     │
│  │   analysis      │  │   analysis      │  │ • Merging       │     │
│  │ • Confidence    │  │ • Relevance     │  │ • Meta-memory   │     │
│  │   scoring       │  │   ranking       │  │   synthesis     │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ DECAY/FORGET    │  │ SEMANTIC        │  │ ADVERSARIAL     │     │
│  │ AGENT           │  │ LINKING AGENT   │  │ DETECTOR        │     │
│  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤     │
│  │ • Access track  │  │ • Relationship  │  │ • Injection     │     │
│  │ • Decay scoring │  │   discovery     │  │   detection     │     │
│  │ • Archive       │  │ • Bidirectional │  │ • Contradiction │     │
│  │   workflow      │  │   linking       │  │   flagging      │     │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘     │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                     LLM CLIENT ABSTRACTION                     │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │ │
│  │  │ Anthropic│  │  OpenAI  │  │  Ollama  │  │ Rate Limiter │   │ │
│  │  │ Provider │  │ Provider │  │ Provider │  │ + Batcher    │   │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              EXTENDED INDEX (sqlite-vec + metadata)            │ │
│  │  • Embeddings  • Links  • Decay scores  • Access patterns      │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ▲                                      │
└──────────────────────────────│──────────────────────────────────────┘
                               │
┌──────────────────────────────│──────────────────────────────────────┐
│                     git-notes-memory                                │
│                  (Persistent Storage Layer)                         │
│  • Git notes for sync  • Namespace organization  • Versioning       │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM calls | Async/batched | Don't block agent; minimize API costs |
| Provider abstraction | Interface-based | Swap providers without code changes |
| Confidence representation | Float (0.0-1.0) | Enables threshold-based decisions |
| Memory linking | Bidirectional graph | When A links to B, B knows about A |
| Forgetting | Archive, not delete | Preserve audit trail |
| Local fallback | Ollama | Offline capability |

## Component Design

### Component 1: LLM Client Abstraction

**Purpose**: Provide a provider-agnostic interface for LLM operations.

**Module**: `src/git_notes_memory/subconsciousness/llm_client.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM call."""
    content: str
    model: str
    usage: dict[str, int]  # tokens
    latency_ms: float

class LLMProvider(Protocol):
    """Protocol for LLM provider implementations."""

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send a completion request."""
        ...

    async def complete_batch(
        self,
        batch: list[list[dict[str, str]]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> list[LLMResponse]:
        """Send multiple completion requests (batched for efficiency)."""
        ...

class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""
    ...

class OpenAIProvider(LLMProvider):
    """OpenAI GPT API provider."""
    ...

class OllamaProvider(LLMProvider):
    """Local Ollama provider for offline mode."""
    ...

class LLMClient:
    """Unified LLM client with provider selection and rate limiting."""

    def __init__(
        self,
        primary_provider: str = "anthropic",
        fallback_provider: str | None = "ollama",
        rate_limit_rpm: int = 60,
    ):
        ...
```

**Responsibilities**:
- Provider selection and fallback
- Rate limiting and retry logic
- Request batching for cost optimization
- Timeout handling

**Interfaces**:
- `LLMProvider` protocol for implementations
- `LLMClient` as the unified entry point

**Dependencies**:
- `anthropic` (optional)
- `openai` (optional)
- `ollama` (optional)

**Technology**: Python async/await, Protocol for interface

### Component 2: Implicit Capture Agent

**Purpose**: Analyze session transcripts to identify memory-worthy content.

**Module**: `src/git_notes_memory/subconsciousness/implicit_capture.py`

```python
@dataclass(frozen=True)
class ImplicitMemory:
    """Memory candidate identified by subconsciousness."""
    namespace: str
    summary: str
    content: str
    confidence: float
    rationale: str
    source_hash: str  # Hash of source transcript for deduplication

class ImplicitCaptureAgent:
    """Analyzes transcripts to identify implicit memories."""

    def __init__(
        self,
        llm_client: LLMClient,
        min_confidence: float = 0.7,
        auto_capture_threshold: float = 0.9,
    ):
        ...

    async def analyze_transcript(
        self,
        transcript: str,
        existing_memories: list[Memory] | None = None,
    ) -> list[ImplicitMemory]:
        """
        Use LLM to identify memory-worthy content:
        - Decisions made (explicit or implicit)
        - Technical learnings or insights
        - Patterns or anti-patterns discovered
        - Blockers encountered and resolutions
        - Architectural or design choices
        """
        ...

    async def capture_approved(
        self,
        memories: list[ImplicitMemory],
    ) -> list[CaptureResult]:
        """Capture approved implicit memories."""
        ...
```

**Responsibilities**:
- Transcript parsing and chunking
- LLM-based content analysis
- Confidence scoring
- Deduplication against existing memories

**Interfaces**:
- Consumes `LLMClient`
- Produces `ImplicitMemory` candidates
- Integrates with `CaptureService`

### Component 3: Memory Consolidation Agent

**Purpose**: Cluster and merge related memories into abstractions.

**Module**: `src/git_notes_memory/subconsciousness/consolidation.py`

```python
@dataclass(frozen=True)
class ConsolidationProposal:
    """A proposed consolidation of related memories."""
    cluster: tuple[str, ...]  # Memory IDs
    proposed_summary: str
    proposed_content: str
    confidence: float
    rationale: str

class ConsolidationAgent:
    """Consolidates and abstracts memories during 'sleep cycles'."""

    def __init__(
        self,
        llm_client: LLMClient,
        index_service: IndexService,
        cluster_threshold: float = 0.85,
    ):
        ...

    async def find_clusters(
        self,
        memories: list[Memory],
    ) -> list[list[Memory]]:
        """Cluster semantically similar memories."""
        ...

    async def propose_consolidation(
        self,
        cluster: list[Memory],
    ) -> ConsolidationProposal | None:
        """Generate a consolidation proposal for a cluster."""
        ...

    async def execute_consolidation(
        self,
        proposal: ConsolidationProposal,
    ) -> Memory:
        """
        Execute a consolidation:
        1. Create meta-memory
        2. Link original memories to meta-memory
        3. Update decay scores (consolidated memories decay faster)
        """
        ...
```

**Responsibilities**:
- Vector-based clustering
- LLM-powered abstraction synthesis
- Link creation for merged memories
- Decay score updates

### Component 4: Decay and Forgetting Agent

**Purpose**: Track access patterns and manage memory lifecycle.

**Module**: `src/git_notes_memory/subconsciousness/forgetting.py`

```python
@dataclass(frozen=True)
class DecayMetadata:
    """Tracks memory access patterns for decay calculation."""
    memory_id: str
    created_at: datetime
    last_accessed_at: datetime
    access_count: int
    relevance_score: float
    superseded_by: str | None
    archived_at: datetime | None

@dataclass(frozen=True)
class DecayScore:
    """Calculated decay score with factors."""
    memory_id: str
    score: float  # 0.0 = forget, 1.0 = highly relevant
    factors: tuple[tuple[str, float], ...]  # (factor_name, contribution)

class ForgettingAgent:
    """Manages memory decay and archival."""

    def __init__(
        self,
        llm_client: LLMClient,
        index_service: IndexService,
        archive_threshold: float = 0.3,
    ):
        ...

    def track_access(self, memory_id: str) -> None:
        """Record a memory access (updates last_accessed and count)."""
        ...

    async def calculate_decay(
        self,
        memory: Memory,
        metadata: DecayMetadata,
    ) -> DecayScore:
        """
        Calculate decay score based on:
        - Days since last access (recency)
        - Total access count (frequency)
        - Project relevance (is project still active?)
        - Supersession (has this been overridden?)
        - Semantic uniqueness (is info available elsewhere?)
        """
        ...

    async def evaluate_batch(
        self,
        memories: list[Memory],
    ) -> list[DecayScore]:
        """Evaluate decay for multiple memories."""
        ...

    async def archive(self, memory_id: str) -> bool:
        """
        Archive a memory:
        - Set archived_at timestamp
        - Remove from active index
        - Preserve in git notes (never delete)
        """
        ...
```

**Responsibilities**:
- Access pattern tracking
- Decay score calculation
- Archive workflow
- Supersession handling

### Component 5: Proactive Surfacing Agent

**Purpose**: Surface relevant memories before explicit queries.

**Module**: `src/git_notes_memory/subconsciousness/surfacing.py`

```python
@dataclass(frozen=True)
class SurfacedMemory:
    """A proactively surfaced memory with relevance context."""
    memory: Memory
    relevance_score: float
    reason: str
    trigger: str  # What triggered surfacing (file, error, topic)

class ProactiveSurfacingAgent:
    """Surfaces memories before they are explicitly requested."""

    def __init__(
        self,
        llm_client: LLMClient,
        index_service: IndexService,
        intuition_threshold: float = 0.6,
    ):
        ...

    async def analyze_context(
        self,
        context: SessionContext,
    ) -> list[SurfacedMemory]:
        """
        Given current context, identify relevant memories:
        - File being edited has related decisions
        - Error message matches previous blocker
        - Discussion topic relates to past learnings
        - Code pattern matches known anti-patterns
        """
        ...

    async def rank_by_intuition(
        self,
        candidates: list[Memory],
        context: SessionContext,
    ) -> list[SurfacedMemory]:
        """
        LLM-powered ranking:
        - How likely to help right now?
        - How surprising/non-obvious is the connection?
        - How confident in this memory's accuracy?
        """
        ...
```

**Responsibilities**:
- Context analysis (files, errors, topics)
- Relevance scoring
- LLM-powered intuition ranking
- Integration with hooks

### Component 6: Semantic Linking Agent

**Purpose**: Create and manage relationships between memories.

**Module**: `src/git_notes_memory/subconsciousness/linking.py`

```python
class LinkType(Enum):
    """Types of semantic relationships between memories."""
    SUPPORTS = "supports"      # Memory A supports/validates B
    CONTRADICTS = "contradicts"  # Memory A conflicts with B
    SUPERSEDES = "supersedes"   # Memory A replaces B
    EXTENDS = "extends"        # Memory A adds detail to B
    REQUIRES = "requires"      # Memory A depends on B

@dataclass(frozen=True)
class MemoryLink:
    """Bidirectional link between memories."""
    id: str
    source_id: str
    target_id: str
    link_type: LinkType
    confidence: float
    created_by: str  # "user" | "subconsciousness"
    created_at: datetime

class SemanticLinkingAgent:
    """Creates associative links between memories."""

    def __init__(
        self,
        llm_client: LLMClient,
        index_service: IndexService,
    ):
        ...

    async def discover_links(
        self,
        memory: Memory,
        candidates: list[Memory] | None = None,
    ) -> list[MemoryLink]:
        """Find and type relationships between memories."""
        ...

    async def detect_contradictions(
        self,
        memory: Memory,
    ) -> list[MemoryLink]:
        """Specifically look for conflicting memories."""
        ...

    def traverse_graph(
        self,
        memory_id: str,
        depth: int = 2,
        link_types: list[LinkType] | None = None,
    ) -> list[Memory]:
        """Traverse the memory graph from a starting point."""
        ...
```

**Responsibilities**:
- Link discovery via LLM
- Contradiction detection
- Graph traversal
- Bidirectional link maintenance

### Component 7: Adversarial Detector

**Purpose**: Detect and flag potentially malicious memory content.

**Module**: `src/git_notes_memory/subconsciousness/adversarial.py`

```python
class ThreatType(Enum):
    """Types of adversarial threats."""
    PROMPT_INJECTION = "prompt_injection"
    AUTHORITY_CLAIM = "authority_claim"
    TEMPORAL_ANOMALY = "temporal_anomaly"
    CONTRADICTION = "contradiction"
    SOURCE_MISMATCH = "source_mismatch"

@dataclass(frozen=True)
class ThreatDetection:
    """Result of adversarial detection."""
    threat_type: ThreatType
    confidence: float
    evidence: str
    recommendation: str  # "block" | "flag" | "reduce_confidence"

class AdversarialDetector:
    """Detects adversarial content in memories."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
    ):
        # LLM optional - pattern matching works without
        ...

    def detect_injection(self, content: str) -> ThreatDetection | None:
        """Pattern match for prompt injection attempts."""
        ...

    def detect_authority_claims(self, content: str) -> ThreatDetection | None:
        """Detect "as system admin" type claims."""
        ...

    async def full_analysis(
        self,
        memory: Memory,
        existing_memories: list[Memory],
    ) -> list[ThreatDetection]:
        """Complete adversarial analysis including contradictions."""
        ...
```

**Responsibilities**:
- Pattern-based injection detection
- Authority claim detection
- Contradiction flagging
- Confidence adjustment

## Data Design

### Data Models

```python
# Extended models in src/git_notes_memory/subconsciousness/models.py

@dataclass(frozen=True)
class MemoryLink:
    """Bidirectional link between memories."""
    id: str
    source_id: str
    target_id: str
    link_type: str  # supports, contradicts, supersedes, extends, requires
    confidence: float
    created_by: str
    created_at: datetime

@dataclass(frozen=True)
class DecayMetadata:
    """Tracks memory access patterns for decay calculation."""
    memory_id: str
    created_at: datetime
    last_accessed_at: datetime
    access_count: int
    relevance_score: float
    superseded_by: str | None
    archived_at: datetime | None
    decay_score: float | None  # Computed periodically

@dataclass(frozen=True)
class ImplicitCapture:
    """Pending implicit capture for user review."""
    id: str
    namespace: str
    summary: str
    content: str
    confidence: float
    rationale: str
    source_hash: str
    created_at: datetime
    reviewed_at: datetime | None
    accepted: bool | None  # None = pending

@dataclass(frozen=True)
class SubconsciousnessConfig:
    """Configuration for subconsciousness features."""
    enabled: bool = False
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    implicit_capture_enabled: bool = True
    consolidation_enabled: bool = True
    forgetting_enabled: bool = True
    surfacing_enabled: bool = True
    linking_enabled: bool = True
    auto_capture_threshold: float = 0.9
    review_threshold: float = 0.7
    archive_threshold: float = 0.3
    surfacing_threshold: float = 0.6
```

### Data Flow

```
Capture Flow (System 2 - Deliberate):

Input Memory
    │
    ▼
┌─────────────────┐
│ Adversarial     │ ──▶ REJECT if injection detected
│ Pre-screen      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Enrichment      │ ──▶ Extract entities, topics, tags
│ Pipeline        │ ──▶ Compute initial confidence
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Contradiction   │ ──▶ Compare against existing memories
│ Check           │ ──▶ Flag conflicts, adjust confidence
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Relationship    │ ──▶ Link to related memories
│ Mapping         │ ──▶ Update graph structure
└────────┬────────┘
         │
         ▼
    Store in git-notes + index


Recall Flow (System 1 → System 2 escalation):

Query
    │
    ▼
┌─────────────────┐
│ Fast Semantic   │ ──▶ Embedding similarity search
│ Search (S1)     │ ──▶ Return top-k candidates
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Confidence      │ ──▶ │ If low/suspect: │
│ Assessment      │     │ Escalate to S2  │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │              ┌────────▼────────┐
         │              │ Deep Verify     │
         │              │ • Cross-check   │
         │              │ • Source review │
         │              │ • Warning gen   │
         │              └────────┬────────┘
         │                       │
         ▼◀──────────────────────┘
┌─────────────────┐
│ Context         │ ──▶ Synthesize natural language context
│ Synthesizer     │ ──▶ Include confidence + warnings
└────────┬────────┘
         │
         ▼
    Return to Conscious Agent
```

### Database Schema Extensions

```sql
-- Memory links table
CREATE TABLE IF NOT EXISTS memory_links (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    link_type TEXT NOT NULL,  -- supports, contradicts, supersedes, extends, requires
    confidence REAL NOT NULL,
    created_by TEXT NOT NULL,  -- "user" | "subconsciousness"
    created_at TEXT NOT NULL,
    UNIQUE(source_id, target_id, link_type),
    FOREIGN KEY (source_id) REFERENCES memories(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_links_source ON memory_links(source_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON memory_links(target_id);
CREATE INDEX IF NOT EXISTS idx_links_type ON memory_links(link_type);

-- Decay metadata table
CREATE TABLE IF NOT EXISTS memory_decay (
    memory_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    last_accessed_at TEXT NOT NULL,
    access_count INTEGER DEFAULT 0,
    relevance_score REAL DEFAULT 1.0,
    superseded_by TEXT,
    archived_at TEXT,
    decay_score REAL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_decay_score ON memory_decay(decay_score);
CREATE INDEX IF NOT EXISTS idx_decay_archived ON memory_decay(archived_at);

-- Implicit capture candidates (pending user review)
CREATE TABLE IF NOT EXISTS implicit_captures (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    summary TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL,
    rationale TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    accepted INTEGER  -- NULL=pending, 1=accepted, 0=rejected
);

CREATE INDEX IF NOT EXISTS idx_implicit_pending ON implicit_captures(accepted) WHERE accepted IS NULL;
CREATE INDEX IF NOT EXISTS idx_implicit_source ON implicit_captures(source_hash);
```

### Storage Strategy

- **Primary Store**: SQLite with sqlite-vec (existing)
- **Schema Version**: Increment to 3 with migration for new tables
- **Link Storage**: `memory_links` table with foreign keys
- **Decay Tracking**: `memory_decay` table updated on each access
- **Implicit Queue**: `implicit_captures` for pending review

## LLM Output Templates

**Critical Requirement**: All LLM-generated memories MUST conform to the existing memory format used by `note_parser.py`. The LLM output templates ensure compatibility with:
- YAML frontmatter parsing via `parse_note()`
- Progressive hydration levels (SUMMARY, FULL, FILES)
- Existing capture and recall pipelines

### Memory Output Schema

The LLM MUST output memories in this exact JSON schema, which is then serialized via `serialize_note()`:

```json
{
  "type": "object",
  "required": ["namespace", "summary", "content", "confidence"],
  "properties": {
    "namespace": {
      "type": "string",
      "enum": ["decisions", "learnings", "blockers", "progress", "patterns"]
    },
    "summary": {
      "type": "string",
      "maxLength": 100,
      "description": "One-line summary for SUMMARY hydration level"
    },
    "content": {
      "type": "string",
      "description": "Full markdown content for FULL hydration level"
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0
    },
    "rationale": {
      "type": "string",
      "description": "Why this content is memory-worthy"
    },
    "tags": {
      "type": "array",
      "items": {"type": "string"}
    },
    "relates_to": {
      "type": "array",
      "items": {"type": "string"},
      "description": "IDs of related memories"
    }
  }
}
```

### Serialized Memory Format

LLM output is converted to git note format via `serialize_note()`:

```yaml
---
type: decisions
timestamp: 2025-01-15T10:30:00Z
summary: Chose provider-agnostic LLM abstraction
spec: llm-subconsciousness
phase: implementation
tags:
  - architecture
  - llm
  - subconsciousness
status: active
relates_to: decisions:abc123:0, learnings:def456:1
---

## Context

During implementation of the subconsciousness layer, we needed to decide
how to abstract LLM providers...

## Decision

Implement a Protocol-based abstraction with AnthropicProvider, OpenAIProvider,
and OllamaProvider implementations...

## Consequences

- Positive: Provider flexibility
- Negative: Must maintain multiple implementations
```

### Progressive Hydration Levels

The LLM must understand and support progressive hydration:

| Level | Data Returned | LLM Responsibility |
|-------|---------------|---------------------|
| **SUMMARY** | `summary` field only (≤100 chars) | Generate concise, searchable summary |
| **FULL** | `summary` + full `content` | Generate complete markdown with ## sections |
| **FILES** | All above + file snapshots | Reference specific file paths with line numbers |

### Implicit Capture Prompt Template

```
You are analyzing a conversation transcript to identify memory-worthy content.

Extract any:
1. **Decisions** - Choices made with rationale (explicit or implicit)
2. **Learnings** - Technical insights, debugging discoveries, "TIL" moments
3. **Patterns** - Reusable approaches, best practices, anti-patterns
4. **Blockers** - Problems encountered and their resolutions
5. **Progress** - Significant milestones or completions

For each identified memory, output JSON matching the Memory Output Schema.

IMPORTANT:
- summary must be ≤100 characters and complete (no ellipsis)
- content should use markdown with ## sections
- confidence should reflect how certain you are this is memory-worthy
- Include specific file paths with line numbers when referencing code

Existing memories for deduplication:
{existing_memories}

Transcript to analyze:
{transcript}

Output format:
```json
{
  "memories": [
    {
      "namespace": "decisions",
      "summary": "...",
      "content": "...",
      "confidence": 0.85,
      "rationale": "...",
      "tags": ["..."]
    }
  ]
}
```
```

### Consolidation Prompt Template

```
You are synthesizing related memories into a higher-level abstraction.

Given these related memories:
{cluster_memories}

Create a meta-memory that:
1. Captures the essential pattern or theme
2. Preserves key details from each source
3. Uses SUMMARY level for quick recall
4. Links back to source memories

Output JSON matching the Memory Output Schema with:
- namespace: "patterns" (for meta-memories)
- relates_to: list of source memory IDs
- confidence: based on cluster coherence

The synthesized summary should be a generalization, not a concatenation.
```

### Surfacing Context Template

```
You are evaluating memories for proactive surfacing.

Current context:
- Files being accessed: {file_paths}
- Recent conversation topics: {topics}
- Current task: {task_description}

Candidate memories:
{candidate_memories}

For each candidate, score relevance (0.0-1.0) and provide a brief reason.

Output JSON:
```json
{
  "surfaced": [
    {
      "memory_id": "...",
      "relevance_score": 0.85,
      "reason": "This decision about X is directly relevant to the current file edit"
    }
  ]
}
```
```

### Template Loading

Templates are loaded from `src/git_notes_memory/subconsciousness/templates/`:

```
templates/
├── implicit_capture.txt
├── consolidation.txt
├── surfacing.txt
├── link_discovery.txt
├── decay_evaluation.txt
└── adversarial_check.txt
```

Templates support variable substitution via `{variable_name}` syntax.

## API Design

### Service API

```python
# Main subconsciousness service
class SubconsciousnessService:
    """Unified interface to all subconsciousness capabilities."""

    def __init__(
        self,
        config: SubconsciousnessConfig,
        llm_client: LLMClient | None = None,
        index_service: IndexService | None = None,
    ):
        ...

    # Implicit Capture
    async def analyze_transcript(self, transcript: str) -> list[ImplicitCapture]:
        """Analyze transcript for implicit memories."""
        ...

    async def get_pending_captures(self) -> list[ImplicitCapture]:
        """Get pending implicit captures for review."""
        ...

    async def approve_capture(self, capture_id: str) -> CaptureResult:
        """Approve and capture an implicit memory."""
        ...

    async def reject_capture(self, capture_id: str) -> bool:
        """Reject an implicit memory candidate."""
        ...

    # Consolidation
    async def consolidate(
        self,
        memories: list[Memory] | None = None,
        auto_execute: bool = False,
    ) -> list[ConsolidationProposal]:
        """Run consolidation cycle."""
        ...

    async def execute_consolidation(
        self,
        proposal_id: str,
    ) -> Memory:
        """Execute a consolidation proposal."""
        ...

    # Decay/Forgetting
    def track_access(self, memory_id: str) -> None:
        """Record a memory access."""
        ...

    async def evaluate_decay(
        self,
        threshold: float | None = None,
    ) -> list[DecayScore]:
        """Evaluate decay for all memories."""
        ...

    async def archive_memory(self, memory_id: str) -> bool:
        """Archive a decayed memory."""
        ...

    # Surfacing
    async def surface_relevant(
        self,
        context: SessionContext,
    ) -> list[SurfacedMemory]:
        """Proactively surface relevant memories."""
        ...

    # Linking
    async def discover_links(
        self,
        memory_id: str,
    ) -> list[MemoryLink]:
        """Discover links for a memory."""
        ...

    async def get_memory_graph(
        self,
        memory_id: str,
        depth: int = 2,
    ) -> list[Memory]:
        """Get linked memories via graph traversal."""
        ...

    # Adversarial
    async def check_content(
        self,
        content: str,
    ) -> list[ThreatDetection]:
        """Check content for adversarial patterns."""
        ...
```

### CLI Commands

```
/memory:review
  - List pending implicit captures
  - Accept/reject individual or batch
  - Filter by confidence, namespace

/memory:consolidate
  - Run consolidation cycle
  - Show merge proposals
  - Execute approved merges

/memory:graph <memory-id>
  - Display linked memories
  - Show relationship types
  - Traverse to depth N

/memory:decay [--threshold=X]
  - List memories below threshold
  - Show decay factors
  - Preview archive candidates

/memory:intuition
  - Force proactive surfacing
  - Show relevance scores
  - Explain why each surfaced
```

## Integration Points

### Hook Integration

**Stop Hook Enhancement** (`stop_handler.py`):
```python
# After existing transcript analysis
if config.subconsciousness_enabled:
    subconscious = get_subconsciousness_service()
    implicit = await subconscious.analyze_transcript(transcript)

    # Auto-capture high confidence
    for capture in implicit:
        if capture.confidence >= config.auto_capture_threshold:
            await subconscious.approve_capture(capture.id)
        else:
            # Queue for review
            pass
```

**PostToolUse Hook Enhancement** (`post_tool_use_handler.py`):
```python
# When file is read/edited
if config.subconsciousness_enabled and config.surfacing_enabled:
    subconscious = get_subconsciousness_service()
    context = SessionContext(
        files_accessed=[tool_result.file_path],
        # ... other context
    )
    surfaced = await subconscious.surface_relevant(context)
    if surfaced:
        # Add to additionalContext
        pass
```

**SessionStart Hook Enhancement** (`session_start_handler.py`):
```python
# Check for pending reviews
if config.subconsciousness_enabled:
    subconscious = get_subconsciousness_service()
    pending = await subconscious.get_pending_captures()
    if pending:
        # Add reminder to context
        pass
```

### Internal Integrations

| Component | Integration Type | Purpose |
|-----------|-----------------|---------|
| `CaptureService` | Method extension | Add implicit capture pathway |
| `RecallService` | Method extension | Track access for decay |
| `IndexService` | Schema extension | Add links and decay tables |
| `SessionAnalyzer` | Enhancement | LLM-powered analysis |

### External Integrations

| Service | Type | Purpose |
|---------|------|---------|
| Anthropic API | HTTP/SDK | Claude completions |
| OpenAI API | HTTP/SDK | GPT fallback |
| Ollama | Local | Offline mode |

## Security Design

### API Key Management

- Store in environment variables only
- Never log API keys
- Validate key presence at startup

### Adversarial Detection

| Pattern | Detection Method | Action |
|---------|-----------------|--------|
| Prompt injection | Regex + LLM | Block capture |
| Authority claims | Regex | Flag, reduce confidence |
| Temporal anomalies | Timestamp analysis | Flag for review |
| Contradictions | Vector similarity + LLM | Create CONTRADICTS link |

### Data Protection

- No PII in LLM prompts (configurable filter)
- Rate limiting to prevent abuse
- Audit log for all subconsciousness actions

## Performance Considerations

### Expected Load

| Operation | Frequency | Expected Load |
|-----------|-----------|---------------|
| Implicit capture | Per session end | 1-5 per session |
| Proactive surfacing | Per file access | 10-50 per session |
| Consolidation | Daily/weekly | 1 per cycle |
| Decay evaluation | Weekly | 1 per cycle |

### Performance Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| LLM latency (async) | <5s | User doesn't wait |
| Surfacing overhead | <50ms | Don't slow hooks |
| Consolidation batch | <10s/100 memories | Background task |
| Decay evaluation | <1s/1000 memories | Weekly is fine |

### Optimization Strategies

1. **Batch LLM calls**: Combine multiple analysis requests
2. **Cache embeddings**: Don't regenerate unless content changes
3. **Lazy linking**: Discover links on-demand, not at capture
4. **Async processing**: All LLM calls are non-blocking
5. **Confidence shortcuts**: Skip LLM for low-signal content

## Testing Strategy

### Unit Testing

- Mock LLM responses for deterministic tests
- Test each agent in isolation
- 80% coverage target

### Integration Testing

- Test with real SQLite database
- Test hook integrations
- Test schema migrations

### End-to-End Testing

- Test full capture → consolidate → surface flow
- Test with real (or simulated) transcripts
- Performance benchmarks

## Deployment Considerations

### Environment Requirements

```bash
# Required for any LLM provider
MEMORY_SUBCONSCIOUSNESS_ENABLED=true

# Provider configuration (one of)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Or for local mode
MEMORY_LLM_PROVIDER=ollama
MEMORY_LLM_MODEL=llama3.2

# Feature toggles
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
```

### Configuration Management

- All settings via environment variables
- Sensible defaults for all thresholds
- Feature flags for gradual rollout

### Rollback Plan

- Feature flags allow instant disable
- Schema migrations are additive only
- No data deleted, only archived
