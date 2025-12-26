"""Embedding service for generating semantic vectors.

Uses sentence-transformers for generating text embeddings. The model is
lazily loaded on first use to avoid slow startup times.

The default model is 'all-MiniLM-L6-v2' which produces 384-dimensional vectors.
This can be overridden via the MEMORY_PLUGIN_EMBEDDING_MODEL environment variable.

Model files are cached in the XDG data directory (models/ subdirectory).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from git_notes_memory.config import (
    EMBEDDING_DIMENSIONS,
    get_embedding_model,
    get_models_path,
)
from git_notes_memory.exceptions import EmbeddingError
from git_notes_memory.observability.decorators import measure_duration
from git_notes_memory.observability.metrics import get_metrics
from git_notes_memory.observability.tracing import trace_operation

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

__all__ = [
    "EmbeddingService",
    "get_default_service",
]

logger = logging.getLogger(__name__)


# =============================================================================
# EmbeddingService
# =============================================================================


class EmbeddingService:
    """Service for generating text embeddings using sentence-transformers.

    The model is lazily loaded on first use. This avoids slow startup times
    when the embedding service isn't immediately needed.

    Attributes:
        model_name: Name of the sentence-transformer model.
        cache_dir: Directory for caching model files.
        dimensions: Number of dimensions in the output vectors.

    Examples:
        >>> service = EmbeddingService()
        >>> embedding = service.embed("Hello, world!")
        >>> len(embedding)
        384

        >>> embeddings = service.embed_batch(["Hello", "World"])
        >>> len(embeddings)
        2
    """

    def __init__(
        self,
        model_name: str | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        """Initialize the embedding service.

        Args:
            model_name: Name of the sentence-transformer model.
                Defaults to the configured model (all-MiniLM-L6-v2).
            cache_dir: Directory for caching model files.
                Defaults to the XDG data directory's models/ subdirectory.
        """
        self._model_name = model_name or get_embedding_model()
        self._cache_dir = cache_dir or get_models_path()
        self._model: SentenceTransformer | None = None
        self._dimensions: int | None = None

    @property
    def model_name(self) -> str:
        """Get the model name."""
        return self._model_name

    @property
    def cache_dir(self) -> Path:
        """Get the cache directory."""
        return self._cache_dir

    @property
    def dimensions(self) -> int:
        """Get the embedding dimensions.

        Returns the configured dimensions without loading the model.
        The actual model dimensions are verified on first use.
        """
        if self._dimensions is not None:
            return self._dimensions
        return EMBEDDING_DIMENSIONS

    @property
    def is_loaded(self) -> bool:
        """Check if the model has been loaded."""
        return self._model is not None

    def load(self) -> None:
        """Load the embedding model.

        This is called automatically on first use, but can be called
        explicitly to control when the model is loaded.

        Raises:
            EmbeddingError: If the model cannot be loaded.
        """
        if self._model is not None:
            return

        metrics = get_metrics()
        start_time = time.perf_counter()

        with trace_operation("embedding.load", labels={"model": self._model_name}):
            try:
                # Import here to defer the heavy import
                from sentence_transformers import SentenceTransformer

                # Ensure cache directory exists
                self._cache_dir.mkdir(parents=True, exist_ok=True)

                # Set environment variable for transformers cache
                # This ensures the model is cached in our directory
                os.environ.setdefault(
                    "TRANSFORMERS_CACHE",
                    str(self._cache_dir),
                )
                os.environ.setdefault(
                    "HF_HOME",
                    str(self._cache_dir),
                )

                logger.info(
                    "Loading embedding model '%s' (cache: %s)",
                    self._model_name,
                    self._cache_dir,
                )

                self._model = SentenceTransformer(
                    self._model_name,
                    cache_folder=str(self._cache_dir),
                )

                # Verify and cache the actual dimensions
                self._dimensions = self._model.get_sentence_embedding_dimension()

                # Record model load time as a gauge
                load_time_ms = (time.perf_counter() - start_time) * 1000
                metrics.set_gauge(
                    "embedding_model_load_time_ms",
                    load_time_ms,
                    labels={"model": self._model_name},
                )
                metrics.increment("embedding_model_loads_total")

                logger.info(
                    "Loaded embedding model '%s' (%d dimensions) in %.1fms",
                    self._model_name,
                    self._dimensions,
                    load_time_ms,
                )

            except MemoryError as e:
                raise EmbeddingError(
                    "Insufficient memory to load embedding model",
                    "Close other applications or use a smaller model",
                ) from e
            except OSError as e:
                if "corrupt" in str(e).lower() or "invalid" in str(e).lower():
                    raise EmbeddingError(
                        "Embedding model cache corrupted",
                        f"Delete the {self._cache_dir} directory and retry",
                    ) from e
                raise EmbeddingError(
                    f"Failed to load embedding model: {e}",
                    "Check network connectivity and retry",
                ) from e
            except Exception as e:
                raise EmbeddingError(
                    f"Failed to load embedding model '{self._model_name}': {e}",
                    "Check model name and network connectivity",
                ) from e

    @measure_duration("embedding_generate")
    def embed(self, text: str) -> list[float]:
        """Generate an embedding for a single text.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            EmbeddingError: If embedding generation fails.

        Examples:
            >>> service = EmbeddingService()
            >>> embedding = service.embed("Hello, world!")
            >>> len(embedding)
            384
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.dimensions

        self.load()

        metrics = get_metrics()

        with trace_operation("embedding.generate"):
            try:
                assert self._model is not None  # For type checker
                embedding = self._model.encode(
                    text,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                result: list[float] = embedding.tolist()

                metrics.increment("embeddings_generated_total")

                return result

            except Exception as e:
                raise EmbeddingError(
                    f"Failed to generate embedding: {e}",
                    "Check input text and retry",
                ) from e

    @measure_duration("embedding_generate_batch")
    def embed_batch(
        self,
        texts: Sequence[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: Sequence of texts to embed.
            batch_size: Number of texts to process in each batch.
            show_progress: Whether to show a progress bar.

        Returns:
            A list of embedding vectors, one per input text.

        Raises:
            EmbeddingError: If embedding generation fails.

        Examples:
            >>> service = EmbeddingService()
            >>> embeddings = service.embed_batch(["Hello", "World"])
            >>> len(embeddings)
            2
            >>> all(len(e) == 384 for e in embeddings)
            True
        """
        if not texts:
            return []

        # Handle empty strings by tracking their positions
        non_empty_indices: list[int] = []
        non_empty_texts: list[str] = []

        for i, text in enumerate(texts):
            if text and text.strip():
                non_empty_indices.append(i)
                non_empty_texts.append(text)

        # If all texts are empty, return zero vectors
        if not non_empty_texts:
            return [[0.0] * self.dimensions for _ in texts]

        self.load()

        metrics = get_metrics()

        with trace_operation(
            "embedding.generate_batch", labels={"batch_size": str(len(texts))}
        ):
            try:
                assert self._model is not None  # For type checker
                embeddings = self._model.encode(
                    non_empty_texts,
                    batch_size=batch_size,
                    show_progress_bar=show_progress,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )

                # Reconstruct the full result list
                result: list[list[float]] = [[0.0] * self.dimensions for _ in texts]
                for i, embedding in zip(non_empty_indices, embeddings, strict=True):
                    result[i] = embedding.tolist()

                metrics.increment(
                    "embeddings_generated_total", amount=float(len(non_empty_texts))
                )

                return result

            except Exception as e:
                raise EmbeddingError(
                    f"Failed to generate batch embeddings: {e}",
                    "Check input texts and retry",
                ) from e

    def similarity(
        self, embedding1: Sequence[float], embedding2: Sequence[float]
    ) -> float:
        """Calculate cosine similarity between two embeddings.

        Since embeddings are normalized, this is just the dot product.

        Args:
            embedding1: First embedding vector.
            embedding2: Second embedding vector.

        Returns:
            Cosine similarity score between -1 and 1.

        Raises:
            ValueError: If embeddings have different dimensions.
        """
        if len(embedding1) != len(embedding2):
            raise ValueError(
                f"Embedding dimensions must match: {len(embedding1)} != {len(embedding2)}"
            )

        # Dot product of normalized vectors = cosine similarity
        return sum(a * b for a, b in zip(embedding1, embedding2, strict=True))

    def prewarm(self) -> bool:
        """Pre-warm the embedding model by loading it eagerly.

        PERF-004: Call this during application startup or hook initialization
        to avoid cold start latency on first embed() call. Useful for:
        - Session start hooks that need fast response
        - Background workers that will process embeddings
        - Applications where predictable latency is important

        Returns:
            True if model was loaded (or already loaded), False on error.

        Examples:
            >>> service = EmbeddingService()
            >>> service.prewarm()  # Load model in background
            True
            >>> service.is_loaded
            True
        """
        try:
            self.load()
            return True
        except Exception as e:
            # Use error level for prewarm failures - these indicate configuration
            # issues (missing dependencies, permissions) that users should see
            logger.error("Failed to pre-warm embedding model: %s", e, exc_info=True)
            return False

    def unload(self) -> None:
        """Unload the model to free memory.

        After calling this, the model will be reloaded on next use.
        """
        if self._model is not None:
            logger.info("Unloading embedding model '%s'", self._model_name)
            self._model = None
            # Keep _dimensions cached to avoid reloading just for that


# =============================================================================
# Singleton Access (using ServiceRegistry)
# =============================================================================


def get_default_service() -> EmbeddingService:
    """Get the default embedding service singleton.

    Returns:
        The default EmbeddingService instance.

    Examples:
        >>> service = get_default_service()
        >>> service.model_name
        'all-MiniLM-L6-v2'
    """
    from git_notes_memory.registry import ServiceRegistry

    return ServiceRegistry.get(EmbeddingService)
