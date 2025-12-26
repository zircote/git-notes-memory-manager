"""Context builder for SessionStart hook.

This module provides the ContextBuilder class which constructs XML-structured
memory context for injection at session start. It handles:
- Token budget calculation based on project complexity
- Memory filtering and prioritization
- XML serialization for Claude's additionalContext field

The context is structured into:
- Working Memory: Active blockers, recent decisions, pending actions
- Semantic Context: Relevant learnings, related patterns
- Commands: Available memory commands hint
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from git_notes_memory.config import TOKENS_PER_CHAR, get_project_index_path
from git_notes_memory.exceptions import MemoryIndexError
from git_notes_memory.hooks.config_loader import (
    BudgetMode,
    HookConfig,
    load_hook_config,
)
from git_notes_memory.hooks.models import (
    MemoryContext,
    SemanticContext,
    TokenBudget,
    WorkingMemory,
)
from git_notes_memory.hooks.xml_formatter import XMLBuilder
from git_notes_memory.observability import get_logger

if TYPE_CHECKING:
    from git_notes_memory.index import IndexService
    from git_notes_memory.models import Memory
    from git_notes_memory.recall import RecallService

__all__ = ["ContextBuilder"]

logger = get_logger(__name__)


class ContextBuilder:
    """Builds XML-structured memory context for session injection.

    This class constructs the memory context that gets injected at the start
    of Claude Code sessions. It queries relevant memories, calculates token
    budgets, and formats the output as XML.

    The context is split into:
    - Working Memory: High-priority, immediately relevant content
    - Semantic Context: Contextually relevant learnings and patterns
    - Commands: Brief hint about available memory commands

    Attributes:
        config: Hook configuration settings.

    Example::

        builder = ContextBuilder()
        xml_context = builder.build_context(
            project="my-project",
            session_source="startup",
        )
        # Returns XML string for additionalContext field
    """

    def __init__(
        self,
        *,
        recall_service: RecallService | None = None,
        index_service: IndexService | None = None,
        config: HookConfig | None = None,
    ) -> None:
        """Initialize the context builder.

        Args:
            recall_service: Optional pre-configured RecallService instance.
                If not provided, one will be created lazily.
            index_service: Optional pre-configured IndexService instance.
                If not provided, one will be created lazily.
            config: Optional hook configuration. If not provided, will be
                loaded from environment variables.
        """
        self._recall_service = recall_service
        self._index_service = index_service
        self.config = config or load_hook_config()
        # Track relevance scores for memories (populated during semantic context building)
        self._relevance_map: dict[str, float] = {}

    # -------------------------------------------------------------------------
    # Lazy-loaded Dependencies
    # -------------------------------------------------------------------------

    def _get_recall_service(self) -> RecallService:
        """Get or create the RecallService instance."""
        if self._recall_service is None:
            from git_notes_memory.recall import get_default_service

            self._recall_service = get_default_service()
        return self._recall_service

    def _get_index_service(self) -> IndexService:
        """Get or create the IndexService instance."""
        if self._index_service is None:
            from git_notes_memory.index import IndexService

            self._index_service = IndexService(get_project_index_path())
        return self._index_service

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def build_context(
        self,
        project: str,
        session_source: str = "startup",
        *,
        spec_id: str | None = None,
    ) -> str:
        """Build complete XML memory context for session injection.

        This is the main entry point for context generation. It calculates
        the appropriate token budget, gathers relevant memories, and
        serializes everything to XML.

        Args:
            project: Project identifier (usually from cwd detection).
            session_source: How the session started ("startup", "resume",
                "clear", "compact").
            spec_id: Optional spec identifier for project-specific filtering.

        Returns:
            XML string suitable for Claude's additionalContext field.

        Example::

            context = builder.build_context(
                project="my-app",
                session_source="startup",
                spec_id="SPEC-2025-12-19-001",
            )
        """
        logger.debug(
            "Building context for project=%s, source=%s, spec=%s",
            project,
            session_source,
            spec_id,
        )

        # Clear relevance map for fresh build
        self._relevance_map = {}

        # Calculate token budget
        budget = self.calculate_budget(project)

        # Gather memories within budget
        working_memory = self._build_working_memory(
            project=project,
            spec_id=spec_id,
            token_budget=budget.working_memory,
        )
        semantic_context = self._build_semantic_context(
            project=project,
            spec_id=spec_id,
            token_budget=budget.semantic_context,
        )

        # Build the complete context model
        context = MemoryContext(
            project=project,
            token_budget=budget,
            working_memory=working_memory,
            semantic_context=semantic_context,
            commands=self._get_command_hints(),
            spec_id=spec_id,
            timestamp=datetime.now(UTC),
        )

        # Serialize to XML
        return self.to_xml(context)

    def calculate_budget(self, project: str) -> TokenBudget:
        """Calculate token budget based on project complexity.

        The budget mode determines how tokens are allocated:
        - ADAPTIVE: Uses complexity heuristics to choose a tier
        - FIXED: Uses the configured fixed budget
        - FULL: Uses maximum available budget
        - MINIMAL: Uses minimal budget for fast startup

        Args:
            project: Project identifier for complexity analysis.

        Returns:
            TokenBudget with allocations for each context section.
        """
        mode = self.config.session_start_budget_mode

        if mode == BudgetMode.MINIMAL:
            return TokenBudget.simple(500)

        if mode == BudgetMode.FIXED:
            return TokenBudget.simple(self.config.session_start_fixed_budget)

        if mode == BudgetMode.FULL:
            return TokenBudget.simple(self.config.session_start_max_budget)

        # ADAPTIVE mode - analyze project complexity
        complexity = self._analyze_project_complexity(project)
        total, working, semantic = self.config.get_budget_tier(complexity)

        return TokenBudget(
            total=total,
            working_memory=working,
            semantic_context=semantic,
            commands=min(100, total // 10),
        )

    def filter_memories(
        self,
        memories: list[Memory],
        budget: int,
    ) -> list[Memory]:
        """Filter and prioritize memories within token budget.

        Memories are filtered to fit within the token budget while
        prioritizing by recency and relevance.

        Args:
            memories: List of memories to filter.
            budget: Maximum tokens available for these memories.

        Returns:
            Filtered list of memories that fit within budget.
        """
        if not memories:
            return []

        filtered: list[Memory] = []
        tokens_used = 0

        for memory in memories:
            mem_tokens = self._estimate_memory_tokens(memory)
            if tokens_used + mem_tokens <= budget:
                filtered.append(memory)
                tokens_used += mem_tokens
            else:
                # Budget exhausted
                break

        logger.debug(
            "Filtered %d memories to %d within budget %d (used %d tokens)",
            len(memories),
            len(filtered),
            budget,
            tokens_used,
        )

        return filtered

    def to_xml(self, context: MemoryContext) -> str:
        """Serialize a MemoryContext to XML.

        The XML structure follows Claude Code's expectations for
        additionalContext injection.

        Args:
            context: The memory context to serialize.

        Returns:
            XML string representation.

        Example output::

            <memory_context project="my-project" timestamp="...">
              <working_memory>
                <blockers title="Active Blockers">
                  <memory id="..." namespace="blockers">
                    <summary>...</summary>
                  </memory>
                </blockers>
                ...
              </working_memory>
              <semantic_context>
                ...
              </semantic_context>
              <commands>
                <hint>Use /memory:capture to save insights</hint>
              </commands>
            </memory_context>
        """
        # Calculate total memory count
        total_memories = context.working_memory.count + context.semantic_context.count

        attrs = {
            "project": context.project,
            "timestamp": context.timestamp.isoformat(),
            "memories_retrieved": str(total_memories),
        }
        if context.spec_id:
            attrs["spec"] = context.spec_id

        builder = XMLBuilder("memory_context", attrs)

        # Add visual header when memories are present
        if total_memories > 0:
            builder.add_element(
                "root",
                "recall_notice",
                text=(
                    f"Retrieved {total_memories} memories from prior sessions. "
                    "Reference these when relevant to the current task."
                ),
                priority="high",
            )

        # Build working memory section
        self._add_working_memory_xml(builder, context.working_memory)

        # Build semantic context section
        self._add_semantic_context_xml(builder, context.semantic_context)

        # Add commands hint
        if context.commands:
            cmd_key = builder.add_section("root", "commands")
            for cmd in context.commands:
                builder.add_element(cmd_key, "hint", text=cmd)

        return builder.to_string()

    # -------------------------------------------------------------------------
    # Private Methods - Memory Gathering
    # -------------------------------------------------------------------------

    def _build_working_memory(
        self,
        project: str,  # noqa: ARG002 - Reserved for future project-scoped filtering
        spec_id: str | None,
        token_budget: int,
    ) -> WorkingMemory:
        """Build the working memory context.

        Working memory contains high-priority, immediately relevant content:
        - Active blockers (from "blockers" namespace, recent)
        - Recent decisions (from "decisions" namespace, last 7 days)
        - Pending actions (incomplete tasks, if tracked)
        """
        recall = self._get_recall_service()

        # Budget split: 50% blockers, 40% decisions, 10% actions
        blocker_budget = int(token_budget * 0.5)
        decision_budget = int(token_budget * 0.4)
        action_budget = token_budget - blocker_budget - decision_budget

        # Calculate proportional memory limits from configurable max
        max_memories = self.config.session_start_max_memories
        blocker_limit = max(3, max_memories // 3)  # ~33%
        decision_limit = max(3, max_memories // 3)  # ~33%
        action_limit = max(2, max_memories // 6)  # ~17%

        # Get active blockers (most recent first)
        blockers = recall.get_by_namespace(
            "blockers", spec=spec_id, limit=blocker_limit
        )
        blockers = self.filter_memories(blockers, blocker_budget)

        # Get recent decisions (last 7 days)
        decisions = recall.get_by_namespace(
            "decisions", spec=spec_id, limit=decision_limit
        )
        recent_cutoff = datetime.now(UTC) - timedelta(days=7)
        decisions = [d for d in decisions if d.timestamp >= recent_cutoff]
        decisions = self.filter_memories(decisions, decision_budget)

        # Get pending actions (from progress namespace)
        actions = recall.get_by_namespace("progress", spec=spec_id, limit=action_limit)
        actions = [a for a in actions if a.status in ("pending", "in-progress")]
        actions = self.filter_memories(actions, action_budget)

        return WorkingMemory(
            active_blockers=tuple(blockers),
            recent_decisions=tuple(decisions),
            pending_actions=tuple(actions),
        )

    def _build_semantic_context(
        self,
        project: str,
        spec_id: str | None,  # noqa: ARG002 - Reserved for future spec-scoped filtering
        token_budget: int,
    ) -> SemanticContext:
        """Build the semantic context.

        Semantic context contains contextually relevant learnings and patterns
        based on semantic similarity to the project.
        """
        recall = self._get_recall_service()

        # Budget split: 60% learnings, 40% patterns
        learning_budget = int(token_budget * 0.6)
        pattern_budget = token_budget - learning_budget

        # Calculate proportional memory limits from configurable max
        max_memories = self.config.session_start_max_memories
        learning_limit = max(5, max_memories // 2)  # ~50% for learnings
        pattern_limit = max(2, max_memories // 6)  # ~17% for patterns

        # Search for relevant learnings and track relevance scores
        learnings: list[Memory] = []
        if project:
            results = recall.search(project, k=learning_limit, namespace="learnings")
            for r in results:
                # Convert distance to similarity (lower distance = higher similarity)
                # Using 1/(1+distance) for bounded [0,1] range
                self._relevance_map[r.memory.id] = 1.0 / (1.0 + r.distance)
            learnings = [r.memory for r in results]
        learnings = self.filter_memories(learnings, learning_budget)

        # Search for relevant patterns and track relevance scores
        patterns: list[Memory] = []
        if project:
            results = recall.search(project, k=pattern_limit, namespace="patterns")
            for r in results:
                # Convert distance to similarity (lower distance = higher similarity)
                self._relevance_map[r.memory.id] = 1.0 / (1.0 + r.distance)
            patterns = [r.memory for r in results]
        patterns = self.filter_memories(patterns, pattern_budget)

        return SemanticContext(
            relevant_learnings=tuple(learnings),
            related_patterns=tuple(patterns),
        )

    def _get_command_hints(self) -> tuple[str, ...]:
        """Get brief hints about available memory commands."""
        return (
            "Use /memory:capture to save insights during this session",
            "Use /memory:recall <query> to search past memories",
        )

    # -------------------------------------------------------------------------
    # Private Methods - XML Building
    # -------------------------------------------------------------------------

    def _add_working_memory_xml(
        self,
        builder: XMLBuilder,
        working: WorkingMemory,
    ) -> None:
        """Add working memory section to XML builder."""
        if working.count == 0:
            return

        wm_key = builder.add_section("root", "working_memory")

        # Add blockers
        if working.active_blockers:
            blockers_key = builder.add_section(
                wm_key, "blockers", title="Active Blockers"
            )
            for memory in working.active_blockers:
                builder.add_memory_element(blockers_key, memory, hydration="summary")

        # Add decisions
        if working.recent_decisions:
            decisions_key = builder.add_section(
                wm_key, "decisions", title="Recent Decisions"
            )
            for memory in working.recent_decisions:
                builder.add_memory_element(decisions_key, memory, hydration="summary")

        # Add pending actions
        if working.pending_actions:
            actions_key = builder.add_section(
                wm_key, "pending_actions", title="Pending Actions"
            )
            for memory in working.pending_actions:
                builder.add_memory_element(actions_key, memory, hydration="summary")

    def _add_semantic_context_xml(
        self,
        builder: XMLBuilder,
        semantic: SemanticContext,
    ) -> None:
        """Add semantic context section to XML builder."""
        if semantic.count == 0:
            return

        sc_key = builder.add_section("root", "semantic_context")
        threshold = self.config.session_start_auto_expand_threshold

        # Add learnings with relevance scores
        if semantic.relevant_learnings:
            learnings_key = builder.add_section(
                sc_key, "learnings", title="Relevant Learnings"
            )
            for memory in semantic.relevant_learnings:
                relevance = self._relevance_map.get(memory.id)
                builder.add_memory_element(
                    learnings_key,
                    memory,
                    hydration="summary",
                    relevance=relevance,
                    auto_expand_threshold=threshold,
                )

        # Add patterns with relevance scores
        if semantic.related_patterns:
            patterns_key = builder.add_section(
                sc_key, "patterns", title="Related Patterns"
            )
            for memory in semantic.related_patterns:
                relevance = self._relevance_map.get(memory.id)
                builder.add_memory_element(
                    patterns_key,
                    memory,
                    hydration="summary",
                    relevance=relevance,
                    auto_expand_threshold=threshold,
                )

    # -------------------------------------------------------------------------
    # Private Methods - Analysis
    # -------------------------------------------------------------------------

    def _analyze_project_complexity(self, project: str) -> str:
        """Analyze project complexity to determine budget tier.

        Uses heuristics based on:
        - Number of memories associated with project
        - Presence of spec-scoped memories
        - Recent activity level

        Args:
            project: Project identifier.

        Returns:
            Complexity tier: "simple", "medium", "complex", or "full".
        """
        try:
            index = self._get_index_service()
            stats = index.get_stats()

            # Heuristics for complexity
            total_memories = stats.total_memories

            if total_memories < 10:
                return "simple"
            if total_memories < 50:
                return "medium"
            if total_memories < 200:
                return "complex"
            return "full"

        # QUAL-002: Catch specific exceptions instead of bare Exception
        except (MemoryIndexError, OSError) as e:
            logger.debug("Failed to analyze complexity for %s: %s", project, e)
            return "medium"  # Default to medium on error

    def _estimate_memory_tokens(self, memory: Memory) -> int:
        """Estimate token count for a memory at summary hydration level.

        Args:
            memory: The memory to estimate.

        Returns:
            Estimated token count.
        """
        chars = len(memory.summary or "")
        chars += 50  # Overhead for metadata
        if memory.tags:
            chars += sum(len(t) for t in memory.tags) + len(memory.tags) * 2
        return int(chars * TOKENS_PER_CHAR)
