#!/usr/bin/env python3
"""Performance tests for hook system timing requirements.

These tests verify that hook operations complete within acceptable
time limits to avoid blocking Claude Code sessions.

Target timing:
- Hook handlers: <100ms total execution
- Signal detection: <50ms per prompt
- XML generation: <20ms per context
- Project detection: <50ms
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def hook_env() -> Generator[None, None, None]:
    """Set up hook environment variables."""
    env = {
        "HOOK_ENABLED": "true",
        "HOOK_DEBUG": "false",
        "HOOK_SESSION_START_ENABLED": "true",
        "HOOK_USER_PROMPT_ENABLED": "true",
        "HOOK_STOP_ENABLED": "true",
    }
    with patch.dict(os.environ, env):
        yield


@pytest.fixture
def sample_prompts() -> list[str]:
    """Generate sample prompts for performance testing."""
    return [
        # Decision prompts
        "I decided to use PostgreSQL instead of MySQL for better JSON support",
        "After reviewing options, we've decided to implement a microservices architecture",
        "The team decided to adopt TypeScript for better type safety",
        # Learning prompts
        "I learned that connection pooling can improve database performance by 50%",
        "TIL that async/await is more efficient than callback-based code",
        "Today I discovered that Redis can be used as a message broker",
        # Blocker prompts
        "We're blocked by the external API being unavailable",
        "The deployment is blocked waiting for security approval",
        "Progress is blocked by missing documentation",
        # Plain prompts (no signals)
        "Can you help me write a function to sort a list?",
        "What is the best way to handle errors in Python?",
        "Please explain how this code works",
    ]


# ============================================================================
# Signal Detection Performance Tests
# ============================================================================


class TestSignalDetectorPerformance:
    """Performance tests for signal detection."""

    @pytest.mark.parametrize("iterations", [10, 50, 100])
    def test_signal_detection_throughput(
        self, sample_prompts: list[str], hook_env: None, iterations: int
    ) -> None:
        """Test signal detection can process prompts quickly."""
        from git_notes_memory.hooks.signal_detector import SignalDetector

        detector = SignalDetector()

        start = time.perf_counter()
        for _ in range(iterations):
            for prompt in sample_prompts:
                detector.detect(prompt)
        elapsed = time.perf_counter() - start

        prompts_processed = iterations * len(sample_prompts)
        avg_time_ms = (elapsed / prompts_processed) * 1000

        # Target: <5ms per prompt on average
        assert avg_time_ms < 5, f"Signal detection too slow: {avg_time_ms:.2f}ms/prompt"

    def test_single_prompt_latency(
        self, sample_prompts: list[str], hook_env: None
    ) -> None:
        """Test single prompt detection completes quickly."""
        from git_notes_memory.hooks.signal_detector import SignalDetector

        detector = SignalDetector()

        for prompt in sample_prompts:
            start = time.perf_counter()
            detector.detect(prompt)
            elapsed_ms = (time.perf_counter() - start) * 1000

            # Target: <50ms per prompt
            assert elapsed_ms < 50, f"Detection too slow for: {prompt[:50]}..."

    def test_long_prompt_handling(self, hook_env: None) -> None:
        """Test detection handles long prompts without timeout."""
        from git_notes_memory.hooks.signal_detector import SignalDetector

        detector = SignalDetector()

        # Generate a long prompt (5000 chars)
        long_prompt = "I decided to use PostgreSQL. " * 200

        start = time.perf_counter()
        detector.detect(long_prompt)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Target: <100ms even for long prompts
        assert elapsed_ms < 100, f"Long prompt too slow: {elapsed_ms:.2f}ms"


# ============================================================================
# XML Generation Performance Tests
# ============================================================================


class TestXMLBuilderPerformance:
    """Performance tests for XML generation."""

    def test_xml_builder_creation(self, hook_env: None) -> None:
        """Test XMLBuilder creation is fast."""
        from git_notes_memory.hooks.xml_formatter import XMLBuilder

        start = time.perf_counter()
        for _ in range(1000):
            builder = XMLBuilder("test")
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 1000
        # Target: <0.1ms per creation
        assert avg_ms < 0.1, f"XMLBuilder creation too slow: {avg_ms:.4f}ms"

    def test_xml_element_addition(self, hook_env: None) -> None:
        """Test adding elements is fast."""
        from git_notes_memory.hooks.xml_formatter import XMLBuilder

        builder = XMLBuilder("test")

        start = time.perf_counter()
        for i in range(100):
            builder.add_element("root", f"item_{i}", text=f"value_{i}")
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Target: <5ms for 100 elements
        assert elapsed_ms < 5, f"Element addition too slow: {elapsed_ms:.2f}ms"

    def test_xml_serialization(self, hook_env: None) -> None:
        """Test XML serialization is fast."""
        from git_notes_memory.hooks.xml_formatter import XMLBuilder

        builder = XMLBuilder("test")
        for i in range(50):
            builder.add_element("root", f"item_{i}", text=f"value_{i}", attr=f"val_{i}")

        start = time.perf_counter()
        for _ in range(100):
            builder.to_string()
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 100
        # Target: <2ms per serialization
        assert avg_ms < 2, f"XML serialization too slow: {avg_ms:.2f}ms"


# ============================================================================
# Config Loading Performance Tests
# ============================================================================


class TestConfigPerformance:
    """Performance tests for configuration loading."""

    def test_config_loading_speed(self, hook_env: None) -> None:
        """Test config loading is fast."""
        from git_notes_memory.hooks.config_loader import load_hook_config

        start = time.perf_counter()
        for _ in range(100):
            load_hook_config()
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 100
        # Target: <1ms per load
        assert avg_ms < 1, f"Config loading too slow: {avg_ms:.2f}ms"

    def test_config_initialization(self, hook_env: None) -> None:
        """Test HookConfig initialization is fast."""
        from git_notes_memory.hooks.config_loader import HookConfig

        start = time.perf_counter()
        for _ in range(1000):
            HookConfig()
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 1000
        # Target: <0.05ms per creation
        assert avg_ms < 0.05, f"HookConfig init too slow: {avg_ms:.4f}ms"


# ============================================================================
# Project Detection Performance Tests
# ============================================================================


class TestProjectDetectionPerformance:
    """Performance tests for project detection."""

    def test_project_detection_speed(self, tmp_path: Path, hook_env: None) -> None:
        """Test project detection completes quickly."""
        from git_notes_memory.hooks.project_detector import detect_project

        # Create a simple project structure
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"')

        start = time.perf_counter()
        for _ in range(50):
            detect_project(str(tmp_path))
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 50
        # Target: <10ms per detection
        assert avg_ms < 10, f"Project detection too slow: {avg_ms:.2f}ms"


# ============================================================================
# Capture Decider Performance Tests
# ============================================================================


class TestCaptureDeciderPerformance:
    """Performance tests for capture decision logic."""

    def test_decision_speed(self, hook_env: None) -> None:
        """Test capture decision is fast (without database novelty checks)."""
        from git_notes_memory.hooks.capture_decider import CaptureDecider
        from git_notes_memory.hooks.config_loader import HookConfig
        from git_notes_memory.hooks.models import CaptureSignal, SignalType

        # Disable novelty checking to test pure decision logic
        config = HookConfig(capture_detection_novelty_threshold=1.0)  # Skip novelty
        decider = CaptureDecider(config=config, check_novelty_enabled=False)

        signals = [
            CaptureSignal(
                type=SignalType.DECISION,
                match="Use PostgreSQL",
                confidence=0.9,
                context="Database choice",
                suggested_namespace="decisions",
            ),
            CaptureSignal(
                type=SignalType.LEARNING,
                match="Indexes help",
                confidence=0.8,
                context="Performance",
                suggested_namespace="learnings",
            ),
        ]

        start = time.perf_counter()
        for _ in range(1000):
            decider.decide(signals)
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 1000
        # Target: <1ms per decision (pure logic, no DB calls)
        assert avg_ms < 1, f"Decision too slow: {avg_ms:.4f}ms"


# ============================================================================
# Session Analyzer Performance Tests
# ============================================================================


class TestSessionAnalyzerPerformance:
    """Performance tests for session transcript analysis."""

    def test_transcript_parsing_speed(self, tmp_path: Path, hook_env: None) -> None:
        """Test transcript parsing is fast."""
        import json

        from git_notes_memory.hooks.session_analyzer import SessionAnalyzer

        # Create a transcript with 100 messages
        transcript = tmp_path / "transcript.jsonl"
        lines = []
        for i in range(100):
            if i % 2 == 0:
                lines.append(json.dumps({"role": "user", "content": f"Message {i}"}))
            else:
                lines.append(
                    json.dumps({"role": "assistant", "content": f"Response {i}"})
                )
        transcript.write_text("\n".join(lines))

        analyzer = SessionAnalyzer()

        start = time.perf_counter()
        for _ in range(10):
            analyzer.analyze(transcript, check_novelty=False)
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 10
        # Target: <50ms per analysis
        assert avg_ms < 50, f"Transcript analysis too slow: {avg_ms:.2f}ms"


# ============================================================================
# End-to-End Pipeline Performance Tests
# ============================================================================


class TestPipelinePerformance:
    """Performance tests for complete hook pipelines."""

    def test_signal_detection_pipeline(
        self, sample_prompts: list[str], hook_env: None
    ) -> None:
        """Test full signal detection pipeline meets timing target."""
        from git_notes_memory.hooks.capture_decider import CaptureDecider
        from git_notes_memory.hooks.config_loader import HookConfig
        from git_notes_memory.hooks.signal_detector import SignalDetector

        # Disable novelty checking to avoid DB calls in pipeline test
        config = HookConfig()
        detector = SignalDetector()
        decider = CaptureDecider(config=config, check_novelty_enabled=False)

        total_time_ms: float = 0.0
        for prompt in sample_prompts:
            start = time.perf_counter()

            signals = detector.detect(prompt)
            if signals:
                decider.decide(signals)

            elapsed_ms = (time.perf_counter() - start) * 1000
            total_time_ms += elapsed_ms

        avg_ms = total_time_ms / len(sample_prompts)
        # Target: <10ms per prompt through full pipeline
        assert avg_ms < 10, f"Pipeline too slow: {avg_ms:.2f}ms/prompt"

    def test_xml_generation_pipeline(self, hook_env: None) -> None:
        """Test XML context generation pipeline meets timing target."""
        from git_notes_memory.hooks.models import CaptureSignal, SignalType
        from git_notes_memory.hooks.stop_handler import _format_uncaptured_xml

        signals = [
            CaptureSignal(
                type=SignalType.DECISION,
                match=f"Decision {i}",
                confidence=0.9,
                context=f"Context {i}",
                suggested_namespace="decisions",
            )
            for i in range(10)
        ]

        start = time.perf_counter()
        for _ in range(100):
            _format_uncaptured_xml(signals)
        elapsed_ms = (time.perf_counter() - start) * 1000

        avg_ms = elapsed_ms / 100
        # Target: <5ms per XML generation
        assert avg_ms < 5, f"XML generation too slow: {avg_ms:.2f}ms"


# ============================================================================
# Memory Usage Tests
# ============================================================================


class TestMemoryUsage:
    """Tests for memory efficiency."""

    def test_signal_detector_memory_reuse(self, hook_env: None) -> None:
        """Test SignalDetector can be reused without memory leaks."""
        from git_notes_memory.hooks.signal_detector import SignalDetector

        detector = SignalDetector()

        # Process many prompts
        for _ in range(1000):
            detector.detect("I decided to use PostgreSQL for the database")

        # Should not accumulate state
        # (This is a basic sanity check - actual memory profiling would need
        # more sophisticated tools)

    def test_xml_builder_cleanup(self, hook_env: None) -> None:
        """Test XMLBuilder doesn't accumulate state across uses."""
        from git_notes_memory.hooks.xml_formatter import XMLBuilder

        for _ in range(100):
            builder = XMLBuilder("test")
            for i in range(50):
                builder.add_element("root", f"item_{i}", text=f"value_{i}")
            builder.to_string()
            # Builder goes out of scope, memory should be freed
