"""Tests for git_notes_memory.hooks module.

Tests the hook infrastructure including:
- XML formatting (XMLBuilder)
- Configuration loading (HookConfig)
- Signal detection (SignalDetector)
- Novelty checking (NoveltyChecker)
- Capture decisions (CaptureDecider)
- Session analysis (SessionAnalyzer)
- Data models (SignalType, CaptureSignal, etc.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Import directly from concrete modules to help mypy with types
from git_notes_memory.hooks.capture_decider import CaptureDecider
from git_notes_memory.hooks.config_loader import HookConfig, load_hook_config
from git_notes_memory.hooks.models import (
    CaptureAction,
    CaptureDecision,
    CaptureSignal,
    NoveltyResult,
    SemanticContext,
    SignalType,
    SuggestedCapture,
    TokenBudget,
    WorkingMemory,
)
from git_notes_memory.hooks.novelty_checker import NoveltyChecker
from git_notes_memory.hooks.session_analyzer import SessionAnalyzer, TranscriptContent
from git_notes_memory.hooks.signal_detector import SignalDetector
from git_notes_memory.hooks.xml_formatter import XMLBuilder

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def xml_builder() -> XMLBuilder:
    """Create an XMLBuilder instance."""
    return XMLBuilder("test_root")


@pytest.fixture
def signal_detector() -> SignalDetector:
    """Create a SignalDetector instance."""
    return SignalDetector()


@pytest.fixture
def sample_decision_signal() -> CaptureSignal:
    """Create a sample decision signal."""
    return CaptureSignal(
        type=SignalType.DECISION,
        match="I decided to use PostgreSQL",
        confidence=0.9,
        context="Evaluating database options",
        suggested_namespace="decisions",
    )


@pytest.fixture
def sample_learning_signal() -> CaptureSignal:
    """Create a sample learning signal."""
    return CaptureSignal(
        type=SignalType.LEARNING,
        match="TIL that Python dataclasses support frozen",
        confidence=0.85,
        context="Working on immutable models",
        suggested_namespace="learnings",
    )


@pytest.fixture
def tmp_transcript(tmp_path: Path) -> Path:
    """Create a temporary transcript file."""
    transcript = tmp_path / "transcript.md"
    content = (
        "Human: I decided to use SQLite for the local cache.\n\n"
        "Assistant: Good choice for local storage.\n\n"
        "Human: TIL that SQLite supports JSON columns.\n\n"
        "Assistant: Yes, it has great JSON support.\n"
    )
    transcript.write_text(content)
    return transcript


# =============================================================================
# XMLBuilder Tests
# =============================================================================


class TestXMLBuilder:
    """Test the XMLBuilder class."""

    def test_create_empty_builder(self) -> None:
        """Test creating an empty XML builder."""
        builder = XMLBuilder("root")
        xml = builder.to_string()
        # Empty root may be self-closing (<root />) or full (<root></root>)
        assert "root" in xml
        assert xml.startswith("<")

    def test_add_element_with_text(self, xml_builder: XMLBuilder) -> None:
        """Test adding an element with text content."""
        xml_builder.add_element("root", "child", text="Hello World")
        xml = xml_builder.to_string()
        assert "<child>Hello World</child>" in xml

    def test_add_element_with_attributes(self, xml_builder: XMLBuilder) -> None:
        """Test adding an element with attributes."""
        xml_builder.add_element("root", "item", id="123", type="test")
        xml = xml_builder.to_string()
        assert 'id="123"' in xml
        assert 'type="test"' in xml

    def test_nested_elements(self, xml_builder: XMLBuilder) -> None:
        """Test adding nested elements."""
        parent_key = xml_builder.add_element("root", "parent")
        xml_builder.add_element(parent_key, "child", text="nested")
        xml = xml_builder.to_string()
        assert "<parent>" in xml
        assert "<child>nested</child>" in xml
        assert "</parent>" in xml

    def test_xml_escaping(self, xml_builder: XMLBuilder) -> None:
        """Test that special characters are escaped."""
        xml_builder.add_element("root", "text", text="<script>alert('xss')</script>")
        xml = xml_builder.to_string()
        assert "&lt;script&gt;" in xml
        assert "<script>" not in xml.replace("&lt;script&gt;", "")


# =============================================================================
# HookConfig Tests
# =============================================================================


class TestHookConfig:
    """Test the HookConfig dataclass and loading."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = HookConfig()
        assert config.enabled is True
        assert config.session_start_enabled is True
        assert config.capture_detection_enabled is False
        assert config.stop_enabled is True
        assert config.timeout == 30
        assert config.debug is False

    def test_load_config_with_env(self) -> None:
        """Test loading configuration from environment variables."""
        env = {
            "HOOK_ENABLED": "false",
            "HOOK_DEBUG": "true",
            "HOOK_TIMEOUT": "60",
        }
        config = load_hook_config(env)
        assert config.enabled is False
        assert config.debug is True
        assert config.timeout == 60

    def test_load_config_with_capture_settings(self) -> None:
        """Test loading capture detection settings."""
        env = {
            "HOOK_CAPTURE_DETECTION_ENABLED": "true",
            "HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE": "0.8",
            "HOOK_CAPTURE_DETECTION_AUTO_THRESHOLD": "0.9",
        }
        config = load_hook_config(env)
        assert config.capture_detection_enabled is True
        assert config.capture_detection_min_confidence == 0.8
        assert config.capture_detection_auto_threshold == 0.9

    def test_load_config_with_invalid_values(self) -> None:
        """Test that invalid values fall back to defaults."""
        env = {
            "HOOK_TIMEOUT": "not_a_number",
            "HOOK_CAPTURE_DETECTION_MIN_CONFIDENCE": "invalid",
        }
        config = load_hook_config(env)
        assert config.timeout == 30  # Default
        assert config.capture_detection_min_confidence == 0.7  # Default

    def test_budget_tier_lookup(self) -> None:
        """Test budget tier lookup."""
        config = HookConfig()
        total, working, semantic = config.get_budget_tier("simple")
        assert total == 500
        assert working == 300
        assert semantic == 100

    def test_budget_tier_invalid(self) -> None:
        """Test invalid budget tier raises error."""
        config = HookConfig()
        with pytest.raises(ValueError, match="Unknown complexity"):
            config.get_budget_tier("invalid")

    def test_pre_compact_prompt_first_default(self) -> None:
        """Test pre_compact_prompt_first defaults to False."""
        config = HookConfig()
        assert config.pre_compact_prompt_first is False

    def test_load_config_pre_compact_prompt_first_enabled(self) -> None:
        """Test loading pre_compact_prompt_first from environment."""
        env = {"HOOK_PRE_COMPACT_PROMPT_FIRST": "true"}
        config = load_hook_config(env)
        assert config.pre_compact_prompt_first is True

    def test_load_config_pre_compact_prompt_first_disabled(self) -> None:
        """Test disabling pre_compact_prompt_first via environment."""
        env = {"HOOK_PRE_COMPACT_PROMPT_FIRST": "false"}
        config = load_hook_config(env)
        assert config.pre_compact_prompt_first is False


# =============================================================================
# SignalType Tests
# =============================================================================


class TestSignalType:
    """Test the SignalType enum."""

    def test_all_signal_types_exist(self) -> None:
        """Test all expected signal types exist."""
        assert SignalType.DECISION
        assert SignalType.LEARNING
        assert SignalType.BLOCKER
        assert SignalType.RESOLUTION
        assert SignalType.PREFERENCE
        assert SignalType.EXPLICIT

    def test_suggested_namespace(self) -> None:
        """Test suggested namespace for each signal type."""
        assert SignalType.DECISION.suggested_namespace == "decisions"
        assert SignalType.LEARNING.suggested_namespace == "learnings"
        assert SignalType.BLOCKER.suggested_namespace == "blockers"
        assert SignalType.RESOLUTION.suggested_namespace == "solutions"
        assert SignalType.PREFERENCE.suggested_namespace == "preferences"
        assert SignalType.EXPLICIT.suggested_namespace == "notes"


# =============================================================================
# CaptureSignal Tests
# =============================================================================


class TestCaptureSignal:
    """Test the CaptureSignal dataclass."""

    def test_create_signal(self, sample_decision_signal: CaptureSignal) -> None:
        """Test creating a capture signal."""
        assert sample_decision_signal.type == SignalType.DECISION
        assert sample_decision_signal.confidence == 0.9
        assert sample_decision_signal.match == "I decided to use PostgreSQL"

    def test_signal_is_frozen(self, sample_decision_signal: CaptureSignal) -> None:
        """Test that CaptureSignal is immutable."""
        with pytest.raises(AttributeError):
            sample_decision_signal.confidence = 0.5  # type: ignore[misc]

    def test_invalid_confidence_raises(self) -> None:
        """Test that invalid confidence raises ValueError."""
        with pytest.raises(ValueError, match="Confidence must be"):
            CaptureSignal(
                type=SignalType.DECISION,
                match="test",
                confidence=1.5,  # Invalid
                context="test",
                suggested_namespace="decisions",
            )


# =============================================================================
# TokenBudget Tests
# =============================================================================


class TestTokenBudget:
    """Test the TokenBudget dataclass."""

    def test_create_budget(self) -> None:
        """Test creating a token budget."""
        budget = TokenBudget(
            total=1000,
            working_memory=600,
            semantic_context=300,
            commands=100,
        )
        assert budget.total == 1000
        assert budget.working_memory == 600

    def test_simple_budget_factory(self) -> None:
        """Test the simple budget factory method."""
        budget = TokenBudget.simple(1000)
        assert budget.total == 1000
        assert budget.working_memory + budget.semantic_context + budget.commands <= 1000

    def test_budget_exceeds_total_raises(self) -> None:
        """Test that exceeding total raises ValueError."""
        with pytest.raises(ValueError, match="Allocated tokens"):
            TokenBudget(
                total=100,
                working_memory=200,  # Exceeds total
                semantic_context=100,
            )


# =============================================================================
# SignalDetector Tests
# =============================================================================


class TestSignalDetector:
    """Test the SignalDetector class."""

    def test_detect_decision_signal(self, signal_detector: SignalDetector) -> None:
        """Test detecting decision signals."""
        text = "I decided to use PostgreSQL for the database."
        signals = signal_detector.detect(text)
        assert len(signals) >= 1
        assert any(s.type == SignalType.DECISION for s in signals)

    def test_detect_learning_signal(self, signal_detector: SignalDetector) -> None:
        """Test detecting learning signals."""
        text = "TIL that Python supports async/await natively."
        signals = signal_detector.detect(text)
        assert len(signals) >= 1
        assert any(s.type == SignalType.LEARNING for s in signals)

    def test_detect_blocker_signal(self, signal_detector: SignalDetector) -> None:
        """Test detecting blocker signals."""
        text = "I'm blocked by the authentication service being down."
        signals = signal_detector.detect(text)
        assert len(signals) >= 1
        assert any(s.type == SignalType.BLOCKER for s in signals)

    def test_detect_resolution_signal(self, signal_detector: SignalDetector) -> None:
        """Test detecting resolution signals."""
        text = "Fixed the issue by adding proper error handling."
        signals = signal_detector.detect(text)
        assert len(signals) >= 1
        assert any(s.type == SignalType.RESOLUTION for s in signals)

    def test_detect_explicit_signal(self, signal_detector: SignalDetector) -> None:
        """Test detecting explicit capture requests."""
        text = "Remember this: the API key is in environment variables."
        signals = signal_detector.detect(text)
        assert len(signals) >= 1
        assert any(s.type == SignalType.EXPLICIT for s in signals)

    def test_no_signals_in_plain_text(self, signal_detector: SignalDetector) -> None:
        """Test that plain text has no signals."""
        text = "The weather is nice today."
        signals = signal_detector.detect(text)
        assert len(signals) == 0

    def test_empty_text(self, signal_detector: SignalDetector) -> None:
        """Test empty text returns no signals."""
        signals = signal_detector.detect("")
        assert len(signals) == 0

    def test_signal_context_extraction(self, signal_detector: SignalDetector) -> None:
        """Test that context is extracted around matches."""
        text = "After much deliberation, I decided to use Redis for caching."
        signals = signal_detector.detect(text)
        assert len(signals) >= 1
        # Context should include surrounding text
        decision_signal = next(s for s in signals if s.type == SignalType.DECISION)
        assert (
            "Redis" in decision_signal.context or "caching" in decision_signal.context
        )

    def test_confidence_scoring(self, signal_detector: SignalDetector) -> None:
        """Test that confidence scores are reasonable."""
        text = "I decided to implement a caching layer."
        signals = signal_detector.detect(text)
        assert len(signals) >= 1
        for signal in signals:
            assert 0.0 <= signal.confidence <= 1.0


# =============================================================================
# NoveltyChecker Tests
# =============================================================================


class TestNoveltyChecker:
    """Test the NoveltyChecker class."""

    def test_check_novelty_returns_result(
        self, sample_decision_signal: CaptureSignal
    ) -> None:
        """Test that check_novelty returns a NoveltyResult."""
        checker = NoveltyChecker(novelty_threshold=0.3)
        result = checker.check_signal_novelty(sample_decision_signal)
        assert isinstance(result, NoveltyResult)
        assert 0.0 <= result.novelty_score <= 1.0

    def test_novelty_threshold(self) -> None:
        """Test novelty threshold is respected."""
        checker = NoveltyChecker(novelty_threshold=0.5)
        assert checker.novelty_threshold == 0.5

    def test_novelty_result_is_novel_flag(self) -> None:
        """Test NoveltyResult is_novel flag."""
        # High novelty score should be novel
        result = NoveltyResult(novelty_score=0.8, is_novel=True)
        assert result.is_novel is True

        # Low novelty score should not be novel
        result = NoveltyResult(novelty_score=0.1, is_novel=False)
        assert result.is_novel is False


# =============================================================================
# CaptureDecider Tests
# =============================================================================


class TestCaptureDecider:
    """Test the CaptureDecider class."""

    def test_decide_auto_for_high_confidence(self) -> None:
        """Test AUTO action for high confidence signals."""
        config = HookConfig(
            capture_detection_auto_threshold=0.95,
            capture_detection_min_confidence=0.7,
        )
        decider = CaptureDecider(config=config)

        signal = CaptureSignal(
            type=SignalType.EXPLICIT,
            match="Remember this important note",
            confidence=0.98,  # Very high
            context="context",
            suggested_namespace="notes",
        )

        decision = decider.decide([signal])
        assert decision.action == CaptureAction.AUTO

    def test_decide_suggest_for_medium_confidence(self) -> None:
        """Test SUGGEST action for medium confidence signals."""
        config = HookConfig(
            capture_detection_auto_threshold=0.95,
            capture_detection_min_confidence=0.7,
        )
        decider = CaptureDecider(config=config)

        signal = CaptureSignal(
            type=SignalType.DECISION,
            match="I decided to try a new approach",
            confidence=0.85,  # Medium
            context="context",
            suggested_namespace="decisions",
        )

        decision = decider.decide([signal])
        assert decision.action == CaptureAction.SUGGEST

    def test_decide_skip_for_low_confidence(self) -> None:
        """Test SKIP action for low confidence signals."""
        config = HookConfig(
            capture_detection_min_confidence=0.7,
        )
        decider = CaptureDecider(config=config)

        signal = CaptureSignal(
            type=SignalType.PREFERENCE,
            match="I like this color",
            confidence=0.5,  # Low
            context="context",
            suggested_namespace="preferences",
        )

        decision = decider.decide([signal])
        assert decision.action == CaptureAction.SKIP

    def test_decide_with_empty_signals(self) -> None:
        """Test decision with no signals."""
        decider = CaptureDecider()
        decision = decider.decide([])
        assert decision.action == CaptureAction.SKIP

    def test_suggested_captures_generated(self) -> None:
        """Test that suggested captures are generated."""
        config = HookConfig(
            capture_detection_auto_threshold=0.95,
            capture_detection_min_confidence=0.7,
        )
        decider = CaptureDecider(config=config)

        signal = CaptureSignal(
            type=SignalType.LEARNING,
            match="I learned that async is better",
            confidence=0.85,
            context="Working on performance improvements",
            suggested_namespace="learnings",
        )

        decision = decider.decide([signal])
        assert len(decision.suggested_captures) > 0
        assert decision.suggested_captures[0].namespace == "learnings"


# =============================================================================
# SessionAnalyzer Tests
# =============================================================================


class TestSessionAnalyzer:
    """Test the SessionAnalyzer class."""

    def test_parse_transcript_file(self, tmp_transcript: Path) -> None:
        """Test parsing a transcript file."""
        analyzer = SessionAnalyzer()
        content = analyzer.parse_transcript(tmp_transcript)
        assert content is not None
        assert isinstance(content, TranscriptContent)
        assert len(content.user_messages) > 0

    def test_parse_nonexistent_file(self, tmp_path: Path) -> None:
        """Test parsing a nonexistent file returns None."""
        analyzer = SessionAnalyzer()
        content = analyzer.parse_transcript(tmp_path / "nonexistent.md")
        assert content is None

    def test_analyze_transcript(self, tmp_transcript: Path) -> None:
        """Test analyzing a transcript for signals."""
        analyzer = SessionAnalyzer(min_confidence=0.5, max_signals=10)
        signals = analyzer.analyze(tmp_transcript, check_novelty=False)
        # Should find decision and learning signals
        assert isinstance(signals, list)

    def test_analyze_with_novelty_check(self, tmp_transcript: Path) -> None:
        """Test analyzing with novelty check enabled."""
        analyzer = SessionAnalyzer()
        signals = analyzer.analyze(tmp_transcript, check_novelty=True)
        assert isinstance(signals, list)

    def test_has_uncaptured_content(self, tmp_transcript: Path) -> None:
        """Test checking for uncaptured content."""
        analyzer = SessionAnalyzer(min_confidence=0.5)
        has_content = analyzer.has_uncaptured_content(
            tmp_transcript, check_novelty=False
        )
        assert isinstance(has_content, bool)

    def test_analyze_content_directly(self) -> None:
        """Test analyzing content string directly."""
        analyzer = SessionAnalyzer(min_confidence=0.5)
        content = "I decided to use Docker for containerization."
        signals = analyzer.analyze_content(content, check_novelty=False)
        assert isinstance(signals, list)


# =============================================================================
# TranscriptContent Tests
# =============================================================================


class TestTranscriptContent:
    """Test the TranscriptContent dataclass."""

    def test_create_transcript_content(self) -> None:
        """Test creating transcript content."""
        content = TranscriptContent(
            user_messages=("Hello", "How are you?"),
            assistant_messages=("Hi!", "I am fine."),
            raw_content="raw",
            total_turns=2,
        )
        assert len(content.user_messages) == 2
        assert content.total_turns == 2

    def test_all_user_content(self) -> None:
        """Test combining all user messages."""
        content = TranscriptContent(
            user_messages=("First message", "Second message"),
            assistant_messages=(),
            raw_content="raw",
            total_turns=2,
        )
        combined = content.all_user_content
        assert "First message" in combined
        assert "Second message" in combined


# =============================================================================
# Data Models Tests
# =============================================================================


class TestDataModels:
    """Test additional data models."""

    def test_novelty_result_validation(self) -> None:
        """Test NoveltyResult validation."""
        with pytest.raises(ValueError, match="Novelty score must be"):
            NoveltyResult(novelty_score=1.5, is_novel=True)

    def test_capture_decision_structure(self) -> None:
        """Test CaptureDecision structure."""
        decision = CaptureDecision(
            action=CaptureAction.SUGGEST,
            signals=(),
            suggested_captures=(),
            reason="Test reason",
        )
        assert decision.action == CaptureAction.SUGGEST
        assert decision.reason == "Test reason"

    def test_suggested_capture_structure(self) -> None:
        """Test SuggestedCapture structure."""
        suggestion = SuggestedCapture(
            namespace="learnings",
            summary="Test summary",
            content="Test content",
            tags=("test", "learning"),
            confidence=0.85,
        )
        assert suggestion.namespace == "learnings"
        assert len(suggestion.tags) == 2

    def test_working_memory_count(self) -> None:
        """Test WorkingMemory count property."""
        memory = WorkingMemory(
            active_blockers=(),
            recent_decisions=(),
            pending_actions=(),
        )
        assert memory.count == 0

    def test_semantic_context_count(self) -> None:
        """Test SemanticContext count property."""
        context = SemanticContext(
            relevant_learnings=(),
            related_patterns=(),
        )
        assert context.count == 0


# =============================================================================
# Module Exports Tests
# =============================================================================


class TestModuleExports:
    """Test that the hooks module exports all expected items."""

    def test_lazy_loading_works(self) -> None:
        """Test that lazy loading works correctly."""
        from git_notes_memory import hooks

        # These should all be accessible via lazy loading
        assert hooks.XMLBuilder is not None
        assert hooks.HookConfig is not None
        assert hooks.SignalDetector is not None
        assert hooks.CaptureDecider is not None
        assert hooks.SessionAnalyzer is not None

    def test_all_exports_importable(self) -> None:
        """Test that all __all__ exports are importable."""
        import git_notes_memory.hooks as hooks_module
        from git_notes_memory.hooks import __all__

        for name in __all__:
            assert hasattr(hooks_module, name), f"Missing export: {name}"
