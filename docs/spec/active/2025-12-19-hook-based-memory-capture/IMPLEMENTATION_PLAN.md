---
document_type: implementation_plan
project_id: SPEC-2025-12-19-001
version: 1.0.0
last_updated: 2025-12-19T00:00:00Z
status: approved
---

# Hook-Based Memory Capture - Implementation Plan

## Implementation Overview

This plan adds hook-based integration to the existing Memory Capture Plugin. The implementation builds on the existing `git-notes-memory` library and extends the Claude Code plugin with SessionStart context injection, capture signal detection, and session-end prompts.

### Timeline Phases

| Phase | Description | Dependencies |
|-------|-------------|--------------|
| Phase 1 | Core Hook Infrastructure | None |
| Phase 2 | SessionStart Context Injection | Phase 1 |
| Phase 3 | Capture Signal Detection | Phases 1, 2 |
| Phase 4 | Stop Hook Enhancement | Phases 1, 2 |
| Phase 5 | Testing & Documentation | Phases 1-4 |

### Success Criteria

- [ ] SessionStart hook fires on every session and injects XML context
- [ ] Context injection completes in ≤2000ms
- [ ] Signal detection identifies ≥80% of obvious memorable content
- [ ] Stop hook prompts for uncaptured content when appropriate
- [ ] All hooks fail gracefully (sessions continue without errors)

---

## Phase 1: Core Hook Infrastructure

**Goal**: Create the foundational module structure and shared utilities for hook handlers.

### Task 1.1: Create Hook Services Module

- [ ] Create `src/git_notes_memory/hooks/` directory structure
- [ ] Create `__init__.py` with module exports
- [ ] Create `xml_formatter.py` with XML generation utilities
- [ ] Create `config_loader.py` for hook-specific configuration

**Files to create**:
```
src/git_notes_memory/hooks/
├── __init__.py
├── xml_formatter.py
└── config_loader.py
```

### Task 1.2: Implement XML Formatter

- [ ] Create `XMLBuilder` class for building memory context XML
- [ ] Implement `build_element()` method for element creation
- [ ] Implement `to_string()` method with proper escaping
- [ ] Add helper methods for memory-specific elements

**Key implementation**:
```python
class XMLBuilder:
    def __init__(self, root_tag: str, attributes: Dict[str, str] = None):
        """Initialize XML builder with root element."""

    def add_element(self, parent: str, tag: str, text: str = None, **attrs) -> None:
        """Add child element to parent."""

    def add_memory_element(self, parent: str, memory: Memory, hydration: str) -> None:
        """Add memory-specific element with proper formatting."""

    def to_string(self, pretty: bool = True) -> str:
        """Serialize to XML string with optional formatting."""
```

### Task 1.3: Implement Config Loader

- [ ] Create `HookConfig` dataclass for hook settings
- [ ] Implement `load_hook_config()` function
- [ ] Add defaults for all hook configuration options
- [ ] Support environment variable overrides

**Configuration schema**:
```python
@dataclass
class HookConfig:
    enabled: bool = True
    session_start_enabled: bool = True
    session_start_budget_mode: str = "adaptive"
    session_start_fixed_budget: int = 1000
    capture_detection_enabled: bool = False
    capture_detection_min_confidence: float = 0.7
    capture_detection_auto_threshold: float = 0.95
    capture_detection_novelty_threshold: float = 0.3
    stop_enabled: bool = True
    stop_prompt_uncaptured: bool = True
    prompt_hook_timeout: int = 30
```

### Task 1.4: Create Shared Data Models

- [ ] Create `models.py` with hook-specific data classes
- [ ] Implement `CaptureSignal`, `SignalType` from architecture
- [ ] Implement `CaptureDecision`, `CaptureAction`
- [ ] Implement `TokenBudget`, `MemoryContext`

### Task 1.5: Update Plugin Configuration

- [ ] Extend `config.toml` schema for hook settings
- [ ] Update ConfigService to load hook configuration
- [ ] Add validation for hook-specific settings

---

## Phase 2: SessionStart Context Injection

**Goal**: Implement automatic memory context injection at session start.

### Task 2.1: Implement ContextBuilder

- [ ] Create `context_builder.py` in hooks module
- [ ] Implement `ContextBuilder` class per architecture spec
- [ ] Add `build_context()` method for full context generation
- [ ] Add `calculate_budget()` for adaptive token allocation
- [ ] Add `filter_memories()` for relevance-based filtering
- [ ] Add `to_xml()` for XML serialization

**Key methods**:
```python
class ContextBuilder:
    def __init__(self, recall_service: RecallService, index_service: IndexService):
        """Initialize with required services."""

    def build_context(self, project: str, session_source: str) -> str:
        """Build complete XML context for session injection."""

    def calculate_budget(self, project: str) -> TokenBudget:
        """Calculate token budget based on project complexity."""

    def filter_memories(self, memories: List[Memory], budget: TokenBudget) -> List[Memory]:
        """Filter memories to fit within token budget."""
```

### Task 2.2: Implement Project Detection

- [ ] Create `project_detector.py` utility
- [ ] Detect project from working directory
- [ ] Match against existing memory namespaces/tags
- [ ] Extract spec_id from CLAUDE.md or related files

### Task 2.3: Implement Budget Calculator

- [ ] Define complexity heuristics (file count, memory count)
- [ ] Implement tiered budget allocation
- [ ] Add allocation split between working memory and semantic context

**Budget tiers**:
| Project Complexity | Total Budget | Working Memory | Semantic Context |
|-------------------|--------------|----------------|------------------|
| Simple | 500 tokens | 350 | 150 |
| Medium | 1000 tokens | 600 | 400 |
| Complex | 2000 tokens | 1000 | 1000 |
| Full | 3000 tokens | 1500 | 1500 |

### Task 2.4: Create SessionStart Hook Handler

- [ ] Create `hooks/session_start.py` script
- [ ] Implement stdin JSON parsing
- [ ] Initialize services (RecallService, IndexService)
- [ ] Call ContextBuilder to generate context
- [ ] Output hookSpecificOutput JSON

**Hook script structure**:
```python
#!/usr/bin/env python3
"""SessionStart hook handler for memory context injection."""

import sys
import json
from git_notes_memory.hooks import ContextBuilder
from git_notes_memory.services import RecallService, IndexService

def main():
    input_data = json.load(sys.stdin)
    # ... implementation
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context_xml
        }
    }
    print(json.dumps(output))
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### Task 2.5: Register SessionStart Hook

- [ ] Update `hooks/hooks.json` with SessionStart configuration
- [ ] Set appropriate timeout (5s)
- [ ] Add source matcher for startup/resume/clear/compact

---

## Phase 3: Capture Signal Detection

**Goal**: Implement intelligent detection of memorable content in user prompts.

### Task 3.1: Implement SignalDetector

- [ ] Create `signal_detector.py` in hooks module
- [ ] Implement pattern compilation and caching
- [ ] Add `detect()` method for pattern matching
- [ ] Add `classify()` for namespace suggestion
- [ ] Add `score_confidence()` for confidence scoring

**Pattern categories** (from architecture):
- Decision: "decided", "chose", "went with"
- Learning: "learned", "TIL", "turns out"
- Blocker: "blocked by", "stuck on"
- Resolution: "fixed", "solved", "workaround"
- Preference: "I prefer", "I like"
- Explicit: "remember this", "save this"

### Task 3.2: Implement Novelty Checker

- [ ] Add `check_novelty()` method to SignalDetector
- [ ] Query similar memories using EmbeddingService
- [ ] Calculate novelty score (0.0 = duplicate, 1.0 = new)
- [ ] Use threshold from configuration (default 0.3)

### Task 3.3: Implement CaptureDecider

- [ ] Create `capture_decider.py` in hooks module
- [ ] Implement `should_capture()` decision logic
- [ ] Add threshold-based action selection (auto/suggest/skip)
- [ ] Generate suggested capture metadata

**Decision thresholds**:
| Confidence | Action | User Experience |
|------------|--------|-----------------|
| ≥0.95 | AUTO | Capture silently with notification |
| 0.7-0.95 | SUGGEST | Show suggestion, user confirms |
| <0.7 | SKIP | No action, unless explicit signal |

### Task 3.4: Create UserPromptSubmit Hook Handler

- [ ] Create `hooks/user_prompt.py` script
- [ ] Parse prompt from input JSON
- [ ] Run SignalDetector on prompt text
- [ ] Check novelty for detected signals
- [ ] Format capture suggestion if warranted
- [ ] Output additionalContext with suggestion

### Task 3.5: Format Capture Suggestions

- [ ] Create XML structure for capture suggestions
- [ ] Include signal type, confidence, suggested namespace
- [ ] Provide actionable prompt for Claude to offer capture
- [ ] Handle multiple signals in single prompt

**Suggestion format**:
```xml
<memory_capture_suggestion>
  <signal type="decision" confidence="0.92">
    <match>I decided to use SQLite for storage</match>
    <suggested_namespace>decisions</suggested_namespace>
    <suggested_tags>architecture, database</suggested_tags>
  </signal>
  <action>Consider using /remember to capture this decision</action>
</memory_capture_suggestion>
```

### Task 3.6: Register UserPromptSubmit Hook

- [ ] Update `hooks/hooks.json` with UserPromptSubmit configuration
- [ ] Set timeout to 2s (must be fast)
- [ ] Add configuration for enable/disable

---

## Phase 4: Stop Hook Enhancement

**Goal**: Enhance session end to prompt for uncaptured content and sync index.

### Task 4.1: Implement Session Analyzer

- [ ] Create `session_analyzer.py` in hooks module
- [ ] Parse session transcript from file
- [ ] Extract potential memorable content
- [ ] Check against already-captured memories

### Task 4.2: Detect Uncaptured Memories

- [ ] Apply SignalDetector to session transcript
- [ ] Filter out already-captured content
- [ ] Rank remaining signals by importance
- [ ] Return top N suggestions

### Task 4.3: Enhance Stop Hook Handler

- [ ] Update existing `hooks/stop.py`
- [ ] Add session analysis for uncaptured content
- [ ] Implement capture prompt if worthy content found
- [ ] Add index sync before session end
- [ ] Ensure graceful degradation

### Task 4.4: Implement Capture Prompt

- [ ] Format prompt with discovered signals
- [ ] Use blocking decision if high-value uncaptured content
- [ ] Allow bypass after one prompt (no infinite loops)
- [ ] Track prompt state in session context

### Task 4.5: Index Synchronization

- [ ] Call SyncService at session end
- [ ] Handle sync errors gracefully
- [ ] Log sync statistics

---

## Phase 5: Testing & Documentation

**Goal**: Comprehensive testing and documentation updates.

### Task 5.1: Unit Tests - Hook Services

- [ ] Test XMLBuilder with various inputs
- [ ] Test ContextBuilder budget calculation
- [ ] Test SignalDetector pattern matching
- [ ] Test CaptureDecider threshold logic
- [ ] Test config loading with defaults and overrides

### Task 5.2: Unit Tests - Hook Handlers

- [ ] Test session_start.py with mock input
- [ ] Test user_prompt.py signal detection
- [ ] Test stop.py session analysis
- [ ] Test error handling and graceful failures

### Task 5.3: Integration Tests

- [ ] End-to-end SessionStart context injection
- [ ] Signal detection → suggestion flow
- [ ] Stop hook → capture prompt → index sync
- [ ] Multi-hook interaction testing

### Task 5.4: Performance Tests

- [ ] Measure SessionStart hook execution time (<2000ms target)
- [ ] Measure signal detection time (<500ms target)
- [ ] Measure Stop hook execution time (<1000ms target)
- [ ] Profile memory usage during context building

### Task 5.5: Hook Script Testing

- [ ] Create test fixtures for hook inputs
- [ ] Manual testing with Claude Code
- [ ] Verify JSON output format
- [ ] Test exit codes and error paths

```bash
# Example hook test
echo '{"session_id":"test","cwd":"/tmp","hook_event_name":"SessionStart","source":"startup"}' | \
  python3 hooks/session_start.py | jq .
```

### Task 5.6: Documentation Updates

- [ ] Update plugin README with hook features
- [ ] Document configuration options in CLAUDE.md
- [ ] Add usage examples for each hook
- [ ] Document troubleshooting for hook issues

### Task 5.7: Update CHANGELOG

- [ ] Add entries for all new features
- [ ] Document breaking changes (if any)
- [ ] Include migration notes from manual-only usage

---

## Implementation Notes

### Dependencies on Existing Code

All hook handlers depend on existing services:

| Service | Used By | Purpose |
|---------|---------|---------|
| RecallService | ContextBuilder | Query memories for context |
| IndexService | ContextBuilder | Get memory statistics |
| CaptureService | Stop hook | Auto-capture if enabled |
| EmbeddingService | SignalDetector | Novelty checking |
| SyncService | Stop hook | Index synchronization |
| ConfigService | All hooks | Load configuration |

### Error Handling Strategy

All hooks must fail gracefully:

```python
def main():
    try:
        # Hook logic
        pass
    except Exception as e:
        # Log error but don't block session
        print(f"Hook error: {e}", file=sys.stderr)
        sys.exit(0)  # Exit 0 = non-blocking
```

### Testing Commands

```bash
# Run unit tests
pytest tests/test_hooks/ -v

# Run integration tests
pytest tests/integration/test_hook_handlers.py -v

# Test individual hook manually
cat fixtures/session_start_input.json | python3 hooks/session_start.py

# Performance profile
python3 -m cProfile -s time hooks/session_start.py < fixtures/session_start_input.json
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| SessionStart delays | Timeout enforcement, async context loading option |
| False positive captures | Confidence thresholds, user confirmation for SUGGEST |
| Context overload | Token budget limits, relevance filtering |
| Hook script errors | Graceful failure (exit 0), comprehensive error logging |
| Performance regression | Benchmark tests, lazy loading, caching |

---

## Acceptance Criteria

### Phase 1 Complete When:
- [ ] Hook services module exists with all files
- [ ] XMLBuilder generates valid XML
- [ ] Configuration loads with defaults
- [ ] Data models match architecture spec

### Phase 2 Complete When:
- [ ] SessionStart hook fires on session start
- [ ] XML context appears in Claude's system prompt
- [ ] Context includes relevant memories from current project
- [ ] Execution time ≤2000ms

### Phase 3 Complete When:
- [ ] Signal patterns detect common memorable phrases
- [ ] Novelty check prevents duplicate suggestions
- [ ] Capture suggestions appear in Claude context
- [ ] Detection time ≤500ms

### Phase 4 Complete When:
- [ ] Stop hook analyzes session transcript
- [ ] Uncaptured content prompts appear when appropriate
- [ ] Index syncs on session end
- [ ] No infinite prompt loops

### Phase 5 Complete When:
- [ ] Unit test coverage ≥80%
- [ ] All hooks pass integration tests
- [ ] Performance targets met
- [ ] Documentation updated
