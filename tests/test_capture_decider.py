"""Tests for the CaptureDecider class.

Comprehensive test coverage for capture decision logic including:
- Initialization with default and custom thresholds
- Decision making based on signal confidence
- Novelty checking integration
- Summary and tag extraction
- Edge cases and unicode handling
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from git_notes_memory.hooks.capture_decider import CaptureDecider
from git_notes_memory.hooks.config_loader import HookConfig
from git_notes_memory.hooks.models import (
    CaptureAction,
    CaptureSignal,
    NoveltyResult,
    SignalType,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_novelty_checker() -> MagicMock:
    """Create a mock NoveltyChecker that returns novel content by default."""
    mock = MagicMock()
    mock.check_signal_novelty.return_value = NoveltyResult(
        novelty_score=0.8,
        is_novel=True,
        similar_memory_ids=[],
        highest_similarity=0.2,
    )
    return mock


@pytest.fixture
def decider(mock_novelty_checker: MagicMock) -> CaptureDecider:
    """Create a CaptureDecider with mocked novelty checker."""
    return CaptureDecider(
        novelty_checker=mock_novelty_checker,
        check_novelty_enabled=True,
    )


@pytest.fixture
def decider_no_novelty() -> CaptureDecider:
    """Create a CaptureDecider with novelty checking disabled."""
    return CaptureDecider(check_novelty_enabled=False)


def make_signal(
    signal_type: SignalType = SignalType.DECISION,
    confidence: float = 0.8,
    match: str = "I decided to use PostgreSQL",
    context: str | None = None,
    suggested_namespace: str | None = None,
    position: int = 0,
) -> CaptureSignal:
    """Helper to create CaptureSignal instances."""
    return CaptureSignal(
        type=signal_type,
        match=match,
        confidence=confidence,
        context=context or match,
        suggested_namespace=suggested_namespace or signal_type.suggested_namespace,
        position=position,
    )


# =============================================================================
# Initialization Tests
# =============================================================================


class TestCaptureDeciderInit:
    """Tests for CaptureDecider initialization."""

    def test_default_thresholds(self) -> None:
        """CaptureDecider initializes with default thresholds."""
        decider = CaptureDecider()
        assert decider.auto_threshold == 0.95
        assert decider.suggest_threshold == 0.7
        assert decider.novelty_threshold == 0.3
        assert decider.check_novelty_enabled is True

    def test_custom_thresholds(self) -> None:
        """CaptureDecider accepts custom thresholds."""
        decider = CaptureDecider(
            auto_threshold=0.9,
            suggest_threshold=0.6,
            novelty_threshold=0.4,
            check_novelty_enabled=False,
        )
        assert decider.auto_threshold == 0.9
        assert decider.suggest_threshold == 0.6
        assert decider.novelty_threshold == 0.4
        assert decider.check_novelty_enabled is False

    def test_config_override(self) -> None:
        """CaptureDecider uses HookConfig values when provided."""
        config = HookConfig(
            capture_detection_auto_threshold=0.85,
            capture_detection_min_confidence=0.5,
            capture_detection_novelty_threshold=0.2,
        )
        decider = CaptureDecider(
            auto_threshold=0.99,  # Should be overridden
            suggest_threshold=0.9,  # Should be overridden
            novelty_threshold=0.5,  # Should be overridden
            config=config,
        )
        assert decider.auto_threshold == 0.85
        assert decider.suggest_threshold == 0.5
        assert decider.novelty_threshold == 0.2

    def test_novelty_checker_injection(self, mock_novelty_checker: MagicMock) -> None:
        """CaptureDecider accepts injected NoveltyChecker."""
        decider = CaptureDecider(novelty_checker=mock_novelty_checker)
        assert decider._novelty_checker is mock_novelty_checker

    def test_lazy_novelty_checker_creation(self) -> None:
        """CaptureDecider creates NoveltyChecker lazily."""
        decider = CaptureDecider()
        assert decider._novelty_checker is None
        # Accessing should create it (NoveltyChecker is imported inside method)
        with patch(
            "git_notes_memory.hooks.novelty_checker.NoveltyChecker"
        ) as mock_class:
            mock_class.return_value = MagicMock()
            checker = decider._get_novelty_checker()
            assert checker is not None
            mock_class.assert_called_once_with(novelty_threshold=0.3)


# =============================================================================
# decide() Method Tests - Empty and Single Signal
# =============================================================================


class TestDecideEmptySignals:
    """Tests for decide() with empty signal list."""

    def test_empty_signals_returns_skip(self, decider: CaptureDecider) -> None:
        """Empty signal list results in SKIP action."""
        decision = decider.decide([])
        assert decision.action == CaptureAction.SKIP
        assert decision.signals == ()
        assert decision.suggested_captures == ()
        assert "No signals detected" in decision.reason


class TestDecideSingleSignal:
    """Tests for decide() with single signal at various confidence levels."""

    def test_high_confidence_auto_capture(self, decider: CaptureDecider) -> None:
        """Signal above auto_threshold results in AUTO action."""
        signal = make_signal(confidence=0.98)  # >= 0.95
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.AUTO
        assert len(decision.signals) == 1
        assert len(decision.suggested_captures) == 1
        assert "High confidence" in decision.reason
        assert "0.98" in decision.reason

    def test_exactly_at_auto_threshold(self, decider: CaptureDecider) -> None:
        """Signal exactly at auto_threshold results in AUTO."""
        signal = make_signal(confidence=0.95)
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.AUTO

    def test_medium_confidence_suggest(self, decider: CaptureDecider) -> None:
        """Signal between thresholds results in SUGGEST action."""
        signal = make_signal(confidence=0.85)  # 0.7 <= x < 0.95
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.SUGGEST
        assert len(decision.suggested_captures) == 1
        assert "Medium confidence" in decision.reason

    def test_exactly_at_suggest_threshold(self, decider: CaptureDecider) -> None:
        """Signal exactly at suggest_threshold results in SUGGEST."""
        signal = make_signal(confidence=0.7)
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.SUGGEST

    def test_low_confidence_skip(self, decider: CaptureDecider) -> None:
        """Signal below suggest_threshold results in SKIP action."""
        signal = make_signal(confidence=0.5)  # < 0.7
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.SKIP
        assert decision.suggested_captures == ()
        assert "Low confidence" in decision.reason

    def test_very_low_confidence_skip(self, decider: CaptureDecider) -> None:
        """Signal with very low confidence results in SKIP."""
        signal = make_signal(confidence=0.1)
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.SKIP


# =============================================================================
# decide() Method Tests - Multiple Signals
# =============================================================================


class TestDecideMultipleSignals:
    """Tests for decide() with multiple signals."""

    def test_highest_confidence_determines_action(
        self, decider: CaptureDecider
    ) -> None:
        """Action is determined by highest confidence signal."""
        signals = [
            make_signal(confidence=0.98, match="first"),  # AUTO
            make_signal(confidence=0.75, match="second"),  # SUGGEST
            make_signal(confidence=0.5, match="third"),  # SKIP
        ]
        decision = decider.decide(signals)

        assert decision.action == CaptureAction.AUTO
        assert len(decision.signals) == 3

    def test_only_high_confidence_signals_captured(
        self, decider: CaptureDecider
    ) -> None:
        """Only signals at or above suggest_threshold get suggested captures."""
        signals = [
            make_signal(confidence=0.98, match="high"),
            make_signal(confidence=0.75, match="medium"),
            make_signal(confidence=0.5, match="low"),  # Below threshold
        ]
        decision = decider.decide(signals)

        # Only 2 signals should have suggestions (those >= suggest_threshold)
        assert len(decision.suggested_captures) == 2

    def test_all_medium_results_in_suggest(self, decider: CaptureDecider) -> None:
        """All medium confidence signals result in SUGGEST."""
        signals = [
            make_signal(confidence=0.85, match="first"),
            make_signal(confidence=0.8, match="second"),
            make_signal(confidence=0.75, match="third"),
        ]
        decision = decider.decide(signals)

        assert decision.action == CaptureAction.SUGGEST
        assert len(decision.suggested_captures) == 3

    def test_all_low_results_in_skip(self, decider: CaptureDecider) -> None:
        """All low confidence signals result in SKIP."""
        signals = [
            make_signal(confidence=0.5, match="first"),
            make_signal(confidence=0.4, match="second"),
            make_signal(confidence=0.3, match="third"),
        ]
        decision = decider.decide(signals)

        assert decision.action == CaptureAction.SKIP
        assert decision.suggested_captures == ()


# =============================================================================
# Explicit Signal Tests
# =============================================================================


class TestExplicitSignals:
    """Tests for explicit signal handling."""

    def test_explicit_signal_always_suggest(self, decider: CaptureDecider) -> None:
        """Explicit signals result in SUGGEST even with low confidence."""
        signal = make_signal(
            signal_type=SignalType.EXPLICIT,
            confidence=0.3,  # Below suggest threshold
            match="remember this important thing",
        )
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.SUGGEST
        assert "Explicit capture request" in decision.reason
        assert len(decision.suggested_captures) == 1

    def test_explicit_with_high_confidence_is_auto(
        self, decider: CaptureDecider
    ) -> None:
        """Explicit signal with high confidence results in AUTO."""
        signal = make_signal(
            signal_type=SignalType.EXPLICIT,
            confidence=0.98,
        )
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.AUTO

    def test_mixed_explicit_and_low_confidence(self, decider: CaptureDecider) -> None:
        """Mixed explicit and low-confidence signals."""
        signals = [
            make_signal(confidence=0.3, match="low"),  # Would be SKIP
            make_signal(
                signal_type=SignalType.EXPLICIT,
                confidence=0.4,
                match="remember this",
            ),
        ]
        decision = decider.decide(signals)

        # Explicit signal should force at least SUGGEST
        assert decision.action == CaptureAction.SUGGEST


# =============================================================================
# Novelty Checking Tests
# =============================================================================


class TestNoveltyChecking:
    """Tests for novelty checking integration."""

    def test_novel_content_proceeds(
        self, mock_novelty_checker: MagicMock, decider: CaptureDecider
    ) -> None:
        """Novel content results in normal decision flow."""
        mock_novelty_checker.check_signal_novelty.return_value = NoveltyResult(
            novelty_score=0.9,
            is_novel=True,
            similar_memory_ids=[],
            highest_similarity=0.1,
        )
        signal = make_signal(confidence=0.98)
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.AUTO
        mock_novelty_checker.check_signal_novelty.assert_called_once_with(signal)

    def test_duplicate_content_skipped(
        self, mock_novelty_checker: MagicMock, decider: CaptureDecider
    ) -> None:
        """Duplicate content results in SKIP regardless of confidence."""
        mock_novelty_checker.check_signal_novelty.return_value = NoveltyResult(
            novelty_score=0.1,
            is_novel=False,
            similar_memory_ids=["mem:123", "mem:456"],
            highest_similarity=0.9,
        )
        signal = make_signal(confidence=0.98)
        decision = decider.decide([signal])

        assert decision.action == CaptureAction.SKIP
        assert "duplicates" in decision.reason.lower()

    def test_all_duplicates_result_in_skip(
        self, mock_novelty_checker: MagicMock, decider: CaptureDecider
    ) -> None:
        """All signals being duplicates results in SKIP."""
        mock_novelty_checker.check_signal_novelty.return_value = NoveltyResult(
            novelty_score=0.05,
            is_novel=False,
            similar_memory_ids=["mem:789"],
            highest_similarity=0.95,
        )
        signals = [
            make_signal(confidence=0.98, match="first"),
            make_signal(confidence=0.95, match="second"),
        ]
        decision = decider.decide(signals)

        assert decision.action == CaptureAction.SKIP
        assert "duplicates" in decision.reason.lower()

    def test_novelty_check_disabled_instance(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Novelty checking can be disabled at instance level."""
        signal = make_signal(confidence=0.98)
        decision = decider_no_novelty.decide([signal])

        # Should proceed without novelty check
        assert decision.action == CaptureAction.AUTO

    def test_novelty_check_disabled_per_call(
        self, mock_novelty_checker: MagicMock, decider: CaptureDecider
    ) -> None:
        """Novelty checking can be disabled per decide() call."""
        signal = make_signal(confidence=0.98)
        decision = decider.decide([signal], check_novelty=False)

        assert decision.action == CaptureAction.AUTO
        mock_novelty_checker.check_signal_novelty.assert_not_called()

    def test_novelty_check_enabled_per_call(
        self, mock_novelty_checker: MagicMock
    ) -> None:
        """Novelty checking can be enabled per decide() call."""
        decider = CaptureDecider(
            novelty_checker=mock_novelty_checker,
            check_novelty_enabled=False,  # Disabled at instance level
        )
        signal = make_signal(confidence=0.98)
        decider.decide([signal], check_novelty=True)

        # Should check novelty because per-call override
        mock_novelty_checker.check_signal_novelty.assert_called_once()

    def test_partial_novelty_mixed_signals(
        self, mock_novelty_checker: MagicMock, decider: CaptureDecider
    ) -> None:
        """Mixed novel and duplicate signals - only novel ones proceed."""
        # First signal is novel, second is duplicate
        mock_novelty_checker.check_signal_novelty.side_effect = [
            NoveltyResult(novelty_score=0.8, is_novel=True),
            NoveltyResult(novelty_score=0.1, is_novel=False, similar_memory_ids=["x"]),
        ]
        signals = [
            make_signal(confidence=0.98, match="novel content"),
            make_signal(confidence=0.98, match="duplicate content"),
        ]
        decision = decider.decide(signals)

        # Should proceed with the novel signal
        assert decision.action == CaptureAction.AUTO
        assert len(decision.suggested_captures) == 1

    def test_novelty_affects_confidence(
        self, mock_novelty_checker: MagicMock, decider: CaptureDecider
    ) -> None:
        """Novelty score affects suggested capture confidence."""
        mock_novelty_checker.check_signal_novelty.return_value = NoveltyResult(
            novelty_score=0.5,  # Partial novelty
            is_novel=True,
            similar_memory_ids=[],
            highest_similarity=0.5,
        )
        signal = make_signal(confidence=0.98)
        decision = decider.decide([signal])

        assert len(decision.suggested_captures) == 1
        # Confidence should be adjusted: 0.98 * (0.5 + 0.5 * 0.5) = 0.98 * 0.75 = 0.735
        assert decision.suggested_captures[0].confidence == pytest.approx(
            0.735, rel=0.01
        )


# =============================================================================
# decide_single() Tests
# =============================================================================


class TestDecideSingle:
    """Tests for the decide_single() convenience method."""

    def test_decide_single_high_confidence(self, decider: CaptureDecider) -> None:
        """decide_single with high confidence returns AUTO."""
        signal = make_signal(confidence=0.98)
        decision = decider.decide_single(signal)

        assert decision.action == CaptureAction.AUTO
        assert len(decision.signals) == 1

    def test_decide_single_low_confidence(self, decider: CaptureDecider) -> None:
        """decide_single with low confidence returns SKIP."""
        signal = make_signal(confidence=0.3)
        decision = decider.decide_single(signal)

        assert decision.action == CaptureAction.SKIP

    def test_decide_single_with_novelty_override(
        self, mock_novelty_checker: MagicMock, decider: CaptureDecider
    ) -> None:
        """decide_single respects check_novelty parameter."""
        signal = make_signal(confidence=0.98)
        decision = decider.decide_single(signal, check_novelty=False)

        assert decision.action == CaptureAction.AUTO
        mock_novelty_checker.check_signal_novelty.assert_not_called()


# =============================================================================
# should_capture() Tests
# =============================================================================


class TestShouldCapture:
    """Tests for the should_capture() boolean check method."""

    def test_should_capture_for_auto(self, decider: CaptureDecider) -> None:
        """should_capture returns True for AUTO action."""
        signals = [make_signal(confidence=0.98)]
        assert decider.should_capture(signals) is True

    def test_should_capture_for_suggest(self, decider: CaptureDecider) -> None:
        """should_capture returns True for SUGGEST action."""
        signals = [make_signal(confidence=0.85)]
        assert decider.should_capture(signals) is True

    def test_should_not_capture_for_skip(self, decider: CaptureDecider) -> None:
        """should_capture returns False for SKIP action."""
        signals = [make_signal(confidence=0.3)]
        assert decider.should_capture(signals) is False

    def test_should_not_capture_empty(self, decider: CaptureDecider) -> None:
        """should_capture returns False for empty signals."""
        assert decider.should_capture([]) is False


# =============================================================================
# _extract_summary() Tests
# =============================================================================


class TestExtractSummary:
    """Tests for summary extraction logic."""

    def test_summary_from_context(self, decider_no_novelty: CaptureDecider) -> None:
        """Summary uses context when available."""
        signal = make_signal(
            match="decided",
            context="I decided to use PostgreSQL for better performance",
        )
        summary = decider_no_novelty._extract_summary(signal)
        assert "PostgreSQL" in summary
        assert "performance" in summary

    def test_summary_from_match_when_no_context(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Summary uses match when context is empty."""
        signal = CaptureSignal(
            type=SignalType.DECISION,
            match="chose Redis",
            confidence=0.9,
            context="",
            suggested_namespace="decisions",
        )
        summary = decider_no_novelty._extract_summary(signal)
        assert "Redis" in summary

    def test_summary_strips_whitespace(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Summary strips leading/trailing whitespace."""
        signal = make_signal(context="   important decision   ")
        summary = decider_no_novelty._extract_summary(signal)
        assert not summary.startswith(" ")
        assert not summary.endswith(" ")

    def test_summary_removes_ellipsis(self, decider_no_novelty: CaptureDecider) -> None:
        """Summary removes leading/trailing ellipsis from context."""
        signal = make_signal(context="...middle of the content...")
        summary = decider_no_novelty._extract_summary(signal)
        assert not summary.startswith("...")
        assert not summary.endswith("...")

    def test_summary_truncates_long_content(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Summary truncates content over 200 characters."""
        max_length = 200  # From capture_decider.py
        long_context = "A" * 300
        signal = make_signal(context=long_context)
        summary = decider_no_novelty._extract_summary(signal)

        # No word boundary (all A's), so truncates at max_length - 3 + "..."
        assert len(summary) == max_length  # 197 chars + "..."
        assert summary.endswith("...")

    def test_summary_truncates_at_word_boundary(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Summary truncates at word boundary when possible."""
        # Create context with words
        words = ["word" + str(i) for i in range(50)]
        long_context = " ".join(words)  # ~300 chars
        signal = make_signal(context=long_context)
        summary = decider_no_novelty._extract_summary(signal)

        # Should end with "..." after a complete word
        assert summary.endswith("...")
        # The part before "..." should not end mid-word
        before_ellipsis = summary[:-3]
        assert not before_ellipsis.endswith("d")  # Not mid-word

    def test_summary_handles_no_word_boundary(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Summary handles content with no good word boundary."""
        max_length = 200  # From capture_decider.py
        # No spaces = no word boundary
        long_context = "x" * 300
        signal = make_signal(context=long_context)
        summary = decider_no_novelty._extract_summary(signal)

        # Hard truncate at max_length - 3, add "..." = max_length total
        assert len(summary) == max_length
        assert summary.endswith("...")


# =============================================================================
# _extract_tags() Tests
# =============================================================================


class TestExtractTags:
    """Tests for tag extraction logic."""

    def test_signal_type_always_included(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Signal type is always included as a tag."""
        signal = make_signal(signal_type=SignalType.DECISION, context="some content")
        tags = decider_no_novelty._extract_tags(signal)

        assert "decision" in tags

    def test_python_tag_detected(self, decider_no_novelty: CaptureDecider) -> None:
        """Python-related keywords add python tag."""
        signal = make_signal(context="I decided to use pytest for testing")
        tags = decider_no_novelty._extract_tags(signal)

        assert "python" in tags
        assert "testing" in tags

    def test_javascript_tag_detected(self, decider_no_novelty: CaptureDecider) -> None:
        """JavaScript-related keywords add javascript tag."""
        signal = make_signal(context="Using React with npm for the frontend")
        tags = decider_no_novelty._extract_tags(signal)

        assert "javascript" in tags

    def test_database_tag_detected(self, decider_no_novelty: CaptureDecider) -> None:
        """Database-related keywords add database tag."""
        signal = make_signal(context="I chose PostgreSQL for the SQL database")
        tags = decider_no_novelty._extract_tags(signal)

        assert "database" in tags

    def test_docker_tag_detected(self, decider_no_novelty: CaptureDecider) -> None:
        """Docker-related keywords add docker tag."""
        signal = make_signal(context="Deploying with Docker containers on Kubernetes")
        tags = decider_no_novelty._extract_tags(signal)

        assert "docker" in tags

    def test_security_tag_detected(self, decider_no_novelty: CaptureDecider) -> None:
        """Security-related keywords add security tag."""
        signal = make_signal(context="Added authentication with encryption")
        tags = decider_no_novelty._extract_tags(signal)

        assert "security" in tags

    def test_multiple_tags_detected(self, decider_no_novelty: CaptureDecider) -> None:
        """Multiple relevant tags are detected."""
        signal = make_signal(
            context="Python API using Flask with PostgreSQL database and Docker"
        )
        tags = decider_no_novelty._extract_tags(signal)

        assert "python" in tags
        assert "api" in tags
        assert "database" in tags
        assert "docker" in tags

    def test_max_five_tags(self, decider_no_novelty: CaptureDecider) -> None:
        """Tags are limited to 5 maximum."""
        # Content with many technology keywords
        signal = make_signal(
            context="Python JavaScript TypeScript API database Docker Git testing "
            "performance security"
        )
        tags = decider_no_novelty._extract_tags(signal)

        assert len(tags) <= 5

    def test_case_insensitive_matching(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Tag matching is case insensitive."""
        signal = make_signal(context="Using PYTHON with PYTEST and DOCKER")
        tags = decider_no_novelty._extract_tags(signal)

        assert "python" in tags
        assert "docker" in tags
        assert "testing" in tags

    def test_no_additional_tags_for_plain_content(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Plain content without keywords gets only signal type tag."""
        signal = make_signal(context="I made an important choice today")
        tags = decider_no_novelty._extract_tags(signal)

        assert tags == ("decision",)


# =============================================================================
# Edge Cases and Unicode
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and special content."""

    def test_empty_match(self, decider_no_novelty: CaptureDecider) -> None:
        """Handle signal with empty match."""
        signal = CaptureSignal(
            type=SignalType.DECISION,
            match="",
            confidence=0.9,
            context="Some context",
            suggested_namespace="decisions",
        )
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SUGGEST
        assert len(decision.suggested_captures) == 1

    def test_empty_context(self, decider_no_novelty: CaptureDecider) -> None:
        """Handle signal with empty context."""
        signal = CaptureSignal(
            type=SignalType.DECISION,
            match="decided something",
            confidence=0.9,
            context="",
            suggested_namespace="decisions",
        )
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SUGGEST
        # Summary should fall back to match
        assert "decided" in decision.suggested_captures[0].summary

    def test_unicode_content(self, decider_no_novelty: CaptureDecider) -> None:
        """Handle unicode characters in content."""
        signal = make_signal(
            context="Decided to use emoji: \U0001f680 \u4e2d\u6587 caf\xe9"
        )
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SUGGEST
        summary = decision.suggested_captures[0].summary
        assert "\U0001f680" in summary or "emoji" in summary

    def test_very_long_content(self, decider_no_novelty: CaptureDecider) -> None:
        """Handle very long content (multiple KB)."""
        long_content = "word " * 10000  # ~50KB
        signal = make_signal(context=long_content)
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SUGGEST
        # Summary should be truncated
        assert len(decision.suggested_captures[0].summary) <= 203

    def test_special_characters(self, decider_no_novelty: CaptureDecider) -> None:
        """Handle special characters in content."""
        signal = make_signal(
            context="Using regex: ^[a-z]+$ and SQL: SELECT * FROM users WHERE id = 1"
        )
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SUGGEST
        # Tags should include database from SQL keyword
        assert "database" in decision.suggested_captures[0].tags

    def test_newlines_in_content(self, decider_no_novelty: CaptureDecider) -> None:
        """Handle newlines in content."""
        signal = make_signal(context="Line 1\nLine 2\nLine 3")
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SUGGEST

    def test_whitespace_only_context(self, decider_no_novelty: CaptureDecider) -> None:
        """Handle whitespace-only context."""
        signal = CaptureSignal(
            type=SignalType.DECISION,
            match="decided",
            confidence=0.9,
            context="   \n\t  ",
            suggested_namespace="decisions",
        )
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SUGGEST
        # Should fall back to match
        summary = decision.suggested_captures[0].summary
        assert "decided" in summary or summary.strip() == ""


# =============================================================================
# Suggested Capture Content Tests
# =============================================================================


class TestSuggestedCaptureContent:
    """Tests for the content of generated SuggestedCapture objects."""

    def test_namespace_from_signal(self, decider_no_novelty: CaptureDecider) -> None:
        """Suggested capture uses namespace from signal."""
        signal = make_signal(
            signal_type=SignalType.LEARNING,
            suggested_namespace="learnings",
        )
        decision = decider_no_novelty.decide([signal])

        assert decision.suggested_captures[0].namespace == "learnings"

    def test_content_uses_context(self, decider_no_novelty: CaptureDecider) -> None:
        """Suggested capture content uses context when available."""
        signal = make_signal(
            match="learned",
            context="I learned that SQLite is great for testing",
        )
        decision = decider_no_novelty.decide([signal])

        assert "SQLite" in decision.suggested_captures[0].content

    def test_content_falls_back_to_match(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Suggested capture content uses match when context is empty."""
        signal = CaptureSignal(
            type=SignalType.DECISION,
            match="chose Redis",
            confidence=0.9,
            context="",
            suggested_namespace="decisions",
        )
        decision = decider_no_novelty.decide([signal])

        assert "Redis" in decision.suggested_captures[0].content

    def test_tags_are_tuple(self, decider_no_novelty: CaptureDecider) -> None:
        """Suggested capture tags are a tuple (immutable)."""
        signal = make_signal(context="Python testing with pytest")
        decision = decider_no_novelty.decide([signal])

        assert isinstance(decision.suggested_captures[0].tags, tuple)

    def test_confidence_is_rounded(self, decider_no_novelty: CaptureDecider) -> None:
        """Suggested capture confidence is rounded to 3 decimals."""
        signal = make_signal(confidence=0.87654321)
        decision = decider_no_novelty.decide([signal])

        confidence = decision.suggested_captures[0].confidence
        # Should be 0.877 (rounded to 3 decimals)
        assert confidence == 0.877


# =============================================================================
# Signal Type Namespace Mapping Tests
# =============================================================================


class TestSignalTypeNamespaces:
    """Tests for signal type to namespace mapping."""

    @pytest.mark.parametrize(
        "signal_type,expected_namespace",
        [
            (SignalType.DECISION, "decisions"),
            (SignalType.LEARNING, "learnings"),
            (SignalType.BLOCKER, "blockers"),
            (SignalType.RESOLUTION, "solutions"),
            (SignalType.PREFERENCE, "preferences"),
            (SignalType.EXPLICIT, "notes"),
        ],
    )
    def test_signal_type_namespaces(
        self,
        decider_no_novelty: CaptureDecider,
        signal_type: SignalType,
        expected_namespace: str,
    ) -> None:
        """Each signal type maps to the correct namespace."""
        signal = make_signal(signal_type=signal_type, confidence=0.9)
        decision = decider_no_novelty.decide([signal])

        assert decision.suggested_captures[0].namespace == expected_namespace


# =============================================================================
# Boundary Condition Tests
# =============================================================================


class TestBoundaryConditions:
    """Tests for boundary conditions at threshold values."""

    def test_confidence_just_below_auto(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Confidence just below auto_threshold results in SUGGEST."""
        signal = make_signal(confidence=0.9499)
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SUGGEST

    def test_confidence_just_below_suggest(
        self, decider_no_novelty: CaptureDecider
    ) -> None:
        """Confidence just below suggest_threshold results in SKIP."""
        signal = make_signal(confidence=0.6999)
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SKIP

    def test_zero_confidence(self, decider_no_novelty: CaptureDecider) -> None:
        """Zero confidence results in SKIP."""
        signal = make_signal(confidence=0.0)
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.SKIP

    def test_max_confidence(self, decider_no_novelty: CaptureDecider) -> None:
        """Maximum confidence (1.0) results in AUTO."""
        signal = make_signal(confidence=1.0)
        decision = decider_no_novelty.decide([signal])

        assert decision.action == CaptureAction.AUTO

    def test_custom_thresholds_boundary(self) -> None:
        """Custom thresholds work correctly at boundaries."""
        decider = CaptureDecider(
            auto_threshold=0.8,
            suggest_threshold=0.5,
            check_novelty_enabled=False,
        )

        # At auto threshold
        signal = make_signal(confidence=0.8)
        decision = decider.decide([signal])
        assert decision.action == CaptureAction.AUTO

        # Just below auto, at suggest
        signal = make_signal(confidence=0.79)
        decision = decider.decide([signal])
        assert decision.action == CaptureAction.SUGGEST

        # Just below suggest
        signal = make_signal(confidence=0.49)
        decision = decider.decide([signal])
        assert decision.action == CaptureAction.SKIP
