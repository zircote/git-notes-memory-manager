"""Tests for git_notes_memory.sync module.

Tests for SyncService including index synchronization, consistency verification,
reindexing, and repair operations. Uses mocked dependencies for unit tests
and real services for integration tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from git_notes_memory.exceptions import RecallError
from git_notes_memory.models import (
    Memory,
    NoteRecord,
    VerificationResult,
)
from git_notes_memory.sync import SyncService, get_sync_service

if TYPE_CHECKING:
    from git_notes_memory.index import IndexService


# =============================================================================
# Fixtures
# =============================================================================


def make_note_record(
    commit_sha: str = "abc1234567890",
    namespace: str = "decisions",
    index: int = 0,
    summary: str = "Use PostgreSQL for persistence",
    body: str = "We chose PostgreSQL for its reliability.",
    spec: str = "SPEC-2025-12-18-001",
    tags: list[str] | None = None,
    phase: str | None = "implementation",
    status: str | None = "active",
    timestamp: str | None = None,
    relates_to: list[str] | None = None,
) -> NoteRecord:
    """Create a NoteRecord with proper front_matter structure."""
    if tags is None:
        tags = ["database", "architecture"]
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()
    if relates_to is None:
        relates_to = []

    front_matter: list[tuple[str, str]] = [
        ("type", namespace),
        ("spec", spec),
        ("timestamp", timestamp),
        ("summary", summary),
    ]
    if phase:
        front_matter.append(("phase", phase))
    if status:
        front_matter.append(("status", status))
    if tags:
        front_matter.append(("tags", ",".join(tags)))
    if relates_to:
        front_matter.append(("relates_to", ",".join(relates_to)))

    return NoteRecord(
        commit_sha=commit_sha,
        namespace=namespace,
        index=index,
        front_matter=tuple(front_matter),
        body=body,
        raw=f"---\n{chr(10).join(f'{k}: {v}' for k, v in front_matter)}\n---\n\n{body}",
    )


@pytest.fixture
def sample_note_record() -> NoteRecord:
    """Create a sample NoteRecord for testing."""
    return make_note_record()


@pytest.fixture
def sample_note_records() -> list[NoteRecord]:
    """Create a list of sample note records."""
    timestamp = datetime.now(UTC).isoformat()
    return [
        make_note_record(
            namespace="decisions",
            spec="SPEC-001",
            timestamp=timestamp,
            summary="Use PostgreSQL",
            body="PostgreSQL for reliability",
            tags=["database"],
        ),
        make_note_record(
            namespace="learnings",
            spec="SPEC-001",
            timestamp=timestamp,
            summary="Type hints improve DX",
            body="Type hints help with IDE support",
            tags=["python"],
            phase=None,
            index=1,
        ),
    ]


@pytest.fixture
def sample_memory() -> Memory:
    """Create a sample Memory for testing."""
    return Memory(
        id="decisions:abc1234:0",
        commit_sha="abc1234567890",
        namespace="decisions",
        timestamp=datetime.now(UTC),
        summary="Use PostgreSQL",
        content="PostgreSQL content",
        spec="SPEC-001",
        tags=("database",),
        phase="implementation",
        status="active",
        relates_to=(),
    )


@pytest.fixture
def mock_index() -> MagicMock:
    """Create a mock IndexService."""
    index = MagicMock()
    index.exists.return_value = False
    index.get_all_ids.return_value = []
    return index


@pytest.fixture
def mock_git_ops() -> MagicMock:
    """Create a mock GitOps."""
    git_ops = MagicMock()
    git_ops.list_notes.return_value = []
    git_ops.show_note.return_value = None
    # PERF-001: Also mock show_notes_batch for batch operations
    git_ops.show_notes_batch.return_value = {}
    return git_ops


@pytest.fixture
def mock_embedding() -> MagicMock:
    """Create a mock EmbeddingService."""
    embedding = MagicMock()
    embedding.embed.return_value = [0.1] * 384
    # PERF-002: Also mock embed_batch for batch operations
    embedding.embed_batch.return_value = [[0.1] * 384]
    return embedding


@pytest.fixture
def mock_note_parser() -> MagicMock:
    """Create a mock NoteParser."""
    parser = MagicMock()
    parser.parse_many.return_value = []
    return parser


@pytest.fixture
def sync_service(
    mock_index: MagicMock,
    mock_git_ops: MagicMock,
    mock_embedding: MagicMock,
    mock_note_parser: MagicMock,
    tmp_path: Path,
) -> SyncService:
    """Create a SyncService with mocked dependencies."""
    return SyncService(
        repo_path=tmp_path,
        index=mock_index,
        git_ops=mock_git_ops,
        embedding_service=mock_embedding,
        note_parser=mock_note_parser,
    )


# =============================================================================
# Integration Test Fixtures
# =============================================================================


@pytest.fixture
def real_index_service(tmp_path: Path) -> Iterator[IndexService]:
    """Create a real IndexService for integration tests."""
    from git_notes_memory.index import IndexService

    db_path = tmp_path / "test_index.db"
    service = IndexService(db_path)
    service.initialize()
    yield service
    service.close()


# =============================================================================
# SyncService Initialization Tests
# =============================================================================


class TestSyncServiceInit:
    """Tests for SyncService initialization."""

    def test_default_init(self) -> None:
        """Test default initialization uses cwd."""
        service = SyncService()
        assert service.repo_path == Path.cwd()
        assert service._index is None
        assert service._git_ops is None

    def test_init_with_custom_repo_path(self, tmp_path: Path) -> None:
        """Test initialization with custom repo path."""
        service = SyncService(repo_path=tmp_path)
        assert service.repo_path == tmp_path

    def test_init_with_injected_services(
        self,
        mock_index: MagicMock,
        mock_git_ops: MagicMock,
        mock_embedding: MagicMock,
        mock_note_parser: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test initialization with injected dependencies."""
        service = SyncService(
            repo_path=tmp_path,
            index=mock_index,
            git_ops=mock_git_ops,
            embedding_service=mock_embedding,
            note_parser=mock_note_parser,
        )
        assert service._index is mock_index
        assert service._git_ops is mock_git_ops

    def test_lazy_index_creation(self, tmp_path: Path) -> None:
        """Test index is created lazily."""
        # Create .git directory to satisfy git root requirement
        (tmp_path / ".git").mkdir()

        # Patch at the source module level where IndexService is defined
        with patch("git_notes_memory.index.IndexService") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance

            service = SyncService(repo_path=tmp_path)
            # Index not created yet
            assert service._index is None

            # Access triggers creation (find_git_root now returns tmp_path)
            result = service._get_index()
            assert result is mock_instance
            mock_instance.initialize.assert_called_once()

    def test_lazy_git_ops_creation(self, tmp_path: Path) -> None:
        """Test git_ops is created lazily."""
        # Patch at the source module level where GitOps is defined
        with patch("git_notes_memory.git_ops.GitOps") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance

            service = SyncService(repo_path=tmp_path)
            result = service._get_git_ops()
            assert result is mock_instance
            mock_cls.assert_called_once_with(tmp_path)

    def test_lazy_embedding_creation(self, tmp_path: Path) -> None:
        """Test embedding service is created lazily."""
        # Patch at the source module level where EmbeddingService is defined
        with patch("git_notes_memory.embedding.EmbeddingService") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance

            service = SyncService(repo_path=tmp_path)
            result = service._get_embedding_service()
            assert result is mock_instance

    def test_lazy_note_parser_creation(self, tmp_path: Path) -> None:
        """Test note parser is created lazily."""
        # Patch at the source module level where NoteParser is defined
        with patch("git_notes_memory.note_parser.NoteParser") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance

            service = SyncService(repo_path=tmp_path)
            result = service._get_note_parser()
            assert result is mock_instance


# =============================================================================
# sync_note_to_index Tests
# =============================================================================


class TestSyncNoteToIndex:
    """Tests for sync_note_to_index method."""

    def test_sync_no_note_returns_zero(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
    ) -> None:
        """Test syncing when no note exists returns zero."""
        mock_git_ops.show_note.return_value = None

        result = sync_service.sync_note_to_index("abc123", "decisions")

        assert result == 0
        mock_git_ops.show_note.assert_called_once_with("decisions", "abc123")

    def test_sync_single_note(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
        sample_note_record: NoteRecord,
    ) -> None:
        """Test syncing a single note."""
        mock_git_ops.show_note.return_value = "---\ntype: decisions\n---"
        mock_note_parser.parse_many.return_value = [sample_note_record]

        result = sync_service.sync_note_to_index("abc1234567890", "decisions")

        assert result == 1
        mock_index.insert.assert_called_once()

    def test_sync_updates_existing_memory(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
        sample_note_record: NoteRecord,
    ) -> None:
        """Test syncing updates existing memories."""
        mock_git_ops.show_note.return_value = "---\ntype: decisions\n---"
        mock_note_parser.parse_many.return_value = [sample_note_record]
        mock_index.exists.return_value = True

        result = sync_service.sync_note_to_index("abc1234567890", "decisions")

        assert result == 1
        mock_index.update.assert_called_once()

    def test_sync_multiple_records_in_note(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
        sample_note_records: list[NoteRecord],
    ) -> None:
        """Test syncing note with multiple records."""
        mock_git_ops.show_note.return_value = "---\ntype: decisions\n---"
        mock_note_parser.parse_many.return_value = sample_note_records

        result = sync_service.sync_note_to_index("abc1234567890", "decisions")

        assert result == 2
        assert mock_index.insert.call_count == 2

    def test_sync_parse_failure_returns_zero(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
    ) -> None:
        """Test parsing failure returns zero."""
        mock_git_ops.show_note.return_value = "invalid content"
        mock_note_parser.parse_many.side_effect = Exception("Parse error")

        result = sync_service.sync_note_to_index("abc123", "decisions")

        assert result == 0

    def test_sync_embedding_failure_continues(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_embedding: MagicMock,
        mock_index: MagicMock,
        sample_note_record: NoteRecord,
    ) -> None:
        """Test embedding failure doesn't block indexing."""
        mock_git_ops.show_note.return_value = "---\ntype: decisions\n---"
        mock_note_parser.parse_many.return_value = [sample_note_record]
        mock_embedding.embed.side_effect = Exception("Embedding failed")

        result = sync_service.sync_note_to_index("abc1234567890", "decisions")

        # Should still index without embedding
        assert result == 1
        mock_index.insert.assert_called_once()

    def test_sync_index_failure_logged(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
        sample_note_record: NoteRecord,
    ) -> None:
        """Test index failure is logged and doesn't crash."""
        mock_git_ops.show_note.return_value = "---\ntype: decisions\n---"
        mock_note_parser.parse_many.return_value = [sample_note_record]
        mock_index.insert.side_effect = Exception("Index error")

        result = sync_service.sync_note_to_index("abc1234567890", "decisions")

        assert result == 0


# =============================================================================
# _record_to_memory Tests
# =============================================================================


class TestRecordToMemory:
    """Tests for _record_to_memory helper method."""

    def test_converts_record_to_memory(
        self,
        sync_service: SyncService,
        sample_note_record: NoteRecord,
    ) -> None:
        """Test conversion of NoteRecord to Memory."""
        memory = sync_service._record_to_memory(
            sample_note_record,
            commit="abc1234567890",
            namespace="decisions",
            index=0,
        )

        assert memory.commit_sha == "abc1234567890"
        assert memory.namespace == "decisions"
        assert memory.summary == sample_note_record.summary
        assert memory.content == sample_note_record.body

    def test_deterministic_id_format(
        self,
        sync_service: SyncService,
        sample_note_record: NoteRecord,
    ) -> None:
        """Test memory ID format is deterministic."""
        memory = sync_service._record_to_memory(
            sample_note_record,
            commit="abc1234567890",
            namespace="decisions",
            index=0,
        )

        assert memory.id == "decisions:abc1234:0"

    def test_handles_none_timestamp(
        self,
        sync_service: SyncService,
    ) -> None:
        """Test handling of None timestamp."""
        record = make_note_record(timestamp="invalid-timestamp")

        memory = sync_service._record_to_memory(
            record,
            commit="abc1234567890",
            namespace="decisions",
            index=0,
        )

        # Should use current time when timestamp is invalid
        assert memory.timestamp is not None
        assert isinstance(memory.timestamp, datetime)

    def test_handles_empty_tags(
        self,
        sync_service: SyncService,
    ) -> None:
        """Test handling of empty tags."""
        record = make_note_record(tags=[])

        memory = sync_service._record_to_memory(
            record,
            commit="abc123",
            namespace="decisions",
            index=0,
        )

        assert memory.tags == ()

    def test_handles_none_status(
        self,
        sync_service: SyncService,
    ) -> None:
        """Test handling of None status defaults to active."""
        record = make_note_record(status=None)

        memory = sync_service._record_to_memory(
            record,
            commit="abc123",
            namespace="decisions",
            index=0,
        )

        assert memory.status == "active"

    def test_handles_empty_body(
        self,
        sync_service: SyncService,
    ) -> None:
        """Test handling of empty body."""
        record = make_note_record(body="")

        memory = sync_service._record_to_memory(
            record,
            commit="abc123",
            namespace="decisions",
            index=0,
        )

        assert memory.content == ""


# =============================================================================
# collect_notes Tests
# =============================================================================


class TestCollectNotes:
    """Tests for collect_notes method."""

    def test_collect_empty_returns_empty(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
    ) -> None:
        """Test collecting from empty repo returns empty list."""
        mock_git_ops.list_notes.return_value = []

        result = sync_service.collect_notes()

        assert result == []

    def test_collect_single_note(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        sample_note_record: NoteRecord,
    ) -> None:
        """Test collecting a single note."""
        # Only one namespace has notes
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "commit_sha")] if ns == "decisions" else []
        )
        # PERF-001: Mock batch operations
        mock_git_ops.show_notes_batch.return_value = {
            "commit_sha": "---\ntype: decisions\n---"
        }
        mock_note_parser.parse_many.return_value = [sample_note_record]

        result = sync_service.collect_notes()

        assert len(result) == 1

    def test_collect_multiple_namespaces(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
    ) -> None:
        """Test collecting from multiple namespaces."""
        # Two namespaces have notes
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note1", "commit1")] if ns in ["decisions", "learnings"] else []
        )
        # PERF-001: Mock batch operations
        mock_git_ops.show_notes_batch.return_value = {"commit1": "---\ntype: test\n---"}

        record1 = make_note_record(namespace="decisions")
        record2 = make_note_record(namespace="learnings")

        call_count = [0]

        def parse_side_effect(
            content: str,  # noqa: ARG001 - Required by signature
            commit_sha: str = "",  # noqa: ARG001 - Required by signature
            namespace: str = "",  # noqa: ARG001 - Required by signature
        ) -> list[NoteRecord]:
            call_count[0] += 1
            return [record1] if call_count[0] == 1 else [record2]

        mock_note_parser.parse_many.side_effect = parse_side_effect

        result = sync_service.collect_notes()

        assert len(result) == 2

    def test_collect_stores_commit_metadata(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
    ) -> None:
        """Test that collected notes have commit metadata passed to parser."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "abc123")] if ns == "decisions" else []
        )
        # PERF-001: Mock show_notes_batch for batch operations
        mock_git_ops.show_notes_batch.return_value = {
            "abc123": "---\ntype: decisions\n---"
        }

        # Create record that will be returned (with commit_sha set)
        record = make_note_record(commit_sha="abc123", namespace="decisions")
        mock_note_parser.parse_many.return_value = [record]

        result = sync_service.collect_notes()

        assert len(result) == 1
        # Verify parse_many was called with commit_sha and namespace
        mock_note_parser.parse_many.assert_called_with(
            "---\ntype: decisions\n---",
            commit_sha="abc123",
            namespace="decisions",
        )

    def test_collect_handles_namespace_error(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
    ) -> None:
        """Test error handling when listing notes fails."""
        mock_git_ops.list_notes.side_effect = Exception("Git error")

        result = sync_service.collect_notes()

        assert result == []

    def test_collect_handles_note_read_error(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
    ) -> None:
        """Test error handling when reading note content fails."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "commit_sha")] if ns == "decisions" else []
        )
        mock_git_ops.show_note.side_effect = Exception("Read error")

        result = sync_service.collect_notes()

        assert result == []


# =============================================================================
# reindex Tests
# =============================================================================


class TestReindex:
    """Tests for reindex method."""

    def test_reindex_empty_repo(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
    ) -> None:
        """Test reindexing empty repository."""
        mock_git_ops.list_notes.return_value = []

        result = sync_service.reindex()

        assert result == 0

    def test_reindex_single_note(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
        mock_embedding: MagicMock,
    ) -> None:
        """Test reindexing a single note."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "abc123")] if ns == "decisions" else []
        )
        # PERF-001: Mock batch operations
        mock_git_ops.show_notes_batch.return_value = {
            "abc123": "---\ntype: decisions\n---"
        }
        # PERF-002: Mock batch embedding
        mock_embedding.embed_batch.return_value = [[0.1] * 384]

        record = make_note_record()
        mock_note_parser.parse_many.return_value = [record]

        result = sync_service.reindex()

        assert result == 1
        mock_index.insert.assert_called_once()

    def test_reindex_full_clears_index(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test full reindex clears index first."""
        mock_git_ops.list_notes.return_value = []

        sync_service.reindex(full=True)

        mock_index.clear.assert_called_once()

    def test_reindex_incremental_skips_existing(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test incremental reindex skips existing entries."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "abc123")] if ns == "decisions" else []
        )
        mock_git_ops.show_note.return_value = "---\ntype: decisions\n---"

        record = make_note_record()
        mock_note_parser.parse_many.return_value = [record]
        mock_index.exists.return_value = True

        result = sync_service.reindex(full=False)

        assert result == 0
        mock_index.insert.assert_not_called()

    def test_reindex_full_includes_existing(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
        mock_embedding: MagicMock,
    ) -> None:
        """Test full reindex includes existing entries."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "abc123")] if ns == "decisions" else []
        )
        # PERF-001: Mock batch operations
        mock_git_ops.show_notes_batch.return_value = {
            "abc123": "---\ntype: decisions\n---"
        }
        # PERF-002: Mock batch embedding
        mock_embedding.embed_batch.return_value = [[0.1] * 384]

        record = make_note_record()
        mock_note_parser.parse_many.return_value = [record]
        mock_index.exists.return_value = True

        result = sync_service.reindex(full=True)

        # Should still insert even though exists
        assert result == 1
        mock_index.insert.assert_called_once()

    def test_reindex_multiple_notes(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
        mock_embedding: MagicMock,
    ) -> None:
        """Test reindexing multiple notes."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note1", "commit1"), ("note2", "commit2")] if ns == "decisions" else []
        )
        # PERF-001: Mock batch operations with both commits
        mock_git_ops.show_notes_batch.return_value = {
            "commit1": "---\ntype: decisions\n---",
            "commit2": "---\ntype: decisions\n---",
        }
        # PERF-002: Mock batch embedding for 2 notes
        mock_embedding.embed_batch.return_value = [[0.1] * 384, [0.1] * 384]

        record = make_note_record()
        mock_note_parser.parse_many.return_value = [record]

        result = sync_service.reindex()

        assert result == 2
        assert mock_index.insert.call_count == 2

    def test_reindex_handles_note_errors(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,  # noqa: ARG002 - Required fixture
        mock_embedding: MagicMock,
    ) -> None:
        """Test reindex continues after note errors."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note1", "commit1"), ("note2", "commit2")] if ns == "decisions" else []
        )

        # PERF-001: Mock batch operations - commit2 returns None (error)
        mock_git_ops.show_notes_batch.return_value = {
            "commit1": "---\ntype: decisions\n---",
            "commit2": None,  # Simulates read error
        }
        # PERF-002: Mock batch embedding for 1 note (only commit1 succeeds)
        mock_embedding.embed_batch.return_value = [[0.1] * 384]

        record = make_note_record()
        mock_note_parser.parse_many.return_value = [record]

        result = sync_service.reindex()

        assert result == 1  # Only first succeeded


# =============================================================================
# verify_consistency Tests
# =============================================================================


class TestVerifyConsistency:
    """Tests for verify_consistency method."""

    def test_verify_consistent_empty(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test verification of empty repo is consistent."""
        mock_git_ops.list_notes.return_value = []
        mock_index.get_all_ids.return_value = []

        result = sync_service.verify_consistency()

        assert result.is_consistent is True
        assert len(result.missing_in_index) == 0
        assert len(result.orphaned_in_index) == 0

    def test_verify_consistent_with_data(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
        sample_memory: Memory,
    ) -> None:
        """Test verification when index matches notes."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "abc1234")] if ns == "decisions" else []
        )
        # PERF-001: Mock batch operations
        mock_git_ops.show_notes_batch.return_value = {
            "abc1234": "---\ntype: decisions\n---"
        }

        record = make_note_record(
            commit_sha="abc1234",
            summary="Use PostgreSQL",
            body="PostgreSQL content",
        )
        mock_note_parser.parse_many.return_value = [record]
        mock_index.get_all_ids.return_value = ["decisions:abc1234:0"]
        mock_index.get.return_value = sample_memory

        result = sync_service.verify_consistency()

        assert result.is_consistent is True

    def test_verify_missing_in_index(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test detection of notes missing from index."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "abc1234")] if ns == "decisions" else []
        )
        # PERF-001: Mock batch operations
        mock_git_ops.show_notes_batch.return_value = {
            "abc1234": "---\ntype: decisions\n---"
        }

        record = make_note_record()
        mock_note_parser.parse_many.return_value = [record]
        mock_index.get_all_ids.return_value = []  # Index is empty

        result = sync_service.verify_consistency()

        assert result.is_consistent is False
        assert "decisions:abc1234:0" in result.missing_in_index

    def test_verify_orphaned_in_index(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test detection of orphaned entries in index."""
        mock_git_ops.list_notes.return_value = []  # No notes
        mock_index.get_all_ids.return_value = [
            "decisions:abc1234:0"
        ]  # But index has entry

        result = sync_service.verify_consistency()

        assert result.is_consistent is False
        assert "decisions:abc1234:0" in result.orphaned_in_index

    def test_verify_mismatched_content(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test detection of content mismatches."""
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "abc1234")] if ns == "decisions" else []
        )
        # PERF-001: Mock batch operations
        mock_git_ops.show_notes_batch.return_value = {
            "abc1234": "---\ntype: decisions\n---"
        }

        # Note has different content than indexed
        record = make_note_record(
            summary="New summary",
            body="New body content",
        )
        mock_note_parser.parse_many.return_value = [record]
        mock_index.get_all_ids.return_value = ["decisions:abc1234:0"]

        # Indexed version has different content
        indexed_memory = Memory(
            id="decisions:abc1234:0",
            commit_sha="abc1234",
            namespace="decisions",
            timestamp=datetime.now(UTC),
            summary="Old summary",
            content="Old body content",
            spec="SPEC-001",
            tags=(),
            phase=None,
            status="active",
            relates_to=(),
        )
        mock_index.get.return_value = indexed_memory

        result = sync_service.verify_consistency()

        assert result.is_consistent is False
        assert "decisions:abc1234:0" in result.mismatched

    def test_verify_index_read_error(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test verification handles index read errors."""
        mock_git_ops.list_notes.return_value = []
        mock_index.get_all_ids.side_effect = Exception("Database error")

        with pytest.raises(RecallError):
            sync_service.verify_consistency()


# =============================================================================
# repair Tests
# =============================================================================


class TestRepair:
    """Tests for repair method."""

    def test_repair_consistent_index(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test repair on consistent index does nothing."""
        mock_git_ops.list_notes.return_value = []
        mock_index.get_all_ids.return_value = []

        result = sync_service.repair()

        assert result == 0

    def test_repair_removes_orphans(
        self,
        sync_service: SyncService,
        mock_index: MagicMock,
    ) -> None:
        """Test repair removes orphaned entries."""
        verification = VerificationResult(
            is_consistent=False,
            missing_in_index=(),
            orphaned_in_index=("decisions:abc1234:0",),
            mismatched=(),
        )

        result = sync_service.repair(verification)

        assert result == 1
        mock_index.delete.assert_called_once_with("decisions:abc1234:0")

    def test_repair_reindexes_missing(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test repair re-indexes missing entries."""
        mock_git_ops.list_notes.return_value = [("note_sha", "abc1234567")]
        mock_git_ops.show_note.return_value = "---\ntype: decisions\n---"

        record = make_note_record()
        mock_note_parser.parse_many.return_value = [record]

        verification = VerificationResult(
            is_consistent=False,
            missing_in_index=("decisions:abc1234:0",),
            orphaned_in_index=(),
            mismatched=(),
        )

        result = sync_service.repair(verification)

        assert result >= 1  # At least one repair made

    def test_repair_reindexes_mismatched(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_note_parser: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test repair re-indexes mismatched entries."""
        mock_git_ops.list_notes.return_value = [("note_sha", "abc1234567")]
        mock_git_ops.show_note.return_value = "---\ntype: decisions\n---"

        record = make_note_record()
        mock_note_parser.parse_many.return_value = [record]

        verification = VerificationResult(
            is_consistent=False,
            missing_in_index=(),
            orphaned_in_index=(),
            mismatched=("decisions:abc1234:0",),
        )

        result = sync_service.repair(verification)

        assert result >= 1

    def test_repair_verifies_first_if_no_result(
        self,
        sync_service: SyncService,
        mock_git_ops: MagicMock,
        mock_index: MagicMock,
    ) -> None:
        """Test repair runs verification if no result provided."""
        mock_git_ops.list_notes.return_value = []
        mock_index.get_all_ids.return_value = []

        result = sync_service.repair()

        assert result == 0
        # Verification was called (implicit via get_all_ids)
        mock_index.get_all_ids.assert_called()

    def test_repair_handles_delete_errors(
        self,
        sync_service: SyncService,
        mock_index: MagicMock,
    ) -> None:
        """Test repair handles delete errors gracefully."""
        mock_index.delete.side_effect = Exception("Delete failed")

        verification = VerificationResult(
            is_consistent=False,
            missing_in_index=(),
            orphaned_in_index=("decisions:abc1234:0",),
            mismatched=(),
        )

        result = sync_service.repair(verification)

        assert result == 0  # Delete failed


# =============================================================================
# Singleton Tests
# =============================================================================


class TestGetSyncService:
    """Tests for get_sync_service singleton."""

    def test_returns_sync_service(self) -> None:
        """Test singleton returns a SyncService."""
        # Reset singleton
        from git_notes_memory import sync

        sync._sync_service = None

        result = get_sync_service()

        assert isinstance(result, SyncService)

    def test_returns_same_instance(self) -> None:
        """Test singleton returns same instance."""
        from git_notes_memory import sync

        sync._sync_service = None

        result1 = get_sync_service()
        result2 = get_sync_service()

        assert result1 is result2

    def test_accepts_repo_path(self, tmp_path: Path) -> None:
        """Test singleton accepts repo path on first call."""
        from git_notes_memory import sync

        sync._sync_service = None

        result = get_sync_service(tmp_path)

        assert result.repo_path == tmp_path


# =============================================================================
# Integration Tests
# =============================================================================


class TestSyncServiceIntegration:
    """Integration tests using real IndexService."""

    def test_verify_consistency_with_real_index(
        self,
        real_index_service: IndexService,
        tmp_path: Path,
    ) -> None:
        """Test consistency verification with real index."""
        mock_git_ops = MagicMock()
        mock_git_ops.list_notes.return_value = []
        mock_note_parser = MagicMock()

        service = SyncService(
            repo_path=tmp_path,
            index=real_index_service,
            git_ops=mock_git_ops,
            note_parser=mock_note_parser,
        )

        result = service.verify_consistency()

        assert result.is_consistent is True

    def test_repair_with_real_index(
        self,
        real_index_service: IndexService,
        tmp_path: Path,
    ) -> None:
        """Test repair with real index."""
        mock_git_ops = MagicMock()
        mock_git_ops.list_notes.return_value = []

        service = SyncService(
            repo_path=tmp_path,
            index=real_index_service,
            git_ops=mock_git_ops,
        )

        result = service.repair()

        assert result == 0  # Nothing to repair in empty index

    def test_sync_note_with_real_index(
        self,
        real_index_service: IndexService,
        tmp_path: Path,
    ) -> None:
        """Test syncing a note with real index."""
        mock_git_ops = MagicMock()
        mock_git_ops.show_note.return_value = "---\ntype: decisions\n---"

        # Use real parser
        from git_notes_memory.note_parser import NoteParser

        parser = NoteParser()

        mock_embedding = MagicMock()
        mock_embedding.embed.return_value = [0.1] * 384

        service = SyncService(
            repo_path=tmp_path,
            index=real_index_service,
            git_ops=mock_git_ops,
            embedding_service=mock_embedding,
            note_parser=parser,
        )

        # Create proper note content
        note_content = """---
type: decisions
spec: SPEC-001
timestamp: 2025-12-18T10:00:00Z
summary: Test decision
---

Test body content.
"""
        mock_git_ops.show_note.return_value = note_content

        result = service.sync_note_to_index("abc1234567890", "decisions")

        assert result == 1
        # Verify it was indexed
        assert real_index_service.exists("decisions:abc1234:0")

    def test_reindex_with_real_index(
        self,
        real_index_service: IndexService,
        tmp_path: Path,
    ) -> None:
        """Test reindex with real index."""
        mock_git_ops = MagicMock()
        mock_git_ops.list_notes.side_effect = lambda ns: (
            [("note_sha", "def7890123456")] if ns == "decisions" else []
        )

        note_content = """---
type: decisions
spec: SPEC-002
timestamp: 2025-12-18T11:00:00Z
summary: Another decision
---

Body for reindex test.
"""
        # PERF-001: Mock batch operations
        mock_git_ops.show_notes_batch.return_value = {"def7890123456": note_content}

        from git_notes_memory.note_parser import NoteParser

        parser = NoteParser()

        mock_embedding = MagicMock()
        mock_embedding.embed.return_value = [0.1] * 384
        # PERF-002: Mock batch embedding
        mock_embedding.embed_batch.return_value = [[0.1] * 384]

        service = SyncService(
            repo_path=tmp_path,
            index=real_index_service,
            git_ops=mock_git_ops,
            embedding_service=mock_embedding,
            note_parser=parser,
        )

        result = service.reindex(full=True)

        assert result == 1
        assert real_index_service.exists("decisions:def7890:0")
