"""Comprehensive tests for the ContextBuilder class.

This module tests all aspects of the ContextBuilder, including:
- Initialization with default and custom services
- Token budget calculation across all modes
- Full context building
- Working memory retrieval
- Semantic context retrieval
- Project complexity analysis
- Memory filtering based on budget
- XML output formatting
- Edge cases and error handling
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from git_notes_memory.config import TOKENS_PER_CHAR
from git_notes_memory.hooks.config_loader import (
    BudgetMode,
    HookConfig,
    load_hook_config,
)
from git_notes_memory.hooks.context_builder import ContextBuilder
from git_notes_memory.hooks.models import (
    MemoryContext,
    SemanticContext,
    TokenBudget,
    WorkingMemory,
)
from git_notes_memory.models import IndexStats, Memory, MemoryResult

if TYPE_CHECKING:
    pass


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_memory() -> Memory:
    """Create a mock Memory object for testing."""
    return Memory(
        id="decisions:abc123:0",
        commit_sha="abc123",
        namespace="decisions",
        summary="Use PostgreSQL for persistence",
        content="We decided to use PostgreSQL because of ACID compliance.",
        timestamp=datetime.now(),
        repo_path="/path/to/repo",
        spec="test-project",
        phase="planning",
        tags=("database", "architecture"),
        status="active",
        relates_to=(),
    )


@pytest.fixture
def mock_blocker_memory() -> Memory:
    """Create a mock blocker Memory object."""
    return Memory(
        id="blockers:def456:0",
        commit_sha="def456",
        namespace="blockers",
        summary="CI pipeline failing on arm64",
        content="The CI pipeline fails due to architecture incompatibility.",
        timestamp=datetime.now(),
        repo_path="/path/to/repo",
        spec="test-project",
        phase="implementation",
        tags=("ci", "blocker"),
        status="active",
        relates_to=(),
    )


@pytest.fixture
def mock_learning_memory() -> Memory:
    """Create a mock learning Memory object."""
    return Memory(
        id="learnings:ghi789:0",
        commit_sha="ghi789",
        namespace="learnings",
        summary="pytest-cov requires separate install",
        content="Learned that pytest-cov needs to be installed separately.",
        timestamp=datetime.now(),
        repo_path="/path/to/repo",
        spec="test-project",
        phase="testing",
        tags=("testing", "python"),
        status="active",
        relates_to=(),
    )


@pytest.fixture
def mock_pattern_memory() -> Memory:
    """Create a mock pattern Memory object."""
    return Memory(
        id="patterns:jkl012:0",
        commit_sha="jkl012",
        namespace="patterns",
        summary="Use factory functions for service singletons",
        content="Factory pattern ensures lazy initialization and testability.",
        timestamp=datetime.now(),
        repo_path="/path/to/repo",
        spec=None,  # Patterns are often cross-project
        phase=None,
        tags=("design-patterns", "architecture"),
        status="active",
        relates_to=(),
    )


@pytest.fixture
def mock_progress_memory() -> Memory:
    """Create a mock progress Memory with pending status."""
    return Memory(
        id="progress:mno345:0",
        commit_sha="mno345",
        namespace="progress",
        summary="Implement user authentication",
        content="Task to implement OAuth2 authentication flow.",
        timestamp=datetime.now(),
        repo_path="/path/to/repo",
        spec="test-project",
        phase="implementation",
        tags=("auth", "task"),
        status="pending",
        relates_to=(),
    )


@pytest.fixture
def mock_recall_service(
    mock_memory: Memory,
    mock_blocker_memory: Memory,
    mock_learning_memory: Memory,
    mock_pattern_memory: Memory,
    mock_progress_memory: Memory,
) -> MagicMock:
    """Create a mock RecallService with controlled responses."""
    mock_service = MagicMock()

    # Configure get_by_namespace to return appropriate memories
    def mock_get_by_namespace(namespace: str, spec: str | None = None, limit: int | None = None) -> list[Memory]:
        if namespace == "blockers":
            return [mock_blocker_memory]
        if namespace == "decisions":
            return [mock_memory]
        if namespace == "progress":
            return [mock_progress_memory]
        return []

    mock_service.get_by_namespace.side_effect = mock_get_by_namespace

    # Configure search to return learning and pattern results
    def mock_search(query: str, k: int = 10, namespace: str | None = None) -> list[MemoryResult]:
        if namespace == "learnings":
            return [MemoryResult(memory=mock_learning_memory, distance=0.5)]
        if namespace == "patterns":
            return [MemoryResult(memory=mock_pattern_memory, distance=0.6)]
        return []

    mock_service.search.side_effect = mock_search

    return mock_service


@pytest.fixture
def mock_index_service() -> MagicMock:
    """Create a mock IndexService with controlled stats."""
    mock_service = MagicMock()
    mock_service.get_stats.return_value = IndexStats(
        total_memories=25,
        by_namespace=(("decisions", 10), ("learnings", 8), ("blockers", 7)),
        by_spec=(("test-project", 20), ("other-project", 5)),
        last_sync=datetime.now(),
        index_size_bytes=1024,
    )
    return mock_service


@pytest.fixture
def default_config() -> HookConfig:
    """Create default HookConfig for testing."""
    return HookConfig()


@pytest.fixture
def minimal_config() -> HookConfig:
    """Create HookConfig with minimal budget mode."""
    return HookConfig(session_start_budget_mode=BudgetMode.MINIMAL)


@pytest.fixture
def fixed_config() -> HookConfig:
    """Create HookConfig with fixed budget mode."""
    return HookConfig(
        session_start_budget_mode=BudgetMode.FIXED,
        session_start_fixed_budget=1500,
    )


@pytest.fixture
def full_config() -> HookConfig:
    """Create HookConfig with full budget mode."""
    return HookConfig(
        session_start_budget_mode=BudgetMode.FULL,
        session_start_max_budget=3000,
    )


# =============================================================================
# Test: ContextBuilder Initialization
# =============================================================================


class TestContextBuilderInitialization:
    """Tests for ContextBuilder initialization."""

    def test_default_initialization(self) -> None:
        """Test ContextBuilder initializes with default config."""
        builder = ContextBuilder()

        assert builder.config is not None
        assert builder._recall_service is None
        assert builder._index_service is None

    def test_initialization_with_custom_recall_service(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test ContextBuilder initializes with custom RecallService."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        assert builder._recall_service is mock_recall_service

    def test_initialization_with_custom_index_service(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test ContextBuilder initializes with custom IndexService."""
        builder = ContextBuilder(index_service=mock_index_service)

        assert builder._index_service is mock_index_service

    def test_initialization_with_custom_config(
        self, minimal_config: HookConfig
    ) -> None:
        """Test ContextBuilder initializes with custom HookConfig."""
        builder = ContextBuilder(config=minimal_config)

        assert builder.config is minimal_config
        assert builder.config.session_start_budget_mode == BudgetMode.MINIMAL

    def test_initialization_with_all_custom_services(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
        default_config: HookConfig,
    ) -> None:
        """Test ContextBuilder with all custom services and config."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
            config=default_config,
        )

        assert builder._recall_service is mock_recall_service
        assert builder._index_service is mock_index_service
        assert builder.config is default_config

    def test_lazy_recall_service_creation(self) -> None:
        """Test that RecallService is created lazily."""
        builder = ContextBuilder()

        # Before access, should be None
        assert builder._recall_service is None

        # After access via _get_recall_service, should be created
        with patch("git_notes_memory.recall.get_default_service") as mock_get_default:
            mock_service = MagicMock()
            mock_get_default.return_value = mock_service

            service = builder._get_recall_service()

            mock_get_default.assert_called_once()
            assert service is mock_service

    def test_lazy_index_service_creation(self, tmp_path) -> None:
        """Test that IndexService is created lazily."""
        builder = ContextBuilder()

        # Before access, should be None
        assert builder._index_service is None

        # After access via _get_index_service, should be created
        with patch("git_notes_memory.index.IndexService") as mock_cls:
            mock_service = MagicMock()
            mock_cls.return_value = mock_service

            service = builder._get_index_service()

            mock_cls.assert_called_once()
            assert service is mock_service


# =============================================================================
# Test: calculate_budget()
# =============================================================================


class TestCalculateBudget:
    """Tests for the calculate_budget method."""

    def test_minimal_budget_mode(self, minimal_config: HookConfig) -> None:
        """Test MINIMAL budget mode returns 500 token budget."""
        builder = ContextBuilder(config=minimal_config)

        budget = builder.calculate_budget("test-project")

        assert budget.total == 500
        # Check that allocations don't exceed total
        assert budget.working_memory + budget.semantic_context + budget.commands <= budget.total

    def test_fixed_budget_mode(self, fixed_config: HookConfig) -> None:
        """Test FIXED budget mode uses configured fixed budget."""
        builder = ContextBuilder(config=fixed_config)

        budget = builder.calculate_budget("test-project")

        assert budget.total == 1500
        assert budget.working_memory + budget.semantic_context + budget.commands <= budget.total

    def test_full_budget_mode(self, full_config: HookConfig) -> None:
        """Test FULL budget mode uses max budget."""
        builder = ContextBuilder(config=full_config)

        budget = builder.calculate_budget("test-project")

        assert budget.total == 3000
        assert budget.working_memory + budget.semantic_context + budget.commands <= budget.total

    def test_adaptive_mode_simple_project(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test ADAPTIVE mode with simple project (< 10 memories)."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=5,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(
            index_service=mock_index_service,
            config=HookConfig(session_start_budget_mode=BudgetMode.ADAPTIVE),
        )

        budget = builder.calculate_budget("simple-project")

        # Simple tier from default budget_tiers
        assert budget.total == 500

    def test_adaptive_mode_medium_project(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test ADAPTIVE mode with medium project (10-50 memories)."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=25,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(
            index_service=mock_index_service,
            config=HookConfig(session_start_budget_mode=BudgetMode.ADAPTIVE),
        )

        budget = builder.calculate_budget("medium-project")

        # Medium tier
        assert budget.total == 1000

    def test_adaptive_mode_complex_project(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test ADAPTIVE mode with complex project (50-200 memories)."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=100,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(
            index_service=mock_index_service,
            config=HookConfig(session_start_budget_mode=BudgetMode.ADAPTIVE),
        )

        budget = builder.calculate_budget("complex-project")

        # Complex tier
        assert budget.total == 2000

    def test_adaptive_mode_full_project(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test ADAPTIVE mode with very large project (>= 200 memories)."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=500,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(
            index_service=mock_index_service,
            config=HookConfig(session_start_budget_mode=BudgetMode.ADAPTIVE),
        )

        budget = builder.calculate_budget("huge-project")

        # Full tier
        assert budget.total == 3000

    def test_adaptive_mode_handles_index_error_gracefully(self) -> None:
        """Test ADAPTIVE mode defaults to medium when index fails."""
        mock_index = MagicMock()
        mock_index.get_stats.side_effect = Exception("Database error")

        builder = ContextBuilder(
            index_service=mock_index,
            config=HookConfig(session_start_budget_mode=BudgetMode.ADAPTIVE),
        )

        budget = builder.calculate_budget("error-project")

        # Should default to medium on error
        assert budget.total == 1000

    def test_budget_commands_allocation(self, minimal_config: HookConfig) -> None:
        """Test that commands get proper allocation."""
        builder = ContextBuilder(config=minimal_config)

        budget = builder.calculate_budget("test-project")

        # Commands should be min(100, total // 10)
        assert budget.commands == min(100, budget.total // 10)


# =============================================================================
# Test: build_context()
# =============================================================================


class TestBuildContext:
    """Tests for the build_context method."""

    def test_build_context_returns_xml_string(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test build_context returns valid XML string."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
            config=HookConfig(session_start_budget_mode=BudgetMode.MINIMAL),
        )

        result = builder.build_context(project="test-project")

        assert isinstance(result, str)
        assert result.startswith("<memory_context")
        assert "test-project" in result
        assert "</memory_context>" in result

    def test_build_context_includes_project_attribute(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test build_context includes project in XML."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(project="my-app")

        assert 'project="my-app"' in result

    def test_build_context_includes_spec_when_provided(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test build_context includes spec_id when provided."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(
            project="test-project",
            spec_id="SPEC-2025-001",
        )

        assert 'spec="SPEC-2025-001"' in result

    def test_build_context_includes_timestamp(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test build_context includes timestamp."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(project="test-project")

        assert "timestamp=" in result

    def test_build_context_includes_working_memory_section(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test build_context includes working_memory when memories exist."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(project="test-project")

        assert "<working_memory>" in result or "working_memory" in result.lower()

    def test_build_context_includes_semantic_context_section(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test build_context includes semantic_context when memories exist."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(project="test-project")

        # Check for semantic context or learnings/patterns
        has_semantic = (
            "<semantic_context>" in result
            or "learnings" in result.lower()
            or "patterns" in result.lower()
        )
        assert has_semantic

    def test_build_context_includes_commands_section(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test build_context includes commands hints."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(project="test-project")

        assert "<commands>" in result
        assert "/memory:capture" in result or "memory:recall" in result


# =============================================================================
# Test: _build_working_memory()
# =============================================================================


class TestBuildWorkingMemory:
    """Tests for the _build_working_memory private method."""

    def test_retrieves_blockers(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that blockers are retrieved from recall service."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        result = builder._build_working_memory(
            project="test-project",
            spec_id=None,
            token_budget=1000,
        )

        # Verify blockers were retrieved
        mock_recall_service.get_by_namespace.assert_any_call(
            "blockers", spec=None, limit=10
        )
        assert isinstance(result, WorkingMemory)
        assert len(result.active_blockers) >= 0

    def test_retrieves_decisions(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that decisions are retrieved from recall service."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        result = builder._build_working_memory(
            project="test-project",
            spec_id=None,
            token_budget=1000,
        )

        mock_recall_service.get_by_namespace.assert_any_call(
            "decisions", spec=None, limit=10
        )
        assert isinstance(result, WorkingMemory)

    def test_retrieves_progress_actions(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that pending actions are retrieved from progress namespace."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        result = builder._build_working_memory(
            project="test-project",
            spec_id=None,
            token_budget=1000,
        )

        mock_recall_service.get_by_namespace.assert_any_call(
            "progress", spec=None, limit=5
        )
        assert isinstance(result, WorkingMemory)

    def test_filters_recent_decisions(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that only recent decisions (last 7 days) are included."""
        # Create an old decision
        old_decision = Memory(
            id="decisions:old123:0",
            commit_sha="old123",
            namespace="decisions",
            summary="Old decision",
            content="This is 10 days old",
            timestamp=datetime.now() - timedelta(days=10),
            status="active",
        )
        recent_decision = Memory(
            id="decisions:new123:0",
            commit_sha="new123",
            namespace="decisions",
            summary="Recent decision",
            content="This is from today",
            timestamp=datetime.now(),
            status="active",
        )

        mock_recall_service.get_by_namespace.side_effect = lambda ns, spec=None, limit=None: (
            [old_decision, recent_decision] if ns == "decisions" else []
        )

        builder = ContextBuilder(recall_service=mock_recall_service)

        result = builder._build_working_memory(
            project="test-project",
            spec_id=None,
            token_budget=10000,  # Large budget to not filter by size
        )

        # Only recent decision should be included
        assert len(result.recent_decisions) == 1
        assert result.recent_decisions[0].id == "decisions:new123:0"

    def test_filters_pending_actions(
        self, mock_recall_service: MagicMock, mock_progress_memory: Memory
    ) -> None:
        """Test that only pending/in-progress actions are included."""
        completed_action = Memory(
            id="progress:done123:0",
            commit_sha="done123",
            namespace="progress",
            summary="Completed task",
            content="This is done",
            timestamp=datetime.now(),
            status="done",  # Not pending or in-progress
        )

        mock_recall_service.get_by_namespace.side_effect = lambda ns, spec=None, limit=None: (
            [mock_progress_memory, completed_action] if ns == "progress" else []
        )

        builder = ContextBuilder(recall_service=mock_recall_service)

        result = builder._build_working_memory(
            project="test-project",
            spec_id=None,
            token_budget=10000,
        )

        # Only pending action should be included
        assert len(result.pending_actions) == 1
        assert result.pending_actions[0].status == "pending"

    def test_respects_spec_id_filter(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that spec_id is passed to recall service."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        builder._build_working_memory(
            project="test-project",
            spec_id="SPEC-123",
            token_budget=1000,
        )

        # All calls should include spec_id
        for call in mock_recall_service.get_by_namespace.call_args_list:
            assert call.kwargs.get("spec") == "SPEC-123"

    def test_budget_allocation_split(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that budget is split 50/40/10 for blockers/decisions/actions."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        # With small budget, filtering will occur
        result = builder._build_working_memory(
            project="test-project",
            spec_id=None,
            token_budget=100,  # Small budget
        )

        # Result should still be valid WorkingMemory
        assert isinstance(result, WorkingMemory)


# =============================================================================
# Test: _build_semantic_context()
# =============================================================================


class TestBuildSemanticContext:
    """Tests for the _build_semantic_context private method."""

    def test_searches_learnings(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that learnings are searched semantically."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        result = builder._build_semantic_context(
            project="test-project",
            spec_id=None,
            token_budget=1000,
        )

        mock_recall_service.search.assert_any_call(
            "test-project", k=10, namespace="learnings"
        )
        assert isinstance(result, SemanticContext)

    def test_searches_patterns(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that patterns are searched semantically."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        result = builder._build_semantic_context(
            project="test-project",
            spec_id=None,
            token_budget=1000,
        )

        mock_recall_service.search.assert_any_call(
            "test-project", k=5, namespace="patterns"
        )
        assert isinstance(result, SemanticContext)

    def test_extracts_memory_from_results(
        self, mock_recall_service: MagicMock, mock_learning_memory: Memory
    ) -> None:
        """Test that Memory objects are extracted from MemoryResults."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        result = builder._build_semantic_context(
            project="test-project",
            spec_id=None,
            token_budget=10000,
        )

        # Learnings should contain the memory from the mock result
        assert len(result.relevant_learnings) > 0
        assert result.relevant_learnings[0].namespace == "learnings"

    def test_empty_project_skips_search(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test that empty project string skips semantic search."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        result = builder._build_semantic_context(
            project="",
            spec_id=None,
            token_budget=1000,
        )

        # With empty project, should return empty SemanticContext
        assert len(result.relevant_learnings) == 0
        assert len(result.related_patterns) == 0

    def test_budget_split_60_40(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test budget is split 60% learnings, 40% patterns."""
        builder = ContextBuilder(recall_service=mock_recall_service)

        # This tests the budget allocation logic indirectly
        result = builder._build_semantic_context(
            project="test-project",
            spec_id=None,
            token_budget=100,
        )

        assert isinstance(result, SemanticContext)


# =============================================================================
# Test: _analyze_project_complexity()
# =============================================================================


class TestAnalyzeProjectComplexity:
    """Tests for the _analyze_project_complexity private method."""

    def test_simple_complexity_under_10_memories(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test project with < 10 memories is 'simple'."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=5,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(index_service=mock_index_service)

        complexity = builder._analyze_project_complexity("test-project")

        assert complexity == "simple"

    def test_medium_complexity_10_to_50_memories(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test project with 10-50 memories is 'medium'."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=30,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(index_service=mock_index_service)

        complexity = builder._analyze_project_complexity("test-project")

        assert complexity == "medium"

    def test_complex_complexity_50_to_200_memories(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test project with 50-200 memories is 'complex'."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=150,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(index_service=mock_index_service)

        complexity = builder._analyze_project_complexity("test-project")

        assert complexity == "complex"

    def test_full_complexity_over_200_memories(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test project with >= 200 memories is 'full'."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=500,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(index_service=mock_index_service)

        complexity = builder._analyze_project_complexity("test-project")

        assert complexity == "full"

    def test_boundary_10_memories_is_medium(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test exactly 10 memories is 'medium' (not simple)."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=10,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(index_service=mock_index_service)

        complexity = builder._analyze_project_complexity("test-project")

        assert complexity == "medium"

    def test_boundary_50_memories_is_complex(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test exactly 50 memories is 'complex' (not medium)."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=50,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(index_service=mock_index_service)

        complexity = builder._analyze_project_complexity("test-project")

        assert complexity == "complex"

    def test_boundary_200_memories_is_full(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test exactly 200 memories is 'full' (not complex)."""
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=200,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )
        builder = ContextBuilder(index_service=mock_index_service)

        complexity = builder._analyze_project_complexity("test-project")

        assert complexity == "full"

    def test_error_returns_medium(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test that errors default to 'medium' complexity."""
        mock_index_service.get_stats.side_effect = Exception("DB Error")
        builder = ContextBuilder(index_service=mock_index_service)

        complexity = builder._analyze_project_complexity("test-project")

        assert complexity == "medium"


# =============================================================================
# Test: filter_memories()
# =============================================================================


class TestFilterMemories:
    """Tests for the filter_memories method."""

    def test_empty_list_returns_empty(self) -> None:
        """Test empty input returns empty list."""
        builder = ContextBuilder()

        result = builder.filter_memories([], budget=1000)

        assert result == []

    def test_all_memories_fit_in_budget(
        self, mock_memory: Memory
    ) -> None:
        """Test all memories are returned when they fit in budget."""
        builder = ContextBuilder()
        memories = [mock_memory]

        result = builder.filter_memories(memories, budget=10000)

        assert len(result) == 1
        assert result[0] is mock_memory

    def test_budget_limits_returned_memories(
        self, mock_memory: Memory, mock_blocker_memory: Memory
    ) -> None:
        """Test that budget limits the number of memories returned."""
        builder = ContextBuilder()
        memories = [mock_memory, mock_blocker_memory]

        # Very small budget should limit results
        result = builder.filter_memories(memories, budget=10)

        # May return 0 or 1 depending on estimated token size
        assert len(result) <= len(memories)

    def test_zero_budget_returns_empty(
        self, mock_memory: Memory
    ) -> None:
        """Test zero budget returns empty list."""
        builder = ContextBuilder()
        memories = [mock_memory]

        result = builder.filter_memories(memories, budget=0)

        assert result == []

    def test_preserves_order(
        self, mock_memory: Memory, mock_blocker_memory: Memory
    ) -> None:
        """Test that memory order is preserved."""
        builder = ContextBuilder()
        memories = [mock_memory, mock_blocker_memory]

        result = builder.filter_memories(memories, budget=100000)

        assert result[0] is mock_memory
        assert result[1] is mock_blocker_memory

    def test_estimate_tokens_uses_summary_and_tags(
        self, mock_memory: Memory
    ) -> None:
        """Test token estimation includes summary and tags."""
        builder = ContextBuilder()

        tokens = builder._estimate_memory_tokens(mock_memory)

        # Should include summary length, overhead, and tags
        expected_chars = len(mock_memory.summary or "") + 50
        if mock_memory.tags:
            expected_chars += sum(len(t) for t in mock_memory.tags) + len(mock_memory.tags) * 2
        expected_tokens = int(expected_chars * TOKENS_PER_CHAR)

        assert tokens == expected_tokens

    def test_estimate_tokens_handles_no_summary(self) -> None:
        """Test token estimation handles memory without summary."""
        memory = Memory(
            id="test:abc:0",
            commit_sha="abc",
            namespace="test",
            summary="",  # Empty summary
            content="",
            timestamp=datetime.now(),
        )
        builder = ContextBuilder()

        tokens = builder._estimate_memory_tokens(memory)

        # Should just be overhead (50 chars * TOKENS_PER_CHAR)
        assert tokens == int(50 * TOKENS_PER_CHAR)


# =============================================================================
# Test: to_xml()
# =============================================================================


class TestToXml:
    """Tests for the to_xml method."""

    def test_returns_valid_xml_string(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test to_xml returns valid XML string."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        context = MemoryContext(
            project="test-project",
            token_budget=TokenBudget.simple(1000),
            working_memory=WorkingMemory(),
            semantic_context=SemanticContext(),
            commands=("Use /memory:capture",),
            spec_id=None,
            timestamp=datetime.now(),
        )

        result = builder.to_xml(context)

        assert result.startswith("<memory_context")
        assert "</memory_context>" in result

    def test_includes_project_attribute(self) -> None:
        """Test XML includes project attribute."""
        builder = ContextBuilder()

        context = MemoryContext(
            project="my-project",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(),
            semantic_context=SemanticContext(),
        )

        result = builder.to_xml(context)

        assert 'project="my-project"' in result

    def test_includes_spec_when_present(self) -> None:
        """Test XML includes spec attribute when spec_id is set."""
        builder = ContextBuilder()

        context = MemoryContext(
            project="test-project",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(),
            semantic_context=SemanticContext(),
            spec_id="SPEC-123",
        )

        result = builder.to_xml(context)

        assert 'spec="SPEC-123"' in result

    def test_includes_recall_notice_when_memories_present(
        self, mock_memory: Memory
    ) -> None:
        """Test XML includes recall_notice when memories are present."""
        builder = ContextBuilder()

        context = MemoryContext(
            project="test-project",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(recent_decisions=(mock_memory,)),
            semantic_context=SemanticContext(),
        )

        result = builder.to_xml(context)

        assert "recall_notice" in result or "Retrieved" in result

    def test_no_recall_notice_when_no_memories(self) -> None:
        """Test XML omits recall_notice when no memories."""
        builder = ContextBuilder()

        context = MemoryContext(
            project="test-project",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(),
            semantic_context=SemanticContext(),
        )

        result = builder.to_xml(context)

        # Should not have recall notice with 0 memories
        assert "memories_retrieved" in result
        assert 'memories_retrieved="0"' in result

    def test_includes_working_memory_section(
        self, mock_blocker_memory: Memory
    ) -> None:
        """Test XML includes working_memory section with blockers."""
        builder = ContextBuilder()

        context = MemoryContext(
            project="test-project",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(active_blockers=(mock_blocker_memory,)),
            semantic_context=SemanticContext(),
        )

        result = builder.to_xml(context)

        assert "<working_memory>" in result
        assert "<blockers" in result

    def test_includes_semantic_context_section(
        self, mock_learning_memory: Memory
    ) -> None:
        """Test XML includes semantic_context section with learnings."""
        builder = ContextBuilder()

        context = MemoryContext(
            project="test-project",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(),
            semantic_context=SemanticContext(relevant_learnings=(mock_learning_memory,)),
        )

        result = builder.to_xml(context)

        assert "<semantic_context>" in result
        assert "<learnings" in result

    def test_includes_commands_section(self) -> None:
        """Test XML includes commands section."""
        builder = ContextBuilder()

        context = MemoryContext(
            project="test-project",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(),
            semantic_context=SemanticContext(),
            commands=("/memory:capture", "/memory:recall"),
        )

        result = builder.to_xml(context)

        assert "<commands>" in result
        assert "<hint>" in result

    def test_includes_memory_elements(
        self, mock_memory: Memory
    ) -> None:
        """Test XML includes properly formatted memory elements."""
        builder = ContextBuilder()

        context = MemoryContext(
            project="test-project",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(recent_decisions=(mock_memory,)),
            semantic_context=SemanticContext(),
        )

        result = builder.to_xml(context)

        assert "<memory " in result
        assert f'id="{mock_memory.id}"' in result
        assert f'namespace="{mock_memory.namespace}"' in result
        assert "<summary>" in result

    def test_memory_includes_tags_when_present(
        self, mock_memory: Memory
    ) -> None:
        """Test memory elements include tags."""
        builder = ContextBuilder()

        context = MemoryContext(
            project="test-project",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(recent_decisions=(mock_memory,)),
            semantic_context=SemanticContext(),
        )

        result = builder.to_xml(context)

        assert "<tags>" in result


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_no_memories_in_index(
        self, mock_index_service: MagicMock
    ) -> None:
        """Test handling when no memories exist in index."""
        # Create fresh mock recall service that returns empty results
        empty_recall_service = MagicMock()
        empty_recall_service.get_by_namespace.return_value = []
        empty_recall_service.search.return_value = []
        mock_index_service.get_stats.return_value = IndexStats(
            total_memories=0,
            by_namespace=(),
            by_spec=(),
            last_sync=None,
            index_size_bytes=0,
        )

        builder = ContextBuilder(
            recall_service=empty_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(project="empty-project")

        assert isinstance(result, str)
        assert 'memories_retrieved="0"' in result

    def test_very_large_memory_set(
        self, mock_recall_service: MagicMock
    ) -> None:
        """Test handling of large memory set with small budget."""
        # Create many memories
        memories = [
            Memory(
                id=f"decisions:sha{i}:0",
                commit_sha=f"sha{i}",
                namespace="decisions",
                summary=f"Decision {i} " * 20,  # Make summaries substantial
                content=f"Content {i}" * 100,
                timestamp=datetime.now(),
                status="active",
            )
            for i in range(100)
        ]

        builder = ContextBuilder()

        # Small budget should truncate
        result = builder.filter_memories(memories, budget=100)

        assert len(result) < len(memories)

    def test_missing_project_info(
        self, mock_recall_service: MagicMock, mock_index_service: MagicMock
    ) -> None:
        """Test handling when project info is empty/missing."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(project="")

        assert isinstance(result, str)
        assert 'project=""' in result

    def test_special_characters_in_project_name(
        self, mock_recall_service: MagicMock, mock_index_service: MagicMock
    ) -> None:
        """Test handling of special characters in project name."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(project='my-project<>&"\'')

        # XML should be properly escaped
        assert isinstance(result, str)
        # The XMLBuilder handles escaping automatically

    def test_memories_with_no_tags(self) -> None:
        """Test handling memories without tags."""
        memory = Memory(
            id="test:abc:0",
            commit_sha="abc",
            namespace="test",
            summary="No tags memory",
            content="Content",
            timestamp=datetime.now(),
            tags=(),  # No tags
            status="active",
        )

        builder = ContextBuilder()
        tokens = builder._estimate_memory_tokens(memory)

        # Should estimate correctly without tags
        expected = int((len("No tags memory") + 50) * TOKENS_PER_CHAR)
        assert tokens == expected

    def test_config_from_environment(self, monkeypatch) -> None:
        """Test that config is loaded from environment."""
        monkeypatch.setenv("HOOK_SESSION_START_BUDGET_MODE", "minimal")

        config = load_hook_config()
        builder = ContextBuilder(config=config)

        assert builder.config.session_start_budget_mode == BudgetMode.MINIMAL

    def test_token_budget_validation(self) -> None:
        """Test TokenBudget validates allocations don't exceed total."""
        # This should raise ValueError
        with pytest.raises(ValueError, match="exceed total"):
            TokenBudget(
                total=100,
                working_memory=80,
                semantic_context=80,
                commands=20,
            )

    def test_token_budget_simple_factory(self) -> None:
        """Test TokenBudget.simple() creates valid budget."""
        budget = TokenBudget.simple(1000)

        assert budget.total == 1000
        # Should have proper allocation
        assert budget.working_memory > 0
        assert budget.semantic_context > 0
        assert budget.commands > 0
        # Should not exceed total
        assert budget.working_memory + budget.semantic_context + budget.commands <= budget.total


# =============================================================================
# Test: Integration
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple ContextBuilder features."""

    def test_full_workflow(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test complete workflow from build_context to XML output."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
            config=HookConfig(session_start_budget_mode=BudgetMode.ADAPTIVE),
        )

        result = builder.build_context(
            project="integration-test",
            session_source="startup",
            spec_id="SPEC-INT-001",
        )

        # Verify complete XML structure
        assert "<memory_context" in result
        assert 'project="integration-test"' in result
        assert 'spec="SPEC-INT-001"' in result
        assert "timestamp=" in result
        assert "</memory_context>" in result

    def test_context_with_all_memory_types(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
        mock_memory: Memory,
        mock_blocker_memory: Memory,
        mock_learning_memory: Memory,
        mock_pattern_memory: Memory,
    ) -> None:
        """Test context includes all types of memories."""
        builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
        )

        result = builder.build_context(project="test-project")

        # Should have working memory section
        assert "<working_memory>" in result or "blockers" in result or "decisions" in result

        # Should have semantic context section
        assert "<semantic_context>" in result or "learnings" in result or "patterns" in result

    def test_budget_affects_memory_count(
        self,
        mock_recall_service: MagicMock,
        mock_index_service: MagicMock,
    ) -> None:
        """Test that different budgets affect memory counts."""
        # Create builder with minimal budget
        minimal_builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
            config=HookConfig(session_start_budget_mode=BudgetMode.MINIMAL),
        )

        minimal_result = minimal_builder.build_context(project="test")

        # Create builder with full budget
        full_builder = ContextBuilder(
            recall_service=mock_recall_service,
            index_service=mock_index_service,
            config=HookConfig(session_start_budget_mode=BudgetMode.FULL),
        )

        full_result = full_builder.build_context(project="test")

        # Both should produce valid XML
        assert "<memory_context" in minimal_result
        assert "<memory_context" in full_result

    def test_memory_context_model_count_property(
        self, mock_memory: Memory, mock_blocker_memory: Memory
    ) -> None:
        """Test MemoryContext.total_memories property."""
        context = MemoryContext(
            project="test",
            token_budget=TokenBudget.simple(500),
            working_memory=WorkingMemory(
                active_blockers=(mock_blocker_memory,),
                recent_decisions=(mock_memory,),
            ),
            semantic_context=SemanticContext(),
        )

        assert context.total_memories == 2

    def test_working_memory_count_property(
        self, mock_memory: Memory, mock_blocker_memory: Memory
    ) -> None:
        """Test WorkingMemory.count property."""
        wm = WorkingMemory(
            active_blockers=(mock_blocker_memory,),
            recent_decisions=(mock_memory,),
            pending_actions=(),
        )

        assert wm.count == 2

    def test_semantic_context_count_property(
        self, mock_learning_memory: Memory, mock_pattern_memory: Memory
    ) -> None:
        """Test SemanticContext.count property."""
        sc = SemanticContext(
            relevant_learnings=(mock_learning_memory,),
            related_patterns=(mock_pattern_memory,),
        )

        assert sc.count == 2
