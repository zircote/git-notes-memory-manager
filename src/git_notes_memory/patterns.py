"""Pattern detection and management for memory corpus analysis.

This module provides the PatternManager for detecting recurring patterns
across memories. It identifies:

- Success patterns: Things that worked well
- Anti-patterns: Things to avoid
- Workflow patterns: Process patterns
- Decision patterns: Decision-making patterns
- Technical patterns: Implementation patterns

Patterns progress through a lifecycle:
- CANDIDATE: Newly detected, needs validation
- VALIDATED: Confirmed by user or multiple occurrences
- PROMOTED: Actively suggested to users
- DEPRECATED: No longer relevant

The detection algorithm uses a combination of:
- Term frequency analysis for identifying common themes
- Semantic clustering for grouping similar memories
- Confidence scoring based on evidence strength
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from git_notes_memory.config import DECAY_HALF_LIFE_DAYS
from git_notes_memory.models import (
    Memory,
    Pattern,
    PatternStatus,
    PatternType,
)
from git_notes_memory.utils import calculate_temporal_decay

if TYPE_CHECKING:
    from collections.abc import Sequence

    from git_notes_memory.index import IndexService
    from git_notes_memory.recall import RecallService

__all__ = [
    "PatternManager",
    "PatternCandidate",
    "PatternDetectionResult",
    "get_default_manager",
]

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Minimum occurrences for a candidate pattern
MIN_OCCURRENCES_FOR_CANDIDATE = 2

# Minimum confidence for validation
MIN_CONFIDENCE_FOR_VALIDATION = 0.6

# Minimum occurrences for automatic promotion
MIN_OCCURRENCES_FOR_PROMOTION = 5

# MED-007: Extracted magic numbers to named constants for clarity
# Scoring weights for pattern confidence calculation
NORMALIZED_SCORE_WEIGHT = 0.6  # Weight for normalized score in confidence
OCCURRENCE_FACTOR_WEIGHT = 0.4  # Weight for occurrence factor in confidence
RECENCY_BOOST_FACTOR = 0.2  # Multiplier for recency boost

# Evidence and term importance scaling factors
EVIDENCE_IMPORTANCE_EXPONENT = 0.5  # Square root prevents evidence count dominance
TERM_BONUS_EXPONENT = 0.3  # Mild bonus for more terms

# Pattern promotion boost
EVIDENCE_PROMOTION_BOOST = 0.05  # Confidence boost per evidence

# Stop words for term analysis (common English words to filter)
STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "been",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "i",
        "we",
        "you",
        "they",
        "he",
        "she",
        "my",
        "our",
        "your",
        "their",
        "his",
        "her",
        "what",
        "which",
        "who",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "also",
        "now",
        "then",
        "here",
        "there",
        "about",
        "after",
        "before",
        "because",
        "if",
        "into",
        "through",
        "during",
        "while",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "once",
    }
)

# Pattern type keywords for classification
PATTERN_TYPE_KEYWORDS: dict[PatternType, frozenset[str]] = {
    PatternType.SUCCESS: frozenset(
        {
            "success",
            "successful",
            "worked",
            "solved",
            "fixed",
            "resolved",
            "improved",
            "better",
            "effective",
            "efficient",
            "optimal",
            "clean",
            "elegant",
        }
    ),
    PatternType.ANTI_PATTERN: frozenset(
        {
            "failed",
            "failure",
            "error",
            "bug",
            "issue",
            "problem",
            "mistake",
            "wrong",
            "avoid",
            "dont",
            "don't",
            "never",
            "bad",
            "poor",
            "broken",
            "complex",
            "complicated",
            "confusing",
        }
    ),
    PatternType.WORKFLOW: frozenset(
        {
            "process",
            "workflow",
            "step",
            "procedure",
            "approach",
            "method",
            "sequence",
            "order",
            "flow",
            "pipeline",
            "routine",
            "practice",
        }
    ),
    PatternType.DECISION: frozenset(
        {
            "decision",
            "decided",
            "chose",
            "choice",
            "selected",
            "option",
            "alternative",
            "tradeoff",
            "trade-off",
            "consider",
            "evaluate",
            "compare",
            "rationale",
            "reason",
            "because",
        }
    ),
    PatternType.TECHNICAL: frozenset(
        {
            "implementation",
            "architecture",
            "design",
            "pattern",
            "structure",
            "algorithm",
            "optimization",
            "performance",
            "scalability",
            "security",
            "api",
            "database",
            "cache",
            "queue",
        }
    ),
}

# Namespace to pattern type mapping hints
NAMESPACE_PATTERN_HINTS: dict[str, PatternType] = {
    "decisions": PatternType.DECISION,
    "learnings": PatternType.SUCCESS,
    "blockers": PatternType.ANTI_PATTERN,
    "reviews": PatternType.TECHNICAL,
    "progress": PatternType.WORKFLOW,
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class PatternCandidate:
    """A candidate pattern before promotion to full Pattern.

    Holds intermediate state during pattern detection before the candidate
    is confirmed or rejected.

    Attributes:
        name: Descriptive name derived from common terms.
        pattern_type: Inferred pattern classification.
        terms: Key terms that define this pattern.
        evidence_ids: Memory IDs that support this pattern.
        raw_score: Unnormalized score from detection algorithm.
        normalized_score: Score normalized to 0-1 range.
        recency_boost: Boost factor based on evidence recency.
    """

    name: str
    pattern_type: PatternType
    terms: tuple[str, ...]
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    raw_score: float = 0.0
    normalized_score: float = 0.0
    recency_boost: float = 0.0

    @property
    def occurrence_count(self) -> int:
        """Number of memories supporting this pattern."""
        return len(self.evidence_ids)

    def to_pattern(self, now: datetime | None = None) -> Pattern:
        """Convert to a full Pattern object.

        Args:
            now: Current timestamp. Defaults to UTC now.

        Returns:
            A Pattern object in CANDIDATE status.
        """
        if now is None:
            now = datetime.now(UTC)

        # Calculate confidence from normalized score and occurrence count
        occurrence_factor = min(
            1.0, self.occurrence_count / MIN_OCCURRENCES_FOR_PROMOTION
        )
        confidence = (
            self.normalized_score * NORMALIZED_SCORE_WEIGHT
            + occurrence_factor * OCCURRENCE_FACTOR_WEIGHT
        ) * (1.0 + self.recency_boost * RECENCY_BOOST_FACTOR)
        confidence = min(1.0, max(0.0, confidence))

        return Pattern(
            name=self.name,
            pattern_type=self.pattern_type,
            description=self._generate_description(),
            evidence=self.evidence_ids,
            confidence=confidence,
            tags=self.terms,
            status=PatternStatus.CANDIDATE,
            first_seen=now,
            last_seen=now,
            occurrence_count=self.occurrence_count,
        )

    def _generate_description(self) -> str:
        """Generate a description from pattern metadata."""
        type_name = self.pattern_type.value.replace("-", " ").title()
        terms_str = ", ".join(self.terms[:5])
        return f"{type_name} pattern identified from terms: {terms_str}"


@dataclass(frozen=True)
class PatternDetectionResult:
    """Result of a pattern detection run.

    Contains all detected patterns along with statistics about the
    detection process.

    Attributes:
        candidates: List of detected pattern candidates.
        memories_analyzed: Number of memories analyzed.
        terms_extracted: Total unique terms extracted.
        clusters_found: Number of semantic clusters identified.
        detection_time_ms: Time taken for detection in milliseconds.
    """

    candidates: tuple[PatternCandidate, ...]
    memories_analyzed: int = 0
    terms_extracted: int = 0
    clusters_found: int = 0
    detection_time_ms: float = 0.0

    @property
    def candidate_count(self) -> int:
        """Number of pattern candidates found."""
        return len(self.candidates)

    def get_by_type(self, pattern_type: PatternType) -> list[PatternCandidate]:
        """Filter candidates by pattern type.

        Args:
            pattern_type: The type to filter by.

        Returns:
            List of candidates matching the type.
        """
        return [c for c in self.candidates if c.pattern_type == pattern_type]


# =============================================================================
# PatternManager
# =============================================================================


class PatternManager:
    """Service for detecting and managing patterns across memories.

    The PatternManager analyzes the memory corpus to identify recurring
    patterns, which can be:
    - Success patterns: Things that worked well
    - Anti-patterns: Things to avoid
    - Workflow patterns: Process patterns
    - Decision patterns: Decision-making patterns
    - Technical patterns: Implementation patterns

    Detection uses term frequency analysis combined with semantic clustering.
    Patterns progress through a lifecycle from CANDIDATE to PROMOTED to
    DEPRECATED.

    Example:
        >>> manager = PatternManager()
        >>> result = manager.detect_patterns(memories)
        >>> for candidate in result.candidates:
        ...     print(f"{candidate.name}: {candidate.normalized_score:.2f}")

        >>> promoted = manager.get_promoted_patterns()
        >>> for pattern in promoted:
        ...     print(f"[{pattern.status.value}] {pattern.name}")
    """

    def __init__(
        self,
        *,
        index_service: IndexService | None = None,
        recall_service: RecallService | None = None,
    ) -> None:
        """Initialize the PatternManager.

        Args:
            index_service: Optional pre-configured IndexService.
            recall_service: Optional pre-configured RecallService.
        """
        self._index_service = index_service
        self._recall_service = recall_service
        self._patterns: dict[str, Pattern] = {}

    # -------------------------------------------------------------------------
    # Lazy-loaded Dependencies
    # -------------------------------------------------------------------------

    def _get_index(self) -> IndexService:
        """Get or create the IndexService instance."""
        if self._index_service is None:
            from git_notes_memory.index import IndexService

            self._index_service = IndexService()
            self._index_service.initialize()
        return self._index_service

    def _get_recall(self) -> RecallService:
        """Get or create the RecallService instance."""
        if self._recall_service is None:
            from git_notes_memory.recall import get_default_service

            self._recall_service = get_default_service()
        return self._recall_service

    # -------------------------------------------------------------------------
    # Pattern Detection
    # -------------------------------------------------------------------------

    def detect_patterns(
        self,
        memories: Sequence[Memory],
        *,
        min_occurrences: int = MIN_OCCURRENCES_FOR_CANDIDATE,
        max_candidates: int = 20,
    ) -> PatternDetectionResult:
        """Detect patterns in a set of memories.

        Analyzes the provided memories to identify recurring patterns using
        term frequency analysis. Patterns are classified by type and ranked
        by confidence.

        Args:
            memories: Sequence of memories to analyze.
            min_occurrences: Minimum occurrences for a pattern candidate.
            max_candidates: Maximum number of candidates to return.

        Returns:
            PatternDetectionResult with detected candidates and statistics.

        Example:
            >>> memories = recall_service.get_by_namespace("learnings")
            >>> result = manager.detect_patterns(memories)
            >>> print(f"Found {result.candidate_count} patterns")
        """
        import time

        start_time = time.perf_counter()

        if not memories:
            return PatternDetectionResult(
                candidates=(),
                memories_analyzed=0,
                terms_extracted=0,
                clusters_found=0,
                detection_time_ms=0.0,
            )

        # Step 1: Extract terms from all memories
        # QUAL-M-007: Use defaultdict type annotation for accuracy
        term_memory_map: defaultdict[str, set[str]] = defaultdict(set)
        memory_terms: dict[str, set[str]] = {}
        all_terms: set[str] = set()

        for memory in memories:
            terms = self._extract_terms(memory)
            memory_terms[memory.id] = terms
            all_terms.update(terms)

            for term in terms:
                term_memory_map[term].add(memory.id)

        # Step 2: Find term clusters (terms that co-occur frequently)
        clusters = self._find_term_clusters(term_memory_map, min_occurrences)

        # Step 3: Score and create candidates
        candidates: list[PatternCandidate] = []
        seen_evidence: set[frozenset[str]] = set()

        for cluster_terms, evidence_ids in clusters:
            # Deduplicate by evidence set
            evidence_key = frozenset(evidence_ids)
            if evidence_key in seen_evidence:
                continue
            seen_evidence.add(evidence_key)

            # Get representative memories for type classification
            memories_in_cluster = [m for m in memories if m.id in evidence_ids]
            pattern_type = self._classify_pattern_type(
                memories_in_cluster, cluster_terms
            )

            # Calculate raw score based on term significance
            raw_score = self._calculate_raw_score(
                cluster_terms, evidence_ids, term_memory_map, len(memories)
            )

            # Calculate recency boost
            recency_boost = self._calculate_recency_boost(memories_in_cluster)

            # Generate pattern name
            name = self._generate_pattern_name(cluster_terms, pattern_type)

            candidates.append(
                PatternCandidate(
                    name=name,
                    pattern_type=pattern_type,
                    terms=tuple(cluster_terms),
                    evidence_ids=tuple(evidence_ids),
                    raw_score=raw_score,
                    recency_boost=recency_boost,
                )
            )

        # Step 4: Normalize scores
        if candidates:
            max_score = max(c.raw_score for c in candidates)
            if max_score > 0:
                for candidate in candidates:
                    candidate.normalized_score = candidate.raw_score / max_score

        # Step 5: Sort by normalized score and limit
        candidates.sort(key=lambda c: c.normalized_score, reverse=True)
        candidates = candidates[:max_candidates]

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return PatternDetectionResult(
            candidates=tuple(candidates),
            memories_analyzed=len(memories),
            terms_extracted=len(all_terms),
            clusters_found=len(clusters),
            detection_time_ms=elapsed_ms,
        )

    def detect_from_namespace(
        self,
        namespace: str,
        *,
        spec: str | None = None,
        min_occurrences: int = MIN_OCCURRENCES_FOR_CANDIDATE,
    ) -> PatternDetectionResult:
        """Detect patterns from memories in a specific namespace.

        Convenience method that retrieves memories and runs detection.

        Args:
            namespace: The namespace to analyze.
            spec: Optional spec filter.
            min_occurrences: Minimum occurrences for candidates.

        Returns:
            PatternDetectionResult with detected candidates.
        """
        recall = self._get_recall()
        memories = recall.get_by_namespace(namespace, spec=spec)
        return self.detect_patterns(memories, min_occurrences=min_occurrences)

    def detect_all(
        self,
        *,
        spec: str | None = None,
        min_occurrences: int = MIN_OCCURRENCES_FOR_CANDIDATE,
    ) -> PatternDetectionResult:
        """Detect patterns across all memories.

        Args:
            spec: Optional spec filter.
            min_occurrences: Minimum occurrences for candidates.

        Returns:
            PatternDetectionResult with detected candidates.
        """
        index = self._get_index()
        if not index.is_initialized:
            index.initialize()

        # Get all memories
        memory_ids = index.get_all_ids()
        memories = index.get_batch(memory_ids)

        # Optionally filter by spec
        if spec is not None:
            memories = [m for m in memories if m.spec == spec]

        return self.detect_patterns(memories, min_occurrences=min_occurrences)

    # -------------------------------------------------------------------------
    # Term Extraction and Analysis
    # -------------------------------------------------------------------------

    def _extract_terms(self, memory: Memory) -> set[str]:
        """Extract significant terms from a memory.

        Combines summary, content, and tags to extract meaningful terms.
        Filters out stop words and short terms.

        Args:
            memory: The memory to extract terms from.

        Returns:
            Set of extracted terms.
        """
        # Combine text sources
        text_parts: list[str] = []

        if memory.summary:
            # Weight summary terms higher by including twice
            text_parts.append(memory.summary.lower())
            text_parts.append(memory.summary.lower())

        if memory.content:
            text_parts.append(memory.content.lower())

        if memory.tags:
            text_parts.extend(tag.lower() for tag in memory.tags)

        combined_text = " ".join(text_parts)

        # Tokenize and filter
        words = re.findall(r"\b[a-z][a-z0-9_-]*[a-z0-9]\b|\b[a-z]\b", combined_text)

        # Filter stop words and very short terms
        terms = {
            word
            for word in words
            if word not in STOP_WORDS and len(word) >= 2 and not word.isdigit()
        }

        return terms

    # Maximum terms to analyze to prevent O(n²) explosion in clustering
    MAX_TERMS_FOR_CLUSTERING: int = 100

    def _find_term_clusters(
        self,
        term_memory_map: dict[str, set[str]],
        min_occurrences: int,
    ) -> list[tuple[list[str], set[str]]]:
        """Find clusters of terms that co-occur frequently.

        Uses a simple co-occurrence algorithm to find term groups that
        appear together in multiple memories.

        To prevent O(n²) explosion with large vocabularies, only the top
        MAX_TERMS_FOR_CLUSTERING terms by occurrence count are analyzed.

        Args:
            term_memory_map: Mapping from terms to memory IDs.
            min_occurrences: Minimum co-occurrence count.

        Returns:
            List of (terms, memory_ids) tuples.
        """
        # Filter terms by minimum occurrence
        frequent_terms = {
            term: mem_ids
            for term, mem_ids in term_memory_map.items()
            if len(mem_ids) >= min_occurrences
        }

        if not frequent_terms:
            return []

        # Limit terms to top N by occurrence count to prevent O(n²) explosion
        # Sort by occurrence count (descending) and take top terms
        sorted_terms = sorted(
            frequent_terms.keys(),
            key=lambda t: len(frequent_terms[t]),
            reverse=True,
        )
        if len(sorted_terms) > self.MAX_TERMS_FOR_CLUSTERING:
            sorted_terms = sorted_terms[: self.MAX_TERMS_FOR_CLUSTERING]
            frequent_terms = {t: frequent_terms[t] for t in sorted_terms}

        # Find term pairs with high co-occurrence
        term_list = list(frequent_terms.keys())
        clusters: list[tuple[list[str], set[str]]] = []

        # Build clusters greedily
        used_terms: set[str] = set()

        for i, term1 in enumerate(term_list):
            if term1 in used_terms:
                continue

            mem_ids1 = frequent_terms[term1]
            cluster_terms = [term1]
            cluster_memories = set(mem_ids1)

            # Try to extend cluster with related terms
            for term2 in term_list[i + 1 :]:
                if term2 in used_terms:
                    continue

                mem_ids2 = frequent_terms[term2]

                # Check co-occurrence (Jaccard-like)
                intersection = cluster_memories & mem_ids2
                if len(intersection) >= min_occurrences:
                    # Term is related - add to cluster
                    cluster_terms.append(term2)
                    # Narrow cluster memories to co-occurring ones
                    cluster_memories = intersection

            # Only create cluster if we have multiple terms or strong evidence
            if len(cluster_terms) >= 2 or len(cluster_memories) >= min_occurrences:
                clusters.append((cluster_terms, cluster_memories))
                used_terms.update(cluster_terms)

        return clusters

    def _calculate_raw_score(
        self,
        terms: list[str],
        evidence_ids: set[str],
        term_memory_map: dict[str, set[str]],
        total_memories: int,
    ) -> float:
        """Calculate raw score for a pattern candidate.

        Score combines:
        - Term specificity (inverse document frequency)
        - Evidence count
        - Term count

        Args:
            terms: Pattern terms.
            evidence_ids: Memory IDs supporting the pattern.
            term_memory_map: Global term to memory mapping.
            total_memories: Total number of memories analyzed.

        Returns:
            Raw score (unnormalized).
        """
        import math

        if total_memories == 0:
            return 0.0

        # Calculate term specificity (TF-IDF inspired)
        specificity_sum = 0.0
        for term in terms:
            doc_freq = len(term_memory_map.get(term, set()))
            if doc_freq > 0:
                idf = math.log(total_memories / doc_freq)
                specificity_sum += idf

        avg_specificity = specificity_sum / len(terms) if terms else 0.0

        # Combine factors using named constants
        evidence_factor = len(evidence_ids) ** EVIDENCE_IMPORTANCE_EXPONENT
        term_factor = len(terms) ** TERM_BONUS_EXPONENT

        score: float = avg_specificity * evidence_factor * term_factor
        return score

    def _calculate_recency_boost(self, memories: Sequence[Memory]) -> float:
        """Calculate recency boost based on evidence memory timestamps.

        Args:
            memories: Memories to analyze.

        Returns:
            Boost factor 0.0 to 1.0 (1.0 = all recent).
        """
        if not memories:
            return 0.0

        decay_sum = 0.0

        for memory in memories:
            decay_sum += calculate_temporal_decay(
                memory.timestamp, DECAY_HALF_LIFE_DAYS
            )

        return decay_sum / len(memories)

    def _classify_pattern_type(
        self,
        memories: Sequence[Memory],
        terms: list[str],
    ) -> PatternType:
        """Classify the pattern type based on content and terms.

        Uses keyword matching and namespace hints to determine type.

        Args:
            memories: Memories in this pattern.
            terms: Pattern terms.

        Returns:
            Classified PatternType.
        """
        # Count type keywords in terms
        type_scores: Counter[PatternType] = Counter()
        term_set = set(terms)

        for pattern_type, keywords in PATTERN_TYPE_KEYWORDS.items():
            overlap = len(term_set & keywords)
            type_scores[pattern_type] = overlap

        # Add namespace hints
        for memory in memories:
            if memory.namespace in NAMESPACE_PATTERN_HINTS:
                type_scores[NAMESPACE_PATTERN_HINTS[memory.namespace]] += 1

        # Return highest scoring type, default to TECHNICAL
        if type_scores:
            top_type = type_scores.most_common(1)[0][0]
            if type_scores[top_type] > 0:
                return top_type

        return PatternType.TECHNICAL

    def _generate_pattern_name(
        self,
        terms: list[str],
        pattern_type: PatternType,
    ) -> str:
        """Generate a human-readable pattern name.

        Args:
            terms: Pattern terms.
            pattern_type: The pattern type.

        Returns:
            Generated name string.
        """
        # Take top 3 most significant terms
        top_terms = terms[:3]
        terms_str = " ".join(top_terms).title()

        type_label = pattern_type.value.replace("-", " ").title()

        return f"{terms_str} ({type_label})"

    # -------------------------------------------------------------------------
    # Pattern Lifecycle Management
    # -------------------------------------------------------------------------

    def register_pattern(self, pattern: Pattern) -> None:
        """Register a pattern in the manager's store.

        Args:
            pattern: The pattern to register.
        """
        self._patterns[pattern.name] = pattern
        logger.debug("Registered pattern: %s", pattern.name)

    def get_pattern(self, name: str) -> Pattern | None:
        """Get a pattern by name.

        Args:
            name: The pattern name.

        Returns:
            The Pattern if found, None otherwise.
        """
        return self._patterns.get(name)

    def list_patterns(
        self,
        *,
        status: PatternStatus | None = None,
        pattern_type: PatternType | None = None,
    ) -> list[Pattern]:
        """List patterns with optional filtering.

        Args:
            status: Optional status filter.
            pattern_type: Optional type filter.

        Returns:
            List of matching patterns.
        """
        result = list(self._patterns.values())

        if status is not None:
            result = [p for p in result if p.status == status]

        if pattern_type is not None:
            result = [p for p in result if p.pattern_type == pattern_type]

        # Sort by confidence descending
        result.sort(key=lambda p: p.confidence, reverse=True)

        return result

    def get_promoted_patterns(self) -> list[Pattern]:
        """Get all promoted patterns for active suggestion.

        Returns:
            List of patterns in PROMOTED status.
        """
        return self.list_patterns(status=PatternStatus.PROMOTED)

    def validate_pattern(self, name: str) -> Pattern | None:
        """Transition a pattern from CANDIDATE to VALIDATED.

        Args:
            name: The pattern name.

        Returns:
            Updated Pattern if found, None otherwise.
        """
        return self._transition_status(
            name,
            from_status=PatternStatus.CANDIDATE,
            to_status=PatternStatus.VALIDATED,
        )

    def promote_pattern(self, name: str) -> Pattern | None:
        """Transition a pattern from VALIDATED to PROMOTED.

        Args:
            name: The pattern name.

        Returns:
            Updated Pattern if found, None otherwise.
        """
        return self._transition_status(
            name,
            from_status=PatternStatus.VALIDATED,
            to_status=PatternStatus.PROMOTED,
        )

    def deprecate_pattern(self, name: str) -> Pattern | None:
        """Transition a pattern to DEPRECATED from any status.

        Args:
            name: The pattern name.

        Returns:
            Updated Pattern if found, None otherwise.
        """
        pattern = self._patterns.get(name)
        if pattern is None:
            return None

        # Create updated pattern with DEPRECATED status
        updated = Pattern(
            name=pattern.name,
            pattern_type=pattern.pattern_type,
            description=pattern.description,
            evidence=pattern.evidence,
            confidence=pattern.confidence,
            tags=pattern.tags,
            status=PatternStatus.DEPRECATED,
            first_seen=pattern.first_seen,
            last_seen=datetime.now(UTC),
            occurrence_count=pattern.occurrence_count,
        )

        self._patterns[name] = updated
        logger.info("Deprecated pattern: %s", name)
        return updated

    def _transition_status(
        self,
        name: str,
        *,
        from_status: PatternStatus,
        to_status: PatternStatus,
    ) -> Pattern | None:
        """Transition a pattern's status.

        Args:
            name: Pattern name.
            from_status: Required current status.
            to_status: New status.

        Returns:
            Updated Pattern if transition valid, None otherwise.
        """
        pattern = self._patterns.get(name)
        if pattern is None:
            logger.warning("Pattern not found for transition: %s", name)
            return None

        if pattern.status != from_status:
            logger.warning(
                "Pattern %s has status %s, expected %s for transition to %s",
                name,
                pattern.status.value,
                from_status.value,
                to_status.value,
            )
            return None

        # Create updated pattern
        updated = Pattern(
            name=pattern.name,
            pattern_type=pattern.pattern_type,
            description=pattern.description,
            evidence=pattern.evidence,
            confidence=pattern.confidence,
            tags=pattern.tags,
            status=to_status,
            first_seen=pattern.first_seen,
            last_seen=datetime.now(UTC),
            occurrence_count=pattern.occurrence_count,
        )

        self._patterns[name] = updated
        logger.info(
            "Transitioned pattern %s: %s -> %s",
            name,
            from_status.value,
            to_status.value,
        )
        return updated

    # -------------------------------------------------------------------------
    # Pattern Application
    # -------------------------------------------------------------------------

    def add_evidence(self, name: str, memory_id: str) -> Pattern | None:
        """Add new evidence to an existing pattern.

        Args:
            name: Pattern name.
            memory_id: Memory ID to add as evidence.

        Returns:
            Updated Pattern if found, None otherwise.
        """
        pattern = self._patterns.get(name)
        if pattern is None:
            return None

        if memory_id in pattern.evidence:
            return pattern  # Already present

        # Create updated pattern with new evidence
        new_evidence = pattern.evidence + (memory_id,)
        new_count = pattern.occurrence_count + 1

        # Recalculate confidence with more evidence
        new_confidence = min(
            1.0,
            pattern.confidence + EVIDENCE_PROMOTION_BOOST,
        )

        updated = Pattern(
            name=pattern.name,
            pattern_type=pattern.pattern_type,
            description=pattern.description,
            evidence=new_evidence,
            confidence=new_confidence,
            tags=pattern.tags,
            status=pattern.status,
            first_seen=pattern.first_seen,
            last_seen=datetime.now(UTC),
            occurrence_count=new_count,
        )

        self._patterns[name] = updated
        logger.debug("Added evidence to pattern %s: %s", name, memory_id)

        # Auto-validate if enough occurrences
        if (
            updated.status == PatternStatus.CANDIDATE
            and updated.confidence >= MIN_CONFIDENCE_FOR_VALIDATION
        ):
            logger.info(
                "Auto-validating pattern %s (confidence: %.2f)",
                name,
                updated.confidence,
            )
            return self.validate_pattern(name)

        return updated

    def find_matching_patterns(
        self,
        memory: Memory,
        *,
        min_term_overlap: int = 2,
    ) -> list[tuple[Pattern, float]]:
        """Find patterns that match a memory.

        Args:
            memory: The memory to match against.
            min_term_overlap: Minimum overlapping terms for a match.

        Returns:
            List of (Pattern, match_score) tuples sorted by score.
        """
        memory_terms = self._extract_terms(memory)
        matches: list[tuple[Pattern, float]] = []

        for pattern in self._patterns.values():
            if pattern.status == PatternStatus.DEPRECATED:
                continue

            pattern_terms = set(pattern.tags)
            overlap = memory_terms & pattern_terms

            if len(overlap) >= min_term_overlap:
                # Calculate match score based on overlap ratio
                max_terms = max(len(memory_terms), len(pattern_terms))
                match_score = len(overlap) / max_terms if max_terms > 0 else 0.0
                matches.append((pattern, match_score))

        # Sort by match score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches


# =============================================================================
# Singleton Instance
# =============================================================================


_manager: PatternManager | None = None


def get_default_manager() -> PatternManager:
    """Get the default PatternManager singleton.

    Returns:
        The default PatternManager instance.

    Example:
        >>> manager = get_default_manager()
        >>> result = manager.detect_all()
    """
    global _manager
    if _manager is None:
        _manager = PatternManager()
    return _manager
