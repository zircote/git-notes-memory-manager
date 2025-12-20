"""Hook-specific data models.

This module provides data classes for the hook system, including:
- Signal detection models (CaptureSignal, SignalType)
- Capture decision models (CaptureDecision, CaptureAction, SuggestedCapture)
- Token budget models (TokenBudget)
- Context models (MemoryContext, WorkingMemory, SemanticContext)

All models are frozen dataclasses for immutability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from git_notes_memory.models import Memory


def _utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(UTC)


__all__ = [
    "SignalType",
    "CaptureSignal",
    "NoveltyResult",
    "CaptureAction",
    "CaptureDecision",
    "SuggestedCapture",
    "TokenBudget",
    "MemoryContext",
    "WorkingMemory",
    "SemanticContext",
]


class SignalType(Enum):
    """Types of capture signals detected in user prompts.

    Each type maps to specific patterns and a suggested namespace.

    Attributes:
        DECISION: User made a decision ("I chose", "decided to", "we'll go with")
        LEARNING: User learned something ("I learned", "TIL", "turns out")
        BLOCKER: User encountered a blocker ("blocked by", "stuck on")
        RESOLUTION: User resolved an issue ("fixed", "solved", "workaround")
        PREFERENCE: User expressed a preference ("I prefer", "I like")
        EXPLICIT: User explicitly requested capture ("remember this", "save this")
    """

    DECISION = "decision"
    LEARNING = "learning"
    BLOCKER = "blocker"
    RESOLUTION = "resolution"
    PREFERENCE = "preference"
    EXPLICIT = "explicit"

    @property
    def suggested_namespace(self) -> str:
        """Get the suggested namespace for this signal type.

        Returns:
            Default namespace for memories of this type.
        """
        namespace_map = {
            SignalType.DECISION: "decisions",
            SignalType.LEARNING: "learnings",
            SignalType.BLOCKER: "blockers",
            SignalType.RESOLUTION: "solutions",
            SignalType.PREFERENCE: "preferences",
            SignalType.EXPLICIT: "notes",
        }
        return namespace_map[self]


@dataclass(frozen=True)
class CaptureSignal:
    """A detected signal indicating memorable content.

    Represents a pattern match in user input that suggests the content
    should be captured as a memory.

    Attributes:
        type: The type of signal detected.
        match: The exact text that matched the pattern.
        confidence: Confidence score from 0.0 to 1.0.
        context: Surrounding context text.
        suggested_namespace: Inferred namespace for capture.
        position: Character position of match in source text.
    """

    type: SignalType
    match: str
    confidence: float
    context: str
    suggested_namespace: str
    position: int = 0

    def __post_init__(self) -> None:
        """Validate confidence score is in valid range."""
        if not 0.0 <= self.confidence <= 1.0:
            msg = f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            raise ValueError(msg)


@dataclass(frozen=True)
class NoveltyResult:
    """Result of novelty checking for a capture signal.

    Indicates whether detected content is novel (should be captured)
    or a duplicate of existing memories.

    Attributes:
        novelty_score: Score from 0.0 (duplicate) to 1.0 (completely new).
        is_novel: Whether the content passes the novelty threshold.
        similar_memory_ids: IDs of similar existing memories.
        highest_similarity: Highest similarity score found.
    """

    novelty_score: float
    is_novel: bool
    similar_memory_ids: list[str] = field(default_factory=list)
    highest_similarity: float = 0.0

    def __post_init__(self) -> None:
        """Validate novelty score is in valid range."""
        if not 0.0 <= self.novelty_score <= 1.0:
            msg = f"Novelty score must be between 0.0 and 1.0, got {self.novelty_score}"
            raise ValueError(msg)


class CaptureAction(Enum):
    """Actions the capture decider can take.

    Attributes:
        AUTO: Capture automatically (high confidence, ≥0.95)
        SUGGEST: Suggest capture to user (medium confidence, 0.7-0.95)
        SKIP: Don't capture (low confidence, <0.7)
    """

    AUTO = "auto"
    SUGGEST = "suggest"
    SKIP = "skip"


@dataclass(frozen=True)
class SuggestedCapture:
    """A suggested memory capture with pre-filled metadata.

    Attributes:
        namespace: Suggested namespace for the memory.
        summary: Generated summary for the memory.
        content: Full content to capture.
        tags: Suggested tags for the memory.
        confidence: Confidence score for the suggestion.
    """

    namespace: str
    summary: str
    content: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0


@dataclass(frozen=True)
class CaptureDecision:
    """Decision from the capture decider.

    Contains the action to take and supporting information for
    the capture suggestion or auto-capture.

    Attributes:
        action: The capture action (auto, suggest, skip).
        signals: The signals that led to this decision.
        suggested_captures: Pre-filled capture suggestions.
        reason: Human-readable explanation of the decision.
    """

    action: CaptureAction
    signals: tuple[CaptureSignal, ...] = field(default_factory=tuple)
    suggested_captures: tuple[SuggestedCapture, ...] = field(default_factory=tuple)
    reason: str = ""


@dataclass(frozen=True)
class TokenBudget:
    """Token allocation for context injection.

    Defines how tokens should be allocated across different
    types of memory context.

    Attributes:
        total: Total tokens available for context.
        working_memory: Tokens for blockers, recent decisions.
        semantic_context: Tokens for relevant learnings.
        commands: Tokens for command hints.
    """

    total: int
    working_memory: int
    semantic_context: int
    commands: int = 100

    def __post_init__(self) -> None:
        """Validate budget allocation doesn't exceed total."""
        allocated = self.working_memory + self.semantic_context + self.commands
        if allocated > self.total:
            msg = (
                f"Allocated tokens ({allocated}) exceed total ({self.total}). "
                f"working_memory={self.working_memory}, "
                f"semantic_context={self.semantic_context}, "
                f"commands={self.commands}"
            )
            raise ValueError(msg)

    @classmethod
    def simple(cls, total: int) -> TokenBudget:
        """Create a simple budget split evenly.

        Args:
            total: Total token budget.

        Returns:
            TokenBudget with even split (70% working, 20% semantic, 10% commands).
        """
        commands = min(100, total // 10)
        remaining = total - commands
        working = int(remaining * 0.7)
        semantic = remaining - working
        return cls(
            total=total,
            working_memory=working,
            semantic_context=semantic,
            commands=commands,
        )


@dataclass(frozen=True)
class WorkingMemory:
    """High-priority, current working context.

    Contains memories that are immediately relevant to the
    current work session.

    Attributes:
        active_blockers: Current blocking issues.
        recent_decisions: Recently made decisions.
        pending_actions: Actions waiting to be completed.
    """

    active_blockers: tuple[Memory, ...] = field(default_factory=tuple)
    recent_decisions: tuple[Memory, ...] = field(default_factory=tuple)
    pending_actions: tuple[Memory, ...] = field(default_factory=tuple)

    @property
    def count(self) -> int:
        """Total number of memories in working memory."""
        return (
            len(self.active_blockers)
            + len(self.recent_decisions)
            + len(self.pending_actions)
        )


@dataclass(frozen=True)
class SemanticContext:
    """Semantically relevant memories.

    Contains memories retrieved based on semantic similarity
    to the current project or topic.

    Attributes:
        relevant_learnings: Learnings relevant to current work.
        related_patterns: Patterns and solutions that may apply.
    """

    relevant_learnings: tuple[Memory, ...] = field(default_factory=tuple)
    related_patterns: tuple[Memory, ...] = field(default_factory=tuple)

    @property
    def count(self) -> int:
        """Total number of memories in semantic context."""
        return len(self.relevant_learnings) + len(self.related_patterns)


@dataclass(frozen=True)
class MemoryContext:
    """Structured memory context for injection.

    The complete context that gets serialized to XML and
    injected at session start.

    Attributes:
        project: Project identifier.
        token_budget: Token allocation used.
        working_memory: High-priority working context.
        semantic_context: Semantically relevant memories.
        commands: Available command hints.
        spec_id: Optional spec identifier if in a spec project.
        timestamp: When the context was generated.
    """

    project: str
    token_budget: TokenBudget
    working_memory: WorkingMemory
    semantic_context: SemanticContext
    commands: tuple[str, ...] = field(default_factory=tuple)
    spec_id: str | None = None
    timestamp: datetime = field(default_factory=_utc_now)

    @property
    def total_memories(self) -> int:
        """Total number of memories in the context."""
        return self.working_memory.count + self.semantic_context.count
