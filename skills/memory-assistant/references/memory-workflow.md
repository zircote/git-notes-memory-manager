# End-to-End Memory Lifecycle Workflow

This reference documents the complete memory lifecycle from capture through recall to maintenance.

## Lifecycle Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Memory Lifecycle Flow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│   │ Capture  │───►│  Index   │───►│  Recall  │───►│  Review  │  │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│        │                              │                │        │
│        │                              │                │        │
│        ▼                              ▼                ▼        │
│   ┌──────────┐                   ┌──────────┐    ┌──────────┐   │
│   │ Git Note │                   │  Inform  │    │  Update  │   │
│   │ Storage  │                   │ Decision │    │ Archive  │   │
│   └──────────┘                   └──────────┘    └──────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Capture

### Trigger Points
1. **Explicit capture**: User invokes `/memory:capture`
2. **Inline markers**: `[remember]`, `[capture]`, `@memory`
3. **Signal detection**: Assistant recognizes capture-worthy content
4. **Session end**: Stop hook prompts for uncaptured content

### Capture Flow
```
1. Detect capture opportunity (signal detection)
2. Identify appropriate namespace
3. Extract summary (max 100 chars)
4. Compose full content
5. Apply tags and metadata
6. Write to git note
7. Generate embedding
8. Index in SQLite
9. Confirm to user
```

### Quality Checklist
- [ ] Summary is scannable and actionable
- [ ] Content is self-contained
- [ ] Namespace is appropriate
- [ ] No sensitive data included
- [ ] Tags are consistent with project conventions
- [ ] Related memories linked if applicable

### Example Flow
```
User: "After testing, we've decided to use PostgreSQL because of JSONB support"

Assistant detects:
- Decision signal: "decided to use"
- Research signal: "after testing"
- Confidence: 0.92

Assistant suggests:
"💡 Decision detected! Capture this?

/memory:capture decisions Use PostgreSQL for data layer -- JSONB support for flexible schemas, better concurrency than SQLite, team familiarity. Trade-off: more operational overhead."
```

---

## Phase 2: Index

### Automatic Indexing
Every captured memory is automatically:
1. Stored as a git note (primary storage)
2. Embedded using sentence-transformers
3. Indexed in SQLite with sqlite-vec

### Index Maintenance
```
/memory:sync           # Incremental sync (default)
/memory:sync full      # Complete reindex
/memory:sync verify    # Check consistency
/memory:sync repair    # Fix inconsistencies
```

### When to Reindex
- After `git pull` that may include memory notes
- After manual git operations on notes
- When search results seem incomplete
- After errors in capture operations

### Index Health Monitoring
```bash
uv run python3 -c "
from git_notes_memory import get_sync_service

sync = get_sync_service()
result = sync.verify_consistency()

if result.is_consistent:
    print('Index healthy')
else:
    print(f'Issues: {len(result.missing_in_index)} missing, {len(result.orphaned_in_index)} orphaned')
"
```

---

## Phase 3: Recall

### Recall Triggers
1. **Explicit query**: User invokes `/memory:recall`
2. **Question patterns**: "what did we decide about..."
3. **Topic context**: Starting work on a known topic
4. **Error matching**: Similar errors to past blockers
5. **Session start**: Proactive context loading

### Search Methods
| Method | Use Case | Configuration |
|--------|----------|---------------|
| `search()` | Semantic/conceptual | `min_similarity=0.7` |
| `search_text()` | Exact keywords | FTS5 query syntax |
| `get_by_namespace()` | Browse by type | Namespace filter |
| `proactive_recall()` | Context-based | Auto-extracts terms |

### Result Presentation
```
## Recalled Memories ({n} results)

### 1. {Namespace}: {Summary}
**Relevance**: {score}% | **Captured**: {date}
> {content preview}...

---

### 2. ...
```

### Hydration Levels
```python
from git_notes_memory.models import HydrationLevel

# Metadata only (fast)
summary = recall.hydrate(id, HydrationLevel.SUMMARY)

# Full content (default)
full = recall.hydrate(id, HydrationLevel.FULL)

# Content + file snapshots (slow)
with_files = recall.hydrate(id, HydrationLevel.FILES)
```

---

## Phase 4: Inform

### How Recalled Memories Inform Work

#### Decision Support
```
User: "Should we add caching?"

Recalled: Previous decision about Redis selection

Value: Informs cache technology choice, surfaces known constraints
```

#### Error Resolution
```
User: "Getting connection timeout errors"

Recalled: Past blocker with similar error signature

Value: Provides known resolution path, saves debugging time
```

#### Pattern Application
```
User: "Implementing a new API endpoint"

Recalled: Existing API patterns in codebase

Value: Ensures consistency, applies proven approaches
```

### Feedback Loop
When recalled memories influence a decision or solution:
1. Acknowledge the memory's contribution
2. Consider capturing the new outcome
3. Link new memory to the recalled memory
4. Update original if context changed

---

## Phase 5: Review

### Periodic Memory Review

#### When to Review
- End of project phase
- Start of new sprint/iteration
- After major feature completion
- During retrospectives

#### Review Workflow
```
1. List memories by namespace: `/memory:search --namespace=decisions`
2. Check for outdated content
3. Identify gaps (what should be captured but isn't)
4. Archive stale memories
5. Consolidate related memories
```

### Memory Quality Audit
```bash
uv run python3 -c "
from git_notes_memory import get_recall_service

recall = get_recall_service()

# Get all memories
for ns in ['decisions', 'learnings', 'patterns']:
    memories = recall.get_by_namespace(ns)
    print(f'\n## {ns.title()} ({len(memories)})')
    for m in memories[:10]:
        # Check quality indicators
        summary_len = len(m.summary)
        content_len = len(m.content)
        has_tags = len(m.tags) > 0

        quality = 'Good' if all([
            summary_len <= 100,
            content_len > 50,
            has_tags
        ]) else 'Review'

        print(f'- [{quality}] {m.summary[:50]}...')
"
```

### Archive Workflow
```python
# Mark memory as archived (soft delete)
# The memory remains in git notes but is filtered from search

capture.capture(
    namespace="decisions",
    summary=original_summary,
    content=original_content,
    status="archived",  # Mark as archived
    relates_to=[original_memory_id]  # Link to original
)
```

---

## Phase 6: Maintenance

### Regular Maintenance Tasks

#### Daily (Automated via Hooks)
- Index sync on session end
- Consistency check for new memories

#### Weekly (Manual Review)
- Review recent captures for quality
- Check for duplicate content
- Verify tag consistency

#### Monthly (Deep Review)
- Audit all namespaces
- Archive outdated memories
- Consolidate related memories
- Update project documentation from memories

### Maintenance Commands
```bash
# Check system health
/memory:status --verbose

# Verify index consistency
/memory:sync verify

# Repair any issues
/memory:sync repair

# Full reindex if needed
/memory:sync full
```

### Git Notes Maintenance
```bash
# List all memory notes
git notes --ref=refs/notes/mem list

# Push notes to remote (if configured)
git push origin 'refs/notes/mem/*'

# Fetch notes from remote
git fetch origin 'refs/notes/mem/*:refs/notes/mem/*'
```

---

## Workflow Integration

### With Git Workflow
```
1. Work on feature branch
2. Capture decisions/learnings during development
3. Memories attached to feature commits
4. Merge to main - memories come along
5. Push to remote - notes can be shared
6. Pull from remote - notes sync
```

### With Project Lifecycle
```
Inception Phase:
  └── Capture: inception, elicitation

Research Phase:
  └── Capture: research, decisions

Implementation Phase:
  └── Capture: decisions, learnings, blockers, progress, patterns

Review Phase:
  └── Capture: reviews, learnings

Completion Phase:
  └── Capture: retrospective, patterns
  └── Review: all namespaces
  └── Archive: outdated memories
```

### With Claude Code Sessions
```
Session Start:
  └── Hook: Inject relevant context
  └── Recall: Project memories loaded

During Session:
  └── Detect: Capture opportunities
  └── Recall: On-demand context
  └── Capture: Inline markers

Session End:
  └── Hook: Prompt for uncaptured content
  └── Sync: Update index
```

---

## Best Practices Summary

### Capture Best Practices
1. Capture decisions when they're made, not after
2. Include rationale, not just the decision
3. Keep summaries under 100 characters
4. Use consistent namespace selection
5. Tag with project-consistent terms

### Recall Best Practices
1. Start specific, broaden if needed
2. Use namespace filters when you know the type
3. Combine semantic and text search appropriately
4. Don't ignore low-similarity results for troubleshooting

### Maintenance Best Practices
1. Sync regularly (Stop hook handles this)
2. Review memories at project milestones
3. Archive, don't delete, outdated content
4. Keep index consistent with git notes

### Team Collaboration
1. Push notes to shared remote
2. Establish namespace conventions
3. Use consistent tagging
4. Review each other's captures for quality
