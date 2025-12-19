"""Data models for the memory capture system.

These dataclasses define the core domain objects used throughout the memory system.
All models are immutable (frozen) to ensure thread-safety and prevent accidental mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

__all__ = [
    # Enums
    "HydrationLevel",
    "PatternType",
    "PatternStatus",
    # Core Models
    "Memory",
    "MemoryResult",
    "HydratedMemory",
    "SpecContext",
    # Result Models
    "CaptureResult",
    "CaptureAccumulator",
    "IndexStats",
    "VerificationResult",
    # Pattern Models
    "Pattern",
    # Git Models
    "CommitInfo",
    "NoteRecord",
]


# =============================================================================
# Enums
# =============================================================================


class HydrationLevel(Enum):
    """Progressive hydration levels for memory recall.

    Controls how much data is loaded when retrieving memories:
    - SUMMARY: Only metadata and one-line summary (fast, minimal context)
    - FULL: Complete note content from git notes show
    - FILES: Full content plus file snapshots from the commit
    """

    SUMMARY = 1
    FULL = 2
    FILES = 3


class PatternType(Enum):
    """Types of patterns that can be detected across memories.

    Used to categorize recurring patterns found in the memory corpus:
    - SUCCESS: Things that worked well
    - ANTI_PATTERN: Things to avoid
    - WORKFLOW: Process patterns
    - DECISION: Decision-making patterns
    - TECHNICAL: Technical implementation patterns
    """

    SUCCESS = "success"
    ANTI_PATTERN = "anti-pattern"
    WORKFLOW = "workflow"
    DECISION = "decision"
    TECHNICAL = "technical"


class PatternStatus(Enum):
    """Lifecycle status of a detected pattern.

    Patterns progress through these states:
    - CANDIDATE: Newly detected, needs validation
    - VALIDATED: Confirmed by user or multiple occurrences
    - PROMOTED: Actively suggested to users
    - DEPRECATED: No longer relevant
    """

    CANDIDATE = "candidate"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    DEPRECATED = "deprecated"


# =============================================================================
# Core Memory Models
# =============================================================================


@dataclass(frozen=True)
class Memory:
    """Core memory object representing a captured piece of context.

    This is the primary entity in the memory system, representing a single
    captured piece of context attached to a git commit.

    Attributes:
        id: Unique identifier (typically <namespace>:<commit_sha>:<index>)
        commit_sha: Git commit this memory is attached to
        namespace: Memory type (decisions, learnings, blockers, etc.)
        summary: One-line summary (max 100 chars)
        content: Full markdown content of the note
        timestamp: When the memory was captured
        repo_path: Absolute path to the git repository containing this memory
        spec: Specification slug this memory belongs to (may be None for global)
        phase: Lifecycle phase (planning, implementation, review, etc.)
        tags: Categorization tags
        status: Memory status (active, resolved, archived, tombstone)
        relates_to: IDs of related memories
    """

    id: str
    commit_sha: str
    namespace: str
    summary: str
    content: str
    timestamp: datetime
    repo_path: str | None = None
    spec: str | None = None
    phase: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    status: str = "active"
    relates_to: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MemoryResult:
    """A memory with its semantic similarity score from vector search.

    Wraps a Memory with its distance score from a vector similarity search.
    Provides convenience properties to access underlying Memory fields directly.

    Attributes:
        memory: The recalled memory
        distance: Euclidean distance from query vector (lower = more similar)
    """

    memory: Memory
    distance: float

    # Convenience properties for uniform access with Memory
    @property
    def id(self) -> str:
        """Get the memory ID."""
        return self.memory.id

    @property
    def commit_sha(self) -> str:
        """Get the commit SHA."""
        return self.memory.commit_sha

    @property
    def namespace(self) -> str:
        """Get the namespace."""
        return self.memory.namespace

    @property
    def summary(self) -> str:
        """Get the summary."""
        return self.memory.summary

    @property
    def content(self) -> str:
        """Get the content."""
        return self.memory.content

    @property
    def timestamp(self) -> datetime:
        """Get the timestamp."""
        return self.memory.timestamp

    @property
    def spec(self) -> str | None:
        """Get the spec."""
        return self.memory.spec

    @property
    def phase(self) -> str | None:
        """Get the phase."""
        return self.memory.phase

    @property
    def tags(self) -> tuple[str, ...]:
        """Get the tags."""
        return self.memory.tags

    @property
    def status(self) -> str:
        """Get the status."""
        return self.memory.status

    @property
    def relates_to(self) -> tuple[str, ...]:
        """Get related memory IDs."""
        return self.memory.relates_to

    @property
    def score(self) -> float:
        """Alias for distance for semantic compatibility."""
        return self.distance


@dataclass(frozen=True)
class HydratedMemory:
    """A fully hydrated memory with additional context.

    Contains the memory result plus additional data loaded from git
    based on the hydration level requested.

    Attributes:
        result: The base memory result
        full_content: Complete note content (HydrationLevel.FULL+)
        files: Dict of file paths to content snapshots (HydrationLevel.FILES)
        commit_info: Commit metadata (author, date, message)
    """

    result: MemoryResult
    full_content: str | None = None
    files: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    commit_info: CommitInfo | None = None

    @property
    def files_dict(self) -> dict[str, str]:
        """Get files as a dictionary for convenience."""
        return dict(self.files)


@dataclass(frozen=True)
class SpecContext:
    """All memories for a specification, organized for context loading.

    Groups all memories belonging to a spec by namespace for efficient
    context retrieval.

    Attributes:
        spec: Specification slug
        memories: All memories grouped by namespace
        total_count: Total number of memories
        token_estimate: Estimated token count for all content
    """

    spec: str
    memories: tuple[Memory, ...] = field(default_factory=tuple)
    total_count: int = 0
    token_estimate: int = 0

    @property
    def by_namespace(self) -> dict[str, list[Memory]]:
        """Group memories by namespace."""
        result: dict[str, list[Memory]] = {}
        for mem in self.memories:
            if mem.namespace not in result:
                result[mem.namespace] = []
            result[mem.namespace].append(mem)
        return result


# =============================================================================
# Result Models
# =============================================================================


@dataclass(frozen=True)
class CaptureResult:
    """Result of a memory capture operation.

    Returned by capture methods to indicate success/failure and provide
    the captured memory if successful.

    Attributes:
        success: Whether the capture completed
        memory: The captured memory (if successful)
        indexed: Whether the memory was added to the search index
        warning: Optional warning message (e.g., embedding failed)
    """

    success: bool
    memory: Memory | None = None
    indexed: bool = False
    warning: str | None = None


@dataclass
class CaptureAccumulator:
    """Tracks captures during a command execution for summary display.

    This is a mutable container (NOT frozen) that accumulates CaptureResults
    as they are captured during a command session.

    Attributes:
        captures: List of CaptureResult objects from this session
        start_time: When the accumulator was created
    """

    captures: list[CaptureResult] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add(self, result: CaptureResult) -> None:
        """Add a capture result to the accumulator."""
        self.captures.append(result)

    @property
    def count(self) -> int:
        """Return the number of captures."""
        return len(self.captures)

    @property
    def successful_count(self) -> int:
        """Return the number of successful captures."""
        return sum(1 for c in self.captures if c.success)

    @property
    def by_namespace(self) -> dict[str, int]:
        """Group capture counts by namespace."""
        counts: dict[str, int] = {}
        for capture in self.captures:
            if capture.memory:
                ns = capture.memory.namespace
                counts[ns] = counts.get(ns, 0) + 1
        return counts

    def summary(self) -> str:
        """Generate a summary string for display."""
        if not self.captures:
            return "No memories captured this session."

        lines = [
            "────────────────────────────────────────────────────────────────",
            "Memory Capture Summary",
            "────────────────────────────────────────────────────────────────",
            f"Captured: {self.count} memories ({self.successful_count} successful)",
        ]

        for capture in self.captures:
            if capture.memory:
                status = "✓" if capture.success else "✗"
                lines.append(
                    f"  {status} {capture.memory.id} - {capture.memory.summary}"
                )
            elif capture.warning:
                lines.append(f"  ⚠ {capture.warning}")

        lines.append("────────────────────────────────────────────────────────────────")
        return "\n".join(lines)


@dataclass(frozen=True)
class IndexStats:
    """Statistics about the memory index.

    Provides summary information about the indexed memories for
    status displays and health checks.

    Attributes:
        total_memories: Total number of indexed memories
        by_namespace: Count per namespace
        by_spec: Count per specification
        last_sync: Timestamp of last synchronization
        index_size_bytes: Size of the SQLite database
    """

    total_memories: int
    by_namespace: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    by_spec: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    last_sync: datetime | None = None
    index_size_bytes: int = 0

    @property
    def by_namespace_dict(self) -> dict[str, int]:
        """Get namespace counts as a dictionary."""
        return dict(self.by_namespace)

    @property
    def by_spec_dict(self) -> dict[str, int]:
        """Get spec counts as a dictionary."""
        return dict(self.by_spec)


@dataclass(frozen=True)
class VerificationResult:
    """Result of verifying index consistency against Git notes.

    Returned by verification operations to report on index health.

    Attributes:
        is_consistent: True if index matches notes
        missing_in_index: Memory IDs in notes but not in index
        orphaned_in_index: Memory IDs in index but not in notes
        mismatched: Memory IDs with different content
    """

    is_consistent: bool
    missing_in_index: tuple[str, ...] = field(default_factory=tuple)
    orphaned_in_index: tuple[str, ...] = field(default_factory=tuple)
    mismatched: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total_issues(self) -> int:
        """Get the total number of issues found."""
        return (
            len(self.missing_in_index)
            + len(self.orphaned_in_index)
            + len(self.mismatched)
        )


# =============================================================================
# Pattern Models
# =============================================================================


@dataclass(frozen=True)
class Pattern:
    """A detected pattern across memories.

    Represents a recurring theme, practice, or anti-pattern found
    by analyzing the memory corpus.

    Attributes:
        name: Human-readable pattern name
        pattern_type: Classification of the pattern
        description: Full description of the pattern
        evidence: Memory IDs that support this pattern
        confidence: Confidence score (0.0 - 1.0)
        tags: Associated tags
        status: Lifecycle status
        first_seen: When pattern was first detected
        last_seen: When pattern was last observed
        occurrence_count: Number of times pattern has been seen
    """

    name: str
    pattern_type: PatternType
    description: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    tags: tuple[str, ...] = field(default_factory=tuple)
    status: PatternStatus = PatternStatus.CANDIDATE
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    occurrence_count: int = 1


# =============================================================================
# Git Models
# =============================================================================


@dataclass(frozen=True)
class CommitInfo:
    """Git commit metadata.

    Contains information about a git commit for display and tracking.

    Attributes:
        sha: Full commit SHA
        author_name: Name of the commit author
        author_email: Email of the commit author
        date: Commit date as ISO string
        message: Commit message (first line)
    """

    sha: str
    author_name: str
    author_email: str
    date: str
    message: str


@dataclass(frozen=True)
class NoteRecord:
    """A parsed git note record.

    Represents a single memory entry parsed from a git note.

    Attributes:
        commit_sha: Commit the note is attached to
        namespace: Memory namespace
        index: Index within the note (for multi-memory notes)
        front_matter: Parsed YAML front matter as key-value pairs
        body: Markdown body content
        raw: Original raw note content
    """

    commit_sha: str
    namespace: str
    index: int = 0
    front_matter: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    body: str = ""
    raw: str = ""

    @property
    def front_matter_dict(self) -> dict[str, str]:
        """Get front matter as a dictionary."""
        return dict(self.front_matter)

    @property
    def timestamp(self) -> datetime | None:
        """Get the parsed timestamp from front matter."""
        ts_str = self.front_matter_dict.get("timestamp")
        if ts_str is None:
            return None
        # Parse ISO format timestamp
        try:
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            return datetime.fromisoformat(ts_str)
        except ValueError:
            return None

    @property
    def summary(self) -> str | None:
        """Get the summary from front matter."""
        return self.front_matter_dict.get("summary")

    @property
    def spec(self) -> str | None:
        """Get the spec identifier from front matter."""
        return self.front_matter_dict.get("spec")

    @property
    def tags(self) -> list[str]:
        """Get the tags from front matter as a list."""
        tags_str = self.front_matter_dict.get("tags", "")
        if not tags_str:
            return []
        # Tags stored as comma-separated string
        return [t.strip() for t in tags_str.split(",") if t.strip()]

    @property
    def phase(self) -> str | None:
        """Get the phase from front matter."""
        return self.front_matter_dict.get("phase")

    @property
    def status(self) -> str | None:
        """Get the status from front matter."""
        return self.front_matter_dict.get("status")

    @property
    def relates_to(self) -> list[str]:
        """Get the relates_to from front matter as a list."""
        relates_str = self.front_matter_dict.get("relates_to", "")
        if not relates_str:
            return []
        # Relates_to stored as comma-separated string
        return [r.strip() for r in relates_str.split(",") if r.strip()]
