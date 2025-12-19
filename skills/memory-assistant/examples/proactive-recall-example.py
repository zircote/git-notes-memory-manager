#!/usr/bin/env python3
"""
Example: Proactive memory recall based on context.

This example demonstrates how to automatically recall
relevant memories based on the current working context.
"""

from git_notes_memory import get_recall_service


def recall_for_topic(topic: str) -> None:
    """Recall memories relevant to a topic."""
    recall = get_recall_service()

    print(f"## Context for: {topic}\n")

    # Semantic search across all namespaces
    results = recall.search(
        query=topic,
        k=5,
        min_similarity=0.6,  # Broader threshold for context
    )

    if not results:
        print("No relevant memories found.")
        return

    print(f"Found {len(results)} relevant memories:\n")

    for i, r in enumerate(results, 1):
        print(f"### {i}. {r.memory.namespace.title()}: {r.memory.summary}")
        print(f"**Relevance**: {r.similarity:.0%} | **Captured**: {r.memory.timestamp.strftime('%Y-%m-%d')}")
        print(f"> {r.memory.content[:200]}...")
        print()


def recall_for_question(question: str) -> None:
    """Recall memories to answer a specific question."""
    recall = get_recall_service()

    print(f'## Answering: "{question}"\n')

    # Higher threshold for direct questions
    results = recall.search(
        query=question,
        k=5,
        min_similarity=0.7,
    )

    if not results:
        print("No memories found that answer this question.")
        return

    print("Based on stored memories:\n")

    for i, r in enumerate(results, 1):
        print(f"### {i}. {r.memory.namespace.title()}: {r.memory.summary}")
        print(f"**Relevance**: {r.similarity:.0%}")
        print()
        # Show full content for questions
        print(r.memory.content)
        print("\n---\n")


def recall_for_error(error_message: str) -> None:
    """Recall memories related to an error."""
    recall = get_recall_service()

    print(f"## Searching for similar issues...\n")

    # Lower threshold for troubleshooting
    results = recall.search(
        query=error_message,
        k=5,
        min_similarity=0.55,
    )

    # Prioritize blockers and learnings
    priority_namespaces = ["blockers", "learnings", "patterns"]
    prioritized = sorted(
        results,
        key=lambda r: (
            -1 if r.memory.namespace in priority_namespaces else 0,
            -r.similarity,
        ),
    )

    if not prioritized:
        print("No similar issues found in memory.")
        return

    print("Possible related issues:\n")

    for i, r in enumerate(prioritized[:5], 1):
        print(f"### {i}. {r.memory.namespace.title()}: {r.memory.summary}")
        print(f"**Relevance**: {r.similarity:.0%}")
        print(f"> {r.memory.content[:300]}...")
        print()


def recall_session_context(project_terms: list[str]) -> None:
    """Recall context at session start."""
    recall = get_recall_service()

    print("## Session Context Loading\n")

    # Combine project terms into query
    query = " ".join(project_terms)

    # Broader search for context loading
    results = recall.search(
        query=query,
        k=5,
        min_similarity=0.5,
    )

    # Also get recent memories
    recent_results = recall.search(
        query=query,
        k=3,
        min_similarity=0.4,
    )

    if results:
        print("### Relevant to Current Project")
        for r in results[:3]:
            print(f"- **{r.memory.namespace}**: {r.memory.summary} ({r.similarity:.0%})")
        print()

    if recent_results:
        print("### Recent Memories")
        for r in recent_results[:3]:
            date_str = r.memory.timestamp.strftime("%Y-%m-%d")
            print(f"- {r.memory.summary} ({r.memory.namespace}, {date_str})")
        print()

    print("Use `/memory:recall` for more context.\n")


if __name__ == "__main__":
    # Example 1: Topic-based recall
    print("=" * 60)
    print("Example 1: Recalling context for a topic")
    print("=" * 60)
    recall_for_topic("authentication")

    # Example 2: Question-driven recall
    print("=" * 60)
    print("Example 2: Answering a question from memory")
    print("=" * 60)
    recall_for_question("Why did we choose PostgreSQL?")

    # Example 3: Error-pattern recall
    print("=" * 60)
    print("Example 3: Finding similar errors")
    print("=" * 60)
    recall_for_error("ConnectionTimeout: database connection failed")

    # Example 4: Session context loading
    print("=" * 60)
    print("Example 4: Loading session context")
    print("=" * 60)
    recall_session_context(["api", "authentication", "database"])
