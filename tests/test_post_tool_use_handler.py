"""Tests for git_notes_memory.hooks.post_tool_use_handler module.

Tests the PostToolUse hook handler including:
- Input validation
- Tool filtering
- Domain extraction integration
- Memory search integration
- XML output formatting
- Error handling
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import StringIO
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from git_notes_memory.hooks.hook_utils import read_json_input
from git_notes_memory.hooks.post_tool_use_handler import (
    DEFAULT_TIMEOUT,
    TRIGGERING_TOOLS,
    _extract_file_path,
    _format_memories_xml,
    _search_related_memories,
    _write_output,
    main,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass(frozen=True)
class MockMemory:
    """Mock Memory object for testing."""

    id: str
    namespace: str
    summary: str
    content: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MockMemoryResult:
    """Mock MemoryResult for testing."""

    memory: MockMemory
    distance: float


@pytest.fixture
def mock_hook_config() -> MagicMock:
    """Create mock HookConfig."""
    config = MagicMock()
    config.enabled = True
    config.debug = False
    config.post_tool_use_enabled = True
    config.post_tool_use_min_similarity = 0.6
    config.post_tool_use_max_results = 3
    config.post_tool_use_timeout = 5
    return config


@pytest.fixture
def sample_write_input() -> dict:
    """Sample Write tool input."""
    return {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/src/auth/jwt_handler.py",
            "content": "def validate_token(): pass",
        },
        "tool_response": {"success": True},
    }


@pytest.fixture
def sample_edit_input() -> dict:
    """Sample Edit tool input."""
    return {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/src/auth/jwt_handler.py",
            "old_string": "old",
            "new_string": "new",
        },
        "tool_response": {"success": True},
    }


@pytest.fixture
def sample_read_input() -> dict:
    """Sample Read tool input."""
    return {
        "tool_name": "Read",
        "tool_input": {
            "file_path": "/src/auth/jwt_handler.py",
        },
        "tool_response": {"content": "def validate_token(): pass"},
    }


@pytest.fixture
def sample_memories() -> list[MockMemoryResult]:
    """Sample memory results for testing."""
    return [
        MockMemoryResult(
            memory=MockMemory(
                id="decisions:abc123:0",
                namespace="decisions",
                summary="Use JWT for authentication",
                content="We decided to use JWT tokens for API authentication because...",
                tags=("auth", "jwt", "security"),
            ),
            distance=0.2,
        ),
        MockMemoryResult(
            memory=MockMemory(
                id="learnings:def456:0",
                namespace="learnings",
                summary="JWT token validation gotcha",
                content="TIL that JWT tokens need to be validated on every request...",
                tags=("jwt", "validation"),
            ),
            distance=0.3,
        ),
    ]


# =============================================================================
# Constants Tests
# =============================================================================


class TestConstants:
    """Test module constants."""

    def test_triggering_tools(self) -> None:
        """Test that correct tools trigger the hook."""
        assert "Read" in TRIGGERING_TOOLS
        assert "Write" in TRIGGERING_TOOLS
        assert "Edit" in TRIGGERING_TOOLS
        assert "MultiEdit" in TRIGGERING_TOOLS
        assert len(TRIGGERING_TOOLS) == 4

    def test_default_timeout(self) -> None:
        """Test default timeout is 5 seconds."""
        assert DEFAULT_TIMEOUT == 5


# =============================================================================
# Input Reading Tests
# =============================================================================


class TestReadInput:
    """Test read_json_input function (from hook_utils)."""

    def test_valid_json_input(self) -> None:
        """Test reading valid JSON input."""
        input_data = '{"tool_name": "Write", "tool_input": {}}'
        with patch("sys.stdin", StringIO(input_data)):
            result = read_json_input()
            assert result == {"tool_name": "Write", "tool_input": {}}

    def test_empty_input_raises(self) -> None:
        """Test that empty input raises ValueError."""
        with patch("sys.stdin", StringIO("")):
            with pytest.raises(ValueError, match="Empty input"):
                read_json_input()

    def test_whitespace_only_raises(self) -> None:
        """Test that whitespace-only input raises ValueError."""
        with patch("sys.stdin", StringIO("   \n\t  ")):
            with pytest.raises(ValueError, match="Empty input"):
                read_json_input()

    def test_invalid_json_raises(self) -> None:
        """Test that invalid JSON raises JSONDecodeError."""
        with patch("sys.stdin", StringIO("not valid json")):
            with pytest.raises(json.JSONDecodeError):
                read_json_input()

    def test_non_dict_raises(self) -> None:
        """Test that non-dict JSON raises ValueError."""
        with patch("sys.stdin", StringIO('["a", "b"]')):
            with pytest.raises(ValueError, match="Expected JSON object"):
                read_json_input()


# =============================================================================
# File Path Extraction Tests
# =============================================================================


class TestExtractFilePath:
    """Test _extract_file_path function."""

    def test_extract_from_write_input(self, sample_write_input: dict) -> None:
        """Test extraction from Write tool input."""
        path = _extract_file_path(sample_write_input)
        assert path == "/src/auth/jwt_handler.py"

    def test_extract_from_edit_input(self, sample_edit_input: dict) -> None:
        """Test extraction from Edit tool input."""
        path = _extract_file_path(sample_edit_input)
        assert path == "/src/auth/jwt_handler.py"

    def test_missing_tool_input(self) -> None:
        """Test when tool_input is missing."""
        path = _extract_file_path({})
        assert path is None

    def test_missing_file_path(self) -> None:
        """Test when file_path is missing from tool_input."""
        path = _extract_file_path({"tool_input": {"other": "value"}})
        assert path is None

    def test_non_dict_tool_input(self) -> None:
        """Test when tool_input is not a dict."""
        path = _extract_file_path({"tool_input": "string value"})
        assert path is None


# =============================================================================
# Memory Search Tests
# =============================================================================


class TestSearchRelatedMemories:
    """Test _search_related_memories function."""

    def test_successful_search(self, sample_memories: list[MockMemoryResult]) -> None:
        """Test successful memory search."""
        mock_recall = MagicMock()
        mock_recall.search.return_value = sample_memories

        with patch(
            "git_notes_memory.recall.get_default_service",
            return_value=mock_recall,
        ):
            results = _search_related_memories(
                terms=["auth", "jwt"],
                max_results=3,
                min_similarity=0.6,
            )

        assert len(results) == 2
        mock_recall.search.assert_called_once_with(
            query="auth jwt",
            k=3,
            min_similarity=0.6,
        )

    def test_import_error_returns_empty(self) -> None:
        """Test that ImportError returns empty list."""
        with patch(
            "git_notes_memory.recall.get_default_service",
            side_effect=ImportError("Module not found"),
        ):
            results = _search_related_memories(
                terms=["auth"],
                max_results=3,
                min_similarity=0.6,
            )

        assert results == []

    def test_exception_returns_empty(self) -> None:
        """Test that other exceptions return empty list."""
        mock_recall = MagicMock()
        mock_recall.search.side_effect = RuntimeError("Search failed")

        with patch(
            "git_notes_memory.recall.get_default_service",
            return_value=mock_recall,
        ):
            results = _search_related_memories(
                terms=["auth"],
                max_results=3,
                min_similarity=0.6,
            )

        assert results == []


# =============================================================================
# XML Formatting Tests
# =============================================================================


class TestFormatMemoriesXml:
    """Test _format_memories_xml function."""

    def test_empty_results(self) -> None:
        """Test that empty results returns empty string."""
        assert _format_memories_xml([], "/path/to/file.py") == ""

    def test_basic_formatting(self, sample_memories: list[MockMemoryResult]) -> None:
        """Test basic XML formatting."""
        xml = _format_memories_xml(sample_memories, "/src/auth/jwt_handler.py")

        assert "<related_memories>" in xml
        assert "</related_memories>" in xml
        assert "jwt_handler.py" in xml
        assert "decisions" in xml
        assert "learnings" in xml
        assert "Use JWT for authentication" in xml
        assert "JWT token validation gotcha" in xml

    def test_includes_similarity_score(
        self, sample_memories: list[MockMemoryResult]
    ) -> None:
        """Test that similarity score is included."""
        xml = _format_memories_xml(sample_memories, "/path/file.py")
        # distance=0.2 -> similarity=0.8
        assert 'similarity="0.80"' in xml
        # distance=0.3 -> similarity=0.7
        assert 'similarity="0.70"' in xml

    def test_includes_tags(self, sample_memories: list[MockMemoryResult]) -> None:
        """Test that tags are included."""
        xml = _format_memories_xml(sample_memories, "/path/file.py")
        assert "<tags>" in xml
        assert "<tag>auth</tag>" in xml
        assert "<tag>jwt</tag>" in xml

    def test_truncates_long_content(self) -> None:
        """Test that long content is truncated."""
        long_content = "x" * 300
        memories = [
            MockMemoryResult(
                memory=MockMemory(
                    id="test:abc:0",
                    namespace="learnings",
                    summary="Test",
                    content=long_content,
                ),
                distance=0.1,
            )
        ]

        xml = _format_memories_xml(memories, "/path/file.py")
        assert "..." in xml
        # Should have ~200 chars + ellipsis
        assert long_content[:200] in xml

    def test_handles_no_tags(self) -> None:
        """Test handling memory without tags."""
        memories = [
            MockMemoryResult(
                memory=MockMemory(
                    id="test:abc:0",
                    namespace="learnings",
                    summary="Test memory",
                    content="Some content",
                    tags=(),
                ),
                distance=0.1,
            )
        ]

        xml = _format_memories_xml(memories, "/path/file.py")
        # Tags section should not appear for empty tags
        assert xml.count("<tags>") == 0


# =============================================================================
# Output Writing Tests
# =============================================================================


class TestWriteOutput:
    """Test _write_output function."""

    def test_output_with_context(self, capsys: pytest.CaptureFixture) -> None:
        """Test output when context is provided."""
        _write_output("<related_memories>test</related_memories>")
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert (
            output["hookSpecificOutput"]["additionalContext"]
            == "<related_memories>test</related_memories>"
        )

    def test_output_without_context(self, capsys: pytest.CaptureFixture) -> None:
        """Test output when no context is provided."""
        _write_output()
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output == {"continue": True}

    def test_output_with_none_context(self, capsys: pytest.CaptureFixture) -> None:
        """Test output with explicit None context."""
        _write_output(None)
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output == {"continue": True}


# =============================================================================
# Main Function Tests
# =============================================================================


class TestMain:
    """Test main function integration."""

    def test_hooks_disabled(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when hooks are disabled globally."""
        mock_hook_config.enabled = False

        with (
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {"continue": True}

    def test_post_tool_use_disabled(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when PostToolUse hook is specifically disabled."""
        mock_hook_config.post_tool_use_enabled = False

        with (
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {"continue": True}

    def test_non_triggering_tool(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test with non-triggering tool (e.g., Bash)."""
        input_data = json.dumps({"tool_name": "Bash", "tool_input": {}})

        with (
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {"continue": True}

    def test_read_tool_triggers(
        self,
        mock_hook_config: MagicMock,
        sample_read_input: dict,
        sample_memories: list[MockMemoryResult],
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test that Read tool triggers the hook and injects memories."""
        mock_recall = MagicMock()
        mock_recall.search.return_value = sample_memories

        input_data = json.dumps(sample_read_input)

        with (
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            patch(
                "git_notes_memory.recall.get_default_service",
                return_value=mock_recall,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        # Should have hookSpecificOutput
        assert "hookSpecificOutput" in output
        assert "additionalContext" in output["hookSpecificOutput"]
        assert "<related_memories>" in output["hookSpecificOutput"]["additionalContext"]

    def test_no_file_path_in_input(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when tool_input has no file_path."""
        input_data = json.dumps({"tool_name": "Write", "tool_input": {}})

        with (
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {"continue": True}

    def test_successful_memory_injection(
        self,
        mock_hook_config: MagicMock,
        sample_write_input: dict,
        sample_memories: list[MockMemoryResult],
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test successful memory context injection."""
        mock_recall = MagicMock()
        mock_recall.search.return_value = sample_memories

        input_data = json.dumps(sample_write_input)

        with (
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            patch(
                "git_notes_memory.recall.get_default_service",
                return_value=mock_recall,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert "hookSpecificOutput" in output
        assert "<related_memories>" in output["hookSpecificOutput"]["additionalContext"]

    def test_no_memories_found(
        self,
        mock_hook_config: MagicMock,
        sample_write_input: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test when no related memories are found."""
        mock_recall = MagicMock()
        mock_recall.search.return_value = []

        input_data = json.dumps(sample_write_input)

        with (
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            patch(
                "git_notes_memory.recall.get_default_service",
                return_value=mock_recall,
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {"continue": True}

    def test_json_decode_error_graceful(
        self,
        mock_hook_config: MagicMock,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test graceful handling of JSON decode errors."""
        with (
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO("not valid json")),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {"continue": True}

    def test_exception_graceful_handling(
        self,
        mock_hook_config: MagicMock,
        sample_write_input: dict,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Test graceful handling of unexpected exceptions."""
        input_data = json.dumps(sample_write_input)

        with (
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.load_hook_config",
                return_value=mock_hook_config,
            ),
            patch("sys.stdin", StringIO(input_data)),
            patch(
                "git_notes_memory.hooks.post_tool_use_handler.extract_domain_terms",
                side_effect=RuntimeError("Unexpected error"),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == {"continue": True}
