"""Tests for the IndexService module.

Tests SQLite + sqlite-vec database operations including:
- Database initialization and schema creation
- Memory CRUD operations
- Vector similarity search
- Batch operations
- Statistics and utilities
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

# Filter sqlite3 ResourceWarning that can occur during test teardown
# This is a known issue with pytest's unraisable exception handling
pytestmark = pytest.mark.filterwarnings(
    "ignore:Exception ignored in:pytest.PytestUnraisableExceptionWarning"
)

from git_notes_memory.exceptions import MemoryIndexError
from git_notes_memory.index import IndexService
from git_notes_memory.models import Memory

if TYPE_CHECKING:
    pass


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_memory() -> Memory:
    """Create a sample Memory for testing."""
    return Memory(
        id="decisions:abc123:0",
        commit_sha="abc123def456",
        namespace="decisions",
        summary="Chose PostgreSQL for data layer",
        content="We evaluated several database options...",
        timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
        spec="my-project",
        phase="planning",
        tags=("database", "architecture"),
        status="active",
        relates_to=("decisions:abc123:1",),
    )


@pytest.fixture
def sample_embedding() -> list[float]:
    """Create a sample 384-dimension embedding."""
    return [0.1] * 384


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_index.db"


@pytest.fixture
def index_service(db_path: Path) -> IndexService:
    """Create and initialize an IndexService for testing."""
    service = IndexService(db_path)
    service.initialize()
    yield service
    service.close()


# =============================================================================
# Test: Initialization
# =============================================================================


class TestInitialization:
    """Test IndexService initialization."""

    def test_init_with_default_path(self) -> None:
        """Test initialization uses default path when none provided."""
        with patch("git_notes_memory.index.get_index_path") as mock_path:
            mock_path.return_value = Path("/tmp/default.db")
            service = IndexService()
            assert service.db_path == Path("/tmp/default.db")

    def test_init_with_custom_path(self, db_path: Path) -> None:
        """Test initialization with custom path."""
        service = IndexService(db_path)
        assert service.db_path == db_path

    def test_is_initialized_false_before_init(self, db_path: Path) -> None:
        """Test is_initialized is False before initialize()."""
        service = IndexService(db_path)
        assert service.is_initialized is False

    def test_is_initialized_true_after_init(self, db_path: Path) -> None:
        """Test is_initialized is True after initialize()."""
        service = IndexService(db_path)
        service.initialize()
        assert service.is_initialized is True
        service.close()

    def test_initialize_creates_directory(self, tmp_path: Path) -> None:
        """Test initialize creates parent directories."""
        nested_path = tmp_path / "nested" / "dir" / "index.db"
        service = IndexService(nested_path)
        service.initialize()
        assert nested_path.parent.exists()
        service.close()

    def test_initialize_creates_tables(self, db_path: Path) -> None:
        """Test initialize creates required tables."""
        service = IndexService(db_path)
        service.initialize()

        # Check tables exist
        cursor = service._conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]

        assert "memories" in tables
        assert "metadata" in tables
        # vec_memories is a virtual table
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' OR sql LIKE '%VIRTUAL%'"
        )

        service.close()

    def test_initialize_idempotent(self, db_path: Path) -> None:
        """Test initialize can be called multiple times safely."""
        service = IndexService(db_path)
        service.initialize()
        service.initialize()  # Should not raise
        assert service.is_initialized is True
        service.close()

    def test_initialize_sets_schema_version(self, db_path: Path) -> None:
        """Test initialize sets schema version in metadata."""
        service = IndexService(db_path)
        service.initialize()

        cursor = service._conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = 'schema_version'")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "2"  # Schema v2 adds repo_path column

        service.close()

    def test_initialize_sets_last_sync(self, db_path: Path) -> None:
        """Test initialize sets last_sync in metadata."""
        service = IndexService(db_path)
        service.initialize()

        cursor = service._conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key = 'last_sync'")
        row = cursor.fetchone()
        assert row is not None
        # Should be a valid ISO timestamp
        datetime.fromisoformat(row[0])

        service.close()

    def test_close_resets_initialized(self, db_path: Path) -> None:
        """Test close resets is_initialized to False."""
        service = IndexService(db_path)
        service.initialize()
        assert service.is_initialized is True
        service.close()
        assert service.is_initialized is False

    def test_close_can_be_called_multiple_times(self, db_path: Path) -> None:
        """Test close can be called safely multiple times."""
        service = IndexService(db_path)
        service.initialize()
        service.close()
        service.close()  # Should not raise


class TestInitializationErrors:
    """Test error handling during initialization."""

    def test_sqlite_vec_load_failure(self, db_path: Path) -> None:
        """Test error when sqlite-vec fails to load."""
        service = IndexService(db_path)

        with patch("git_notes_memory.index.sqlite_vec.load") as mock_load:
            mock_load.side_effect = Exception("Extension not found")
            with pytest.raises(MemoryIndexError) as exc_info:
                service.initialize()

            assert "sqlite-vec" in exc_info.value.message


# =============================================================================
# Test: Insert Operations
# =============================================================================


class TestInsertOperations:
    """Test memory insert operations."""

    def test_insert_memory(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test inserting a memory without embedding."""
        result = index_service.insert(sample_memory)
        assert result is True

        # Verify it was inserted
        retrieved = index_service.get(sample_memory.id)
        assert retrieved is not None
        assert retrieved.id == sample_memory.id
        assert retrieved.summary == sample_memory.summary

    def test_insert_memory_with_embedding(
        self,
        index_service: IndexService,
        sample_memory: Memory,
        sample_embedding: list[float],
    ) -> None:
        """Test inserting a memory with embedding."""
        result = index_service.insert(sample_memory, sample_embedding)
        assert result is True

        # Verify embedding was stored
        assert index_service.has_embedding(sample_memory.id) is True

    def test_insert_duplicate_raises_error(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test inserting duplicate memory raises error."""
        index_service.insert(sample_memory)

        with pytest.raises(MemoryIndexError) as exc_info:
            index_service.insert(sample_memory)

        assert "already exists" in exc_info.value.message

    def test_insert_invalid_type_raises_error(
        self,
        index_service: IndexService,
    ) -> None:
        """Test inserting non-Memory object raises error."""
        with pytest.raises(MemoryIndexError) as exc_info:
            index_service.insert({"id": "test"})  # type: ignore[arg-type]

        assert "Invalid memory object" in exc_info.value.message

    def test_insert_preserves_all_fields(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test all memory fields are preserved on insert."""
        index_service.insert(sample_memory)
        retrieved = index_service.get(sample_memory.id)

        assert retrieved is not None
        assert retrieved.commit_sha == sample_memory.commit_sha
        assert retrieved.namespace == sample_memory.namespace
        assert retrieved.summary == sample_memory.summary
        assert retrieved.content == sample_memory.content
        assert retrieved.timestamp == sample_memory.timestamp
        assert retrieved.spec == sample_memory.spec
        assert retrieved.phase == sample_memory.phase
        assert retrieved.tags == sample_memory.tags
        assert retrieved.status == sample_memory.status
        assert retrieved.relates_to == sample_memory.relates_to

    def test_insert_memory_with_none_optional_fields(
        self,
        index_service: IndexService,
    ) -> None:
        """Test inserting memory with None optional fields."""
        memory = Memory(
            id="test:123:0",
            commit_sha="abc123",
            namespace="learnings",
            summary="A test memory",
            content="Test content",
            timestamp=datetime.now(UTC),
            spec=None,
            phase=None,
            tags=(),
            status="active",
            relates_to=(),
        )
        result = index_service.insert(memory)
        assert result is True

        retrieved = index_service.get(memory.id)
        assert retrieved is not None
        assert retrieved.spec is None
        assert retrieved.phase is None
        assert retrieved.tags == ()


class TestBatchInsertOperations:
    """Test batch insert operations."""

    def test_insert_batch(
        self,
        index_service: IndexService,
    ) -> None:
        """Test batch insert multiple memories."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(5)
        ]

        count = index_service.insert_batch(memories)
        assert count == 5

        # Verify all were inserted
        for memory in memories:
            assert index_service.exists(memory.id)

    def test_insert_batch_with_embeddings(
        self,
        index_service: IndexService,
    ) -> None:
        """Test batch insert with embeddings."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(3)
        ]
        embeddings = [[0.1 * i] * 384 for i in range(3)]

        count = index_service.insert_batch(memories, embeddings)
        assert count == 3

        for memory in memories:
            assert index_service.has_embedding(memory.id)

    def test_insert_batch_skips_duplicates(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test batch insert skips duplicates without failing."""
        index_service.insert(sample_memory)

        memories = [
            sample_memory,  # Duplicate
            Memory(
                id="new:123:0",
                commit_sha="new123",
                namespace="learnings",
                summary="New memory",
                content="New content",
                timestamp=datetime.now(UTC),
            ),
        ]

        count = index_service.insert_batch(memories)
        assert count == 1  # Only the new one

    def test_insert_batch_empty_list(
        self,
        index_service: IndexService,
    ) -> None:
        """Test batch insert with empty list."""
        count = index_service.insert_batch([])
        assert count == 0

    def test_insert_batch_mismatched_embeddings_raises_error(
        self,
        index_service: IndexService,
    ) -> None:
        """Test batch insert with mismatched embedding count raises error."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(3)
        ]
        embeddings = [[0.1] * 384, [0.2] * 384]  # Only 2 embeddings for 3 memories

        with pytest.raises(MemoryIndexError) as exc_info:
            index_service.insert_batch(memories, embeddings)

        assert "must match" in exc_info.value.message


# =============================================================================
# Test: Read Operations
# =============================================================================


class TestReadOperations:
    """Test memory read operations."""

    def test_get_existing_memory(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test getting an existing memory."""
        index_service.insert(sample_memory)
        retrieved = index_service.get(sample_memory.id)

        assert retrieved is not None
        assert retrieved.id == sample_memory.id

    def test_get_nonexistent_memory(
        self,
        index_service: IndexService,
    ) -> None:
        """Test getting a nonexistent memory returns None."""
        result = index_service.get("nonexistent:id:0")
        assert result is None

    def test_get_batch(
        self,
        index_service: IndexService,
    ) -> None:
        """Test getting multiple memories by ID."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(3)
        ]
        index_service.insert_batch(memories)

        ids = [m.id for m in memories]
        retrieved = index_service.get_batch(ids)

        assert len(retrieved) == 3
        assert all(m.id in ids for m in retrieved)

    def test_get_batch_partial(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test get_batch with some nonexistent IDs."""
        index_service.insert(sample_memory)

        ids = [sample_memory.id, "nonexistent:id:0"]
        retrieved = index_service.get_batch(ids)

        assert len(retrieved) == 1
        assert retrieved[0].id == sample_memory.id

    def test_get_batch_empty_list(
        self,
        index_service: IndexService,
    ) -> None:
        """Test get_batch with empty list."""
        result = index_service.get_batch([])
        assert result == []

    def test_exists_true(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test exists returns True for existing memory."""
        index_service.insert(sample_memory)
        assert index_service.exists(sample_memory.id) is True

    def test_exists_false(
        self,
        index_service: IndexService,
    ) -> None:
        """Test exists returns False for nonexistent memory."""
        assert index_service.exists("nonexistent:id:0") is False

    def test_get_all_ids(
        self,
        index_service: IndexService,
    ) -> None:
        """Test getting all memory IDs."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(3)
        ]
        index_service.insert_batch(memories)

        ids = index_service.get_all_ids()
        assert len(ids) == 3
        assert all(m.id in ids for m in memories)


class TestReadByFilters:
    """Test read operations with filters."""

    def test_get_by_spec(
        self,
        index_service: IndexService,
    ) -> None:
        """Test getting memories by spec."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
                spec="project-a" if i < 2 else "project-b",
            )
            for i in range(4)
        ]
        index_service.insert_batch(memories)

        results = index_service.get_by_spec("project-a")
        assert len(results) == 2
        assert all(m.spec == "project-a" for m in results)

    def test_get_by_spec_with_namespace(
        self,
        index_service: IndexService,
    ) -> None:
        """Test getting memories by spec and namespace."""
        memories = [
            Memory(
                id="test:1:0",
                commit_sha="sha1",
                namespace="decisions",
                summary="Decision 1",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-a",
            ),
            Memory(
                id="test:2:0",
                commit_sha="sha2",
                namespace="learnings",
                summary="Learning 1",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-a",
            ),
        ]
        index_service.insert_batch(memories)

        results = index_service.get_by_spec("project-a", namespace="decisions")
        assert len(results) == 1
        assert results[0].namespace == "decisions"

    def test_get_by_spec_with_limit(
        self,
        index_service: IndexService,
    ) -> None:
        """Test get_by_spec with limit."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
                spec="project-a",
            )
            for i in range(5)
        ]
        index_service.insert_batch(memories)

        results = index_service.get_by_spec("project-a", limit=2)
        assert len(results) == 2

    def test_get_by_commit(
        self,
        index_service: IndexService,
    ) -> None:
        """Test getting memories by commit SHA."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha="same-commit" if i < 2 else f"commit{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(4)
        ]
        index_service.insert_batch(memories)

        results = index_service.get_by_commit("same-commit")
        assert len(results) == 2

    def test_get_by_namespace(
        self,
        index_service: IndexService,
    ) -> None:
        """Test getting memories by namespace."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="decisions" if i % 2 == 0 else "learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(4)
        ]
        index_service.insert_batch(memories)

        results = index_service.get_by_namespace("decisions")
        assert len(results) == 2
        assert all(m.namespace == "decisions" for m in results)

    def test_list_recent(
        self,
        index_service: IndexService,
    ) -> None:
        """Test listing recent memories."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime(2024, 1, i + 1, tzinfo=UTC),
            )
            for i in range(5)
        ]
        index_service.insert_batch(memories)

        results = index_service.list_recent(limit=3)
        assert len(results) == 3
        # Should be ordered by timestamp descending
        assert results[0].timestamp > results[1].timestamp > results[2].timestamp

    def test_list_recent_with_filters(
        self,
        index_service: IndexService,
    ) -> None:
        """Test listing recent with namespace filter."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="decisions" if i % 2 == 0 else "learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(4)
        ]
        index_service.insert_batch(memories)

        results = index_service.list_recent(limit=10, namespace="decisions")
        assert len(results) == 2
        assert all(m.namespace == "decisions" for m in results)


# =============================================================================
# Test: Update Operations
# =============================================================================


class TestUpdateOperations:
    """Test memory update operations."""

    def test_update_memory(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test updating a memory."""
        index_service.insert(sample_memory)

        updated = Memory(
            id=sample_memory.id,
            commit_sha=sample_memory.commit_sha,
            namespace=sample_memory.namespace,
            summary="Updated summary",
            content="Updated content",
            timestamp=sample_memory.timestamp,
            spec=sample_memory.spec,
            phase="implementation",  # Changed
            tags=("new-tag",),  # Changed
            status="resolved",  # Changed
            relates_to=sample_memory.relates_to,
        )

        result = index_service.update(updated)
        assert result is True

        retrieved = index_service.get(sample_memory.id)
        assert retrieved is not None
        assert retrieved.summary == "Updated summary"
        assert retrieved.content == "Updated content"
        assert retrieved.phase == "implementation"
        assert retrieved.tags == ("new-tag",)
        assert retrieved.status == "resolved"

    def test_update_nonexistent_memory(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test updating nonexistent memory returns False."""
        result = index_service.update(sample_memory)
        assert result is False

    def test_update_with_embedding(
        self,
        index_service: IndexService,
        sample_memory: Memory,
        sample_embedding: list[float],
    ) -> None:
        """Test updating memory with new embedding."""
        index_service.insert(sample_memory, sample_embedding)

        new_embedding = [0.5] * 384
        result = index_service.update(sample_memory, new_embedding)
        assert result is True

        # Verify embedding was updated (we can't easily verify the values)
        assert index_service.has_embedding(sample_memory.id) is True

    def test_update_embedding_only(
        self,
        index_service: IndexService,
        sample_memory: Memory,
        sample_embedding: list[float],
    ) -> None:
        """Test updating only the embedding."""
        index_service.insert(sample_memory, sample_embedding)

        new_embedding = [0.9] * 384
        result = index_service.update_embedding(sample_memory.id, new_embedding)
        assert result is True

    def test_update_embedding_nonexistent(
        self,
        index_service: IndexService,
        sample_embedding: list[float],
    ) -> None:
        """Test updating embedding for nonexistent memory."""
        result = index_service.update_embedding("nonexistent:id:0", sample_embedding)
        assert result is False


# =============================================================================
# Test: Delete Operations
# =============================================================================


class TestDeleteOperations:
    """Test memory delete operations."""

    def test_delete_memory(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test deleting a memory."""
        index_service.insert(sample_memory)
        assert index_service.exists(sample_memory.id) is True

        result = index_service.delete(sample_memory.id)
        assert result is True
        assert index_service.exists(sample_memory.id) is False

    def test_delete_memory_with_embedding(
        self,
        index_service: IndexService,
        sample_memory: Memory,
        sample_embedding: list[float],
    ) -> None:
        """Test deleting memory also removes embedding."""
        index_service.insert(sample_memory, sample_embedding)
        assert index_service.has_embedding(sample_memory.id) is True

        index_service.delete(sample_memory.id)
        assert index_service.has_embedding(sample_memory.id) is False

    def test_delete_nonexistent(
        self,
        index_service: IndexService,
    ) -> None:
        """Test deleting nonexistent memory returns False."""
        result = index_service.delete("nonexistent:id:0")
        assert result is False

    def test_delete_batch(
        self,
        index_service: IndexService,
    ) -> None:
        """Test batch delete."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(5)
        ]
        index_service.insert_batch(memories)

        ids_to_delete = [m.id for m in memories[:3]]
        count = index_service.delete_batch(ids_to_delete)
        assert count == 3

        # Verify deletions
        for memory_id in ids_to_delete:
            assert index_service.exists(memory_id) is False

        # Verify remaining
        for memory in memories[3:]:
            assert index_service.exists(memory.id) is True

    def test_delete_batch_empty(
        self,
        index_service: IndexService,
    ) -> None:
        """Test batch delete with empty list."""
        count = index_service.delete_batch([])
        assert count == 0

    def test_clear(
        self,
        index_service: IndexService,
    ) -> None:
        """Test clearing all memories."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(5)
        ]
        index_service.insert_batch(memories)

        count = index_service.clear()
        assert count == 5

        # Verify all deleted
        assert index_service.count() == 0


# =============================================================================
# Test: Search Operations
# =============================================================================


class TestVectorSearch:
    """Test vector similarity search."""

    def test_search_vector_basic(
        self,
        index_service: IndexService,
    ) -> None:
        """Test basic vector search."""
        # Insert memories with different embeddings
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(3)
        ]
        embeddings = [
            [0.1] * 384,  # Most similar to query
            [0.5] * 384,
            [0.9] * 384,  # Least similar to query
        ]

        for memory, emb in zip(memories, embeddings, strict=False):
            index_service.insert(memory, emb)

        # Search with query similar to first embedding
        query = [0.1] * 384
        results = index_service.search_vector(query, k=2)

        assert len(results) == 2
        # First result should be most similar
        assert results[0][0].id == "test:0:0"

    def test_search_vector_with_namespace_filter(
        self,
        index_service: IndexService,
    ) -> None:
        """Test vector search with namespace filter."""
        memories = [
            Memory(
                id="decisions:1:0",
                commit_sha="sha1",
                namespace="decisions",
                summary="Decision",
                content="Content",
                timestamp=datetime.now(UTC),
            ),
            Memory(
                id="learnings:1:0",
                commit_sha="sha2",
                namespace="learnings",
                summary="Learning",
                content="Content",
                timestamp=datetime.now(UTC),
            ),
        ]
        embedding = [0.5] * 384

        for memory in memories:
            index_service.insert(memory, embedding)

        query = [0.5] * 384
        results = index_service.search_vector(query, k=10, namespace="decisions")

        assert len(results) == 1
        assert results[0][0].namespace == "decisions"

    def test_search_vector_with_spec_filter(
        self,
        index_service: IndexService,
    ) -> None:
        """Test vector search with spec filter."""
        memories = [
            Memory(
                id="test:1:0",
                commit_sha="sha1",
                namespace="learnings",
                summary="Memory 1",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-a",
            ),
            Memory(
                id="test:2:0",
                commit_sha="sha2",
                namespace="learnings",
                summary="Memory 2",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-b",
            ),
        ]
        embedding = [0.5] * 384

        for memory in memories:
            index_service.insert(memory, embedding)

        query = [0.5] * 384
        results = index_service.search_vector(query, k=10, spec="project-a")

        assert len(results) == 1
        assert results[0][0].spec == "project-a"

    def test_search_vector_returns_distance(
        self,
        index_service: IndexService,
    ) -> None:
        """Test vector search returns distance scores."""
        memory = Memory(
            id="test:1:0",
            commit_sha="sha1",
            namespace="learnings",
            summary="Memory",
            content="Content",
            timestamp=datetime.now(UTC),
        )
        embedding = [0.5] * 384
        index_service.insert(memory, embedding)

        query = [0.5] * 384
        results = index_service.search_vector(query, k=1)

        assert len(results) == 1
        assert isinstance(results[0][1], float)
        # Identical vectors should have zero distance
        assert results[0][1] < 0.01


class TestTextSearch:
    """Test text-based search."""

    def test_search_text_in_summary(
        self,
        index_service: IndexService,
    ) -> None:
        """Test searching text in summary."""
        memories = [
            Memory(
                id="test:1:0",
                commit_sha="sha1",
                namespace="learnings",
                summary="PostgreSQL database choice",
                content="Content",
                timestamp=datetime.now(UTC),
            ),
            Memory(
                id="test:2:0",
                commit_sha="sha2",
                namespace="learnings",
                summary="Redis caching strategy",
                content="Content",
                timestamp=datetime.now(UTC),
            ),
        ]
        index_service.insert_batch(memories)

        results = index_service.search_text("PostgreSQL")
        assert len(results) == 1
        assert results[0].id == "test:1:0"

    def test_search_text_in_content(
        self,
        index_service: IndexService,
    ) -> None:
        """Test searching text in content."""
        memories = [
            Memory(
                id="test:1:0",
                commit_sha="sha1",
                namespace="learnings",
                summary="Database choice",
                content="We chose PostgreSQL for its reliability",
                timestamp=datetime.now(UTC),
            ),
            Memory(
                id="test:2:0",
                commit_sha="sha2",
                namespace="learnings",
                summary="Cache choice",
                content="We chose Redis for caching",
                timestamp=datetime.now(UTC),
            ),
        ]
        index_service.insert_batch(memories)

        results = index_service.search_text("reliability")
        assert len(results) == 1
        assert results[0].id == "test:1:0"

    def test_search_text_with_filters(
        self,
        index_service: IndexService,
    ) -> None:
        """Test text search with namespace filter."""
        memories = [
            Memory(
                id="decisions:1:0",
                commit_sha="sha1",
                namespace="decisions",
                summary="Database decision",
                content="Content",
                timestamp=datetime.now(UTC),
            ),
            Memory(
                id="learnings:1:0",
                commit_sha="sha2",
                namespace="learnings",
                summary="Database learning",
                content="Content",
                timestamp=datetime.now(UTC),
            ),
        ]
        index_service.insert_batch(memories)

        results = index_service.search_text("Database", namespace="decisions")
        assert len(results) == 1
        assert results[0].namespace == "decisions"

    def test_search_text_case_insensitive(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test text search is case-insensitive."""
        index_service.insert(sample_memory)

        # Search with different case
        results = index_service.search_text("postgresql")
        assert len(results) == 1


# =============================================================================
# Test: Statistics Operations
# =============================================================================


class TestStatisticsOperations:
    """Test statistics and count operations."""

    def test_get_stats_empty(
        self,
        index_service: IndexService,
    ) -> None:
        """Test stats on empty database."""
        stats = index_service.get_stats()
        assert stats.total_memories == 0
        assert stats.by_namespace == ()
        assert stats.by_spec == ()

    def test_get_stats_with_data(
        self,
        index_service: IndexService,
    ) -> None:
        """Test stats with data."""
        memories = [
            Memory(
                id="decisions:1:0",
                commit_sha="sha1",
                namespace="decisions",
                summary="Decision",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-a",
            ),
            Memory(
                id="decisions:2:0",
                commit_sha="sha2",
                namespace="decisions",
                summary="Decision 2",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-a",
            ),
            Memory(
                id="learnings:1:0",
                commit_sha="sha3",
                namespace="learnings",
                summary="Learning",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-b",
            ),
        ]
        index_service.insert_batch(memories)

        stats = index_service.get_stats()
        assert stats.total_memories == 3

        # Check namespace counts
        by_namespace = dict(stats.by_namespace)
        assert by_namespace["decisions"] == 2
        assert by_namespace["learnings"] == 1

        # Check spec counts
        by_spec = dict(stats.by_spec)
        assert by_spec["project-a"] == 2
        assert by_spec["project-b"] == 1

    def test_get_stats_includes_size(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test stats includes database size."""
        index_service.insert(sample_memory)
        stats = index_service.get_stats()
        assert stats.index_size_bytes > 0

    def test_count_all(
        self,
        index_service: IndexService,
    ) -> None:
        """Test count all memories."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(5)
        ]
        index_service.insert_batch(memories)

        assert index_service.count() == 5

    def test_count_with_filters(
        self,
        index_service: IndexService,
    ) -> None:
        """Test count with filters."""
        memories = [
            Memory(
                id="decisions:1:0",
                commit_sha="sha1",
                namespace="decisions",
                summary="Decision",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-a",
            ),
            Memory(
                id="learnings:1:0",
                commit_sha="sha2",
                namespace="learnings",
                summary="Learning",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-a",
            ),
            Memory(
                id="learnings:2:0",
                commit_sha="sha3",
                namespace="learnings",
                summary="Learning 2",
                content="Content",
                timestamp=datetime.now(UTC),
                spec="project-b",
            ),
        ]
        index_service.insert_batch(memories)

        assert index_service.count(namespace="decisions") == 1
        assert index_service.count(namespace="learnings") == 2
        assert index_service.count(spec="project-a") == 2
        assert index_service.count(namespace="learnings", spec="project-a") == 1


# =============================================================================
# Test: Utility Operations
# =============================================================================


class TestUtilityOperations:
    """Test utility operations."""

    def test_has_embedding_true(
        self,
        index_service: IndexService,
        sample_memory: Memory,
        sample_embedding: list[float],
    ) -> None:
        """Test has_embedding returns True when embedding exists."""
        index_service.insert(sample_memory, sample_embedding)
        assert index_service.has_embedding(sample_memory.id) is True

    def test_has_embedding_false(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test has_embedding returns False when no embedding."""
        index_service.insert(sample_memory)
        assert index_service.has_embedding(sample_memory.id) is False

    def test_has_embedding_nonexistent(
        self,
        index_service: IndexService,
    ) -> None:
        """Test has_embedding for nonexistent memory."""
        assert index_service.has_embedding("nonexistent:id:0") is False

    def test_get_memories_without_embeddings(
        self,
        index_service: IndexService,
    ) -> None:
        """Test getting memories that lack embeddings."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(3)
        ]

        # Insert first with embedding, others without
        index_service.insert(memories[0], [0.5] * 384)
        index_service.insert(memories[1])
        index_service.insert(memories[2])

        missing = index_service.get_memories_without_embeddings()
        assert len(missing) == 2
        assert memories[0].id not in missing
        assert memories[1].id in missing
        assert memories[2].id in missing

    def test_get_memories_without_embeddings_limit(
        self,
        index_service: IndexService,
    ) -> None:
        """Test getting memories without embeddings with limit."""
        memories = [
            Memory(
                id=f"test:{i}:0",
                commit_sha=f"sha{i}",
                namespace="learnings",
                summary=f"Memory {i}",
                content=f"Content {i}",
                timestamp=datetime.now(UTC),
            )
            for i in range(5)
        ]
        index_service.insert_batch(memories)

        missing = index_service.get_memories_without_embeddings(limit=2)
        assert len(missing) == 2

    def test_update_last_sync(
        self,
        index_service: IndexService,
    ) -> None:
        """Test updating last sync timestamp."""
        initial_stats = index_service.get_stats()
        initial_sync = initial_stats.last_sync

        # Wait a tiny bit to ensure different timestamp
        import time

        time.sleep(0.01)

        index_service.update_last_sync()

        updated_stats = index_service.get_stats()
        assert updated_stats.last_sync is not None
        assert updated_stats.last_sync > initial_sync

    def test_vacuum(
        self,
        index_service: IndexService,
        sample_memory: Memory,
    ) -> None:
        """Test vacuum doesn't raise errors."""
        index_service.insert(sample_memory)
        index_service.delete(sample_memory.id)

        # Should not raise
        index_service.vacuum()


# =============================================================================
# Test: Error Handling
# =============================================================================


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_operation_before_initialize(
        self,
        db_path: Path,
        sample_memory: Memory,
    ) -> None:
        """Test operations before initialize raise error."""
        service = IndexService(db_path)

        with pytest.raises(MemoryIndexError) as exc_info:
            service.insert(sample_memory)

        assert "not initialized" in exc_info.value.message

    def test_get_before_initialize(
        self,
        db_path: Path,
    ) -> None:
        """Test get before initialize raises error."""
        service = IndexService(db_path)

        with pytest.raises(MemoryIndexError):
            service.get("any-id")

    def test_vacuum_before_initialize(
        self,
        db_path: Path,
    ) -> None:
        """Test vacuum before initialize raises error."""
        service = IndexService(db_path)

        with pytest.raises(MemoryIndexError):
            service.vacuum()
