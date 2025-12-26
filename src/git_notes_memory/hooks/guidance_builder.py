"""Response guidance builder for SessionStart hook.

This module provides the GuidanceBuilder class which loads Markdown templates
teaching Claude how to structure responses for reliable memory signal detection.

The guidance templates are stored as external Markdown files in the templates/
directory for easy editing without code changes.

The guidance includes:
- Capture patterns for decisions, learnings, blockers, progress
- Trigger phrases that improve signal detection accuracy
- Inline marker syntax reference with namespace support
- Memory recall instructions for surfacing past memories
- Best practices for memorable content formatting

Detail Levels:
- minimal: Basic syntax reference only (~200 tokens)
- standard: Syntax + key patterns + recall instructions (~900 tokens)
- detailed: Full templates with examples (~1200 tokens)
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from git_notes_memory.observability import get_logger

__all__ = ["GuidanceBuilder", "GuidanceLevel"]

logger = get_logger(__name__)

# Directory containing Markdown templates
TEMPLATES_DIR = Path(__file__).parent / "templates"


class GuidanceLevel(Enum):
    """Detail level for response guidance.

    - MINIMAL: Inline marker syntax only, lowest token cost
    - STANDARD: Syntax + capture patterns + recall instructions, balanced
    - DETAILED: Full templates with examples, highest value
    """

    MINIMAL = "minimal"
    STANDARD = "standard"
    DETAILED = "detailed"


class GuidanceBuilder:
    """Builds response guidance for session injection.

    This class loads Markdown templates from the templates/ directory that teach
    Claude how to structure responses for reliable memory signal detection.
    The guidance helps improve signal detection accuracy from ~70% to ~85%+.

    Templates can be edited directly without code changes.

    The guidance is included in SessionStart additionalContext when
    `HOOK_SESSION_START_INCLUDE_GUIDANCE` is enabled.

    Example::

        builder = GuidanceBuilder()
        guidance = builder.build_guidance("standard")
        # Returns guidance string for additionalContext prepending
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        """Initialize the guidance builder.

        Args:
            templates_dir: Optional custom templates directory.
                Defaults to the bundled templates/ directory.
        """
        self._templates_dir = templates_dir or TEMPLATES_DIR
        self._cache: dict[str, str] = {}

    def build_guidance(self, detail_level: str = "standard") -> str:
        """Build response guidance by loading from template file.

        Args:
            detail_level: One of "minimal", "standard", or "detailed".
                - minimal: Inline marker syntax only (~200 tokens)
                - standard: Syntax + capture patterns + recall (~900 tokens)
                - detailed: Full templates with examples (~1200 tokens)

        Returns:
            Guidance string for inclusion in additionalContext.

        Raises:
            ValueError: If detail_level is not recognized.
            FileNotFoundError: If template file doesn't exist.

        Example::

            builder = GuidanceBuilder()
            guidance = builder.build_guidance("standard")
            # Use in SessionStart additionalContext
        """
        try:
            level = GuidanceLevel(detail_level.lower())
        except ValueError:
            valid = [lv.value for lv in GuidanceLevel]
            msg = f"Invalid detail_level '{detail_level}'. Valid: {valid}"
            raise ValueError(msg) from None

        return self._load_template(level.value)

    def _load_template(self, level: str) -> str:
        """Load a template file by level name.

        Args:
            level: The guidance level (minimal, standard, detailed).

        Returns:
            Template content as string.

        Raises:
            FileNotFoundError: If template file doesn't exist.
        """
        # Check cache first
        if level in self._cache:
            return self._cache[level]

        template_path = self._templates_dir / f"guidance_{level}.md"

        if not template_path.exists():
            msg = f"Template file not found: {template_path}"
            raise FileNotFoundError(msg)

        content = template_path.read_text(encoding="utf-8").strip()
        self._cache[level] = content

        logger.debug("Loaded guidance template: %s (%d chars)", level, len(content))
        return content

    def clear_cache(self) -> None:
        """Clear the template cache to reload from disk."""
        self._cache.clear()


def get_guidance_builder() -> GuidanceBuilder:
    """Get a GuidanceBuilder instance.

    Returns:
        GuidanceBuilder instance for generating response guidance.
    """
    return GuidanceBuilder()
