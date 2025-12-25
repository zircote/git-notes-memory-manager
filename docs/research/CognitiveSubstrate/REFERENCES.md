# Research References
## Memory Subconscious Architecture

A curated bibliography organized by topic for the git-notes-memory evolution project.

---

## Cognitive Architectures & Dual-Process Theory

### Seminal Works

| Citation | Link | Key Contribution |
|----------|------|------------------|
| Kahneman (2011). *Thinking, Fast and Slow* | Book | System 1/System 2 framework |
| Newell (1990). *Unified Theories of Cognition* | Book | Problem Space Hypothesis, SOAR foundations |
| Anderson (1983). *The Architecture of Cognition* | Book | ACT-R foundations |

### Contemporary Analysis

| Citation | Link | Key Contribution |
|----------|------|------------------|
| Laird (2022). "Analysis of ACT-R and Soar" | [arXiv:2201.09305](https://arxiv.org/abs/2201.09305) | Detailed comparison of memory architectures |
| Laird (2022). "Introduction to Soar" | [arXiv:2205.03854](https://arxiv.org/pdf/2205.03854) | Comprehensive Soar tutorial |
| Brady et al. (2025). "Dual-process theory in LLMs" | [Nature Rev Psychology](https://www.nature.com/articles/s44159-025-00506-1) | LLM decision-making through dual-process lens |

### AI Applications

| Citation | Link | Key Contribution |
|----------|------|------------------|
| Booch et al. (2021). "SOFAI" | Referenced in SOFAI-LM | Fast/slow AI architecture |
| Fabiano et al. (2025). "SOFAI-LM" | [arXiv:2508.17959](https://arxiv.org/html/2508.17959v1) | Metacognitive governance for LLMs |
| Frontiers (2024). "Dual-process for neuro-symbolic AI" | [Frontiers](https://www.frontiersin.org/journals/cognition/articles/10.3389/fcogn.2024.1356941/full) | Integration blueprint |

---

## LLM Memory Systems

### Core Papers

| System | Citation | Link | Key Innovation |
|--------|----------|------|----------------|
| MemGPT | Packer et al. (2023) | [arXiv:2310.08560](https://arxiv.org/abs/2310.08560) | Virtual context management |
| A-MEM | Xu et al. (2025) | [arXiv:2502.12110](https://arxiv.org/html/2502.12110v11) | Zettelkasten-inspired agentic memory |
| Letta | Framework docs | [docs.letta.com](https://docs.letta.com/concepts/memgpt/) | Conscious/subconscious threads |

### Memory Implementations

| Repository | Link | Notes |
|------------|------|-------|
| mem0 | [github.com/mem0ai/mem0](https://github.com/mem0ai/mem0) | Universal memory layer |
| cognee | [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee) | Graph + vector hybrid |
| OpenMemory | [github.com/CaviraOSS/OpenMemory](https://github.com/CaviraOSS/OpenMemory) | Local-first cognitive memory |
| MemOS | [github.com/MemTensor/MemOS](https://github.com/MemTensor/MemOS) | Memory operating system |

---

## Adversarial Robustness in RAG/Memory Systems

### Attack Research

| Citation | Link | Attack Type |
|----------|------|-------------|
| Zhang et al. (2025). "RAG Security Bench" | [arXiv:2505.18543](https://arxiv.org/abs/2505.18543) | Comprehensive poisoning benchmark |
| Zou et al. (2025). "PoisonedRAG" | USENIX Security | Knowledge poisoning attacks |
| Zhao et al. (2025). "KG-RAG Safety" | [arXiv:2507.08862](https://arxiv.org/abs/2507.08862) | Knowledge graph poisoning |
| CorruptRAG (2025) | [arXiv:2504.03957](https://arxiv.org/html/2504.03957v1) | Practical single-shot poisoning |

### Defense Research

| Citation | Link | Defense Method |
|----------|------|----------------|
| RAGForensics (2025) | [ACM WWW](https://dl.acm.org/doi/abs/10.1145/3696410.3714756) | Traceback system for poisoning |
| FilterRAG (2025) | [arXiv:2508.02835](https://arxiv.org/html/2508.02835) | Statistical filtering of adversarial text |
| Skeptical prompting | [ADS](https://ui.adsabs.harvard.edu/abs/2024arXiv241216708S/abstract) | Activate LLM internal reasoning |

---

## Hallucination Detection & Self-Reflection

### Survey Papers

| Citation | Link | Coverage |
|----------|------|----------|
| LLM Hallucination Survey | [GitHub](https://github.com/HillZhang1999/llm-hallucination-survey) | Comprehensive reading list |
| Agent Hallucination Survey (2025) | [arXiv:2509.18970](https://arxiv.org/html/2509.18970v1) | Taxonomy for agent hallucinations |

### Key Methods

| Citation | Link | Approach |
|----------|------|----------|
| Ji et al. (2023). "Self Reflection" | [ACL](https://aclanthology.org/2023.findings-emnlp.123/) | Interactive self-reflection for QA |
| Asai et al. (2023). "Self-RAG" | [arXiv:2310.11511](https://arxiv.org) | Retrieve, generate, and critique |
| Mousavi et al. (2023). "N-Critics" | Paper | Ensemble of critics |
| HSP (2025) | [Springer](https://link.springer.com/article/10.1007/s40747-025-01833-9) | Hierarchical semantic piece detection |
| Datadog (2024). "LLM-as-a-judge" | [Blog](https://www.datadoghq.com/blog/ai/llm-hallucination-detection/) | Production hallucination detection |

---

## Metacognition & Self-Monitoring

| Citation | Link | Key Concept |
|----------|------|-------------|
| Posner. "Robots Thinking Fast and Slow" | [Oxford](https://iposner.github.io/fast-and-slow/) | Feeling of Knowing for robots |
| De Neys (2018). *Dual Process Theory 2.0* | Book | Conflict monitoring in cognition |

---

## Recommended Reading Order

### For Conceptual Understanding
1. Kahneman - *Thinking, Fast and Slow* (System 1/2 intuition)
2. Brady et al. - "Dual-process theory in LLMs" (modern application)
3. Packer et al. - "MemGPT" (LLM memory architecture)

### For Implementation Guidance
1. Laird - "Introduction to Soar" (memory taxonomy)
2. Xu et al. - "A-MEM" (Zettelkasten patterns)
3. Letta docs (conscious/subconscious threads)

### For Security Design
1. Zhang et al. - "RAG Security Bench" (threat landscape)
2. FilterRAG paper (defense mechanisms)
3. Ji et al. - "Self Reflection" (verification patterns)

---

## Industry Implementations to Study

| Company | System | Relevance |
|---------|--------|-----------|
| Anthropic | Claude Memory | Production memory with skepticism |
| Letta (MemGPT team) | Letta Framework | Open-source multi-thread agents |
| Datadog | LLM Observability | Production hallucination detection |
| AWS | Bedrock Agents | Agentic intervention patterns |

---

*Last updated: December 2024*
