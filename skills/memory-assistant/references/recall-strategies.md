# Context-Aware Recall Strategies

This reference documents strategies for proactively recalling relevant memories based on conversation context.

## Recall Trigger Framework

The memory assistant uses multiple strategies to determine when and what to recall.

---

## Strategy 1: Topic-Based Recall

When a specific topic is mentioned, search for related memories.

### Trigger Detection
```python
# Keywords that indicate a topic worth searching
topic_indicators = [
    "working on", "implementing", "debugging", "reviewing",
    "starting", "continuing", "finishing", "looking at"
]

# Extract the topic following the indicator
# "working on authentication" -> topic = "authentication"
```

### Search Configuration
```python
recall.search(
    query=topic,
    k=5,
    min_similarity=0.6,  # Broader threshold for topic context
    namespace=None  # Search all namespaces
)
```

### Presentation Format
```
## Context for: {topic}

Found {n} relevant memories:
- **{namespace}**: {summary} ({score}% relevant)
...

Use `/memory:recall {topic}` for full details.
```

### When to Use
- User explicitly mentions starting work on something
- Topic hasn't been discussed recently in the session
- Confidence the topic has stored memories (based on project history)

---

## Strategy 2: Question-Driven Recall

When user asks about past decisions, learnings, or approaches.

### Trigger Detection
```python
question_patterns = [
    (r"what did we decide", "decisions"),
    (r"why did we (choose|use|pick)", "decisions"),
    (r"how did we (solve|fix|handle)", ["learnings", "patterns"]),
    (r"remember when", None),  # Search all
    (r"what was the (reason|rationale)", "decisions"),
    (r"previously", None),
    (r"last time", None),
]
```

### Search Configuration
```python
# Higher threshold for direct questions
recall.search(
    query=extracted_query,
    k=5,
    min_similarity=0.7,  # Higher precision for questions
    namespace=inferred_namespace
)
```

### Presentation Format
```
## Answering: "{question}"

Based on stored memories:

### 1. {namespace}: {summary}
**Captured**: {date} | **Relevance**: {score}%
> {content preview}

...
```

### When to Use
- User asks an explicit question about past work
- Question contains "why", "what", "how" about past events
- Question references time ("when", "last time", "before")

---

## Strategy 3: Error-Pattern Recall

When an error or issue appears that may match past blockers/learnings.

### Trigger Detection
```python
error_indicators = [
    "error:", "exception:", "failed:", "cannot",
    "doesn't work", "broken", "crash", "timeout"
]

# Extract error signature for search
# "ConnectionTimeout error in database" -> "ConnectionTimeout database"
```

### Search Configuration
```python
# Search blockers and learnings specifically
recall.search(
    query=error_signature,
    k=5,
    min_similarity=0.55,  # Lower threshold for troubleshooting
    namespace=None  # But prioritize blockers, learnings
)

# Post-filter by namespace relevance
prioritized = sort_by_namespace_priority(
    results,
    priority=["blockers", "learnings", "patterns"]
)
```

### Presentation Format
```
## Possible Related Issues

This error resembles past issues:

1. **Blocker**: {summary}
   Resolution: {resolution if captured}

2. **Learning**: {summary}
   Insight: {key takeaway}

Try these approaches first before deep debugging.
```

### When to Use
- Error message or stack trace appears in output
- User describes something "not working"
- Pattern matches known issue signatures

---

## Strategy 4: File-Context Recall

When working on specific files, recall memories related to those files or their domain.

### Trigger Detection
```python
# When a file is read or edited
file_context_triggers = [
    "reading", "editing", "looking at", "opening",
    "modifying", "updating", "checking"
]

# Extract domain from file path
# "src/auth/jwt_handler.py" -> ["auth", "jwt", "authentication"]
```

### Search Configuration
```python
# Build query from file path and name
file_domain = extract_domain(file_path)

recall.search(
    query=file_domain,
    k=5,
    min_similarity=0.65
)
```

### Presentation Format
```
## Context for: {file_name}

Memories related to this area:
- {summary} ({namespace}, {date})
...
```

### When to Use
- Opening a file for significant changes
- File is in a domain with known memories
- First time touching this file in the session

---

## Strategy 5: Session Continuity Recall

At session start, recall memories from recent work or project context.

### Trigger Detection
```python
# Triggered by SessionStart hook
# Also triggered by:
session_continuity_triggers = [
    "continuing from", "picking up", "back to",
    "where were we", "resuming"
]
```

### Search Configuration
```python
# Use project detector to identify context
project_context = detect_project_context()

recall.search(
    query=project_context.key_terms,
    k=5,
    min_similarity=0.5,  # Broader for context loading
    spec=project_context.spec_id
)

# Also fetch recent memories regardless of similarity
recent = recall.list_recent(
    limit=3,
    namespace=None,
    spec=project_context.spec_id
)
```

### Presentation Format
```
## Session Context Loaded

### Recent Memories
- {summary} ({namespace}, {relative_time})

### Related to Current Project
- {summary} ({score}% relevant)
...

Use `/memory:recall` for more context.
```

### When to Use
- Session start (via hook)
- User indicates they're continuing previous work
- Gap of significant time since last interaction

---

## Strategy 6: Decision-Impact Recall

When about to make a decision, recall related past decisions.

### Trigger Detection
```python
decision_consideration_patterns = [
    "should we use", "thinking about", "considering",
    "evaluating", "options are", "trade-off between"
]
```

### Search Configuration
```python
recall.search(
    query=decision_topic,
    k=5,
    min_similarity=0.7,
    namespace="decisions"  # Focus on decisions
)
```

### Presentation Format
```
## Related Past Decisions

Before deciding, consider these related choices:

1. **{summary}** ({date})
   Rationale: {key rationale}
   Outcome: {if known}

2. ...

These may inform or constrain your current decision.
```

### When to Use
- User is about to make an architectural decision
- Topic relates to existing decision memories
- Decision domain has high-impact past choices

---

## Relevance Scoring Adjustments

Base similarity scores can be adjusted based on context:

### Recency Boost
```python
def apply_recency_boost(result, max_boost=0.1):
    """Boost recent memories slightly."""
    age_days = (now - result.timestamp).days
    if age_days < 7:
        return result.score + max_boost
    elif age_days < 30:
        return result.score + (max_boost * 0.5)
    return result.score
```

### Namespace Priority
```python
def apply_namespace_priority(results, priority_namespaces):
    """Boost results from priority namespaces."""
    for r in results:
        if r.namespace in priority_namespaces:
            r.adjusted_score = r.score + 0.05
    return sorted(results, key=lambda r: r.adjusted_score, reverse=True)
```

### Tag Match Boost
```python
def apply_tag_boost(results, context_tags):
    """Boost memories with matching tags."""
    for r in results:
        matching_tags = set(r.tags) & set(context_tags)
        r.adjusted_score = r.score + (len(matching_tags) * 0.02)
    return results
```

---

## Recall Suppression

Avoid recalling in certain situations:

### When to Suppress
1. **Same memory just shown**: Don't repeat within session
2. **Low-confidence context**: Don't guess at relevance
3. **Rapid conversation flow**: Don't interrupt with recall
4. **User explicitly declined**: Respect "don't recall" signals

### Suppression Implementation
```python
class RecallTracker:
    def __init__(self):
        self.shown_this_session = set()
        self.suppressed_until = None

    def should_recall(self, memory_id: str) -> bool:
        if memory_id in self.shown_this_session:
            return False
        if self.suppressed_until and now < self.suppressed_until:
            return False
        return True

    def mark_shown(self, memory_id: str):
        self.shown_this_session.add(memory_id)

    def suppress_for(self, seconds: int):
        self.suppressed_until = now + timedelta(seconds=seconds)
```

---

## Multi-Strategy Combination

For complex contexts, combine multiple strategies:

```python
def comprehensive_recall(context: ConversationContext) -> RecallResult:
    """Combine multiple recall strategies."""
    results = []

    # Topic-based (if topic detected)
    if context.current_topic:
        results.extend(topic_recall(context.current_topic))

    # File-based (if files mentioned)
    if context.active_files:
        results.extend(file_recall(context.active_files))

    # Error-based (if errors present)
    if context.recent_errors:
        results.extend(error_recall(context.recent_errors))

    # Deduplicate and sort
    unique_results = deduplicate(results)
    sorted_results = sort_by_relevance(unique_results)

    return RecallResult(
        memories=sorted_results[:5],  # Top 5
        strategy_used=identify_primary_strategy(results),
        confidence=calculate_overall_confidence(sorted_results)
    )
```

---

## Performance Considerations

### Caching
```python
# Cache embeddings for frequently searched terms
@lru_cache(maxsize=200)
def cached_embed(query: str) -> list[float]:
    return embedding_service.embed(query)

# Cache recent search results
@lru_cache(maxsize=50)
def cached_search(query: str, namespace: str | None) -> tuple:
    results = recall.search(query, namespace=namespace)
    return tuple(results)  # Tuple for hashability
```

### Batch Queries
```python
# For multiple strategies, batch where possible
def batch_recall(queries: list[str]) -> dict[str, list]:
    embeddings = embedding_service.embed_batch(queries)
    results = {}
    for query, embedding in zip(queries, embeddings):
        results[query] = index_service.search_vector(embedding)
    return results
```

### Threshold Shortcuts
```python
# Skip search if query is too generic
SKIP_QUERIES = {"the", "a", "this", "that", "it"}

def should_search(query: str) -> bool:
    words = query.lower().split()
    meaningful_words = [w for w in words if w not in SKIP_QUERIES]
    return len(meaningful_words) >= 1
```
