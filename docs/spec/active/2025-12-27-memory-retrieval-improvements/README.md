---
project_id: SPEC-2025-12-27-002
project_name: "Memory Retrieval Performance Improvements"
slug: memory-retrieval-improvements
status: in-progress
created: 2025-12-27T18:00:00Z
approved: 2025-12-27T19:00:00Z
started: 2025-12-27T19:00:00Z
completed: null
expires: 2026-03-27T18:00:00Z
superseded_by: null
tags: [retrieval, search, indexing, performance, bm25, vector, llm]
stakeholders: []
benchmark_baseline: 65%
benchmark_target: 90%+
phases: 5
tasks: 21
adrs: 10
---

# Memory Retrieval Performance Improvements

## Overview

Improve memory retrieval accuracy from the current 65% benchmark score to 90%+ through advanced indexing, hybrid search, and LLM-assisted query expansion.

## Problem Statement

Current memory-benchmark-harness validation shows:
- **Baseline (no-memory)**: 0/20 correct (0%)
- **git-notes-memory**: 13/20 correct (65%)
- **Gap**: 7 questions failing completely

The current vector-only search with sentence-transformers (all-MiniLM-L6-v2) lacks:
1. Named entity awareness for specific queries
2. Keyword matching for exact terms
3. Temporal reasoning for date-based questions
4. Query understanding and expansion

## Proposed Solutions

1. **Entity-Aware Indexing**: Extract and index named entities (people, projects, technologies)
2. **Hybrid Search (BM25 + Vector)**: Combine keyword and semantic search
3. **Hierarchical Summaries**: Leverage consolidation for entity-centric summaries
4. **Temporal Indexing**: Parse and normalize dates in memories
5. **Query Expansion with LLM**: Expand queries before search

## Key Documents

- [REQUIREMENTS.md](./REQUIREMENTS.md) - Product Requirements Document
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Technical Design
- [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) - Phased Task Breakdown
- [DECISIONS.md](./DECISIONS.md) - Architecture Decision Records
- [RESEARCH_NOTES.md](./RESEARCH_NOTES.md) - Research Findings

## Related Work

- Previous spec: `docs/spec/completed/2025-12-25-llm-subconsciousness/` (LLM integration)
- Related spec: `docs/spec/active/2025-12-27-memory-consolidation/` (consolidation pipeline)
