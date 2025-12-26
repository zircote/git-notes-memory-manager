"""Note parser for extracting structured data from git notes.

Parses YAML front matter and markdown body from git notes. The expected format is:

```
---
type: decisions
spec: my-project
timestamp: 2024-01-15T10:30:00Z
summary: Chose PostgreSQL for data layer
phase: planning
tags:
  - database
  - architecture
---

## Context

We needed to choose a database...
```

The parser handles:
- Standard YAML front matter delimited by `---`
- Graceful handling of malformed YAML
- Preservation of body formatting
- Multi-document YAML (multiple notes in one git note)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import yaml

from git_notes_memory.config import NOTE_REQUIRED_FIELDS
from git_notes_memory.exceptions import ParseError

if TYPE_CHECKING:
    from git_notes_memory.models import NoteRecord

__all__ = [
    "parse_note",
    "parse_note_safe",
    "parse_multi_note",
    "serialize_note",
    "ParsedNote",
    "NoteParser",
    "to_note_record",
]


# =============================================================================
# Constants
# =============================================================================

# Pattern to match YAML front matter at the start of content
# Matches: ---\n<yaml>\n--- followed by optional body
# The (.*?) group can be empty for empty front matter
_FRONT_MATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)^---\s*(?:\n(.*))?$",
    re.DOTALL | re.MULTILINE,
)

# Pattern to split multiple notes in a single git note
# Each note starts with --- on its own line
_MULTI_NOTE_SPLIT = re.compile(r"(?:^|\n)(?=---\s*\n)")

# SEC-HIGH-002: Maximum YAML front matter size (64KB)
# Prevents YAML "billion laughs" attacks where recursive anchors/aliases
# cause exponential memory expansion during parsing
_MAX_YAML_SIZE = 65536  # 64KB


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class ParsedNote:
    """Intermediate representation of a parsed note.

    This is the raw parsing result before conversion to a NoteRecord.
    Contains the front matter as a dict and the body as-is.

    Attributes:
        front_matter: Parsed YAML front matter dictionary
        body: Markdown body content (may be empty)
        raw: Original raw content
    """

    front_matter: dict[str, object]
    body: str
    raw: str

    @property
    def type(self) -> str | None:
        """Get the note type (namespace)."""
        value = self.front_matter.get("type")
        return str(value) if value is not None else None

    @property
    def spec(self) -> str | None:
        """Get the spec identifier."""
        value = self.front_matter.get("spec")
        return str(value) if value is not None else None

    @property
    def timestamp(self) -> str | None:
        """Get the timestamp string."""
        value = self.front_matter.get("timestamp")
        return str(value) if value is not None else None

    @property
    def summary(self) -> str | None:
        """Get the summary."""
        value = self.front_matter.get("summary")
        return str(value) if value is not None else None

    def get(self, key: str, default: object = None) -> object:
        """Get a front matter value with default."""
        return self.front_matter.get(key, default)

    def has_required_fields(self) -> bool:
        """Check if all required fields are present."""
        return all(
            self.front_matter.get(field) is not None for field in NOTE_REQUIRED_FIELDS
        )

    def missing_fields(self) -> list[str]:
        """Get list of missing required fields."""
        return [
            field
            for field in NOTE_REQUIRED_FIELDS
            if self.front_matter.get(field) is None
        ]

    def validate(self) -> None:
        """Validate the note has all required fields.

        Raises:
            ParseError: If required fields are missing.
        """
        missing = self.missing_fields()
        if missing:
            raise ParseError(
                f"Note missing required fields: {', '.join(sorted(missing))}",
                f"Ensure note has: {', '.join(sorted(NOTE_REQUIRED_FIELDS))}",
            )


# =============================================================================
# Parsing Functions
# =============================================================================


def parse_note(content: str) -> ParsedNote:
    """Parse a git note with YAML front matter.

    Extracts structured metadata from YAML front matter and preserves
    the markdown body content.

    Args:
        content: Raw git note content.

    Returns:
        ParsedNote with front_matter dict and body string.

    Raises:
        ParseError: If the content cannot be parsed (no front matter,
            invalid YAML, etc.).

    Examples:
        >>> note = parse_note('''---
        ... type: decisions
        ... spec: my-project
        ... timestamp: 2024-01-15T10:30:00Z
        ... summary: Chose PostgreSQL
        ... ---
        ...
        ... Some body content.
        ... ''')
        >>> note.type
        'decisions'
        >>> note.body.strip()
        'Some body content.'
    """
    if not content or not content.strip():
        raise ParseError(
            "Cannot parse empty note content",
            "Note must contain YAML front matter between --- markers",
        )

    # Handle content that doesn't start with ---
    stripped = content.strip()
    if not stripped.startswith("---"):
        raise ParseError(
            "Note does not have YAML front matter",
            "Note must start with --- followed by YAML metadata",
        )

    match = _FRONT_MATTER_PATTERN.match(stripped)
    if not match:
        raise ParseError(
            "Could not parse YAML front matter",
            "Ensure front matter is enclosed in --- markers on separate lines",
        )

    yaml_content = match.group(1)
    body = match.group(2) or ""

    # SEC-HIGH-002: Reject oversized YAML to prevent billion laughs attacks
    if len(yaml_content) > _MAX_YAML_SIZE:
        raise ParseError(
            f"YAML front matter exceeds maximum size ({len(yaml_content)} > {_MAX_YAML_SIZE} bytes)",
            "Reduce front matter size or split into multiple notes",
        )

    try:
        front_matter = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        # Extract line number if available
        line_info = ""
        if hasattr(e, "problem_mark") and e.problem_mark is not None:
            line_info = f" at line {e.problem_mark.line + 1}"
        raise ParseError(
            f"Invalid YAML in front matter{line_info}",
            "Check YAML syntax: proper indentation, quoting, and valid values",
        ) from e

    # Handle case where YAML is empty or not a dict
    if front_matter is None:
        front_matter = {}
    elif not isinstance(front_matter, dict):
        raise ParseError(
            "Front matter must be a YAML mapping (key: value pairs)",
            "Ensure front matter contains key-value pairs, not a list or scalar",
        )

    return ParsedNote(
        front_matter=front_matter,
        body=body,
        raw=content,
    )


def parse_note_safe(content: str) -> ParsedNote | None:
    """Parse a git note safely, returning None on error.

    A safe wrapper around parse_note that catches ParseError
    and returns None instead of raising exceptions.

    Args:
        content: Raw git note content.

    Returns:
        ParsedNote if parsing succeeds, None otherwise.

    Examples:
        >>> parse_note_safe("invalid content")
        None
        >>> parse_note_safe("---\\ntype: test\\n---")
        ParsedNote(...)
    """
    try:
        return parse_note(content)
    except ParseError:
        return None


def parse_multi_note(content: str) -> list[ParsedNote]:
    """Parse a git note that may contain multiple notes.

    Some git notes contain multiple memory entries concatenated together.
    This function splits them and parses each one.

    Args:
        content: Raw git note content (may contain multiple notes).

    Returns:
        List of ParsedNote objects (one per entry found).

    Examples:
        >>> notes = parse_multi_note('''---
        ... type: decisions
        ... spec: proj
        ... timestamp: 2024-01-15T10:30:00Z
        ... summary: First
        ... ---
        ... Body 1
        ...
        ... ---
        ... type: learnings
        ... spec: proj
        ... timestamp: 2024-01-15T11:00:00Z
        ... summary: Second
        ... ---
        ... Body 2
        ... ''')
        >>> len(notes)
        2
    """
    if not content or not content.strip():
        return []

    # Split on --- that starts a new note
    # We need to be careful: --- appears both as front matter start AND end
    parts = _split_multi_note(content)

    results = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        parsed = parse_note_safe(part)
        if parsed is not None:
            results.append(parsed)

    return results


def _split_multi_note(content: str) -> list[str]:
    """Split content that may contain multiple notes.

    Internal helper that handles the tricky splitting logic.
    """
    # First, try to detect if there are multiple notes
    # A new note starts with --- after a body section

    # Simple heuristic: count how many times we see the pattern
    # `---` followed by yaml-like content
    lines = content.split("\n")
    note_starts: list[int] = []
    in_front_matter = False
    front_matter_end = -1

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "---":
            if not in_front_matter:
                # This could be the start of a new note
                in_front_matter = True
                # Check if this is after a body (not at the very start)
                if i > 0 and front_matter_end >= 0 and i > front_matter_end:
                    # This is a new note starting
                    note_starts.append(i)
                elif i == 0 or (note_starts == [] and front_matter_end < 0):
                    # First note
                    note_starts.append(i)
            else:
                # This is the end of front matter
                in_front_matter = False
                front_matter_end = i

    if not note_starts:
        return [content]

    # Split at each note start
    parts = []
    for idx, start in enumerate(note_starts):
        if idx + 1 < len(note_starts):
            end = note_starts[idx + 1]
            parts.append("\n".join(lines[start:end]))
        else:
            parts.append("\n".join(lines[start:]))

    return parts


# =============================================================================
# Conversion to NoteRecord
# =============================================================================


def to_note_record(
    parsed: ParsedNote,
    commit_sha: str,
    namespace: str | None = None,
    index: int = 0,
) -> NoteRecord:
    """Convert a ParsedNote to a NoteRecord.

    Args:
        parsed: The parsed note.
        commit_sha: Git commit SHA this note is attached to.
        namespace: Override the namespace (if not in front matter).
        index: Index of this note within a multi-note (default 0).

    Returns:
        NoteRecord with all fields populated.

    Raises:
        ParseError: If the note is missing required fields.
    """
    # Import here to avoid circular imports
    from git_notes_memory.models import NoteRecord

    # Determine namespace from front matter or override
    note_type = parsed.type
    if namespace:
        note_type = namespace
    elif note_type is None:
        raise ParseError(
            "Note missing 'type' field (namespace)",
            "Add 'type: <namespace>' to the front matter",
        )

    # Convert front_matter dict to tuple of tuples for frozen dataclass
    # Only include string-convertible values
    front_matter_tuples: list[tuple[str, str]] = []
    for key, value in parsed.front_matter.items():
        if value is not None:
            # Handle lists specially (convert to comma-separated)
            if isinstance(value, list):
                str_value = ",".join(str(v) for v in value)
            else:
                str_value = str(value)
            front_matter_tuples.append((key, str_value))

    return NoteRecord(
        commit_sha=commit_sha,
        namespace=note_type,
        index=index,
        front_matter=tuple(front_matter_tuples),
        body=parsed.body,
        raw=parsed.raw,
    )


# =============================================================================
# Serialization Functions
# =============================================================================


def serialize_note(
    front_matter: dict[str, object],
    body: str = "",
) -> str:
    """Serialize a note to YAML front matter format.

    Creates a git note string from structured data.

    Args:
        front_matter: Dictionary of metadata fields.
        body: Optional markdown body content.

    Returns:
        Formatted note string with YAML front matter.

    Examples:
        >>> content = serialize_note(
        ...     {"type": "decisions", "summary": "Test"}, "Some body text"
        ... )
        >>> print(content)
        ---
        type: decisions
        summary: Test
        ---

        Some body text
    """
    # Use yaml.dump with specific options for clean output
    yaml_content = yaml.dump(
        front_matter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,  # Preserve insertion order
    )

    # Remove trailing newline from yaml.dump
    yaml_content = yaml_content.rstrip()

    if body and body.strip():
        return f"---\n{yaml_content}\n---\n\n{body}"
    else:
        return f"---\n{yaml_content}\n---\n"


# =============================================================================
# NoteParser Class (Wrapper for dependency injection)
# =============================================================================


class NoteParser:
    """Parser wrapper for dependency injection in services.

    This class wraps the module-level parsing functions to provide
    a class-based interface suitable for dependency injection and testing.

    Example:
        >>> parser = NoteParser()
        >>> records = parser.parse_many(
        ...     content, commit_sha="abc123", namespace="decisions"
        ... )
    """

    def parse(self, content: str) -> ParsedNote:
        """Parse a single note.

        Args:
            content: Raw git note content.

        Returns:
            ParsedNote with front_matter and body.

        Raises:
            ParseError: If parsing fails.
        """
        return parse_note(content)

    def parse_safe(self, content: str) -> ParsedNote | None:
        """Parse a note safely, returning None on error.

        Args:
            content: Raw git note content.

        Returns:
            ParsedNote if successful, None otherwise.
        """
        return parse_note_safe(content)

    def parse_multi(self, content: str) -> list[ParsedNote]:
        """Parse content that may contain multiple notes.

        Args:
            content: Raw git note content (may contain multiple notes).

        Returns:
            List of ParsedNote objects.
        """
        return parse_multi_note(content)

    def parse_many(
        self,
        content: str,
        commit_sha: str = "",
        namespace: str = "",
    ) -> list[NoteRecord]:
        """Parse content and convert to NoteRecord objects.

        This is the main entry point for parsing git notes into
        the NoteRecord format used by SyncService.

        Args:
            content: Raw git note content (may contain multiple notes).
            commit_sha: Git commit SHA the note is attached to.
            namespace: Default namespace if not in front matter.

        Returns:
            List of NoteRecord objects.
        """
        parsed_notes = parse_multi_note(content)
        records = []

        for i, parsed in enumerate(parsed_notes):
            # Determine namespace from front matter or use default
            note_namespace = parsed.type or namespace
            if not note_namespace:
                continue  # Skip notes without namespace

            try:
                record = to_note_record(
                    parsed,
                    commit_sha=commit_sha,
                    namespace=note_namespace,
                    index=i,
                )
                records.append(record)
            except ParseError:
                # Skip notes that fail validation
                continue

        return records

    def serialize(
        self,
        front_matter: dict[str, object],
        body: str = "",
    ) -> str:
        """Serialize front matter and body to note format.

        Args:
            front_matter: Dictionary of metadata fields.
            body: Optional markdown body content.

        Returns:
            Formatted note string.
        """
        return serialize_note(front_matter, body)
