# Research Plan: Git-Notes Memory Manager

## Research Classification
- **Primary Type:** CODEBASE + DOMAIN (hybrid)
- **Secondary:** TECHNICAL (LLM integration patterns)

## Research Questions

### Core Architecture
1. How does the git-notes storage mechanism work?
2. What is the progressive hydration model and its stages?
3. How do hooks intercept and capture memories?
4. What is the prompt injection mechanism for context loading?

### Theoretical Foundations
1. What cognitive science principles inform the memory design?
2. How does this relate to human memory systems (working/long-term)?
3. What is the novelty vs. existing RAG approaches?

### Novel Use Cases
1. How can git-native storage benefit LLM memory?
2. What patterns emerge from hooks-based capture?
3. How do Claude skills extend memory utility?

## Success Criteria
- [ ] Complete architecture documentation
- [ ] Theoretical framework articulation
- [ ] Novel use case identification (5+ distinct cases)
- [ ] Professional paper structure

## Investigation Plan

### Phase 2A: Codebase Deep Dive (Parallel Subagents)
1. **Core Services Analysis**: capture.py, recall.py, sync.py, index.py
2. **Hooks Subsystem**: All hook handlers, signal detection, context building
3. **Data Models**: Memory, HydrationLevel, CaptureSignal structures

### Phase 2B: Documentation Mining
1. ARCHITECTURE.md files in completed specs
2. DECISIONS.md (ADRs)
3. RETROSPECTIVE.md files for lessons learned

### Phase 2C: External Research
1. RAG literature comparison
2. Cognitive memory models
3. Git internals (notes refs)

## Estimated Scope
- **Complexity:** High
- **Files to analyze:** ~40 core files
- **Expected duration:** Comprehensive analysis

## Rabbit Holes to Avoid
- Implementation details of sqlite-vec (treat as black box)
- Deep git internals beyond notes refs
- Unrelated Claude Code plugin architecture
