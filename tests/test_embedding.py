"""Tests for the EmbeddingService module.

Tests cover:
- Lazy loading behavior
- Single text embedding
- Batch embedding
- Similarity calculation
- Error handling
- Singleton access

Note: Some tests mock the sentence-transformers library to avoid
slow model downloads during testing. Integration tests with real
models are marked with pytest.mark.slow.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from git_notes_memory.embedding import (
    CircuitOpenError,
    CircuitState,
    EmbeddingCircuitBreaker,
    EmbeddingService,
    get_default_service,
)
from git_notes_memory.exceptions import EmbeddingError

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_model() -> MagicMock:
    """Create a mock SentenceTransformer model."""
    model = MagicMock()
    model.get_sentence_embedding_dimension.return_value = 384

    def mock_encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=False,
    ):
        """Generate mock embeddings."""
        # Handle single text vs batch
        if isinstance(texts, str):
            return np.array([0.1] * 384, dtype=np.float32)
        else:
            return np.array([[0.1] * 384 for _ in texts], dtype=np.float32)

    model.encode.side_effect = mock_encode
    return model


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory."""
    cache = tmp_path / "models"
    cache.mkdir()
    return cache


@pytest.fixture
def embedding_service(cache_dir: Path, mock_model: MagicMock) -> EmbeddingService:
    """Create an EmbeddingService with mocked model."""
    service = EmbeddingService(
        model_name="test-model",
        cache_dir=cache_dir,
    )

    # Patch at the source since SentenceTransformer is imported inside load()
    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        service.load()

    return service


# =============================================================================
# Test: Initialization
# =============================================================================


class TestInitialization:
    """Test EmbeddingService initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization uses default settings."""
        with patch("git_notes_memory.embedding.get_embedding_model") as mock_model:
            with patch("git_notes_memory.embedding.get_models_path") as mock_path:
                mock_model.return_value = "all-MiniLM-L6-v2"
                mock_path.return_value = Path("/tmp/models")

                service = EmbeddingService()

                assert service.model_name == "all-MiniLM-L6-v2"
                assert service.cache_dir == Path("/tmp/models")

    def test_init_with_custom_model(self, cache_dir: Path) -> None:
        """Test initialization with custom model name."""
        service = EmbeddingService(
            model_name="custom-model",
            cache_dir=cache_dir,
        )
        assert service.model_name == "custom-model"

    def test_init_with_custom_cache_dir(self, cache_dir: Path) -> None:
        """Test initialization with custom cache directory."""
        service = EmbeddingService(
            model_name="test-model",
            cache_dir=cache_dir,
        )
        assert service.cache_dir == cache_dir

    def test_is_loaded_false_initially(self, cache_dir: Path) -> None:
        """Test is_loaded is False before loading."""
        service = EmbeddingService(cache_dir=cache_dir)
        assert service.is_loaded is False

    def test_dimensions_returns_default_before_load(self, cache_dir: Path) -> None:
        """Test dimensions returns default value before model is loaded."""
        service = EmbeddingService(cache_dir=cache_dir)
        assert service.dimensions == 384


# =============================================================================
# Test: Model Loading
# =============================================================================


class TestModelLoading:
    """Test model loading behavior."""

    def test_load_sets_is_loaded(self, cache_dir: Path, mock_model: MagicMock) -> None:
        """Test load sets is_loaded to True."""
        service = EmbeddingService(cache_dir=cache_dir)

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            service.load()

        assert service.is_loaded is True

    def test_load_creates_cache_directory(
        self, tmp_path: Path, mock_model: MagicMock
    ) -> None:
        """Test load creates cache directory if it doesn't exist."""
        cache_dir = tmp_path / "nonexistent" / "models"
        service = EmbeddingService(cache_dir=cache_dir)

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            service.load()

        assert cache_dir.exists()

    def test_load_is_idempotent(self, cache_dir: Path, mock_model: MagicMock) -> None:
        """Test load can be called multiple times safely."""
        service = EmbeddingService(cache_dir=cache_dir)

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ) as mock_cls:
            service.load()
            service.load()  # Second call should be no-op

            # Only one instance should be created
            assert mock_cls.call_count == 1

    def test_load_sets_dimensions_from_model(self, cache_dir: Path) -> None:
        """Test load sets dimensions from actual model."""
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 512

        service = EmbeddingService(cache_dir=cache_dir)

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            service.load()

        assert service.dimensions == 512

    def test_load_memory_error_raises_embedding_error(self, cache_dir: Path) -> None:
        """Test load raises EmbeddingError on memory error."""
        service = EmbeddingService(cache_dir=cache_dir)

        with patch("sentence_transformers.SentenceTransformer") as mock_cls:
            mock_cls.side_effect = MemoryError("Out of memory")

            with pytest.raises(EmbeddingError) as exc_info:
                service.load()

            assert "Insufficient memory" in exc_info.value.message

    def test_load_corrupt_cache_raises_embedding_error(self, cache_dir: Path) -> None:
        """Test load raises EmbeddingError on corrupt cache."""
        service = EmbeddingService(cache_dir=cache_dir)

        with patch("sentence_transformers.SentenceTransformer") as mock_cls:
            mock_cls.side_effect = OSError("Corrupt file detected")

            with pytest.raises(EmbeddingError) as exc_info:
                service.load()

            assert "corrupted" in exc_info.value.message

    def test_load_generic_error_raises_embedding_error(self, cache_dir: Path) -> None:
        """Test load raises EmbeddingError on generic error."""
        service = EmbeddingService(cache_dir=cache_dir)

        with patch("sentence_transformers.SentenceTransformer") as mock_cls:
            mock_cls.side_effect = ValueError("Unknown error")

            with pytest.raises(EmbeddingError) as exc_info:
                service.load()

            assert "Failed to load" in exc_info.value.message


class TestWarmup:
    """Test model warmup for PERF-H-004."""

    def test_warmup_loads_model(self, cache_dir: Path, mock_model: MagicMock) -> None:
        """Test warmup loads the model if not loaded."""
        service = EmbeddingService(cache_dir=cache_dir)

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            warmup_time = service.warmup()

        assert service.is_loaded is True
        assert warmup_time >= 0.0

    def test_warmup_runs_test_embedding(
        self, cache_dir: Path, mock_model: MagicMock
    ) -> None:
        """Test warmup runs a test embedding to warm up JIT."""
        service = EmbeddingService(cache_dir=cache_dir)

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            service.warmup()

        # Verify encode was called with warmup text
        mock_model.encode.assert_called_once()
        call_args = mock_model.encode.call_args
        assert call_args[0][0] == "warmup"

    def test_warmup_returns_elapsed_time(
        self, cache_dir: Path, mock_model: MagicMock
    ) -> None:
        """Test warmup returns the time taken."""
        service = EmbeddingService(cache_dir=cache_dir)

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            warmup_time = service.warmup()

        assert isinstance(warmup_time, float)
        assert warmup_time >= 0.0


# =============================================================================
# Test: Single Text Embedding
# =============================================================================


class TestSingleEmbedding:
    """Test single text embedding."""

    def test_embed_returns_list_of_floats(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed returns a list of floats."""
        result = embedding_service.embed("Hello, world!")

        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)

    def test_embed_returns_correct_dimensions(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed returns vector with correct dimensions."""
        result = embedding_service.embed("Hello, world!")
        assert len(result) == 384

    def test_embed_empty_string_returns_zero_vector(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed returns zero vector for empty string."""
        result = embedding_service.embed("")
        assert result == [0.0] * 384

    def test_embed_whitespace_returns_zero_vector(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed returns zero vector for whitespace-only string."""
        result = embedding_service.embed("   \n\t  ")
        assert result == [0.0] * 384

    def test_embed_lazy_loads_model(
        self, cache_dir: Path, mock_model: MagicMock
    ) -> None:
        """Test embed loads model on first call."""
        service = EmbeddingService(cache_dir=cache_dir)
        assert service.is_loaded is False

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            service.embed("Hello")

        assert service.is_loaded is True

    def test_embed_error_raises_embedding_error(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed raises EmbeddingError on failure."""
        embedding_service._model.encode.side_effect = RuntimeError("Encoding failed")

        with pytest.raises(EmbeddingError) as exc_info:
            embedding_service.embed("Hello")

        assert "Failed to generate embedding" in exc_info.value.message


# =============================================================================
# Test: Batch Embedding
# =============================================================================


class TestBatchEmbedding:
    """Test batch text embedding."""

    def test_embed_batch_returns_list_of_lists(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed_batch returns a list of lists."""
        texts = ["Hello", "World"]
        result = embedding_service.embed_batch(texts)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(e, list) for e in result)

    def test_embed_batch_correct_dimensions(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed_batch returns vectors with correct dimensions."""
        texts = ["Hello", "World", "Test"]
        result = embedding_service.embed_batch(texts)

        assert all(len(e) == 384 for e in result)

    def test_embed_batch_empty_list_returns_empty(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed_batch returns empty list for empty input."""
        result = embedding_service.embed_batch([])
        assert result == []

    def test_embed_batch_handles_empty_strings(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed_batch returns zero vectors for empty strings."""
        texts = ["Hello", "", "World"]
        result = embedding_service.embed_batch(texts)

        assert len(result) == 3
        # Second embedding should be zeros
        assert result[1] == [0.0] * 384
        # Others should be non-zero
        assert result[0] != [0.0] * 384
        assert result[2] != [0.0] * 384

    def test_embed_batch_all_empty_returns_zero_vectors(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed_batch returns zero vectors when all inputs are empty."""
        texts = ["", "  ", "\n"]
        result = embedding_service.embed_batch(texts)

        assert len(result) == 3
        assert all(e == [0.0] * 384 for e in result)

    def test_embed_batch_lazy_loads_model(
        self,
        cache_dir: Path,
        mock_model: MagicMock,
    ) -> None:
        """Test embed_batch loads model on first call."""
        service = EmbeddingService(cache_dir=cache_dir)
        assert service.is_loaded is False

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            service.embed_batch(["Hello", "World"])

        assert service.is_loaded is True

    def test_embed_batch_with_batch_size(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed_batch respects batch_size parameter."""
        texts = ["Hello", "World"]
        embedding_service.embed_batch(texts, batch_size=1)

        # Verify batch_size was passed to model
        call_kwargs = embedding_service._model.encode.call_args.kwargs
        assert call_kwargs.get("batch_size") == 1

    def test_embed_batch_with_progress(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed_batch respects show_progress parameter."""
        texts = ["Hello", "World"]
        embedding_service.embed_batch(texts, show_progress=True)

        # Verify show_progress_bar was passed to model
        call_kwargs = embedding_service._model.encode.call_args.kwargs
        assert call_kwargs.get("show_progress_bar") is True

    def test_embed_batch_error_raises_embedding_error(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test embed_batch raises EmbeddingError on failure."""
        embedding_service._model.encode.side_effect = RuntimeError("Batch failed")

        with pytest.raises(EmbeddingError) as exc_info:
            embedding_service.embed_batch(["Hello", "World"])

        assert "Failed to generate batch embeddings" in exc_info.value.message


# =============================================================================
# Test: Circuit Breaker (CRIT-001)
# =============================================================================


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_initial_state_is_closed(self) -> None:
        """Test circuit breaker starts in closed state."""
        cb = EmbeddingCircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    def test_allow_request_when_closed(self) -> None:
        """Test requests are allowed in closed state."""
        cb = EmbeddingCircuitBreaker()
        assert cb.allow_request() is True

    def test_state_opens_after_threshold_failures(self) -> None:
        """Test circuit opens after failure threshold is reached."""
        cb = EmbeddingCircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

        cb.record_failure()  # Third failure opens circuit
        assert cb.state == CircuitState.OPEN

    def test_requests_blocked_when_open(self) -> None:
        """Test requests are blocked when circuit is open."""
        cb = EmbeddingCircuitBreaker(failure_threshold=1)
        cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self) -> None:
        """Test success resets failure count in closed state."""
        cb = EmbeddingCircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()

        # After success, should need 3 more failures to open
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_status_returns_correct_info(self) -> None:
        """Test status returns correct state information."""
        cb = EmbeddingCircuitBreaker(failure_threshold=3)
        cb.record_failure()

        status = cb.status()
        assert status["state"] == "closed"
        assert status["failure_count"] == 1
        assert status["failure_threshold"] == 3

    def test_reset_clears_all_state(self) -> None:
        """Test reset clears circuit breaker state."""
        cb = EmbeddingCircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_circuit_open_error_attributes(self) -> None:
        """Test CircuitOpenError has correct attributes."""
        error = CircuitOpenError(
            state=CircuitState.OPEN,
            failures=3,
            threshold=3,
        )

        assert error.circuit_state == CircuitState.OPEN
        assert error.failures == 3
        assert error.threshold == 3
        assert "circuit breaker is open" in str(error)


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration with EmbeddingService."""

    def test_embed_raises_circuit_open_error(
        self,
        cache_dir: Path,
        mock_model: MagicMock,
    ) -> None:
        """Test embed raises CircuitOpenError when circuit is open."""
        cb = EmbeddingCircuitBreaker(failure_threshold=1)
        cb.record_failure()  # Open the circuit

        service = EmbeddingService(cache_dir=cache_dir, circuit_breaker=cb)

        with pytest.raises(CircuitOpenError) as exc_info:
            service.embed("Hello")

        assert exc_info.value.circuit_state == CircuitState.OPEN

    def test_embed_batch_raises_circuit_open_error(
        self,
        cache_dir: Path,
        mock_model: MagicMock,
    ) -> None:
        """Test embed_batch raises CircuitOpenError when circuit is open."""
        cb = EmbeddingCircuitBreaker(failure_threshold=1)
        cb.record_failure()  # Open the circuit

        service = EmbeddingService(cache_dir=cache_dir, circuit_breaker=cb)

        with pytest.raises(CircuitOpenError) as exc_info:
            service.embed_batch(["Hello", "World"])

        assert exc_info.value.circuit_state == CircuitState.OPEN

    def test_embed_records_failure_on_error(
        self,
        cache_dir: Path,
        mock_model: MagicMock,
    ) -> None:
        """Test embed records failure to circuit breaker on error."""
        cb = EmbeddingCircuitBreaker(failure_threshold=3)
        service = EmbeddingService(cache_dir=cache_dir, circuit_breaker=cb)

        # Patch to make encode fail
        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            service.load()

        mock_model.encode.side_effect = RuntimeError("Model error")

        # Should not raise CircuitOpenError yet
        with pytest.raises(EmbeddingError):
            service.embed("Hello")

        status = cb.status()
        assert status["failure_count"] == 1

    def test_embed_records_success(
        self,
        cache_dir: Path,
        mock_model: MagicMock,
    ) -> None:
        """Test embed records success to circuit breaker."""
        cb = EmbeddingCircuitBreaker(failure_threshold=3)
        cb.record_failure()  # Add a failure

        service = EmbeddingService(cache_dir=cache_dir, circuit_breaker=cb)

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            service.load()

        service.embed("Hello")

        # Success should reset failure count
        status = cb.status()
        assert status["failure_count"] == 0

    def test_circuit_breaker_property(
        self,
        cache_dir: Path,
    ) -> None:
        """Test circuit_breaker property returns the instance."""
        cb = EmbeddingCircuitBreaker()
        service = EmbeddingService(cache_dir=cache_dir, circuit_breaker=cb)

        assert service.circuit_breaker is cb

    def test_default_circuit_breaker_created(
        self,
        cache_dir: Path,
    ) -> None:
        """Test default circuit breaker is created if not provided."""
        service = EmbeddingService(cache_dir=cache_dir)
        assert service.circuit_breaker is not None
        assert isinstance(service.circuit_breaker, EmbeddingCircuitBreaker)


# =============================================================================
# Test: Similarity
# =============================================================================


class TestSimilarity:
    """Test similarity calculation."""

    def test_similarity_identical_vectors(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test similarity of identical normalized vectors is 1."""
        # Normalized vector (unit length)
        vec = [1.0 / (384**0.5)] * 384
        result = embedding_service.similarity(vec, vec)

        assert abs(result - 1.0) < 0.001

    def test_similarity_orthogonal_vectors(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test similarity of orthogonal vectors is 0."""
        vec1 = [1.0] + [0.0] * 383
        vec2 = [0.0, 1.0] + [0.0] * 382
        result = embedding_service.similarity(vec1, vec2)

        assert abs(result) < 0.001

    def test_similarity_opposite_vectors(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test similarity of opposite vectors is -1."""
        vec1 = [1.0 / (384**0.5)] * 384
        vec2 = [-1.0 / (384**0.5)] * 384
        result = embedding_service.similarity(vec1, vec2)

        assert abs(result + 1.0) < 0.001

    def test_similarity_different_dimensions_raises(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test similarity raises ValueError for mismatched dimensions."""
        vec1 = [1.0] * 384
        vec2 = [1.0] * 256

        with pytest.raises(ValueError) as exc_info:
            embedding_service.similarity(vec1, vec2)

        assert "dimensions must match" in str(exc_info.value)


# =============================================================================
# Test: Unload
# =============================================================================


class TestUnload:
    """Test model unloading."""

    def test_unload_sets_is_loaded_false(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test unload sets is_loaded to False."""
        assert embedding_service.is_loaded is True
        embedding_service.unload()
        assert embedding_service.is_loaded is False

    def test_unload_preserves_dimensions(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test unload preserves cached dimensions."""
        dims_before = embedding_service.dimensions
        embedding_service.unload()
        assert embedding_service.dimensions == dims_before

    def test_unload_can_be_called_multiple_times(
        self,
        embedding_service: EmbeddingService,
    ) -> None:
        """Test unload can be called safely multiple times."""
        embedding_service.unload()
        embedding_service.unload()  # Should not raise

    def test_embed_after_unload_reloads(
        self,
        cache_dir: Path,
        mock_model: MagicMock,
    ) -> None:
        """Test embed reloads model after unload."""
        service = EmbeddingService(cache_dir=cache_dir)

        with patch(
            "sentence_transformers.SentenceTransformer", return_value=mock_model
        ):
            service.load()
            service.unload()
            assert service.is_loaded is False

            service.embed("Hello")
            assert service.is_loaded is True


# =============================================================================
# Test: Singleton
# =============================================================================


class TestSingleton:
    """Test singleton access."""

    def test_get_default_service_returns_instance(self) -> None:
        """Test get_default_service returns an EmbeddingService."""
        # Reset singleton for test
        import git_notes_memory.embedding as embedding_module

        embedding_module._default_service = None

        service = get_default_service()
        assert isinstance(service, EmbeddingService)

    def test_get_default_service_returns_same_instance(self) -> None:
        """Test get_default_service returns the same instance."""
        # Reset singleton for test
        import git_notes_memory.embedding as embedding_module

        embedding_module._default_service = None

        service1 = get_default_service()
        service2 = get_default_service()
        assert service1 is service2


# =============================================================================
# Test: Integration (Slow)
# =============================================================================


@pytest.mark.slow
class TestIntegration:
    """Integration tests with real model.

    These tests download and use the actual embedding model.
    They are slow and require network access.
    Mark with pytest.mark.slow and skip by default.
    """

    def test_real_model_loads(self, cache_dir: Path) -> None:
        """Test that the real model loads successfully."""
        service = EmbeddingService(cache_dir=cache_dir)
        service.load()

        assert service.is_loaded is True
        assert service.dimensions == 384

    def test_real_embedding_generation(self, cache_dir: Path) -> None:
        """Test generating real embeddings."""
        service = EmbeddingService(cache_dir=cache_dir)
        embedding = service.embed("Hello, world!")

        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)
        # Normalized embeddings should have magnitude ~1
        magnitude = sum(x * x for x in embedding) ** 0.5
        assert abs(magnitude - 1.0) < 0.01

    def test_similar_texts_have_high_similarity(self, cache_dir: Path) -> None:
        """Test that similar texts have high similarity."""
        service = EmbeddingService(cache_dir=cache_dir)

        emb1 = service.embed("The cat sat on the mat")
        emb2 = service.embed("A cat was sitting on the mat")
        emb3 = service.embed("Quantum physics is fascinating")

        sim_similar = service.similarity(emb1, emb2)
        sim_different = service.similarity(emb1, emb3)

        # Similar texts should have higher similarity
        assert sim_similar > sim_different
        assert sim_similar > 0.5  # Should be quite similar


# =============================================================================
# Test: Module Exports
# =============================================================================


class TestModuleExports:
    """Test module exports."""

    def test_all_exports_exist(self) -> None:
        """Test all __all__ exports exist."""
        import git_notes_memory.embedding as module

        for name in module.__all__:
            assert hasattr(module, name), f"Missing export: {name}"

    def test_embedding_service_exported(self) -> None:
        """Test EmbeddingService is exported."""
        from git_notes_memory.embedding import EmbeddingService

        assert EmbeddingService is not None

    def test_get_default_service_exported(self) -> None:
        """Test get_default_service is exported."""
        from git_notes_memory.embedding import get_default_service

        assert callable(get_default_service)
