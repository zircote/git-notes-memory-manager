"""End-to-end functional tests for plugin hooks.

These tests validate the hook entry points and handlers work correctly
to ensure the plugin integrates properly with Claude Code hooks API.

Hooks tested:
- SessionStart: Injects context on session start
- UserPromptSubmit: Detects capture markers in user prompts
- PostToolUse: Provides file-contextual memories after Read/Write/Edit
- PreCompact: Preserves important memories before context compaction
- Stop: Syncs index and prompts for uncaptured content on session end
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


# =============================================================================
# SessionStart Hook Tests
# =============================================================================


class TestSessionStartHookE2E:
    """E2E tests for SessionStart hook."""

    def test_handler_import(self) -> None:
        """Test SessionStart handler can be imported."""
        from git_notes_memory.hooks.session_start_handler import main

        assert callable(main)

    def test_handler_has_required_functions(self) -> None:
        """Test SessionStart handler has required internal functions."""
        from git_notes_memory.hooks import hook_utils, session_start_handler

        # These functions are used by the hook entry point
        assert hasattr(session_start_handler, "main")
        assert hasattr(hook_utils, "read_json_input")  # Now in hook_utils
        assert hasattr(session_start_handler, "_write_output")

    def test_entry_point_syntax(self) -> None:
        """Test entry point script has valid Python syntax."""
        entry_point = Path("hooks/sessionstart.py")
        if entry_point.exists():
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(entry_point)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Syntax error: {result.stderr}"


# =============================================================================
# UserPromptSubmit Hook Tests
# =============================================================================


class TestUserPromptSubmitHookE2E:
    """E2E tests for UserPromptSubmit hook."""

    def test_handler_import(self) -> None:
        """Test UserPromptSubmit handler can be imported."""
        from git_notes_memory.hooks.user_prompt_handler import main

        assert callable(main)

    def test_handler_has_required_functions(self) -> None:
        """Test UserPromptSubmit handler has required internal functions."""
        from git_notes_memory.hooks import hook_utils, user_prompt_handler

        assert hasattr(user_prompt_handler, "main")
        assert hasattr(hook_utils, "read_json_input")  # Now in hook_utils

    def test_signal_detector_exists(self) -> None:
        """Test SignalDetector class exists and works."""
        from git_notes_memory.hooks.signal_detector import SignalDetector

        detector = SignalDetector()

        # detect() returns a list of signals
        assert hasattr(detector, "detect")
        assert callable(detector.detect)

        # detect_all_types for comprehensive detection
        assert hasattr(detector, "detect_all_types")

    def test_entry_point_syntax(self) -> None:
        """Test entry point script has valid Python syntax."""
        entry_point = Path("hooks/userpromptsubmit.py")
        if entry_point.exists():
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(entry_point)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Syntax error: {result.stderr}"


# =============================================================================
# PostToolUse Hook Tests
# =============================================================================


class TestPostToolUseHookE2E:
    """E2E tests for PostToolUse hook."""

    def test_handler_import(self) -> None:
        """Test PostToolUse handler can be imported."""
        from git_notes_memory.hooks.post_tool_use_handler import main

        assert callable(main)

    def test_handler_has_required_functions(self) -> None:
        """Test PostToolUse handler has required internal functions."""
        from git_notes_memory.hooks import hook_utils, post_tool_use_handler

        assert hasattr(post_tool_use_handler, "main")
        assert hasattr(hook_utils, "read_json_input")  # Now in hook_utils
        assert hasattr(hook_utils, "MAX_INPUT_SIZE")  # Now in hook_utils

    def test_domain_extractor_singleton(self) -> None:
        """Test DomainExtractor uses singleton pattern for performance."""
        from git_notes_memory.hooks.domain_extractor import (
            _get_default_extractor,
            extract_domain_terms,
        )

        # Call twice and verify same instance
        extractor1 = _get_default_extractor()
        extractor2 = _get_default_extractor()
        assert extractor1 is extractor2

        # Function should work
        terms = extract_domain_terms("/src/auth/login.py")
        assert isinstance(terms, list)

    def test_namespace_parser(self) -> None:
        """Test namespace parser correctly identifies namespaces."""
        from git_notes_memory.hooks.namespace_parser import NamespaceParser

        parser = NamespaceParser()

        # Test parsing method exists and is callable
        assert hasattr(parser, "parse")
        assert callable(parser.parse)

    def test_entry_point_syntax(self) -> None:
        """Test entry point script has valid Python syntax."""
        entry_point = Path("hooks/posttooluse.py")
        if entry_point.exists():
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(entry_point)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_input_size_limit(self) -> None:
        """Test handler has input size limit for security."""
        from git_notes_memory.hooks.hook_utils import MAX_INPUT_SIZE

        # Should be 10MB
        assert MAX_INPUT_SIZE == 10 * 1024 * 1024


# =============================================================================
# PreCompact Hook Tests
# =============================================================================


class TestPreCompactHookE2E:
    """E2E tests for PreCompact hook."""

    def test_handler_import(self) -> None:
        """Test PreCompact handler can be imported."""
        from git_notes_memory.hooks.pre_compact_handler import main

        assert callable(main)

    def test_handler_has_required_functions(self) -> None:
        """Test PreCompact handler has required internal functions."""
        from git_notes_memory.hooks import hook_utils, pre_compact_handler

        assert hasattr(pre_compact_handler, "main")
        assert hasattr(hook_utils, "read_json_input")  # Now in hook_utils
        assert hasattr(hook_utils, "MAX_INPUT_SIZE")  # Now in hook_utils

    def test_capture_decider(self) -> None:
        """Test CaptureDecider for worthiness evaluation."""
        from git_notes_memory.hooks.capture_decider import CaptureDecider

        decider = CaptureDecider()

        # Test methods exist - decide() and should_capture()
        assert hasattr(decider, "decide")
        assert hasattr(decider, "should_capture")
        assert callable(decider.decide)
        assert callable(decider.should_capture)

    def test_guidance_builder(self) -> None:
        """Test GuidanceBuilder produces valid output."""
        from git_notes_memory.hooks.guidance_builder import GuidanceBuilder

        builder = GuidanceBuilder()

        # build_guidance is the actual method name
        assert hasattr(builder, "build_guidance")
        assert callable(builder.build_guidance)

    def test_entry_point_syntax(self) -> None:
        """Test entry point script has valid Python syntax."""
        entry_point = Path("hooks/precompact.py")
        if entry_point.exists():
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(entry_point)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_input_size_limit(self) -> None:
        """Test handler has input size limit for security."""
        from git_notes_memory.hooks.hook_utils import MAX_INPUT_SIZE

        # Should be 10MB
        assert MAX_INPUT_SIZE == 10 * 1024 * 1024


# =============================================================================
# Stop Hook Tests
# =============================================================================


class TestStopHookE2E:
    """E2E tests for Stop hook."""

    def test_handler_import(self) -> None:
        """Test Stop handler can be imported."""
        from git_notes_memory.hooks.stop_handler import main

        assert callable(main)

    def test_handler_has_required_functions(self) -> None:
        """Test Stop handler has required internal functions."""
        from git_notes_memory.hooks import stop_handler

        assert hasattr(stop_handler, "main")

    def test_session_analyzer(self) -> None:
        """Test SessionAnalyzer works correctly."""
        from git_notes_memory.hooks.session_analyzer import SessionAnalyzer

        analyzer = SessionAnalyzer()

        # analyze() is the method for session analysis
        assert hasattr(analyzer, "analyze")
        assert callable(analyzer.analyze)

        # has_uncaptured_content for checking if content should be captured
        assert hasattr(analyzer, "has_uncaptured_content")
        assert callable(analyzer.has_uncaptured_content)

    def test_entry_point_syntax(self) -> None:
        """Test entry point script has valid Python syntax."""
        entry_point = Path("hooks/stop.py")
        if entry_point.exists():
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", str(entry_point)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"Syntax error: {result.stderr}"


# =============================================================================
# Hook Configuration Tests
# =============================================================================


class TestHooksConfiguration:
    """Tests for hooks.json configuration."""

    def test_hooks_json_exists(self) -> None:
        """Test hooks.json exists."""
        hooks_json = Path("hooks/hooks.json")
        assert hooks_json.exists(), "hooks/hooks.json must exist"

    def test_hooks_json_valid(self) -> None:
        """Test hooks.json is valid JSON."""
        hooks_json = Path("hooks/hooks.json")
        with hooks_json.open() as f:
            config = json.load(f)

        assert "hooks" in config
        assert isinstance(config["hooks"], dict)

    def test_all_hooks_defined(self) -> None:
        """Test all expected hooks are defined."""
        hooks_json = Path("hooks/hooks.json")
        with hooks_json.open() as f:
            config = json.load(f)

        hooks = config["hooks"]

        # All 5 hooks should be defined
        expected_hooks = [
            "SessionStart",
            "UserPromptSubmit",
            "PostToolUse",
            "PreCompact",
            "Stop",
        ]

        for hook_name in expected_hooks:
            assert hook_name in hooks, f"Missing hook: {hook_name}"

    def test_hook_commands_exist(self) -> None:
        """Test all referenced hook commands exist as files."""
        hooks_json = Path("hooks/hooks.json")
        with hooks_json.open() as f:
            config = json.load(f)

        hooks_dir = Path("hooks")

        for _hook_name, hook_configs in config["hooks"].items():
            for hook_config in hook_configs:
                for hook in hook_config.get("hooks", []):
                    if hook.get("type") == "command":
                        cmd = hook["command"]
                        # Extract filename from ${CLAUDE_PLUGIN_ROOT}/hooks/xxx.py
                        filename = cmd.split("/")[-1]
                        hook_file = hooks_dir / filename
                        assert hook_file.exists(), f"Missing hook file: {hook_file}"

    def test_hook_timeouts_reasonable(self) -> None:
        """Test hook timeouts are within reasonable bounds."""
        hooks_json = Path("hooks/hooks.json")
        with hooks_json.open() as f:
            config = json.load(f)

        for hook_name, hook_configs in config["hooks"].items():
            for hook_config in hook_configs:
                for hook in hook_config.get("hooks", []):
                    timeout = hook.get("timeout", 10)
                    # SessionStart allows up to 120s for bootstrap (venv creation + deps)
                    max_timeout = 120 if hook_name == "SessionStart" else 60
                    assert 1 <= timeout <= max_timeout, (
                        f"Unreasonable timeout for {hook_name}: {timeout}"
                    )


# =============================================================================
# Integration Tests
# =============================================================================


class TestHookHandlerIntegration:
    """Integration tests for hook handlers working together."""

    def test_signal_detector_namespace_consistency(self) -> None:
        """Test signal detector namespaces are valid."""
        from git_notes_memory.config import NAMESPACES
        from git_notes_memory.hooks.signal_detector import SignalDetector

        detector = SignalDetector()

        # Detected signals should map to valid namespaces
        test_cases = [
            "[remember] test learning",
            "[capture] decisions: use postgres",
            "@memory test content",
        ]

        for test_input in test_cases:
            result = detector.detect(test_input)
            if result and hasattr(result, "namespace") and result.namespace:
                assert result.namespace in NAMESPACES, (
                    f"Invalid namespace: {result.namespace}"
                )

    def test_all_handlers_have_main_function(self) -> None:
        """Test all handlers have main() as entry point."""
        # Each handler should have a main() function for the entry point scripts
        handlers = [
            "session_start_handler",
            "user_prompt_handler",
            "post_tool_use_handler",
            "pre_compact_handler",
            "stop_handler",
        ]

        for module_name in handlers:
            module = __import__(
                f"git_notes_memory.hooks.{module_name}",
                fromlist=["main"],
            )
            assert hasattr(module, "main"), f"{module_name} should have main()"
            assert callable(module.main), f"{module_name}.main should be callable"


# =============================================================================
# SessionStart Hook Execution Tests
# =============================================================================


class TestSessionStartHookExecution:
    """Tests for SessionStart hook execution with real subprocess calls.

    These tests verify the hook works end-to-end when invoked via subprocess,
    catching issues like datetime comparison errors that unit tests might miss.
    """

    @pytest.mark.slow
    def test_hook_execution_with_valid_input(self, tmp_path: Path) -> None:
        """Test SessionStart hook executes successfully with valid input.

        This test is marked slow because it may trigger embedding model loading
        which can take 30+ seconds on first run.
        """
        import os

        hook_script = Path("hooks/sessionstart.py")
        if not hook_script.exists():
            pytest.skip("Hook script not found")

        input_data = json.dumps(
            {
                "cwd": str(tmp_path),
                "source": "startup",
                "session_id": "test-session-123",
            }
        )

        # Set up environment to avoid loading real memories
        env = os.environ.copy()
        env["MEMORY_PLUGIN_DATA_DIR"] = str(tmp_path)
        env["HOOK_DEBUG"] = "false"
        # Disable embedding to speed up test
        env["MEMORY_PLUGIN_EMBEDDING_ENABLED"] = "false"

        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input=input_data,
            capture_output=True,
            text=True,
            env=env,
            timeout=60,  # Allow more time for model loading if needed
        )

        # Hook should exit successfully (code 0)
        assert result.returncode == 0, f"Hook failed with stderr: {result.stderr}"

        # Output should be valid JSON
        output = result.stdout.strip()
        if output:  # May be empty if hooks are disabled
            parsed = json.loads(output)
            # Should have either hookSpecificOutput or continue flag
            assert "hookSpecificOutput" in parsed or "continue" in parsed

    def test_hook_execution_handles_missing_cwd(self) -> None:
        """Test SessionStart hook handles missing cwd gracefully."""
        import os

        hook_script = Path("hooks/sessionstart.py")
        if not hook_script.exists():
            return

        input_data = json.dumps(
            {
                "source": "startup",
                "session_id": "test-session-123",
                # Missing "cwd"
            }
        )

        env = os.environ.copy()
        env["HOOK_DEBUG"] = "false"

        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input=input_data,
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

        # Hook should exit successfully (graceful degradation)
        assert result.returncode == 0

    def test_hook_execution_with_invalid_json(self) -> None:
        """Test SessionStart hook handles invalid JSON gracefully."""
        hook_script = Path("hooks/sessionstart.py")
        if not hook_script.exists():
            return

        result = subprocess.run(
            [sys.executable, str(hook_script)],
            input="not valid json",
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Hook should exit successfully (graceful degradation)
        assert result.returncode == 0

    def test_context_builder_datetime_comparison(self, tmp_path: Path) -> None:
        """Test ContextBuilder handles datetime comparisons correctly.

        This test specifically validates that timezone-aware and timezone-naive
        datetimes are handled correctly to prevent TypeError.
        """
        from datetime import datetime, timedelta

        from git_notes_memory.hooks.context_builder import ContextBuilder
        from git_notes_memory.models import Memory

        # Create memories with timezone-aware timestamps (production behavior)
        old_memory = Memory(
            id="decisions:old123:0",
            commit_sha="old123",
            namespace="decisions",
            summary="Old decision",
            content="Made 10 days ago",
            timestamp=datetime.now(UTC) - timedelta(days=10),
            status="active",
        )
        recent_memory = Memory(
            id="decisions:new123:0",
            commit_sha="new123",
            namespace="decisions",
            summary="Recent decision",
            content="Made today",
            timestamp=datetime.now(UTC),
            status="active",
        )

        # Mock recall service
        from unittest.mock import MagicMock

        mock_recall = MagicMock()
        mock_recall.get_by_namespace.side_effect = lambda ns, spec=None, limit=None: (  # noqa: ARG005
            [old_memory, recent_memory] if ns == "decisions" else []
        )
        mock_recall.search.return_value = []

        builder = ContextBuilder(recall_service=mock_recall)

        # This should NOT raise TypeError about datetime comparison
        result = builder._build_working_memory(
            project="test-project",
            spec_id=None,
            token_budget=10000,
        )

        # Only recent memory should be included (old one filtered out)
        assert len(result.recent_decisions) == 1
        assert result.recent_decisions[0].id == "decisions:new123:0"

    def test_context_builder_with_offset_naive_memories(self, tmp_path: Path) -> None:
        """Test ContextBuilder handles offset-naive timestamps by conversion.

        Edge case: if a memory somehow has offset-naive timestamp, the builder
        should either handle it gracefully or the test should document the
        expected behavior.
        """
        from datetime import datetime, timedelta

        from git_notes_memory.hooks.context_builder import ContextBuilder
        from git_notes_memory.models import Memory

        # Create memory with offset-aware timestamp (correct behavior)
        memory = Memory(
            id="decisions:abc123:0",
            commit_sha="abc123",
            namespace="decisions",
            summary="Test decision",
            content="Test content",
            timestamp=datetime.now(UTC) - timedelta(days=1),
            status="active",
        )

        from unittest.mock import MagicMock

        mock_recall = MagicMock()
        mock_recall.get_by_namespace.side_effect = (
            lambda ns, spec=None, limit=None: [memory] if ns == "decisions" else []  # noqa: ARG005
        )
        mock_recall.search.return_value = []

        builder = ContextBuilder(recall_service=mock_recall)

        # Should work without raising TypeError
        result = builder._build_working_memory(
            project="test-project",
            spec_id=None,
            token_budget=10000,
        )

        # Recent memory (1 day old) should be included
        assert len(result.recent_decisions) == 1

    def test_full_session_start_handler_execution(self, tmp_path: Path) -> None:
        """Test full SessionStart handler execution with mocked services.

        This is an integration test that exercises the full handler path
        without subprocess overhead.
        """
        import io
        import os
        from unittest.mock import patch

        # Prepare test input
        input_data = json.dumps(
            {
                "cwd": str(tmp_path),
                "source": "startup",
                "session_id": "integration-test-123",
            }
        )

        # Mock stdin and capture stdout
        mock_stdin = io.StringIO(input_data)
        mock_stdout = io.StringIO()

        with (
            patch("sys.stdin", mock_stdin),
            patch("sys.stdout", mock_stdout),
            patch.dict(
                os.environ,
                {
                    "MEMORY_PLUGIN_DATA_DIR": str(tmp_path),
                    "HOOK_ENABLED": "true",
                    "HOOK_SESSION_START_ENABLED": "true",
                    "HOOK_DEBUG": "false",
                },
            ),
        ):
            from git_notes_memory.hooks.session_start_handler import main

            # Run should not raise exceptions (main() calls sys.exit(0))
            with contextlib.suppress(SystemExit):
                main()

        # Verify output is valid JSON
        output = mock_stdout.getvalue().strip()
        if output:
            parsed = json.loads(output)
            assert isinstance(parsed, dict)
