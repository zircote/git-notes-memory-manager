# Subconsciousness: LLM-Powered Implicit Memory Capture

The subconsciousness layer provides intelligent, automatic memory capture from Claude Code sessions. It uses LLM analysis to extract valuable insights from conversations without requiring explicit capture markers.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [Review Workflow](#review-workflow)
- [Security: Adversarial Detection](#security-adversarial-detection)
- [Prompt Engineering](#prompt-engineering)
- [Troubleshooting](#troubleshooting)
- [API Reference](#api-reference)

---

## Overview

### What is the Subconsciousness Layer?

The subconsciousness layer is an intelligent background process that:

1. **Analyzes session transcripts** after Claude Code sessions end
2. **Extracts memory-worthy content** (decisions, learnings, patterns, blockers)
3. **Assigns confidence scores** to each potential memory
4. **Screens for adversarial content** before storage
5. **Routes memories by confidence**: auto-approve (high), queue for review (medium), discard (low)

### Key Benefits

- **Zero friction**: Memories are captured without explicit `/memory:capture` commands
- **Context-aware**: LLM understands the semantic value of content
- **Safe by default**: Adversarial screening prevents prompt injection attacks
- **Human-in-the-loop**: Medium-confidence captures require approval
- **Namespace-aware**: Auto-classifies into decisions, learnings, progress, etc.

---

## Quick Start

### 1. Enable Subconsciousness

Add to your shell configuration:

```bash
# Required: Enable the subconsciousness layer
export MEMORY_SUBCONSCIOUSNESS_ENABLED=true

# Required: Choose an LLM provider (anthropic, openai, or ollama)
export MEMORY_LLM_PROVIDER=anthropic

# Required for cloud providers: Set your API key
export ANTHROPIC_API_KEY=sk-ant-...  # For Anthropic
# or
export OPENAI_API_KEY=sk-...          # For OpenAI
# Ollama requires no API key
```

### 2. Work Normally

Use Claude Code as you normally would. The subconsciousness layer watches for:

- Decisions being made
- Technical learnings and insights
- Progress milestones
- Blockers and resolutions
- Patterns and best practices

### 3. Review Captures

After sessions, review pending memories:

```bash
# See pending implicit memories
/memory:review

# Or list without interaction
/memory:review --list
```

---

## Configuration

### Environment Variables

#### Core Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_SUBCONSCIOUSNESS_ENABLED` | Master switch for subconsciousness | `false` |
| `MEMORY_IMPLICIT_CAPTURE_ENABLED` | Enable implicit capture from transcripts | `true` |
| `MEMORY_LLM_PROVIDER` | LLM provider: `anthropic`, `openai`, `ollama` | `anthropic` |

#### Provider API Keys

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for Anthropic Claude |
| `OPENAI_API_KEY` | API key for OpenAI GPT |
| `OLLAMA_BASE_URL` | Base URL for Ollama (default: `http://localhost:11434`) |

#### Model Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_LLM_MODEL` | Model to use for analysis | Provider-specific |
| `MEMORY_LLM_TEMPERATURE` | Temperature for LLM calls | `0.1` |
| `MEMORY_LLM_MAX_TOKENS` | Max tokens for responses | `4096` |

**Default Models by Provider:**
- **Anthropic**: `claude-sonnet-4-20250514`
- **OpenAI**: `gpt-4o-mini`
- **Ollama**: `llama3.2`

#### Confidence Thresholds

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_AUTO_APPROVE_THRESHOLD` | Minimum confidence for auto-approval | `0.9` |
| `MEMORY_DISCARD_THRESHOLD` | Maximum confidence for discarding | `0.7` |

Memories with confidence:
- **>= 0.9**: Auto-approved and stored immediately
- **0.7 - 0.9**: Queued for human review
- **< 0.7**: Discarded as not memory-worthy

#### Pending Capture Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_PENDING_EXPIRY_DAYS` | Days before pending captures expire | `7` |
| `MEMORY_MAX_PENDING_CAPTURES` | Maximum pending captures stored | `100` |

#### Rate Limiting

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORY_LLM_RPM_LIMIT` | Requests per minute limit | `50` |
| `MEMORY_LLM_TPM_LIMIT` | Tokens per minute limit | `100000` |

### Example Configurations

#### Minimal (Local with Ollama)

```bash
export MEMORY_SUBCONSCIOUSNESS_ENABLED=true
export MEMORY_LLM_PROVIDER=ollama
# No API key needed - uses localhost:11434
```

#### Production (Anthropic)

```bash
export MEMORY_SUBCONSCIOUSNESS_ENABLED=true
export MEMORY_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export MEMORY_AUTO_APPROVE_THRESHOLD=0.95  # More conservative
export MEMORY_LLM_RPM_LIMIT=30             # Stay within quotas
```

#### Team Environment

```bash
export MEMORY_SUBCONSCIOUSNESS_ENABLED=true
export MEMORY_LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export HOOK_SESSION_START_FETCH_REMOTE=true  # Sync team memories
export HOOK_STOP_PUSH_REMOTE=true            # Share new memories
```

---

## How It Works

### Capture Pipeline

```
Session Ends (Stop hook)
       │
       ▼
┌──────────────────────┐
│ 1. Parse Transcript  │
│    Extract turns     │
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│ 2. Chunk Transcript  │
│    Max 4000 tokens   │
│    Context overlap   │
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│ 3. LLM Extraction    │
│    Identify memories │
│    Score confidence  │
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│ 4. Adversarial Check │
│    Screen threats    │
│    Fail-closed safe  │
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│ 5. Route by Score    │
│    ≥0.9 → Auto       │
│    ≥0.7 → Queue      │
│    <0.7 → Discard    │
└──────────────────────┘
```

### Confidence Scoring

Each potential memory is scored on 6 dimensions:

| Dimension | Description |
|-----------|-------------|
| **Relevance** | How relevant to the project/codebase |
| **Actionability** | Can it inform future decisions? |
| **Novelty** | Is it new information (not already captured)? |
| **Specificity** | Is it specific enough to be useful? |
| **Coherence** | Is the content well-structured? |
| **Overall** | Weighted average of all dimensions |

The **overall** score determines routing:

```python
overall = (
    relevance * 0.25 +
    actionability * 0.25 +
    novelty * 0.20 +
    specificity * 0.15 +
    coherence * 0.15
)
```

### Namespace Classification

The LLM automatically classifies memories into namespaces:

| Namespace | Triggers |
|-----------|----------|
| `decisions` | "We decided...", "Chose X over Y", architectural choices |
| `learnings` | "I learned...", "Discovered that...", insights |
| `progress` | "Completed...", "Implemented...", milestones |
| `blockers` | "Blocked by...", "Issue with...", problems |
| `patterns` | "Pattern for...", "Best practice...", reusable approaches |
| `research` | "Found that...", "Research shows...", external findings |

---

## Review Workflow

### Interactive Review

```bash
# Start interactive review
/memory:review
```

This shows pending captures and asks what you want to do:

1. **Review individually**: Go through each memory
2. **Approve all**: Approve all pending captures
3. **Do nothing**: Leave for later
4. **Cleanup**: Remove expired/old captures

### Direct Commands

```bash
# List pending without interaction
/memory:review --list

# Approve a specific capture (use first 8 chars of ID)
/memory:review --approve abc12345

# Reject a specific capture
/memory:review --reject abc12345

# Approve all pending
/memory:review --approve-all

# Clean up old captures
/memory:review --cleanup
```

### Capture States

| State | Description |
|-------|-------------|
| `pending` | Awaiting human review |
| `approved` | Approved and stored as memory |
| `rejected` | Rejected by user |
| `blocked` | Blocked by adversarial detection |
| `expired` | Exceeded pending expiry time |

### Understanding Pending Captures

When reviewing, you'll see:

```
### 1. [abc12345] Use PostgreSQL for persistence

- **Namespace**: decisions
- **Confidence**: 85%
- **Expires in**: 5 days

> We decided to use PostgreSQL instead of SQLite for the production
> database because we need concurrent write access and...
```

The confidence score indicates the LLM's certainty that this is memory-worthy content. Scores between 70-90% are queued because they're likely valuable but benefit from human judgment.

---

## Security: Adversarial Detection

### Why Adversarial Detection?

The subconsciousness layer processes conversation content that could contain:

- **Prompt injection**: Attempts to override LLM behavior
- **Data exfiltration**: Requests for sensitive information
- **Memory poisoning**: Malicious content designed to corrupt memories
- **Authority claims**: Fake system messages or admin commands

### How It Works

Every potential memory is screened before storage:

```
Content → AdversarialDetector → ThreatDetection
                                    │
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
             ThreatLevel        Patterns         should_block
             (none/low/       (list of           (true/false)
              medium/high/     matched
              critical)        patterns)
```

### Threat Levels

| Level | Description | Action |
|-------|-------------|--------|
| `none` | Safe content | Allow |
| `low` | Suspicious but benign | Allow with logging |
| `medium` | Potentially harmful | Block |
| `high` | Likely malicious | Block |
| `critical` | Definite attack | Block |

### Detected Patterns

- `prompt_injection`: Attempts to override instructions
- `authority_claim`: Fake system/admin messages
- `data_exfiltration`: Requests for credentials/secrets
- `memory_poisoning`: Malicious memory content
- `code_injection`: Shell commands, SQL injection, etc.

### Fail-Safe Behavior

The detector is **fail-closed** by default:

- **LLM exceptions**: Block content if `fail_closed=True` (default)
- **Parse errors**: Always block (potential response manipulation)
- **Timeout**: Block content (potential DoS)

This ensures security even when the detection system fails.

### False Positive Handling

The detector is tuned to avoid blocking legitimate content:

- Discussing security concepts ("prompt injection prevention")
- Mentioning credentials in debugging context
- Code review comments about vulnerabilities
- Security documentation

If legitimate content is blocked, you can:
1. Review and approve manually via `/memory:review`
2. Report the false positive for prompt tuning

---

## Prompt Engineering

### Extraction Prompt

The extraction prompt guides the LLM to identify memory-worthy content:

```python
from git_notes_memory.subconsciousness.prompts import get_extraction_prompt

prompt = get_extraction_prompt(
    transcript="...",
    project_context="Building a REST API with FastAPI",
    existing_summaries=["Already captured: Use SQLAlchemy for ORM"]
)
```

Key elements:
- **Project context**: Helps focus on relevant content
- **Existing summaries**: Prevents duplicate captures
- **Namespace definitions**: Guides classification
- **Confidence criteria**: Defines scoring dimensions

### Adversarial Prompt

The adversarial prompt screens for threats:

```python
from git_notes_memory.subconsciousness.prompts import get_adversarial_prompt

prompt = get_adversarial_prompt(content="...")
```

Key elements:
- **Threat pattern catalog**: Examples of each attack type
- **Context awareness**: Distinguishes discussion from attack
- **Severity guidelines**: When to block vs. allow

### Customizing Prompts

Prompts are in `src/git_notes_memory/subconsciousness/prompts/`:

```
prompts/
├── __init__.py          # Prompt factory functions
├── extraction.py        # Memory extraction templates
└── adversarial.py       # Threat detection templates
```

To customize, modify the template strings in these files. Key considerations:

1. **Preserve JSON output format**: The response parser expects specific fields
2. **Maintain confidence criteria**: Scoring must be consistent
3. **Keep threat patterns updated**: Add new attack patterns as discovered

---

## Troubleshooting

### Subconsciousness Not Working

**Symptom**: No implicit memories being captured

**Check**:
```bash
# Is it enabled?
echo $MEMORY_SUBCONSCIOUSNESS_ENABLED  # Should be "true"

# Is the provider configured?
echo $MEMORY_LLM_PROVIDER  # Should be anthropic/openai/ollama

# Is the API key set?
echo $ANTHROPIC_API_KEY | head -c 10  # Should show key prefix
```

**Solution**: Set required environment variables.

### All Captures Being Blocked

**Symptom**: Everything shows as "blocked" in review

**Check**:
```bash
# Check capture stats
/memory:review --list
```

If blocked_count is high, possible causes:
1. Adversarial detector is too aggressive (rare)
2. Session content contains attack patterns (intentional)
3. LLM response parsing is failing

**Solution**: Check error logs, review blocked content manually.

### High Token Usage

**Symptom**: API costs are higher than expected

**Check**:
- Transcript length (long sessions = more tokens)
- Model choice (GPT-4 > GPT-4o-mini)
- Rate limit settings

**Solution**:
```bash
# Use a cheaper model
export MEMORY_LLM_MODEL=gpt-4o-mini

# Reduce rate limits
export MEMORY_LLM_RPM_LIMIT=20
export MEMORY_LLM_TPM_LIMIT=50000
```

### Ollama Connection Issues

**Symptom**: "Connection refused" errors

**Check**:
```bash
# Is Ollama running?
curl http://localhost:11434/api/tags

# Is the model pulled?
ollama list
```

**Solution**:
```bash
# Start Ollama
ollama serve

# Pull the model
ollama pull llama3.2
```

### Pending Captures Not Expiring

**Symptom**: Old pending captures remain

**Check**:
```bash
# See expiration status
/memory:review --list
```

**Solution**:
```bash
# Run cleanup
/memory:review --cleanup

# Or reduce expiry time
export MEMORY_PENDING_EXPIRY_DAYS=3
```

### Debug Mode

Enable detailed logging:

```bash
export HOOK_DEBUG=true
```

This logs to stderr with detailed pipeline information.

---

## API Reference

### Python API

#### Check Availability

```python
from git_notes_memory.subconsciousness import is_subconsciousness_enabled

if is_subconsciousness_enabled():
    print("Subconsciousness is active")
```

#### Get LLM Client

```python
from git_notes_memory.subconsciousness import get_llm_client

client = get_llm_client()
response = await client.complete(
    "Summarize this: ...",
    system="You are a helpful assistant.",
    json_mode=True
)
print(response.content)
```

#### Implicit Capture Service

```python
from git_notes_memory.subconsciousness.implicit_capture_service import (
    get_implicit_capture_service
)

service = get_implicit_capture_service()

# Capture from a transcript
result = await service.capture_from_transcript(
    transcript="user: How should we handle caching?\nassistant: Use Redis...",
    session_id="session-123",
    project_context="E-commerce platform"
)

print(f"Captured: {result.capture_count}")
print(f"Auto-approved: {result.auto_approved_count}")

# Get pending captures
pending = service.get_pending_captures(limit=10)
for cap in pending:
    print(f"{cap.id}: {cap.memory.summary}")

# Approve a capture
service.approve_capture("capture-id")

# Reject a capture
service.reject_capture("capture-id")
```

#### Adversarial Detector

```python
from git_notes_memory.subconsciousness import get_adversarial_detector

detector = get_adversarial_detector()

result = await detector.analyze("Some content to check")

if result.should_block:
    print(f"Blocked: {result.detection.explanation}")
    print(f"Patterns: {result.detection.patterns_found}")
else:
    print("Content is safe")
```

### Hook Integration

The subconsciousness integrates via the Stop hook:

```python
from git_notes_memory.subconsciousness.hook_integration import (
    analyze_session_transcript,
    is_subconsciousness_available,
)

if is_subconsciousness_available():
    result = await analyze_session_transcript(
        transcript_path="/path/to/transcript.txt",
        session_id="session-123",
        timeout_seconds=30.0
    )

    if result.success:
        print(f"Captured {result.captured_count} memories")
        print(f"Auto-approved: {result.auto_approved_count}")
        print(f"Pending review: {result.pending_count}")
```

---

## See Also

- [User Guide](USER_GUIDE.md) - Core memory capture and recall
- [Developer Guide](DEVELOPER_GUIDE.md) - Architecture and internals
- [Hooks Reference](claude-code-hooks-reference.md) - Hook system details
