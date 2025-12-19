# Hook Enhancement Plan: Expanded Memory Capture & Response Structuring

## Overview

Enhance the git-notes-memory plugin hooks to:
1. Add new hooks (PostToolUse, PreCompact) for contextual memory injection
2. Enhance UserPromptSubmit with namespace-aware markers
3. Add response structuring guidance at SessionStart to improve capture reliability

## Goals

- **Increase capture reliability**: Guide Claude to structure responses for consistent signal detection
- **Reduce missed captures**: Inject context at more lifecycle points
- **Improve namespace targeting**: Allow users to specify namespace in inline markers
- **Preserve context**: Capture valuable content before compaction

---

## Phase 1: SessionStart Response Structuring Guidance

### Objective
Inject guidance into `additionalContext` that teaches Claude how to structure responses for reliable memory capture.

### Implementation

**File**: `src/git_notes_memory/hooks/session_start_handler.py`

**Changes to ContextBuilder.build_context()**:
Add a new `_build_response_guidance()` method that generates XML guidance for Claude.

```xml
<response_guidance>
  <capture_patterns title="How to Structure Responses for Memory Capture">
    <pattern type="decision">
      <description>When making architectural/design decisions</description>
      <template>
        **Decision**: [One-line summary]
        **Context**: [Why this decision was needed]
        **Choice**: [What was chosen]
        **Rationale**: [Why this choice over alternatives]
        **Alternatives considered**: [Other options evaluated]
      </template>
      <trigger_phrases>
        - "We decided to..."
        - "The decision is to..."
        - "Going with X because..."
      </trigger_phrases>
    </pattern>

    <pattern type="learning">
      <description>When discovering insights or TIL moments</description>
      <template>
        **Learning**: [One-line insight]
        **Context**: [How this was discovered]
        **Application**: [When/how to apply this]
      </template>
      <trigger_phrases>
        - "TIL..."
        - "Discovered that..."
        - "Learned that..."
        - "Turns out..."
      </trigger_phrases>
    </pattern>

    <pattern type="blocker">
      <description>When encountering obstacles</description>
      <template>
        **Blocker**: [One-line issue]
        **Impact**: [What this blocks]
        **Status**: [investigating/blocked/resolved]
        **Resolution**: [If resolved, how]
      </template>
      <trigger_phrases>
        - "Blocked by..."
        - "Cannot proceed because..."
        - "Stuck on..."
      </trigger_phrases>
    </pattern>

    <pattern type="progress">
      <description>When completing milestones</description>
      <template>
        **Completed**: [What was finished]
        **Deliverables**: [Concrete outputs]
        **Next**: [What comes next]
      </template>
      <trigger_phrases>
        - "Completed..."
        - "Finished implementing..."
        - "Milestone reached..."
      </trigger_phrases>
    </pattern>
  </capture_patterns>

  <inline_markers title="Quick Capture Markers">
    <marker syntax="[remember] text" namespace="learnings" />
    <marker syntax="[remember:namespace] text" namespace="specified" />
    <marker syntax="[capture] text" namespace="auto-detect" />
    <marker syntax="[capture:decisions] text" namespace="decisions" />
    <marker syntax="@memory text" namespace="auto-detect" />
    <marker syntax="@memory:patterns text" namespace="patterns" />
  </inline_markers>

  <best_practices>
    <practice>Use clear trigger phrases at the start of memorable content</practice>
    <practice>Include rationale with decisions, not just the choice</practice>
    <practice>Tag blockers with resolution when solved</practice>
    <practice>Keep summaries under 100 characters</practice>
  </best_practices>
</response_guidance>
```

**New Config Options**:
- `HOOK_SESSION_START_INCLUDE_GUIDANCE`: bool (default: true)
- `HOOK_SESSION_START_GUIDANCE_DETAIL`: enum (minimal/standard/detailed)

### Files to Modify
- `src/git_notes_memory/hooks/session_start_handler.py`
- `src/git_notes_memory/hooks/context_builder.py` (add `_build_response_guidance()`)
- `src/git_notes_memory/hooks/config_loader.py` (add new config options)

---

## Phase 2: Enhanced UserPromptSubmit with Namespace Support

### Objective
Support namespace hints in inline markers: `[remember:decisions]`, `@memory:patterns`

### Implementation

**File**: `src/git_notes_memory/hooks/user_prompt_handler.py`

**Enhanced Marker Patterns**:
```python
NAMESPACE_MARKERS = [
    # With namespace: [remember:decisions] content
    (r"^\[remember:(\w+)\]\s*", "namespace_specified"),
    # Without namespace: [remember] content -> learnings
    (r"^\[remember\]\s*", "learnings"),
    # With namespace: [capture:patterns] content
    (r"^\[capture:(\w+)\]\s*", "namespace_specified"),
    # Without namespace: [capture] content -> auto-detect
    (r"^\[capture\]\s*", "auto_detect"),
    # With namespace: @memory:decisions content
    (r"^@memory:(\w+)\s+", "namespace_specified"),
    # Without namespace: @memory content -> auto-detect
    (r"^@memory\s+", "auto_detect"),
]
```

**Auto-Detection Logic** (for `auto_detect` mode):
```python
def _detect_namespace(content: str) -> str:
    """Detect appropriate namespace from content signals."""
    signals = signal_detector.detect(content)
    if signals:
        # Map signal type to namespace
        type_to_namespace = {
            SignalType.DECISION: "decisions",
            SignalType.LEARNING: "learnings",
            SignalType.BLOCKER: "blockers",
            SignalType.RESOLUTION: "blockers",  # Resolution updates blocker
            SignalType.PREFERENCE: "decisions",
            SignalType.EXPLICIT: "learnings",  # Default for explicit
        }
        return type_to_namespace.get(signals[0].type, "learnings")
    return "learnings"  # Default
```

### Files to Modify
- `src/git_notes_memory/hooks/user_prompt_handler.py`
- `hooks/userpromptsubmit.py` (entry point script)

---

## Phase 3: PostToolUse Hook for File-Contextual Injection

### Objective
After file writes/edits, inject relevant memories about the modified file's domain.

### Implementation

**New File**: `src/git_notes_memory/hooks/post_tool_use_handler.py`

**New File**: `hooks/posttooluse.py` (entry point)

**Logic**:
```python
def main():
    input_data = json.load(sys.stdin)
    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name not in ["Write", "Edit", "MultiEdit"]:
        print(json.dumps({"continue": True}))
        return

    file_path = tool_input.get("file_path", "")
    if not file_path:
        print(json.dumps({"continue": True}))
        return

    # Extract domain from file path
    domain_terms = extract_domain_terms(file_path)
    # e.g., "src/auth/jwt_handler.py" -> ["auth", "jwt", "authentication"]

    # Search for related memories
    recall = get_recall_service()
    results = recall.search(
        " ".join(domain_terms),
        k=3,
        min_similarity=0.6
    )

    if not results:
        print(json.dumps({"continue": True}))
        return

    # Build additionalContext
    context_lines = [f"Related memories for {Path(file_path).name}:"]
    for r in results:
        context_lines.append(f"- [{r.memory.namespace}] {r.memory.summary}")

    output = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(context_lines)
        }
    }
    print(json.dumps(output))
```

**Domain Extraction**:
```python
def extract_domain_terms(file_path: str) -> list[str]:
    """Extract searchable terms from file path."""
    path = Path(file_path)
    terms = []

    # From directory names (skip common ones)
    skip_dirs = {"src", "lib", "app", "tests", "test", "spec"}
    for part in path.parts[:-1]:
        if part.lower() not in skip_dirs and not part.startswith("."):
            terms.append(part)

    # From filename (without extension)
    stem = path.stem
    # Split on common separators
    for term in re.split(r"[_\-.]", stem):
        if len(term) > 2:
            terms.append(term)

    return terms[:5]  # Limit to top 5 terms
```

**Config Options**:
- `HOOK_POST_TOOL_USE_ENABLED`: bool (default: true)
- `HOOK_POST_TOOL_USE_MIN_SIMILARITY`: float (default: 0.6)
- `HOOK_POST_TOOL_USE_MAX_RESULTS`: int (default: 3)

### Files to Create
- `src/git_notes_memory/hooks/post_tool_use_handler.py`
- `hooks/posttooluse.py`

### Files to Modify
- `hooks/hooks.json` (add PostToolUse configuration)
- `src/git_notes_memory/hooks/config_loader.py` (add config options)

---

## Phase 4: PreCompact Hook for Memory Preservation

### Objective
Before context compaction, auto-capture high-confidence uncaptured content to prevent loss.

### Implementation

**New File**: `src/git_notes_memory/hooks/pre_compact_handler.py`

**New File**: `hooks/precompact.py` (entry point)

**Logic**:
```python
def main():
    input_data = json.load(sys.stdin)
    transcript_path = input_data.get("transcript_path")
    trigger = input_data.get("trigger", "auto")  # "manual" or "auto"

    if not transcript_path or not Path(transcript_path).exists():
        print(json.dumps({"continue": True}))
        return

    # Analyze transcript for uncaptured signals
    analyzer = SessionAnalyzer()
    signals = analyzer.analyze(transcript_path, check_novelty=True)

    # Filter to high-confidence signals only
    high_confidence = [s for s in signals if s.confidence >= 0.85]

    if not high_confidence:
        print(json.dumps({"continue": True}))
        return

    # Auto-capture top 3 most important
    capture = get_capture_service()
    captured = []

    for signal in high_confidence[:3]:
        result = capture.capture(
            namespace=signal.namespace,
            summary=_extract_summary(signal),
            content=signal.context,
            tags=["auto-captured", "pre-compact"],
        )
        if result.success:
            captured.append(result.memory.summary)

    # Report what was preserved
    if captured:
        output = {
            "continue": True,
            "systemMessage": f"Auto-captured {len(captured)} memories before compaction"
        }
    else:
        output = {"continue": True}

    print(json.dumps(output))
```

**Config Options**:
- `HOOK_PRE_COMPACT_ENABLED`: bool (default: true)
- `HOOK_PRE_COMPACT_AUTO_CAPTURE`: bool (default: true)
- `HOOK_PRE_COMPACT_MIN_CONFIDENCE`: float (default: 0.85)
- `HOOK_PRE_COMPACT_MAX_CAPTURES`: int (default: 3)

### Files to Create
- `src/git_notes_memory/hooks/pre_compact_handler.py`
- `hooks/precompact.py`

### Files to Modify
- `hooks/hooks.json` (add PreCompact configuration)
- `src/git_notes_memory/hooks/config_loader.py` (add config options)

---

## Phase 5: Update hooks.json

**Final hooks/hooks.json**:
```json
{
  "description": "Memory Capture Plugin Hooks",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume",
        "hooks": [{
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/hooks/sessionstart.py",
          "timeout": 10
        }]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [{
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/hooks/userpromptsubmit.py",
          "timeout": 10
        }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [{
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/hooks/posttooluse.py",
          "timeout": 5
        }]
      }
    ],
    "PreCompact": [
      {
        "matcher": "manual|auto",
        "hooks": [{
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/hooks/precompact.py",
          "timeout": 15
        }]
      }
    ],
    "Stop": [
      {
        "hooks": [{
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop.py",
          "timeout": 30
        }]
      }
    ]
  }
}
```

---

## Phase 6: Testing & Documentation

### Test Files to Create
- `tests/hooks/test_post_tool_use_handler.py`
- `tests/hooks/test_pre_compact_handler.py`
- `tests/hooks/test_response_guidance.py`
- `tests/hooks/test_namespace_markers.py`

### Documentation Updates
- `docs/USER_GUIDE.md` - Add response structuring best practices
- `README.md` - Update hook configuration section
- `skills/memory-assistant/SKILL.md` - Update integration section

---

## Implementation Order

1. **Phase 1**: SessionStart response guidance (highest user value)
2. **Phase 2**: Enhanced UserPromptSubmit namespace markers
3. **Phase 3**: PostToolUse file-contextual injection
4. **Phase 4**: PreCompact memory preservation
5. **Phase 5**: hooks.json update
6. **Phase 6**: Testing & documentation

---

## Critical Files Summary

### New Files
| File | Purpose |
|------|---------|
| `src/git_notes_memory/hooks/post_tool_use_handler.py` | PostToolUse handler |
| `src/git_notes_memory/hooks/pre_compact_handler.py` | PreCompact handler |
| `hooks/posttooluse.py` | PostToolUse entry script |
| `hooks/precompact.py` | PreCompact entry script |

### Modified Files
| File | Changes |
|------|---------|
| `src/git_notes_memory/hooks/context_builder.py` | Add `_build_response_guidance()` |
| `src/git_notes_memory/hooks/session_start_handler.py` | Include guidance in output |
| `src/git_notes_memory/hooks/user_prompt_handler.py` | Namespace-aware markers |
| `src/git_notes_memory/hooks/config_loader.py` | New config options |
| `hooks/hooks.json` | Add PostToolUse, PreCompact |
| `hooks/userpromptsubmit.py` | Support namespace in markers |

---

## Success Metrics

- Signal detection accuracy improves from ~70% to ~85%
- Namespace targeting increases from 10% (all to learnings) to 60%+
- Pre-compaction capture saves 90%+ of high-confidence uncaptured content
- User satisfaction with capture reliability increases
