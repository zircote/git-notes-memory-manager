"""Namespace styling with unicode characters.

This module provides visual styling for memory namespaces using unicode
box-drawing characters and emojis. No ANSI color codes are used, ensuring
clean display across all terminal types.

Unicode Format:
    ▶ decision ─────────────────────────────────────
    Content here describing the decision...
    ────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "NamespaceStyle",
    "get_style",
    "format_block_open",
    "format_block_close",
    "STYLES",
]

# Unicode characters for block formatting
ARROW = "▶"
DASH = "─"
BLOCK_WIDTH = 48  # Total width of the block marker line


@dataclass(frozen=True)
class NamespaceStyle:
    """Visual style for a namespace.

    Attributes:
        namespace: The namespace identifier.
        emoji: Emoji representing the namespace.
        label: Short label for block markers (e.g., "decision", "learned").
        description: Brief description of namespace purpose.
    """

    namespace: str
    emoji: str
    label: str
    description: str

    def format_block_open(self, summary: str = "") -> str:
        """Format a unicode block opening.

        Args:
            summary: Optional summary line after the marker.

        Returns:
            Unicode block opening like "▶ decision ───...".

        Example:
            >>> style.format_block_open("Use PostgreSQL")
            '▶ decision ───────────────────────────────────'
        """
        # Build the opening line: ▶ label ─────...
        prefix = f"{ARROW} {self.label} "
        # Fill remaining width with dashes
        dash_count = max(BLOCK_WIDTH - len(prefix), 10)
        opening = f"{prefix}{DASH * dash_count}"

        if summary:
            return f"{opening}\n{summary}"
        return opening

    def format_block_close(self) -> str:
        """Format a unicode block closing.

        Returns:
            Line of dashes to close the block.
        """
        return DASH * BLOCK_WIDTH


# =============================================================================
# Namespace Style Definitions
# =============================================================================

STYLES: dict[str, NamespaceStyle] = {
    "blockers": NamespaceStyle(
        namespace="blockers",
        emoji="🛑",
        label="blocker",
        description="Obstacles and impediments",
    ),
    "decisions": NamespaceStyle(
        namespace="decisions",
        emoji="⚖️",
        label="decision",
        description="Architecture decisions and choices",
    ),
    "learnings": NamespaceStyle(
        namespace="learnings",
        emoji="💡",
        label="learned",
        description="Technical insights and discoveries",
    ),
    "progress": NamespaceStyle(
        namespace="progress",
        emoji="🚀",
        label="progress",
        description="Task completions and milestones",
    ),
    "patterns": NamespaceStyle(
        namespace="patterns",
        emoji="🧩",
        label="pattern",
        description="Cross-project generalizations",
    ),
    "research": NamespaceStyle(
        namespace="research",
        emoji="🔍",
        label="research",
        description="External findings and evaluations",
    ),
    "reviews": NamespaceStyle(
        namespace="reviews",
        emoji="👁️",
        label="review",
        description="Code review findings",
    ),
    "retrospective": NamespaceStyle(
        namespace="retrospective",
        emoji="🔄",
        label="retro",
        description="Post-mortem reflections",
    ),
    "inception": NamespaceStyle(
        namespace="inception",
        emoji="🌱",
        label="inception",
        description="Problem statements and scope",
    ),
    "elicitation": NamespaceStyle(
        namespace="elicitation",
        emoji="💬",
        label="elicit",
        description="Requirements clarifications",
    ),
}

# Default style for unknown namespaces
DEFAULT_STYLE = NamespaceStyle(
    namespace="memory",
    emoji="📝",
    label="memory",
    description="General memory",
)


# =============================================================================
# Public API
# =============================================================================


def get_style(namespace: str) -> NamespaceStyle:
    """Get the style for a namespace.

    Args:
        namespace: The namespace identifier.

    Returns:
        NamespaceStyle for the namespace, or DEFAULT_STYLE if unknown.
    """
    return STYLES.get(namespace, DEFAULT_STYLE)


def format_block_open(namespace: str, summary: str = "") -> str:
    """Format a unicode block opening.

    Args:
        namespace: The namespace identifier.
        summary: Optional summary line after the marker.

    Returns:
        Unicode block opening.

    Example:
        >>> format_block_open("decisions", "Use PostgreSQL for persistence")
        '▶ decision ───────────────────────────────────
        Use PostgreSQL for persistence'
    """
    style = get_style(namespace)
    return style.format_block_open(summary)


def format_block_close(namespace: str) -> str:
    """Format a unicode block closing.

    Args:
        namespace: The namespace identifier.

    Returns:
        Line of dashes.

    Example:
        >>> format_block_close("decisions")
        '────────────────────────────────────────────────'
    """
    style = get_style(namespace)
    return style.format_block_close()
