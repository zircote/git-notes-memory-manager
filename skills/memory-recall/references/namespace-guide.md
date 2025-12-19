# Namespace Guide

Detailed guidance on when and how to use each memory namespace.

## Namespace Overview

The memory system organizes memories into 10 namespaces, each serving a distinct purpose:

| Namespace | Purpose | Persistence | Search Priority |
|-----------|---------|-------------|-----------------|
| `inception` | Problem statements, scope | Project lifetime | High |
| `elicitation` | Requirements, constraints | Project lifetime | Medium |
| `research` | External findings, evaluations | Long-term | Medium |
| `decisions` | Architectural choices | Long-term | High |
| `progress` | Milestones, completions | Project lifetime | Low |
| `blockers` | Obstacles, impediments | Medium-term | Medium |
| `reviews` | Code review findings | Medium-term | Medium |
| `learnings` | Knowledge discoveries | Long-term | High |
| `retrospective` | Post-mortems | Long-term | Medium |
| `patterns` | Recurring solutions | Long-term | High |

---

## Inception Namespace

### When to Store

- Project problem statements ("Building a memory system for Claude")
- Success criteria ("Must support semantic search with <500ms latency")
- Scope definitions ("CLI and API, no GUI for MVP")
- Initial constraints ("Must work offline")

### When to Recall

- Starting new phases of the project
- Evaluating feature requests against original scope
- Checking if success criteria are met
- Onboarding new contributors

### Example Memories

```
Inception: Building git-notes-memory plugin
Problem: Claude Code lacks persistent memory across sessions
Success criteria:
- Semantic search in <500ms
- 90%+ test coverage
- Works with existing git workflows
Scope: Python library + Claude Code plugin
```

### Search Queries

- "project scope", "success criteria"
- "what are we building", "project goals"

---

## Elicitation Namespace

### When to Store

- Requirements clarifications ("Must support Python 3.11+")
- Constraints discovered during development ("Git 2.25+ required for notes features")
- User feedback that refines requirements
- Non-functional requirements ("100KB max memory size")

### When to Recall

- Making implementation decisions
- Evaluating trade-offs
- Checking compatibility requirements
- Writing documentation

### Example Memories

```
Elicitation: Git version requirement
Requirement: Must support Git 2.25 or higher
Reason: git notes features used require this version
Impact: Document in README, add version check
```

### Search Queries

- "requirements", "must support", "constraint"
- "version requirement", "compatibility"

---

## Research Namespace

### When to Store

- Technology evaluations ("Compared sqlite-vec vs pgvector")
- External documentation findings
- Benchmark results
- Third-party library assessments

### When to Recall

- Making technology decisions
- Justifying architectural choices
- Investigating alternatives
- Performance optimization

### Example Memories

```
Research: Embedding model comparison
Evaluated: all-MiniLM-L6-v2, all-mpnet-base-v2, e5-small-v2
Winner: all-MiniLM-L6-v2
Rationale: Best balance of speed (384 dims) and quality
Benchmarks: 0.82 accuracy, 15ms latency
```

### Search Queries

- "compared", "evaluated", "benchmark"
- "technology evaluation", "alternative options"

---

## Decisions Namespace

### When to Store

- Architectural choices ("Use frozen dataclasses for immutability")
- Technology selections ("Using FastAPI for the API layer")
- Design decisions ("Events will be stored in append-only log")
- Trade-off resolutions ("Prioritized consistency over availability")

### When to Recall

- Questions starting with "why did we..."
- When similar decisions need to be made
- During code reviews questioning design
- When onboarding new team members

### Example Memories

```
Decision: Use PostgreSQL for main database
Rationale: JSONB support, strong Python ecosystem, team familiarity
Trade-offs: Slightly more complex than SQLite, but scales better
Alternatives considered: SQLite, MongoDB
Date: 2024-01-15
```

### Search Queries

- "database choice", "why postgres"
- "api framework decision"
- "architecture decision authentication"

---

## Progress Namespace

### When to Store

- Milestone completions ("Phase 1: Foundation complete")
- Feature completions ("Implemented semantic search")
- Sprint/iteration summaries
- Version releases

### When to Recall

- Checking project status
- Writing release notes
- Preparing status updates
- Planning next phases

### Example Memories

```
Progress: Phase 1 Foundation complete
Completed: 2024-01-20
Deliverables:
- Core capture/recall services
- SQLite + sqlite-vec index
- 90% test coverage
Next: Phase 2 - Hooks integration
```

### Search Queries

- "completed", "finished", "milestone"
- "phase complete", "delivered"

---

## Blockers Namespace

### When to Store

- Obstacles encountered ("CI pipeline timeout")
- Dependencies blocking progress
- Technical debt items
- Resolutions when blockers are cleared

### When to Recall

- Similar issues arise
- Sprint planning
- Risk assessment
- Post-mortems

### Example Memories

```
Blocker: CI pipeline timeout
Issue: Tests exceed 30-minute GitHub Actions limit
Impact: PRs cannot merge, blocking all development
Resolution: Split test suite into parallel jobs
Date resolved: 2024-01-18
```

### Search Queries

- "blocked", "stuck", "cannot"
- "timeout", "failing", "broken"

---

## Reviews Namespace

### When to Store

- Code review findings ("Security: validate all git refs")
- Review feedback patterns
- Common issues found in reviews
- Architecture review outcomes

### When to Recall

- Doing similar code reviews
- Creating review checklists
- Training on common issues
- Security audits

### Example Memories

```
Review: Security - Git ref validation
Finding: Git refs passed to subprocess without validation
Severity: High
Fix: Added validate_git_ref() with allowlist
Files: git_ops.py, utils.py
```

### Search Queries

- "code review", "security finding"
- "review feedback", "found in review"

---

## Learnings Namespace

### When to Store

- TIL discoveries ("pytest fixtures can be module-scoped")
- Bug root causes ("Memory leak caused by unclosed connections")
- Performance insights ("Batch inserts 10x faster than individual")
- Gotchas and edge cases ("SQLite doesn't enforce foreign keys by default")

### When to Recall

- Encountering similar problems
- Working with related technologies
- Debugging issues
- Code review discussions

### Example Memories

```
Learning: pytest fixtures with scope="module" persist across tests
Context: Discovered while optimizing slow test suite
Application: Use for expensive setup like database connections
Gotcha: Must handle cleanup properly to avoid test pollution
Date: 2024-01-12
```

### Search Queries

- "pytest slow tests"
- "database performance"
- "memory leak python"

---

## Retrospective Namespace

### When to Store

- Project post-mortems
- Sprint retrospectives
- What went well / what didn't
- Process improvements identified

### When to Recall

- Starting similar projects
- Process improvement discussions
- Estimating new work
- Avoiding past mistakes

### Example Memories

```
Retrospective: git-notes-memory v0.1.0
Outcome: success
What went well:
- TDD approach caught bugs early
- Type hints prevented runtime errors
What to improve:
- Start documentation earlier
- More integration tests
Lessons: Always validate external inputs
```

### Search Queries

- "retrospective", "post-mortem"
- "lessons learned", "what went well"

---

## Patterns Namespace

### When to Store

- Recurring solutions ("Error handling follows Result pattern")
- Common code structures ("API endpoints follow controller pattern")
- Reusable approaches ("Retry with exponential backoff for network calls")
- Idioms ("Use context managers for resource cleanup")

### When to Recall

- Implementing similar functionality
- Code review for consistency
- Suggesting implementations
- Teaching patterns to new code areas

### Example Memories

```
Pattern: Error handling with Result type
Usage: All service methods return Result[T, Error] instead of raising
Implementation: See utils/result.py for Result class
Applies to: Service layer, not controllers
Evidence: Used in 15+ modules successfully
Date: 2024-01-05
```

### Search Queries

- "error handling pattern"
- "api endpoint structure"
- "retry logic"

---

## Cross-Namespace Queries

Some queries benefit from searching multiple namespaces:

### "Authentication" Query

| Namespace | Expected Results |
|-----------|-----------------|
| inception | "Building secure auth system" |
| elicitation | "Must support OAuth2 and JWT" |
| decisions | "Use JWT for stateless auth" |
| learnings | "Refresh tokens need secure storage" |
| patterns | "Token validation pattern" |

### "Database" Query

| Namespace | Expected Results |
|-----------|-----------------|
| research | "Compared PostgreSQL vs MySQL vs SQLite" |
| decisions | "PostgreSQL for JSONB support" |
| learnings | "Connection pooling prevents timeouts" |
| progress | "Schema migration complete" |
| patterns | "Repository pattern for data access" |

---

## Namespace Selection Logic

When the query doesn't explicitly target a namespace:

```python
def infer_namespace(query):
    """Infer likely namespace from query patterns."""

    # Inception indicators
    if any(w in query.lower() for w in ['scope', 'goals', 'building', 'problem']):
        return 'inception'

    # Elicitation indicators
    if any(w in query.lower() for w in ['requirement', 'must', 'constraint']):
        return 'elicitation'

    # Research indicators
    if any(w in query.lower() for w in ['compared', 'evaluated', 'benchmark']):
        return 'research'

    # Decision indicators
    if any(w in query.lower() for w in ['why', 'chose', 'decision', 'rationale']):
        return 'decisions'

    # Progress indicators
    if any(w in query.lower() for w in ['completed', 'finished', 'milestone']):
        return 'progress'

    # Blocker indicators
    if any(w in query.lower() for w in ['blocked', 'stuck', 'cannot', 'broken']):
        return 'blockers'

    # Review indicators
    if any(w in query.lower() for w in ['review', 'finding', 'audit']):
        return 'reviews'

    # Learning indicators
    if any(w in query.lower() for w in ['til', 'learned', 'discovered', 'gotcha']):
        return 'learnings'

    # Retrospective indicators
    if any(w in query.lower() for w in ['retrospective', 'postmortem', 'lessons']):
        return 'retrospective'

    # Pattern indicators
    if any(w in query.lower() for w in ['pattern', 'approach', 'idiom', 'how to']):
        return 'patterns'

    # Default: search all
    return None
```

---

## Lifecycle Considerations

Memories have different retention characteristics:

| Namespace | Typical Lifespan | Archive Trigger |
|-----------|------------------|-----------------|
| inception | Project lifetime | Project completion |
| elicitation | Project lifetime | Requirements change |
| research | Long-term | Technology obsolete |
| decisions | Long-term | Decision reversed |
| progress | Project lifetime | Project completion |
| blockers | Medium-term | Resolution found |
| reviews | Medium-term | Issues addressed |
| learnings | Long-term | Rarely archived |
| retrospective | Long-term | Never archived |
| patterns | Long-term | Pattern superseded |

---

## Best Practices

1. **Be specific in queries**: "authentication jwt" better than "auth"
2. **Use namespace hints**: When you know the type you're looking for
3. **Cross-reference**: Important topics often span multiple namespaces
4. **Update stale content**: Mark outdated memories as archived
5. **Link related memories**: Reference decision IDs in patterns
6. **Include context**: Add "why" not just "what"
7. **Keep summaries short**: 100 characters max, be concise
8. **Tag appropriately**: Use consistent tags across namespaces
