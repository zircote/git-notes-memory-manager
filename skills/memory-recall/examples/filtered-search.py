#!/usr/bin/env python3
"""
Filtered search example: Namespace-specific and multi-filter queries.

This example demonstrates how to perform targeted searches
with namespace filtering and advanced query options.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SearchFilter:
    """Filters for memory search."""
    namespace: str | None = None
    namespaces: list[str] | None = None
    since: datetime | None = None
    until: datetime | None = None
    tags: list[str] | None = None
    min_score: float = 0.5


def search_by_namespace(
    query: str,
    namespace: str,
    limit: int = 5
) -> list:
    """
    Search within a specific namespace.

    Args:
        query: Search query
        namespace: Target namespace (decisions, learnings, etc.)
        limit: Maximum results

    Returns:
        List of matching memories
    """
    from git_notes_memory import get_recall_service

    recall = get_recall_service()
    return recall.search(
        query=query,
        namespace=namespace,
        k=limit
    )


def search_decisions(query: str, limit: int = 5) -> list:
    """Search only architectural decisions."""
    return search_by_namespace(query, 'decisions', limit)


def search_learnings(query: str, limit: int = 5) -> list:
    """Search only learnings and discoveries."""
    return search_by_namespace(query, 'learnings', limit)


def search_patterns(query: str, limit: int = 5) -> list:
    """Search only recurring patterns."""
    return search_by_namespace(query, 'patterns', limit)


def search_with_filters(
    query: str,
    filters: SearchFilter,
    limit: int = 10
) -> list:
    """
    Search with multiple filters applied.

    Args:
        query: Search query
        filters: SearchFilter with constraints
        limit: Maximum results

    Returns:
        Filtered list of memories
    """
    from git_notes_memory import get_recall_service

    recall = get_recall_service()

    # Start with base search
    if filters.namespaces:
        # Multi-namespace search
        all_results = []
        for ns in filters.namespaces:
            results = recall.search(query=query, namespace=ns, k=limit)
            all_results.extend(results)
        # Sort by score and deduplicate
        seen_ids = set()
        results = []
        for r in sorted(all_results, key=lambda x: x.score, reverse=True):
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                results.append(r)
    elif filters.namespace:
        results = recall.search(
            query=query,
            namespace=filters.namespace,
            k=limit * 2  # Get more for filtering
        )
    else:
        results = recall.search(query=query, k=limit * 2)

    # Apply additional filters
    filtered = []
    for r in results:
        # Score filter
        if r.score < filters.min_score:
            continue

        # Date filters (timestamp is already a datetime object)
        if filters.since and r.timestamp < filters.since:
            continue
        if filters.until and r.timestamp > filters.until:
            continue

        # Tag filter
        if filters.tags:
            memory_tags = getattr(r, 'tags', []) or []
            if not any(tag in memory_tags for tag in filters.tags):
                continue

        filtered.append(r)

        if len(filtered) >= limit:
            break

    return filtered


def search_recent(
    query: str,
    days: int = 7,
    namespace: str | None = None,
    limit: int = 5
) -> list:
    """Search memories from recent days."""
    filters = SearchFilter(
        namespace=namespace,
        since=datetime.now() - timedelta(days=days)
    )
    return search_with_filters(query, filters, limit)


def search_by_tags(
    tags: list[str],
    query: str | None = None,
    limit: int = 10
) -> list:
    """Search memories with specific tags."""
    filters = SearchFilter(tags=tags)
    search_query = query or ' '.join(tags)
    return search_with_filters(search_query, filters, limit)


def cross_namespace_search(
    query: str,
    namespaces: list[str],
    limit_per_namespace: int = 3
) -> dict:
    """
    Search across multiple namespaces, returning results by namespace.

    Args:
        query: Search query
        namespaces: List of namespaces to search
        limit_per_namespace: Max results per namespace

    Returns:
        Dict mapping namespace to results
    """
    from git_notes_memory import get_recall_service

    recall = get_recall_service()
    results_by_namespace = {}

    for ns in namespaces:
        results = recall.search(
            query=query,
            namespace=ns,
            k=limit_per_namespace
        )
        if results:
            results_by_namespace[ns] = results

    return results_by_namespace


def format_cross_namespace_results(results: dict) -> str:
    """Format cross-namespace search results."""
    if not results:
        return "No memories found across searched namespaces."

    lines = []
    for namespace, memories in results.items():
        lines.append(f"\n### {namespace.title()} ({len(memories)} found)")
        for i, m in enumerate(memories, 1):
            lines.append(f"  {i}. {m.summary} ({m.score:.2f})")

    return '\n'.join(lines)


# Example usage
if __name__ == '__main__':
    # Example 1: Search only decisions
    print("=== Decision Search ===")
    decisions = search_decisions("database")
    for d in decisions:
        print(f"  - {d.summary}: {d.score:.2f}")

    # Example 2: Search with date filter
    print("\n=== Recent Learnings (7 days) ===")
    recent = search_recent("error handling", days=7, namespace='learnings')
    for r in recent:
        print(f"  - {r.summary}: {r.timestamp.strftime('%Y-%m-%d')}")

    # Example 3: Cross-namespace search
    print("\n=== Cross-Namespace: Authentication ===")
    cross = cross_namespace_search(
        "authentication",
        namespaces=['decisions', 'learnings', 'patterns'],
        limit_per_namespace=2
    )
    print(format_cross_namespace_results(cross))

    # Example 4: Tag-based search
    print("\n=== Tagged: API + Security ===")
    tagged = search_by_tags(['api', 'security'], limit=5)
    for t in tagged:
        print(f"  - {t.namespace}: {t.summary}")
