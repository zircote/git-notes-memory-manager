"""Namespace styling with ANSI colors and emojis.

This module provides visual styling for memory namespaces using ANSI
color codes and emojis. Colors are chosen based on psychological and
philosophical associations with each namespace's purpose.

Color Psychology:
- RED: Danger, urgency, stop (blockers)
- BLUE: Trust, stability, authority (decisions)
- GREEN: Growth, knowledge, freshness (learnings, inception)
- CYAN: Forward movement, achievement (progress, elicitation)
- YELLOW: Curiosity, discovery, attention (research)
- MAGENTA: Creativity, patterns, wisdom (patterns, retrospective)
- ORANGE: Evaluation, warmth, feedback (reviews)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "NamespaceStyle",
    "get_style",
    "format_namespace",
    "format_marker",
    "STYLES",
]


class Color(Enum):
    """ANSI color codes for terminal output."""

    # Standard colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    # Bright/bold colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"

    # Orange (via 256-color mode)
    ORANGE = "\033[38;5;208m"
    BRIGHT_ORANGE = "\033[38;5;214m"

    # Reset
    RESET = "\033[0m"

    # Bold modifier
    BOLD = "\033[1m"


@dataclass(frozen=True)
class NamespaceStyle:
    """Visual style for a namespace.

    Attributes:
        namespace: The namespace identifier.
        emoji: Emoji representing the namespace.
        color: ANSI color code for the namespace.
        label: Human-readable label for the namespace.
        description: Brief description of namespace purpose.
    """

    namespace: str
    emoji: str
    color: str
    label: str
    description: str

    def format_badge(self, text: str | None = None) -> str:
        """Format a colored badge for the namespace.

        Args:
            text: Optional text to include after the badge.
                If None, just returns the emoji and label.

        Returns:
            ANSI-colored string with emoji, label, and optional text.
        """
        badge = f"{self.color}{self.emoji} {self.label}{Color.RESET.value}"
        if text:
            return f"{badge} {text}"
        return badge

    def format_marker(self, content: str) -> str:
        """Format a capture marker with styling.

        Args:
            content: The marker content text.

        Returns:
            Styled marker string like "[🛑 blocker] content".
        """
        marker_name = self.namespace
        # Use shorter names for common markers
        if self.namespace == "learnings":
            marker_name = "learned"
        elif self.namespace == "decisions":
            marker_name = "decision"
        elif self.namespace == "blockers":
            marker_name = "blocker"

        return f"{self.color}[{self.emoji} {marker_name}]{Color.RESET.value} {content}"

    def format_inline(self) -> str:
        """Format just the namespace with emoji and color.

        Returns:
            Colored namespace string like "🛑 blockers".
        """
        return f"{self.color}{self.emoji} {self.namespace}{Color.RESET.value}"


# =============================================================================
# Namespace Style Definitions
# =============================================================================

STYLES: dict[str, NamespaceStyle] = {
    # 🛑 BLOCKERS - Red for danger/stop/urgent
    "blockers": NamespaceStyle(
        namespace="blockers",
        emoji="🛑",
        color=Color.BRIGHT_RED.value,
        label="BLOCKER",
        description="Obstacles and impediments",
    ),
    # ⚖️ DECISIONS - Blue for trust/authority/stability
    "decisions": NamespaceStyle(
        namespace="decisions",
        emoji="⚖️",
        color=Color.BRIGHT_BLUE.value,
        label="DECISION",
        description="Architecture decisions and choices",
    ),
    # 💡 LEARNINGS - Green for growth/knowledge/insight
    "learnings": NamespaceStyle(
        namespace="learnings",
        emoji="💡",
        color=Color.BRIGHT_GREEN.value,
        label="LEARNED",
        description="Technical insights and discoveries",
    ),
    # 🚀 PROGRESS - Cyan for forward movement/achievement
    "progress": NamespaceStyle(
        namespace="progress",
        emoji="🚀",
        color=Color.BRIGHT_CYAN.value,
        label="PROGRESS",
        description="Task completions and milestones",
    ),
    # 🧩 PATTERNS - Magenta for creativity/abstraction/wisdom
    "patterns": NamespaceStyle(
        namespace="patterns",
        emoji="🧩",
        color=Color.BRIGHT_MAGENTA.value,
        label="PATTERN",
        description="Cross-project generalizations",
    ),
    # 🔍 RESEARCH - Yellow for curiosity/discovery/illumination
    "research": NamespaceStyle(
        namespace="research",
        emoji="🔍",
        color=Color.BRIGHT_YELLOW.value,
        label="RESEARCH",
        description="External findings and evaluations",
    ),
    # 👁️ REVIEWS - Orange for evaluation/scrutiny/feedback
    "reviews": NamespaceStyle(
        namespace="reviews",
        emoji="👁️",
        color=Color.ORANGE.value,
        label="REVIEW",
        description="Code review findings",
    ),
    # 🔄 RETROSPECTIVE - Magenta for reflection/introspection
    "retrospective": NamespaceStyle(
        namespace="retrospective",
        emoji="🔄",
        color=Color.MAGENTA.value,
        label="RETRO",
        description="Post-mortem reflections",
    ),
    # 🌱 INCEPTION - Light green for beginnings/new growth
    "inception": NamespaceStyle(
        namespace="inception",
        emoji="🌱",
        color=Color.GREEN.value,
        label="INCEPTION",
        description="Problem statements and scope",
    ),
    # 💬 ELICITATION - Light cyan for communication/dialogue
    "elicitation": NamespaceStyle(
        namespace="elicitation",
        emoji="💬",
        color=Color.CYAN.value,
        label="ELICIT",
        description="Requirements clarifications",
    ),
}

# Default style for unknown namespaces
DEFAULT_STYLE = NamespaceStyle(
    namespace="memory",
    emoji="📝",
    color=Color.RESET.value,
    label="MEMORY",
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


def format_namespace(namespace: str, with_emoji: bool = True) -> str:
    """Format a namespace with color and optional emoji.

    Args:
        namespace: The namespace identifier.
        with_emoji: Whether to include the emoji (default True).

    Returns:
        Colored namespace string.
    """
    style = get_style(namespace)
    if with_emoji:
        return style.format_inline()
    return f"{style.color}{namespace}{Color.RESET.value}"


def format_marker(namespace: str, content: str) -> str:
    """Format a capture marker with full styling.

    Args:
        namespace: The namespace identifier.
        content: The marker content text.

    Returns:
        Fully styled marker string.

    Example:
        >>> format_marker("blockers", "Database connection timeout")
        '[🛑 blocker] Database connection timeout'  # with red coloring
    """
    style = get_style(namespace)
    return style.format_marker(content)


def format_memory_header(
    namespace: str,
    memory_id: str,
    timestamp: str | None = None,
) -> str:
    """Format a memory header for display.

    Args:
        namespace: The namespace identifier.
        memory_id: The memory ID.
        timestamp: Optional ISO timestamp.

    Returns:
        Formatted header string with color and emoji.
    """
    style = get_style(namespace)
    header = f"{style.color}{style.emoji} [{style.label}]{Color.RESET.value}"

    # Add dimmed ID
    dim = "\033[2m"
    header += f" {dim}{memory_id}{Color.RESET.value}"

    if timestamp:
        header += f" {dim}({timestamp}){Color.RESET.value}"

    return header


# =============================================================================
# Marker Reference for Guidance Templates
# =============================================================================


def get_marker_reference_styled() -> str:
    """Get a styled marker reference for guidance templates.

    Returns:
        Multi-line string showing all markers with colors and emojis.
    """
    lines = ["**Capture Markers:**", ""]

    # Primary markers (most commonly used)
    primary = ["decisions", "learnings", "blockers", "progress"]
    lines.append("*Primary:*")
    for ns in primary:
        style = STYLES[ns]
        marker_name = ns
        if ns == "learnings":
            marker_name = "learned"
        elif ns == "decisions":
            marker_name = "decision"
        elif ns == "blockers":
            marker_name = "blocker"
        lines.append(f"  `[{style.emoji} {marker_name}]` - {style.description}")

    lines.append("")
    lines.append("*Additional:*")

    # Additional markers
    additional = ["research", "patterns", "reviews", "retrospective"]
    for ns in additional:
        style = STYLES[ns]
        lines.append(f"  `[{style.emoji} {ns}]` - {style.description}")

    return "\n".join(lines)
