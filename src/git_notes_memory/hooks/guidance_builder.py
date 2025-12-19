"""Response guidance builder for SessionStart hook.

This module provides the GuidanceBuilder class which generates XML templates
teaching Claude how to structure responses for reliable memory signal detection.

The guidance includes:
- Capture patterns for decisions, learnings, blockers, progress
- Trigger phrases that improve signal detection accuracy
- Inline marker syntax reference with namespace support
- Best practices for memorable content formatting

Detail Levels:
- minimal: Basic syntax reference only (~200 tokens)
- standard: Syntax + key patterns (~500 tokens)
- detailed: Full templates with examples (~1000 tokens)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = ["GuidanceBuilder", "GuidanceLevel"]


class GuidanceLevel(Enum):
    """Detail level for response guidance.

    - MINIMAL: Inline marker syntax only, lowest token cost
    - STANDARD: Syntax + capture patterns, balanced
    - DETAILED: Full templates with examples, highest value
    """

    MINIMAL = "minimal"
    STANDARD = "standard"
    DETAILED = "detailed"


@dataclass(frozen=True)
class CapturePattern:
    """Represents a capture pattern definition.

    Attributes:
        type_name: The signal type (decision, learning, blocker, progress)
        description: When to use this pattern
        template: Markdown template for structuring content
        trigger_phrases: Phrases that trigger signal detection
    """

    type_name: str
    description: str
    template: str
    trigger_phrases: tuple[str, ...]


# Pattern definitions for detailed guidance
CAPTURE_PATTERNS: tuple[CapturePattern, ...] = (
    CapturePattern(
        type_name="decision",
        description="When making architectural or design decisions",
        template="""**Decision**: [One-line summary]
**Context**: [Why this decision was needed]
**Choice**: [What was chosen]
**Rationale**: [Why this choice over alternatives]
**Alternatives considered**: [Other options evaluated]""",
        trigger_phrases=(
            "We decided to...",
            "The decision is to...",
            "Going with X because...",
            "After evaluating, we chose...",
        ),
    ),
    CapturePattern(
        type_name="learning",
        description="When discovering insights or TIL moments",
        template="""**Learning**: [One-line insight]
**Context**: [How this was discovered]
**Application**: [When/how to apply this]""",
        trigger_phrases=(
            "TIL...",
            "Discovered that...",
            "Learned that...",
            "Turns out...",
            "Interesting finding...",
        ),
    ),
    CapturePattern(
        type_name="blocker",
        description="When encountering obstacles or issues",
        template="""**Blocker**: [One-line issue]
**Impact**: [What this blocks]
**Status**: [investigating/blocked/resolved]
**Resolution**: [If resolved, how]""",
        trigger_phrases=(
            "Blocked by...",
            "Cannot proceed because...",
            "Stuck on...",
            "Issue discovered...",
            "Problem found...",
        ),
    ),
    CapturePattern(
        type_name="progress",
        description="When completing milestones or deliverables",
        template="""**Completed**: [What was finished]
**Deliverables**: [Concrete outputs]
**Next**: [What comes next]""",
        trigger_phrases=(
            "Completed...",
            "Finished implementing...",
            "Milestone reached...",
            "Done with...",
            "Successfully implemented...",
        ),
    ),
)

# Namespace definitions for inline markers
VALID_NAMESPACES: tuple[str, ...] = (
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
)


class GuidanceBuilder:
    """Builds XML response guidance for session injection.

    This class generates XML templates that teach Claude how to structure
    responses for reliable memory signal detection. The guidance helps
    improve signal detection accuracy from ~70% to ~85%+.

    The guidance is included in SessionStart additionalContext when
    `HOOK_SESSION_START_INCLUDE_GUIDANCE` is enabled.

    Example::

        builder = GuidanceBuilder()
        xml = builder.build_guidance("standard")
        # Returns XML string for additionalContext prepending
    """

    def build_guidance(self, detail_level: str = "standard") -> str:
        """Build response guidance XML.

        Args:
            detail_level: One of "minimal", "standard", or "detailed".
                - minimal: Inline marker syntax only (~200 tokens)
                - standard: Syntax + capture patterns (~500 tokens)
                - detailed: Full templates with examples (~1000 tokens)

        Returns:
            XML string for inclusion in additionalContext.

        Raises:
            ValueError: If detail_level is not recognized.

        Example::

            builder = GuidanceBuilder()
            xml = builder.build_guidance("standard")
            # Use in SessionStart additionalContext
        """
        try:
            level = GuidanceLevel(detail_level.lower())
        except ValueError:
            valid = [level.value for level in GuidanceLevel]
            msg = f"Invalid detail_level '{detail_level}'. Valid: {valid}"
            raise ValueError(msg) from None

        if level == GuidanceLevel.MINIMAL:
            return self._build_minimal()
        if level == GuidanceLevel.STANDARD:
            return self._build_standard()
        return self._build_detailed()

    def _build_minimal(self) -> str:
        """Build minimal guidance - inline markers only."""
        return """<response_guidance level="minimal">
  <inline_markers title="Quick Capture Markers">
    <marker syntax="[remember] text" description="Capture to learnings namespace"/>
    <marker syntax="[remember:namespace] text" description="Capture to specified namespace"/>
    <marker syntax="[capture] text" description="Auto-detect namespace from content"/>
    <marker syntax="@memory text" description="Alternative capture syntax"/>
    <marker syntax="@memory:namespace text" description="Alternative with namespace"/>
  </inline_markers>
  <namespaces>decisions, learnings, blockers, progress, patterns, research, reviews, retrospective</namespaces>
</response_guidance>"""

    def _build_standard(self) -> str:
        """Build standard guidance - syntax + patterns."""
        patterns_xml = self._build_patterns_section(include_templates=False)
        markers_xml = self._build_markers_section()
        practices_xml = self._build_practices_section()

        return f"""<response_guidance level="standard">
{patterns_xml}
{markers_xml}
{practices_xml}
</response_guidance>"""

    def _build_detailed(self) -> str:
        """Build detailed guidance - full templates with examples."""
        patterns_xml = self._build_patterns_section(include_templates=True)
        markers_xml = self._build_markers_section()
        practices_xml = self._build_practices_section()
        examples_xml = self._build_examples_section()

        return f"""<response_guidance level="detailed">
{patterns_xml}
{markers_xml}
{practices_xml}
{examples_xml}
</response_guidance>"""

    def _build_patterns_section(self, include_templates: bool = False) -> str:
        """Build the capture patterns section."""
        lines = [
            '  <capture_patterns title="How to Structure Responses for Memory Capture">'
        ]

        for pattern in CAPTURE_PATTERNS:
            lines.append(f'    <pattern type="{pattern.type_name}">')
            lines.append(f"      <description>{pattern.description}</description>")

            if include_templates:
                # Escape template content for XML
                escaped_template = (
                    pattern.template.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                lines.append(f"      <template>{escaped_template}</template>")

            # Always include trigger phrases
            lines.append("      <trigger_phrases>")
            for phrase in pattern.trigger_phrases:
                lines.append(f"        <phrase>{phrase}</phrase>")
            lines.append("      </trigger_phrases>")
            lines.append("    </pattern>")

        lines.append("  </capture_patterns>")
        return "\n".join(lines)

    def _build_markers_section(self) -> str:
        """Build the inline markers section."""
        return """  <inline_markers title="Quick Capture Markers">
    <marker syntax="[remember] text" namespace="learnings" description="Quick capture to learnings"/>
    <marker syntax="[remember:namespace] text" namespace="specified" description="Capture to specific namespace"/>
    <marker syntax="[capture] text" namespace="auto-detect" description="Auto-detect namespace from content"/>
    <marker syntax="[capture:decisions] text" namespace="decisions" description="Capture decision explicitly"/>
    <marker syntax="@memory text" namespace="auto-detect" description="Alternative inline syntax"/>
    <marker syntax="@memory:patterns text" namespace="patterns" description="Alternative with namespace"/>
  </inline_markers>
  <valid_namespaces>decisions, learnings, blockers, progress, patterns, research, reviews, retrospective, inception, elicitation</valid_namespaces>"""

    def _build_practices_section(self) -> str:
        """Build the best practices section."""
        return """  <best_practices title="Memory Capture Best Practices">
    <practice>Use clear trigger phrases at the start of memorable content</practice>
    <practice>Include rationale with decisions, not just the choice</practice>
    <practice>Tag blockers with resolution status when solved</practice>
    <practice>Keep summaries under 100 characters for better signal detection</practice>
    <practice>Use namespace hints when content clearly belongs to a specific category</practice>
  </best_practices>"""

    def _build_examples_section(self) -> str:
        """Build the examples section for detailed level."""
        return """  <examples title="Effective Capture Examples">
    <example type="decision">
      <input>We need to pick a database</input>
      <output>**Decision**: Use PostgreSQL for persistence
**Context**: Need ACID compliance and JSON support
**Choice**: PostgreSQL 15 with JSONB columns
**Rationale**: Team expertise, proven reliability, excellent JSON support
**Alternatives considered**: MongoDB (no ACID), SQLite (scaling concerns)</output>
    </example>
    <example type="learning">
      <input>Found a pytest quirk</input>
      <output>**Learning**: pytest fixtures with scope="module" share state across tests
**Context**: Discovered when tests failed intermittently due to shared mock state
**Application**: Use scope="function" for mutable fixtures, module for readonly</output>
    </example>
    <example type="inline_marker">
      <input>Quick insight during coding</input>
      <output>[remember:patterns] Always use frozen dataclasses for immutable models to prevent accidental mutation</output>
    </example>
  </examples>"""


def get_guidance_builder() -> GuidanceBuilder:
    """Get a GuidanceBuilder instance.

    Returns:
        GuidanceBuilder instance for generating response guidance.
    """
    return GuidanceBuilder()
