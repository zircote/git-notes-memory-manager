"""Tests for git_notes_memory.hooks.namespace_parser module.

Tests the namespace-aware inline marker parser including:
- ParsedMarker dataclass
- NamespaceParser class
- parse_inline_marker convenience function
- Namespace validation and auto-detection
"""

from __future__ import annotations

import pytest

from git_notes_memory.hooks.namespace_parser import (
    SHORTHAND_MARKERS,
    VALID_NAMESPACES,
    NamespaceParser,
    ParsedMarker,
    parse_inline_marker,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def namespace_parser() -> NamespaceParser:
    """Create a NamespaceParser instance."""
    return NamespaceParser()


# =============================================================================
# VALID_NAMESPACES Tests
# =============================================================================


class TestValidNamespaces:
    """Test the VALID_NAMESPACES constant."""

    def test_expected_namespaces(self) -> None:
        """Test that all expected namespaces are valid."""
        expected = {
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
        assert frozenset(expected) == VALID_NAMESPACES

    def test_namespace_count(self) -> None:
        """Test that 10 namespaces are defined."""
        assert len(VALID_NAMESPACES) == 10


# =============================================================================
# ParsedMarker Tests
# =============================================================================


class TestParsedMarker:
    """Test the ParsedMarker dataclass."""

    def test_marker_with_explicit_namespace(self) -> None:
        """Test marker with explicit namespace."""
        marker = ParsedMarker(
            marker_type="remember",
            namespace="decisions",
            content="Use PostgreSQL",
            original_text="[remember:decisions] Use PostgreSQL",
        )
        assert marker.marker_type == "remember"
        assert marker.namespace == "decisions"
        assert marker.content == "Use PostgreSQL"
        assert not marker.uses_auto_detect

    def test_marker_without_namespace(self) -> None:
        """Test marker without namespace uses auto-detect."""
        marker = ParsedMarker(
            marker_type="capture",
            namespace=None,
            content="TIL about pytest",
            original_text="[capture] TIL about pytest",
        )
        assert marker.namespace is None
        assert marker.uses_auto_detect

    def test_default_namespace(self) -> None:
        """Test default namespace is learnings."""
        marker = ParsedMarker(
            marker_type="remember",
            namespace=None,
            content="Something",
            original_text="[remember] Something",
        )
        assert marker.default_namespace == "learnings"

    def test_marker_is_frozen(self) -> None:
        """Test that marker is immutable."""
        marker = ParsedMarker(
            marker_type="remember",
            namespace="decisions",
            content="test",
            original_text="test",
        )
        with pytest.raises(AttributeError):
            marker.namespace = "learnings"  # type: ignore[misc]


# =============================================================================
# NamespaceParser - Bracket Pattern Tests
# =============================================================================


class TestBracketPatternParsing:
    """Test [remember] and [capture] bracket patterns."""

    def test_remember_with_namespace(self, namespace_parser: NamespaceParser) -> None:
        """Test [remember:namespace] pattern."""
        result = namespace_parser.parse("[remember:decisions] Use PostgreSQL for DB")
        assert result is not None
        assert result.marker_type == "remember"
        assert result.namespace == "decisions"
        assert result.content == "Use PostgreSQL for DB"

    def test_remember_without_namespace(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test [remember] pattern defaults to learnings."""
        result = namespace_parser.parse("[remember] TIL about pytest fixtures")
        assert result is not None
        assert result.marker_type == "remember"
        assert result.namespace is None
        # resolve_namespace should return learnings for [remember]
        assert namespace_parser.resolve_namespace(result) == "learnings"

    def test_capture_with_namespace(self, namespace_parser: NamespaceParser) -> None:
        """Test [capture:namespace] pattern."""
        result = namespace_parser.parse("[capture:patterns] API error handling")
        assert result is not None
        assert result.marker_type == "capture"
        assert result.namespace == "patterns"

    def test_capture_without_namespace_auto_detects(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test [capture] pattern auto-detects from content."""
        result = namespace_parser.parse("[capture] I decided to use React")
        assert result is not None
        assert result.marker_type == "capture"
        assert result.namespace is None
        # Auto-detect should find "decided" -> decisions namespace
        resolved = namespace_parser.resolve_namespace(result)
        assert resolved == "decisions"

    def test_case_insensitive_marker(self, namespace_parser: NamespaceParser) -> None:
        """Test that marker types are case-insensitive."""
        result1 = namespace_parser.parse("[REMEMBER:decisions] Test")
        result2 = namespace_parser.parse("[Remember:decisions] Test")
        result3 = namespace_parser.parse("[remember:decisions] Test")

        assert result1 is not None
        assert result2 is not None
        assert result3 is not None
        assert result1.marker_type == "remember"
        assert result2.marker_type == "remember"
        assert result3.marker_type == "remember"

    def test_case_insensitive_namespace(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test that namespaces are case-insensitive."""
        result = namespace_parser.parse("[remember:DECISIONS] Test")
        assert result is not None
        assert result.namespace == "decisions"

    def test_invalid_namespace_falls_back(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test that invalid namespace falls back to auto-detect."""
        result = namespace_parser.parse("[remember:invalid_ns] Test content")
        assert result is not None
        assert result.namespace is None  # Invalid namespace -> None (auto-detect)


# =============================================================================
# NamespaceParser - At Pattern Tests
# =============================================================================


class TestAtPatternParsing:
    """Test @memory pattern parsing."""

    def test_memory_with_namespace(self, namespace_parser: NamespaceParser) -> None:
        """Test @memory:namespace pattern."""
        result = namespace_parser.parse("@memory:blockers CORS issue with frontend")
        assert result is not None
        assert result.marker_type == "memory"
        assert result.namespace == "blockers"
        assert result.content == "CORS issue with frontend"

    def test_memory_without_namespace(self, namespace_parser: NamespaceParser) -> None:
        """Test @memory pattern auto-detects."""
        result = namespace_parser.parse("@memory TIL something new")
        assert result is not None
        assert result.marker_type == "memory"
        assert result.namespace is None
        # Should auto-detect to learnings (TIL pattern)
        resolved = namespace_parser.resolve_namespace(result)
        assert resolved == "learnings"

    def test_memory_case_insensitive(self, namespace_parser: NamespaceParser) -> None:
        """Test @memory is case-insensitive."""
        result1 = namespace_parser.parse("@MEMORY:decisions Test")
        result2 = namespace_parser.parse("@Memory:decisions Test")

        assert result1 is not None
        assert result2 is not None
        assert result1.marker_type == "memory"
        assert result2.marker_type == "memory"

    def test_memory_requires_space_before_content(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test that @memory requires space before content."""
        # This should NOT match - no space between @memory and content
        result = namespace_parser.parse("@memorytest content")
        assert result is None


# =============================================================================
# NamespaceParser - No Match Tests
# =============================================================================


class TestNoMatchCases:
    """Test cases that should not match."""

    def test_no_marker(self, namespace_parser: NamespaceParser) -> None:
        """Test text without marker returns None."""
        result = namespace_parser.parse("Just regular text")
        assert result is None

    def test_empty_string(self, namespace_parser: NamespaceParser) -> None:
        """Test empty string returns None."""
        result = namespace_parser.parse("")
        assert result is None

    def test_whitespace_only(self, namespace_parser: NamespaceParser) -> None:
        """Test whitespace-only returns None."""
        result = namespace_parser.parse("   \n\t  ")
        assert result is None

    def test_marker_in_middle_of_text(self, namespace_parser: NamespaceParser) -> None:
        """Test marker not at start doesn't match."""
        result = namespace_parser.parse("Some text [remember] then marker")
        assert result is None

    def test_incomplete_bracket(self, namespace_parser: NamespaceParser) -> None:
        """Test incomplete bracket doesn't match."""
        result = namespace_parser.parse("[remember content without closing")
        assert result is None

    def test_unknown_marker_type(self, namespace_parser: NamespaceParser) -> None:
        """Test unknown marker type doesn't match."""
        result = namespace_parser.parse("[unknown:decisions] test")
        assert result is None


# =============================================================================
# NamespaceParser - Resolve Namespace Tests
# =============================================================================


class TestResolveNamespace:
    """Test namespace resolution logic."""

    def test_explicit_namespace_used(self, namespace_parser: NamespaceParser) -> None:
        """Test explicit namespace takes precedence."""
        result = namespace_parser.parse("[remember:decisions] test")
        assert result is not None
        resolved = namespace_parser.resolve_namespace(result)
        assert resolved == "decisions"

    def test_remember_without_ns_uses_learnings(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test [remember] without namespace uses learnings."""
        result = namespace_parser.parse("[remember] test")
        assert result is not None
        resolved = namespace_parser.resolve_namespace(result)
        assert resolved == "learnings"

    def test_capture_without_ns_auto_detects(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test [capture] without namespace auto-detects."""
        # Content has "decided" which should map to decisions
        result = namespace_parser.parse("[capture] I decided to use Python")
        assert result is not None
        resolved = namespace_parser.resolve_namespace(result)
        assert resolved == "decisions"

    def test_memory_without_ns_auto_detects(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test @memory without namespace auto-detects."""
        # Content has "blocked" which should map to blockers
        result = namespace_parser.parse("@memory Blocked by CORS issue")
        assert result is not None
        resolved = namespace_parser.resolve_namespace(result)
        assert resolved == "blockers"

    def test_auto_detect_no_signals_fallback(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test auto-detect with no signals falls back to learnings."""
        result = namespace_parser.parse("[capture] Some random text here")
        assert result is not None
        resolved = namespace_parser.resolve_namespace(result)
        # No clear signal -> learnings fallback
        assert resolved == "learnings"


# =============================================================================
# NamespaceParser - All Valid Namespaces Tests
# =============================================================================


class TestAllValidNamespaces:
    """Test parsing with all valid namespaces."""

    @pytest.mark.parametrize(
        "namespace",
        [
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
        ],
    )
    def test_all_namespaces_valid(
        self, namespace_parser: NamespaceParser, namespace: str
    ) -> None:
        """Test that all valid namespaces are accepted."""
        result = namespace_parser.parse(f"[remember:{namespace}] test content")
        assert result is not None
        assert result.namespace == namespace


# =============================================================================
# parse_inline_marker Convenience Function Tests
# =============================================================================


class TestParseInlineMarkerFunction:
    """Test the module-level convenience function."""

    def test_parses_valid_marker(self) -> None:
        """Test function parses valid markers."""
        result = parse_inline_marker("[remember:decisions] Use PostgreSQL")
        assert result is not None
        assert result.namespace == "decisions"

    def test_returns_none_for_no_marker(self) -> None:
        """Test function returns None for no marker."""
        result = parse_inline_marker("No marker here")
        assert result is None

    def test_handles_empty_string(self) -> None:
        """Test function handles empty string."""
        result = parse_inline_marker("")
        assert result is None


# =============================================================================
# Edge Cases and Content Preservation Tests
# =============================================================================


class TestContentPreservation:
    """Test that content is properly preserved after parsing."""

    def test_multiline_content(self, namespace_parser: NamespaceParser) -> None:
        """Test multiline content is preserved."""
        text = "[remember:decisions] First line\nSecond line\nThird line"
        result = namespace_parser.parse(text)
        assert result is not None
        assert "Second line" in result.content
        assert "Third line" in result.content

    def test_content_with_special_chars(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test content with special characters is preserved."""
        text = "[remember:decisions] Use `PostgreSQL` with <JSON> support & more"
        result = namespace_parser.parse(text)
        assert result is not None
        assert "`PostgreSQL`" in result.content
        assert "<JSON>" in result.content
        assert "&" in result.content

    def test_content_with_brackets(self, namespace_parser: NamespaceParser) -> None:
        """Test content containing brackets is preserved."""
        text = "[remember:learnings] Arrays use [index] notation"
        result = namespace_parser.parse(text)
        assert result is not None
        assert "[index]" in result.content

    def test_content_trimming(self, namespace_parser: NamespaceParser) -> None:
        """Test that content is trimmed of leading/trailing whitespace."""
        text = "[remember:decisions]   Lots of spaces   "
        result = namespace_parser.parse(text)
        assert result is not None
        assert result.content == "Lots of spaces"

    def test_original_text_preserved(self, namespace_parser: NamespaceParser) -> None:
        """Test original text is preserved in parsed result."""
        text = "[remember:decisions] Use PostgreSQL"
        result = namespace_parser.parse(text)
        assert result is not None
        assert result.original_text == text


# =============================================================================
# Shorthand Marker Tests
# =============================================================================


class TestShorthandMarkers:
    """Test shorthand marker patterns like [decision], [learned], etc."""

    def test_shorthand_markers_constant(self) -> None:
        """Test SHORTHAND_MARKERS has all expected entries."""
        expected = {
            "decision": "decisions",
            "learned": "learnings",
            "blocker": "blockers",
            "progress": "progress",
            "pattern": "patterns",
            "research": "research",
            "learning": "learnings",
            "block": "blockers",
            "insight": "learnings",
            "til": "learnings",
            "review": "reviews",
            "retro": "retrospective",
            "inception": "inception",
            "requirement": "elicitation",
        }
        assert expected == SHORTHAND_MARKERS

    def test_shorthand_namespaces_are_valid(self) -> None:
        """Test all shorthand namespaces are in VALID_NAMESPACES."""
        for namespace in SHORTHAND_MARKERS.values():
            assert namespace in VALID_NAMESPACES, f"{namespace} not in VALID_NAMESPACES"

    @pytest.mark.parametrize(
        "marker,expected_namespace",
        [
            ("decision", "decisions"),
            ("learned", "learnings"),
            ("blocker", "blockers"),
            ("progress", "progress"),
            ("pattern", "patterns"),
            ("research", "research"),
        ],
    )
    def test_primary_shorthand_markers(
        self, namespace_parser: NamespaceParser, marker: str, expected_namespace: str
    ) -> None:
        """Test primary shorthand markers map to correct namespaces."""
        result = namespace_parser.parse(f"[{marker}] Test content here")
        assert result is not None
        assert result.marker_type == marker
        assert result.namespace == expected_namespace
        assert result.content == "Test content here"

    @pytest.mark.parametrize(
        "marker,expected_namespace",
        [
            ("learning", "learnings"),
            ("block", "blockers"),
            ("insight", "learnings"),
            ("til", "learnings"),
            ("review", "reviews"),
            ("retro", "retrospective"),
            ("inception", "inception"),
            ("requirement", "elicitation"),
        ],
    )
    def test_shorthand_aliases(
        self, namespace_parser: NamespaceParser, marker: str, expected_namespace: str
    ) -> None:
        """Test shorthand aliases map to correct namespaces."""
        result = namespace_parser.parse(f"[{marker}] Alias test content")
        assert result is not None
        assert result.namespace == expected_namespace

    def test_shorthand_case_insensitive(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test shorthand markers are case-insensitive."""
        result1 = namespace_parser.parse("[DECISION] Test")
        result2 = namespace_parser.parse("[Decision] Test")
        result3 = namespace_parser.parse("[decision] Test")

        assert result1 is not None
        assert result2 is not None
        assert result3 is not None
        assert result1.namespace == "decisions"
        assert result2.namespace == "decisions"
        assert result3.namespace == "decisions"

    def test_shorthand_with_emoji_prefix(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test shorthand markers work with emoji prefix (as used in templates)."""
        result = namespace_parser.parse("⚖️ [decision] Use PostgreSQL for persistence")
        assert result is not None
        assert result.marker_type == "decision"
        assert result.namespace == "decisions"
        assert result.content == "Use PostgreSQL for persistence"

    def test_all_emoji_prefixed_markers(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test all marker types with their standard emoji prefixes."""
        cases = [
            ("⚖️ [decision] Decision content", "decisions"),
            ("💡 [learned] Learning content", "learnings"),
            ("🛑 [blocker] Blocker content", "blockers"),
            ("🚀 [progress] Progress content", "progress"),
        ]
        for text, expected_ns in cases:
            result = namespace_parser.parse(text)
            assert result is not None, f"Failed to parse: {text}"
            assert result.namespace == expected_ns, f"Wrong namespace for: {text}"

    def test_shorthand_preserves_content(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test that shorthand markers preserve full content."""
        text = "[decision] Use PostgreSQL for DB: ACID compliance, JSON support, team expertise"
        result = namespace_parser.parse(text)
        assert result is not None
        assert "ACID compliance" in result.content
        assert "JSON support" in result.content

    def test_shorthand_multiline_content(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test shorthand with multiline content."""
        text = "[learned] First line\nSecond line\nThird line"
        result = namespace_parser.parse(text)
        assert result is not None
        assert "Second line" in result.content
        assert "Third line" in result.content

    def test_unknown_shorthand_returns_none(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test unknown shorthand marker returns None."""
        result = namespace_parser.parse("[unknown] Some content")
        assert result is None

    def test_shorthand_not_uses_auto_detect(
        self, namespace_parser: NamespaceParser
    ) -> None:
        """Test shorthand markers have explicit namespace (no auto-detect)."""
        result = namespace_parser.parse("[decision] Content about learning")
        assert result is not None
        assert not result.uses_auto_detect
        assert result.namespace == "decisions"  # Explicit, not auto-detected


# =============================================================================
# Integration-like Tests
# =============================================================================


class TestRealWorldExamples:
    """Test with realistic usage examples."""

    def test_decision_capture(self, namespace_parser: NamespaceParser) -> None:
        """Test capturing a decision."""
        result = namespace_parser.parse(
            "[remember:decisions] Use PostgreSQL for persistence because of "
            "ACID compliance and JSON support"
        )
        assert result is not None
        assert result.namespace == "decisions"
        assert "PostgreSQL" in result.content
        assert "ACID compliance" in result.content

    def test_learning_capture(self, namespace_parser: NamespaceParser) -> None:
        """Test capturing a learning."""
        result = namespace_parser.parse(
            "[remember] TIL that pytest fixtures can have scope='module' "
            "for sharing state"
        )
        assert result is not None
        resolved = namespace_parser.resolve_namespace(result)
        assert resolved == "learnings"
        assert "pytest fixtures" in result.content

    def test_blocker_capture(self, namespace_parser: NamespaceParser) -> None:
        """Test capturing a blocker."""
        result = namespace_parser.parse(
            "@memory:blockers CORS configuration prevents frontend "
            "from calling backend API"
        )
        assert result is not None
        assert result.namespace == "blockers"
        assert "CORS" in result.content

    def test_pattern_capture(self, namespace_parser: NamespaceParser) -> None:
        """Test capturing a pattern."""
        result = namespace_parser.parse(
            "[capture:patterns] Use dependency injection for all services "
            "to enable testing"
        )
        assert result is not None
        assert result.namespace == "patterns"
        assert "dependency injection" in result.content
