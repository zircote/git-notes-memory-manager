"""Tests for hook integration module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from git_notes_memory.subconsciousness.hook_integration import (
    HookIntegrationResult,
    analyze_session_transcript,
    is_subconsciousness_available,
)


class TestHookIntegrationResult:
    """Tests for HookIntegrationResult dataclass."""

    def test_basic_result(self) -> None:
        """Test basic result creation."""
        result = HookIntegrationResult(
            success=True,
            captured_count=5,
            auto_approved_count=2,
            pending_count=3,
            blocked_count=1,
            discarded_count=0,
            errors=(),
            summary="Memories: 2 auto-captured, 3 pending review",
        )
        assert result.success
        assert result.captured_count == 5
        assert result.auto_approved_count == 2

    def test_disabled_result(self) -> None:
        """Test disabled result factory."""
        result = HookIntegrationResult.disabled()
        assert result.success
        assert result.captured_count == 0
        assert "disabled" in result.summary.lower()

    def test_empty_result(self) -> None:
        """Test empty result factory."""
        result = HookIntegrationResult.empty()
        assert result.success
        assert result.captured_count == 0
        assert "no memories" in result.summary.lower()

    def test_error_result(self) -> None:
        """Test error result factory."""
        result = HookIntegrationResult.error("Something went wrong")
        assert not result.success
        assert "Something went wrong" in result.errors
        assert "error" in result.summary.lower()

    def test_is_frozen(self) -> None:
        """Test result is immutable."""
        result = HookIntegrationResult.empty()
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]


class TestIsSubconsciousnessAvailable:
    """Tests for availability check."""

    def test_disabled_when_master_switch_off(self) -> None:
        """Test disabled when MEMORY_SUBCONSCIOUSNESS_ENABLED is false."""
        with patch.dict(
            "os.environ",
            {"MEMORY_SUBCONSCIOUSNESS_ENABLED": "false"},
            clear=False,
        ):
            assert not is_subconsciousness_available()

    def test_disabled_when_implicit_capture_off(self) -> None:
        """Test disabled when implicit capture is off."""
        with patch.dict(
            "os.environ",
            {
                "MEMORY_SUBCONSCIOUSNESS_ENABLED": "true",
                "MEMORY_IMPLICIT_CAPTURE_ENABLED": "false",
            },
            clear=False,
        ):
            assert not is_subconsciousness_available()

    def test_disabled_when_no_api_key(self) -> None:
        """Test disabled when no API key for non-Ollama provider."""
        with patch.dict(
            "os.environ",
            {
                "MEMORY_SUBCONSCIOUSNESS_ENABLED": "true",
                "MEMORY_LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "",
            },
            clear=False,
        ):
            # Clear the key
            import os

            old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
            try:
                assert not is_subconsciousness_available()
            finally:
                if old_key:
                    os.environ["ANTHROPIC_API_KEY"] = old_key

    def test_enabled_with_ollama(self) -> None:
        """Test enabled with Ollama (no API key needed)."""
        with patch.dict(
            "os.environ",
            {
                "MEMORY_SUBCONSCIOUSNESS_ENABLED": "true",
                "MEMORY_LLM_PROVIDER": "ollama",
            },
            clear=False,
        ):
            assert is_subconsciousness_available()


class TestAnalyzeSessionTranscript:
    """Tests for session analysis."""

    @pytest.mark.asyncio
    async def test_disabled_returns_disabled_result(self) -> None:
        """Test disabled subconsciousness returns disabled result."""
        with patch(
            "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
            return_value=False,
        ):
            result = await analyze_session_transcript("/tmp/transcript.txt")
            assert result.success
            assert "disabled" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        """Test missing transcript file returns error."""
        with patch(
            "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
            return_value=True,
        ):
            result = await analyze_session_transcript(tmp_path / "nonexistent.txt")
            assert not result.success
            assert "not found" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_empty_transcript_returns_empty(self, tmp_path: Path) -> None:
        """Test empty transcript returns empty result."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("")

        with patch(
            "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
            return_value=True,
        ):
            result = await analyze_session_transcript(transcript_file)
            assert result.success
            assert "no memories" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_whitespace_transcript_returns_empty(self, tmp_path: Path) -> None:
        """Test whitespace-only transcript returns empty result."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("   \n\n  \t  \n")

        with patch(
            "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
            return_value=True,
        ):
            result = await analyze_session_transcript(transcript_file)
            assert result.success
            assert result.captured_count == 0

    @pytest.mark.asyncio
    async def test_successful_capture(self, tmp_path: Path) -> None:
        """Test successful capture returns results."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text(
            "user: What database should we use?\n"
            "assistant: We should use PostgreSQL for persistence."
        )

        # Mock the service result
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.capture_count = 2
        mock_result.auto_approved_count = 1
        mock_result.blocked_count = 0
        mock_result.discarded_count = 0
        mock_result.errors = ()

        mock_service = MagicMock()
        mock_service.capture_from_transcript = AsyncMock(return_value=mock_result)
        mock_service.expire_pending_captures.return_value = 0

        with (
            patch(
                "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
                return_value=True,
            ),
            patch(
                "git_notes_memory.subconsciousness.implicit_capture_service.get_implicit_capture_service",
                return_value=mock_service,
            ),
        ):
            result = await analyze_session_transcript(
                transcript_file, session_id="test-session"
            )

            assert result.success
            assert result.captured_count == 2
            assert result.auto_approved_count == 1
            assert result.pending_count == 1
            assert "1 auto-captured" in result.summary
            assert "1 pending review" in result.summary

    @pytest.mark.asyncio
    async def test_timeout_handling(self, tmp_path: Path) -> None:
        """Test timeout returns error result."""
        import asyncio

        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("user: test\nassistant: test")

        async def slow_capture(*args, **kwargs):
            await asyncio.sleep(10)  # Very slow
            return MagicMock()

        mock_service = MagicMock()
        mock_service.capture_from_transcript = slow_capture
        mock_service.expire_pending_captures.return_value = 0

        with (
            patch(
                "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
                return_value=True,
            ),
            patch(
                "git_notes_memory.subconsciousness.implicit_capture_service.get_implicit_capture_service",
                return_value=mock_service,
            ),
        ):
            result = await analyze_session_transcript(
                transcript_file, timeout_seconds=0.1
            )

            assert not result.success
            assert "timed out" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_exception_handling(self, tmp_path: Path) -> None:
        """Test exception returns error result."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("user: test\nassistant: test")

        mock_service = MagicMock()
        mock_service.capture_from_transcript = AsyncMock(
            side_effect=RuntimeError("LLM crashed")
        )
        mock_service.expire_pending_captures.return_value = 0

        with (
            patch(
                "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
                return_value=True,
            ),
            patch(
                "git_notes_memory.subconsciousness.implicit_capture_service.get_implicit_capture_service",
                return_value=mock_service,
            ),
        ):
            result = await analyze_session_transcript(transcript_file)

            assert not result.success
            assert "LLM crashed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_blocked_count_in_summary(self, tmp_path: Path) -> None:
        """Test blocked memories appear in summary."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("user: test\nassistant: test")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.capture_count = 1
        mock_result.auto_approved_count = 1
        mock_result.blocked_count = 2
        mock_result.discarded_count = 0
        mock_result.errors = ()

        mock_service = MagicMock()
        mock_service.capture_from_transcript = AsyncMock(return_value=mock_result)
        mock_service.expire_pending_captures.return_value = 0

        with (
            patch(
                "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
                return_value=True,
            ),
            patch(
                "git_notes_memory.subconsciousness.implicit_capture_service.get_implicit_capture_service",
                return_value=mock_service,
            ),
        ):
            result = await analyze_session_transcript(transcript_file)

            assert result.blocked_count == 2
            assert "2 blocked" in result.summary

    @pytest.mark.asyncio
    async def test_no_captures_summary(self, tmp_path: Path) -> None:
        """Test summary when no memories captured."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("user: hi\nassistant: hello")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.capture_count = 0
        mock_result.auto_approved_count = 0
        mock_result.blocked_count = 0
        mock_result.discarded_count = 5
        mock_result.errors = ()

        mock_service = MagicMock()
        mock_service.capture_from_transcript = AsyncMock(return_value=mock_result)
        mock_service.expire_pending_captures.return_value = 0

        with (
            patch(
                "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
                return_value=True,
            ),
            patch(
                "git_notes_memory.subconsciousness.implicit_capture_service.get_implicit_capture_service",
                return_value=mock_service,
            ),
        ):
            result = await analyze_session_transcript(transcript_file)

            assert result.captured_count == 0
            assert result.discarded_count == 5
            assert "no memories" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_expiration_runs(self, tmp_path: Path) -> None:
        """Test that expiration runs during analysis."""
        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("user: test\nassistant: test")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.capture_count = 0
        mock_result.auto_approved_count = 0
        mock_result.blocked_count = 0
        mock_result.discarded_count = 0
        mock_result.errors = ()

        mock_service = MagicMock()
        mock_service.capture_from_transcript = AsyncMock(return_value=mock_result)
        mock_service.expire_pending_captures.return_value = 3  # 3 expired

        with (
            patch(
                "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
                return_value=True,
            ),
            patch(
                "git_notes_memory.subconsciousness.implicit_capture_service.get_implicit_capture_service",
                return_value=mock_service,
            ),
        ):
            await analyze_session_transcript(transcript_file)

            mock_service.expire_pending_captures.assert_called_once()


class TestAnalyzeSessionTranscriptSync:
    """Tests for synchronous wrapper."""

    def test_sync_wrapper_disabled(self, tmp_path: Path) -> None:
        """Test sync wrapper returns disabled result when disabled."""
        from git_notes_memory.subconsciousness.hook_integration import (
            analyze_session_transcript_sync,
        )

        with patch(
            "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
            return_value=False,
        ):
            result = analyze_session_transcript_sync(tmp_path / "test.txt")
            assert result.success
            assert "disabled" in result.summary.lower()

    def test_sync_wrapper_returns_result(self, tmp_path: Path) -> None:
        """Test sync wrapper returns correct result."""
        from git_notes_memory.subconsciousness.hook_integration import (
            analyze_session_transcript_sync,
        )

        transcript_file = tmp_path / "transcript.txt"
        transcript_file.write_text("user: test\nassistant: test")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.capture_count = 1
        mock_result.auto_approved_count = 1
        mock_result.blocked_count = 0
        mock_result.discarded_count = 0
        mock_result.errors = ()

        mock_service = MagicMock()
        mock_service.capture_from_transcript = AsyncMock(return_value=mock_result)
        mock_service.expire_pending_captures.return_value = 0

        with (
            patch(
                "git_notes_memory.subconsciousness.hook_integration.is_subconsciousness_available",
                return_value=True,
            ),
            patch(
                "git_notes_memory.subconsciousness.implicit_capture_service.get_implicit_capture_service",
                return_value=mock_service,
            ),
        ):
            result = analyze_session_transcript_sync(transcript_file)

            assert result.success
            assert result.captured_count == 1
            assert "1 auto-captured" in result.summary
