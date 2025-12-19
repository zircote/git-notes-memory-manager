---
name: memory-recall
description: This skill should be used when the user asks about "past decisions", "previous learnings", "what did we decide", "how did we solve", "remember when", or mentions topics that may have stored memories. Also triggers when working on tasks where historical context would be valuable, such as "working on authentication", "implementing the database", or encountering errors similar to previously resolved issues.
version: 0.1.0
---

# Memory Recall Skill

Automatically recalls relevant memories from the git-backed memory system to provide historical context during conversations.

## Purpose

This skill bridges the gap between conversations by surfacing relevant decisions, learnings, context, preferences, and patterns stored in the git notes memory system. It helps maintain continuity across sessions and prevents re-solving problems that have already been addressed.

## When This Skill Activates

### Direct Triggers

- Questions about past work: "what did we decide about...", "how did we handle...", "why did we choose..."
- Explicit recall requests: "recall", "remember when", "previously", "last time"
- Decision inquiries: "what was the reasoning", "why are we using..."

### Contextual Triggers

- Starting work on a feature that has related memories
- Encountering errors similar to previously resolved issues
- Discussing topics with high relevance scores to stored memories
- Beginning tasks where historical context would be valuable

## Core Workflow

### Step 1: Context Extraction

Extract key concepts from the current conversation:

```python
from git_notes_memory import get_recall_service

recall = get_recall_service()

# Extract concepts from recent messages
concepts = extract_concepts(conversation_context)
# Examples: file names, function names, error messages, technology terms
```

### Step 2: Memory Search

Perform semantic search across namespaces:

```bash
python3 -c "
from git_notes_memory import get_recall_service

recall = get_recall_service()
results = recall.search(
    query='''$EXTRACTED_CONCEPTS''',
    k=5,
    min_similarity=0.7  # Only high-relevance results
)

for r in results:
    print(f'{r.namespace}: {r.summary} (score: {r.score:.2f})')
"
```

### Step 3: Format Results

Present memories in a non-intrusive summary:

```
**Relevant Memories Found** (3 matches)

1. **Decision** (0.92 relevance): Use PostgreSQL for JSONB support
2. **Learning** (0.85 relevance): Connection pooling prevents timeouts
3. **Context** (0.78 relevance): Database schema in migrations/

_Use `/memory:recall` for more details or `/memory:search` for custom queries._
```

## Configuration

The skill respects environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORY_AUTO_RECALL` | `true` | Enable/disable automatic recall |
| `MEMORY_RECALL_THRESHOLD` | `0.7` | Minimum similarity score |
| `MEMORY_RECALL_LIMIT` | `3` | Maximum memories to surface |

## Namespace Reference

| Namespace | Contains | Example Query |
|-----------|----------|---------------|
| `decisions` | Architectural choices | "database selection", "auth approach" |
| `learnings` | Knowledge discoveries | "pytest fixtures", "async patterns" |
| `context` | Project information | "file locations", "conventions" |
| `preferences` | User preferences | "coding style", "tool choices" |
| `patterns` | Recurring solutions | "error handling", "API patterns" |

## Non-Intrusive Design Principles

1. **Relevance threshold**: Only surface memories above 0.7 similarity
2. **Limited output**: Show brief summaries, not full content
3. **No interruption**: Don't break user's flow mid-thought
4. **Escape hatch**: Can be disabled via environment variable
5. **On-demand detail**: Full content available via `/memory:recall`

## Integration Examples

### Automatic Context Loading

When user starts: "I'm working on the authentication system"

The skill:
1. Extracts "authentication system" as the query
2. Searches all namespaces
3. Surfaces relevant decisions, learnings, and patterns

### Error Resolution

When user encounters: "Getting a connection timeout error"

The skill:
1. Extracts "connection timeout error"
2. Searches for similar past issues
3. Surfaces relevant learnings and patterns

### Decision Inquiry

When user asks: "Why are we using Redis for caching?"

The skill:
1. Extracts "Redis caching" as the query
2. Focuses on `decisions` namespace
3. Surfaces the original decision with reasoning

## Related Commands

- `/memory:capture` - Store new memories
- `/memory:recall` - Manual recall with options
- `/memory:search` - Advanced search with filters
- `/memory:status` - Check system health

## Additional Resources

### Reference Files

For detailed implementation patterns:
- **`references/search-optimization.md`** - Query optimization techniques
- **`references/namespace-guide.md`** - When to use each namespace

### Example Files

Working examples in `examples/`:
- **`examples/auto-recall.py`** - Automatic context extraction
- **`examples/filtered-search.py`** - Namespace-filtered queries
