---
document_type: architecture
project_id: SPEC-2025-12-19-002
version: 1.0.0
last_updated: 2025-12-19T00:00:00Z
status: draft
---

# Hook Enhancement v2 - Technical Architecture

## System Overview

This enhancement extends the existing hook infrastructure with four capabilities:

1. **Response Guidance Injection** - XML templates in SessionStart additionalContext
2. **Namespace-Aware Markers** - Extended regex patterns in UserPromptSubmit
3. **PostToolUse Handler** - New hook for file-contextual memory injection
4. **PreCompact Handler** - New hook for pre-compaction memory preservation

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Claude Code Session                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ SessionStart  │          │UserPromptSubmit│          │  PostToolUse  │
│    Hook       │          │     Hook       │          │     Hook      │
└───────┬───────┘          └───────┬───────┘          └───────┬───────┘
        │                          │                          │
        ▼                          ▼                          ▼
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ContextBuilder │          │ UserPrompt    │          │ PostToolUse   │
│ + Guidance    │          │ Handler       │          │ Handler       │
│   Builder     │          │ + Namespace   │          │ + Domain      │
│   [NEW]       │          │   Parser      │          │   Extractor   │
└───────┬───────┘          │   [NEW]       │          │   [NEW]       │
        │                  └───────┬───────┘          └───────┬───────┘
        │                          │                          │
        │                          ▼                          ▼
        │                  ┌───────────────┐          ┌───────────────┐
        │                  │SignalDetector │          │ RecallService │
        │                  │ (existing)    │          │  (existing)   │
        │                  └───────┬───────┘          └───────────────┘
        │                          │
        │                          ▼
        │                  ┌───────────────┐
        │                  │CaptureService │
        │                  │  (existing)   │
        │                  └───────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                        additionalContext (XML)                            │
│  <memory_context>                                                         │
│    <response_guidance> [NEW]                                              │
│      <capture_patterns>...</capture_patterns>                             │
│      <inline_markers>...</inline_markers>                                 │
│    </response_guidance>                                                   │
│    <working_memory>...</working_memory>                                   │
│    <semantic_context>...</semantic_context>                               │
│  </memory_context>                                                        │
└───────────────────────────────────────────────────────────────────────────┘

                                    │
                                    ▼
                          ┌───────────────┐
                          │  PreCompact   │
                          │     Hook      │
                          └───────┬───────┘
                                  │
                                  ▼
                          ┌───────────────┐
                          │ PreCompact    │
                          │ Handler       │
                          │ + Session     │
                          │   Analyzer    │
                          │   [NEW]       │
                          └───────┬───────┘
                                  │
                          ┌───────┴───────┐
                          ▼               ▼
                  ┌───────────┐   ┌───────────┐
                  │Capture    │   │ stderr    │
                  │Service    │   │ output    │
                  │(existing) │   │ (to user) │
                  └───────────┘   └───────────┘
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Extend ContextBuilder rather than new service | Reuses existing XML formatting and token budget |
| Namespace regex in UserPromptHandler | Minimal change to existing pattern matching |
| PostToolUse as separate handler | Clean separation; different lifecycle point |
| PreCompact uses stderr for user feedback | API constraint: no additionalContext support |

## Component Design

### Component 1: Response Guidance Builder

**Purpose**: Generate XML templates teaching Claude how to structure responses for reliable signal detection

**Responsibilities**:
- Build XML guidance based on configured detail level
- Include trigger phrases for each capture pattern type
- Provide inline marker syntax reference

**Interfaces**:
```python
class GuidanceBuilder:
    def build_guidance(self, detail_level: str = "standard") -> str:
        """Build response guidance XML.

        Args:
            detail_level: "minimal", "standard", or "detailed"

        Returns:
            XML string for inclusion in additionalContext
        """
```

**Dependencies**: None (pure XML generation)

**Technology**: Python dataclasses + string templating

**Location**: `src/git_notes_memory/hooks/guidance_builder.py`

### Component 2: Namespace Parser

**Purpose**: Parse namespace hints from inline markers

**Responsibilities**:
- Detect `[remember:namespace]` pattern
- Detect `@memory:namespace` pattern
- Validate namespace against known namespaces
- Fall back to auto-detection or `learnings` on invalid

**Interfaces**:
```python
@dataclass(frozen=True)
class ParsedMarker:
    marker_type: str  # "remember" | "capture" | "memory"
    namespace: str | None  # Explicit namespace or None for auto-detect
    content: str  # Content after marker

def parse_inline_marker(text: str) -> ParsedMarker | None:
    """Parse inline marker with optional namespace.

    Examples:
        "[remember:decisions] Use PostgreSQL" -> ParsedMarker("remember", "decisions", "Use PostgreSQL")
        "[remember] TIL about pytest" -> ParsedMarker("remember", None, "TIL about pytest")
        "@memory:patterns API error handling" -> ParsedMarker("memory", "patterns", "API error handling")
    """
```

**Dependencies**: SignalDetector (for auto-detection when namespace=None)

**Location**: `src/git_notes_memory/hooks/namespace_parser.py`

### Component 3: PostToolUse Handler

**Purpose**: Inject relevant memories after file writes based on file domain

**Responsibilities**:
- Extract domain terms from file path
- Search for related memories via RecallService
- Format results as additionalContext XML
- Respect timeout and fail gracefully

**Interfaces**:
```python
# Input (from stdin)
{
    "tool_name": "Write",
    "tool_input": {"file_path": "/src/auth/jwt_handler.py", ...},
    "tool_response": {"success": true, ...},
    ...
}

# Output (to stdout)
{
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "<related_memories>...</related_memories>"
    }
}
```

**Dependencies**: RecallService, DomainExtractor

**Location**:
- Entry: `hooks/posttooluse.py`
- Handler: `src/git_notes_memory/hooks/post_tool_use_handler.py`

### Component 4: Domain Extractor

**Purpose**: Extract searchable terms from file paths

**Responsibilities**:
- Parse path components
- Filter common directories (src, lib, tests, etc.)
- Split filename on separators
- Limit to top N terms

**Interfaces**:
```python
def extract_domain_terms(file_path: str) -> list[str]:
    """Extract searchable domain terms from file path.

    Args:
        file_path: Absolute or relative file path

    Returns:
        List of domain terms (max 5)

    Examples:
        "src/auth/jwt_handler.py" -> ["auth", "jwt", "handler"]
        "tests/test_database.py" -> ["database"]
    """
```

**Dependencies**: None (pure path parsing)

**Location**: `src/git_notes_memory/hooks/domain_extractor.py`

### Component 5: PreCompact Handler

**Purpose**: Capture high-confidence uncaptured content before context compaction

**Responsibilities**:
- Read transcript from provided path
- Analyze for uncaptured signals using SessionAnalyzer
- Filter to high-confidence signals (≥0.85)
- Auto-capture top N signals
- Report captures via stderr (user-visible)

**Interfaces**:
```python
# Input (from stdin)
{
    "trigger": "auto",  # or "manual"
    "transcript_path": "/path/to/transcript.jsonl",
    "custom_instructions": "",  # Only set when trigger="manual"
    ...
}

# Output (to stdout) - minimal, PreCompact is side-effects only
{}

# Side effects:
# 1. Captures written to git notes via CaptureService
# 2. stderr shows: "Auto-captured 2 memories before compaction"
```

**Dependencies**: SessionAnalyzer (existing), CaptureService, SignalDetector

**Location**:
- Entry: `hooks/precompact.py`
- Handler: `src/git_notes_memory/hooks/pre_compact_handler.py`

## Data Design

### New Configuration Options

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HOOK_SESSION_START_INCLUDE_GUIDANCE` | bool | true | Include response guidance in SessionStart |
| `HOOK_SESSION_START_GUIDANCE_DETAIL` | enum | "standard" | minimal/standard/detailed |
| `HOOK_POST_TOOL_USE_ENABLED` | bool | true | Enable PostToolUse hook |
| `HOOK_POST_TOOL_USE_MIN_SIMILARITY` | float | 0.6 | Minimum similarity for memory recall |
| `HOOK_POST_TOOL_USE_MAX_RESULTS` | int | 3 | Maximum memories to inject |
| `HOOK_POST_TOOL_USE_TIMEOUT` | int | 5 | Timeout in seconds |
| `HOOK_PRE_COMPACT_ENABLED` | bool | true | Enable PreCompact hook |
| `HOOK_PRE_COMPACT_AUTO_CAPTURE` | bool | true | Auto-capture without prompt |
| `HOOK_PRE_COMPACT_MIN_CONFIDENCE` | float | 0.85 | Minimum confidence for auto-capture |
| `HOOK_PRE_COMPACT_MAX_CAPTURES` | int | 3 | Maximum memories to auto-capture |
| `HOOK_PRE_COMPACT_TIMEOUT` | int | 15 | Timeout in seconds |

### Data Flow: PostToolUse

```
Claude Code executes Write tool
         │
         ▼
PostToolUse hook triggered with tool_input
         │
         ▼
DomainExtractor.extract_domain_terms(file_path)
         │
         ▼
RecallService.search(terms, k=3, min_similarity=0.6)
         │
         ▼
Format results as XML additionalContext
         │
         ▼
Return JSON with hookSpecificOutput
         │
         ▼
Claude receives related memories in context
```

### Data Flow: PreCompact

```
Claude Code triggers compaction (auto or manual)
         │
         ▼
PreCompact hook triggered with transcript_path
         │
         ▼
SessionAnalyzer.analyze(transcript_path)
         │
         ▼
Filter signals: confidence >= 0.85
         │
         ▼
For each signal (up to 3):
    CaptureService.capture(namespace, summary, content)
         │
         ▼
Write summary to stderr (user visible)
         │
         ▼
Return empty JSON (side-effects only)
```

## Integration Points

### hooks.json Updates

```json
{
  "hooks": {
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
    ]
  }
}
```

### Existing Handler Modifications

**session_start_handler.py**:
- Import GuidanceBuilder
- Call `guidance_builder.build_guidance()` if enabled
- Prepend guidance to additionalContext

**user_prompt_handler.py**:
- Import namespace_parser
- Replace simple marker regex with namespace-aware parsing
- Use parsed namespace or auto-detect

**config_loader.py**:
- Add new environment variable mappings
- Add validation for enum values

## Testing Strategy

### Unit Testing

| Component | Tests | Coverage Target |
|-----------|-------|-----------------|
| GuidanceBuilder | XML generation, detail levels | 90% |
| NamespaceParser | All marker patterns, edge cases | 95% |
| DomainExtractor | Path parsing, filtering | 90% |
| PostToolUseHandler | Input/output, error handling | 85% |
| PreCompactHandler | Capture flow, stderr output | 85% |

### Integration Testing

| Scenario | Test |
|----------|------|
| Full SessionStart with guidance | Verify XML structure in output |
| Namespace marker capture | Verify memory in correct namespace |
| PostToolUse on Write | Verify related memories injected |
| PreCompact with signals | Verify captures created |

### Performance Testing

| Scenario | Target |
|----------|--------|
| PostToolUse latency | <100ms p99 |
| PreCompact with 3 captures | <15s |
| SessionStart with guidance | <10ms additional |

## Deployment Considerations

### Rollout Strategy

1. **Phase 1**: SessionStart guidance + namespace markers (low risk)
2. **Phase 2**: PostToolUse hook (medium risk - new hook)
3. **Phase 3**: PreCompact hook (medium risk - auto-capture)

### Configuration for Gradual Enablement

```bash
# Start conservative
HOOK_SESSION_START_INCLUDE_GUIDANCE=true
HOOK_SESSION_START_GUIDANCE_DETAIL=minimal
HOOK_POST_TOOL_USE_ENABLED=false
HOOK_PRE_COMPACT_ENABLED=false

# Then enable PostToolUse
HOOK_POST_TOOL_USE_ENABLED=true

# Finally enable PreCompact
HOOK_PRE_COMPACT_ENABLED=true
HOOK_PRE_COMPACT_AUTO_CAPTURE=true
```

### Rollback Plan

- Each hook can be individually disabled via environment variable
- No database migrations required
- No breaking changes to existing behavior
