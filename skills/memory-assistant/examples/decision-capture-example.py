#!/usr/bin/env python3
"""
Example: Capturing a decision with full context.

This example demonstrates capturing an architectural decision
with rationale, alternatives considered, and trade-offs.
"""

from git_notes_memory import get_capture_service


def capture_database_decision():
    """Capture a database technology decision."""
    capture = get_capture_service()

    # Structured decision content
    decision_content = """## Context
We need to choose a database for storing user sessions and application state.

## Options Considered
1. **PostgreSQL**: Full-featured RDBMS with JSONB support
2. **SQLite**: Simple, file-based, zero-config
3. **MongoDB**: Document store, flexible schema

## Decision
We will use **PostgreSQL** for the primary database.

## Rationale
- JSONB columns provide schema flexibility without sacrificing SQL capabilities
- Strong Python ecosystem (psycopg2, SQLAlchemy, asyncpg)
- Team has prior experience with PostgreSQL
- Better concurrency handling than SQLite for multi-user scenarios

## Trade-offs
- More operational complexity than SQLite (need to run/manage a server)
- Overkill for simple applications
- Requires connection pooling for optimal performance

## Consequences
- Need to set up PostgreSQL in development and CI environments
- Must implement connection pooling
- Database migrations will use Alembic
"""

    result = capture.capture(
        namespace="decisions",
        summary="Use PostgreSQL for primary database",
        content=decision_content,
        spec="my-project",
        tags=["database", "architecture", "postgresql"],
        phase="design",
    )

    if result.success:
        print(f"Decision captured: {result.memory_id}")
        print(f"Namespace: {result.namespace}")
        print(f"Commit: {result.commit[:8]}")
    else:
        print(f"Capture failed: {result.message}")


def capture_auth_decision():
    """Capture an authentication decision using convenience method."""
    capture = get_capture_service()

    result = capture.capture_decision(
        summary="Use JWT for API authentication",
        content="""## Context
Need to implement authentication for the REST API.

## Decision
Use JWT (JSON Web Tokens) for stateless API authentication.

## Rationale
- Stateless: No server-side session storage required
- Scalable: Works well with horizontal scaling
- Standard: Well-supported across languages and frameworks

## Alternatives
- Session cookies: Simpler but requires server-side storage
- API keys: Simpler but less secure for user authentication
- OAuth2 only: More complex than needed for this use case

## Implementation Notes
- Access tokens expire after 15 minutes
- Refresh tokens expire after 7 days
- Use httpOnly cookies for refresh token storage
""",
        spec="my-project",
    )

    print(f"Auth decision captured: {result.memory_id}")


if __name__ == "__main__":
    print("Capturing database decision...")
    capture_database_decision()

    print("\nCapturing auth decision...")
    capture_auth_decision()

    print("\nDone! Use /memory:recall to retrieve these decisions.")
