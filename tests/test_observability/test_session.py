"""Tests for session identification."""

from __future__ import annotations

from git_notes_memory.observability.session import (
    SessionInfo,
    generate_session_id,
    get_session_info,
    reset_session,
)


class TestSessionInfo:
    """Tests for SessionInfo dataclass."""

    def test_session_info_creation(self) -> None:
        """Test creating session info."""
        info = SessionInfo(
            hostname="testhost",
            repo_hash="abc12345",
            user_hash="xyz98765",
        )

        assert info.hostname == "testhost"
        assert info.repo_hash == "abc12345"
        assert info.user_hash == "xyz98765"

    def test_session_id_format(self) -> None:
        """Test session ID format."""
        info = SessionInfo(
            hostname="myhost",
            repo_hash="deadbeef",
            user_hash="cafebabe",
        )

        session_id = info.session_id

        # Format: {hostname}:{repo_hash}:{timestamp_hex}:{uuid_suffix}
        parts = session_id.split(":")
        assert len(parts) == 4
        assert parts[0] == "myhost"
        assert parts[1] == "deadbeef"
        # parts[2] is hex timestamp
        assert len(parts[3]) == 8  # UUID suffix

    def test_short_id(self) -> None:
        """Test short ID format."""
        info = SessionInfo(
            hostname="myhost",
            repo_hash="deadbeef",
            user_hash="cafebabe",
        )

        short_id = info.short_id

        # Format: {repo_hash}:{uuid_suffix}
        parts = short_id.split(":")
        assert len(parts) == 2
        assert parts[0] == "deadbeef"

    def test_start_time(self) -> None:
        """Test start_time property."""
        info = SessionInfo(
            hostname="host",
            repo_hash="repo",
            user_hash="user",
        )

        assert info.start_time is not None
        assert info.start_time.tzinfo is not None

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        info = SessionInfo(
            hostname="testhost",
            repo_hash="abc12345",
            user_hash="xyz98765",
        )

        data = info.to_dict()

        assert data["hostname"] == "testhost"
        assert data["repo_hash"] == "abc12345"
        assert data["user_hash"] == "xyz98765"
        assert "session_id" in data
        assert "short_id" in data
        assert "timestamp" in data
        assert "start_time" in data
        assert "uuid_suffix" in data

    def test_frozen_dataclass(self) -> None:
        """Test that session info is immutable."""
        import pytest

        info = SessionInfo(
            hostname="host",
            repo_hash="repo",
            user_hash="user",
        )

        with pytest.raises(AttributeError):
            info.hostname = "new_host"  # type: ignore[misc]


class TestGenerateSessionId:
    """Tests for generate_session_id function."""

    def test_generates_unique_ids(self) -> None:
        """Test each call generates unique ID."""
        id1 = generate_session_id()
        id2 = generate_session_id()

        assert id1 != id2

    def test_id_format(self) -> None:
        """Test generated ID has correct format."""
        session_id = generate_session_id()

        # Should have 4 colon-separated parts
        parts = session_id.split(":")
        assert len(parts) == 4


class TestGetSessionInfo:
    """Tests for get_session_info singleton."""

    def setup_method(self) -> None:
        """Reset session before test."""
        reset_session()

    def teardown_method(self) -> None:
        """Reset session after test."""
        reset_session()

    def test_returns_singleton(self) -> None:
        """Test get_session_info returns same instance."""
        info1 = get_session_info()
        info2 = get_session_info()

        assert info1 is info2

    def test_reset_creates_new_instance(self) -> None:
        """Test reset_session creates new instance."""
        info1 = get_session_info()
        reset_session()
        info2 = get_session_info()

        assert info1 is not info2
        assert info1.session_id != info2.session_id

    def test_session_has_hostname(self) -> None:
        """Test session includes hostname."""
        info = get_session_info()

        assert info.hostname is not None
        assert len(info.hostname) > 0

    def test_session_has_hashes(self) -> None:
        """Test session includes hashes."""
        info = get_session_info()

        assert info.repo_hash is not None
        assert len(info.repo_hash) == 8  # SHA256 truncated to 8 chars
        assert info.user_hash is not None
        assert len(info.user_hash) == 8
