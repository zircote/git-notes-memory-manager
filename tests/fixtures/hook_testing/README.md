# Hook Script Manual Testing Fixtures

This directory contains test fixtures for manually testing the Claude Code hook scripts in `hooks/`.

## Overview

The hook scripts are designed to integrate with Claude Code's hook system. Each script:
- Reads JSON input from stdin
- Outputs JSON to stdout
- Exits with code 0 (non-blocking)
- Delegates to handler modules in `git_notes_memory.hooks`

## Test Fixtures

### Session Start Hook

**Purpose**: Inject memory context at session startup

**Test Fixture**: `session_start_input.json`
```json
{
  "cwd": "/path/to/project",
  "source": "startup"
}
```

**Expected Output**:
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<memory_context>...</memory_context>"
  }
}
```

**Manual Test Command**:
```bash
cd /path/to/project
cat tests/fixtures/hook_testing/session_start_input.json | python hooks/session_start.py
```

---

### User Prompt Submit Hook

**Purpose**: Detect capture-worthy signals in user prompts

**Test Fixtures**:
- `user_prompt_decision.json` - Decision signal
- `user_prompt_learning.json` - Learning signal
- `user_prompt_blocker.json` - Blocker signal
- `user_prompt_mundane.json` - No signals (mundane text)

**Example Input** (`user_prompt_decision.json`):
```json
{
  "userMessage": {
    "content": "I decided to use PostgreSQL instead of MySQL because it has better JSON support and more robust transaction handling for our use case."
  }
}
```

**Expected Output** (decision signal):
```json
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "action": "SUGGEST",
    "additionalContext": "<capture_suggestions>...</capture_suggestions>"
  }
}
```

**Manual Test Command**:
```bash
cat tests/fixtures/hook_testing/user_prompt_decision.json | python hooks/user_prompt.py
```

---

### Stop Hook

**Purpose**: Detect uncaptured content and sync index at session end

**Test Fixture**: `stop_input.json`
```json
{
  "transcriptFile": "tests/fixtures/hook_testing/sample_transcript.jsonl",
  "reason": "user_stop"
}
```

**Sample Transcript** (`sample_transcript.jsonl`):
```jsonl
{"role": "user", "content": "I decided to use Redis for caching"}
{"role": "assistant", "content": "Good choice for performance!"}
{"role": "user", "content": "I learned that connection pooling improves throughput"}
{"role": "assistant", "content": "Yes, it reduces overhead."}
```

**Expected Output**:
```json
{
  "continue": true,
  "hookSpecificOutput": {
    "hookEventName": "Stop",
    "uncapturedContent": "<uncaptured_memories>...</uncaptured_memories>",
    "syncStats": {
      "success": true,
      "stats": {
        "indexed": 3,
        "duration_ms": 42
      }
    }
  }
}
```

**Manual Test Command**:
```bash
cat tests/fixtures/hook_testing/stop_input.json | python hooks/stop.py
```

---

## Environment Variables

Set these before testing:

```bash
export HOOK_ENABLED=true
export HOOK_DEBUG=true  # Enable debug output
export HOOK_SESSION_START_ENABLED=true
export HOOK_USER_PROMPT_ENABLED=true
export HOOK_STOP_ENABLED=true
export HOOK_STOP_PROMPT_UNCAPTURED=true
export HOOK_STOP_SYNC_INDEX=true
```

## Testing Scenarios

### 1. Library Not Installed

Simulate ImportError by temporarily renaming the library:

```bash
# Make library import fail
mv src/git_notes_memory /tmp/git_notes_memory.bak

# Test graceful fallback
cat tests/fixtures/hook_testing/user_prompt_decision.json | python hooks/user_prompt.py

# Should output: {"continue": true}

# Restore library
mv /tmp/git_notes_memory.bak src/git_notes_memory
```

### 2. Invalid Input

Test with malformed JSON:

```bash
echo '{"bad json' | python hooks/session_start.py
# Should exit 0 with continue:true (non-blocking)
```

### 3. Hook Disabled

```bash
export HOOK_ENABLED=false
cat tests/fixtures/hook_testing/session_start_input.json | python hooks/session_start.py
# Should skip processing and exit 0
```

### 4. Performance

Test timing with `time`:

```bash
time cat tests/fixtures/hook_testing/user_prompt_decision.json | python hooks/user_prompt.py
# Should complete in <100ms
```

## Verification Checklist

For each hook script, verify:

- [ ] Executes without errors with valid input
- [ ] Produces correctly formatted JSON output
- [ ] Exits with code 0 in all cases (non-blocking)
- [ ] Handles ImportError gracefully (library not installed)
- [ ] Handles malformed input gracefully
- [ ] Respects HOOK_ENABLED=false
- [ ] Respects hook-specific enable flags
- [ ] Completes within performance budget (<100ms)
- [ ] Debug output works when HOOK_DEBUG=true

## Automated Testing

These manual fixtures complement the automated tests in:
- `tests/test_hook_handlers.py` - Handler unit tests
- `tests/test_hooks_integration.py` - Integration tests
- `tests/test_hooks_performance.py` - Performance benchmarks

Use this manual testing for:
- Smoke testing during development
- Verifying Claude Code integration
- Debugging hook behavior in real scenarios
