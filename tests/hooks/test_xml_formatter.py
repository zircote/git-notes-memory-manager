"""Tests for XML formatting functionality.

TEST-H-004: Tests for xml_formatter.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from git_notes_memory.hooks.xml_formatter import XMLBuilder, escape_xml_text
from git_notes_memory.models import Memory

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_memory() -> Memory:
    """Create a sample memory for testing."""
    return Memory(
        id="decisions:abc1234:0",
        commit_sha="abc1234",
        namespace="decisions",
        timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        summary="Use SQLite for storage",
        content="After evaluating options, decided to use SQLite for storage.",
        tags=("database", "architecture"),
        relates_to=("patterns:def5678:0",),
        spec="my-project",
        phase="planning",
        domain="project",
    )


@pytest.fixture
def builder() -> XMLBuilder:
    """Create a basic XMLBuilder for testing."""
    return XMLBuilder("memory_context", {"project": "test-project"})


# =============================================================================
# XMLBuilder Initialization Tests
# =============================================================================


class TestXMLBuilderInit:
    """Tests for XMLBuilder initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with just root tag."""
        builder = XMLBuilder("root")
        assert builder.root_tag == "root"
        assert builder.attributes == {}
        assert "root" in builder._elements

    def test_init_with_attributes(self) -> None:
        """Test initialization with attributes."""
        builder = XMLBuilder("context", {"project": "test", "version": "1.0"})
        assert builder.attributes == {"project": "test", "version": "1.0"}

    def test_root_element_created(self) -> None:
        """Test that root element is properly created."""
        builder = XMLBuilder("memory_context", {"timestamp": "2024-01-15"})
        xml = builder.to_string()
        assert "<memory_context" in xml
        assert 'timestamp="2024-01-15"' in xml


# =============================================================================
# add_element Tests
# =============================================================================


class TestAddElement:
    """Tests for the add_element method."""

    def test_add_child_to_root(self, builder: XMLBuilder) -> None:
        """Test adding a child element to root."""
        key = builder.add_element("root", "section")
        assert key == "section"
        assert "section" in builder._elements

    def test_add_element_with_text(self, builder: XMLBuilder) -> None:
        """Test adding element with text content."""
        builder.add_element("root", "message", text="Hello, World!")
        xml = builder.to_string()
        assert "<message>Hello, World!</message>" in xml

    def test_add_element_with_attributes(self, builder: XMLBuilder) -> None:
        """Test adding element with attributes."""
        builder.add_element("root", "item", id="123", type="test")
        xml = builder.to_string()
        assert "<item" in xml
        assert 'id="123"' in xml
        assert 'type="test"' in xml

    def test_add_nested_elements(self, builder: XMLBuilder) -> None:
        """Test adding nested elements."""
        section_key = builder.add_element("root", "section")
        builder.add_element(section_key, "item", text="Item 1")
        xml = builder.to_string()
        assert "<section>" in xml
        assert "<item>Item 1</item>" in xml

    def test_duplicate_tag_handling(self, builder: XMLBuilder) -> None:
        """Test that duplicate tags get unique keys."""
        key1 = builder.add_element("root", "item")
        key2 = builder.add_element("root", "item")
        key3 = builder.add_element("root", "item")

        assert key1 == "item"
        assert key2 == "item_1"
        assert key3 == "item_2"

    def test_invalid_parent_raises(self, builder: XMLBuilder) -> None:
        """Test that invalid parent raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            builder.add_element("nonexistent", "child")
        assert "nonexistent" in str(exc_info.value)


# =============================================================================
# add_memory_element Tests
# =============================================================================


class TestAddMemoryElement:
    """Tests for the add_memory_element method."""

    def test_add_memory_basic(self, builder: XMLBuilder, sample_memory: Memory) -> None:
        """Test adding a memory element with basic attributes."""
        section = builder.add_element("root", "memories")
        key = builder.add_memory_element(section, sample_memory)

        assert "memory_decisions_abc1234_0" in key
        xml = builder.to_string()
        assert "<memory" in xml
        assert 'id="decisions:abc1234:0"' in xml
        assert 'namespace="decisions"' in xml

    def test_memory_includes_summary(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test that summary is always included."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory)

        xml = builder.to_string()
        assert "<summary>Use SQLite for storage</summary>" in xml

    def test_memory_includes_tags(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test that tags are included when present."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory)

        xml = builder.to_string()
        assert "<tags>database, architecture</tags>" in xml

    def test_memory_includes_relations(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test that relations are included when present."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory)

        xml = builder.to_string()
        assert "<relates_to>patterns:def5678:0</relates_to>" in xml

    def test_memory_full_hydration(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test that content is included for full hydration."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory, hydration="full")

        xml = builder.to_string()
        assert "<content>" in xml
        assert "After evaluating options" in xml

    def test_memory_summary_hydration_no_content(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test that content is not included for summary hydration."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory, hydration="summary")

        xml = builder.to_string()
        assert "<content>" not in xml

    def test_memory_relevance_score(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test that relevance score is included."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory, relevance=0.75)

        xml = builder.to_string()
        assert 'relevance="0.75"' in xml

    def test_memory_auto_expand_high_relevance(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test auto_expand is added for high relevance."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory, relevance=0.90)

        xml = builder.to_string()
        assert 'auto_expand="true"' in xml

    def test_memory_no_auto_expand_low_relevance(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test auto_expand is not added for low relevance."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory, relevance=0.60)

        xml = builder.to_string()
        assert "auto_expand" not in xml

    def test_memory_spec_and_phase(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test that spec and phase are included."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory)

        xml = builder.to_string()
        assert 'spec="my-project"' in xml
        assert 'phase="planning"' in xml

    def test_memory_domain_attribute(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test that domain attribute is included."""
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, sample_memory)

        xml = builder.to_string()
        assert 'domain="project"' in xml

    def test_invalid_parent_raises(
        self, builder: XMLBuilder, sample_memory: Memory
    ) -> None:
        """Test that invalid parent raises KeyError."""
        with pytest.raises(KeyError):
            builder.add_memory_element("nonexistent", sample_memory)


# =============================================================================
# add_instruction Tests
# =============================================================================


class TestAddInstruction:
    """Tests for the add_instruction method."""

    def test_add_instruction(self, builder: XMLBuilder) -> None:
        """Test adding an instruction element."""
        builder.add_instruction("root", "Reference memories when relevant")
        xml = builder.to_string()
        assert "<instruction>Reference memories when relevant</instruction>" in xml


# =============================================================================
# add_section Tests
# =============================================================================


class TestAddSection:
    """Tests for the add_section method."""

    def test_add_section_basic(self, builder: XMLBuilder) -> None:
        """Test adding a basic section."""
        key = builder.add_section("root", "working_memory")
        assert key == "working_memory"
        xml = builder.to_string()
        assert "<working_memory" in xml

    def test_add_section_with_title(self, builder: XMLBuilder) -> None:
        """Test adding a section with title."""
        builder.add_section("root", "recent_decisions", title="Recent Decisions")
        xml = builder.to_string()
        assert 'title="Recent Decisions"' in xml


# =============================================================================
# to_string Tests
# =============================================================================


class TestToString:
    """Tests for the to_string method."""

    def test_to_string_pretty(self, builder: XMLBuilder) -> None:
        """Test pretty-printed output."""
        builder.add_element("root", "child", text="Hello")
        xml = builder.to_string(pretty=True)
        # Pretty printing adds newlines
        assert "\n" in xml

    def test_to_string_compact(self, builder: XMLBuilder) -> None:
        """Test compact output."""
        builder.add_element("root", "child", text="Hello")
        xml = builder.to_string(pretty=False)
        # Compact is on one line
        lines = xml.strip().split("\n")
        assert len(lines) == 1


# =============================================================================
# clear Tests
# =============================================================================


class TestClear:
    """Tests for the clear method."""

    def test_clear_removes_elements(self, builder: XMLBuilder) -> None:
        """Test that clear removes all added elements."""
        builder.add_element("root", "section")
        builder.add_element("root", "another")
        assert len(builder._elements) > 1

        builder.clear()
        assert len(builder._elements) == 1
        assert "root" in builder._elements

    def test_clear_preserves_root_attributes(self) -> None:
        """Test that clear preserves root attributes."""
        builder = XMLBuilder("context", {"project": "test"})
        builder.add_element("root", "child")
        builder.clear()

        xml = builder.to_string()
        assert 'project="test"' in xml


# =============================================================================
# escape_xml_text Tests
# =============================================================================


class TestEscapeXmlText:
    """Tests for the escape_xml_text function."""

    def test_escape_ampersand(self) -> None:
        """Test escaping ampersand."""
        assert escape_xml_text("A & B") == "A &amp; B"

    def test_escape_less_than(self) -> None:
        """Test escaping less than."""
        assert escape_xml_text("a < b") == "a &lt; b"

    def test_escape_greater_than(self) -> None:
        """Test escaping greater than."""
        assert escape_xml_text("a > b") == "a &gt; b"

    def test_escape_double_quote(self) -> None:
        """Test escaping double quotes."""
        assert escape_xml_text('say "hello"') == "say &quot;hello&quot;"

    def test_escape_single_quote(self) -> None:
        """Test escaping single quotes."""
        assert escape_xml_text("it's") == "it&apos;s"

    def test_escape_multiple(self) -> None:
        """Test escaping multiple special characters."""
        text = '<tag attr="val">A & B</tag>'
        expected = "&lt;tag attr=&quot;val&quot;&gt;A &amp; B&lt;/tag&gt;"
        assert escape_xml_text(text) == expected

    def test_no_escape_needed(self) -> None:
        """Test text without special characters."""
        assert escape_xml_text("Hello World") == "Hello World"


# =============================================================================
# Integration Tests
# =============================================================================


class TestXMLBuilderIntegration:
    """Integration tests for complete XML document building."""

    def test_full_memory_context(self, sample_memory: Memory) -> None:
        """Test building a complete memory context document."""
        builder = XMLBuilder(
            "memory_context",
            {"project": "test-project", "timestamp": "2024-01-15"},
        )

        # Add semantic context section
        semantic = builder.add_section("root", "semantic_context")
        decisions = builder.add_section(semantic, "decisions", title="Decisions")
        builder.add_memory_element(decisions, sample_memory, relevance=0.85)

        # Add instructions
        builder.add_instruction("root", "Reference memories when relevant")

        xml = builder.to_string()

        # Verify structure
        assert "<memory_context" in xml
        assert "<semantic_context" in xml
        assert '<decisions title="Decisions"' in xml
        assert "<memory" in xml
        assert "<instruction>" in xml

    def test_memory_without_optional_fields(self) -> None:
        """Test memory without optional fields."""
        memory = Memory(
            id="test:abc:0",
            commit_sha="abc",
            namespace="test",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            summary="Simple memory",
            content="",  # Empty content to test omission
            tags=(),
            relates_to=(),
            spec=None,
            phase=None,
        )

        builder = XMLBuilder("context")
        section = builder.add_element("root", "memories")
        builder.add_memory_element(section, memory)

        xml = builder.to_string()

        # Should still have required elements
        assert "<memory" in xml
        assert "<summary>Simple memory</summary>" in xml
        # Should not have optional elements
        assert "<tags>" not in xml
        assert "<relates_to>" not in xml
        assert "<content>" not in xml
