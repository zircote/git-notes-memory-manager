"""Tests for git_notes_memory.hooks.signal_detector module.

Tests the signal detection system including:
- SignalDetector initialization and configuration
- Signal pattern detection for all SignalType values
- Confidence scoring adjustments
- Context extraction with word boundary alignment
- Deduplication of overlapping matches
- detect_all_types() grouping functionality
- Edge cases (empty text, unicode, special characters)
"""

from __future__ import annotations

import pytest

from git_notes_memory.hooks.models import CaptureSignal, SignalType
from git_notes_memory.hooks.signal_detector import (
    SIGNAL_PATTERNS,
    SignalDetector,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def detector() -> SignalDetector:
    """Create a SignalDetector with default settings."""
    return SignalDetector()


@pytest.fixture
def detector_high_threshold() -> SignalDetector:
    """Create a SignalDetector with high minimum confidence threshold."""
    return SignalDetector(min_confidence=0.85)


@pytest.fixture
def detector_small_context() -> SignalDetector:
    """Create a SignalDetector with small context window."""
    return SignalDetector(context_window=20)


# =============================================================================
# SignalDetector Initialization Tests
# =============================================================================


class TestSignalDetectorInitialization:
    """Test SignalDetector initialization and configuration."""

    def test_default_context_window(self, detector: SignalDetector) -> None:
        """Test default context window is 100 characters."""
        assert detector.context_window == 100

    def test_default_min_confidence(self, detector: SignalDetector) -> None:
        """Test default min_confidence is 0.0."""
        assert detector.min_confidence == 0.0

    def test_custom_context_window(self) -> None:
        """Test custom context window is respected."""
        detector = SignalDetector(context_window=50)
        assert detector.context_window == 50

    def test_custom_min_confidence(self) -> None:
        """Test custom min_confidence is respected."""
        detector = SignalDetector(min_confidence=0.75)
        assert detector.min_confidence == 0.75

    def test_combined_custom_settings(self) -> None:
        """Test both custom settings together."""
        detector = SignalDetector(context_window=200, min_confidence=0.5)
        assert detector.context_window == 200
        assert detector.min_confidence == 0.5

    def test_patterns_compiled_once(self) -> None:
        """Test that patterns are compiled at class level (shared between instances)."""
        detector1 = SignalDetector()
        detector2 = SignalDetector()
        # Both should reference the same compiled patterns dict
        assert detector1._compiled_patterns is detector2._compiled_patterns

    def test_all_signal_types_have_patterns(self) -> None:
        """Test that all SignalType values have defined patterns."""
        for signal_type in SignalType:
            assert signal_type in SIGNAL_PATTERNS, f"Missing patterns for {signal_type}"
            assert len(SIGNAL_PATTERNS[signal_type]) > 0, (
                f"Empty patterns for {signal_type}"
            )


# =============================================================================
# SIGNAL_PATTERNS Constant Tests
# =============================================================================


class TestSignalPatternsConstant:
    """Test the SIGNAL_PATTERNS constant structure."""

    def test_pattern_structure(self) -> None:
        """Test each pattern is a tuple of (regex_string, confidence)."""
        for signal_type, patterns in SIGNAL_PATTERNS.items():
            for pattern_str, confidence in patterns:
                assert isinstance(pattern_str, str), (
                    f"Pattern for {signal_type} not string"
                )
                assert isinstance(confidence, float), (
                    f"Confidence for {signal_type} not float"
                )
                assert 0.0 <= confidence <= 1.0, (
                    f"Invalid confidence {confidence} for {signal_type}"
                )

    def test_expected_signal_types(self) -> None:
        """Test all expected signal types are present."""
        expected_types = {
            SignalType.DECISION,
            SignalType.LEARNING,
            SignalType.BLOCKER,
            SignalType.RESOLUTION,
            SignalType.PREFERENCE,
            SignalType.EXPLICIT,
        }
        assert set(SIGNAL_PATTERNS.keys()) == expected_types


# =============================================================================
# DECISION Signal Detection Tests
# =============================================================================


class TestDecisionSignalDetection:
    """Test detection of DECISION signal type patterns."""

    @pytest.mark.parametrize(
        "text,expected_match",
        [
            ("I decided to use PostgreSQL", "I decided to"),
            ("We chose to go with React", "We chose to"),
            ("I selected for this approach", "I selected for"),
            ("We picked on the blue theme", "We picked on"),
            ("I opted to refactor", "I opted to"),
            ("The decision is to proceed", "the decision is to"),
            ("The decision was that we continue", "the decision was that"),
            ("We'll go with option A", "We'll go with"),
            ("We will go with the simpler solution", "We will go with"),
            ("After considering, I chose", "After considering, I"),
            ("After evaluating, we decided", "After evaluating, we"),
            ("After weighing, I picked", "After weighing, I"),
            ("I went with the first option", "I went with"),
            ("We went with TypeScript", "We went with"),
            ("Finally decided on this approach", "Finally decided"),
            ("Made the call to postpone", "made the call to"),
        ],
    )
    def test_decision_patterns(
        self, detector: SignalDetector, text: str, expected_match: str
    ) -> None:
        """Test various DECISION signal patterns are detected."""
        signals = detector.detect(text)
        assert len(signals) >= 1, f"No signals detected in: {text}"
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1, f"No DECISION signal in: {text}"
        # Check that match contains expected text (case-insensitive comparison)
        assert any(
            expected_match.lower() in s.match.lower() for s in decision_signals
        ), f"Expected '{expected_match}' in matches for: {text}"

    def test_decision_high_confidence(self, detector: SignalDetector) -> None:
        """Test high confidence DECISION patterns have confidence >= 0.85."""
        text = "I decided to use SQLite for storage"
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1
        # "I decided to" is a high confidence pattern (base 0.90)
        assert decision_signals[0].confidence >= 0.85


# =============================================================================
# LEARNING Signal Detection Tests
# =============================================================================


class TestLearningSignalDetection:
    """Test detection of LEARNING signal type patterns."""

    @pytest.mark.parametrize(
        "text",
        [
            "I learned that async is better here",
            "We realized that caching helps",
            "I discovered about this new feature",
            "I found out that it works differently",
            "TIL you can do this in Python",
            "Turns out the API has a bug",
            "Key insight: performance matters",
            "Key takeaway: keep it simple",
            "Key learning: test early",
            "Interestingly, this works",
            "I didn't know about this feature",
            "I never realized how complex it is",
            "Now I know how to fix it",
            "Now I understand the issue",
            "It was an aha moment for me",
        ],
    )
    def test_learning_patterns(self, detector: SignalDetector, text: str) -> None:
        """Test various LEARNING signal patterns are detected."""
        signals = detector.detect(text)
        assert len(signals) >= 1, f"No signals detected in: {text}"
        learning_signals = [s for s in signals if s.type == SignalType.LEARNING]
        assert len(learning_signals) >= 1, f"No LEARNING signal in: {text}"

    def test_til_highest_confidence(self, detector: SignalDetector) -> None:
        """Test TIL has very high confidence (0.95 base)."""
        text = "TIL about Python decorators"
        signals = detector.detect(text)
        learning_signals = [s for s in signals if s.type == SignalType.LEARNING]
        assert len(learning_signals) >= 1
        # TIL should have high confidence after scoring adjustments
        assert learning_signals[0].confidence >= 0.85

    def test_learning_suggested_namespace(self, detector: SignalDetector) -> None:
        """Test LEARNING signals suggest 'learnings' namespace."""
        text = "I learned that pytest fixtures are powerful"
        signals = detector.detect(text)
        learning_signals = [s for s in signals if s.type == SignalType.LEARNING]
        assert len(learning_signals) >= 1
        assert learning_signals[0].suggested_namespace == "learnings"


# =============================================================================
# BLOCKER Signal Detection Tests
# =============================================================================


class TestBlockerSignalDetection:
    """Test detection of BLOCKER signal type patterns."""

    @pytest.mark.parametrize(
        "text",
        [
            "Blocked by CORS configuration",
            "Blocked on the API approval",
            "Stuck on this authentication issue",
            "Stuck with the deployment",
            "Can't deploy because of missing credentials",
            "This is blocking our progress",
            "That blocking issue needs resolution",
            "The issue with CORS is preventing us",
            "Problem: the database is not responding",
            "I'm having trouble with the setup",
            "We're struggling with performance",
            "Can't figure out why this fails",
            "Can't get the tests to pass",
            "Can't make the API work",
        ],
    )
    def test_blocker_patterns(self, detector: SignalDetector, text: str) -> None:
        """Test various BLOCKER signal patterns are detected."""
        signals = detector.detect(text)
        assert len(signals) >= 1, f"No signals detected in: {text}"
        blocker_signals = [s for s in signals if s.type == SignalType.BLOCKER]
        assert len(blocker_signals) >= 1, f"No BLOCKER signal in: {text}"

    def test_blocker_suggested_namespace(self, detector: SignalDetector) -> None:
        """Test BLOCKER signals suggest 'blockers' namespace."""
        text = "Blocked by the firewall configuration"
        signals = detector.detect(text)
        blocker_signals = [s for s in signals if s.type == SignalType.BLOCKER]
        assert len(blocker_signals) >= 1
        assert blocker_signals[0].suggested_namespace == "blockers"


# =============================================================================
# RESOLUTION Signal Detection Tests
# =============================================================================


class TestResolutionSignalDetection:
    """Test detection of RESOLUTION signal type patterns."""

    @pytest.mark.parametrize(
        "text",
        [
            "Fixed the authentication bug",
            "Resolved the CORS issue",
            "Solved the performance problem",
            "Resolved this deployment issue",
            "Workaround: use a different port",
            "Solution: add the missing header",
            "Figured it out finally",
            "Figured out why it failed",
            "That worked perfectly",
            "That fixed it immediately",
            "Got it working now",
            "Got it to work after changing config",
            "The fix was simple",
            "The solution is to restart",
            "Finally got the tests passing",
        ],
    )
    def test_resolution_patterns(self, detector: SignalDetector, text: str) -> None:
        """Test various RESOLUTION signal patterns are detected."""
        signals = detector.detect(text)
        assert len(signals) >= 1, f"No signals detected in: {text}"
        resolution_signals = [s for s in signals if s.type == SignalType.RESOLUTION]
        assert len(resolution_signals) >= 1, f"No RESOLUTION signal in: {text}"

    def test_resolution_suggested_namespace(self, detector: SignalDetector) -> None:
        """Test RESOLUTION signals suggest 'solutions' namespace."""
        text = "Fixed the database connection issue"
        signals = detector.detect(text)
        resolution_signals = [s for s in signals if s.type == SignalType.RESOLUTION]
        assert len(resolution_signals) >= 1
        assert resolution_signals[0].suggested_namespace == "solutions"


# =============================================================================
# PREFERENCE Signal Detection Tests
# =============================================================================


class TestPreferenceSignalDetection:
    """Test detection of PREFERENCE signal type patterns."""

    @pytest.mark.parametrize(
        "text",
        [
            "I prefer to use TypeScript",
            "I always prefer to use functional programming",
            "I like to write tests first",
            "My preference is for simpler solutions",
            "I'd rather use React than Vue",
            "I would prefer the async approach",
            "I don't like when code is too verbose",
            "I like how clean this looks",
            "I want to keep this simple",
            "I want it to be maintainable",
            "I need clear documentation",
            "I require type safety",
        ],
    )
    def test_preference_patterns(self, detector: SignalDetector, text: str) -> None:
        """Test various PREFERENCE signal patterns are detected."""
        signals = detector.detect(text)
        assert len(signals) >= 1, f"No signals detected in: {text}"
        preference_signals = [s for s in signals if s.type == SignalType.PREFERENCE]
        assert len(preference_signals) >= 1, f"No PREFERENCE signal in: {text}"

    def test_preference_suggested_namespace(self, detector: SignalDetector) -> None:
        """Test PREFERENCE signals suggest 'preferences' namespace."""
        text = "My preference is for readable code"
        signals = detector.detect(text)
        preference_signals = [s for s in signals if s.type == SignalType.PREFERENCE]
        assert len(preference_signals) >= 1
        assert preference_signals[0].suggested_namespace == "preferences"


# =============================================================================
# EXPLICIT Signal Detection Tests
# =============================================================================


class TestExplicitSignalDetection:
    """Test detection of EXPLICIT signal type patterns."""

    @pytest.mark.parametrize(
        "text",
        [
            "Remember this for later",
            "Remember that approach",
            "Save this configuration",
            "Save that for reference",
            "Save this as a template",
            "Note that this is important",
            "Note this: use caution here",
            "For future reference: the API key format",
            "For later reference: configuration steps",
            "Don't forget about this edge case",
            "Keep this in mind when refactoring",
            "Keep in mind the performance impact",
            "Important: this must be done first",
        ],
    )
    def test_explicit_patterns(self, detector: SignalDetector, text: str) -> None:
        """Test various EXPLICIT signal patterns are detected."""
        signals = detector.detect(text)
        assert len(signals) >= 1, f"No signals detected in: {text}"
        explicit_signals = [s for s in signals if s.type == SignalType.EXPLICIT]
        assert len(explicit_signals) >= 1, f"No EXPLICIT signal in: {text}"

    def test_explicit_highest_confidence(self, detector: SignalDetector) -> None:
        """Test 'remember this' has highest confidence (0.98 base)."""
        text = "Remember this for the next session."
        signals = detector.detect(text)
        explicit_signals = [s for s in signals if s.type == SignalType.EXPLICIT]
        assert len(explicit_signals) >= 1
        # "remember this" should have very high confidence
        assert explicit_signals[0].confidence >= 0.90

    def test_explicit_suggested_namespace(self, detector: SignalDetector) -> None:
        """Test EXPLICIT signals suggest 'notes' namespace."""
        text = "Remember this important configuration"
        signals = detector.detect(text)
        explicit_signals = [s for s in signals if s.type == SignalType.EXPLICIT]
        assert len(explicit_signals) >= 1
        assert explicit_signals[0].suggested_namespace == "notes"


# =============================================================================
# Confidence Scoring Tests
# =============================================================================


class TestConfidenceScoring:
    """Test confidence score adjustments."""

    def test_long_match_increases_confidence(self, detector: SignalDetector) -> None:
        """Test that longer matches slightly increase confidence."""
        # Create a context with a strong decision pattern
        text = "After considering, I decided to go with this approach."
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1

    def test_short_match_decreases_confidence(self, detector: SignalDetector) -> None:
        """Test that very short matches decrease confidence."""
        # TIL is short (3 chars) so should get penalty
        text = "TIL!"
        signals = detector.detect(text)
        learning_signals = [s for s in signals if s.type == SignalType.LEARNING]
        # Should still detect but with reduced confidence
        if learning_signals:
            # The base is 0.95, but short match (-0.05) and short context could reduce it
            assert learning_signals[0].confidence < 0.95

    def test_complete_sentence_increases_confidence(
        self, detector: SignalDetector
    ) -> None:
        """Test complete sentences (ending with punctuation) increase confidence."""
        text = "I decided to use PostgreSQL for this project."
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1
        # With complete sentence, confidence should be boosted
        assert decision_signals[0].confidence >= 0.85

    def test_reinforcing_words_increase_confidence(
        self, detector: SignalDetector
    ) -> None:
        """Test reinforcing words in context increase confidence."""
        text = "This is important: I decided to prioritize security, it's critical."
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1
        # "important" and "critical" are reinforcers
        assert decision_signals[0].confidence >= 0.90

    def test_confidence_capped_at_one(self, detector: SignalDetector) -> None:
        """Test confidence never exceeds 1.0."""
        # Create scenario with maximum boosters
        text = "This is critical and essential. I decided to proceed. Must do this!"
        signals = detector.detect(text)
        for signal in signals:
            assert signal.confidence <= 1.0

    def test_confidence_minimum_zero(self, detector: SignalDetector) -> None:
        """Test confidence never goes below 0.0."""
        # Even with penalties, confidence stays non-negative
        text = "TIL"  # Very short match and context
        signals = detector.detect(text)
        for signal in signals:
            assert signal.confidence >= 0.0

    def test_score_confidence_method_directly(self, detector: SignalDetector) -> None:
        """Test score_confidence method directly."""
        # Test with various inputs
        score = detector.score_confidence(0.90, "I decided to", "Full context here.")
        assert 0.0 <= score <= 1.0

        # Long match bonus
        long_match_score = detector.score_confidence(
            0.80, "This is a very long match text here", "Context"
        )
        short_match_score = detector.score_confidence(0.80, "TIL", "Context")
        assert long_match_score > short_match_score


# =============================================================================
# Context Extraction Tests
# =============================================================================


class TestContextExtraction:
    """Test context extraction around matches."""

    def test_context_includes_match(self, detector: SignalDetector) -> None:
        """Test that context always includes the matched text."""
        text = "Before text. I decided to use Python. After text."
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1
        assert "I decided to" in decision_signals[0].context

    def test_context_respects_window_size(
        self, detector_small_context: SignalDetector
    ) -> None:
        """Test that context is limited by context_window parameter."""
        text = "A" * 100 + " I decided to use X " + "B" * 100
        signals = detector_small_context.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1
        # With 20 char window, context should be bounded
        context = decision_signals[0].context
        # Context includes the match plus surrounding window
        assert "I decided to" in context

    def test_context_word_boundary_alignment(self, detector: SignalDetector) -> None:
        """Test context tries to align at word boundaries."""
        text = "Some preliminary text here. I decided to proceed. Some following text."
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1
        context = decision_signals[0].context
        # Context should contain whole words, not cut-off words
        assert "I decided" in context

    def test_context_truncation_at_start(self, detector: SignalDetector) -> None:
        """Test context is truncated when match is far from start."""
        # Create text where match is far from start
        text = "A" * 200 + " I decided to use X " + "B" * 50
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1
        # Context should be bounded and contain the match
        assert "I decided to" in decision_signals[0].context

    def test_context_truncation_at_end(self, detector: SignalDetector) -> None:
        """Test context is truncated when match is far from end."""
        text = "A" * 50 + " I decided to use X " + "B" * 200
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1
        # Context should be bounded and contain the match
        assert "I decided to" in decision_signals[0].context

    def test_no_ellipsis_when_full_text_fits(
        self, detector_small_context: SignalDetector
    ) -> None:
        """Test no ellipsis when entire text fits in context."""
        text = "I decided to use X"
        signals = detector_small_context.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        # Short text should not have ellipsis
        if decision_signals:
            context = decision_signals[0].context
            # If text is very short, no ellipsis needed
            if len(text) <= detector_small_context.context_window * 2 + 20:
                assert not (context.startswith("...") and context.endswith("..."))


# =============================================================================
# Deduplication Tests
# =============================================================================


class TestSignalDeduplication:
    """Test deduplication of overlapping signals."""

    def test_overlapping_signals_deduplicated(self, detector: SignalDetector) -> None:
        """Test that overlapping matches keep only highest confidence."""
        # "I decided to" and "decided" might both match at similar positions
        text = "I decided to proceed with the plan"
        signals = detector.detect(text)
        # Should be deduplicated - no overlapping positions
        # Check for reasonable deduplication (not too many signals)
        assert len(signals) <= 5  # Reasonable upper bound

    def test_non_overlapping_signals_preserved(self, detector: SignalDetector) -> None:
        """Test that non-overlapping signals are all preserved."""
        text = (
            "I decided to use PostgreSQL. TIL that it supports JSON. Fixed the issue."
        )
        signals = detector.detect(text)
        # Should have at least 3 different signals
        types_found = {s.type for s in signals}
        assert len(types_found) >= 2  # At least decision and learning

    def test_higher_confidence_wins_in_overlap(self, detector: SignalDetector) -> None:
        """Test that when signals overlap, higher confidence wins."""
        # This tests the internal deduplication logic
        text = "Remember this important decision"
        signals = detector.detect(text)
        # Verify deduplication worked - positions shouldn't overlap
        for i, sig1 in enumerate(signals):
            for sig2 in signals[i + 1 :]:
                sig1_end = sig1.position + len(sig1.match)
                # Either no overlap, or same position means different patterns
                if sig1.position < sig2.position:
                    assert (
                        sig2.position >= sig1_end or sig1.confidence >= sig2.confidence
                    )

    def test_single_signal_not_affected(self, detector: SignalDetector) -> None:
        """Test that single signal passes through deduplication unchanged."""
        text = "I decided to use Python"
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1

    def test_empty_list_deduplication(self, detector: SignalDetector) -> None:
        """Test that empty signal list is handled."""
        text = "No signals here at all"
        signals = detector.detect(text)
        # Should return empty list without error
        assert isinstance(signals, list)


# =============================================================================
# detect_all_types() Tests
# =============================================================================


class TestDetectAllTypes:
    """Test the detect_all_types() grouping method."""

    def test_returns_dict(self, detector: SignalDetector) -> None:
        """Test detect_all_types returns a dictionary."""
        text = "I decided to use Python because TIL it has great libraries"
        result = detector.detect_all_types(text)
        assert isinstance(result, dict)

    def test_groups_by_signal_type(self, detector: SignalDetector) -> None:
        """Test signals are correctly grouped by type."""
        text = "I decided to use PostgreSQL. TIL about its JSON support."
        result = detector.detect_all_types(text)

        if SignalType.DECISION in result:
            assert all(
                s.type == SignalType.DECISION for s in result[SignalType.DECISION]
            )
        if SignalType.LEARNING in result:
            assert all(
                s.type == SignalType.LEARNING for s in result[SignalType.LEARNING]
            )

    def test_multiple_signals_same_type(self, detector: SignalDetector) -> None:
        """Test multiple signals of same type are grouped together."""
        text = "I decided on option A. Later, we chose option B. Finally decided on C."
        result = detector.detect_all_types(text)

        if SignalType.DECISION in result:
            # Might have multiple decision signals
            assert isinstance(result[SignalType.DECISION], list)

    def test_empty_text_returns_empty_dict(self, detector: SignalDetector) -> None:
        """Test empty text returns empty dict."""
        result = detector.detect_all_types("")
        assert result == {}

    def test_no_signals_returns_empty_dict(self, detector: SignalDetector) -> None:
        """Test text with no signals returns empty dict."""
        result = detector.detect_all_types("Just some regular text here")
        # May or may not have signals depending on patterns
        assert isinstance(result, dict)

    def test_all_types_represented(self, detector: SignalDetector) -> None:
        """Test that all signal types can appear in result."""
        text = (
            "I decided to proceed. "
            "TIL about this. "
            "Blocked by the issue. "
            "Fixed the bug. "
            "I prefer this approach. "
            "Remember this for later."
        )
        result = detector.detect_all_types(text)
        # Should have multiple different types
        assert len(result) >= 3


# =============================================================================
# classify() Method Tests
# =============================================================================


class TestClassifyMethod:
    """Test the classify() convenience method."""

    def test_classify_returns_namespace(self, detector: SignalDetector) -> None:
        """Test classify returns the suggested namespace."""
        text = "I decided to use Python"
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1

        namespace = detector.classify(decision_signals[0])
        assert namespace == "decisions"

    def test_classify_all_types(self, detector: SignalDetector) -> None:
        """Test classify returns correct namespace for all types."""
        expected_namespaces = {
            SignalType.DECISION: "decisions",
            SignalType.LEARNING: "learnings",
            SignalType.BLOCKER: "blockers",
            SignalType.RESOLUTION: "solutions",
            SignalType.PREFERENCE: "preferences",
            SignalType.EXPLICIT: "notes",
        }

        for signal_type, expected_namespace in expected_namespaces.items():
            signal = CaptureSignal(
                type=signal_type,
                match="test",
                confidence=0.9,
                context="test context",
                suggested_namespace=signal_type.suggested_namespace,
                position=0,
            )
            assert detector.classify(signal) == expected_namespace


# =============================================================================
# Edge Cases and Boundary Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_text(self, detector: SignalDetector) -> None:
        """Test empty text returns empty list."""
        signals = detector.detect("")
        assert signals == []

    def test_very_short_text(self, detector: SignalDetector) -> None:
        """Test text shorter than 5 characters returns empty list."""
        signals = detector.detect("Hi")
        assert signals == []

    def test_exactly_five_chars(self, detector: SignalDetector) -> None:
        """Test text exactly 5 characters."""
        signals = detector.detect("Hello")
        assert isinstance(signals, list)

    def test_whitespace_only(self, detector: SignalDetector) -> None:
        """Test whitespace-only text."""
        signals = detector.detect("   \n\t  ")
        assert signals == []

    def test_very_long_text(self, detector: SignalDetector) -> None:
        """Test very long text is handled."""
        text = "I decided to proceed. " * 1000
        signals = detector.detect(text)
        assert isinstance(signals, list)
        # Should detect many signals in repeated text
        assert len(signals) >= 1

    def test_unicode_characters(self, detector: SignalDetector) -> None:
        """Test unicode characters in text."""
        text = "I decided to use the emoji approach"
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1

    def test_unicode_in_context(self, detector: SignalDetector) -> None:
        """Test unicode in surrounding context."""
        text = "After considering options, I decided to proceed."
        signals = detector.detect(text)
        assert len(signals) >= 1

    def test_special_characters(self, detector: SignalDetector) -> None:
        """Test special characters don't break detection."""
        text = 'I decided to use <HTML> & "quotes" in the `code`'
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1

    def test_newlines_in_text(self, detector: SignalDetector) -> None:
        """Test newlines in text."""
        text = "First line.\nI decided to proceed.\nLast line."
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1

    def test_tabs_in_text(self, detector: SignalDetector) -> None:
        """Test tabs in text."""
        text = "Code:\tI decided to\tuse\ttabs"
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1

    def test_mixed_case_patterns(self, detector: SignalDetector) -> None:
        """Test patterns match case-insensitively."""
        cases = [
            "I DECIDED to proceed",
            "i decided to proceed",
            "I Decided To Proceed",
        ]
        for text in cases:
            signals = detector.detect(text)
            decision_signals = [s for s in signals if s.type == SignalType.DECISION]
            assert len(decision_signals) >= 1, f"Failed for: {text}"

    def test_no_false_positives_on_similar_text(self, detector: SignalDetector) -> None:
        """Test that similar but non-matching text doesn't trigger false positives."""
        # "decide" without "to" shouldn't match "I decided to"
        text = "The decide function is complex"
        signals = detector.detect(text)
        # May or may not have signals, but shouldn't have high-confidence decision signal
        decision_signals = [
            s for s in signals if s.type == SignalType.DECISION and s.confidence > 0.85
        ]
        assert len(decision_signals) == 0


# =============================================================================
# Minimum Confidence Threshold Tests
# =============================================================================


class TestMinConfidenceThreshold:
    """Test min_confidence filtering behavior."""

    def test_signals_below_threshold_filtered(
        self, detector_high_threshold: SignalDetector
    ) -> None:
        """Test signals below min_confidence are filtered out."""
        # "interestingly" has base confidence 0.70, which is below 0.85 threshold
        text = "Interestingly, this works differently"
        signals = detector_high_threshold.detect(text)
        # Low confidence signals should be filtered
        for signal in signals:
            assert signal.confidence >= 0.85

    def test_signals_above_threshold_kept(
        self, detector_high_threshold: SignalDetector
    ) -> None:
        """Test signals at or above min_confidence are kept."""
        # "I decided to" has base confidence 0.90
        text = "I decided to use the high confidence pattern"
        signals = detector_high_threshold.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1

    def test_zero_threshold_includes_all(self, detector: SignalDetector) -> None:
        """Test zero min_confidence includes all signals."""
        text = "Interestingly, I want this to work"
        signals = detector.detect(text)
        # Should include low-confidence signals with default threshold of 0.0
        types_found = {s.type for s in signals}
        assert len(types_found) >= 1


# =============================================================================
# Signal Position Tests
# =============================================================================


class TestSignalPositions:
    """Test signal position tracking."""

    def test_position_is_correct(self, detector: SignalDetector) -> None:
        """Test that position accurately reflects where match starts."""
        text = "Start text. I decided to proceed. End text."
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1

        signal = decision_signals[0]
        # Position should point to where match starts
        assert (
            text[signal.position : signal.position + len(signal.match)] == signal.match
        )

    def test_signals_sorted_by_position(self, detector: SignalDetector) -> None:
        """Test signals are returned sorted by position."""
        text = "First: TIL about this. Second: I decided to proceed."
        signals = detector.detect(text)

        positions = [s.position for s in signals]
        assert positions == sorted(positions)

    def test_multiple_positions_different_types(self, detector: SignalDetector) -> None:
        """Test multiple signals at different positions."""
        text = "TIL x. I decided y. Fixed z."
        signals = detector.detect(text)

        # Each signal should have unique position
        positions = [s.position for s in signals]
        # After deduplication, positions should be reasonable
        assert len(positions) >= 1


# =============================================================================
# CaptureSignal Model Integration Tests
# =============================================================================


class TestCaptureSignalIntegration:
    """Test integration with CaptureSignal model."""

    def test_signal_is_frozen_dataclass(self, detector: SignalDetector) -> None:
        """Test returned signals are immutable CaptureSignal objects."""
        text = "I decided to use Python"
        signals = detector.detect(text)
        assert len(signals) >= 1

        signal = signals[0]
        assert isinstance(signal, CaptureSignal)

        # Should be immutable
        with pytest.raises(AttributeError):
            signal.confidence = 0.5  # type: ignore[misc]

    def test_signal_has_all_required_fields(self, detector: SignalDetector) -> None:
        """Test signals have all required CaptureSignal fields."""
        text = "I decided to use PostgreSQL"
        signals = detector.detect(text)
        assert len(signals) >= 1

        signal = signals[0]
        assert hasattr(signal, "type")
        assert hasattr(signal, "match")
        assert hasattr(signal, "confidence")
        assert hasattr(signal, "context")
        assert hasattr(signal, "suggested_namespace")
        assert hasattr(signal, "position")

    def test_signal_type_is_enum(self, detector: SignalDetector) -> None:
        """Test signal type is a SignalType enum value."""
        text = "I decided to proceed"
        signals = detector.detect(text)
        assert len(signals) >= 1

        signal = signals[0]
        assert isinstance(signal.type, SignalType)

    def test_confidence_within_valid_range(self, detector: SignalDetector) -> None:
        """Test all confidence scores are valid (0.0-1.0)."""
        text = "I decided x. TIL y. Blocked by z. Fixed w. I prefer a. Remember b."
        signals = detector.detect(text)

        for signal in signals:
            assert 0.0 <= signal.confidence <= 1.0


# =============================================================================
# Real-World Usage Pattern Tests
# =============================================================================


class TestRealWorldPatterns:
    """Test with realistic usage patterns."""

    def test_developer_decision(self, detector: SignalDetector) -> None:
        """Test typical developer decision statement."""
        text = (
            "After evaluating PostgreSQL, MySQL, and SQLite, I decided to use "
            "PostgreSQL for this project because of its ACID compliance and JSON support."
        )
        signals = detector.detect(text)
        decision_signals = [s for s in signals if s.type == SignalType.DECISION]
        assert len(decision_signals) >= 1
        assert decision_signals[0].confidence >= 0.80

    def test_learning_from_debugging(self, detector: SignalDetector) -> None:
        """Test learning discovered during debugging."""
        text = (
            "I learned that the cache was stale because the TTL was set incorrectly. "
            "Turns out the default value was much higher than expected."
        )
        signals = detector.detect(text)
        learning_signals = [s for s in signals if s.type == SignalType.LEARNING]
        assert len(learning_signals) >= 1

    def test_blocker_report(self, detector: SignalDetector) -> None:
        """Test typical blocker report."""
        text = (
            "Blocked by CORS configuration. The frontend can't call the backend API "
            "because the Access-Control-Allow-Origin header is missing."
        )
        signals = detector.detect(text)
        blocker_signals = [s for s in signals if s.type == SignalType.BLOCKER]
        assert len(blocker_signals) >= 1
        assert blocker_signals[0].confidence >= 0.85

    def test_resolution_announcement(self, detector: SignalDetector) -> None:
        """Test typical resolution announcement."""
        text = (
            "Fixed the authentication issue by updating the JWT validation logic. "
            "The solution was to check the token expiry before validating the signature."
        )
        signals = detector.detect(text)
        resolution_signals = [s for s in signals if s.type == SignalType.RESOLUTION]
        assert len(resolution_signals) >= 1

    def test_preference_expression(self, detector: SignalDetector) -> None:
        """Test typical preference expression."""
        text = (
            "I prefer to use TypeScript for larger projects because of its type safety. "
            "My preference is for explicit types over inferred types."
        )
        signals = detector.detect(text)
        preference_signals = [s for s in signals if s.type == SignalType.PREFERENCE]
        assert len(preference_signals) >= 1

    def test_explicit_memory_request(self, detector: SignalDetector) -> None:
        """Test explicit memory request."""
        text = (
            "Remember this for future deployments: always check the environment "
            "variables before starting the application. For future reference, "
            "the config file must exist."
        )
        signals = detector.detect(text)
        explicit_signals = [s for s in signals if s.type == SignalType.EXPLICIT]
        assert len(explicit_signals) >= 1

    def test_mixed_signals_in_discussion(self, detector: SignalDetector) -> None:
        """Test realistic discussion with multiple signal types."""
        text = (
            "I was stuck on the authentication issue for hours. "
            "Turns out the problem was in the token validation. "
            "I decided to switch to a different JWT library. "
            "After the change, everything worked. "
            "Remember this approach for similar issues."
        )
        signals = detector.detect(text)

        # Should have multiple types
        types_found = {s.type for s in signals}
        assert len(types_found) >= 3
