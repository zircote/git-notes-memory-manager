#!/usr/bin/env python3
"""
Auto-recall example: Extract context and surface relevant memories.

This example demonstrates how to automatically extract key concepts
from conversation context and recall relevant memories.
"""

import re


def extract_concepts(text: str) -> list[str]:
    """
    Extract key concepts from conversation text.

    Identifies:
    - File paths and names
    - Function/class names (CamelCase, snake_case)
    - Technology terms
    - Error messages
    """
    concepts = []

    # File paths
    file_patterns = re.findall(r'[\w/]+\.\w+', text)
    concepts.extend(file_patterns)

    # CamelCase identifiers (likely class names)
    camel_case = re.findall(r'\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b', text)
    concepts.extend(camel_case)

    # snake_case identifiers (likely function names)
    snake_case = re.findall(r'\b[a-z]+(?:_[a-z]+)+\b', text)
    concepts.extend(snake_case)

    # Technology terms (common patterns)
    tech_terms = [
        'database', 'api', 'auth', 'authentication', 'cache', 'redis',
        'postgres', 'postgresql', 'mysql', 'sqlite', 'mongodb',
        'docker', 'kubernetes', 'aws', 'gcp', 'azure',
        'python', 'javascript', 'typescript', 'react', 'fastapi',
        'pytest', 'test', 'migration', 'deploy', 'ci/cd'
    ]
    for term in tech_terms:
        if term.lower() in text.lower():
            concepts.append(term)

    # Error-related terms
    if any(word in text.lower() for word in ['error', 'exception', 'failed', 'timeout']):
        # Extract the error context
        error_match = re.search(r'(\w+(?:Error|Exception|Failed|Timeout))', text)
        if error_match:
            concepts.append(error_match.group(1))

    return list(set(concepts))  # Deduplicate


def build_query(concepts: list[str], max_terms: int = 5) -> str:
    """Build a search query from extracted concepts."""
    # Prioritize: errors > tech terms > identifiers
    prioritized = sorted(concepts, key=lambda c: (
        0 if 'error' in c.lower() else 1,
        0 if c.lower() in ['database', 'auth', 'api'] else 1,
        len(c)  # Shorter terms often more specific
    ))
    return ' '.join(prioritized[:max_terms])


def auto_recall(
    conversation_text: str,
    namespace: str | None = None,
    threshold: float = 0.7,
    limit: int = 3
) -> dict:
    """
    Automatically recall memories relevant to conversation context.

    Args:
        conversation_text: Recent conversation messages
        namespace: Optional namespace to filter (None = all)
        threshold: Minimum relevance score
        limit: Maximum memories to return

    Returns:
        dict with concepts, query, and results
    """
    from git_notes_memory import get_recall_service

    # Step 1: Extract concepts
    concepts = extract_concepts(conversation_text)

    if not concepts:
        return {
            'concepts': [],
            'query': '',
            'results': [],
            'message': 'No key concepts found in context'
        }

    # Step 2: Build query
    query = build_query(concepts)

    # Step 3: Search memories
    recall = get_recall_service()
    results = recall.search(
        query=query,
        namespace=namespace,
        k=limit * 2  # Get more, then filter by threshold
    )

    # Step 4: Filter by threshold
    filtered = [r for r in results if r.score >= threshold][:limit]

    return {
        'concepts': concepts,
        'query': query,
        'results': filtered,
        'message': f'Found {len(filtered)} relevant memories'
    }


def format_results(recall_result: dict) -> str:
    """Format recall results for display."""
    if not recall_result['results']:
        return "No relevant memories found for current context."

    lines = [f"**Relevant Memories Found** ({len(recall_result['results'])} matches)\n"]

    for i, r in enumerate(recall_result['results'], 1):
        lines.append(f"{i}. **{r.namespace.title()}** ({r.score:.2f}): {r.summary}")

    lines.append("\n_Use `/memory:recall` for details or `/memory:search` for custom queries._")

    return '\n'.join(lines)


# Example usage
if __name__ == '__main__':
    # Simulate conversation context
    conversation = """
    User: I'm working on the authentication system.
    The login endpoint is returning a 401 error.
    I think it might be related to JWT token validation.
    """

    result = auto_recall(conversation)

    print("Extracted concepts:", result['concepts'])
    print("Search query:", result['query'])
    print("\nFormatted output:")
    print(format_results(result))
