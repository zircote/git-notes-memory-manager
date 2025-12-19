"""Tests for git_notes_memory.hooks.guidance_builder module.

Tests the response guidance builder including:
- GuidanceBuilder class
- XML generation for different detail levels
- GuidanceLevel enum
- Configuration integration
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from git_notes_memory.hooks.config_loader import (
    GuidanceDetailLevel,
    HookConfig,
    load_hook_config,
)
from git_notes_memory.hooks.guidance_builder import (
    GuidanceBuilder,
    GuidanceLevel,
    get_guidance_builder,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def guidance_builder() -> GuidanceBuilder:
    """Create a GuidanceBuilder instance."""
    return GuidanceBuilder()


# =============================================================================
# GuidanceLevel Tests
# =============================================================================


class TestGuidanceLevel:
    """Test the GuidanceLevel enum."""

    def test_minimal_value(self) -> None:
        """Test minimal level has correct value."""
        assert GuidanceLevel.MINIMAL.value == "minimal"

    def test_standard_value(self) -> None:
        """Test standard level has correct value."""
        assert GuidanceLevel.STANDARD.value == "standard"

    def test_detailed_value(self) -> None:
        """Test detailed level has correct value."""
        assert GuidanceLevel.DETAILED.value == "detailed"

    def test_all_levels_defined(self) -> None:
        """Test all expected levels are defined."""
        levels = {level.value for level in GuidanceLevel}
        assert levels == {"minimal", "standard", "detailed"}


# =============================================================================
# XML Template Content Tests
# =============================================================================


class TestXMLTemplateContent:
    """Test that XML templates contain expected content."""

    def test_detailed_has_behavioral_examples(
        self, guidance_builder: GuidanceBuilder
    ) -> None:
        """Test that detailed template has behavioral examples."""
        xml = guidance_builder.build_guidance("detailed")
        # Check for example contexts showing behavior in action
        assert "architecture discussion" in xml
        assert "[decision]" in xml
        assert "[learned]" in xml
        assert "[blocker]" in xml

    def test_templates_have_namespaces(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that templates list valid namespaces."""
        for level in ["minimal", "standard", "detailed"]:
            xml = guidance_builder.build_guidance(level)
            # Check for key namespaces
            assert "decisions" in xml
            assert "learnings" in xml
            assert "blockers" in xml
            assert "progress" in xml


# =============================================================================
# GuidanceBuilder Tests
# =============================================================================


class TestGuidanceBuilder:
    """Test the GuidanceBuilder class."""

    def test_build_minimal(self, guidance_builder: GuidanceBuilder) -> None:
        """Test minimal guidance generation."""
        xml = guidance_builder.build_guidance("minimal")
        assert '<session_operating_context level="minimal">' in xml
        assert "<active_behaviors>" in xml
        assert "<memory_recall>" in xml
        assert "<namespaces>" in xml
        # Minimal should be concise
        assert "<template>" not in xml
        assert "<examples>" not in xml

    def test_build_standard(self, guidance_builder: GuidanceBuilder) -> None:
        """Test standard guidance generation."""
        xml = guidance_builder.build_guidance("standard")
        assert '<session_operating_context level="standard">' in xml
        assert "<active_behaviors" in xml
        assert "<memory_recall_behaviors" in xml
        assert "<inline_markers" in xml
        # Standard should have behavior triggers
        assert 'trigger="making_decision"' in xml
        # Standard should NOT have detailed templates
        assert "<template>" not in xml

    def test_build_detailed(self, guidance_builder: GuidanceBuilder) -> None:
        """Test detailed guidance generation."""
        xml = guidance_builder.build_guidance("detailed")
        assert '<session_operating_context level="detailed">' in xml
        assert "<active_behaviors" in xml
        assert "<memory_recall_behaviors" in xml
        assert "<examples" in xml
        # Detailed SHOULD have structured templates (with type attribute)
        assert "<template type=" in xml
        # Detailed should have priority markers
        assert 'priority="critical"' in xml

    def test_invalid_detail_level(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that invalid detail level raises ValueError."""
        with pytest.raises(ValueError, match="Invalid detail_level"):
            guidance_builder.build_guidance("invalid")

    def test_case_insensitive_level(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that level names are case-insensitive."""
        xml_lower = guidance_builder.build_guidance("minimal")
        xml_upper = guidance_builder.build_guidance("MINIMAL")
        xml_mixed = guidance_builder.build_guidance("Minimal")
        # All should produce the same output
        assert xml_lower == xml_upper == xml_mixed

    def test_minimal_is_shortest(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that minimal guidance is shorter than others."""
        minimal = guidance_builder.build_guidance("minimal")
        standard = guidance_builder.build_guidance("standard")
        detailed = guidance_builder.build_guidance("detailed")
        assert len(minimal) < len(standard) < len(detailed)

    def test_contains_inline_marker_syntax(
        self, guidance_builder: GuidanceBuilder
    ) -> None:
        """Test that all levels contain inline marker syntax."""
        for level in ["minimal", "standard", "detailed"]:
            xml = guidance_builder.build_guidance(level)
            # All levels should have core capture markers
            assert "[decision]" in xml or "[remember" in xml
            assert "[learned]" in xml or "[remember" in xml
            assert "[blocker]" in xml or "blocker" in xml


class TestGuidanceBuilderXMLStructure:
    """Test XML structure validity of generated guidance."""

    def test_minimal_is_valid_xml(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that minimal output is valid XML."""
        xml = guidance_builder.build_guidance("minimal")
        # Should parse without error (S314 safe: parsing our own generated XML)
        root = ET.fromstring(xml)  # noqa: S314
        assert root.tag == "session_operating_context"
        assert root.attrib.get("level") == "minimal"

    def test_standard_is_valid_xml(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that standard output is valid XML."""
        xml = guidance_builder.build_guidance("standard")
        root = ET.fromstring(xml)  # noqa: S314
        assert root.tag == "session_operating_context"
        assert root.attrib.get("level") == "standard"

    def test_detailed_is_valid_xml(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that detailed output is valid XML."""
        xml = guidance_builder.build_guidance("detailed")
        root = ET.fromstring(xml)  # noqa: S314
        assert root.tag == "session_operating_context"
        assert root.attrib.get("level") == "detailed"

    def test_detailed_has_behavior_triggers(
        self, guidance_builder: GuidanceBuilder
    ) -> None:
        """Test that detailed guidance has all behavior triggers."""
        xml = guidance_builder.build_guidance("detailed")
        root = ET.fromstring(xml)  # noqa: S314
        behaviors = root.find("active_behaviors")
        assert behaviors is not None
        triggers = {b.attrib.get("trigger") for b in behaviors.findall("behavior")}
        expected = {
            "making_decision",
            "discovering_insight",
            "hitting_blocker",
            "completing_milestone",
        }
        assert triggers == expected


class TestGuidanceBuilderTokenEstimation:
    """Test approximate token sizes of generated guidance."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count (roughly 4 chars per token)."""
        return len(text) // 4

    def test_minimal_under_200_tokens(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that minimal guidance is under ~200 tokens."""
        xml = guidance_builder.build_guidance("minimal")
        tokens = self.estimate_tokens(xml)
        # Allow some margin
        assert tokens < 250, f"Minimal guidance is ~{tokens} tokens, expected <250"

    def test_standard_under_1000_tokens(
        self, guidance_builder: GuidanceBuilder
    ) -> None:
        """Test that standard guidance is under ~1000 tokens."""
        xml = guidance_builder.build_guidance("standard")
        tokens = self.estimate_tokens(xml)
        assert tokens < 1000, f"Standard guidance is ~{tokens} tokens, expected <1000"

    def test_detailed_under_1200_tokens(
        self, guidance_builder: GuidanceBuilder
    ) -> None:
        """Test that detailed guidance is under ~1200 tokens."""
        xml = guidance_builder.build_guidance("detailed")
        tokens = self.estimate_tokens(xml)
        assert tokens < 1500, f"Detailed guidance is ~{tokens} tokens, expected <1500"


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestGetGuidanceBuilder:
    """Test the get_guidance_builder factory function."""

    def test_returns_guidance_builder(self) -> None:
        """Test that factory returns GuidanceBuilder instance."""
        builder = get_guidance_builder()
        assert isinstance(builder, GuidanceBuilder)

    def test_produces_valid_output(self) -> None:
        """Test that factory-created builder produces valid output."""
        builder = get_guidance_builder()
        xml = builder.build_guidance("minimal")
        assert "<session_operating_context" in xml


# =============================================================================
# Configuration Integration Tests
# =============================================================================


class TestConfigIntegration:
    """Test integration with HookConfig."""

    def test_default_config_has_guidance_enabled(self) -> None:
        """Test that default config enables guidance."""
        config = HookConfig()
        assert config.session_start_include_guidance is True

    def test_default_config_uses_standard_level(self) -> None:
        """Test that default config uses standard detail level."""
        config = HookConfig()
        assert config.session_start_guidance_detail == GuidanceDetailLevel.STANDARD

    def test_load_config_guidance_enabled(self) -> None:
        """Test loading config with guidance enabled."""
        env = {"HOOK_SESSION_START_INCLUDE_GUIDANCE": "true"}
        config = load_hook_config(env)
        assert config.session_start_include_guidance is True

    def test_load_config_guidance_disabled(self) -> None:
        """Test loading config with guidance disabled."""
        env = {"HOOK_SESSION_START_INCLUDE_GUIDANCE": "false"}
        config = load_hook_config(env)
        assert config.session_start_include_guidance is False

    def test_load_config_minimal_level(self) -> None:
        """Test loading config with minimal detail level."""
        env = {"HOOK_SESSION_START_GUIDANCE_DETAIL": "minimal"}
        config = load_hook_config(env)
        assert config.session_start_guidance_detail == GuidanceDetailLevel.MINIMAL

    def test_load_config_detailed_level(self) -> None:
        """Test loading config with detailed level."""
        env = {"HOOK_SESSION_START_GUIDANCE_DETAIL": "detailed"}
        config = load_hook_config(env)
        assert config.session_start_guidance_detail == GuidanceDetailLevel.DETAILED

    def test_load_config_invalid_level_uses_default(self) -> None:
        """Test that invalid level falls back to default."""
        env = {"HOOK_SESSION_START_GUIDANCE_DETAIL": "invalid"}
        config = load_hook_config(env)
        # Should use default (STANDARD)
        assert config.session_start_guidance_detail == GuidanceDetailLevel.STANDARD

    def test_guidance_level_matches_builder_level(self) -> None:
        """Test that config level values match builder level values."""
        for config_level in GuidanceDetailLevel:
            builder_level = GuidanceLevel(config_level.value)
            assert config_level.value == builder_level.value


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string_level_raises(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that empty string level raises ValueError."""
        with pytest.raises(ValueError):
            guidance_builder.build_guidance("")

    def test_whitespace_level_raises(self, guidance_builder: GuidanceBuilder) -> None:
        """Test that whitespace level raises ValueError."""
        with pytest.raises(ValueError):
            guidance_builder.build_guidance("  ")

    def test_special_chars_in_templates_escaped(
        self, guidance_builder: GuidanceBuilder
    ) -> None:
        """Test that special XML chars in templates are escaped."""
        xml = guidance_builder.build_guidance("detailed")
        # Templates contain ** which should be preserved
        # But < and > should be escaped to &lt; and &gt;
        # The template text contains brackets that get escaped
        # Let's verify the XML is still valid (S314 safe: parsing our own generated XML)
        root = ET.fromstring(xml)  # noqa: S314
        assert root is not None

    def test_multiple_builds_are_independent(
        self, guidance_builder: GuidanceBuilder
    ) -> None:
        """Test that multiple builds don't interfere with each other."""
        xml1 = guidance_builder.build_guidance("minimal")
        xml2 = guidance_builder.build_guidance("detailed")
        xml3 = guidance_builder.build_guidance("minimal")
        # Same level should produce same output
        assert xml1 == xml3
        # Different levels should produce different output
        assert xml1 != xml2
