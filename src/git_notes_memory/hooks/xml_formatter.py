"""XML formatting utilities for hook output.

This module provides the XMLBuilder class for constructing XML documents
used in hook responses. It handles proper escaping and formatting for
memory context injection.

The XML format follows Claude Code's expectations for additionalContext,
using semantic XML elements that Claude can understand and act upon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from git_notes_memory.models import Memory

__all__ = ["XMLBuilder"]


@dataclass
class XMLBuilder:
    """Builder for constructing XML documents for hook output.

    This class provides a fluent interface for building XML documents
    that will be injected into Claude's context. It handles proper
    escaping and formatting automatically.

    Attributes:
        root_tag: The root element tag name.
        attributes: Attributes for the root element.

    Example::

        builder = XMLBuilder("memory_context", {"project": "my-project"})
        builder.add_element("working_memory", "memories")
        builder.add_memory_element("memories", memory, hydration="summary")
        xml_str = builder.to_string()
    """

    root_tag: str
    attributes: dict[str, str] = field(default_factory=dict)
    _root: ET.Element = field(init=False, repr=False)
    _elements: dict[str, ET.Element] = field(
        init=False, repr=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        """Initialize the root element after dataclass initialization."""
        self._root = ET.Element(self.root_tag, self.attributes)
        self._elements = {"root": self._root}

    def add_element(
        self,
        parent: str,
        tag: str,
        text: str | None = None,
        **attrs: str,
    ) -> str:
        """Add a child element to a parent.

        Args:
            parent: Key of the parent element ("root" for root element).
            tag: Tag name for the new element.
            text: Optional text content for the element.
            **attrs: Attributes for the new element.

        Returns:
            Key to reference this element (same as tag).

        Raises:
            KeyError: If parent element doesn't exist.
        """
        if parent not in self._elements:
            msg = f"Parent element '{parent}' not found"
            raise KeyError(msg)

        parent_elem = self._elements[parent]
        elem = ET.SubElement(parent_elem, tag, attrs)
        if text is not None:
            elem.text = text

        # Use tag as key, but handle duplicates
        key = tag
        counter = 1
        while key in self._elements:
            key = f"{tag}_{counter}"
            counter += 1
        self._elements[key] = elem

        return key

    def add_memory_element(
        self,
        parent: str,
        memory: Memory,
        hydration: str = "summary",
        *,
        relevance: float | None = None,
        auto_expand_threshold: float = 0.85,
    ) -> str:
        """Add a memory-specific element with proper formatting.

        Creates a structured element for a Memory object that includes
        relevant metadata based on the hydration level.

        Args:
            parent: Key of the parent element.
            memory: Memory object to add.
            hydration: Hydration level ("summary", "full", "files").
            relevance: Optional relevance score (0.0-1.0) for this memory.
            auto_expand_threshold: Threshold above which auto_expand hint is added.

        Returns:
            Key to reference this element.
        """
        if parent not in self._elements:
            msg = f"Parent element '{parent}' not found"
            raise KeyError(msg)

        parent_elem = self._elements[parent]

        # Create memory element with core attributes
        attrs = {
            "id": memory.id,
            "namespace": memory.namespace,
            "timestamp": memory.timestamp.isoformat(),
        }
        if memory.spec:
            attrs["spec"] = memory.spec
        if memory.phase:
            attrs["phase"] = memory.phase

        # Add relevance and auto-expand hints
        if relevance is not None:
            attrs["relevance"] = f"{relevance:.2f}"
            if relevance >= auto_expand_threshold:
                attrs["auto_expand"] = "true"

        mem_elem = ET.SubElement(parent_elem, "memory", attrs)

        # Add summary (always included)
        summary_elem = ET.SubElement(mem_elem, "summary")
        summary_elem.text = memory.summary

        # Add tags if present
        if memory.tags:
            tags_elem = ET.SubElement(mem_elem, "tags")
            tags_elem.text = ", ".join(memory.tags)

        # Add full content for higher hydration levels
        if hydration in ("full", "files") and memory.content:
            content_elem = ET.SubElement(mem_elem, "content")
            content_elem.text = memory.content

        # Add relations if present
        if memory.relates_to:
            relations_elem = ET.SubElement(mem_elem, "relates_to")
            relations_elem.text = ", ".join(memory.relates_to)

        # Generate unique key
        key = f"memory_{memory.id.replace(':', '_')}"
        counter = 1
        while key in self._elements:
            key = f"{key}_{counter}"
            counter += 1
        self._elements[key] = mem_elem

        return key

    def add_instruction(self, parent: str, text: str) -> str:
        """Add an instruction element for Claude.

        Instructions are special elements that guide Claude's behavior
        when processing the memory context.

        Args:
            parent: Key of the parent element.
            text: Instruction text.

        Returns:
            Key to reference this element.
        """
        return self.add_element(parent, "instruction", text=text)

    def add_section(
        self,
        parent: str,
        name: str,
        title: str | None = None,
    ) -> str:
        """Add a named section element.

        Sections group related content under a common header.

        Args:
            parent: Key of the parent element.
            name: Section name (used as tag).
            title: Optional title attribute.

        Returns:
            Key to reference this element.
        """
        attrs = {}
        if title:
            attrs["title"] = title
        return self.add_element(parent, name, **attrs)

    def to_string(self, pretty: bool = True) -> str:
        """Serialize the XML tree to a string.

        Args:
            pretty: If True, format with indentation (default True).

        Returns:
            XML string representation.
        """
        if pretty:
            ET.indent(self._root)

        return ET.tostring(self._root, encoding="unicode")

    def clear(self) -> None:
        """Clear all elements and reset to initial state."""
        self._root = ET.Element(self.root_tag, self.attributes)
        self._elements = {"root": self._root}


def escape_xml_text(text: str) -> str:
    """Escape special characters for XML text content.

    This is a utility function for cases where manual escaping is needed.
    The XMLBuilder handles escaping automatically, so this is mainly for
    edge cases or testing.

    Args:
        text: Raw text to escape.

    Returns:
        XML-safe text string.
    """
    # ElementTree handles this automatically, but expose for manual use
    replacements = [
        ("&", "&amp;"),
        ("<", "&lt;"),
        (">", "&gt;"),
        ('"', "&quot;"),
        ("'", "&apos;"),
    ]
    result = text
    for old, new in replacements:
        result = result.replace(old, new)
    return result
