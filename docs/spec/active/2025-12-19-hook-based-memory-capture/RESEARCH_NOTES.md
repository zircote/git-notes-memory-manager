---
document_type: research
project_id: SPEC-2025-12-19-001
version: 1.0.0
last_updated: 2025-12-19T00:00:00Z
status: complete
---

# Hook-Based Memory Capture - Research Notes

## Research Summary

This document consolidates research findings on AI memory management systems, Claude Code hooks, and XML-structured prompt design for the hook-based memory capture enhancement.

## 1. AI Memory Management Best Practices

### 1.1 Industry Memory Architectures

| System | Architecture | Storage | Key Innovation |
|--------|--------------|---------|----------------|
| **Claude Memory** | Project-scoped, file-based | CLAUDE.md markdown | Transparent, git-managed, user-controlled |
| **ChatGPT Memory** | Global + RAG hybrid | Saved memories + history | Automatic extraction + full history search |
| **Mem0** | Three-tier hierarchy | Vector DB + graph store | User/Session/Agent memory levels |
| **MemGPT/Letta** | OS-inspired virtual context | Main (RAM) + External (Disk) | Autonomous paging with "heartbeats" |

### 1.2 Memory Tiering Strategy (MemGPT OS Paradigm)

```
┌─────────────────────────────────────────────────────────────────┐
│ PRIMARY CONTEXT (Working Memory / "RAM")                        │
│ ├── Static System Prompt (base instructions)                    │
│ ├── Dynamic Working Context (current reasoning state)           │
│ └── FIFO Message Buffer (recent conversation turns)             │
├─────────────────────────────────────────────────────────────────┤
│ EXTERNAL CONTEXT (Long-Term Memory / "Disk")                    │
│ ├── Recall Storage (searchable historical interaction logs)     │
│ └── Archival Storage (vector-based semantic retrieval)          │
└─────────────────────────────────────────────────────────────────┘
```

**Key mechanism**: Memory pressure triggers automatic write-back when token usage approaches ~70% capacity.

### 1.3 Memory Types (Cognitive Model)

| Memory Type | Purpose | Implementation Pattern |
|-------------|---------|------------------------|
| **Semantic** | Facts and knowledge | Collections (unbounded, searchable) + Profiles (strict schemas) |
| **Episodic** | Successful interactions | Full context preservation with situation, reasoning, outcome |
| **Procedural** | Behavioral rules | System instructions that evolve through feedback |

### 1.4 Context Window Optimization

1. **Token compression**: Rephrase information to use fewer tokens
2. **Smart filtering**: Score and keep only most relevant memories
3. **Dynamic allocation**: Adjust memory usage based on complexity
4. **Hierarchical namespaces**: Multi-level segmentation

**Performance data**: Mem0's selective retrieval achieves:
- 91% reduction in p95 latency
- 90% reduction in token consumption
- 26% improvement in overall accuracy vs. OpenAI's memory

### 1.5 Memory Capture Strategies

| Approach | Best For | Implementation |
|----------|----------|----------------|
| **Automatic** | Key facts users wouldn't document | Real-time detection with LLM extraction |
| **Manual** | User-curated important decisions | `/remember` command |
| **Hybrid** | Production systems | Auto-detect candidates, user confirms |

### 1.6 Identifying "Memorable" Moments

| Signal | Description | Detection Method |
|--------|-------------|------------------|
| **Novelty** | Information differs from existing | Embedding similarity threshold (<0.7) |
| **Surprise** | Unexpected patterns or outcomes | Google's Titans "surprise metric" |
| **Preference** | Explicit statements about preferences | Keyword + LLM classification |
| **Decision** | Choices made with rationale | Pattern: "I chose X because Y" |
| **Error/Resolution** | Problems and solutions | Blocker → resolution state change |
| **Explicit marker** | User says "remember this" | Command parsing |

### 1.7 Retrieval Best Practices

**Hybrid Search Strategy**:
```
┌─────────────────────────────────────────────────────────────────┐
│ HYBRID SEARCH                                                   │
│ ├── Lexical Search (BM25/keyword) → Precision for identifiers   │
│ ├── Vector Search (embeddings) → Semantic recall                │
│ └── Fusion Layer → Combine and deduplicate                      │
├─────────────────────────────────────────────────────────────────┤
│ RE-RANKING LAYER                                                │
│ ├── Cross-encoder re-ranking (top K)                            │
│ ├── Recency boost (temporal decay)                              │
│ └── Namespace priority (configurable weights)                   │
└─────────────────────────────────────────────────────────────────┘
```

**Benchmark**: Hybrid achieves 84.3% Recall@10 vs. 65-70% vector-only.

### 1.8 Memory Relevance Scoring

| Score | Interpretation | Action |
|-------|----------------|--------|
| 4.0 | Highly relevant | Include in context |
| 3.0-3.9 | Relevant | Include with lower priority |
| 2.0-2.9 | Possibly relevant | Include if space permits |
| 0-1.9 | Low relevance | Exclude |

### 1.9 Privacy and User Control

**Gold standard from Claude's implementation**:
- Memory toggle (global on/off)
- Incognito mode (per-conversation)
- Project scoping (isolated memory)
- View/Edit/Delete (full CRUD)
- Export (data portability)

---

## 2. Claude Code Hooks Reference

### 2.1 Available Hook Events

| Event | When It Fires | Can Block? | Best For |
|-------|---------------|-----------|----------|
| `SessionStart` | Session begins | NO | Load context, set environment |
| `UserPromptSubmit` | User submits prompt | YES | Validation, context injection |
| `PreToolUse` | Before tool call | YES | Validate, approve, modify inputs |
| `PostToolUse` | After tool completes | YES (soft) | Feedback, logging, formatting |
| `Stop` | Claude finishes | YES | Force continuation, capture prompts |
| `SubagentStop` | Subagent finishes | YES | Task completion validation |
| `SessionEnd` | Session ends | NO | Cleanup, logging, metrics |

### 2.2 Hook Configuration Locations

```
~/.claude/settings.json             # User-level hooks
.claude/settings.json               # Project-level hooks
.claude/settings.local.json         # Local (not committed)
Plugin's hooks/hooks.json           # Plugin-provided hooks
```

### 2.3 Hook Input Structure (Common Fields)

```json
{
  "session_id": "unique-id-per-session",
  "transcript_path": "/absolute/path/to/session.jsonl",
  "cwd": "/current/working/directory",
  "permission_mode": "default|plan|acceptEdits|bypassPermissions",
  "hook_event_name": "EventName"
}
```

### 2.4 Hook Output Structure

| Exit Code | Behavior | Use Case |
|-----------|----------|----------|
| 0 | Success, parse JSON | Normal operation |
| 2 | Blocking error | Block with message |
| Other | Non-blocking error | Warning/logging |

```json
{
  "hookSpecificOutput": {
    "hookEventName": "EventName",
    "additionalContext": "Context injected into session..."
  }
}
```

### 2.5 Prompt-Type Hooks (LLM-Assisted Decisions)

**Supported Events**: Stop, SubagentStop, UserPromptSubmit, PreToolUse

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "prompt",
        "prompt": "Check if work complete. Respond: {\"decision\": \"approve\" or \"block\", \"reason\": \"...\"}",
        "timeout": 30
      }]
    }]
  }
}
```

### 2.6 Context Injection Pattern

The `hookSpecificOutput.additionalContext` field is key for memory injection:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "MEMORY CONTEXT:\n\nRecent Decisions:\n- Chose PostgreSQL\n- Implemented semantic search"
  }
}
```

**Two methods**:
1. **Plain text stdout** (simpler): Any text to stdout with exit 0
2. **JSON additionalContext** (structured): Full control

---

## 3. XML-Structured Prompt Design

### 3.1 Design Rationale

XML tags provide:
- Clear semantic boundaries for memory sections
- Hierarchical organization (context → namespace → memory)
- Parseable structure for LLM and tools
- Consistent format across hook events

### 3.2 Proposed Memory Context Structure

```xml
<memory_context source="SessionStart" timestamp="2025-12-19T10:00:00Z">
  <project_scope>
    <project>hook-based-memory-capture</project>
    <spec_id>SPEC-2025-12-19-001</spec_id>
    <token_budget>1500</token_budget>
  </project_scope>

  <working_memory priority="high">
    <active_blockers count="1">
      <blocker id="mem-abc123" age="2d" status="active">
        <summary>Embedding model download fails on cold start</summary>
        <impact>First session takes 30+ seconds to initialize</impact>
      </blocker>
    </active_blockers>

    <recent_decisions count="3" window="7d">
      <decision id="mem-def456" age="1d">
        <summary>Use prompt-type hooks for capture decisions</summary>
        <rationale>LLM can assess context-dependent memorability</rationale>
      </decision>
      <!-- More decisions... -->
    </recent_decisions>

    <pending_actions count="0">
      <!-- Unresolved action items -->
    </pending_actions>
  </working_memory>

  <semantic_context priority="medium">
    <relevant_learnings query="hook implementation" count="3">
      <learning id="mem-ghi789" relevance="0.92">
        <summary>SessionStart hooks must be fast (&lt;5s)</summary>
        <insight>Heavy operations should be async or cached</insight>
      </learning>
      <!-- More learnings... -->
    </relevant_learnings>

    <related_patterns count="1">
      <pattern id="mem-jkl012" confidence="0.85">
        <type>success</type>
        <summary>Progressive hydration improves perceived latency</summary>
      </pattern>
    </related_patterns>
  </semantic_context>

  <commands>
    <command name="/recall">Search memories semantically</command>
    <command name="/remember">Capture new memory</command>
    <command name="/context">Load full project context</command>
  </commands>
</memory_context>
```

### 3.3 Memory Capture Request Structure

```xml
<memory_capture_request>
  <source_event>UserPromptSubmit</source_event>
  <capture_signals detected="3">
    <signal type="decision" confidence="0.95">
      <match>I chose to use XML tags because...</match>
    </signal>
    <signal type="learning" confidence="0.78">
      <match>I realized that hook timeouts...</match>
    </signal>
    <signal type="explicit" confidence="1.0">
      <match>Remember this for next time</match>
    </signal>
  </capture_signals>

  <suggested_captures>
    <capture priority="high">
      <namespace>decisions</namespace>
      <summary>Use XML tags for structured memory prompts</summary>
      <content>...</content>
      <tags>prompt-design, architecture</tags>
    </capture>
  </suggested_captures>

  <action_required>
    <confirm>true</confirm>
    <reason>High confidence captures detected, user confirmation recommended</reason>
  </action_required>
</memory_capture_request>
```

### 3.4 Memory Search Response Structure

```xml
<memory_search_response query="database selection" timestamp="2025-12-19T10:05:00Z">
  <search_metadata>
    <query_type>semantic</query_type>
    <total_results>12</total_results>
    <returned>5</returned>
    <filters>
      <namespace>decisions,learnings</namespace>
      <time_range>30d</time_range>
    </filters>
  </search_metadata>

  <results>
    <memory rank="1" relevance="0.94" hydration="FULL">
      <id>mem-xyz789</id>
      <namespace>decisions</namespace>
      <summary>Chose SQLite + sqlite-vec over PostgreSQL</summary>
      <timestamp>2025-12-17T14:30:00Z</timestamp>
      <content>
        ## Decision Context

        Evaluated options for semantic search backend...

        ## Rationale

        SQLite provides single-file deployment...
      </content>
      <tags>database, performance, architecture</tags>
    </memory>
    <!-- More results... -->
  </results>

  <suggestions>
    <related_query>sqlite-vec performance</related_query>
    <related_query>vector search alternatives</related_query>
  </suggestions>
</memory_search_response>
```

---

## 4. Key Design Decisions

### 4.1 Hook Strategy

| Hook Event | Purpose | Implementation |
|------------|---------|----------------|
| `SessionStart` | Context injection | Load relevant memories, inject XML context |
| `UserPromptSubmit` | Capture detection | Scan for memorable signals, suggest captures |
| `PostToolUse` (Write/Edit) | Change tracking | Track significant file modifications |
| `Stop` | Session capture | Prompt to capture learnings before exit |

### 4.2 Capture Intelligence Levels

| Level | Description | Use Case |
|-------|-------------|----------|
| **Auto-silent** | Capture without prompting | High-confidence signals (explicit markers) |
| **Auto-confirm** | Capture with notification | Medium-confidence signals |
| **Suggest** | Suggest but don't capture | Low-confidence signals |
| **Manual-only** | Only explicit `/remember` | User preference setting |

### 4.3 Context Budget Strategy

| Project Complexity | Token Budget | Allocation |
|-------------------|--------------|------------|
| Simple (1-2 files) | 500 tokens | Blockers + 3 recent |
| Medium (module) | 1000 tokens | + relevant learnings |
| Complex (system) | 2000 tokens | + patterns + decisions |
| Full context | 3000 tokens | Everything relevant |

### 4.4 Integration Approach

**Decision**: Add hooks to existing memory-capture-plugin rather than creating a new plugin.

**Rationale**:
- Reuses existing capture/recall services
- Single installation for users
- Unified configuration
- Shared memory storage

---

## 5. Research Sources

### AI Memory Systems
- Mem0 - Universal memory layer for AI Agents
- MemGPT: Towards LLMs as Operating Systems
- LangMem Conceptual Guide
- Google Titans + MIRAS research
- Claude Memory blog post

### Claude Code Hooks
- Official hooks documentation (code.claude.com/docs/en/hooks.md)
- Hooks quickstart guide
- learning-output-style plugin example

### Semantic Search
- Azure AI Search semantic ranking
- Elasticsearch context engineering
- Hybrid retrieval benchmarks
