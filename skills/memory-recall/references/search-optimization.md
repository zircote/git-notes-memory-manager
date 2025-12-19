# Search Optimization Techniques

Advanced techniques for optimizing memory recall queries.

## Semantic vs Text Search

The library provides two search modes:

```python
from git_notes_memory import get_recall_service

recall = get_recall_service()

# Semantic search (vector similarity) - best for conceptual queries
results = recall.search("authentication flow", k=10)

# Text search (FTS5 keyword matching) - best for exact terms
results = recall.search_text("JWT token", limit=10)
```

| Mode | Method | Best For |
|------|--------|----------|
| Semantic | `search()` | Conceptual queries, finding related ideas |
| Text | `search_text()` | Exact terms, specific identifiers |

## Threshold Tuning

Adjust relevance thresholds based on context using `min_similarity`:

| Scenario | Threshold | Rationale |
|----------|-----------|-----------|
| Direct question | 0.8+ | High precision needed |
| Feature work | 0.6-0.7 | Balance precision/recall |
| Exploration | 0.5 | Cast wider net |
| Troubleshooting | 0.55 | Include related issues |

```python
# High precision for direct questions
results = recall.search(
    query="why did we choose PostgreSQL",
    k=5,
    min_similarity=0.8
)

# Broader search for exploration
results = recall.search(
    query="database",
    k=10,
    min_similarity=0.5
)

# Dynamic threshold based on query type
def get_threshold(query_type):
    thresholds = {
        'question': 0.8,
        'feature': 0.65,
        'explore': 0.5,
        'debug': 0.55
    }
    return thresholds.get(query_type, 0.7)
```

## Namespace Filtering

Target specific memory types for faster, more relevant results:

```python
# For decision inquiries
results = recall.search(
    query="why redis",
    k=5,
    namespace="decisions"
)

# For troubleshooting
results = recall.search(
    query="timeout error",
    k=10,
    namespace="learnings"
)

# For spec-specific context
results = recall.search(
    query="authentication",
    k=10,
    namespace="decisions",
    spec="my-project"
)
```

## Multi-Namespace Search

To search across multiple namespaces, query each and merge results:

```python
def search_multiple_namespaces(query, namespaces, k_per_ns=5):
    """Search across multiple namespaces, merging results."""
    all_results = []

    for ns in namespaces:
        results = recall.search(query=query, namespace=ns, k=k_per_ns)
        all_results.extend(results)

    # Sort by score (lower distance = better)
    all_results.sort(key=lambda r: r.distance)

    # Deduplicate by ID
    seen = set()
    unique = []
    for r in all_results:
        if r.id not in seen:
            seen.add(r.id)
            unique.append(r)

    return unique

# Example: search decisions and patterns together
results = search_multiple_namespaces(
    "database",
    namespaces=["decisions", "patterns"],
    k_per_ns=5
)
```

## Context Window Management

Manage result size for context efficiency:

```python
# Summarize long memories
def format_for_context(memories, max_chars=500):
    formatted = []
    for m in memories:
        content = m.content
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        formatted.append({
            'type': m.namespace,
            'summary': m.summary,
            'score': m.score,
            'content': content
        })
    return formatted
```

## Caching Strategies

Cache frequent queries for faster recall:

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def cached_search(query, namespace=None, k=5):
    recall = get_recall_service()
    # Convert results to tuple for hashability
    return tuple(recall.search(query, namespace=namespace, k=k))

# Clear cache when new memories added
def on_memory_captured():
    cached_search.cache_clear()
```

## Performance Metrics

Monitor search performance:

```python
import time

def timed_search(query, **kwargs):
    recall = get_recall_service()
    start = time.time()
    results = recall.search(query, **kwargs)
    duration = time.time() - start

    return {
        'results': results,
        'duration_ms': duration * 1000,
        'count': len(results),
        'avg_score': sum(r.score for r in results) / len(results) if results else 0
    }
```

## Best Practices

1. **Start specific, then broaden**: Begin with focused queries, expand if no results
2. **Use namespace hints**: When query implies a type (e.g., "why" -> decisions)
3. **Limit results**: Surface 3-5 highly relevant memories, not all matches
4. **Cache common queries**: Project-specific terms are queried repeatedly
5. **Monitor relevance**: Track which recalled memories users actually reference
6. **Use appropriate search mode**: Semantic for concepts, text for exact matches
7. **Combine with hydration**: Use `recall_context()` for search + hydration in one call

## Convenience Methods

The RecallService provides convenience methods for common patterns:

```python
# Search and hydrate in one call
from git_notes_memory.models import HydrationLevel

hydrated = recall.recall_context(
    query="error handling",
    k=5,
    hydration_level=HydrationLevel.FULL
)

# Find similar memories
memory = recall.get("decisions:abc123:0")
similar = recall.recall_similar(memory, k=3)

# List recent memories
recent = recall.list_recent(limit=10, namespace="learnings")
```
