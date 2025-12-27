"""Embedding service for generating semantic vectors.

Uses sentence-transformers for generating text embeddings. The model is
lazily loaded on first use to avoid slow startup times.

The default model is 'all-MiniLM-L6-v2' which produces 384-dimensional vectors.
This can be overridden via the MEMORY_PLUGIN_EMBEDDING_MODEL environment variable.

Model files are cached in the XDG data directory (models/ subdirectory).

CRIT-001: Circuit breaker pattern prevents repeated calls to a failing model.
Timeout protection is applied to all encode() operations to prevent
indefinite hangs on GPU memory exhaustion or model corruption.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from git_notes_memory.config import (
    EMBEDDING_DIMENSIONS,
    get_embedding_model,
    get_models_path,
)
from git_notes_memory.exceptions import EmbeddingError

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

__all__ = [
    "EmbeddingService",
    "EmbeddingCircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    "get_default_service",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Timeout Constants (CRIT-001)
# =============================================================================

# Timeout for single embed() operations (seconds)
EMBED_TIMEOUT_SECONDS = 30.0

# Timeout for batch embed_batch() operations (seconds)
EMBED_BATCH_TIMEOUT_SECONDS = 120.0


# =============================================================================
# Circuit Breaker (CRIT-001)
# =============================================================================


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation, requests allowed
    OPEN = "open"  # Failures exceeded threshold, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitOpenError(EmbeddingError):
    """Raised when circuit breaker is open."""

    def __init__(self, state: CircuitState, failures: int, threshold: int) -> None:
        """Initialize circuit open error.

        Args:
            state: Current circuit state.
            failures: Current failure count.
            threshold: Failure threshold that triggered opening.
        """
        super().__init__(
            f"Embedding circuit breaker is {state.value} ({failures}/{threshold} failures)",
            "The embedding model may be in a bad state. Wait for recovery timeout or restart.",
        )
        self.circuit_state = state
        self.failures = failures
        self.threshold = threshold


@dataclass
class EmbeddingCircuitBreaker:
    """Circuit breaker for embedding service resilience.

    Prevents repeated calls to a failing embedding model by opening the circuit
    after a threshold of failures. After a recovery timeout, the circuit
    moves to half-open state to test if the model recovered.

    Thread Safety:
        All state mutations are protected by a lock for thread-safe operation.

    Attributes:
        failure_threshold: Number of failures before opening circuit.
        recovery_timeout_seconds: Seconds to wait before testing recovery.
        half_open_max_requests: Requests allowed in half-open state.
    """

    failure_threshold: int = 3
    recovery_timeout_seconds: float = 60.0
    half_open_max_requests: int = 1

    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _failure_count: int = field(default=0, repr=False)
    _success_count: int = field(default=0, repr=False)
    _last_failure_time: datetime | None = field(default=None, repr=False)
    _half_open_requests: int = field(default=0, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow_request(self) -> bool:
        """Check if a request should be allowed.

        Returns:
            True if request is allowed, False if circuit is open.
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                if self._last_failure_time is not None:
                    elapsed = (
                        datetime.now(UTC) - self._last_failure_time
                    ).total_seconds()
                    if elapsed >= self.recovery_timeout_seconds:
                        logger.info(
                            "Embedding circuit breaker recovery timeout elapsed (%.1fs), "
                            "transitioning to half-open",
                            elapsed,
                        )
                        self._state = CircuitState.HALF_OPEN
                        self._half_open_requests = 0
                        return True
                return False

            # Half-open state: allow limited requests to test recovery
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_requests < self.half_open_max_requests:
                    self._half_open_requests += 1
                    return True
                return False

            return True  # pragma: no cover

    def record_success(self) -> None:
        """Record a successful request.

        In half-open state, success closes the circuit.
        In closed state, resets failure count.
        """
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_requests:
                    logger.info(
                        "Embedding circuit breaker closing after successful recovery"
                    )
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request.

        In half-open state, failure reopens the circuit.
        In closed state, increments failure count and may open circuit.
        """
        with self._lock:
            self._last_failure_time = datetime.now(UTC)

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens circuit
                logger.warning(
                    "Embedding circuit breaker reopening after half-open failure"
                )
                self._state = CircuitState.OPEN
                self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    logger.warning(
                        "Embedding circuit breaker opening after %d failures",
                        self._failure_count,
                    )
                    self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            self._half_open_requests = 0

    def status(self) -> dict[str, object]:
        """Get circuit breaker status.

        Returns:
            Dict with state, failure count, and timing info.
        """
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_seconds": self.recovery_timeout_seconds,
                "last_failure_time": (
                    self._last_failure_time.isoformat()
                    if self._last_failure_time
                    else None
                ),
            }

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            return self._state


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
        circuit_breaker: EmbeddingCircuitBreaker | None = None,
    ) -> None:
        """Initialize the embedding service.

        Args:
            model_name: Name of the sentence-transformer model.
                Defaults to the configured model (all-MiniLM-L6-v2).
            cache_dir: Directory for caching model files.
                Defaults to the XDG data directory's models/ subdirectory.
            circuit_breaker: Optional circuit breaker for resilience.
                If None, a default circuit breaker is created (CRIT-001).
        """
        self._model_name = model_name or get_embedding_model()
        self._cache_dir = cache_dir or get_models_path()
        self._model: SentenceTransformer | None = None
        self._dimensions: int | None = None
        # CRIT-001: Circuit breaker to prevent repeated calls to failing model
        self._circuit_breaker = circuit_breaker or EmbeddingCircuitBreaker()

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

    @property
    def circuit_breaker(self) -> EmbeddingCircuitBreaker:
        """Get the circuit breaker instance."""
        return self._circuit_breaker

    def load(self) -> None:
        """Load the embedding model.

        This is called automatically on first use, but can be called
        explicitly to control when the model is loaded.

        Raises:
            EmbeddingError: If the model cannot be loaded.
        """
        if self._model is not None:
            return

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

            logger.info(
                "Loaded embedding model '%s' (%d dimensions)",
                self._model_name,
                self._dimensions,
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

    def warmup(self) -> float:
        """Pre-load model and warm up inference to avoid cold start latency.

        PERF-H-004: Call this at application startup to eliminate cold start
        delays on first actual embedding request. This loads the model and
        runs a small test embedding to trigger any JIT compilation.

        Returns:
            Time taken in seconds to warm up the model.

        Raises:
            EmbeddingError: If the model cannot be loaded.

        Examples:
            >>> service = EmbeddingService()
            >>> warmup_time = service.warmup()
            >>> print(f"Model ready in {warmup_time:.2f}s")
        """
        import time

        start = time.monotonic()

        # Load model if not already loaded
        self.load()

        # Run a small test embedding to trigger any JIT compilation
        assert self._model is not None
        self._model.encode("warmup", convert_to_numpy=True, normalize_embeddings=True)

        elapsed = time.monotonic() - start
        logger.info(
            "Embedding model warmed up in %.2fs (model: %s)",
            elapsed,
            self._model_name,
        )
        return elapsed

    def embed(self, text: str) -> list[float]:
        """Generate an embedding for a single text.

        CRIT-001: Uses circuit breaker and timeout to prevent repeated calls
        to a failing model and indefinite hangs.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            CircuitOpenError: If circuit breaker is open.
            EmbeddingError: If embedding generation fails or times out.

        Examples:
            >>> service = EmbeddingService()
            >>> embedding = service.embed("Hello, world!")
            >>> len(embedding)
            384
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.dimensions

        # CRIT-001: Check circuit breaker before attempting embedding
        if not self._circuit_breaker.allow_request():
            status = self._circuit_breaker.status()
            failure_count = status.get("failure_count", 0)
            failure_threshold = status.get("failure_threshold", 0)
            raise CircuitOpenError(
                state=self._circuit_breaker.state,
                failures=failure_count if isinstance(failure_count, int) else 0,
                threshold=failure_threshold
                if isinstance(failure_threshold, int)
                else 0,
            )

        self.load()

        try:
            assert self._model is not None  # For type checker
            model = self._model  # Capture for closure

            def _encode() -> list[float]:
                emb = model.encode(
                    text,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                result: list[float] = emb.tolist()
                return result

            # CRIT-001: Apply timeout to prevent indefinite hangs
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_encode)
                result = future.result(timeout=EMBED_TIMEOUT_SECONDS)

            # CRIT-001: Record success to close circuit breaker if in half-open
            self._circuit_breaker.record_success()
            return result

        except FuturesTimeoutError:
            # CRIT-001: Record failure to circuit breaker
            self._circuit_breaker.record_failure()
            raise EmbeddingError(
                f"Embedding timed out after {EMBED_TIMEOUT_SECONDS}s",
                "The model may be overloaded or GPU memory exhausted. Restart and retry.",
            ) from None
        except Exception as e:
            # CRIT-001: Record failure to circuit breaker
            self._circuit_breaker.record_failure()
            raise EmbeddingError(
                f"Failed to generate embedding: {e}",
                "Check input text and retry",
            ) from e

    def embed_batch(
        self,
        texts: Sequence[str],
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        CRIT-001: Uses circuit breaker and timeout to prevent repeated calls
        to a failing model and indefinite hangs.

        Args:
            texts: Sequence of texts to embed.
            batch_size: Number of texts to process in each batch.
            show_progress: Whether to show a progress bar.

        Returns:
            A list of embedding vectors, one per input text.

        Raises:
            CircuitOpenError: If circuit breaker is open.
            EmbeddingError: If embedding generation fails or times out.

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

        # CRIT-001: Check circuit breaker before attempting embedding
        if not self._circuit_breaker.allow_request():
            status = self._circuit_breaker.status()
            failure_count = status.get("failure_count", 0)
            failure_threshold = status.get("failure_threshold", 0)
            raise CircuitOpenError(
                state=self._circuit_breaker.state,
                failures=failure_count if isinstance(failure_count, int) else 0,
                threshold=failure_threshold
                if isinstance(failure_threshold, int)
                else 0,
            )

        self.load()
        dims = self.dimensions

        try:
            assert self._model is not None  # For type checker
            model = self._model  # Capture for closure

            def _encode_batch() -> list[list[float]]:
                embs = model.encode(
                    non_empty_texts,
                    batch_size=batch_size,
                    show_progress_bar=show_progress,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
                # Reconstruct the full result list
                res: list[list[float]] = [[0.0] * dims for _ in texts]
                for idx, emb in zip(non_empty_indices, embs, strict=True):
                    res[idx] = emb.tolist()
                return res

            # CRIT-001: Apply timeout to prevent indefinite hangs
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_encode_batch)
                result = future.result(timeout=EMBED_BATCH_TIMEOUT_SECONDS)

            # CRIT-001: Record success to close circuit breaker if in half-open
            self._circuit_breaker.record_success()
            return result

        except FuturesTimeoutError:
            # CRIT-001: Record failure to circuit breaker
            self._circuit_breaker.record_failure()
            raise EmbeddingError(
                f"Batch embedding timed out after {EMBED_BATCH_TIMEOUT_SECONDS}s",
                "The model may be overloaded or GPU memory exhausted. Reduce batch size or restart.",
            ) from None
        except Exception as e:
            # CRIT-001: Record failure to circuit breaker
            self._circuit_breaker.record_failure()
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
