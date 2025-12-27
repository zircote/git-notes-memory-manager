"""Memory recall and retrieval service.

Provides semantic search, memory retrieval, and hydration capabilities.
The service supports three hydration levels:
- SUMMARY: Only metadata and one-line summary (fastest)
- FULL: Complete note content
- FILES: Full content plus file snapshots at commit time

Memories can be searched semantically using vector similarity or filtered
by namespace and spec. The service also supports grouping memories by
spec into SpecContext objects for comprehensive context retrieval.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from typing import TYPE_CHECKING

from git_notes_memory.config import (
    TOKENS_PER_CHAR,
    Domain,
    get_project_index_path,
    get_user_index_path,
)
from git_notes_memory.exceptions import MemoryIndexError, RecallError
from git_notes_memory.models import (
    CommitInfo,
    HydratedMemory,
    HydrationLevel,
    Memory,
    MemoryResult,
    SpecContext,
)
from git_notes_memory.retrieval.config import HybridSearchConfig, SearchMode

if TYPE_CHECKING:
    from pathlib import Path

    from git_notes_memory.embedding import EmbeddingService
    from git_notes_memory.git_ops import GitOps
    from git_notes_memory.index import IndexService
    from git_notes_memory.index.hybrid_search import (
        HybridSearchEngine,
        HybridSearchResult,
    )

__all__ = [
    "RecallService",
    "get_default_service",
]

logger = logging.getLogger(__name__)


# =============================================================================
# RecallService
# =============================================================================


class RecallService:
    """Service for retrieving and hydrating memories.

    Provides semantic search, direct retrieval, and hydration of memories
    at different levels of detail. Supports filtering by namespace and spec,
    and can aggregate memories into SpecContext objects for comprehensive
    context retrieval.

    Attributes:
        index_path: Path to the SQLite index database.

    Examples:
        >>> service = RecallService()
        >>> results = service.search("how to handle authentication")
        >>> for r in results:
        ...     print(f"{r.id}: {r.summary} (distance: {r.distance:.4f})")

        >>> hydrated = service.hydrate(results[0], HydrationLevel.FULL)
        >>> print(hydrated.full_content)
    """

    def __init__(
        self,
        index_path: Path | None = None,
        *,
        index_service: IndexService | None = None,
        embedding_service: EmbeddingService | None = None,
        git_ops: GitOps | None = None,
        hybrid_config: HybridSearchConfig | None = None,
    ) -> None:
        """Initialize the recall service.

        Args:
            index_path: Path to the SQLite index database.
                Defaults to the XDG data directory's index.db.
            index_service: Optional pre-configured IndexService instance.
                If not provided, one will be created lazily.
            embedding_service: Optional pre-configured EmbeddingService instance.
                If not provided, one will be created lazily.
            git_ops: Optional pre-configured GitOps instance.
                If not provided, one will be created lazily.
            hybrid_config: Optional hybrid search configuration.
                If not provided, one will be created from environment variables.
        """
        # Use project-specific index for per-repository isolation
        self._index_path = index_path or get_project_index_path()
        self._index_service = index_service
        self._embedding_service = embedding_service
        self._git_ops = git_ops
        self._hybrid_config = hybrid_config
        # RES-M-001: Lock for thread-safe user index initialization
        self._user_index_lock = threading.Lock()
        self._user_index_service: IndexService | None = None
        # RET-H-002: Lazy-initialized hybrid search engine
        self._hybrid_engine: HybridSearchEngine | None = None
        self._hybrid_engine_lock = threading.Lock()

    @property
    def index_path(self) -> Path:
        """Get the index database path."""
        return self._index_path

    # -------------------------------------------------------------------------
    # Lazy-loaded Dependencies
    # -------------------------------------------------------------------------

    def _get_index(self) -> IndexService:
        """Get or create the IndexService instance."""
        if self._index_service is None:
            from git_notes_memory.index import IndexService

            self._index_service = IndexService(self._index_path)
            self._index_service.initialize()
        return self._index_service

    def _get_embedding(self) -> EmbeddingService:
        """Get or create the EmbeddingService instance."""
        if self._embedding_service is None:
            from git_notes_memory.embedding import get_default_service

            self._embedding_service = get_default_service()
        return self._embedding_service

    def _get_git_ops(self) -> GitOps:
        """Get or create the GitOps instance."""
        if self._git_ops is None:
            from git_notes_memory.git_ops import GitOps

            self._git_ops = GitOps()
        return self._git_ops

    def _get_user_git_ops(self) -> GitOps:
        """Get or create the user domain GitOps instance."""
        if not hasattr(self, "_user_git_ops") or self._user_git_ops is None:
            from git_notes_memory.git_ops import GitOps

            self._user_git_ops: GitOps | None = GitOps.for_domain(Domain.USER)
        return self._user_git_ops

    def _get_git_ops_for_memory(self, memory: Memory) -> GitOps:
        """Get the appropriate GitOps instance for a memory based on its domain.

        Args:
            memory: The memory to get GitOps for.

        Returns:
            GitOps instance for the memory's domain.
        """
        if memory.is_user_domain:
            return self._get_user_git_ops()
        return self._get_git_ops()

    def _get_hybrid_engine(self) -> HybridSearchEngine:
        """Get or create the HybridSearchEngine instance.

        RET-H-002: Thread-safe lazy initialization using double-checked locking.

        Returns:
            HybridSearchEngine configured for hybrid search.
        """
        # Fast path: return existing instance without lock
        if self._hybrid_engine is not None:
            return self._hybrid_engine

        # Slow path: acquire lock and create if still None
        with self._hybrid_engine_lock:
            if self._hybrid_engine is None:
                from git_notes_memory.index.hybrid_search import HybridSearchEngine

                # Get or create hybrid config
                config = self._hybrid_config or HybridSearchConfig.from_env()

                # Create embedding function from embedding service
                embedding_service = self._get_embedding()

                def embed_fn(text: str) -> list[float]:
                    return list(embedding_service.embed(text))

                # Get search engine from index service
                index = self._get_index()
                # Access internal search engine (guaranteed non-None after initialize())
                search_engine = index._search_engine
                if search_engine is None:
                    msg = "SearchEngine not initialized"
                    raise RecallError(msg, "Call index.initialize() first")

                self._hybrid_engine = HybridSearchEngine(
                    search_engine=search_engine,
                    embed_fn=embed_fn,
                    config=config,
                )
        return self._hybrid_engine

    @property
    def hybrid_config(self) -> HybridSearchConfig:
        """Get the hybrid search configuration."""
        if self._hybrid_config is None:
            self._hybrid_config = HybridSearchConfig.from_env()
        return self._hybrid_config

    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------

    def search(
        self,
        query: str,
        k: int = 10,
        *,
        namespace: str | None = None,
        spec: str | None = None,
        min_similarity: float | None = None,
        domain: Domain | None = None,
    ) -> list[MemoryResult]:
        """Search for memories semantically similar to the query.

        Uses vector similarity search to find memories with content
        similar to the query text.

        Args:
            query: The search query text.
            k: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            spec: Optional spec identifier to filter results.
            min_similarity: Minimum similarity threshold (0-1).
                Results with similarity below this are filtered out.
            domain: Optional domain filter. If None, searches both domains
                and merges results with project memories taking precedence
                at equal relevance.

        Returns:
            List of MemoryResult objects sorted by relevance (most similar first).

        Raises:
            RecallError: If the search operation fails.

        Examples:
            >>> results = service.search("authentication flow")
            >>> results = service.search("error handling", namespace="decisions")
            >>> results = service.search("api design", k=5, min_similarity=0.5)
            >>> results = service.search("global preferences", domain=Domain.USER)
        """
        if not query or not query.strip():
            return []

        try:
            # Generate embedding for the query
            embedding_service = self._get_embedding()
            query_embedding = embedding_service.embed(query)

            # Determine which domains to search
            if domain is not None:
                # Search a single domain
                raw_results = self._search_single_domain(
                    query_embedding=query_embedding,
                    domain=domain,
                    k=k,
                    namespace=namespace,
                    spec=spec,
                )
            else:
                # Search both domains and merge results
                raw_results = self._search_both_domains(
                    query_embedding=query_embedding,
                    k=k,
                    namespace=namespace,
                    spec=spec,
                )

            # Convert to MemoryResult and apply similarity filter
            results: list[MemoryResult] = []
            for memory, distance in raw_results:
                # Convert distance to similarity (assuming L2 distance)
                # For normalized vectors, similarity = 1 - (distance^2 / 2)
                # But sqlite-vec returns distance directly, so we use 1 / (1 + distance)
                similarity = 1.0 / (1.0 + distance) if distance >= 0 else 0.0

                if min_similarity is not None and similarity < min_similarity:
                    continue

                results.append(MemoryResult(memory=memory, distance=distance))

            logger.debug(
                "Search for '%s' returned %d results (k=%d, namespace=%s, spec=%s, domain=%s)",
                query[:50],
                len(results),
                k,
                namespace,
                spec,
                domain.value if domain else "all",
            )

            return results

        except Exception as e:
            raise RecallError(
                f"Search failed: {e}",
                "Check query text and try again",
            ) from e

    def search_hybrid(
        self,
        query: str,
        k: int = 10,
        *,
        mode: SearchMode | None = None,
        namespace: str | None = None,
        spec: str | None = None,
        domain: Domain | None = None,
    ) -> list[HybridSearchResult]:
        """Search for memories using hybrid vector + BM25 strategy with RRF fusion.

        RET-H-002: Uses Reciprocal Rank Fusion to combine vector similarity
        and BM25 text search results for improved retrieval accuracy.

        Args:
            query: The search query text.
            k: Maximum number of results to return.
            mode: Search mode. Options:
                - "hybrid": Combine vector and BM25 with RRF (default)
                - "vector": Vector search only
                - "bm25": BM25 text search only
            namespace: Optional namespace to filter results.
            spec: Optional specification to filter results.
            domain: Optional domain filter. Currently only supports project domain.
                User domain hybrid search is not yet supported.

        Returns:
            List of HybridSearchResult objects sorted by RRF score descending.

        Raises:
            RecallError: If the search operation fails.

        Examples:
            >>> results = service.search_hybrid("authentication flow")
            >>> for r in results:
            ...     print(f"[{r.rank}] {r.memory.summary} (RRF: {r.rrf_score:.4f})")
            ...     print(f"  Sources: {r.sources}")

            >>> # Vector-only mode
            >>> results = service.search_hybrid("API design", mode="vector")

            >>> # BM25-only mode
            >>> results = service.search_hybrid("PostgreSQL", mode="bm25")
        """
        if not query or not query.strip():
            return []

        try:

            # Get the hybrid search engine
            engine = self._get_hybrid_engine()

            # Perform hybrid search (currently project domain only)
            domain_str = domain.value if domain else None

            results = engine.search(
                query=query,
                limit=k,
                mode=mode,
                namespace=namespace,
                spec=spec,
                domain=domain_str,
            )

            logger.debug(
                "Hybrid search for '%s' returned %d results (k=%d, mode=%s, namespace=%s)",
                query[:50],
                len(results),
                k,
                mode or engine.config.mode,
                namespace,
            )

            return results

        except Exception as e:
            raise RecallError(
                f"Hybrid search failed: {e}",
                "Check query text and try again",
            ) from e

    def _search_single_domain(
        self,
        query_embedding: Sequence[float],
        domain: Domain,
        k: int,
        namespace: str | None,
        spec: str | None,
    ) -> list[tuple[Memory, float]]:
        """Search a single domain's index.

        Args:
            query_embedding: The query embedding vector.
            domain: The domain to search.
            k: Maximum number of results.
            namespace: Optional namespace filter.
            spec: Optional spec filter.

        Returns:
            List of (Memory, distance) tuples.
        """
        if domain == Domain.USER:
            # Use user index
            index = self._get_user_index()
        else:
            # Use project index
            index = self._get_index()

        return index.search_vector(
            query_embedding,
            k=k,
            namespace=namespace,
            spec=spec,
            domain=domain.value,
        )

    def _search_both_domains(
        self,
        query_embedding: Sequence[float],
        k: int,
        namespace: str | None,
        spec: str | None,
    ) -> list[tuple[Memory, float]]:
        """Search both project and user domains and merge results.

        Searches both indexes and merges results, with project memories
        taking precedence at equal relevance. Also deduplicates similar
        memories that appear in both domains.

        Args:
            query_embedding: The query embedding vector.
            k: Maximum number of results.
            namespace: Optional namespace filter.
            spec: Optional spec filter.

        Returns:
            List of (Memory, distance) tuples sorted by distance,
            with project results first at equal distance.
        """
        # Query both domains
        project_results = self._get_index().search_vector(
            query_embedding,
            k=k,
            namespace=namespace,
            spec=spec,
            domain=Domain.PROJECT.value,
        )

        # Get user index - may not exist if user has no memories
        try:
            user_index = self._get_user_index()
            user_results = user_index.search_vector(
                query_embedding,
                k=k,
                namespace=namespace,
                spec=spec,
                domain=Domain.USER.value,
            )
        except (OSError, RecallError, MemoryIndexError):
            # QUAL-HIGH-001: User index doesn't exist or is inaccessible
            user_results = []

        # Merge results, preferring project at equal distance
        # Sort key: (distance, is_user) so project (is_user=False) comes first
        merged = [(mem, dist, False) for mem, dist in project_results] + [
            (mem, dist, True) for mem, dist in user_results
        ]

        # Sort by distance, then by is_user (False/project before True/user)
        merged.sort(key=lambda x: (x[1], x[2]))

        # Deduplicate based on content similarity
        # Keep track of seen content hashes to avoid duplicates
        seen_summaries: set[str] = set()
        deduplicated: list[tuple[Memory, float]] = []

        for mem, dist, _ in merged:
            # Use summary as a quick proxy for content similarity
            # If we've seen a very similar summary, skip this memory
            summary_key = mem.summary.lower().strip()
            if summary_key not in seen_summaries:
                seen_summaries.add(summary_key)
                deduplicated.append((mem, dist))

            if len(deduplicated) >= k:
                break

        return deduplicated[:k]

    def _get_user_index(self) -> IndexService:
        """Get or create the user domain IndexService instance.

        RES-M-001: Thread-safe lazy initialization using double-checked locking.
        Prevents race condition where two threads could create separate instances.

        Returns:
            IndexService configured for the user domain.
        """
        # Fast path: return existing instance without lock
        if self._user_index_service is not None:
            return self._user_index_service

        # Slow path: acquire lock and create if still None
        with self._user_index_lock:
            # Double-check after acquiring lock
            if self._user_index_service is None:
                from git_notes_memory.index import IndexService

                user_index_path = get_user_index_path(ensure_exists=True)
                self._user_index_service = IndexService(user_index_path)
                self._user_index_service.initialize()
        return self._user_index_service

    def search_text(
        self,
        query: str,
        limit: int = 10,
        *,
        namespace: str | None = None,
        spec: str | None = None,
        domain: Domain | None = None,
    ) -> list[Memory]:
        """Search for memories using text matching (FTS5).

        Uses SQLite full-text search for exact or partial text matches.
        This is faster than semantic search but less flexible.

        Args:
            query: The search query text.
            limit: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            spec: Optional spec identifier to filter results.
            domain: Optional domain filter. If None, searches both domains
                and merges results with project memories first.

        Returns:
            List of Memory objects matching the query.

        Raises:
            RecallError: If the search operation fails.

        Examples:
            >>> memories = service.search_text("API endpoint")
            >>> memories = service.search_text("bug fix", namespace="decisions")
            >>> memories = service.search_text("preferences", domain=Domain.USER)
        """
        if not query or not query.strip():
            return []

        try:
            results: list[Memory]
            if domain is not None:
                # Search single domain
                if domain == Domain.USER:
                    index = self._get_user_index()
                else:
                    index = self._get_index()

                results = index.search_text(
                    query,
                    limit=limit,
                    namespace=namespace,
                    spec=spec,
                    domain=domain.value,
                )
            else:
                # Search both domains and merge
                project_results = self._get_index().search_text(
                    query,
                    limit=limit,
                    namespace=namespace,
                    spec=spec,
                    domain=Domain.PROJECT.value,
                )

                try:
                    user_index = self._get_user_index()
                    user_results = user_index.search_text(
                        query,
                        limit=limit,
                        namespace=namespace,
                        spec=spec,
                        domain=Domain.USER.value,
                    )
                except (OSError, RecallError, MemoryIndexError):
                    # QUAL-HIGH-001: User index doesn't exist or is inaccessible
                    user_results = []

                # Merge: project results first, then user, up to limit
                # Deduplicate by summary
                seen_summaries: set[str] = set()
                results = []

                for mem in project_results + user_results:
                    summary_key = mem.summary.lower().strip()
                    if summary_key not in seen_summaries:
                        seen_summaries.add(summary_key)
                        results.append(mem)
                    if len(results) >= limit:
                        break

            logger.debug(
                "Text search for '%s' returned %d results (domain=%s)",
                query[:50],
                len(results),
                domain.value if domain else "all",
            )

            return results

        except Exception as e:
            raise RecallError(
                f"Text search failed: {e}",
                "Check query text and try again",
            ) from e

    # -------------------------------------------------------------------------
    # Direct Retrieval
    # -------------------------------------------------------------------------

    def get(self, memory_id: str) -> Memory | None:
        """Retrieve a memory by its ID.

        Args:
            memory_id: The memory ID in format "namespace:commit_sha:index".

        Returns:
            The Memory object if found, None otherwise.

        Examples:
            >>> memory = service.get("decisions:abc123:0")
            >>> if memory:
            ...     print(memory.summary)
        """
        try:
            index = self._get_index()
            return index.get(memory_id)
        except Exception as e:
            logger.warning("Failed to get memory %s: %s", memory_id, e)
            return None

    def get_batch(self, memory_ids: Sequence[str]) -> list[Memory]:
        """Retrieve multiple memories by their IDs.

        Args:
            memory_ids: Sequence of memory IDs.

        Returns:
            List of found Memory objects. Missing memories are omitted.

        Examples:
            >>> memories = service.get_batch(
            ...     ["decisions:abc123:0", "learnings:def456:1"]
            ... )
        """
        if not memory_ids:
            return []

        try:
            index = self._get_index()
            return index.get_batch(memory_ids)
        except Exception as e:
            logger.warning("Failed to get batch memories: %s", e)
            return []

    def get_by_namespace(
        self,
        namespace: str,
        *,
        spec: str | None = None,
        limit: int | None = None,
        domain: Domain | None = None,
    ) -> list[Memory]:
        """Retrieve all memories in a namespace.

        Args:
            namespace: The namespace to retrieve from.
            spec: Optional spec identifier to filter results.
            limit: Maximum number of results to return.
            domain: Filter by domain. None searches both domains with
                project memories prioritized before user memories.

        Returns:
            List of Memory objects in the namespace.

        Examples:
            >>> decisions = service.get_by_namespace("decisions")
            >>> spec_learnings = service.get_by_namespace("learnings", spec="SPEC-001")
            >>> user_decisions = service.get_by_namespace(
            ...     "decisions", domain=Domain.USER
            ... )
        """
        try:
            if domain is not None:
                # Query single domain
                if domain == Domain.USER:
                    index = self._get_user_index()
                else:
                    index = self._get_index()
                return index.get_by_namespace(
                    namespace, spec=spec, limit=limit, domain=domain.value
                )
            else:
                # Query both domains and merge (project first)
                project_results = self._get_index().get_by_namespace(
                    namespace, spec=spec, limit=limit, domain=Domain.PROJECT.value
                )
                try:
                    user_results = self._get_user_index().get_by_namespace(
                        namespace, spec=spec, limit=limit, domain=Domain.USER.value
                    )
                except (OSError, RecallError, MemoryIndexError):
                    # QUAL-HIGH-001: User index doesn't exist or is inaccessible
                    user_results = []

                # Combine with project first, then user
                combined = list(project_results) + list(user_results)
                if limit:
                    combined = combined[:limit]
                return combined
        except Exception as e:
            logger.warning("Failed to get memories for namespace %s: %s", namespace, e)
            return []

    def get_by_spec(
        self,
        spec: str,
        *,
        namespace: str | None = None,
        limit: int | None = None,
    ) -> list[Memory]:
        """Retrieve all memories for a spec.

        Args:
            spec: The spec identifier (e.g., "SPEC-2025-12-18-001").
            namespace: Optional namespace to filter results.
            limit: Maximum number of results to return.

        Returns:
            List of Memory objects for the spec.

        Examples:
            >>> all_spec_memories = service.get_by_spec("SPEC-2025-12-18-001")
            >>> spec_decisions = service.get_by_spec("SPEC-001", namespace="decisions")
        """
        try:
            index = self._get_index()
            return index.get_by_spec(spec, namespace=namespace, limit=limit)
        except Exception as e:
            logger.warning("Failed to get memories for spec %s: %s", spec, e)
            return []

    def list_recent(
        self,
        limit: int = 10,
        *,
        namespace: str | None = None,
        spec: str | None = None,
    ) -> list[MemoryResult]:
        """List the most recent memories.

        Args:
            limit: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            spec: Optional spec identifier to filter results.

        Returns:
            List of MemoryResult objects sorted by creation time (newest first).
            Distance is set to 0.0 for recency-based results.

        Examples:
            >>> recent = service.list_recent(5)
            >>> recent_decisions = service.list_recent(10, namespace="decisions")
        """
        try:
            index = self._get_index()
            memories = index.list_recent(limit=limit, namespace=namespace, spec=spec)

            # Wrap in MemoryResult with zero distance (not a similarity search)
            return [MemoryResult(memory=m, distance=0.0) for m in memories]

        except Exception as e:
            logger.warning("Failed to list recent memories: %s", e)
            return []

    # -------------------------------------------------------------------------
    # Hydration
    # -------------------------------------------------------------------------

    def hydrate(
        self,
        memory_or_result: Memory | MemoryResult,
        level: HydrationLevel = HydrationLevel.SUMMARY,
    ) -> HydratedMemory:
        """Hydrate a memory to the specified level of detail.

        Hydration levels:
        - SUMMARY: Only the memory metadata (no additional loading)
        - FULL: Loads the complete note content from git
        - FILES: Loads content plus file snapshots at commit time

        Args:
            memory_or_result: The memory to hydrate. Can be a Memory or MemoryResult.
            level: The level of detail to hydrate to.

        Returns:
            A HydratedMemory object with the requested level of detail.

        Raises:
            RecallError: If hydration fails.

        Examples:
            >>> result = service.search("auth")[0]
            >>> hydrated = service.hydrate(result, HydrationLevel.FULL)
            >>> print(hydrated.full_content)

            >>> hydrated = service.hydrate(result, HydrationLevel.FILES)
            >>> for path, content in hydrated.files:
            ...     print(f"{path}: {len(content)} bytes")
        """
        # Normalize to MemoryResult
        if isinstance(memory_or_result, Memory):
            result = MemoryResult(memory=memory_or_result, distance=0.0)
        else:
            result = memory_or_result

        memory = result.memory

        # SUMMARY level - no additional loading needed
        if level == HydrationLevel.SUMMARY:
            return HydratedMemory(result=result)

        try:
            # Use domain-specific GitOps for the memory
            git_ops = self._get_git_ops_for_memory(memory)

            # FULL level - load note content
            full_content: str | None = None
            commit_info: CommitInfo | None = None

            if level.value >= HydrationLevel.FULL.value:
                # Get the full note content
                full_content = git_ops.show_note(
                    namespace=memory.namespace,
                    commit=memory.commit_sha,
                )

                # Get commit info
                try:
                    commit_info = git_ops.get_commit_info(memory.commit_sha)
                except Exception as e:
                    logger.debug(
                        "Failed to get commit info for %s: %s", memory.commit_sha, e
                    )

            # FILES level - also load file snapshots
            files: tuple[tuple[str, str], ...] = ()

            if level == HydrationLevel.FILES:
                files = self._load_files_at_commit(memory.commit_sha)

            return HydratedMemory(
                result=result,
                full_content=full_content,
                files=files,
                commit_info=commit_info,
            )

        except Exception as e:
            raise RecallError(
                f"Failed to hydrate memory {memory.id}: {e}",
                "Check that the git repository is accessible",
            ) from e

    def hydrate_batch(
        self,
        memories: Sequence[Memory | MemoryResult],
        level: HydrationLevel = HydrationLevel.SUMMARY,
    ) -> list[HydratedMemory]:
        """Hydrate multiple memories to the specified level.

        Uses batch git operations (PERF-003) for efficient retrieval when
        hydrating FULL or FILES level.

        Args:
            memories: Sequence of memories to hydrate.
            level: The level of detail to hydrate to.

        Returns:
            List of HydratedMemory objects.

        Examples:
            >>> results = service.search("auth")
            >>> hydrated = service.hydrate_batch(results, HydrationLevel.FULL)
        """
        if not memories:
            return []

        # SUMMARY level doesn't need git ops
        if level == HydrationLevel.SUMMARY:
            return [
                HydratedMemory(
                    result=(
                        MemoryResult(memory=m, distance=0.0)
                        if isinstance(m, Memory)
                        else m
                    )
                )
                for m in memories
            ]

        # Normalize to MemoryResult
        results: list[MemoryResult] = []
        for m in memories:
            if isinstance(m, Memory):
                results.append(MemoryResult(memory=m, distance=0.0))
            else:
                results.append(m)

        # PERF-003: Group memories by domain and namespace for batch git operations
        # Key: (domain, namespace) -> list of commit_shas
        domain_namespace_commits: dict[tuple[str, str], list[str]] = {}
        for r in results:
            key = (r.memory.domain, r.memory.namespace)
            if key not in domain_namespace_commits:
                domain_namespace_commits[key] = []
            if r.memory.commit_sha not in domain_namespace_commits[key]:
                domain_namespace_commits[key].append(r.memory.commit_sha)

        # Batch fetch note contents by (domain, namespace)
        # Key: (domain, namespace) -> {commit_sha -> content}
        note_contents: dict[tuple[str, str], dict[str, str | None]] = {}
        for (domain, ns), commit_shas in domain_namespace_commits.items():
            # Get the appropriate GitOps for this domain
            if domain == Domain.USER.value:
                git_ops = self._get_user_git_ops()
            else:
                git_ops = self._get_git_ops()
            note_contents[(domain, ns)] = git_ops.show_notes_batch(ns, commit_shas)

        # Build hydrated memories using cached contents
        hydrated: list[HydratedMemory] = []
        for r in results:
            memory = r.memory
            full_content: str | None = None
            commit_info: CommitInfo | None = None
            files: tuple[tuple[str, str], ...] = ()

            if level.value >= HydrationLevel.FULL.value:
                # Get from batch-fetched contents using (domain, namespace) key
                key = (memory.domain, memory.namespace)
                ns_contents = note_contents.get(key, {})
                full_content = ns_contents.get(memory.commit_sha)

                # Get commit info using domain-specific GitOps
                git_ops = self._get_git_ops_for_memory(memory)
                try:
                    commit_info = git_ops.get_commit_info(memory.commit_sha)
                except Exception as e:
                    logger.debug(
                        "Failed to get commit info for %s: %s", memory.commit_sha, e
                    )

            if level == HydrationLevel.FILES:
                files = self._load_files_at_commit_for_memory(memory)

            hydrated.append(
                HydratedMemory(
                    result=r,
                    full_content=full_content,
                    files=files,
                    commit_info=commit_info,
                )
            )

        return hydrated

    def _load_files_at_commit(self, commit_sha: str) -> tuple[tuple[str, str], ...]:
        """Load file snapshots at a specific commit (project domain).

        Args:
            commit_sha: The commit SHA to load files from.

        Returns:
            Tuple of (path, content) pairs for changed files.
        """
        return self._load_files_with_git_ops(commit_sha, self._get_git_ops())

    def _load_files_at_commit_for_memory(
        self, memory: Memory
    ) -> tuple[tuple[str, str], ...]:
        """Load file snapshots for a memory, using the correct domain GitOps.

        Args:
            memory: The memory to load files for.

        Returns:
            Tuple of (path, content) pairs for changed files.
        """
        git_ops = self._get_git_ops_for_memory(memory)
        return self._load_files_with_git_ops(memory.commit_sha, git_ops)

    # RES-M-005: Memory limits for file loading
    _MAX_FILES_PER_COMMIT = 50  # Maximum number of files to load per commit
    _MAX_FILE_SIZE_BYTES = 512 * 1024  # 512KB max per file
    _MAX_TOTAL_SIZE_BYTES = 5 * 1024 * 1024  # 5MB total max

    def _load_files_with_git_ops(
        self, commit_sha: str, git_ops: GitOps
    ) -> tuple[tuple[str, str], ...]:
        """Load file snapshots using a specific GitOps instance.

        RES-M-005: Applies memory limits to prevent exhaustion:
        - Maximum 50 files per commit
        - Maximum 512KB per individual file
        - Maximum 5MB total content loaded

        Args:
            commit_sha: The commit SHA to load files from.
            git_ops: The GitOps instance to use.

        Returns:
            Tuple of (path, content) pairs for changed files.
        """
        try:
            # Get list of changed files in the commit
            changed_files = git_ops.get_changed_files(commit_sha)

            # RES-M-005: Limit number of files to process
            if len(changed_files) > self._MAX_FILES_PER_COMMIT:
                logger.debug(
                    "Commit %s has %d files, limiting to %d",
                    commit_sha[:7],
                    len(changed_files),
                    self._MAX_FILES_PER_COMMIT,
                )
                changed_files = changed_files[: self._MAX_FILES_PER_COMMIT]

            # Load content for each file with size limits
            files: list[tuple[str, str]] = []
            total_size = 0
            for path in changed_files:
                try:
                    content = git_ops.get_file_at_commit(path, commit_sha)
                    if content is None:
                        continue

                    content_size = len(content.encode("utf-8", errors="replace"))

                    # RES-M-005: Skip files that are too large
                    if content_size > self._MAX_FILE_SIZE_BYTES:
                        logger.debug(
                            "Skipping large file %s (%d bytes > %d limit)",
                            path,
                            content_size,
                            self._MAX_FILE_SIZE_BYTES,
                        )
                        continue

                    # RES-M-005: Stop if total size limit exceeded
                    if total_size + content_size > self._MAX_TOTAL_SIZE_BYTES:
                        logger.debug(
                            "Total size limit reached (%d bytes), stopping file load",
                            total_size,
                        )
                        break

                    files.append((path, content))
                    total_size += content_size

                except Exception as e:
                    logger.debug(
                        "Failed to load file %s at %s: %s", path, commit_sha, e
                    )

            return tuple(files)

        except Exception as e:
            logger.debug("Failed to load files at commit %s: %s", commit_sha, e)
            return ()

    # -------------------------------------------------------------------------
    # Context Aggregation
    # -------------------------------------------------------------------------

    def get_spec_context(
        self,
        spec: str,
        *,
        hydration_level: HydrationLevel = HydrationLevel.SUMMARY,
    ) -> SpecContext:
        """Get aggregated context for a spec.

        Retrieves all memories for a spec and organizes them by namespace.
        Includes token estimation for LLM context window management.

        Args:
            spec: The spec identifier (e.g., "SPEC-2025-12-18-001").
            hydration_level: Level of detail for memory content.
                Only affects token estimation accuracy.

        Returns:
            A SpecContext object with all memories organized by namespace.

        Examples:
            >>> ctx = service.get_spec_context("SPEC-2025-12-18-001")
            >>> print(f"Total memories: {ctx.total_count}")
            >>> print(f"Token estimate: {ctx.token_estimate}")
            >>> for ns, memories in ctx.by_namespace.items():
            ...     print(f"{ns}: {len(memories)} memories")
        """
        try:
            # Get all memories for the spec
            memories = self.get_by_spec(spec)

            # Calculate token estimate
            token_estimate = self._estimate_tokens(memories, hydration_level)

            return SpecContext(
                spec=spec,
                memories=tuple(memories),
                total_count=len(memories),
                token_estimate=token_estimate,
            )

        except Exception as e:
            logger.warning("Failed to get spec context for %s: %s", spec, e)
            return SpecContext(spec=spec)

    def _estimate_tokens(
        self,
        memories: Sequence[Memory],
        level: HydrationLevel,
    ) -> int:
        """Estimate the number of tokens for a set of memories.

        Uses a simple character-based estimation: ~4 characters per token.
        PERF-006: Uses generator expression for single-pass calculation.

        Args:
            memories: Sequence of memories to estimate.
            level: The hydration level (affects what content is counted).

        Returns:
            Estimated token count.
        """
        include_content = level.value >= HydrationLevel.FULL.value

        # PERF-006: Single-pass generator avoids loop variable overhead
        total_chars = sum(
            len(m.summary)
            + (len(m.content) if include_content else 0)
            + 50  # Metadata overhead
            for m in memories
        )

        return int(total_chars * TOKENS_PER_CHAR)

    # -------------------------------------------------------------------------
    # Convenience Methods
    # -------------------------------------------------------------------------

    def recall_context(
        self,
        query: str,
        k: int = 5,
        *,
        namespace: str | None = None,
        hydration_level: HydrationLevel = HydrationLevel.SUMMARY,
    ) -> list[HydratedMemory]:
        """Search and hydrate memories in one operation.

        Convenience method that combines search and hydration.

        Args:
            query: The search query text.
            k: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            hydration_level: Level of detail for hydration.

        Returns:
            List of HydratedMemory objects sorted by relevance.

        Examples:
            >>> context = service.recall_context(
            ...     "how do we handle errors",
            ...     k=3,
            ...     hydration_level=HydrationLevel.FULL,
            ... )
            >>> for h in context:
            ...     print(h.result.summary)
        """
        results = self.search(query, k=k, namespace=namespace)
        return self.hydrate_batch(results, hydration_level)

    def recall_similar(
        self,
        memory: Memory,
        k: int = 5,
        *,
        exclude_self: bool = True,
    ) -> list[MemoryResult]:
        """Find memories similar to an existing memory.

        Args:
            memory: The reference memory to find similar items for.
            k: Maximum number of results to return.
            exclude_self: Whether to exclude the reference memory from results.

        Returns:
            List of similar MemoryResult objects.

        Examples:
            >>> memory = service.get("decisions:abc123:0")
            >>> similar = service.recall_similar(memory, k=3)
        """
        if not memory.content:
            return []

        # Search using the memory's content
        results = self.search(memory.content, k=k + 1 if exclude_self else k)

        # Optionally filter out the reference memory
        if exclude_self:
            results = [r for r in results if r.memory.id != memory.id][:k]

        return results

    # -------------------------------------------------------------------------
    # Domain-Specific Convenience Methods
    # -------------------------------------------------------------------------

    def search_user(
        self,
        query: str,
        k: int = 10,
        *,
        namespace: str | None = None,
        spec: str | None = None,
        min_similarity: float | None = None,
    ) -> list[MemoryResult]:
        """Search for memories in the user (global) domain only.

        Convenience method that wraps search() with domain=Domain.USER.
        User memories are global, cross-project memories stored in the
        user's data directory.

        Args:
            query: The search query text.
            k: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            spec: Optional spec identifier to filter results.
            min_similarity: Minimum similarity threshold (0-1).

        Returns:
            List of MemoryResult objects from the user domain.

        Examples:
            >>> results = service.search_user("my coding preferences")
            >>> results = service.search_user("terminal setup", namespace="learnings")
        """
        return self.search(
            query,
            k=k,
            namespace=namespace,
            spec=spec,
            min_similarity=min_similarity,
            domain=Domain.USER,
        )

    def search_project(
        self,
        query: str,
        k: int = 10,
        *,
        namespace: str | None = None,
        spec: str | None = None,
        min_similarity: float | None = None,
    ) -> list[MemoryResult]:
        """Search for memories in the project domain only.

        Convenience method that wraps search() with domain=Domain.PROJECT.
        Project memories are repository-scoped memories stored in git notes.

        Args:
            query: The search query text.
            k: Maximum number of results to return.
            namespace: Optional namespace to filter results.
            spec: Optional spec identifier to filter results.
            min_similarity: Minimum similarity threshold (0-1).

        Returns:
            List of MemoryResult objects from the project domain.

        Examples:
            >>> results = service.search_project("authentication flow")
            >>> results = service.search_project("API design", namespace="decisions")
        """
        return self.search(
            query,
            k=k,
            namespace=namespace,
            spec=spec,
            min_similarity=min_similarity,
            domain=Domain.PROJECT,
        )


# =============================================================================
# Singleton Access (using ServiceRegistry)
# =============================================================================


def get_default_service() -> RecallService:
    """Get the default recall service singleton.

    Returns:
        The default RecallService instance.

    Examples:
        >>> service = get_default_service()
        >>> results = service.search("authentication")
    """
    from git_notes_memory.registry import ServiceRegistry

    return ServiceRegistry.get(RecallService)
