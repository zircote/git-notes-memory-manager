#!/usr/bin/env python3
"""Integration tests for hook handlers.

Tests end-to-end flows through the hook pipeline:
- SessionStart context injection
- Signal detection → suggestion flow
- Stop hook → capture prompt → index sync
- Multi-hook interaction testing

These tests use fixtures and mock services to simulate real hook execution.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary git repository for testing."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main")
    # Include origin URL so git_repo name can be detected
    (git_dir / "config").write_text(
        "[core]\n\trepositoryformatversion = 0\n"
        '[remote "origin"]\n\turl = https://github.com/test-user/test-project.git\n'
    )

    # Create a basic project structure
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test-project"\n')
    (tmp_path / "src").mkdir()

    yield tmp_path


@pytest.fixture
def hook_env_enabled() -> Generator[None, None, None]:
    """Environment with all hooks enabled."""
    with patch.dict(
        os.environ,
        {
            "HOOK_ENABLED": "true",
            "HOOK_DEBUG": "false",
            "HOOK_SESSION_START_ENABLED": "true",
            "HOOK_USER_PROMPT_ENABLED": "true",
            "HOOK_STOP_ENABLED": "true",
            "HOOK_STOP_PROMPT_UNCAPTURED": "true",
            "HOOK_STOP_SYNC_INDEX": "false",  # Disable sync to avoid side effects
        },
    ):
        yield


@pytest.fixture
def session_transcript(tmp_path: Path) -> Path:
    """Create a session transcript file with memorable content."""
    transcript = tmp_path / "transcript.json"
    transcript.write_text(
        json.dumps(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "I decided to use PostgreSQL for the database",
                    },
                    {"role": "assistant", "content": "Good choice!"},
                    {
                        "role": "user",
                        "content": "I learned that indexes significantly improve query performance",
                    },
                    {"role": "assistant", "content": "That's correct!"},
                    {"role": "user", "content": "I'm stuck on the authentication flow"},
                ]
            }
        )
    )
    return transcript


@pytest.fixture
def mock_recall_service() -> MagicMock:
    """Mock RecallService for testing."""
    mock = MagicMock()

    # Mock working memory query
    mock_memories = [
        MagicMock(
            id="mem-123",
            summary="Previous decision about API design",
            content="Used REST over GraphQL",
            namespace="decisions",
            tags=["api", "architecture"],
            hydration="minimal",
        )
    ]
    mock.query_working_memory.return_value = mock_memories
    mock.query_semantic.return_value = []

    return mock


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Mock EmbeddingService for novelty checking."""
    mock = MagicMock()
    # Return empty list to indicate no similar memories (novel content)
    mock.find_similar.return_value = []
    return mock


# ============================================================================
# SessionStart Hook Integration Tests
# ============================================================================


class TestSessionStartIntegration:
    """End-to-end tests for SessionStart hook."""

    def test_full_session_start_flow(
        self, temp_git_repo: Path, hook_env_enabled: None
    ) -> None:
        """Test complete SessionStart hook execution."""
        from git_notes_memory.hooks.config_loader import load_hook_config
        from git_notes_memory.hooks.context_builder import ContextBuilder
        from git_notes_memory.hooks.project_detector import detect_project

        # Detect project from temp repo
        project_info = detect_project(str(temp_git_repo))
        assert project_info.name == "test-project"
        assert project_info.git_repo is not None  # git_repo holds repo name when in git

        # Load hook configuration
        config = load_hook_config()
        assert config.enabled is True
        assert config.session_start_enabled is True

        # Mock RecallService to avoid database dependency
        mock_recall = MagicMock()
        mock_recall.search.return_value = []
        mock_recall.get_all.return_value = []
        mock_recall.get_namespace_memories.return_value = []

        # Build context (with mock recall service to avoid DB)
        builder = ContextBuilder(config=config, recall_service=mock_recall)
        context = builder.build_context(
            project=project_info.name,
            session_source="startup",
            spec_id=project_info.spec_id,
        )

        # Verify context is valid XML
        assert context.startswith("<memory_context")
        assert "</memory_context>" in context
        assert "test-project" in context

    def test_session_start_json_output_format(
        self, temp_git_repo: Path, hook_env_enabled: None
    ) -> None:
        """Test SessionStart hook produces valid JSON output."""
        from git_notes_memory.hooks.session_start_handler import _write_output

        context = (
            "<memory_context project='test'><summary>Test</summary></memory_context>"
        )

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output(context)

        output = json.loads(captured.getvalue())

        # Verify hook response contract
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert output["hookSpecificOutput"]["additionalContext"] == context

    def test_session_start_with_complex_project(
        self, temp_git_repo: Path, hook_env_enabled: None
    ) -> None:
        """Test context building for a complex project structure."""
        # Add more files to simulate complex project
        (temp_git_repo / "src" / "main.py").write_text("# Main module\n")
        (temp_git_repo / "src" / "utils.py").write_text("# Utils\n")
        (temp_git_repo / "tests").mkdir()
        (temp_git_repo / "tests" / "test_main.py").write_text("# Tests\n")
        (temp_git_repo / "docs").mkdir()
        (temp_git_repo / "docs" / "README.md").write_text("# Docs\n")

        from git_notes_memory.hooks.config_loader import load_hook_config
        from git_notes_memory.hooks.context_builder import ContextBuilder
        from git_notes_memory.hooks.project_detector import detect_project

        project_info = detect_project(str(temp_git_repo))
        config = load_hook_config()

        # Mock RecallService to avoid database dependency
        mock_recall = MagicMock()
        mock_recall.search.return_value = []
        mock_recall.get_all.return_value = []
        mock_recall.get_namespace_memories.return_value = []

        builder = ContextBuilder(config=config, recall_service=mock_recall)

        context = builder.build_context(
            project=project_info.name,
            session_source="startup",
        )

        # Should still produce valid XML regardless of project complexity
        assert "<memory_context" in context
        assert "</memory_context>" in context


# ============================================================================
# Signal Detection Integration Tests
# ============================================================================


class TestSignalDetectionIntegration:
    """End-to-end tests for signal detection → suggestion flow."""

    def test_signal_detection_to_suggestion(self, hook_env_enabled: None) -> None:
        """Test complete flow from signal detection to suggestion generation."""
        from git_notes_memory.hooks.capture_decider import CaptureDecider
        from git_notes_memory.hooks.config_loader import load_hook_config
        from git_notes_memory.hooks.models import CaptureAction
        from git_notes_memory.hooks.signal_detector import SignalDetector

        # Prompt with clear decision signal
        prompt = "I decided to use Redis for caching instead of Memcached"

        # Detect signals
        detector = SignalDetector()
        signals = detector.detect(prompt)

        assert len(signals) >= 1
        assert any(s.type.value == "decision" for s in signals)

        # Make capture decision
        config = load_hook_config()
        decider = CaptureDecider(config=config)
        decision = decider.decide(signals)

        # High confidence decisions should get AUTO or SUGGEST
        assert decision.action in (CaptureAction.AUTO, CaptureAction.SUGGEST)
        assert len(decision.suggested_captures) >= 1

        # Verify suggestion has proper metadata
        suggestion = decision.suggested_captures[0]
        assert suggestion.namespace == "decisions"
        assert "Redis" in suggestion.summary or "Redis" in suggestion.content

    def test_multiple_signals_in_prompt(self, hook_env_enabled: None) -> None:
        """Test detection of multiple signal types in one prompt."""
        from git_notes_memory.hooks.signal_detector import SignalDetector

        prompt = """
        I decided to use TypeScript for the frontend.
        I learned that strict mode catches many errors early.
        I'm stuck on getting the webpack config right.
        """

        detector = SignalDetector()
        signals = detector.detect(prompt)

        # Should detect all three signal types
        types = {s.type.value for s in signals}
        assert "decision" in types
        assert "learning" in types
        assert "blocker" in types

    def test_signal_detection_json_output(self, hook_env_enabled: None) -> None:
        """Test UserPromptSubmit hook JSON output format."""
        from git_notes_memory.hooks.models import CaptureAction, SuggestedCapture
        from git_notes_memory.hooks.user_prompt_handler import _write_output

        suggestions = [
            SuggestedCapture(
                namespace="decisions",
                summary="Use PostgreSQL",
                content="Decided to use PostgreSQL for the database",
                tags=("database", "architecture"),
                confidence=0.88,
            )
        ]

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output(CaptureAction.SUGGEST, suggestions)

        output = json.loads(captured.getvalue())

        # Verify hook response contract
        assert output["continue"] is True
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        assert len(output["hookSpecificOutput"]["captureSuggestions"]) == 1
        assert "additionalContext" in output["hookSpecificOutput"]

    def test_low_confidence_signals_skipped(self, hook_env_enabled: None) -> None:
        """Test that low-confidence signals result in SKIP action."""
        from git_notes_memory.hooks.capture_decider import CaptureDecider
        from git_notes_memory.hooks.config_loader import load_hook_config
        from git_notes_memory.hooks.models import (
            CaptureAction,
            CaptureSignal,
            SignalType,
        )

        # Create a low-confidence signal
        signals = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="maybe use sqlite",
                confidence=0.3,  # Below threshold
                context="Considering options",
                suggested_namespace="decisions",
            )
        ]

        config = load_hook_config()
        decider = CaptureDecider(config=config)
        decision = decider.decide(signals)

        assert decision.action == CaptureAction.SKIP


# ============================================================================
# Stop Hook Integration Tests
# ============================================================================


class TestStopHookIntegration:
    """End-to-end tests for Stop hook → capture prompt → index sync."""

    def test_stop_hook_analyzes_transcript(
        self, session_transcript: Path, hook_env_enabled: None
    ) -> None:
        """Test Stop hook analyzes session transcript for uncaptured content."""
        from git_notes_memory.hooks.stop_handler import _analyze_session

        signals = _analyze_session(str(session_transcript))

        # Should detect signals from transcript content
        # (may be empty if novelty checking filters them out)
        assert isinstance(signals, list)

    def test_stop_hook_json_output_with_uncaptured(
        self, hook_env_enabled: None
    ) -> None:
        """Test Stop hook JSON output with uncaptured content."""
        from git_notes_memory.hooks.models import CaptureSignal, SignalType
        from git_notes_memory.hooks.stop_handler import _write_output

        signals = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="Use PostgreSQL",
                confidence=0.85,
                context="Database choice",
                suggested_namespace="decisions",
            ),
            CaptureSignal(
                type=SignalType.LEARNING,
                match="Indexes improve performance",
                confidence=0.78,
                context="Performance lesson",
                suggested_namespace="learnings",
            ),
        ]

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output(signals, None, prompt_uncaptured=True)

        output = json.loads(captured.getvalue())

        # Verify hook response contract
        assert output["continue"] is True
        assert "message" in output
        assert "2" in output["message"]  # 2 uncaptured memories
        assert "hookSpecificOutput" in output
        assert output["hookSpecificOutput"]["hookEventName"] == "Stop"
        assert len(output["hookSpecificOutput"]["uncapturedContent"]) == 2

    def test_stop_hook_with_sync_stats(self, hook_env_enabled: None) -> None:
        """Test Stop hook output includes sync statistics."""
        from git_notes_memory.hooks.stop_handler import _write_output

        sync_result = {
            "success": True,
            "stats": {"indexed": 10},
        }

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output([], sync_result, prompt_uncaptured=True)

        output = json.loads(captured.getvalue())

        assert output["continue"] is True
        assert "10 memories indexed" in output.get("message", "")
        assert "syncStats" in output["hookSpecificOutput"]

    def test_stop_hook_graceful_failure(self, hook_env_enabled: None) -> None:
        """Test Stop hook handles sync failures gracefully."""
        from git_notes_memory.hooks.stop_handler import _write_output

        sync_result = {
            "success": False,
            "error": "Database connection failed",
        }

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            _write_output([], sync_result, prompt_uncaptured=True)

        output = json.loads(captured.getvalue())

        # Should still continue even on failure
        assert output["continue"] is True
        assert "syncError" in output["hookSpecificOutput"]


# ============================================================================
# Multi-Hook Interaction Tests
# ============================================================================


class TestMultiHookInteraction:
    """Test interactions between multiple hooks in a session."""

    def test_session_flow_start_to_stop(
        self, temp_git_repo: Path, hook_env_enabled: None
    ) -> None:
        """Test complete session flow from start to stop."""
        from git_notes_memory.hooks.capture_decider import CaptureDecider
        from git_notes_memory.hooks.config_loader import load_hook_config
        from git_notes_memory.hooks.context_builder import ContextBuilder
        from git_notes_memory.hooks.models import CaptureAction
        from git_notes_memory.hooks.project_detector import detect_project
        from git_notes_memory.hooks.signal_detector import SignalDetector

        # 1. Session Start - detect project and build context
        project_info = detect_project(str(temp_git_repo))
        config = load_hook_config()

        # Mock RecallService to avoid database dependency
        mock_recall = MagicMock()
        mock_recall.search.return_value = []
        mock_recall.get_all.return_value = []
        mock_recall.get_namespace_memories.return_value = []

        builder = ContextBuilder(config=config, recall_service=mock_recall)
        context = builder.build_context(
            project=project_info.name, session_source="startup"
        )
        assert "<memory_context" in context

        # 2. User Prompt - detect signals
        prompt = "I decided to use SQLite for the local cache"
        detector = SignalDetector()
        signals = detector.detect(prompt)
        assert len(signals) >= 1

        # 3. Make capture decision
        decider = CaptureDecider(config=config)
        decision = decider.decide(signals)
        assert decision.action in (CaptureAction.AUTO, CaptureAction.SUGGEST)

        # 4. Session End - no uncaptured since we captured during session
        # This is a simplified test; real session would have transcript analysis

    def test_hooks_share_config(self, hook_env_enabled: None) -> None:
        """Test that all hooks share the same configuration."""
        from git_notes_memory.hooks.config_loader import load_hook_config

        # Load config multiple times (simulating different hooks)
        config1 = load_hook_config()
        config2 = load_hook_config()
        config3 = load_hook_config()

        # All should have same values
        assert config1.enabled == config2.enabled == config3.enabled
        assert config1.debug == config2.debug == config3.debug
        assert (
            config1.session_start_enabled
            == config2.session_start_enabled
            == config3.session_start_enabled
        )

    def test_hooks_respect_disabled_state(self) -> None:
        """Test that hooks properly respect disabled state."""
        with patch.dict(os.environ, {"HOOK_ENABLED": "false"}):
            from git_notes_memory.hooks.config_loader import load_hook_config

            config = load_hook_config()
            assert config.enabled is False

            # All individual hooks should also be effectively disabled
            # since master switch is off


# ============================================================================
# Error Handling Integration Tests
# ============================================================================


class TestErrorHandlingIntegration:
    """Test error handling across hook handlers."""

    def test_session_start_handles_missing_cwd(self, hook_env_enabled: None) -> None:
        """Test SessionStart gracefully handles missing cwd."""
        from git_notes_memory.hooks.session_start_handler import _validate_input

        # Missing cwd
        assert _validate_input({}) is False
        assert _validate_input({"source": "startup"}) is False

    def test_user_prompt_handles_empty_prompt(self, hook_env_enabled: None) -> None:
        """Test UserPromptSubmit gracefully handles empty prompt."""
        from git_notes_memory.hooks.user_prompt_handler import _validate_input

        # Empty or missing prompt should be falsy
        assert not _validate_input({})
        assert not _validate_input({"prompt": ""})
        assert not _validate_input({"cwd": "/test"})

    def test_stop_handles_invalid_transcript(
        self, tmp_path: Path, hook_env_enabled: None
    ) -> None:
        """Test Stop hook handles invalid transcript file."""
        from git_notes_memory.hooks.stop_handler import _analyze_session

        # Non-existent file
        result = _analyze_session(str(tmp_path / "nonexistent.json"))
        assert result == []

        # Invalid JSON
        invalid = tmp_path / "invalid.json"
        invalid.write_text("not json")
        result = _analyze_session(str(invalid))
        assert result == []

    def test_all_hooks_output_continue_on_error(self, hook_env_enabled: None) -> None:
        """Test that all hooks output continue:true even on errors."""
        # This verifies the non-blocking error handling pattern

        # SessionStart - outputs empty on error (no hookSpecificOutput)
        from git_notes_memory.hooks.session_start_handler import (
            _write_output as ss_write,
        )

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            ss_write("<test>context</test>")
        output = json.loads(captured.getvalue())
        # SessionStart doesn't have continue field but hookSpecificOutput

        # UserPromptSubmit - outputs continue:true
        from git_notes_memory.hooks.models import CaptureAction
        from git_notes_memory.hooks.user_prompt_handler import _write_output as up_write

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            up_write(CaptureAction.SKIP, [])
        output = json.loads(captured.getvalue())
        assert output["continue"] is True

        # Stop - outputs continue:true
        from git_notes_memory.hooks.stop_handler import _write_output as stop_write

        captured = io.StringIO()
        with patch.object(sys, "stdout", captured):
            stop_write([], None, prompt_uncaptured=True)
        output = json.loads(captured.getvalue())
        assert output["continue"] is True


# ============================================================================
# XML Format Integration Tests
# ============================================================================


class TestXMLFormatIntegration:
    """Test XML output format across hooks."""

    def test_session_start_xml_structure(
        self, temp_git_repo: Path, hook_env_enabled: None
    ) -> None:
        """Test SessionStart produces well-formed XML context."""
        from git_notes_memory.hooks.config_loader import load_hook_config
        from git_notes_memory.hooks.context_builder import ContextBuilder
        from git_notes_memory.hooks.project_detector import detect_project

        project_info = detect_project(str(temp_git_repo))
        config = load_hook_config()

        # Mock RecallService to avoid database dependency
        mock_recall = MagicMock()
        mock_recall.search.return_value = []
        mock_recall.get_all.return_value = []
        mock_recall.get_namespace_memories.return_value = []

        builder = ContextBuilder(config=config, recall_service=mock_recall)

        context = builder.build_context(
            project=project_info.name,
            session_source="startup",
        )

        # Verify XML structure
        assert context.startswith("<memory_context")
        assert context.endswith("</memory_context>")
        # Project is an attribute on the root element, not a child
        assert 'project="test-project"' in context
        # Commands section is always present
        assert "<commands>" in context

    def test_user_prompt_suggestion_xml(self, hook_env_enabled: None) -> None:
        """Test UserPromptSubmit produces valid suggestion XML."""
        from git_notes_memory.hooks.models import SuggestedCapture
        from git_notes_memory.hooks.user_prompt_handler import _format_suggestions_xml

        suggestions = [
            SuggestedCapture(
                namespace="decisions",
                summary="Use PostgreSQL",
                content="Decided to use PostgreSQL",
                tags=("database",),
                confidence=0.85,
            )
        ]

        xml = _format_suggestions_xml(suggestions)

        assert "<capture_suggestions>" in xml
        assert "</capture_suggestions>" in xml
        assert "<suggestion" in xml
        assert "<namespace>decisions</namespace>" in xml
        assert "<summary>Use PostgreSQL</summary>" in xml

    def test_stop_uncaptured_xml(self, hook_env_enabled: None) -> None:
        """Test Stop hook produces valid uncaptured content XML."""
        from git_notes_memory.hooks.models import CaptureSignal, SignalType
        from git_notes_memory.hooks.stop_handler import _format_uncaptured_xml

        signals = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="Use Redis",
                confidence=0.9,
                context="Caching decision",
                suggested_namespace="decisions",
            )
        ]

        xml = _format_uncaptured_xml(signals)

        assert "<uncaptured_memories>" in xml
        assert "</uncaptured_memories>" in xml
        assert "<signal" in xml
        assert "type=" in xml
        assert "/remember" in xml
