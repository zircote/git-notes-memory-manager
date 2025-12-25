# Memory Subconscious Architecture

## PRD/Brief for git-notes-memory Evolution

**Version:** 0.1  
**Date:** December 2024  
**Status:** Research & Conceptual Validation

---

## Executive Summary

This document provides architectural guidance, theoretical foundations, and research validation for evolving **git-notes-memory** into a "memory subconscious" system—a cognitive layer that acts as an intelligent intermediary between raw memory storage and the consuming agent (e.g., Claude Code).

The concept is **architecturally sound** and draws from well-established research in cognitive science, AI safety, and LLM agent design. This document synthesizes the relevant prior art to inform implementation decisions.

---

## 1. Concept Validation

### 1.1 Is This a Valid Architectural Pattern?

**Yes.** The concept aligns with multiple established paradigms:

| Paradigm                     | Alignment | Key Insight                                                          |
| ---------------------------- | --------- | -------------------------------------------------------------------- |
| **Dual-Process Theory**      | Strong    | System 1 (fast recall) + System 2 (deliberate enrichment/skepticism) |
| **Cognitive Architectures**  | Strong    | SOAR, ACT-R separate declarative memory from procedural processing   |
| **MemGPT / Letta**           | Direct    | Explicitly supports "conscious" and "subconscious" agent threads     |
| **Multi-Agent Verification** | Strong    | N-Critics, debate frameworks for hallucination reduction             |

### 1.2 Key Differentiator

Most memory systems are **passive stores**. Your proposed system is an **active cognitive layer** that:

1. **Enriches** incoming memories (tagging, entity extraction, relationship mapping)
2. **Validates** outgoing recalls (confidence scoring, contradiction detection)
3. **Defends** against adversarial conditions (injection detection, provenance tracking)

This positions it as a **metacognitive module**—a component that reasons _about_ memory rather than just storing it.

---

## 2. Theoretical Foundations

### 2.1 Dual-Process Theory (Kahneman)

The foundational framework from cognitive psychology:

- **System 1:** Fast, intuitive, automatic (pattern matching, recall)
- **System 2:** Slow, deliberate, analytical (verification, enrichment)

**Application to Memory Subconscious:**

| System   | Role in Memory Subconscious                                    |
| -------- | -------------------------------------------------------------- |
| System 1 | Fast semantic search via embeddings, immediate recall          |
| System 2 | Confidence scoring, adversarial detection, enrichment pipeline |

**Key Research:**

- Kahneman, D. (2011). _Thinking, Fast and Slow_
- Brady et al. (2025). "Dual-process theory and decision-making in large language models" - _Nature Reviews Psychology_
- Booch et al. (2021). "SOFAI: Slow and Fast AI" architecture

### 2.2 Cognitive Architectures (SOAR, ACT-R, CLARION)

These 40+ year-old architectures provide blueprints for memory organization:

**SOAR Memory Model:**

- **Procedural Memory:** Production rules (how to do things)
- **Semantic Memory:** General facts
- **Episodic Memory:** Specific events/experiences
- **Working Memory:** Active context

**ACT-R Contributions:**

- **Base-Level Activation (BLA):** Memories have "activation" scores based on recency and frequency
- **Spreading Activation:** Related memories prime each other
- **Metadata is architectural:** Not visible to the agent, only influences retrieval

**Application:** Your namespace system (decisions, learnings, patterns, etc.) maps well to this memory taxonomy. The "reinforcement score" concept aligns with ACT-R's activation mechanism.

**Key Research:**

- Laird, J.E. (2022). "An Analysis and Comparison of ACT-R and Soar" - _arXiv:2201.09305_
- Laird, J.E. (2022). "Introduction to the Soar Cognitive Architecture" - _arXiv:2205.03854_
- Anderson, J.R. (1983). _The Architecture of Cognition_

### 2.3 Metacognition and "Feeling of Knowing"

Critical concept from cognitive science: the ability to **evaluate one's own knowledge**.

**The "Feeling of Knowing" process:**

- Rapidly assesses whether an answer is likely retrievable
- Routes to fast recall vs. deliberate reasoning
- When this fails → cognitive biases emerge

**Application:** The subconscious should implement a confidence estimation mechanism that:

1. Assesses retrieval quality before surfacing to the conscious agent
2. Flags low-confidence or contradictory results
3. Triggers deeper verification when uncertainty is high

**Key Research:**

- Posner, I. "Robots Thinking Fast and Slow" - Oxford Robotics Institute
- Fabiano et al. (2023). SOFAI metacognitive governance

---

## 3. Prior Art: LLM Memory Systems

### 3.1 MemGPT / Letta Framework

**Paper:** Packer et al. (2023). "MemGPT: Towards LLMs as Operating Systems" - _arXiv:2310.08560_

**Core Concepts:**

- Virtual context management (analogous to OS virtual memory)
- Main context (RAM) vs. External context (disk)
- Self-editing memory with archival storage
- Function calls to manage memory operations

**Directly Relevant Quote from Letta docs:**

> "The Letta framework also allows you to make agent architectures beyond MemGPT that differ significantly... for example, agents with multiple logical threads (e.g., a 'conscious' and a 'subconscious'), or agents with more advanced memory types."

**Implication:** The Letta team has explicitly identified this pattern as a valid architectural direction.

### 3.2 A-MEM (Agentic Memory)

**Paper:** Xu et al. (2025). "A-MEM: Agentic Memory for LLM Agents" - _arXiv:2502.12110_

**Key Innovation:** Zettelkasten-inspired memory organization

- Atomic notes with structured attributes
- Dynamic indexing and linking
- Memory evolution: new memories trigger updates to existing ones

**Performance:** Outperforms MemGPT on multi-hop reasoning tasks (F1: 3.45 vs 1.18)

**Relevance:** The enrichment/linking phase of your subconscious could adopt Zettelkasten principles.

### 3.3 mem0

**Repository:** github.com/mem0ai/mem0

**Approach:**

- Universal memory layer across LLM providers
- Automatic memory extraction from conversations
- User-scoped and session-scoped memory

**Limitation:** Lacks adversarial detection and confidence scoring—your differentiator.

### 3.4 cognee

**Repository:** github.com/topoteretes/cognee

**Approach:**

- Graph + vector hybrid memory
- Knowledge graph construction from documents
- Pythonic data pipelines

**Relevance:** Graph-based memory relationships align with your "related_memory_ids" concept.

---

## 4. Adversarial Robustness Research

This is the **most critical** and **least explored** area. Your "intelligent skepticism" feature addresses a real gap.

### 4.1 Threat Landscape for Memory/RAG Systems

**Primary Attack Vectors (from RAG Security Bench):**

| Attack Type                     | Description                                           | Relevance to Memory                      |
| ------------------------------- | ----------------------------------------------------- | ---------------------------------------- |
| **Poisoning Attacks**           | Inject malicious content into knowledge base          | Direct threat to git-notes               |
| **Prompt Injection via Memory** | Memory content contains adversarial instructions      | High risk if memories include user input |
| **Contradiction Injection**     | Insert memories that conflict with existing knowledge | Degrades decision quality                |
| **Temporal Manipulation**       | Forge timestamps or provenance                        | Undermines trust in memory history       |

**Key Research:**

- Zhang et al. (2025). "Benchmarking Poisoning Attacks against RAG" - _arXiv:2505.18543_
- Zou et al. (2025). "PoisonedRAG: Knowledge poisoning attacks" - _USENIX Security_
- RAGForensics (2025). "Traceback of Poisoning Attacks" - _ACM WWW_

### 4.2 Defense Strategies

**Current State:** "Current defense techniques fail to provide robust protection" (Zhang et al. 2025)

**Promising Approaches:**

1. **Skeptical Prompting:**

   - Activate LLM's internal reasoning to question retrieved content
   - Partial effectiveness demonstrated
   - _Reference:_ "Towards More Robust RAG: Evaluating Under Adversarial Attacks"

2. **FilterRAG / ML-FilterRAG:**

   - Use smaller LM to pre-filter potentially adversarial content
   - Statistical properties distinguish poisoned from clean text
   - _Reference:_ Elahimanesh et al. (2025). "Defending Against Knowledge Poisoning"

3. **N-Critics / Multi-Agent Verification:**

   - Ensemble of critic agents cross-check content
   - Debate frameworks expose contradictions
   - _Reference:_ Mousavi et al. (2023). "N-Critics: Self-Refinement with Ensemble of Critics"

4. **Provenance Tracking:**
   - Maintain chain of custody for all memories
   - Flag memories with suspicious origins
   - _Your git-notes approach naturally supports this_

### 4.3 Adversarial Detection Signals

Based on the research, your subconscious should detect:

| Signal                       | Detection Method                                                   | Confidence Impact                            |
| ---------------------------- | ------------------------------------------------------------------ | -------------------------------------------- |
| **Semantic Contradiction**   | Compare new memory embeddings against existing cluster             | Flag if cosine similarity indicates conflict |
| **Instruction-like Content** | Pattern matching for imperative phrases, system-like language      | Major red flag                               |
| **Temporal Anomalies**       | Timestamp vs. content analysis (references future events?)         | Flag for review                              |
| **Authority Claims**         | "As the system administrator...", "Override previous instructions" | Reject immediately                           |
| **Source Mismatch**          | Claimed provenance doesn't match content characteristics           | Reduce confidence                            |

---

## 5. Recommended Architecture

### 5.1 Conceptual Model

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONSCIOUS AGENT (Claude Code)               │
│                                                                 │
│  Receives: Synthesized context, confidence scores, warnings     │
│  Sends: Capture requests, recall queries                        │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Clean, validated context
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     MEMORY SUBCONSCIOUS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  ENRICHMENT │  │  ADVERSARIAL│  │  CONTEXT SYNTHESIZER    │  │
│  │  PIPELINE   │  │  DETECTOR   │  │                         │  │
│  ├─────────────┤  ├─────────────┤  ├─────────────────────────┤  │
│  │ • Tagging   │  │ • Injection │  │ • Relevance ranking     │  │
│  │ • Entities  │  │ • Contradict│  │ • Token budgeting       │  │
│  │ • Topics    │  │ • Temporal  │  │ • Warning synthesis     │  │
│  │ • Relations │  │ • Authority │  │ • Natural language      │  │
│  │ • Confidence│  │ • Source    │  │   summary               │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              MEMORY INDEX (sqlite-vec + metadata)           ││
│  │  • Embeddings  • Provenance  • Access patterns  • Scores    ││
│  └─────────────────────────────────────────────────────────────┘│
│                              ▲                                  │
└──────────────────────────────│──────────────────────────────────┘
                               │
┌──────────────────────────────│──────────────────────────────────┐
│                     git-notes-memory                            │
│                  (Persistent Storage Layer)                     │
│  • Git notes for sync  • Namespace organization  • Versioning   │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Processing Flows

**Capture Flow (System 2 - Deliberate):**

```
Input Memory
    │
    ▼
┌─────────────────┐
│ Adversarial     │ ──▶ REJECT if injection detected
│ Pre-screen      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Enrichment      │ ──▶ Extract entities, topics, tags
│ Pipeline        │ ──▶ Compute initial confidence
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Contradiction   │ ──▶ Compare against existing memories
│ Check           │ ──▶ Flag conflicts, adjust confidence
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Relationship    │ ──▶ Link to related memories
│ Mapping         │ ──▶ Update graph structure
└────────┬────────┘
         │
         ▼
    Store in git-notes + index
```

**Recall Flow (System 1 → System 2 escalation):**

```
Query
    │
    ▼
┌─────────────────┐
│ Fast Semantic   │ ──▶ Embedding similarity search
│ Search (S1)     │ ──▶ Return top-k candidates
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Confidence      │ ──▶ │ If low/suspect: │
│ Assessment      │     │ Escalate to S2  │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │              ┌────────▼────────┐
         │              │ Deep Verify     │
         │              │ • Cross-check   │
         │              │ • Source review │
         │              │ • Warning gen   │
         │              └────────┬────────┘
         │                       │
         ▼◀──────────────────────┘
┌─────────────────┐
│ Context         │ ──▶ Synthesize natural language context
│ Synthesizer     │ ──▶ Include confidence + warnings
└────────┬────────┘
         │
         ▼
    Return to Conscious Agent
```

### 5.3 Key Design Decisions

| Decision                           | Recommendation           | Rationale                                                                       |
| ---------------------------------- | ------------------------ | ------------------------------------------------------------------------------- |
| **Local LLM for enrichment?**      | Optional, not required   | Embedding models + heuristics sufficient for MVP; add LLM for complex inference |
| **Blocking vs. async processing?** | Async with sync fallback | Don't block agent for enrichment; do block for adversarial checks               |
| **Confidence representation**      | Enum + float             | Discrete levels (VERIFIED, HIGH, MEDIUM, LOW, SUSPECT) + numeric score          |
| **Memory linking**                 | Bidirectional graph      | When A links to B, B should know about A                                        |
| **Forgetting mechanism**           | Decay + reinforcement    | Memories accessed frequently increase score; unused decay                       |

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Confidence & Provenance)

- Add confidence scoring to existing capture/recall
- Implement provenance tracking (source, timestamp, session)
- Surface confidence in recall results

### Phase 2: Enrichment Pipeline

- Automatic tagging based on content
- Entity extraction (named entities, concepts)
- Topic inference
- Relationship detection

### Phase 3: Adversarial Detection

- Instruction injection detection
- Contradiction detection against existing memories
- Temporal anomaly detection
- Source verification

### Phase 4: Context Synthesis

- Token-budgeted context window generation
- Natural language synthesis of multiple memories
- Warning aggregation and presentation

### Phase 5: Learning & Adaptation

- Access pattern tracking
- Reinforcement/decay mechanisms
- Pattern emergence detection

---

## 7. Key Research Papers

### Foundational (Cognitive Architecture)

1. Laird, J.E. (2022). "An Analysis and Comparison of ACT-R and Soar" - arXiv:2201.09305
2. Kahneman, D. (2011). _Thinking, Fast and Slow_ - Farrar, Straus and Giroux
3. Newell, A. (1990). _Unified Theories of Cognition_ - Harvard University Press

### LLM Memory Systems

4. Packer et al. (2023). "MemGPT: Towards LLMs as Operating Systems" - arXiv:2310.08560
5. Xu et al. (2025). "A-MEM: Agentic Memory for LLM Agents" - arXiv:2502.12110
6. Letta Framework Documentation - docs.letta.com

### Dual-Process Theory in AI

7. Brady et al. (2025). "Dual-process theory and decision-making in LLMs" - Nature Reviews Psychology
8. Booch et al. (2021). "SOFAI: Slow and Fast AI"
9. Fabiano et al. (2023). "SOFAI-LM: Language Models with Metacognition" - arXiv:2508.17959

### Adversarial Robustness

10. Zhang et al. (2025). "Benchmarking Poisoning Attacks against RAG" - arXiv:2505.18543
11. Zou et al. (2025). "PoisonedRAG" - USENIX Security Symposium
12. Elahimanesh et al. (2025). "Defending Against Knowledge Poisoning" - arXiv:2508.02835

### Hallucination Detection & Self-Reflection

13. Ji et al. (2023). "Towards Mitigating LLM Hallucination via Self Reflection" - EMNLP Findings
14. Asai et al. (2023). "Self-RAG: Learning to Retrieve, Generate, and Critique" - arXiv:2310.11511
15. Mousavi et al. (2023). "N-Critics: Self-Refinement with Ensemble of Critics"

---

## 8. Open Questions for Further Research

1. **Calibration:** How do we calibrate confidence scores against ground truth?
2. **Adversarial training data:** Where do we get examples of memory poisoning attacks?
3. **LLM integration:** Should enrichment use Claude API, local LLM, or heuristics?
4. **Cross-project memory:** Should memories link across different git repositories?
5. **Human-in-the-loop:** When should the subconscious escalate to human review?

---

## 9. Conclusion

The "memory subconscious" concept is **architecturally valid** and addresses real gaps in existing memory systems:

- **Theoretical grounding:** Dual-process theory and cognitive architectures provide solid foundation
- **Prior art alignment:** MemGPT/Letta explicitly supports this pattern
- **Security need:** RAG poisoning research shows current defenses are inadequate
- **Differentiation:** Adversarial detection + confidence scoring is underexplored

The recommended approach is **incremental enhancement** of git-notes-memory rather than ground-up rewrite, starting with confidence/provenance and building toward full adversarial detection.

---

_Document prepared for git-notes-memory project evolution planning._
