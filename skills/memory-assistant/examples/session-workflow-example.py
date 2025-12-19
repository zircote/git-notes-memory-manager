#!/usr/bin/env python3
"""
Example: Complete session workflow with memory integration.

This example demonstrates a complete workflow that integrates
memory capture and recall throughout a development session.
"""

from datetime import datetime
from git_notes_memory import get_capture_service, get_recall_service, get_sync_service


def session_start():
    """Initialize session with relevant context."""
    print("=" * 60)
    print("SESSION START")
    print("=" * 60)

    recall = get_recall_service()

    # Simulate detecting project context
    project_terms = ["api", "authentication", "python"]
    query = " ".join(project_terms)

    print(f"\nLoading context for: {query}\n")

    results = recall.search(
        query=query,
        k=5,
        min_similarity=0.5,
    )

    if results:
        print("## Relevant Context\n")
        for r in results:
            print(f"- **{r.memory.namespace}**: {r.memory.summary}")
        print()
    else:
        print("No existing context found. This may be a new project area.\n")

    return results


def work_phase_decision():
    """Simulate making a decision during work."""
    print("=" * 60)
    print("WORK PHASE: Decision Made")
    print("=" * 60)

    capture = get_capture_service()

    # Simulate user making a decision
    print("\nUser decides: 'Let's use FastAPI instead of Flask for the API layer'\n")

    result = capture.capture(
        namespace="decisions",
        summary="Use FastAPI for API layer",
        content="""## Context
Choosing between Flask and FastAPI for the new API endpoints.

## Decision
Use FastAPI for the REST API implementation.

## Rationale
- Built-in async support for better performance
- Automatic OpenAPI documentation
- Type hints for validation and IDE support
- Better performance than Flask in benchmarks

## Trade-offs
- Less mature ecosystem than Flask
- Team needs to learn async patterns
- Some middleware may not be compatible
""",
        tags=["api", "framework", "fastapi"],
    )

    if result.success:
        print(f"Decision captured: {result.memory_id}\n")
    else:
        print(f"Failed to capture: {result.message}\n")

    return result


def work_phase_learning():
    """Simulate discovering a learning during work."""
    print("=" * 60)
    print("WORK PHASE: Learning Discovered")
    print("=" * 60)

    capture = get_capture_service()

    # Simulate user learning something
    print("\nUser discovers: 'TIL FastAPI's Depends() can be used for dependency injection'\n")

    result = capture.capture(
        namespace="learnings",
        summary="FastAPI Depends() enables dependency injection",
        content="""## Discovery
FastAPI's Depends() function provides clean dependency injection.

## Example
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users/")
def get_users(db: Session = Depends(get_db)):
    return db.query(User).all()
```

## Benefits
- Clean separation of concerns
- Easy testing with override_dependency
- Automatic cleanup with generators
- Type hints work for IDE completion

## Gotcha
Dependencies are called once per request by default.
Use `Depends(get_db, use_cache=False)` for fresh instances.
""",
        tags=["fastapi", "dependency-injection", "python"],
    )

    if result.success:
        print(f"Learning captured: {result.memory_id}\n")
    else:
        print(f"Failed to capture: {result.message}\n")

    return result


def work_phase_blocker():
    """Simulate encountering and resolving a blocker."""
    print("=" * 60)
    print("WORK PHASE: Blocker Encountered & Resolved")
    print("=" * 60)

    capture = get_capture_service()

    # Simulate user hitting a blocker
    print("\nUser encounters: 'CORS errors blocking frontend requests'\n")

    result = capture.capture(
        namespace="blockers",
        summary="CORS errors blocking frontend API calls",
        content="""## Issue
Frontend application receiving CORS errors when calling the API.

## Error
```
Access to fetch at 'http://localhost:8000/api' from origin
'http://localhost:3000' has been blocked by CORS policy
```

## Impact
- Frontend development blocked
- Cannot test API integration

## Resolution
Added CORS middleware to FastAPI:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Prevention
- Add CORS configuration to project template
- Document allowed origins in README
""",
        tags=["cors", "fastapi", "frontend"],
        status="resolved",
    )

    if result.success:
        print(f"Blocker (resolved) captured: {result.memory_id}\n")
    else:
        print(f"Failed to capture: {result.message}\n")

    return result


def mid_session_recall():
    """Recall relevant memories during work."""
    print("=" * 60)
    print("MID-SESSION: Recalling Context")
    print("=" * 60)

    recall = get_recall_service()

    # Simulate user asking about past work
    print("\nUser asks: 'What did we decide about the API framework?'\n")

    results = recall.search(
        query="API framework decision",
        k=3,
        min_similarity=0.7,
        namespace="decisions",
    )

    if results:
        print("## Found Related Decisions\n")
        for r in results:
            print(f"### {r.memory.summary}")
            print(f"Relevance: {r.similarity:.0%}")
            print(f"> {r.memory.content[:200]}...")
            print()
    else:
        print("No related decisions found.\n")

    return results


def session_end():
    """Clean up and sync at session end."""
    print("=" * 60)
    print("SESSION END")
    print("=" * 60)

    sync = get_sync_service()

    # Verify and sync index
    print("\nVerifying index consistency...")

    result = sync.verify_consistency()

    if result.is_consistent:
        print("Index is consistent with git notes.")
    else:
        print(f"Found inconsistencies:")
        print(f"  - Missing in index: {len(result.missing_in_index)}")
        print(f"  - Orphaned in index: {len(result.orphaned_in_index)}")

        print("\nRepairing...")
        repaired = sync.repair(result)
        print(f"Repaired {repaired} issues.")

    # Show session summary
    recall = get_recall_service()

    print("\n## Session Summary\n")

    # Get memories created today
    today = datetime.now().date()

    # Search for recent memories
    results = recall.search(
        query="api fastapi cors",  # Topics from this session
        k=10,
        min_similarity=0.4,
    )

    recent = [r for r in results if r.memory.timestamp.date() == today]

    if recent:
        print(f"Memories captured this session: {len(recent)}")
        for r in recent:
            print(f"  - [{r.memory.namespace}] {r.memory.summary}")
    else:
        print("No memories captured this session.")

    print("\n## Uncaptured Content Check\n")
    print("Consider capturing any remaining insights before ending the session.")
    print("Use `/memory:capture` or inline markers like `[remember]`.\n")


def run_session_workflow():
    """Run the complete session workflow."""

    # Phase 1: Session start
    session_start()

    # Phase 2: Work phases
    work_phase_decision()
    work_phase_learning()
    work_phase_blocker()

    # Phase 3: Mid-session recall
    mid_session_recall()

    # Phase 4: Session end
    session_end()


if __name__ == "__main__":
    run_session_workflow()
