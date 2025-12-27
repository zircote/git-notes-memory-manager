"""Tests for HybridSearchConfig.

Tests cover:
- Default configuration values
- Environment variable loading
- Invalid value handling
- RRF weights extraction
"""

from __future__ import annotations

import pytest

from git_notes_memory.retrieval.config import HybridSearchConfig


# =============================================================================
# Test: Default Configuration
# =============================================================================


class TestDefaultConfig:
    """Test default configuration values."""

    def test_default_mode(self) -> None:
        """Test default search mode is hybrid."""
        config = HybridSearchConfig()
        assert config.mode == "hybrid"

    def test_default_rrf_k(self) -> None:
        """Test default RRF k is 60."""
        config = HybridSearchConfig()
        assert config.rrf_k == 60

    def test_default_weights(self) -> None:
        """Test default weights."""
        config = HybridSearchConfig()
        assert config.vector_weight == 1.0
        assert config.bm25_weight == 1.0
        assert config.entity_weight == 0.8

    def test_default_features_enabled(self) -> None:
        """Test default feature flags."""
        config = HybridSearchConfig()
        assert config.entity_boost_enabled is True
        assert config.temporal_enabled is True
        assert config.query_expansion_enabled is True
        assert config.expand_query_default is False  # Opt-in per ADR-007
        assert config.parallel_search is True

    def test_default_max_results(self) -> None:
        """Test default max results per source."""
        config = HybridSearchConfig()
        assert config.max_results_per_source == 100

    def test_default_spacy_model(self) -> None:
        """Test default spaCy model."""
        config = HybridSearchConfig()
        assert config.spacy_model == "en_core_web_sm"


# =============================================================================
# Test: Custom Configuration
# =============================================================================


class TestCustomConfig:
    """Test custom configuration."""

    def test_custom_mode(self) -> None:
        """Test custom search mode."""
        config = HybridSearchConfig(mode="vector")
        assert config.mode == "vector"

    def test_custom_weights(self) -> None:
        """Test custom weights."""
        config = HybridSearchConfig(
            vector_weight=1.5,
            bm25_weight=0.8,
            entity_weight=1.2,
        )
        assert config.vector_weight == 1.5
        assert config.bm25_weight == 0.8
        assert config.entity_weight == 1.2

    def test_frozen_config(self) -> None:
        """Test config is immutable."""
        config = HybridSearchConfig()
        with pytest.raises(AttributeError):
            config.mode = "vector"  # type: ignore[misc]  # noqa: E501


# =============================================================================
# Test: Environment Variable Loading
# =============================================================================


class TestEnvLoading:
    """Test loading config from environment variables."""

    def test_load_mode_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading mode from env."""
        monkeypatch.setenv("HYBRID_SEARCH_MODE", "bm25")
        config = HybridSearchConfig.from_env()
        assert config.mode == "bm25"

    def test_load_rrf_k_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading RRF k from env."""
        monkeypatch.setenv("HYBRID_SEARCH_RRF_K", "100")
        config = HybridSearchConfig.from_env()
        assert config.rrf_k == 100

    def test_load_weights_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading weights from env."""
        monkeypatch.setenv("HYBRID_SEARCH_VECTOR_WEIGHT", "1.5")
        monkeypatch.setenv("HYBRID_SEARCH_BM25_WEIGHT", "0.8")
        monkeypatch.setenv("HYBRID_SEARCH_ENTITY_WEIGHT", "1.2")
        config = HybridSearchConfig.from_env()
        assert config.vector_weight == 1.5
        assert config.bm25_weight == 0.8
        assert config.entity_weight == 1.2

    def test_load_bool_true_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading boolean true variants."""
        for val in ("true", "True", "TRUE", "1", "yes", "on"):
            monkeypatch.setenv("HYBRID_SEARCH_ENTITY_BOOST_ENABLED", val)
            config = HybridSearchConfig.from_env()
            assert config.entity_boost_enabled is True, f"Failed for value: {val}"

    def test_load_bool_false_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading boolean false variants."""
        for val in ("false", "False", "FALSE", "0", "no", "off"):
            monkeypatch.setenv("HYBRID_SEARCH_ENTITY_BOOST_ENABLED", val)
            config = HybridSearchConfig.from_env()
            assert config.entity_boost_enabled is False, f"Failed for value: {val}"

    def test_load_parallel_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading parallel setting from env."""
        monkeypatch.setenv("HYBRID_SEARCH_PARALLEL", "false")
        config = HybridSearchConfig.from_env()
        assert config.parallel_search is False

    def test_load_spacy_model_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading spaCy model from env."""
        monkeypatch.setenv("HYBRID_SEARCH_SPACY_MODEL", "en_core_web_lg")
        config = HybridSearchConfig.from_env()
        assert config.spacy_model == "en_core_web_lg"

    def test_custom_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading with custom prefix."""
        monkeypatch.setenv("CUSTOM_MODE", "vector")
        config = HybridSearchConfig.from_env(prefix="CUSTOM_")
        assert config.mode == "vector"


# =============================================================================
# Test: Invalid Values
# =============================================================================


class TestInvalidValues:
    """Test handling of invalid environment values."""

    def test_invalid_int_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test invalid int falls back to default."""
        monkeypatch.setenv("HYBRID_SEARCH_RRF_K", "not_a_number")
        config = HybridSearchConfig.from_env()
        assert config.rrf_k == 60  # Default

    def test_invalid_float_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test invalid float falls back to default."""
        monkeypatch.setenv("HYBRID_SEARCH_VECTOR_WEIGHT", "not_a_number")
        config = HybridSearchConfig.from_env()
        assert config.vector_weight == 1.0  # Default

    def test_invalid_mode_uses_hybrid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test invalid mode falls back to hybrid."""
        monkeypatch.setenv("HYBRID_SEARCH_MODE", "invalid_mode")
        config = HybridSearchConfig.from_env()
        assert config.mode == "hybrid"


# =============================================================================
# Test: RRF Weights Extraction
# =============================================================================


class TestRRFWeights:
    """Test RRF weights extraction."""

    def test_get_rrf_weights_default(self) -> None:
        """Test default RRF weights extraction."""
        config = HybridSearchConfig()
        weights = config.get_rrf_weights()

        assert weights == (
            ("vector", 1.0),
            ("bm25", 1.0),
            ("entity", 0.8),
        )

    def test_get_rrf_weights_custom(self) -> None:
        """Test custom RRF weights extraction."""
        config = HybridSearchConfig(
            vector_weight=1.5,
            bm25_weight=0.5,
            entity_weight=2.0,
        )
        weights = config.get_rrf_weights()

        assert weights == (
            ("vector", 1.5),
            ("bm25", 0.5),
            ("entity", 2.0),
        )


# =============================================================================
# Test: Integration with RRFConfig
# =============================================================================


class TestRRFIntegration:
    """Test integration with RRFConfig."""

    def test_weights_compatible_with_rrf_config(self) -> None:
        """Test that weights work with RRFConfig."""
        from git_notes_memory.index.rrf_fusion import RRFConfig

        config = HybridSearchConfig()
        weights = config.get_rrf_weights()

        rrf_config = RRFConfig(k=config.rrf_k, weights=weights)

        assert rrf_config.get_weight("vector") == 1.0
        assert rrf_config.get_weight("bm25") == 1.0
        assert rrf_config.get_weight("entity") == 0.8
