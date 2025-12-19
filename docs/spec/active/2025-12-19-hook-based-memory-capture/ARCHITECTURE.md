---
document_type: architecture
project_id: SPEC-2025-12-19-001
version: 1.0.0
last_updated: 2025-12-19T00:00:00Z
status: draft
---

# Hook-Based Memory Capture - Technical Architecture

## System Overview

This enhancement adds hook-based integration to the existing Memory Capture Plugin, enabling automatic context injection at session start and intelligent memory capture detection during work sessions.

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Claude Code Runtime                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │SessionStart │  │UserPrompt   │  │PostToolUse  │  │     Stop            │  │
│  │   Event     │  │Submit Event │  │   Event     │  │    Event            │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                │                     │            │
└─────────┼────────────────┼────────────────┼─────────────────────┼────────────┘
          │                │                │                     │
          ▼                ▼                ▼                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Hook Handler Layer                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ session_start.py│  │user_prompt.py   │  │        stop.py               │  │
│  │                 │  │                 │  │                              │  │
│  │ - Load context  │  │ - Signal detect │  │ - Session summary            │  │
│  │ - Build XML     │  │ - Novelty check │  │ - Capture prompt             │  │
│  │ - Inject memory │  │ - Suggest capture│ │ - Sync index                 │  │
│  └────────┬────────┘  └────────┬────────┘  └─────────────┬────────────────┘  │
│           │                    │                         │                   │
│           └────────────────────┼─────────────────────────┘                   │
│                                │                                             │
│                                ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │                        HookServices                                  │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────┐  │    │
│  │  │ ContextBuilder  │  │ SignalDetector  │  │ CaptureDecider       │  │    │
│  │  │                 │  │                 │  │ (prompt-type)        │  │    │
│  │  │ - build_xml()   │  │ - detect()      │  │                      │  │    │
│  │  │ - filter()      │  │ - classify()    │  │ - should_capture()   │  │    │
│  │  │ - budget()      │  │ - confidence()  │  │ - suggest_namespace()│  │    │
│  │  └────────┬────────┘  └────────┬────────┘  └───────────┬──────────┘  │    │
│  │           │                    │                       │             │    │
│  └───────────┼────────────────────┼───────────────────────┼─────────────┘    │
│              │                    │                       │                  │
└──────────────┼────────────────────┼───────────────────────┼──────────────────┘
               │                    │                       │
               ▼                    ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Existing Memory Capture Plugin Core                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────────────────┐ │
│  │ RecallService  │    │ CaptureService │    │     IndexService           │ │
│  │                │    │                │    │                            │ │
│  │ - search()     │    │ - capture()    │    │ - search_vector()          │ │
│  │ - context()    │    │ - capture_*()  │    │ - get_stats()              │ │
│  │ - hydrate()    │    │                │    │                            │ │
│  └───────┬────────┘    └───────┬────────┘    └─────────────┬──────────────┘ │
│          │                     │                           │                │
│          ▼                     ▼                           ▼                │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────────────────┐ │
│  │EmbeddingService│    │    GitOps      │    │    SyncService             │ │
│  └────────────────┘    └────────────────┘    └────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
               │                    │                       │
               ▼                    ▼                       ▼
┌─────────────────┐      ┌────────────────────┐      ┌────────────────────────┐
│   Git Notes     │      │  SQLite + vec0     │      │   Models Cache         │
│ refs/notes/mem/*│      │ index.db           │      │ all-MiniLM-L6-v2/      │
└─────────────────┘      └────────────────────┘      └────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Integration | Enhance existing plugin | Reuse services, single installation |
| Context format | XML-structured | Hierarchical, parseable, clear boundaries |
| Capture detection | LLM-assisted (prompt hooks) | Context-aware decisions |
| Token management | Adaptive budget | Scale with project complexity |
| Hook handlers | Python scripts | Match existing plugin language |

## Component Design

### Component 1: ContextBuilder

- **Purpose**: Builds XML-structured memory context for session injection
- **Responsibilities**:
  - Query relevant memories from RecallService
  - Filter by project scope and relevance
  - Calculate adaptive token budget
  - Build hierarchical XML structure
  - Prioritize working memory over semantic context
- **Interfaces**:
  ```python
  class ContextBuilder:
      def build_context(self, project: str, session_source: str) -> str:
          """Build XML memory context for injection."""

      def calculate_budget(self, project: str) -> TokenBudget:
          """Determine token allocation based on project complexity."""

      def filter_memories(self, memories: List[Memory], budget: TokenBudget) -> List[Memory]:
          """Filter and prioritize memories within token budget."""

      def to_xml(self, context: MemoryContext) -> str:
          """Convert memory context to XML string."""
  ```
- **Dependencies**: RecallService, IndexService, Config
- **Technology**: Python, xml.etree.ElementTree

### Component 2: SignalDetector

- **Purpose**: Identifies memorable moments in user prompts and tool outputs
- **Responsibilities**:
  - Pattern matching for capture signals
  - Confidence scoring for each signal
  - Namespace suggestion based on signal type
  - Novelty detection against existing memories
- **Interfaces**:
  ```python
  class SignalDetector:
      def detect(self, text: str) -> List[CaptureSignal]:
          """Detect capture signals in text."""

      def classify(self, signal: CaptureSignal) -> str:
          """Classify signal into namespace."""

      def score_confidence(self, signal: CaptureSignal, context: SessionContext) -> float:
          """Calculate confidence score for signal."""

      def check_novelty(self, content: str, existing_memories: List[Memory]) -> float:
          """Check if content is novel vs existing memories."""
  ```
- **Dependencies**: EmbeddingService, RecallService
- **Technology**: Python, regex, embeddings

### Component 3: CaptureDecider (Prompt-Type Hook)

- **Purpose**: LLM-assisted decision making for memory capture
- **Responsibilities**:
  - Evaluate detected signals in context
  - Decide capture action (auto, suggest, skip)
  - Generate capture metadata
  - Format decision response
- **Interfaces**:
  ```python
  class CaptureDecider:
      def should_capture(self, signals: List[CaptureSignal], context: SessionContext) -> CaptureDecision:
          """Decide whether to capture based on signals and context."""

      def suggest_metadata(self, signal: CaptureSignal) -> CaptureMetadata:
          """Generate suggested summary, tags, namespace."""

      def format_prompt(self, signals: List[CaptureSignal]) -> str:
          """Format prompt for LLM decision hook."""
  ```
- **Dependencies**: SignalDetector
- **Technology**: Python, prompt-type hook integration

### Component 4: Hook Handlers

Four Python scripts that handle Claude Code hook events:

#### session_start.py
```python
"""SessionStart hook handler - Context injection."""

def main():
    # Read hook input from stdin
    input_data = json.load(sys.stdin)

    # Build context
    builder = ContextBuilder()
    context = builder.build_context(
        project=detect_project(input_data['cwd']),
        session_source=input_data.get('source', 'startup')
    )

    # Output for injection
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context
        }
    }

    print(json.dumps(output))
    sys.exit(0)
```

#### user_prompt.py (Optional)
```python
"""UserPromptSubmit hook handler - Capture signal detection."""

def main():
    input_data = json.load(sys.stdin)
    prompt = input_data.get('prompt', '')

    # Detect signals
    detector = SignalDetector()
    signals = detector.detect(prompt)

    if not signals:
        sys.exit(0)  # No signals, no action

    # Check novelty
    novel_signals = [s for s in signals if detector.check_novelty(s.content) > 0.3]

    if not novel_signals:
        sys.exit(0)  # Not novel enough

    # Inject capture suggestion context
    context = format_capture_suggestion(novel_signals)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context
        }
    }

    print(json.dumps(output))
    sys.exit(0)
```

#### stop.py
```python
"""Stop hook handler - Session capture prompt."""

def main():
    input_data = json.load(sys.stdin)

    # Read session transcript for potential captures
    transcript_path = input_data.get('transcript_path')
    session_content = analyze_session(transcript_path)

    # Check if already prompted this session
    if input_data.get('stop_hook_active', False):
        sys.exit(0)  # Already ran once

    # Detect uncaptured memorable content
    uncaptured = detect_uncaptured_memories(session_content)

    if not uncaptured:
        # Sync index and exit
        sync_index()
        sys.exit(0)

    # Prompt for capture
    output = {
        "decision": "block",
        "reason": f"Detected {len(uncaptured)} potential memories to capture. Consider using /remember before ending session."
    }

    print(json.dumps(output))
    sys.exit(0)
```

## Data Design

### New Data Models

```python
@dataclass
class CaptureSignal:
    """A detected signal indicating memorable content."""
    type: SignalType              # decision, learning, blocker, explicit, preference
    match: str                    # The matched text
    confidence: float             # 0.0-1.0 confidence score
    context: str                  # Surrounding context
    suggested_namespace: str      # Inferred namespace

class SignalType(Enum):
    DECISION = "decision"         # "I chose", "decided to", "we'll go with"
    LEARNING = "learning"         # "I learned", "TIL", "turns out"
    BLOCKER = "blocker"           # "blocked by", "stuck on", "can't because"
    RESOLUTION = "resolution"     # "fixed", "resolved", "solved"
    PREFERENCE = "preference"     # "I prefer", "I like", "I want"
    EXPLICIT = "explicit"         # "remember this", "save this", "note that"

@dataclass
class CaptureDecision:
    """Decision from capture decider."""
    action: CaptureAction         # auto, suggest, skip
    signals: List[CaptureSignal]  # Signals that led to decision
    suggested_captures: List[SuggestedCapture]
    reason: str                   # Explanation of decision

class CaptureAction(Enum):
    AUTO = "auto"                 # Capture automatically (high confidence)
    SUGGEST = "suggest"           # Suggest to user (medium confidence)
    SKIP = "skip"                 # Don't capture (low confidence)

@dataclass
class SuggestedCapture:
    """A suggested memory capture."""
    namespace: str
    summary: str
    content: str
    tags: List[str]
    confidence: float

@dataclass
class TokenBudget:
    """Token allocation for context injection."""
    total: int                    # Total tokens available
    working_memory: int           # For blockers, recent decisions
    semantic_context: int         # For relevant learnings
    commands: int                 # For command hints

@dataclass
class MemoryContext:
    """Structured memory context for injection."""
    project: str
    spec_id: Optional[str]
    token_budget: TokenBudget
    working_memory: WorkingMemory
    semantic_context: SemanticContext
    commands: List[str]

@dataclass
class WorkingMemory:
    """High-priority, current working context."""
    active_blockers: List[Memory]
    recent_decisions: List[Memory]
    pending_actions: List[Memory]

@dataclass
class SemanticContext:
    """Semantically relevant memories."""
    relevant_learnings: List[Memory]
    related_patterns: List[Memory]
```

### Signal Detection Patterns

```python
SIGNAL_PATTERNS = {
    SignalType.DECISION: [
        r"(?i)\b(I|we)\s+(decided|chose|selected|picked|went with)\b",
        r"(?i)\bthe decision (is|was)\b",
        r"(?i)\bwe('ll| will)\s+go with\b",
        r"(?i)\bafter (considering|evaluating),?\s+(I|we)\b",
    ],
    SignalType.LEARNING: [
        r"(?i)\b(I|we)\s+(learned|realized|discovered|found out)\b",
        r"(?i)\bTIL\b",
        r"(?i)\bturns out\b",
        r"(?i)\binteresting(ly)?[,:]?\s+",
        r"(?i)\bkey (insight|takeaway|learning)\b",
    ],
    SignalType.BLOCKER: [
        r"(?i)\bblocked (by|on)\b",
        r"(?i)\bstuck (on|with)\b",
        r"(?i)\bcan('t| not)\s+.*\s+because\b",
        r"(?i)\bissue (with|is)\b",
        r"(?i)\bproblem[:\s]",
    ],
    SignalType.RESOLUTION: [
        r"(?i)\b(fixed|resolved|solved|figured out)\b",
        r"(?i)\bworkaround[:\s]",
        r"(?i)\bsolution[:\s]",
        r"(?i)\bthat worked\b",
    ],
    SignalType.PREFERENCE: [
        r"(?i)\bI (prefer|like|want|need)\b",
        r"(?i)\bmy preference\b",
        r"(?i)\bI('d| would) rather\b",
    ],
    SignalType.EXPLICIT: [
        r"(?i)\bremember this\b",
        r"(?i)\bsave this\b",
        r"(?i)\bnote (that|this)\b",
        r"(?i)\bfor (future|later) reference\b",
        r"(?i)\bdon't forget\b",
    ],
}
```

### XML Schema

```xml
<!-- memory_context.xsd (logical schema) -->
<xs:schema>
  <xs:element name="memory_context">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="project_scope">
          <xs:complexType>
            <xs:element name="project" type="xs:string"/>
            <xs:element name="spec_id" type="xs:string" minOccurs="0"/>
            <xs:element name="token_budget" type="xs:integer"/>
          </xs:complexType>
        </xs:element>
        <xs:element name="working_memory">
          <xs:complexType>
            <xs:element name="active_blockers" minOccurs="0"/>
            <xs:element name="recent_decisions" minOccurs="0"/>
            <xs:element name="pending_actions" minOccurs="0"/>
          </xs:complexType>
        </xs:element>
        <xs:element name="semantic_context">
          <xs:complexType>
            <xs:element name="relevant_learnings" minOccurs="0"/>
            <xs:element name="related_patterns" minOccurs="0"/>
          </xs:complexType>
        </xs:element>
        <xs:element name="commands" minOccurs="0"/>
      </xs:sequence>
      <xs:attribute name="source" type="xs:string"/>
      <xs:attribute name="timestamp" type="xs:dateTime"/>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

### Data Flow

```
SessionStart Flow:
┌────────────────┐
│ Claude Code    │
│ Session Start  │
└───────┬────────┘
        │
        ▼
┌────────────────┐     ┌─────────────────┐
│ session_start  │────▶│ ContextBuilder  │
│    .py         │     │ .build_context()│
└───────┬────────┘     └────────┬────────┘
        │                       │
        │                       ▼
        │              ┌─────────────────┐
        │              │  RecallService  │
        │              │ .search()       │
        │              │ .context()      │
        │              └────────┬────────┘
        │                       │
        │                       ▼
        │              ┌─────────────────┐
        │              │ XML Context     │
        │              │ Generation      │
        │              └────────┬────────┘
        │                       │
        ▼                       ▼
┌────────────────────────────────────────┐
│  hookSpecificOutput.additionalContext  │
│                                        │
│  <memory_context>                      │
│    <project_scope>...</project_scope>  │
│    <working_memory>...</working_memory>│
│    ...                                 │
│  </memory_context>                     │
└────────────────────────────────────────┘
        │
        ▼
┌────────────────┐
│ Claude Session │
│ (with context) │
└────────────────┘


Capture Detection Flow:
┌────────────────┐
│ User Prompt    │
│ Submitted      │
└───────┬────────┘
        │
        ▼
┌────────────────┐     ┌─────────────────┐
│ user_prompt    │────▶│ SignalDetector  │
│    .py         │     │ .detect()       │
└───────┬────────┘     └────────┬────────┘
        │                       │
        │                       ▼
        │              ┌─────────────────┐
        │              │ Check Novelty   │
        │              │ (vs existing)   │
        │              └────────┬────────┘
        │                       │
        │         ┌─────────────┴─────────────┐
        │         │                           │
        │         ▼                           ▼
        │  ┌────────────┐             ┌────────────┐
        │  │ Novel      │             │ Not Novel  │
        │  │ (score>0.3)│             │ (skip)     │
        │  └─────┬──────┘             └────────────┘
        │        │
        │        ▼
        │  ┌─────────────────┐
        │  │ CaptureDecider  │
        │  │ (prompt hook)   │
        │  └────────┬────────┘
        │           │
        │     ┌─────┴─────┬─────────────┐
        │     ▼           ▼             ▼
        │  ┌──────┐   ┌───────┐    ┌──────┐
        │  │ AUTO │   │SUGGEST│    │ SKIP │
        │  └──┬───┘   └───┬───┘    └──────┘
        │     │           │
        │     ▼           ▼
        │  ┌──────────────────────────────┐
        │  │ Inject capture suggestion    │
        │  │ or auto-capture              │
        │  └──────────────────────────────┘
        │
        ▼
┌────────────────┐
│ Continue to    │
│ Claude         │
└────────────────┘
```

## API Design

### Hook Handler Scripts

All hook handlers follow the same input/output contract:

**Input (stdin)**: JSON with hook event data
**Output (stdout)**: JSON with hook response
**Exit codes**: 0 = success, 2 = block, other = error

### ContextBuilder API

```python
# Public API
def build_session_context(project: str, source: str = "startup") -> str:
    """
    Build XML memory context for session start.

    Args:
        project: Project identifier (from cwd detection)
        source: Session source (startup, resume, clear, compact)

    Returns:
        XML string for additionalContext injection
    """

def get_context_budget(project: str) -> TokenBudget:
    """
    Calculate token budget based on project complexity.

    Args:
        project: Project identifier

    Returns:
        TokenBudget with allocations
    """
```

### SignalDetector API

```python
# Public API
def detect_signals(text: str) -> List[CaptureSignal]:
    """
    Detect capture signals in text.

    Args:
        text: User prompt or tool output text

    Returns:
        List of detected signals with confidence scores
    """

def check_novelty(content: str, limit: int = 10) -> float:
    """
    Check if content is novel vs existing memories.

    Args:
        content: Content to check
        limit: Number of similar memories to compare

    Returns:
        Novelty score (0.0 = duplicate, 1.0 = completely new)
    """
```

### Configuration Extensions

```toml
# ~/.local/share/memory-plugin/config.toml additions

[hooks]
enabled = true                    # Master switch for hook functionality

[hooks.session_start]
enabled = true                    # Enable SessionStart context injection
budget_mode = "adaptive"          # adaptive, fixed, or unlimited
fixed_budget = 1000               # Token budget if mode = fixed

[hooks.capture_detection]
enabled = false                   # Enable UserPromptSubmit detection (opt-in)
min_confidence = 0.7              # Minimum confidence for suggestions
auto_capture_threshold = 0.95     # Auto-capture above this confidence
novelty_threshold = 0.3           # Minimum novelty to consider capture

[hooks.stop]
enabled = true                    # Enable Stop hook capture prompts
prompt_uncaptured = true          # Prompt if uncaptured memories detected

[hooks.prompt_type]
use_local_llm = false             # Use local LLM for prompt hooks (not Claude)
timeout = 30                      # Prompt hook timeout in seconds
```

## Integration Points

### Plugin Structure Updates

```
memory-plugin/
├── .claude-plugin/
│   └── plugin.json              # Updated with hook registrations
├── commands/
│   ├── remember.md              # Existing
│   ├── recall.md                # Existing
│   └── ...
├── hooks/
│   ├── hooks.json               # Hook configuration
│   ├── session_start.py         # NEW: SessionStart handler
│   ├── user_prompt.py           # NEW: UserPromptSubmit handler (optional)
│   ├── stop.py                  # UPDATED: Enhanced Stop handler
│   └── userpromptsubmit.py      # EXISTING: Basic prompt capture
├── src/git_notes_memory/
│   ├── hooks/                   # NEW: Hook services module
│   │   ├── __init__.py
│   │   ├── context_builder.py   # ContextBuilder class
│   │   ├── signal_detector.py   # SignalDetector class
│   │   ├── capture_decider.py   # CaptureDecider class
│   │   └── xml_formatter.py     # XML generation utilities
│   └── ...                      # Existing modules
└── ...
```

### hooks.json Updates

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py",
            "timeout": 5
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/user_prompt.py",
            "timeout": 2
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/stop.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## Security Design

### Hook Script Security

```python
# All hook scripts should:

# 1. Validate input JSON
def validate_hook_input(data: dict) -> bool:
    required_fields = ['session_id', 'cwd', 'hook_event_name']
    return all(field in data for field in required_fields)

# 2. Handle errors gracefully
try:
    main()
except Exception as e:
    print(f"Hook error: {e}", file=sys.stderr)
    sys.exit(0)  # Non-blocking failure

# 3. Respect timeouts
signal.alarm(timeout)  # Set alarm for timeout

# 4. Read transcript read-only
with open(transcript_path, 'r') as f:
    content = f.read()  # Never write to transcript
```

### Content Validation

```python
def validate_memory_content(content: str) -> bool:
    """Validate content before capture."""
    # Check length
    if len(content.encode('utf-8')) > 102400:  # 100KB limit
        return False

    # Check for potential secrets (warning only)
    secret_patterns = [
        r'(?i)api[_-]?key\s*[:=]\s*\S+',
        r'(?i)password\s*[:=]\s*\S+',
        r'(?i)secret\s*[:=]\s*\S+',
    ]
    for pattern in secret_patterns:
        if re.search(pattern, content):
            warn("Potential secret detected in content")

    return True
```

## Performance Considerations

### Expected Load

- SessionStart hooks per day: 10-50 (each session start)
- Capture detection per session: 20-100 prompts analyzed
- Stop hooks per day: 10-50

### Performance Targets

| Operation | Target | Technique |
|-----------|--------|-----------|
| SessionStart context build | ≤2000ms | Cached queries, limited results |
| Signal detection | ≤100ms | Regex compilation, early exit |
| Novelty check | ≤300ms | Top-K similarity only |
| XML generation | ≤50ms | String building, no DOM |
| Stop hook analysis | ≤1000ms | Summary only, no full parse |

### Optimization Strategies

1. **Context caching**: Cache context for same project/session (invalidate on capture)
2. **Lazy signal detection**: Only run on prompts >50 chars
3. **Compiled patterns**: Pre-compile all regex patterns
4. **Embedding cache**: Reuse embeddings from recent queries
5. **Budget-based filtering**: Stop processing once budget reached

## Testing Strategy

### Unit Testing

- ContextBuilder: Test XML generation, budget calculation
- SignalDetector: Test pattern matching, confidence scoring
- CaptureDecider: Test decision logic, threshold handling

### Integration Testing

- End-to-end SessionStart → context injection
- Signal detection → capture suggestion flow
- Stop hook → sync index

### Hook Testing

```bash
# Test hook scripts directly
cat > test_input.json << 'EOF'
{
  "session_id": "test-123",
  "cwd": "/path/to/project",
  "hook_event_name": "SessionStart",
  "source": "startup"
}
EOF

cat test_input.json | python3 hooks/session_start.py | jq .
```

## Future Considerations

1. **Cross-session learning**: Track which injected memories were useful
2. **Feedback loop**: Adjust confidence thresholds based on user overrides
3. **Custom signal patterns**: User-defined patterns for domain-specific captures
4. **Multi-project context**: Aggregate context from related projects
5. **Memory access tracking**: Log which memories Claude references
