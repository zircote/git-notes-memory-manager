"""Tests for git_notes_memory.models module.

Tests all dataclasses, enums, and their behavior including:
- Instantiation with required and optional fields
- Immutability (frozen dataclasses)
- Convenience properties and methods
- Enum values and membership
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from git_notes_memory.config import Domain
from git_notes_memory.models import (
    # Result Models
    CaptureAccumulator,
    CaptureResult,
    # Core Models
    CommitInfo,
    HydratedMemory,
    # Enums
    HydrationLevel,
    IndexStats,
    Memory,
    MemoryResult,
    NoteRecord,
    # Pattern Models
    Pattern,
    PatternStatus,
    PatternType,
    SpecContext,
    VerificationResult,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_timestamp() -> datetime:
    """Sample timestamp for tests."""
    return datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)


@pytest.fixture
def sample_memory(sample_timestamp: datetime) -> Memory:
    """Sample Memory instance for tests."""
    return Memory(
        id="decisions:abc123:0",
        commit_sha="abc123def456",
        namespace="decisions",
        summary="Chose PostgreSQL for persistence",
        content="Evaluated SQLite vs PostgreSQL. PostgreSQL wins for concurrency.",
        timestamp=sample_timestamp,
        spec="auth-service",
        phase="implementation",
        tags=("database", "architecture"),
        status="active",
        relates_to=("blockers:xyz789:0",),
    )


@pytest.fixture
def sample_commit_info() -> CommitInfo:
    """Sample CommitInfo instance for tests."""
    return CommitInfo(
        sha="abc123def456789",
        author_name="Test Author",
        author_email="test@example.com",
        date="2025-01-15T10:30:00Z",
        message="feat: add authentication module",
    )


# =============================================================================
# Enum Tests
# =============================================================================


class TestHydrationLevel:
    """Tests for HydrationLevel enum."""

    def test_values(self) -> None:
        """Test enum values are correct."""
        assert HydrationLevel.SUMMARY.value == 1
        assert HydrationLevel.FULL.value == 2
        assert HydrationLevel.FILES.value == 3

    def test_ordering(self) -> None:
        """Test levels can be compared by value."""
        assert HydrationLevel.SUMMARY.value < HydrationLevel.FULL.value
        assert HydrationLevel.FULL.value < HydrationLevel.FILES.value

    def test_membership(self) -> None:
        """Test all expected members exist."""
        members = list(HydrationLevel)
        assert len(members) == 3
        assert HydrationLevel.SUMMARY in members
        assert HydrationLevel.FULL in members
        assert HydrationLevel.FILES in members


class TestPatternType:
    """Tests for PatternType enum."""

    def test_values(self) -> None:
        """Test enum string values."""
        assert PatternType.SUCCESS.value == "success"
        assert PatternType.ANTI_PATTERN.value == "anti-pattern"
        assert PatternType.WORKFLOW.value == "workflow"
        assert PatternType.DECISION.value == "decision"
        assert PatternType.TECHNICAL.value == "technical"

    def test_membership(self) -> None:
        """Test all expected members exist."""
        members = list(PatternType)
        assert len(members) == 5


class TestPatternStatus:
    """Tests for PatternStatus enum."""

    def test_values(self) -> None:
        """Test enum string values."""
        assert PatternStatus.CANDIDATE.value == "candidate"
        assert PatternStatus.VALIDATED.value == "validated"
        assert PatternStatus.PROMOTED.value == "promoted"
        assert PatternStatus.DEPRECATED.value == "deprecated"

    def test_membership(self) -> None:
        """Test all expected members exist."""
        members = list(PatternStatus)
        assert len(members) == 4


# =============================================================================
# Core Model Tests
# =============================================================================


class TestMemory:
    """Tests for Memory dataclass."""

    def test_creation_with_required_fields(self, sample_timestamp: datetime) -> None:
        """Test creating Memory with only required fields."""
        memory = Memory(
            id="test:sha:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test summary",
            content="Test content",
            timestamp=sample_timestamp,
        )
        assert memory.id == "test:sha:0"
        assert memory.commit_sha == "abc123"
        assert memory.namespace == "decisions"
        assert memory.summary == "Test summary"
        assert memory.content == "Test content"
        assert memory.timestamp == sample_timestamp

    def test_default_values(self, sample_timestamp: datetime) -> None:
        """Test default values for optional fields."""
        memory = Memory(
            id="test:sha:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test summary",
            content="Test content",
            timestamp=sample_timestamp,
        )
        assert memory.spec is None
        assert memory.phase is None
        assert memory.tags == ()
        assert memory.status == "active"
        assert memory.relates_to == ()

    def test_creation_with_all_fields(self, sample_memory: Memory) -> None:
        """Test creating Memory with all fields."""
        assert sample_memory.spec == "auth-service"
        assert sample_memory.phase == "implementation"
        assert sample_memory.tags == ("database", "architecture")
        assert sample_memory.relates_to == ("blockers:xyz789:0",)

    def test_immutability(self, sample_memory: Memory) -> None:
        """Test that Memory is immutable."""
        with pytest.raises(FrozenInstanceError):
            sample_memory.summary = "Changed summary"  # type: ignore[misc]

    def test_equality(self, sample_timestamp: datetime) -> None:
        """Test equality comparison."""
        memory1 = Memory(
            id="test:sha:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test",
            content="Content",
            timestamp=sample_timestamp,
        )
        memory2 = Memory(
            id="test:sha:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test",
            content="Content",
            timestamp=sample_timestamp,
        )
        assert memory1 == memory2

    def test_domain_default_is_project(self, sample_timestamp: datetime) -> None:
        """Test that domain defaults to 'project' for backward compatibility."""
        memory = Memory(
            id="test:sha:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test summary",
            content="Test content",
            timestamp=sample_timestamp,
        )
        assert memory.domain == "project"
        assert memory.is_project_domain is True
        assert memory.is_user_domain is False

    def test_domain_explicit_project(self, sample_timestamp: datetime) -> None:
        """Test creating Memory with explicit project domain."""
        memory = Memory(
            id="decisions:abc123:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test summary",
            content="Test content",
            timestamp=sample_timestamp,
            domain="project",
        )
        assert memory.domain == "project"
        assert memory.is_project_domain is True
        assert memory.is_user_domain is False

    def test_domain_explicit_user(self, sample_timestamp: datetime) -> None:
        """Test creating Memory with user domain."""
        memory = Memory(
            id="user:decisions:abc123:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test summary",
            content="Test content",
            timestamp=sample_timestamp,
            domain="user",
        )
        assert memory.domain == "user"
        assert memory.is_user_domain is True
        assert memory.is_project_domain is False

    def test_domain_enum_property(self, sample_timestamp: datetime) -> None:
        """Test domain_enum property returns Domain enum."""
        project_memory = Memory(
            id="test:sha:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test",
            content="Content",
            timestamp=sample_timestamp,
            domain="project",
        )
        user_memory = Memory(
            id="user:test:sha:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test",
            content="Content",
            timestamp=sample_timestamp,
            domain="user",
        )
        assert project_memory.domain_enum == Domain.PROJECT
        assert user_memory.domain_enum == Domain.USER


class TestMemoryResult:
    """Tests for MemoryResult dataclass."""

    def test_creation(self, sample_memory: Memory) -> None:
        """Test creating MemoryResult."""
        result = MemoryResult(memory=sample_memory, distance=0.25)
        assert result.memory == sample_memory
        assert result.distance == 0.25

    def test_convenience_properties(self, sample_memory: Memory) -> None:
        """Test convenience properties delegate to memory."""
        result = MemoryResult(memory=sample_memory, distance=0.25)
        assert result.id == sample_memory.id
        assert result.commit_sha == sample_memory.commit_sha
        assert result.namespace == sample_memory.namespace
        assert result.summary == sample_memory.summary
        assert result.content == sample_memory.content
        assert result.timestamp == sample_memory.timestamp
        assert result.spec == sample_memory.spec
        assert result.phase == sample_memory.phase
        assert result.tags == sample_memory.tags
        assert result.status == sample_memory.status
        assert result.relates_to == sample_memory.relates_to

    def test_score_alias(self, sample_memory: Memory) -> None:
        """Test score property is alias for distance."""
        result = MemoryResult(memory=sample_memory, distance=0.42)
        assert result.score == result.distance == 0.42

    def test_immutability(self, sample_memory: Memory) -> None:
        """Test that MemoryResult is immutable."""
        result = MemoryResult(memory=sample_memory, distance=0.25)
        with pytest.raises(FrozenInstanceError):
            result.distance = 0.5  # type: ignore[misc]

    def test_domain_property(self, sample_memory: Memory) -> None:
        """Test domain property delegates to memory."""
        result = MemoryResult(memory=sample_memory, distance=0.25)
        assert result.domain == sample_memory.domain
        assert result.domain == "project"

    def test_is_user_domain_property(self, sample_timestamp: datetime) -> None:
        """Test is_user_domain property for user memory."""
        user_memory = Memory(
            id="user:decisions:abc:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test",
            content="Content",
            timestamp=sample_timestamp,
            domain="user",
        )
        result = MemoryResult(memory=user_memory, distance=0.25)
        assert result.is_user_domain is True
        assert result.is_project_domain is False

    def test_is_project_domain_property(self, sample_memory: Memory) -> None:
        """Test is_project_domain property for project memory."""
        result = MemoryResult(memory=sample_memory, distance=0.25)
        assert result.is_project_domain is True
        assert result.is_user_domain is False


class TestHydratedMemory:
    """Tests for HydratedMemory dataclass."""

    def test_creation_minimal(self, sample_memory: Memory) -> None:
        """Test creating HydratedMemory with minimal fields."""
        result = MemoryResult(memory=sample_memory, distance=0.1)
        hydrated = HydratedMemory(result=result)
        assert hydrated.result == result
        assert hydrated.full_content is None
        assert hydrated.files == ()
        assert hydrated.commit_info is None

    def test_creation_with_all_fields(
        self, sample_memory: Memory, sample_commit_info: CommitInfo
    ) -> None:
        """Test creating HydratedMemory with all fields."""
        result = MemoryResult(memory=sample_memory, distance=0.1)
        hydrated = HydratedMemory(
            result=result,
            full_content="Full markdown content here",
            files=(("src/main.py", "print('hello')"), ("README.md", "# Project")),
            commit_info=sample_commit_info,
        )
        assert hydrated.full_content == "Full markdown content here"
        assert len(hydrated.files) == 2
        assert hydrated.commit_info == sample_commit_info

    def test_files_dict_property(self, sample_memory: Memory) -> None:
        """Test files_dict convenience property."""
        result = MemoryResult(memory=sample_memory, distance=0.1)
        hydrated = HydratedMemory(
            result=result,
            files=(("src/main.py", "code"), ("README.md", "docs")),
        )
        files_dict = hydrated.files_dict
        assert files_dict == {"src/main.py": "code", "README.md": "docs"}

    def test_immutability(self, sample_memory: Memory) -> None:
        """Test that HydratedMemory is immutable."""
        result = MemoryResult(memory=sample_memory, distance=0.1)
        hydrated = HydratedMemory(result=result)
        with pytest.raises(FrozenInstanceError):
            hydrated.full_content = "changed"  # type: ignore[misc]


class TestSpecContext:
    """Tests for SpecContext dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creating SpecContext with minimal fields."""
        ctx = SpecContext(spec="auth-service")
        assert ctx.spec == "auth-service"
        assert ctx.memories == ()
        assert ctx.total_count == 0
        assert ctx.token_estimate == 0

    def test_creation_with_memories(
        self, sample_memory: Memory, sample_timestamp: datetime
    ) -> None:
        """Test creating SpecContext with memories."""
        memory2 = Memory(
            id="blockers:xyz:0",
            commit_sha="xyz789",
            namespace="blockers",
            summary="API rate limiting",
            content="Third-party API has rate limits.",
            timestamp=sample_timestamp,
            spec="auth-service",
        )
        ctx = SpecContext(
            spec="auth-service",
            memories=(sample_memory, memory2),
            total_count=2,
            token_estimate=500,
        )
        assert len(ctx.memories) == 2
        assert ctx.total_count == 2
        assert ctx.token_estimate == 500

    def test_by_namespace_property(
        self, sample_memory: Memory, sample_timestamp: datetime
    ) -> None:
        """Test by_namespace groups memories correctly."""
        memory2 = Memory(
            id="blockers:xyz:0",
            commit_sha="xyz789",
            namespace="blockers",
            summary="Blocker summary",
            content="Content",
            timestamp=sample_timestamp,
        )
        memory3 = Memory(
            id="decisions:abc:1",
            commit_sha="abc124",
            namespace="decisions",
            summary="Another decision",
            content="Content",
            timestamp=sample_timestamp,
        )
        ctx = SpecContext(
            spec="test",
            memories=(sample_memory, memory2, memory3),
        )
        by_ns = ctx.by_namespace
        assert "decisions" in by_ns
        assert "blockers" in by_ns
        assert len(by_ns["decisions"]) == 2
        assert len(by_ns["blockers"]) == 1


# =============================================================================
# Result Model Tests
# =============================================================================


class TestCaptureResult:
    """Tests for CaptureResult dataclass."""

    def test_successful_capture(self, sample_memory: Memory) -> None:
        """Test successful capture result."""
        result = CaptureResult(
            success=True,
            memory=sample_memory,
            indexed=True,
        )
        assert result.success is True
        assert result.memory == sample_memory
        assert result.indexed is True
        assert result.warning is None

    def test_failed_capture_with_warning(self) -> None:
        """Test failed capture result with warning."""
        result = CaptureResult(
            success=False,
            warning="Embedding service unavailable",
        )
        assert result.success is False
        assert result.memory is None
        assert result.indexed is False
        assert result.warning == "Embedding service unavailable"

    def test_immutability(self) -> None:
        """Test that CaptureResult is immutable."""
        result = CaptureResult(success=True)
        with pytest.raises(FrozenInstanceError):
            result.success = False  # type: ignore[misc]


class TestCaptureAccumulator:
    """Tests for CaptureAccumulator dataclass."""

    def test_creation_empty(self) -> None:
        """Test creating empty accumulator."""
        acc = CaptureAccumulator()
        assert acc.captures == []
        assert acc.count == 0
        assert acc.successful_count == 0

    def test_add_capture(self, sample_memory: Memory) -> None:
        """Test adding captures."""
        acc = CaptureAccumulator()
        result = CaptureResult(success=True, memory=sample_memory, indexed=True)
        acc.add(result)
        assert acc.count == 1
        assert acc.successful_count == 1

    def test_count_properties(self, sample_memory: Memory) -> None:
        """Test count and successful_count properties."""
        acc = CaptureAccumulator()
        acc.add(CaptureResult(success=True, memory=sample_memory))
        acc.add(CaptureResult(success=False, warning="Failed"))
        acc.add(CaptureResult(success=True, memory=sample_memory))

        assert acc.count == 3
        assert acc.successful_count == 2

    def test_by_namespace_property(
        self, sample_memory: Memory, sample_timestamp: datetime
    ) -> None:
        """Test by_namespace groups counts correctly."""
        acc = CaptureAccumulator()
        blocker = Memory(
            id="blockers:x:0",
            commit_sha="x",
            namespace="blockers",
            summary="Test",
            content="C",
            timestamp=sample_timestamp,
        )
        acc.add(CaptureResult(success=True, memory=sample_memory))
        acc.add(CaptureResult(success=True, memory=blocker))
        acc.add(CaptureResult(success=True, memory=sample_memory))

        by_ns = acc.by_namespace
        assert by_ns["decisions"] == 2
        assert by_ns["blockers"] == 1

    def test_summary_empty(self) -> None:
        """Test summary for empty accumulator."""
        acc = CaptureAccumulator()
        assert acc.summary() == "No memories captured this session."

    def test_summary_with_captures(self, sample_memory: Memory) -> None:
        """Test summary with captures."""
        acc = CaptureAccumulator()
        acc.add(CaptureResult(success=True, memory=sample_memory))
        summary = acc.summary()
        assert "Memory Capture Summary" in summary
        assert "Captured: 1 memories" in summary
        assert sample_memory.id in summary

    def test_summary_with_warning(self) -> None:
        """Test summary includes warnings for failed captures without memory."""
        acc = CaptureAccumulator()
        acc.add(CaptureResult(success=False, warning="Embedding service failed"))
        summary = acc.summary()
        assert "Embedding service failed" in summary
        assert "⚠" in summary

    def test_is_mutable(self) -> None:
        """Test that CaptureAccumulator is NOT frozen (mutable)."""
        acc = CaptureAccumulator()
        acc.captures = []  # Should not raise
        assert acc.captures == []


class TestIndexStats:
    """Tests for IndexStats dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creating IndexStats with minimal fields."""
        stats = IndexStats(total_memories=100)
        assert stats.total_memories == 100
        assert stats.by_namespace == ()
        assert stats.by_spec == ()
        assert stats.last_sync is None
        assert stats.index_size_bytes == 0

    def test_creation_with_all_fields(self, sample_timestamp: datetime) -> None:
        """Test creating IndexStats with all fields."""
        stats = IndexStats(
            total_memories=150,
            by_namespace=(("decisions", 50), ("blockers", 30), ("learnings", 70)),
            by_spec=(("auth-service", 80), ("api-gateway", 70)),
            last_sync=sample_timestamp,
            index_size_bytes=1024000,
        )
        assert stats.total_memories == 150
        assert len(stats.by_namespace) == 3
        assert len(stats.by_spec) == 2
        assert stats.last_sync == sample_timestamp
        assert stats.index_size_bytes == 1024000

    def test_dict_properties(self) -> None:
        """Test dict convenience properties."""
        stats = IndexStats(
            total_memories=100,
            by_namespace=(("decisions", 50), ("blockers", 50)),
            by_spec=(("auth", 60), ("api", 40)),
        )
        assert stats.by_namespace_dict == {"decisions": 50, "blockers": 50}
        assert stats.by_spec_dict == {"auth": 60, "api": 40}

    def test_immutability(self) -> None:
        """Test that IndexStats is immutable."""
        stats = IndexStats(total_memories=100)
        with pytest.raises(FrozenInstanceError):
            stats.total_memories = 200  # type: ignore[misc]


class TestVerificationResult:
    """Tests for VerificationResult dataclass."""

    def test_consistent_index(self) -> None:
        """Test result for consistent index."""
        result = VerificationResult(is_consistent=True)
        assert result.is_consistent is True
        assert result.missing_in_index == ()
        assert result.orphaned_in_index == ()
        assert result.mismatched == ()
        assert result.total_issues == 0

    def test_inconsistent_index(self) -> None:
        """Test result for inconsistent index."""
        result = VerificationResult(
            is_consistent=False,
            missing_in_index=("mem1", "mem2"),
            orphaned_in_index=("mem3",),
            mismatched=("mem4", "mem5", "mem6"),
        )
        assert result.is_consistent is False
        assert len(result.missing_in_index) == 2
        assert len(result.orphaned_in_index) == 1
        assert len(result.mismatched) == 3
        assert result.total_issues == 6

    def test_immutability(self) -> None:
        """Test that VerificationResult is immutable."""
        result = VerificationResult(is_consistent=True)
        with pytest.raises(FrozenInstanceError):
            result.is_consistent = False  # type: ignore[misc]


# =============================================================================
# Pattern Model Tests
# =============================================================================


class TestPattern:
    """Tests for Pattern dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creating Pattern with minimal fields."""
        pattern = Pattern(
            name="Error Handling Pattern",
            pattern_type=PatternType.SUCCESS,
            description="Consistent error handling improves debugging.",
        )
        assert pattern.name == "Error Handling Pattern"
        assert pattern.pattern_type == PatternType.SUCCESS
        assert pattern.description == "Consistent error handling improves debugging."

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        pattern = Pattern(
            name="Test",
            pattern_type=PatternType.WORKFLOW,
            description="Desc",
        )
        assert pattern.evidence == ()
        assert pattern.confidence == 0.0
        assert pattern.tags == ()
        assert pattern.status == PatternStatus.CANDIDATE
        assert pattern.first_seen is None
        assert pattern.last_seen is None
        assert pattern.occurrence_count == 1

    def test_creation_with_all_fields(self, sample_timestamp: datetime) -> None:
        """Test creating Pattern with all fields."""
        pattern = Pattern(
            name="Code Review Pattern",
            pattern_type=PatternType.WORKFLOW,
            description="Always review code before merge.",
            evidence=("mem1", "mem2", "mem3"),
            confidence=0.85,
            tags=("quality", "process"),
            status=PatternStatus.VALIDATED,
            first_seen=sample_timestamp,
            last_seen=sample_timestamp,
            occurrence_count=5,
        )
        assert pattern.confidence == 0.85
        assert len(pattern.evidence) == 3
        assert pattern.status == PatternStatus.VALIDATED
        assert pattern.occurrence_count == 5

    def test_immutability(self) -> None:
        """Test that Pattern is immutable."""
        pattern = Pattern(
            name="Test",
            pattern_type=PatternType.TECHNICAL,
            description="Desc",
        )
        with pytest.raises(FrozenInstanceError):
            pattern.name = "Changed"  # type: ignore[misc]


# =============================================================================
# Git Model Tests
# =============================================================================


class TestCommitInfo:
    """Tests for CommitInfo dataclass."""

    def test_creation(self, sample_commit_info: CommitInfo) -> None:
        """Test creating CommitInfo."""
        assert sample_commit_info.sha == "abc123def456789"
        assert sample_commit_info.author_name == "Test Author"
        assert sample_commit_info.author_email == "test@example.com"
        assert sample_commit_info.date == "2025-01-15T10:30:00Z"
        assert sample_commit_info.message == "feat: add authentication module"

    def test_immutability(self, sample_commit_info: CommitInfo) -> None:
        """Test that CommitInfo is immutable."""
        with pytest.raises(FrozenInstanceError):
            sample_commit_info.sha = "changed"  # type: ignore[misc]


class TestNoteRecord:
    """Tests for NoteRecord dataclass."""

    def test_creation_minimal(self) -> None:
        """Test creating NoteRecord with minimal fields."""
        record = NoteRecord(
            commit_sha="abc123",
            namespace="decisions",
        )
        assert record.commit_sha == "abc123"
        assert record.namespace == "decisions"
        assert record.index == 0
        assert record.front_matter == ()
        assert record.body == ""
        assert record.raw == ""

    def test_creation_with_all_fields(self) -> None:
        """Test creating NoteRecord with all fields."""
        record = NoteRecord(
            commit_sha="abc123",
            namespace="decisions",
            index=1,
            front_matter=(("summary", "Test decision"), ("spec", "auth-service")),
            body="Full markdown body content here.",
            raw="---\nsummary: Test decision\n---\nFull markdown body content here.",
        )
        assert record.index == 1
        assert len(record.front_matter) == 2
        assert record.body == "Full markdown body content here."

    def test_front_matter_dict_property(self) -> None:
        """Test front_matter_dict convenience property."""
        record = NoteRecord(
            commit_sha="abc123",
            namespace="decisions",
            front_matter=(
                ("summary", "Test"),
                ("spec", "auth"),
                ("phase", "planning"),
            ),
        )
        fm_dict = record.front_matter_dict
        assert fm_dict == {"summary": "Test", "spec": "auth", "phase": "planning"}

    def test_immutability(self) -> None:
        """Test that NoteRecord is immutable."""
        record = NoteRecord(commit_sha="abc", namespace="test")
        with pytest.raises(FrozenInstanceError):
            record.body = "changed"  # type: ignore[misc]


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_tuples_are_independent(self) -> None:
        """Test that default tuple factories create independent instances."""
        mem1 = Memory(
            id="1",
            commit_sha="a",
            namespace="test",
            summary="s",
            content="c",
            timestamp=datetime.now(UTC),
        )
        mem2 = Memory(
            id="2",
            commit_sha="b",
            namespace="test",
            summary="s",
            content="c",
            timestamp=datetime.now(UTC),
        )
        # Empty tuples are singletons in Python, but this shouldn't cause issues
        assert mem1.tags == mem2.tags == ()

    def test_memory_result_with_zero_distance(self, sample_memory: Memory) -> None:
        """Test MemoryResult with exact match (distance=0)."""
        result = MemoryResult(memory=sample_memory, distance=0.0)
        assert result.distance == 0.0
        assert result.score == 0.0

    def test_capture_accumulator_start_time(self) -> None:
        """Test that start_time is set on creation."""
        before = datetime.now(UTC)
        acc = CaptureAccumulator()
        after = datetime.now(UTC)
        assert before <= acc.start_time <= after

    def test_verification_result_empty_issues(self) -> None:
        """Test VerificationResult with no issues has zero total."""
        result = VerificationResult(is_consistent=True)
        assert result.total_issues == 0

    def test_pattern_confidence_bounds(self) -> None:
        """Test pattern confidence accepts 0.0 to 1.0 range."""
        pattern_low = Pattern(
            name="Low",
            pattern_type=PatternType.SUCCESS,
            description="D",
            confidence=0.0,
        )
        pattern_high = Pattern(
            name="High",
            pattern_type=PatternType.SUCCESS,
            description="D",
            confidence=1.0,
        )
        assert pattern_low.confidence == 0.0
        assert pattern_high.confidence == 1.0
