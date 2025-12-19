# Memory Lifecycle Guide

This document provides a comprehensive reference for the complete lifecycle of memories in the git-notes-memory system. It covers every stage from creation through storage, indexing, retrieval, and eventual archival or deletion.

## Overview

The git-notes-memory system provides a git-native, semantically-searchable memory storage solution. Memories flow through the following lifecycle stages:

1. **Creation** - Memories are triggered via inline markers, commands, or automatic hook detection
2. **Validation** - Input is validated for namespace, summary length, and content size
3. **Serialization** - Content is formatted as YAML front matter with markdown body
4. **Storage** - Memories are appended to git notes under namespaced refs
5. **Indexing** - Embeddings are generated and stored in SQLite with sqlite-vec
6. **Retrieval** - Memories are recalled via semantic search, text search, or direct ID lookup
7. **Hydration** - Retrieved memories can be progressively loaded with additional context
8. **Lifecycle Management** - Memories transition through active, resolved, archived, and tombstone states

The system integrates with Claude Code via hooks that enable automatic capture detection, context injection, and session-end analysis.

---

## 1. Memory Creation

### 1.1 Trigger Mechanisms

Memories can be created through four primary mechanisms:

#### Inline Markers

Users can embed capture markers directly in their prompts using the `[remember]` or `[remember:namespace]` syntax:

```
[remember:decisions] Use PostgreSQL instead of SQLite for better concurrent writes
```

The marker is parsed by `NamespaceParser` which extracts:
- Marker type (explicit `[remember:namespace]` or generic `[remember]`)
- Explicit namespace (if provided)
- Content following the marker

#### /capture Command

The `/capture` command provides explicit memory capture with full control:

```
/capture --namespace=decisions --summary="Use PostgreSQL" --tags=database,architecture
```

Command parameters:
- `namespace` (required): Target memory namespace
- `summary` (required): One-line description (max 100 characters)
- `content`: Full markdown body
- `tags`: Comma-separated categorization tags
- `spec`: Specification identifier for grouping
- `phase`: Lifecycle phase (planning, implementation, review, etc.)

#### Auto-capture via Hooks

When enabled, the `UserPromptSubmit` hook automatically detects memorable content in user prompts. The detection pipeline:

1. **Signal Detection**: Scans text for capture signal patterns
2. **Novelty Checking**: Compares against existing memories to avoid duplicates
3. **Capture Decision**: Determines action based on confidence thresholds
4. **Auto-capture or Suggestion**: High-confidence signals capture automatically; medium-confidence signals generate suggestions

#### Namespace-Aware Markers

The inline marker syntax supports explicit namespace targeting:

| Marker | Behavior |
|--------|----------|
| `[remember]` | Auto-detects namespace from content using signal detection |
| `[remember:decisions]` | Forces capture to `decisions` namespace |
| `[remember:learnings]` | Forces capture to `learnings` namespace |
| `[remember:blockers]` | Forces capture to `blockers` namespace |

### 1.2 Signal Detection

The `SignalDetector` class identifies memorable content using pre-compiled regex patterns. Each signal type has associated patterns with base confidence scores.

#### SignalType Enumeration

| SignalType | Description | Suggested Namespace |
|------------|-------------|---------------------|
| `DECISION` | User made a decision | `decisions` |
| `LEARNING` | User learned something | `learnings` |
| `BLOCKER` | User encountered an obstacle | `blockers` |
| `RESOLUTION` | User resolved an issue | `solutions` |
| `PREFERENCE` | User expressed a preference | `preferences` |
| `EXPLICIT` | User explicitly requested capture | `notes` |

#### Pattern Definitions

**DECISION Patterns** (maps to `decisions` namespace):

| Pattern | Base Confidence |
|---------|-----------------|
| `\b(I\|we)\s+(decided\|chose\|selected\|picked\|opted)\s+(to\|for\|on)\b` | 0.90 |
| `\bthe decision (is\|was) (to\|that)\b` | 0.88 |
| `\bwe('ll\| will)\s+go with\b` | 0.85 |
| `\bafter (considering\|evaluating\|weighing),?\s+(I\|we)\b` | 0.85 |
| `\b(I\|we) went with\b` | 0.80 |
| `\bfinal(ly)? (choosing\|decided\|settled on)\b` | 0.82 |
| `\bmade the call to\b` | 0.80 |

**LEARNING Patterns** (maps to `learnings` namespace):

| Pattern | Base Confidence |
|---------|-----------------|
| `\b(I\|we)\s+(learned\|realized\|discovered\|found out)\s+(that\|about)?\b` | 0.90 |
| `\bTIL\b` | 0.95 |
| `\bturns out\b` | 0.85 |
| `\bkey (insight\|takeaway\|learning)[:\s]` | 0.92 |
| `\binteresting(ly)?[,:]?\s+` | 0.70 |
| `\bI (didn't\|never) (know\|realize)\b` | 0.80 |
| `\bnow I (know\|understand)\b` | 0.82 |
| `\baha moment\b` | 0.88 |

**BLOCKER Patterns** (maps to `blockers` namespace):

| Pattern | Base Confidence |
|---------|-----------------|
| `\bblocked (by\|on)\b` | 0.92 |
| `\bstuck (on\|with)\b` | 0.88 |
| `\bcan('t\| not)\s+.{1,30}\s+because\b` | 0.85 |
| `\b(this\|that) (is )?blocking\b` | 0.90 |
| `\bissue (with\|is)[:\s]` | 0.75 |
| `\bproblem[:\s]` | 0.70 |
| `\b(I'm\|we're) (having trouble\|struggling) with\b` | 0.80 |
| `\bcan't (figure out\|get\|make)\b` | 0.78 |

**RESOLUTION Patterns** (maps to `solutions` namespace):

| Pattern | Base Confidence |
|---------|-----------------|
| `\b(fixed\|resolved\|solved) (the\|this\|that\|it)\b` | 0.92 |
| `\bworkaround[:\s]` | 0.88 |
| `\bsolution[:\s]` | 0.85 |
| `\bfigured (it )?out\b` | 0.88 |
| `\bthat (worked\|fixed it)\b` | 0.85 |
| `\bgot it (working\|to work)\b` | 0.82 |
| `\bthe (fix\|solution) (was\|is)\b` | 0.85 |
| `\bfinally got\b` | 0.75 |

**PREFERENCE Patterns** (maps to `preferences` namespace):

| Pattern | Base Confidence |
|---------|-----------------|
| `\bI (always )?(prefer\|like) to\b` | 0.88 |
| `\bmy preference is\b` | 0.90 |
| `\bI('d\| would) (rather\|prefer)\b` | 0.88 |
| `\bI (don't )?like (when\|how\|it when)\b` | 0.75 |
| `\bI want (to\|it to)\b` | 0.70 |
| `\bI (need\|require)\b` | 0.68 |

**EXPLICIT Patterns** (maps to `notes` namespace):

| Pattern | Base Confidence |
|---------|-----------------|
| `\bremember (this\|that)\b` | 0.98 |
| `\bsave (this\|that)( (for\|as))?\b` | 0.95 |
| `\bnote (that\|this)[:\s]?` | 0.92 |
| `\bfor (future\|later) reference\b` | 0.90 |
| `\bdon't forget\b` | 0.88 |
| `\bkeep (this )?in mind\b` | 0.85 |
| `\bimportant[:\s]` | 0.75 |

#### Confidence Scoring

The detector adjusts the base confidence based on contextual factors:

```python
def score_confidence(base_confidence, match, context):
    confidence = base_confidence

    # Match length adjustment
    if len(match) > 20:
        confidence = min(1.0, confidence + 0.02)  # Longer = more confident
    elif len(match) < 5:
        confidence = max(0.0, confidence - 0.05)  # Very short = less confident

    # Context quality adjustment
    if context.endswith((".", "!", "?")):
        confidence = min(1.0, confidence + 0.02)  # Complete sentences
    if len(context) < 20:
        confidence = max(0.0, confidence - 0.05)  # Short context = noise

    # Reinforcing words boost
    reinforcers = ["important", "critical", "key", "essential", "must", "need"]
    if any(r in context.lower() for r in reinforcers):
        confidence = min(1.0, confidence + 0.05)

    return round(confidence, 3)
```

#### Context Extraction

For each detected signal, the detector extracts surrounding context within a configurable window (default: 100 characters on each side):

```python
# Extract context around match position
context_start = max(0, match_start - context_window)
context_end = min(len(text), match_end + context_window)

# Align to word boundaries
# Add ellipsis if truncated
```

The resulting `CaptureSignal` contains:
- `type`: SignalType enum value
- `match`: Exact matched text
- `confidence`: Adjusted confidence score (0.0-1.0)
- `context`: Surrounding context (100 chars each side)
- `suggested_namespace`: Inferred namespace from signal type
- `position`: Character position in source text

### 1.3 Novelty Checking

The `NoveltyChecker` prevents duplicate captures by comparing detected content against existing memories using semantic similarity.

#### Novelty Score Calculation

```python
def check_novelty(text, namespace=None):
    # Search for similar memories
    results = recall_service.search(text, k=5, namespace=namespace)

    if not results:
        return NoveltyResult(novelty_score=1.0, is_novel=True)

    # Calculate similarity from distance
    similarities = []
    for result in results:
        # Convert distance to similarity: 1 / (1 + distance)
        similarity = 1.0 / (1.0 + result.distance)
        similarities.append((result.memory.id, similarity))

    # Novelty = inverse of highest similarity
    highest_similarity = max(sim for _, sim in similarities)
    novelty_score = 1.0 - highest_similarity

    return NoveltyResult(
        novelty_score=novelty_score,
        is_novel=novelty_score >= threshold,  # Default 0.3
        similar_memory_ids=...,
        highest_similarity=highest_similarity,
    )
```

#### Novelty Score Interpretation

| Score Range | Interpretation | Action |
|-------------|----------------|--------|
| 0.0-0.3 | Likely duplicate | Skip capture |
| 0.3-0.7 | Partial novelty | Consider suggesting |
| 0.7-1.0 | High novelty | Recommend capture |

#### Configuration

- `novelty_threshold`: Minimum novelty score to consider content novel (default: 0.3)
- `similarity_threshold`: Similarity above which content is considered duplicate (default: 0.7)
- `k`: Number of similar memories to check (default: 5)

### 1.4 Capture Decision

The `CaptureDecider` determines the appropriate action based on signal confidence and novelty.

#### Decision Thresholds

| Action | Confidence Range | Description |
|--------|------------------|-------------|
| `AUTO` | >= 0.95 | Capture automatically with notification |
| `SUGGEST` | 0.70-0.95 | Show suggestion, user confirms |
| `SKIP` | < 0.70 | No action taken |

#### CaptureAction Enumeration

```python
class CaptureAction(Enum):
    AUTO = "auto"      # High confidence, capture silently
    SUGGEST = "suggest"  # Medium confidence, show suggestion
    SKIP = "skip"      # Low confidence, no action
```

#### Decision Logic

```python
def decide(signals, check_novelty=True):
    # Filter out non-novel signals
    novel_signals = []
    for signal in signals:
        novelty = check_signal_novelty(signal)
        if novelty.is_novel:
            novel_signals.append((signal, novelty))

    if not novel_signals:
        return CaptureDecision(action=SKIP, reason="All signals are duplicates")

    # Determine action based on highest confidence
    highest_confidence = max(s.confidence for s, _ in novel_signals)

    if highest_confidence >= 0.95:
        action = CaptureAction.AUTO
    elif highest_confidence >= 0.70:
        action = CaptureAction.SUGGEST
    else:
        action = CaptureAction.SKIP

    # Explicit signals always trigger SUGGEST at minimum
    if any(s.type == SignalType.EXPLICIT for s, _ in novel_signals):
        if action == CaptureAction.SKIP:
            action = CaptureAction.SUGGEST

    # Generate suggested captures
    suggested_captures = [
        generate_suggestion(signal, novelty)
        for signal, novelty in novel_signals
        if signal.confidence >= 0.70 or signal.type == SignalType.EXPLICIT
    ]

    return CaptureDecision(
        action=action,
        signals=signals,
        suggested_captures=suggested_captures,
        reason=f"Confidence {highest_confidence:.2f}",
    )
```

#### SuggestedCapture Generation

When generating suggestions, the decider extracts:

- **Summary**: Cleaned context text, truncated to 200 characters
- **Content**: Full signal context or match text
- **Namespace**: From signal's suggested_namespace
- **Tags**: Signal type + auto-detected technology tags
- **Confidence**: Adjusted for novelty (confidence * (0.5 + 0.5 * novelty_score))

Technology tags are auto-detected from content:

```python
tech_keywords = {
    "python": ["python", "pip", "pytest", "django", "flask"],
    "javascript": ["javascript", "js", "node", "npm", "react", "vue"],
    "typescript": ["typescript", "ts"],
    "database": ["database", "sql", "postgres", "mysql", "sqlite", "mongodb"],
    "api": ["api", "rest", "graphql", "endpoint"],
    "docker": ["docker", "container", "kubernetes", "k8s"],
    "git": ["git", "commit", "branch", "merge", "rebase"],
    "testing": ["test", "unittest", "pytest", "jest", "testing"],
    "performance": ["performance", "optimization", "cache", "fast", "slow"],
    "security": ["security", "auth", "authentication", "encryption"],
}
```

### 1.5 Validation

Before capture, all inputs are validated:

#### Namespace Validation

```python
NAMESPACES = frozenset({
    "inception",      # Problem statements, scope, success criteria
    "elicitation",    # Requirements clarifications, constraints
    "research",       # External findings, technology evaluations
    "decisions",      # Architecture Decision Records
    "progress",       # Task completions, milestones
    "blockers",       # Obstacles and resolutions
    "reviews",        # Code review findings
    "learnings",      # Technical insights, patterns
    "retrospective",  # Post-mortems
    "patterns",       # Cross-spec generalizations
})

def validate_namespace(namespace):
    if not namespace:
        raise ValidationError(
            "Namespace cannot be empty",
            f"Use one of: {', '.join(sorted(NAMESPACES))}"
        )
    if namespace not in NAMESPACES:
        raise ValidationError(
            f"Invalid namespace: '{namespace}'",
            f"Use one of: {', '.join(sorted(NAMESPACES))}"
        )
```

#### Summary Validation

```python
MAX_SUMMARY_CHARS = 100

def validate_summary(summary):
    if not summary or not summary.strip():
        raise ValidationError(
            "Summary cannot be empty",
            "Provide a one-line summary of the memory"
        )
    if len(summary) > MAX_SUMMARY_CHARS:
        raise ValidationError(
            f"Summary too long: {len(summary)} characters (max {MAX_SUMMARY_CHARS})",
            f"Shorten the summary to {MAX_SUMMARY_CHARS} characters or less"
        )
```

#### Content Validation

```python
MAX_CONTENT_BYTES = 102400  # 100KB

def validate_content(content):
    content_bytes = len(content.encode("utf-8"))
    if content_bytes > MAX_CONTENT_BYTES:
        raise ValidationError(
            f"Content too large: {content_bytes} bytes (max {MAX_CONTENT_BYTES})",
            "Reduce content size or split into multiple memories"
        )
```

### 1.6 Serialization

Memories are serialized to YAML front matter format for git notes storage.

#### Note Format

```yaml
---
type: decisions
timestamp: 2024-01-15T10:30:00+00:00
summary: Use PostgreSQL for persistence
spec: my-project
phase: planning
tags:
  - database
  - architecture
status: active
relates_to:
  - blockers:abc123:0
---

## Context

We needed to choose a database for production workloads...

## Decision

PostgreSQL was selected for its strong ACID compliance...
```

#### Front Matter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `type` | Yes | Namespace (e.g., "decisions") |
| `timestamp` | Yes | ISO 8601 timestamp |
| `summary` | Yes | One-line description (max 100 chars) |
| `spec` | No | Specification identifier |
| `phase` | No | Lifecycle phase |
| `tags` | No | List of categorization tags |
| `status` | No | Memory status (default: "active") |
| `relates_to` | No | List of related memory IDs |

#### Serialization Function

```python
def serialize_note(front_matter: dict, body: str = "") -> str:
    yaml_content = yaml.dump(
        front_matter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip()

    if body and body.strip():
        return f"---\n{yaml_content}\n---\n\n{body}"
    else:
        return f"---\n{yaml_content}\n---\n"
```

---

## 2. Storage

### 2.1 File Locking

The capture service uses `fcntl` advisory locking to prevent concurrent corruption when multiple processes attempt to capture simultaneously.

#### Lock Implementation

```python
@contextmanager
def _acquire_lock(lock_path: Path, timeout: float = 10.0):
    # Ensure parent directory exists
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = None
    try:
        # Open or create lock file
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)

        # Acquire exclusive lock (blocking)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if fd is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
```

#### Lock File Location

```python
def get_lock_path() -> Path:
    return get_data_path() / ".capture.lock"
    # Default: ~/.local/share/memory-plugin/.capture.lock
```

#### Concurrency Safety

The lock ensures atomic capture operations:
1. Lock acquired before any git or index operations
2. Git note append is atomic
3. Index insert/update within lock scope
4. Lock released after all operations complete

### 2.2 Git Notes Operations

Memories are stored as git notes under namespaced refs. The `GitOps` class provides a secure wrapper around git commands.

#### Git Ref Structure

```
refs/notes/mem/{namespace}
    refs/notes/mem/inception
    refs/notes/mem/elicitation
    refs/notes/mem/research
    refs/notes/mem/decisions
    refs/notes/mem/progress
    refs/notes/mem/blockers
    refs/notes/mem/reviews
    refs/notes/mem/learnings
    refs/notes/mem/retrospective
    refs/notes/mem/patterns
```

Each commit can have one note per namespace. Notes are stored as git objects referenced by the note ref.

#### Append vs Add Operations

| Operation | Method | Behavior |
|-----------|--------|----------|
| `add_note` | Overwrite | Replaces existing note content |
| `append_note` | Concatenate | Appends to existing note (preferred) |

**append_note** is preferred for capture operations because:
- Safely handles concurrent writes
- Preserves existing notes on the same commit
- No data loss if multiple captures target same commit

```python
def append_note(namespace: str, content: str, commit: str = "HEAD"):
    # Validate inputs
    self._validate_namespace(namespace)
    self._validate_git_ref(commit)

    # Append to note
    args = [
        "notes",
        f"--ref={self._note_ref(namespace)}",
        "append",
        "-m", content,
        commit,
    ]
    self._run_git(args)
```

#### Atomic Operations

Git notes operations are atomic at the git level:
- `git notes append` creates a new note object and updates the ref atomically
- If the command fails, no partial changes are made
- The ref update is protected by git's own locking

#### Security Validations

All git operations validate inputs to prevent command injection:

```python
def _validate_git_ref(ref: str):
    if not ref:
        raise ValidationError("Git ref cannot be empty")
    if ref.startswith("-"):
        raise ValidationError("Invalid ref: cannot start with dash")
    # Allow alphanumeric, dots, underscores, slashes, dashes, tilde/caret
    if not re.match(r"^[a-zA-Z0-9_./@^~-]+$", ref):
        raise ValidationError("Invalid ref format")

def validate_path(path: str):
    if not path:
        raise ValidationError("Path cannot be empty")
    if path.startswith("-"):
        raise ValidationError("Invalid path: cannot start with dash")
    if path.startswith("/") or "\x00" in path:
        raise ValidationError("Invalid path: absolute paths and null bytes not allowed")
    if ".." in path:
        raise ValidationError("Invalid path: path traversal not allowed")
    if not re.match(r"^[a-zA-Z0-9_./@-][a-zA-Z0-9_./@ -]*$", path):
        raise ValidationError("Invalid path format")
```

### 2.3 Memory ID Format

Each memory has a unique identifier in the format:

```
{namespace}:{commit_sha}:{index}
```

Components:
- **namespace**: Memory type (e.g., "decisions")
- **commit_sha**: Full 40-character commit SHA (or 7-char prefix in some contexts)
- **index**: Zero-based index within the note (for multi-memory notes)

Examples:
```
decisions:7e73558abcd1234567890abcdef1234567890abc:0
learnings:abc1234:1
blockers:def5678:0
```

#### Multi-Note Support

A single git note can contain multiple memories, separated by YAML front matter boundaries:

```yaml
---
type: decisions
timestamp: 2024-01-15T10:30:00Z
summary: First decision
---
## Context
...

---
type: decisions
timestamp: 2024-01-15T11:00:00Z
summary: Second decision
---
## Context
...
```

The index differentiates memories within the same note:
- First memory: `decisions:commit:0`
- Second memory: `decisions:commit:1`

---

## 3. Indexing

### 3.1 Embedding Generation

The `EmbeddingService` uses sentence-transformers to generate semantic vectors for memory search.

#### Model Configuration

| Setting | Default | Environment Variable |
|---------|---------|---------------------|
| Model | `all-MiniLM-L6-v2` | `MEMORY_PLUGIN_EMBEDDING_MODEL` |
| Dimensions | 384 | (fixed by model) |
| Normalization | L2 | (always applied) |

#### Lazy Loading

The model is loaded lazily on first use to avoid slow import times:

```python
class EmbeddingService:
    def __init__(self):
        self._model = None  # Not loaded yet

    def load(self):
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            self._model_name,
            cache_folder=str(self._cache_dir),
        )
        self._dimensions = self._model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            return [0.0] * self.dimensions  # Zero vector for empty text

        self.load()  # Lazy load

        embedding = self._model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,  # L2 normalization
        )
        return embedding.tolist()
```

#### Embedding Strategy

For each memory, the embedding is generated from the combined summary and content:

```python
embed_text = f"{summary}\n\n{content}"
embedding = embedding_service.embed(embed_text)
```

This ensures both the concise summary and detailed content contribute to semantic similarity.

### 3.2 SQLite Schema

The index uses SQLite with the sqlite-vec extension for vector similarity search.

#### memories Table

```sql
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,           -- namespace:commit_sha:index
    commit_sha TEXT NOT NULL,      -- Git commit
    namespace TEXT NOT NULL,       -- Memory type
    summary TEXT NOT NULL,         -- One-line description
    content TEXT NOT NULL,         -- Full markdown body
    timestamp TEXT NOT NULL,       -- ISO 8601
    spec TEXT,                     -- Specification ID
    phase TEXT,                    -- Lifecycle phase
    tags TEXT,                     -- Comma-separated tags
    status TEXT DEFAULT 'active',  -- Lifecycle status
    relates_to TEXT,               -- Comma-separated related IDs
    created_at TEXT NOT NULL,      -- Index insert time
    updated_at TEXT NOT NULL       -- Last modification time
);
```

#### Indexes

```sql
CREATE INDEX idx_memories_namespace ON memories(namespace);
CREATE INDEX idx_memories_spec ON memories(spec);
CREATE INDEX idx_memories_commit ON memories(commit_sha);
CREATE INDEX idx_memories_timestamp ON memories(timestamp);
CREATE INDEX idx_memories_status ON memories(status);
```

#### vec_memories Virtual Table

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories USING vec0(
    id TEXT PRIMARY KEY,
    embedding FLOAT[384]  -- EMBEDDING_DIMENSIONS
);
```

The virtual table uses sqlite-vec's `vec0` module for efficient KNN search.

#### metadata Table

```sql
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Stores: schema_version, last_sync
```

### 3.3 Graceful Degradation

Embedding failures do not block memory capture. If embedding generation fails:

1. Memory is still stored in git notes (authoritative source)
2. Memory is indexed without embedding (metadata only)
3. Warning is logged and returned in `CaptureResult`
4. Memory can be found via text search but not semantic search

```python
def capture(...):
    # ... validation and git storage ...

    indexed = False
    warning = None

    if index_service is not None:
        embedding = None
        if embedding_service is not None:
            try:
                embedding = embedding_service.embed(text)
            except Exception as e:
                warning = f"Embedding failed: {e}"
                # Continue without embedding

        try:
            index_service.insert(memory, embedding)
            indexed = True
        except Exception as e:
            warning = f"Indexing failed: {e}"

    return CaptureResult(
        success=True,  # Git storage succeeded
        memory=memory,
        indexed=indexed,
        warning=warning,
    )
```

---

## 4. Retrieval

### 4.1 Search Methods

#### Semantic Search (Vector Similarity)

The primary search method uses vector similarity via sqlite-vec KNN:

```python
def search(
    query: str,
    k: int = 10,
    namespace: str | None = None,
    spec: str | None = None,
    min_similarity: float | None = None,
) -> list[MemoryResult]:
    # Generate query embedding
    query_embedding = embedding_service.embed(query)

    # KNN search via sqlite-vec
    results = index.search_vector(
        query_embedding,
        k=k,
        namespace=namespace,
        spec=spec,
    )

    # Convert distance to similarity and filter
    for memory, distance in results:
        similarity = 1.0 / (1.0 + distance)
        if min_similarity is None or similarity >= min_similarity:
            yield MemoryResult(memory=memory, distance=distance)
```

The underlying sqlite-vec query:

```sql
SELECT v.id, v.distance
FROM vec_memories v
WHERE v.embedding MATCH ?  -- Binary-packed query vector
  AND k = ?                -- Number of neighbors
ORDER BY v.distance
```

#### Text Search (FTS-style)

For exact or partial text matches:

```python
def search_text(
    query: str,
    limit: int = 10,
    namespace: str | None = None,
    spec: str | None = None,
) -> list[Memory]:
    search_term = f"%{query}%"

    sql = """
        SELECT * FROM memories
        WHERE (summary LIKE ? OR content LIKE ?)
    """
    # Add namespace/spec filters if provided
    # ORDER BY timestamp DESC
```

#### Direct Retrieval by ID

```python
def get(memory_id: str) -> Memory | None:
    # SELECT * FROM memories WHERE id = ?

def get_batch(memory_ids: list[str]) -> list[Memory]:
    # SELECT * FROM memories WHERE id IN (?, ?, ...)
```

### 4.2 Progressive Hydration

Memories can be loaded at different levels of detail to balance performance and context richness.

#### HydrationLevel Enumeration

```python
class HydrationLevel(Enum):
    SUMMARY = 1  # Only metadata and summary (fastest)
    FULL = 2     # Complete note content from git
    FILES = 3    # Full content + file snapshots at commit time
```

#### Hydration Process

```python
def hydrate(memory: Memory, level: HydrationLevel) -> HydratedMemory:
    result = MemoryResult(memory=memory, distance=0.0)

    # SUMMARY level - no additional loading
    if level == HydrationLevel.SUMMARY:
        return HydratedMemory(result=result)

    # FULL level - load complete note content
    full_content = None
    commit_info = None

    if level.value >= HydrationLevel.FULL.value:
        full_content = git_ops.show_note(memory.namespace, memory.commit_sha)
        commit_info = git_ops.get_commit_info(memory.commit_sha)

    # FILES level - also load file snapshots
    files = ()
    if level == HydrationLevel.FILES:
        changed_files = git_ops.get_changed_files(memory.commit_sha)
        for path in changed_files:
            content = git_ops.get_file_at_commit(path, memory.commit_sha)
            if content:
                files.append((path, content))

    return HydratedMemory(
        result=result,
        full_content=full_content,
        files=tuple(files),
        commit_info=commit_info,
    )
```

#### HydratedMemory Structure

```python
@dataclass(frozen=True)
class HydratedMemory:
    result: MemoryResult           # Base memory with score
    full_content: str | None       # Complete git note (FULL+)
    files: tuple[tuple[str, str], ...]  # (path, content) pairs (FILES)
    commit_info: CommitInfo | None  # Author, date, message
```

### 4.3 Filtering and Scoring

#### Available Filters

| Filter | Description |
|--------|-------------|
| `namespace` | Limit to specific memory type |
| `spec` | Limit to specific specification |
| `min_similarity` | Minimum similarity threshold (0.0-1.0) |

#### Distance to Similarity Conversion

sqlite-vec returns Euclidean distance. For normalized vectors:

```python
# Lower distance = more similar
# Convert to 0-1 similarity score
similarity = 1.0 / (1.0 + distance)
```

| Distance | Similarity | Interpretation |
|----------|------------|----------------|
| 0.0 | 1.0 | Identical |
| 0.5 | 0.67 | Very similar |
| 1.0 | 0.5 | Moderately similar |
| 2.0 | 0.33 | Somewhat related |
| 3.0+ | <0.25 | Weakly related |

---

## 5. Hook Lifecycle

Claude Code hooks enable automatic memory capture and context injection throughout a session.

### 5.1 SessionStart

Invoked when a Claude Code session begins. Injects relevant memory context.

#### Trigger

```bash
echo '{"session_id": "...", "cwd": "/path", "source": "startup"}' | session_start.py
```

#### Processing Pipeline

1. **Load Configuration**: Read `HookConfig` from environment
2. **Detect Project**: Identify project name and spec from directory structure
3. **Build Guidance**: Generate response guidance XML (if enabled)
4. **Build Context**: Construct memory context within token budget
5. **Output JSON**: Return `additionalContext` for injection

#### Context Injection

```python
def build_context(project: str, session_source: str, spec_id: str | None):
    # Determine token budget based on mode
    if budget_mode == BudgetMode.ADAPTIVE:
        complexity = detect_project_complexity()
        total, working, semantic = config.get_budget_tier(complexity)
    elif budget_mode == BudgetMode.FIXED:
        total = config.session_start_fixed_budget

    # Allocate token budget
    budget = TokenBudget(
        total=total,
        working_memory=working,
        semantic_context=semantic,
        commands=100,
    )

    # Load working memory (active blockers, recent decisions)
    working_memory = load_working_memory(spec_id, budget.working_memory)

    # Load semantic context (relevant learnings, patterns)
    semantic_context = load_semantic_context(project, budget.semantic_context)

    # Format as XML
    return format_xml(working_memory, semantic_context)
```

#### Token Budget Tiers

| Complexity | Total | Working Memory | Semantic Context |
|------------|-------|----------------|------------------|
| simple | 500 | 300 | 100 |
| medium | 1000 | 500 | 300 |
| complex | 2000 | 900 | 900 |
| full | 3000 | 1400 | 1400 |

#### Output Format

```json
{
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "<memory_context>...</memory_context>"
    }
}
```

### 5.2 UserPromptSubmit

Invoked when the user submits a prompt. Detects and handles memorable content.

#### Trigger

```bash
echo '{"prompt": "I decided to use...", "cwd": "/path"}' | user_prompt.py
```

#### Processing Pipeline

1. **Parse Inline Markers**: Check for `[remember]` or `[remember:namespace]` markers
2. **Signal Detection**: If no markers, scan for capture signals
3. **Novelty Check**: Compare against existing memories
4. **Capture Decision**: Determine AUTO, SUGGEST, or SKIP
5. **Execute Action**: Auto-capture or return suggestions

#### Inline Marker Handling

```python
# If marker found, create high-confidence EXPLICIT signal
if parsed_marker:
    resolved_namespace = namespace_parser.resolve_namespace(parsed_marker)
    signals = [
        CaptureSignal(
            type=SignalType.EXPLICIT,
            match=prompt[:50],
            confidence=1.0,  # Highest confidence
            context=parsed_marker.content,
            suggested_namespace=resolved_namespace,
            position=0,
        )
    ]
else:
    # Standard signal detection
    detector = SignalDetector()
    signals = detector.detect(prompt)
```

#### Output Formats

**SKIP Action:**
```json
{"continue": true}
```

**SUGGEST Action:**
```json
{
    "continue": true,
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "captureSuggestions": [
            {
                "namespace": "decisions",
                "summary": "...",
                "content": "...",
                "tags": ["decision", "database"],
                "confidence": 0.85
            }
        ],
        "additionalContext": "<capture_suggestions>...</capture_suggestions>"
    }
}
```

**AUTO Action:**
```json
{
    "continue": true,
    "message": "Captured 1 memory(s) automatically",
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "capturedMemories": [
            {"success": true, "memory_id": "decisions:abc123:0", "summary": "..."}
        ]
    }
}
```

### 5.3 PostToolUse

Invoked after file operations (Read, Write, Edit, MultiEdit). Injects contextually relevant memories.

#### Trigger

```bash
echo '{"tool_name": "Read", "file_path": "/path/to/file.py"}' | post_tool_use.py
```

#### Processing Pipeline

1. **Filter Tool Types**: Only process Read, Write, Edit, MultiEdit
2. **Extract Domain**: Parse file path for domain keywords
3. **Search Memories**: Find memories related to domain/file
4. **Inject Context**: Return relevant memories as additionalContext

#### Domain Extraction

```python
def extract_domain(file_path: str) -> str:
    # Extract meaningful keywords from path
    # /src/auth/oauth.py -> "auth oauth authentication"
    # /tests/test_database.py -> "tests database"

    parts = Path(file_path).parts
    keywords = []
    for part in parts:
        # Skip common non-informative parts
        if part not in {"src", "lib", "tests", "test", ".", "..", ""}:
            keywords.append(part)

    # Include filename without extension
    stem = Path(file_path).stem
    if stem not in keywords:
        keywords.append(stem)

    return " ".join(keywords)
```

#### Output Format

```json
{
    "continue": true,
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "<related_memories>...</related_memories>"
    }
}
```

### 5.4 PreCompact

Invoked before context compaction. Preserves valuable content before it's lost.

#### Trigger

```bash
echo '{"context_summary": "...", "transcript_excerpt": "..."}' | pre_compact.py
```

#### Processing Pipeline

1. **Analyze Context**: Extract memorable content from transcript
2. **Signal Detection**: Detect capture signals in context
3. **Novelty Check**: Filter out duplicates
4. **Mode Decision**: Auto-capture or suggestion mode

#### Suggestion Mode (HOOK_PRE_COMPACT_PROMPT_FIRST)

When enabled, the hook shows what would be captured via stderr instead of auto-capturing:

```python
if config.pre_compact_prompt_first:
    # Suggestion mode: output to stderr, don't capture
    for suggestion in suggested_captures:
        sys.stderr.write(f"[memory] Would capture: {suggestion.summary}\n")

    return {
        "continue": True,
        "hookSpecificOutput": {
            "suggestions": suggested_captures,
            "message": "Use /capture to manually capture these memories"
        }
    }
else:
    # Auto-capture mode
    for suggestion in suggested_captures[:max_captures]:
        capture_memory(suggestion)
```

#### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOOK_PRE_COMPACT_ENABLED` | true | Enable hook |
| `HOOK_PRE_COMPACT_AUTO_CAPTURE` | true | Auto-capture without prompt |
| `HOOK_PRE_COMPACT_PROMPT_FIRST` | false | Suggestion mode |
| `HOOK_PRE_COMPACT_MIN_CONFIDENCE` | 0.85 | Confidence threshold |
| `HOOK_PRE_COMPACT_MAX_CAPTURES` | 3 | Max auto-captures per event |
| `HOOK_PRE_COMPACT_TIMEOUT` | 15 | Timeout in seconds |

### 5.5 Stop

Invoked when a Claude Code session ends. Performs cleanup and analysis.

#### Trigger

```bash
echo '{"cwd": "/path", "transcript_path": "/tmp/transcript.json"}' | stop.py
```

#### Processing Pipeline

1. **Analyze Transcript**: Scan for uncaptured memorable content
2. **Sync Index**: Perform incremental index synchronization
3. **Report**: Output uncaptured content and sync stats

#### Session Analysis

```python
def analyze_session(transcript_path: str) -> list[CaptureSignal]:
    if not transcript_path:
        return []

    path = Path(transcript_path)
    if not path.exists():
        return []

    analyzer = SessionAnalyzer(
        min_confidence=0.7,
        max_signals=5,
        novelty_threshold=0.3,
    )

    return analyzer.analyze(path, check_novelty=True)
```

#### Index Synchronization

```python
def sync_index() -> dict:
    sync = get_sync_service()
    indexed = sync.reindex(full=False)  # Incremental sync

    return {
        "success": True,
        "stats": {"indexed": indexed}
    }
```

#### Output Format

```json
{
    "continue": true,
    "message": "Found 2 potentially uncaptured memory(s) from this session. Consider using /remember to capture them.\nIndex synced: 5 memories indexed",
    "hookSpecificOutput": {
        "hookEventName": "Stop",
        "uncapturedContent": [
            {
                "type": "decision",
                "match": "I decided to...",
                "confidence": 0.85,
                "context": "...",
                "suggestedNamespace": "decisions"
            }
        ],
        "syncStats": {"indexed": 5},
        "additionalContext": "<uncaptured_memories>...</uncaptured_memories>"
    }
}
```

---

## 6. Memory State Transitions

### 6.1 Status Lifecycle

Memories progress through defined lifecycle states:

```
active → resolved → archived → tombstone → [deleted]
```

#### MemoryStatus Enumeration

```python
class MemoryStatus(str, Enum):
    ACTIVE = "active"        # Newly captured, fully relevant
    RESOLVED = "resolved"    # Task completed, still relevant
    ARCHIVED = "archived"    # Old memory, content compressed
    TOMBSTONE = "tombstone"  # Marked for deletion
```

#### Valid Transitions

| From | To | Trigger |
|------|-----|---------|
| `active` | `resolved` | Manual (user marks complete) |
| `active` | `archived` | Manual or automatic (age/decay) |
| `active` | `tombstone` | Manual (user deletes) |
| `resolved` | `archived` | Automatic (age threshold) |
| `resolved` | `tombstone` | Manual (user deletes) |
| `archived` | `tombstone` | Automatic (age threshold) |
| `archived` | `active` | Manual (restore) |
| `tombstone` | `active` | Manual (restore) |

#### Transition Validation

```python
def can_transition_to(current: MemoryStatus, target: MemoryStatus) -> bool:
    valid_transitions = {
        MemoryStatus.ACTIVE: {
            MemoryStatus.RESOLVED,
            MemoryStatus.ARCHIVED,
            MemoryStatus.TOMBSTONE,
        },
        MemoryStatus.RESOLVED: {
            MemoryStatus.ARCHIVED,
            MemoryStatus.TOMBSTONE,
        },
        MemoryStatus.ARCHIVED: {
            MemoryStatus.TOMBSTONE,
            MemoryStatus.ACTIVE,  # Restore
        },
        MemoryStatus.TOMBSTONE: {
            MemoryStatus.ACTIVE,  # Manual restore only
        },
    }
    return target in valid_transitions.get(current, set())
```

### 6.2 Temporal Decay

Memory relevance decays over time using exponential decay with configurable half-life.

#### Decay Formula

```python
def calculate_temporal_decay(timestamp: datetime, half_life_days: float = 30.0) -> float:
    """Calculate relevance score based on age.

    Returns:
        Score from 1.0 (brand new) to ~0.0 (very old)
    """
    age_days = (datetime.now(UTC) - timestamp).total_seconds() / SECONDS_PER_DAY

    # Exponential decay: relevance = 0.5 ^ (age / half_life)
    decay_factor = 0.5 ** (age_days / half_life_days)

    return decay_factor
```

#### Decay Examples (30-day half-life)

| Age | Relevance Score |
|-----|-----------------|
| 0 days | 1.00 |
| 7 days | 0.84 |
| 15 days | 0.71 |
| 30 days | 0.50 |
| 60 days | 0.25 |
| 90 days | 0.125 |
| 180 days | 0.016 |

#### Configuration

```python
DECAY_HALF_LIFE_DAYS = 30  # Configurable in config.py
```

### 6.3 Automatic Lifecycle Processing

The `LifecycleManager` handles automatic state transitions based on thresholds.

#### Thresholds

| Threshold | Default | Description |
|-----------|---------|-------------|
| `ARCHIVE_AGE_DAYS` | 90 | Auto-archive after this many days |
| `TOMBSTONE_AGE_DAYS` | 180 | Auto-tombstone archived memories |
| `GARBAGE_COLLECTION_AGE_DAYS` | 365 | Hard-delete tombstoned memories |
| `MIN_RELEVANCE_FOR_ACTIVE` | 0.1 | Below this relevance, consider archival |

#### Processing Logic

```python
def process_lifecycle(dry_run: bool = False):
    stats = LifecycleStats()

    for memory in get_all_memories():
        stats.scanned += 1

        # Check garbage collection first
        if should_garbage_collect(memory):
            # Tombstoned > 365 days
            if not dry_run:
                hard_delete(memory.id)
            stats.deleted += 1

        elif should_tombstone(memory):
            # Archived > 180 days
            if not dry_run:
                delete(memory.id)  # Soft delete
            stats.tombstoned += 1

        elif should_archive(memory):
            # Active/resolved > 90 days OR relevance < 0.1
            if not dry_run:
                archive(memory.id)
            stats.archived += 1

        else:
            stats.skipped += 1

    return stats
```

#### Content Compression

When archiving, content can be compressed to reduce storage:

```python
def archive(memory_id: str, compress: bool = True):
    memory = get(memory_id)

    if compress:
        compressed = zlib.compress(memory.content.encode(), level=6)
        ratio = len(compressed) / len(memory.content.encode())

        # Store compression metadata in content prefix
        new_content = (
            f"[ARCHIVED] [Compressed: {len(compressed)} bytes, "
            f"ratio: {ratio:.2f}] Original summary: {memory.summary}"
        )

    update(memory, status="archived", content=new_content)
```

---

## 7. Synchronization

### 7.1 Incremental Sync

The `SyncService` keeps the SQLite index synchronized with git notes.

#### sync_note_to_index

Indexes a single note from a specific commit:

```python
def sync_note_to_index(commit: str, namespace: str) -> int:
    # Get note content from git
    content = git_ops.show_note(namespace, commit)
    if content is None:
        return 0

    # Parse note content
    records = parser.parse_many(content)

    indexed = 0
    for i, record in enumerate(records):
        memory = record_to_memory(record, commit, namespace, i)

        # Generate embedding
        embedding = embedding_service.embed(
            f"{memory.summary}\n{memory.content}"
        )

        # Insert or update in index
        if index.exists(memory.id):
            index.update(memory, embedding=embedding)
        else:
            index.insert(memory, embedding=embedding)

        indexed += 1

    return indexed
```

### 7.2 Full Reindex

Rebuilds the entire index from git notes:

```python
def reindex(full: bool = False) -> int:
    if full:
        index.clear()  # Clear existing index

    indexed = 0

    for namespace in NAMESPACES:
        notes_list = git_ops.list_notes(namespace)

        for note_sha, commit_sha in notes_list:
            content = git_ops.show_note(namespace, commit_sha)
            if not content:
                continue

            records = parser.parse_many(content)

            for i, record in enumerate(records):
                memory = record_to_memory(record, commit_sha, namespace, i)

                # Skip if exists and not full reindex
                if not full and index.exists(memory.id):
                    continue

                # Generate embedding
                embedding = embedding_service.embed(...)

                # Insert into index
                index.insert(memory, embedding=embedding)
                indexed += 1

    return indexed
```

### 7.3 Verification and Repair

#### Consistency Verification

Compares index state against git notes:

```python
def verify_consistency() -> VerificationResult:
    # Collect expected IDs from git notes
    expected_ids = set()
    memory_hashes = {}

    for namespace in NAMESPACES:
        for note_sha, commit_sha in git_ops.list_notes(namespace):
            content = git_ops.show_note(namespace, commit_sha)
            records = parser.parse_many(content)

            for i, record in enumerate(records):
                memory_id = f"{namespace}:{commit_sha[:7]}:{i}"
                expected_ids.add(memory_id)

                # Store content hash for mismatch detection
                content_str = f"{record.summary}|{record.body}"
                memory_hashes[memory_id] = hashlib.md5(content_str.encode()).hexdigest()

    # Get indexed IDs
    indexed_ids = set(index.get_all_ids())

    # Find discrepancies
    missing_in_index = expected_ids - indexed_ids
    orphaned_in_index = indexed_ids - expected_ids

    # Check for content mismatches
    mismatched = []
    for memory_id in expected_ids & indexed_ids:
        memory = index.get(memory_id)
        current_hash = hashlib.md5(
            f"{memory.summary}|{memory.content}".encode()
        ).hexdigest()

        if current_hash != memory_hashes.get(memory_id):
            mismatched.append(memory_id)

    return VerificationResult(
        is_consistent=(not missing_in_index and not orphaned_in_index and not mismatched),
        missing_in_index=tuple(missing_in_index),
        orphaned_in_index=tuple(orphaned_in_index),
        mismatched=tuple(mismatched),
    )
```

#### Automatic Repair

```python
def repair(verification: VerificationResult = None) -> int:
    if verification is None:
        verification = verify_consistency()

    if verification.is_consistent:
        return 0

    repairs = 0

    # Remove orphaned entries
    for memory_id in verification.orphaned_in_index:
        index.delete(memory_id)
        repairs += 1

    # Re-index missing and mismatched
    for memory_id in verification.missing_in_index | verification.mismatched:
        namespace, commit_prefix, _ = memory_id.split(":")

        # Find full commit SHA and re-sync
        for note_sha, commit_sha in git_ops.list_notes(namespace):
            if commit_sha.startswith(commit_prefix):
                sync_note_to_index(commit_sha, namespace)
                repairs += 1
                break

    return repairs
```

---

## 8. Configuration Reference

### 8.1 Environment Variables

#### Core Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_PLUGIN_DATA_DIR` | `~/.local/share/memory-plugin/` | Data directory |
| `MEMORY_PLUGIN_GIT_NAMESPACE` | `refs/notes/mem` | Git notes ref prefix |
| `MEMORY_PLUGIN_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model |
| `MEMORY_PLUGIN_AUTO_CAPTURE` | `false` | Enable auto-capture |

#### Performance Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_TIMEOUT_MS` | 500 | Search operation timeout |
| `CAPTURE_TIMEOUT_MS` | 2000 | Capture operation timeout |
| `REINDEX_TIMEOUT_MS` | 60000 | Full reindex timeout |
| `LOCK_TIMEOUT_SECONDS` | 5 | File lock timeout |

#### Cache Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_TTL_SECONDS` | 300 | Cache lifetime (5 minutes) |
| `CACHE_MAX_ENTRIES` | 100 | Maximum cached results |

### 8.2 Hook Configuration

#### Master Controls

| Variable | Default | Description |
|----------|---------|-------------|
| `HOOK_ENABLED` | `true` | Master switch for all hooks |
| `HOOK_DEBUG` | `false` | Enable debug logging |
| `HOOK_TIMEOUT` | 30 | Default hook timeout (seconds) |

#### SessionStart Hook

| Variable | Default | Description |
|----------|---------|-------------|
| `HOOK_SESSION_START_ENABLED` | `true` | Enable hook |
| `HOOK_SESSION_START_BUDGET_MODE` | `adaptive` | Budget mode (adaptive/fixed/full/minimal) |
| `HOOK_SESSION_START_FIXED_BUDGET` | 1000 | Fixed budget token count |
| `HOOK_SESSION_START_MAX_BUDGET` | 3000 | Maximum budget cap |
| `HOOK_SESSION_START_INCLUDE_GUIDANCE` | `true` | Include response guidance |
| `HOOK_SESSION_START_GUIDANCE_DETAIL` | `standard` | Detail level (minimal/standard/detailed) |

#### Capture Detection

| Variable | Default | Description |
|----------|---------|-------------|
| `HOOK_CAPTURE_DETECTION_ENABLED` | `false` | Enable signal detection |
| `HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE` | 0.7 | SUGGEST threshold |
| `HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD` | 0.95 | AUTO threshold |
| `HOOK_CAPTURE_DETECTION_NOVELTY_THRESHOLD` | 0.3 | Novelty threshold |

#### UserPromptSubmit Hook

| Variable | Default | Description |
|----------|---------|-------------|
| `HOOK_USER_PROMPT_ENABLED` | `false` | Enable hook |

#### PostToolUse Hook

| Variable | Default | Description |
|----------|---------|-------------|
| `HOOK_POST_TOOL_USE_ENABLED` | `true` | Enable hook |
| `HOOK_POST_TOOL_USE_MIN_SIMILARITY` | 0.6 | Minimum similarity |
| `HOOK_POST_TOOL_USE_MAX_RESULTS` | 3 | Maximum memories to inject |
| `HOOK_POST_TOOL_USE_TIMEOUT` | 5 | Timeout in seconds |

#### PreCompact Hook

| Variable | Default | Description |
|----------|---------|-------------|
| `HOOK_PRE_COMPACT_ENABLED` | `true` | Enable hook |
| `HOOK_PRE_COMPACT_AUTO_CAPTURE` | `true` | Auto-capture without prompt |
| `HOOK_PRE_COMPACT_PROMPT_FIRST` | `false` | Suggestion mode |
| `HOOK_PRE_COMPACT_MIN_CONFIDENCE` | 0.85 | Confidence threshold |
| `HOOK_PRE_COMPACT_MAX_CAPTURES` | 3 | Max auto-captures |
| `HOOK_PRE_COMPACT_TIMEOUT` | 15 | Timeout in seconds |

#### Stop Hook

| Variable | Default | Description |
|----------|---------|-------------|
| `HOOK_STOP_ENABLED` | `true` | Enable hook |
| `HOOK_STOP_PROMPT_UNCAPTURED` | `true` | Prompt for uncaptured |
| `HOOK_STOP_SYNC_INDEX` | `true` | Sync index on stop |

---

## Appendix

### A. Namespace Reference

| Namespace | Purpose | Typical Content |
|-----------|---------|-----------------|
| `inception` | Problem definition | Problem statements, scope, success criteria |
| `elicitation` | Requirements gathering | Clarifications, constraints, assumptions |
| `research` | External findings | Technology evaluations, documentation links |
| `decisions` | Architecture decisions | ADRs, rationale, alternatives considered |
| `progress` | Milestones | Task completions, achievements, demos |
| `blockers` | Obstacles | Issues, impediments, waiting on others |
| `reviews` | Feedback | Code review findings, design critiques |
| `learnings` | Insights | Technical discoveries, patterns, anti-patterns |
| `retrospective` | Post-mortems | Project outcomes, lessons learned |
| `patterns` | Generalizations | Cross-project patterns, reusable solutions |

### B. Signal Pattern Reference

| SignalType | Trigger Phrases | Namespace | Confidence Range |
|------------|-----------------|-----------|------------------|
| DECISION | "decided to", "chose", "selected", "opted for", "went with", "made the call to" | decisions | 0.80-0.90 |
| LEARNING | "learned", "realized", "discovered", "TIL", "turns out", "aha moment" | learnings | 0.70-0.95 |
| BLOCKER | "blocked by", "stuck on", "can't because", "having trouble" | blockers | 0.70-0.92 |
| RESOLUTION | "fixed", "resolved", "solved", "workaround", "figured out" | solutions | 0.75-0.92 |
| PREFERENCE | "I prefer", "my preference is", "I'd rather" | preferences | 0.68-0.90 |
| EXPLICIT | "remember this", "save this", "note that", "don't forget" | notes | 0.75-0.98 |

### C. Error Handling

#### Exception Types

| Exception | Category | Common Causes |
|-----------|----------|---------------|
| `StorageError` | STORAGE | No commits, permission denied, invalid ref |
| `MemoryIndexError` | INDEX | Database locked, corrupted index, missing extension |
| `EmbeddingError` | EMBEDDING | OOM, corrupted model, network failure |
| `ParseError` | PARSE | Invalid YAML, missing fields, malformed content |
| `CaptureError` | CAPTURE | Lock timeout, concurrent capture |
| `RecallError` | RECALL | Search failure, hydration error |
| `ValidationError` | VALIDATION | Invalid namespace, content too large, path traversal |

#### Recovery Actions

| Error | Recovery Action |
|-------|-----------------|
| `NO_COMMITS_ERROR` | `git commit --allow-empty -m 'initial'` |
| `PERMISSION_DENIED_ERROR` | Check repository permissions |
| `INDEX_LOCKED_ERROR` | Wait or check for stuck processes |
| `SQLITE_VEC_MISSING_ERROR` | `pip install sqlite-vec` |
| `MODEL_OOM_ERROR` | Close applications or use smaller model |
| `MODEL_CORRUPTED_ERROR` | Delete models/ directory and retry |
| `INVALID_YAML_ERROR` | Fix YAML syntax in note |
| `MISSING_FIELD_ERROR` | Add required fields: type, spec, timestamp, summary |
| `LOCK_TIMEOUT_ERROR` | Wait and retry |
| `INVALID_NAMESPACE_ERROR` | Use valid namespace from list |
| `CONTENT_TOO_LARGE_ERROR` | Reduce content or split into multiple memories |

#### Error Message Format

All exceptions include:
- **category**: Error classification
- **message**: Human-readable description
- **recovery_action**: Suggested fix

```python
class MemoryError(Exception):
    def __init__(self, category, message, recovery_action):
        self.category = category
        self.message = message
        self.recovery_action = recovery_action

    def __str__(self):
        return f"[{self.category.value}] {self.message}\n-> {self.recovery_action}"
```

### D. Data Flow Diagram

```
                                User Input
                                    |
                    +---------------+---------------+
                    |               |               |
              Inline Marker    /capture Cmd    Hook Detection
                    |               |               |
                    +-------+-------+-------+-------+
                            |               |
                    NamespaceParser    SignalDetector
                            |               |
                            +-------+-------+
                                    |
                             NoveltyChecker
                                    |
                             CaptureDecider
                                    |
                    +---------------+---------------+
                    |                               |
                   SKIP                         AUTO/SUGGEST
                    |                               |
                  (done)                      CaptureService
                                                    |
                                    +---------------+---------------+
                                    |               |               |
                                validate()    serialize_note()  acquire_lock()
                                    |               |               |
                                    +-------+-------+---------------+
                                            |
                                    GitOps.append_note()
                                            |
                                    +-------+-------+
                                    |               |
                            EmbeddingService  (graceful fail)
                                    |               |
                                    +-------+-------+
                                            |
                                    IndexService.insert()
                                            |
                                    CaptureResult
                                            |
                                    release_lock()
```

### E. Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Search | < 500ms | Vector KNN query |
| Capture | < 2s | Including embedding generation |
| Full reindex | < 60s | Depends on corpus size |
| SessionStart hook | < 5s | Context injection |
| UserPromptSubmit hook | < 2s | Signal detection |
| Stop hook | < 5s | Index sync |
| PostToolUse hook | < 5s | Memory retrieval |
| PreCompact hook | < 15s | Analysis + capture |

### F. Storage Limits

| Limit | Value | Enforced At |
|-------|-------|-------------|
| Summary length | 100 characters | Validation |
| Content size | 100KB | Validation |
| Max file size (hydration) | 100KB | Hydration |
| Max files per hydration | 20 | Hydration |
| Cache entries | 100 | RecallService |
| Cache TTL | 5 minutes | RecallService |
