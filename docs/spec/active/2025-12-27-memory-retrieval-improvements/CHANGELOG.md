# Changelog

All notable changes to this specification will be documented in this file.

## [1.0.0] - 2025-12-27

### Added
- Complete requirements specification (REQUIREMENTS.md)
  - 4 P0 requirements: Hybrid Search, Entity Indexing, Temporal Indexing, Query Expansion
  - 4 P1 requirements: Entity Boost, Mode Selection, Temporal Reasoning, Telemetry
  - 3 P2 requirements: Entity Autocomplete, Semantic Linking, Hierarchical Search
- Technical architecture design (ARCHITECTURE.md)
  - 5 new components: HybridSearchEngine, EntityExtractor, TemporalExtractor, QueryExpander, RRFFusionEngine
  - Schema v5 with entities, memory_entities, temporal_refs tables
  - Integration with existing SearchEngine and LLMClient
- Implementation plan with 5 phases, 21 tasks (IMPLEMENTATION_PLAN.md)
  - Phase 1: Foundation (schema + RRF)
  - Phase 2: Hybrid Search (BM25 + Vector fusion)
  - Phase 3: Entity Indexing (NER + entity boost)
  - Phase 4: Temporal Indexing (date parsing + filtering)
  - Phase 5: Query Expansion (LLM-powered)
- 10 Architecture Decision Records (DECISIONS.md)
  - ADR-001: RRF for fusion
  - ADR-002: Add deps to [consolidation] extra
  - ADR-003: Graceful degradation
  - ADR-004: Parallel search execution
  - ADR-005: Use FTS5 BM25
  - ADR-006: Entity extraction at capture time
  - ADR-007: Opt-in LLM expansion
  - ADR-008: Single SQLite database
  - ADR-009: Regex fallback for entities
  - ADR-010: dateparser for temporal

### Research Conducted
- Analyzed existing codebase: SearchEngine, SchemaManager, RecallService
- Reviewed benchmark harness GitNotesAdapter integration
- Researched RRF, spaCy NER, dateparser, hybrid search patterns

### Baseline
- Benchmark accuracy: 65% (13/20 questions)
- Target accuracy: 90%+ (18/20 questions)
