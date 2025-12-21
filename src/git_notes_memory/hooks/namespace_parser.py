"""Namespace-aware inline marker parser.

This module provides parsing for inline memory capture markers that support
namespace specification. It extends the existing marker detection to allow
users to specify which namespace their captured content should go to.

Supported Marker Syntaxes:

Inline Markers:
- [remember] content          -> Capture to 'learnings' (default)
- [remember:decisions] content -> Capture to 'decisions' namespace
- [capture] content           -> Auto-detect namespace from content
- [capture:patterns] content  -> Capture to 'patterns' namespace
- @memory content             -> Auto-detect namespace from content
- @memory:blockers content    -> Capture to 'blockers' namespace

Shorthand Markers (direct namespace):
- [decision] content          -> Capture to 'decisions' namespace
- [learned] content           -> Capture to 'learnings' namespace
- [blocker] content           -> Capture to 'blockers' namespace
- [progress] content          -> Capture to 'progress' namespace
- [pattern] content           -> Capture to 'patterns' namespace
- [research] content          -> Capture to 'research' namespace

Markdown Block Markers (for detailed captures):
- :::decision Title here      -> Multi-line capture to 'decisions'
  ## Context
  Details...
  :::
- :::decision content:::      -> Single-line block capture

Invalid namespaces fall back to auto-detection (namespace=None).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from git_notes_memory.hooks.signal_detector import SignalDetector

__all__ = ["ParsedMarker", "NamespaceParser", "parse_inline_marker"]

# Valid memory namespaces (from git-notes-memory storage)
VALID_NAMESPACES: frozenset[str] = frozenset(
    {
        "inception",
        "elicitation",
        "research",
        "decisions",
        "progress",
        "blockers",
        "reviews",
        "learnings",
        "retrospective",
        "patterns",
    }
)

# Shorthand marker mappings: marker keyword -> namespace
# These allow simpler syntax like [decision] instead of [remember:decisions]
SHORTHAND_MARKERS: dict[str, str] = {
    # Primary shorthand markers
    "decision": "decisions",
    "learned": "learnings",
    "blocker": "blockers",
    "progress": "progress",
    "pattern": "patterns",
    "research": "research",
    # Additional shorthand aliases
    "learning": "learnings",
    "block": "blockers",
    "insight": "learnings",
    "til": "learnings",
    "review": "reviews",
    "retro": "retrospective",
    "inception": "inception",
    "requirement": "elicitation",
}


@dataclass(frozen=True)
class ParsedMarker:
    """Result of parsing an inline marker from text.

    Attributes:
        marker_type: The marker type found ("remember", "capture", or "memory")
        namespace: The explicit namespace if specified, or None for auto-detect
        content: The content following the marker (trimmed)
        original_text: The full original text that was parsed
    """

    marker_type: str
    namespace: str | None
    content: str
    original_text: str

    @property
    def uses_auto_detect(self) -> bool:
        """Whether this marker should auto-detect namespace from content."""
        # Auto-detect when namespace is None (not specified)
        # Also auto-detect for "capture" markers without namespace
        return self.namespace is None

    @property
    def default_namespace(self) -> str:
        """Get the default namespace if no explicit or auto-detected one."""
        return "learnings"


class NamespaceParser:
    """Parser for namespace-aware inline markers.

    This parser extracts inline capture markers from text and parses them
    for explicit namespace hints. It supports the following patterns:

    - `[remember]` - Capture to learnings (no auto-detect)
    - `[remember:namespace]` - Capture to specified namespace
    - `[capture]` - Auto-detect namespace from content signals
    - `[capture:namespace]` - Capture to specified namespace
    - `@memory` - Auto-detect namespace from content signals
    - `@memory:namespace` - Capture to specified namespace

    Example::

        parser = NamespaceParser()
        result = parser.parse("[remember:decisions] Use PostgreSQL for DB")
        if result:
            print(result.namespace)  # "decisions"
            print(result.content)  # "Use PostgreSQL for DB"
    """

    # Regex patterns for marker detection
    # Group 1: marker type (remember/capture)
    # Group 2: optional namespace (after colon)
    # Group 3: content (rest of text after marker)
    _BRACKET_PATTERN = re.compile(
        r"^\[(remember|capture)(?::(\w+))?\]\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    )

    # @memory pattern
    # Group 1: optional namespace (after colon)
    # Group 2: content (rest of text after marker)
    _AT_PATTERN = re.compile(
        r"^@memory(?::(\w+))?\s+(.+)$",
        re.IGNORECASE | re.DOTALL,
    )

    # Shorthand marker pattern: [decision], [learned], [blocker], [progress], etc.
    # Allows optional emoji prefix (e.g., "⚖️ [decision]" or just "[decision]")
    # Group 1: shorthand marker keyword
    # Group 2: content (rest of text after marker)
    _SHORTHAND_PATTERN = re.compile(
        r"^(?:[^\[\]]*?)?\[(\w+)\]\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    )

    # Markdown block pattern: :::namespace content :::
    # Supports both single-line title and multi-line content
    # Group 1: namespace (required)
    # Group 2: optional title on same line
    # Group 3: content between ::: markers (may be empty if title only)
    _MARKDOWN_BLOCK_PATTERN = re.compile(
        r"^:::(\w+)(?:\s+(.+?))??\n(.*?)^:::$",
        re.MULTILINE | re.DOTALL,
    )

    # Alternative: Single-line markdown block :::namespace content:::
    # Group 1: namespace
    # Group 2: content
    _MARKDOWN_INLINE_PATTERN = re.compile(
        r"^:::(\w+)\s+(.+?):::$",
        re.DOTALL,
    )

    def __init__(
        self,
        *,
        signal_detector: SignalDetector | None = None,
    ) -> None:
        """Initialize the namespace parser.

        Args:
            signal_detector: Optional SignalDetector for namespace auto-detection.
                If not provided, one will be created lazily when needed.
        """
        self._signal_detector = signal_detector

    def _get_signal_detector(self) -> SignalDetector:
        """Get or create the SignalDetector instance."""
        if self._signal_detector is None:
            from git_notes_memory.hooks.signal_detector import SignalDetector

            self._signal_detector = SignalDetector()
        return self._signal_detector

    def parse(self, text: str) -> ParsedMarker | None:
        """Parse text for an inline marker with optional namespace.

        Args:
            text: Text to parse (typically a user prompt line)

        Returns:
            ParsedMarker if a marker was found, None otherwise.

        Example::

            # With explicit namespace
            result = parser.parse("[remember:decisions] Use PostgreSQL")
            # result.namespace = "decisions"
            # result.content = "Use PostgreSQL"

            # Without namespace (default to learnings for [remember])
            result = parser.parse("[remember] TIL about pytest fixtures")
            # result.namespace = None (but marker_type="remember" means learnings)
            # result.content = "TIL about pytest fixtures"

            # Auto-detect with [capture]
            result = parser.parse("[capture] I decided to use React")
            # result.namespace = None (auto-detect)
            # result.content = "I decided to use React"
        """
        text = text.strip()
        if not text:
            return None

        # Try bracket pattern first: [remember:ns] or [capture:ns]
        match = self._BRACKET_PATTERN.match(text)
        if match:
            marker_type = match.group(1).lower()
            raw_namespace = match.group(2)
            content = match.group(3).strip()

            namespace = self._validate_namespace(raw_namespace)

            return ParsedMarker(
                marker_type=marker_type,
                namespace=namespace,
                content=content,
                original_text=text,
            )

        # Try @memory pattern
        match = self._AT_PATTERN.match(text)
        if match:
            raw_namespace = match.group(1)
            content = match.group(2).strip()

            namespace = self._validate_namespace(raw_namespace)

            return ParsedMarker(
                marker_type="memory",
                namespace=namespace,
                content=content,
                original_text=text,
            )

        # Try shorthand pattern: [decision], [learned], [blocker], [progress], etc.
        match = self._SHORTHAND_PATTERN.match(text)
        if match:
            shorthand_keyword = match.group(1).lower()
            content = match.group(2).strip()

            # Check if this is a valid shorthand marker
            if shorthand_keyword in SHORTHAND_MARKERS:
                namespace = SHORTHAND_MARKERS[shorthand_keyword]
                return ParsedMarker(
                    marker_type=shorthand_keyword,
                    namespace=namespace,
                    content=content,
                    original_text=text,
                )

        # Try markdown block pattern: :::namespace\ncontent\n:::
        match = self._MARKDOWN_BLOCK_PATTERN.search(text)
        if match:
            raw_namespace = match.group(1).lower()
            title = (match.group(2) or "").strip()
            body = (match.group(3) or "").strip()

            # Combine title and body for content
            if title and body:
                content = f"{title}\n\n{body}"
            elif title:
                content = title
            else:
                content = body

            # Validate namespace - check both VALID_NAMESPACES and SHORTHAND_MARKERS
            namespace = self._validate_namespace(raw_namespace)
            if namespace is None and raw_namespace in SHORTHAND_MARKERS:
                namespace = SHORTHAND_MARKERS[raw_namespace]

            if namespace:
                return ParsedMarker(
                    marker_type="block",
                    namespace=namespace,
                    content=content,
                    original_text=text,
                )

        # Try inline markdown block: :::namespace content:::
        match = self._MARKDOWN_INLINE_PATTERN.match(text)
        if match:
            raw_namespace = match.group(1).lower()
            content = match.group(2).strip()

            namespace = self._validate_namespace(raw_namespace)
            if namespace is None and raw_namespace in SHORTHAND_MARKERS:
                namespace = SHORTHAND_MARKERS[raw_namespace]

            if namespace:
                return ParsedMarker(
                    marker_type="block",
                    namespace=namespace,
                    content=content,
                    original_text=text,
                )

        return None

    def _validate_namespace(self, namespace: str | None) -> str | None:
        """Validate a namespace against known valid namespaces.

        Args:
            namespace: The namespace string to validate (may be None)

        Returns:
            The validated namespace (lowercased) if valid, None otherwise.
            None indicates auto-detection should be used.
        """
        if namespace is None:
            return None

        normalized = namespace.lower()
        if normalized in VALID_NAMESPACES:
            return normalized

        # Invalid namespace - fall back to auto-detect
        return None

    def resolve_namespace(self, marker: ParsedMarker) -> str:
        """Resolve the final namespace for a parsed marker.

        For markers with explicit namespace, returns that namespace.
        For markers without namespace:
        - [remember] -> "learnings" (no auto-detect)
        - [capture] or @memory -> auto-detect from content

        Args:
            marker: The parsed marker to resolve namespace for.

        Returns:
            The resolved namespace string.
        """
        # Explicit namespace takes precedence
        if marker.namespace is not None:
            return marker.namespace

        # [remember] without namespace defaults to learnings
        if marker.marker_type == "remember":
            return "learnings"

        # [capture] and @memory use auto-detection
        return self._auto_detect_namespace(marker.content)

    def _auto_detect_namespace(self, content: str) -> str:
        """Auto-detect namespace from content using signal detection.

        Args:
            content: The content to analyze for signals.

        Returns:
            Detected namespace, or "learnings" as fallback.
        """
        detector = self._get_signal_detector()
        signals = detector.detect(content)

        if signals:
            # Use the namespace from the highest-confidence signal
            best_signal = max(signals, key=lambda s: s.confidence)
            return best_signal.suggested_namespace

        # Default fallback
        return "learnings"


def parse_inline_marker(text: str) -> ParsedMarker | None:
    """Convenience function to parse an inline marker.

    This is a module-level function that creates a NamespaceParser
    and parses the text. For repeated parsing, prefer creating
    a NamespaceParser instance directly.

    Args:
        text: Text to parse for inline markers.

    Returns:
        ParsedMarker if found, None otherwise.

    Example::

        result = parse_inline_marker("[remember:decisions] Use PostgreSQL")
        if result:
            print(f"Namespace: {result.namespace}")
            print(f"Content: {result.content}")
    """
    parser = NamespaceParser()
    return parser.parse(text)
