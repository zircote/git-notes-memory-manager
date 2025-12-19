# Claude Code Hooks Complete Reference

> A comprehensive guide to all hook events, return formats, context steering, and configurations for Claude Code hook development.

## Table of Contents

- [Overview](#overview)
- [Hook Architecture](#hook-architecture)
- [Common Input Fields](#common-input-fields)
- [Hook Events Reference](#hook-events-reference)
  - [UserPromptSubmit](#1-userpromptsubmit)
  - [PreToolUse](#2-pretooluse)
  - [PostToolUse](#3-posttooluse)
  - [PermissionRequest](#4-permissionrequest)
  - [Notification](#5-notification)
  - [Stop](#6-stop)
  - [SubagentStop](#7-subagentstop)
  - [PreCompact](#8-precompact)
  - [SessionStart](#9-sessionstart)
  - [SessionEnd](#10-sessionend)
- [Exit Code Behavior](#exit-code-behavior)
- [Return Formats Reference](#return-formats-reference)
  - [Output Methods](#output-methods)
  - [Common JSON Fields](#common-json-fields)
  - [Hook-Specific Output Schemas](#hook-specific-output-schemas)
- [Context Steering Guide](#context-steering-guide)
  - [Context Injection Points](#context-injection-points)
  - [Steering Mechanisms](#steering-mechanisms)
  - [Practical Patterns](#practical-patterns)
- [Matcher Patterns](#matcher-patterns)
- [Environment Variables](#environment-variables)
- [Configuration Locations](#configuration-locations)
- [Hook Types](#hook-types)
- [Security Considerations](#security-considerations)
- [Debugging](#debugging)

---

## Overview

Claude Code hooks are user-defined shell commands or scripts that execute automatically at predetermined points in Claude Code's workflow. They provide **deterministic control** over Claude's behavior, enabling:

- **Automation**: Eliminate repetitive manual steps (formatting, linting, approvals)
- **Enforcement**: Apply project-specific rules automatically (block dangerous commands, validate paths)
- **Context Injection**: Feed dynamic information to Claude without manual effort
- **Observability**: Log, audit, and monitor all agent activities

Hooks execute in your local environment with your user permissions, receiving event information via `stdin` (JSON) and communicating back through exit codes and `stdout`.

---

## Hook Architecture

### Execution Flow

```
┌─────────────────┐
│  Event Occurs   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Matcher Check   │  (for applicable events)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Hook Receives  │
│  JSON via stdin │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Hook Executes  │
│  (parallel if   │
│   multiple)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Exit Code +    │
│  stdout/stderr  │
│  Determines     │
│  Outcome        │
└─────────────────┘
```

### Key Characteristics

| Characteristic | Description |
|----------------|-------------|
| **Parallelism** | Multiple hooks matching the same event run in parallel |
| **Deduplication** | Identical commands are automatically deduplicated |
| **Timeout** | Default 60 seconds, configurable per hook |
| **Isolation** | Each hook runs in its own shell process |
| **Permissions** | Hooks execute with your user permissions |

---

## Common Input Fields

All hooks receive a JSON payload via `stdin` containing these common fields:

```typescript
interface CommonHookInput {
  /** Unique identifier for the current session */
  session_id: string;
  
  /** Absolute path to the conversation transcript JSONL file */
  transcript_path: string;
  
  /** Current working directory when the hook is invoked */
  cwd: string;
  
  /** Current permission mode for the session */
  permission_mode: "default" | "plan" | "acceptEdits" | "bypassPermissions";
  
  /** Name of the hook event that triggered this execution */
  hook_event_name: string;
}
```

### Field Details

#### `session_id`
- **Type**: `string`
- **Description**: A unique UUID identifying the current Claude Code session
- **Example**: `"00893aaf-19fa-41d2-8238-13269b9b3ca0"`
- **Use Cases**: Session-specific logging, state management, correlation across hooks

#### `transcript_path`
- **Type**: `string`
- **Description**: Absolute filesystem path to the JSONL file containing the conversation transcript
- **Example**: `"~/.claude/projects/my-project/00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl"`
- **Use Cases**: Transcript analysis, backup, chat history extraction

#### `cwd`
- **Type**: `string`
- **Description**: The current working directory when the hook was invoked
- **Example**: `"/Users/developer/projects/my-app"`
- **Use Cases**: Relative path resolution, project detection

#### `permission_mode`
- **Type**: `string` (enum)
- **Description**: The current permission level for the session
- **Values**:
  - `"default"` - Standard permission prompts for each action
  - `"plan"` - Planning mode, no execution
  - `"acceptEdits"` - Auto-accept file edits
  - `"bypassPermissions"` - No permission prompts (dangerous)
- **Use Cases**: Conditional hook behavior based on trust level

#### `hook_event_name`
- **Type**: `string`
- **Description**: The name of the event that triggered this hook
- **Values**: `"UserPromptSubmit"`, `"PreToolUse"`, `"PostToolUse"`, `"PermissionRequest"`, `"Notification"`, `"Stop"`, `"SubagentStop"`, `"PreCompact"`, `"SessionStart"`, `"SessionEnd"`
- **Use Cases**: Generic hooks that handle multiple event types

---

## Hook Events Reference

### 1. UserPromptSubmit

**Lifecycle Position**: Fires immediately when the user submits a prompt, **before** Claude processes it.

#### Purpose
Intercept and process user input before it reaches Claude. This is your first line of defense and context injection point.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | No |
| **Can Block** | Yes (exit code 2 or `decision: "block"`) |
| **Context Injection** | Yes (`stdout` on exit 0 is added to Claude's context) |

#### Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "UserPromptSubmit",
  "prompt": "Write a function to calculate the factorial of a number"
}
```

#### Input Field Details

| Field | Type | Description |
|-------|------|-------------|
| `prompt` | `string` | The complete prompt text that the user submitted |

#### Output Behavior

| Exit Code | Behavior |
|-----------|----------|
| `0` | Success - `stdout` (plain text or JSON) is **added to Claude's context** |
| `2` | Blocking - Prompt is **erased and blocked**, `stderr` shown to user only |
| Other | Non-blocking error - `stderr` shown in verbose mode, prompt proceeds |

#### JSON Output Schema

```json
{
  "decision": "block",
  "reason": "Explanation shown to user when blocking",
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "Context string added to the conversation"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision` | `"block"` \| `undefined` | No | Set to `"block"` to prevent prompt processing |
| `reason` | `string` | When blocking | Explanation shown to user (not added to context) |
| `hookSpecificOutput.additionalContext` | `string` | No | Context added to conversation if not blocked |

---

### 2. PreToolUse

**Lifecycle Position**: Fires after Claude decides to use a tool but **before** execution.

#### Purpose
Inspect, modify, or block tool calls before they execute. Primary control point for preventing dangerous operations.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | Yes (matches `tool_name`) |
| **Can Block** | Yes (exit code 2 or `permissionDecision: "deny"`) |
| **Can Modify Input** | Yes (via `updatedInput`) |

#### Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/path/to/file.txt",
    "content": "file content"
  },
  "tool_use_id": "toolu_01ABC123..."
}
```

#### Input Field Details

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `string` | Name of the tool being invoked |
| `tool_input` | `object` | Input parameters for the tool (structure varies by tool) |
| `tool_use_id` | `string` | Unique identifier for this tool invocation |

#### Common `tool_input` Structures

**Write Tool:**
```json
{
  "file_path": "/path/to/file.txt",
  "content": "file content"
}
```

**Edit Tool:**
```json
{
  "file_path": "/path/to/file.txt",
  "old_string": "text to find",
  "new_string": "replacement text"
}
```

**Bash Tool:**
```json
{
  "command": "npm test",
  "description": "Run the test suite"
}
```

**Read Tool:**
```json
{
  "file_path": "/path/to/file.txt",
  "offset": 0,
  "limit": 1000
}
```

#### Output Behavior

| Exit Code | Behavior |
|-----------|----------|
| `0` | Success - JSON output processed for permission decision and input modification |
| `2` | Blocking - Tool call **blocked**, `stderr` fed back to Claude |
| Other | Non-blocking error - `stderr` shown in verbose mode, tool proceeds |

#### JSON Output Schema

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Auto-approved safe operation",
    "updatedInput": {
      "file_path": "/modified/path.txt"
    }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `hookSpecificOutput.permissionDecision` | `"allow"` \| `"deny"` \| `"ask"` | No | Permission decision |
| `hookSpecificOutput.permissionDecisionReason` | `string` | No | Reason for the decision |
| `hookSpecificOutput.updatedInput` | `object` | No | Modified tool parameters |

**Permission Decision Values:**
- `"allow"` - Bypasses the permission system. Reason shown to user but not Claude.
- `"deny"` - Prevents tool execution. Reason shown to Claude.
- `"ask"` - Asks user to confirm in the UI. Reason shown to user but not Claude.

---

### 3. PostToolUse

**Lifecycle Position**: Fires **after** a tool completes successfully.

#### Purpose
React to completed tool operations. Ideal for automated follow-up actions like formatting, linting, or providing feedback.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | Yes (matches `tool_name`) |
| **Can Block** | Yes (`decision: "block"` provides feedback to Claude) |
| **Can Add Context** | Yes (via `additionalContext`) |

#### Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/path/to/file.txt",
    "content": "file content"
  },
  "tool_response": {
    "filePath": "/path/to/file.txt",
    "success": true
  },
  "tool_use_id": "toolu_01ABC123..."
}
```

#### Input Field Details

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `string` | Name of the tool that was executed |
| `tool_input` | `object` | Input parameters that were passed to the tool |
| `tool_response` | `object` | Response/output from the tool execution |
| `tool_use_id` | `string` | Unique identifier for this tool invocation |

#### Output Behavior

| Exit Code | Behavior |
|-----------|----------|
| `0` | Success - JSON output processed, `additionalContext` added to Claude's context |
| `2` | Blocking - `stderr` fed back to Claude as feedback |
| Other | Non-blocking error - `stderr` shown in verbose mode |

#### JSON Output Schema

```json
{
  "decision": "block",
  "reason": "Explanation fed back to Claude",
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "Additional information for Claude to consider"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision` | `"block"` \| `undefined` | No | Set to `"block"` to automatically prompt Claude with the reason |
| `reason` | `string` | When blocking | Explanation fed back to Claude |
| `hookSpecificOutput.additionalContext` | `string` | No | Context for Claude to consider |

---

### 4. PermissionRequest

**Lifecycle Position**: Fires when the user is shown a permission dialog.

#### Purpose
Automate permission decisions to streamline workflows. Auto-approve safe operations or auto-deny risky ones.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | Yes (matches tool requesting permission) |
| **Can Block** | Yes (can deny permission) |
| **Can Modify Input** | Yes (via `updatedInput` when allowing) |

#### Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "PermissionRequest",
  "tool_name": "Bash",
  "tool_input": {
    "command": "npm test"
  }
}
```

#### Output Behavior

| Exit Code | Behavior |
|-----------|----------|
| `0` | Success - JSON output determines permission decision |
| `2` | Deny - Permission denied, `stderr` shown as reason |
| Other | Non-blocking - Permission prompt shown to user normally |

#### JSON Output Schema

**For allowing:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {
      "behavior": "allow",
      "updatedInput": {
        "command": "npm run lint"
      }
    }
  }
}
```

**For denying:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {
      "behavior": "deny",
      "message": "Reason for denial shown to Claude",
      "interrupt": true
    }
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision.behavior` | `"allow"` \| `"deny"` | Yes | Permission decision |
| `decision.updatedInput` | `object` | No | Modified parameters when allowing |
| `decision.message` | `string` | No | Message shown when denying |
| `decision.interrupt` | `boolean` | No | If true, stops Claude when denying |

---

### 5. Notification

**Lifecycle Position**: Fires when Claude Code sends notifications.

#### Purpose
Intercept and customize notifications. Useful for desktop alerts, sound notifications, or custom UI integration.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | Yes (matches `notification_type`) |
| **Can Block** | No |
| **Side Effects Only** | Yes |

#### Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "/Users/.../.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "Notification",
  "message": "Claude needs your permission to use Bash",
  "notification_type": "permission_prompt"
}
```

#### Input Field Details

| Field | Type | Description |
|-------|------|-------------|
| `message` | `string` | The notification message text |
| `notification_type` | `string` | Type/category of the notification |

**Known `notification_type` values:**
- `permission_prompt` - Permission requests from Claude Code
- `idle_prompt` - When Claude is waiting for user input (after 60+ seconds idle)
- `auth_success` - Authentication success notifications
- `elicitation_dialog` - When Claude Code needs input for MCP tool elicitation

#### Output Behavior

| Exit Code | Behavior |
|-----------|----------|
| Any | Non-blocking - Notification proceeds regardless |

---

### 6. Stop

**Lifecycle Position**: Fires when Claude's main agent finishes responding.

#### Purpose
Control whether Claude should actually stop or continue working. Enables AI-powered task completion validation.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | No |
| **Can Block** | Yes (exit code 2 or `decision: "block"` **forces Claude to continue**) |
| **Loop Prevention** | `stop_hook_active` field prevents infinite loops |

#### Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "permission_mode": "default",
  "hook_event_name": "Stop",
  "stop_hook_active": true
}
```

#### Input Field Details

| Field | Type | Description |
|-------|------|-------------|
| `stop_hook_active` | `boolean` | True when Claude Code is already continuing as a result of a stop hook. **Check this to prevent infinite loops.** |

#### Output Behavior

| Exit Code | Behavior |
|-----------|----------|
| `0` | Success - Claude stops normally (unless JSON says `decision: "block"`) |
| `2` | Blocking - Claude **prevented from stopping**, `stderr` becomes the reason to continue |
| Other | Non-blocking - Claude stops, `stderr` shown in verbose mode |

#### JSON Output Schema

```json
{
  "decision": "block",
  "reason": "Tests are failing. Please fix before completing."
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision` | `"block"` \| `undefined` | No | Set to `"block"` to prevent stopping |
| `reason` | `string` | When blocking | Explanation fed to Claude about why it must continue |

---

### 7. SubagentStop

**Lifecycle Position**: Fires when a Claude Code subagent (Task tool call) finishes.

#### Purpose
Control subagent completion separately from the main agent. Useful for multi-agent orchestration.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | No |
| **Can Block** | Yes (exit code 2 forces subagent to continue) |
| **Loop Prevention** | Same `stop_hook_active` mechanism as Stop |

#### Input Schema

Same as [Stop](#6-stop) with `hook_event_name: "SubagentStop"`.

#### Output Behavior

Same as [Stop](#6-stop) hook.

---

### 8. PreCompact

**Lifecycle Position**: Fires **before** conversation history compaction/summarization.

#### Purpose
Prepare for or react to context compression. Useful for preserving important information before it's summarized.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | Yes (matches `trigger`: `"manual"` or `"auto"`) |
| **Can Block** | No (stderr shown to user only) |
| **Side Effects Only** | Yes |

#### Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "permission_mode": "default",
  "hook_event_name": "PreCompact",
  "trigger": "manual",
  "custom_instructions": ""
}
```

#### Input Field Details

| Field | Type | Description |
|-------|------|-------------|
| `trigger` | `"manual"` \| `"auto"` | How compaction was initiated |
| `custom_instructions` | `string` | User-provided instructions if trigger is `"manual"`, otherwise empty |

---

### 9. SessionStart

**Lifecycle Position**: Fires when a new session begins or an existing one resumes.

#### Purpose
Initialize session context. Load development state, set environment variables, install dependencies.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | Yes (matches `source`) |
| **Can Block** | No (stderr shown to user only) |
| **Context Injection** | Yes (`additionalContext` added to session) |
| **Environment Persistence** | Yes (via `CLAUDE_ENV_FILE`) |

#### Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "permission_mode": "default",
  "hook_event_name": "SessionStart",
  "source": "startup"
}
```

#### Input Field Details

| Field | Type | Description |
|-------|------|-------------|
| `source` | `string` | How the session was started |

**Source values:**
- `"startup"` - Fresh new session
- `"resume"` - Resuming from `--resume`, `--continue`, or `/resume`
- `"clear"` - Session cleared with `/clear`
- `"compact"` - Invoked from auto or manual compact

#### Output Behavior

| Exit Code | Behavior |
|-----------|----------|
| `0` | Success - `stdout` with `additionalContext` added to session context |
| Other | Non-blocking - `stderr` shown to user, session proceeds |

#### JSON Output Schema

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Git status: 3 modified files\nBranch: feature/new-api"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `hookSpecificOutput.additionalContext` | `string` | No | Context added to the session. Multiple hooks' values are concatenated. |

---

### 10. SessionEnd

**Lifecycle Position**: Fires when a session concludes.

#### Purpose
Cleanup and finalization. Log statistics, save state, close connections.

#### Attributes

| Attribute | Value |
|-----------|-------|
| **Matcher Required** | No |
| **Can Block** | No (cannot prevent session end) |
| **Side Effects Only** | Yes |

#### Input Schema

```json
{
  "session_id": "abc123",
  "transcript_path": "~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl",
  "cwd": "/Users/...",
  "permission_mode": "default",
  "hook_event_name": "SessionEnd",
  "reason": "exit"
}
```

#### Input Field Details

| Field | Type | Description |
|-------|------|-------------|
| `reason` | `string` | Reason for session ending |

**Reason values:**
- `"clear"` - Session cleared with `/clear` command
- `"logout"` - User logged out
- `"prompt_input_exit"` - User exited while prompt input was visible
- `"other"` - Other exit reasons

---

## Exit Code Behavior

Exit codes are the primary mechanism for hooks to communicate outcomes:

| Exit Code | Name | Behavior | `stdout` Processing | `stderr` Handling |
|-----------|------|----------|---------------------|-------------------|
| `0` | Success | Action proceeds | JSON parsed for control fields; plain text used as context (for applicable hooks) | Ignored |
| `2` | Blocking Error | Action **blocked** (for blocking-capable hooks) | **Ignored** | Fed back to Claude or shown to user |
| Other | Non-blocking Error | Action proceeds | Ignored | Shown to user in verbose mode (Ctrl+R) |

### Exit Code 2 Behavior by Hook

| Hook | Exit Code 2 Effect |
|------|-------------------|
| `UserPromptSubmit` | Prompt erased and blocked, `stderr` shown to user only |
| `PreToolUse` | Tool call blocked, `stderr` shown to Claude |
| `PostToolUse` | `stderr` shown to Claude (tool already ran) |
| `PermissionRequest` | Permission denied, `stderr` shown to Claude |
| `Stop` | Claude **prevented from stopping**, `stderr` shown to Claude |
| `SubagentStop` | Subagent prevented from stopping, `stderr` shown to subagent |
| `Notification` | N/A - `stderr` shown to user only |
| `PreCompact` | N/A - `stderr` shown to user only |
| `SessionStart` | N/A - `stderr` shown to user only |
| `SessionEnd` | N/A - `stderr` shown to user only |

---

## Return Formats Reference

### Output Methods

There are two mutually-exclusive ways for hooks to return output:

#### Method 1: Simple Exit Code + stderr

Use exit codes and `stderr` for simple blocking/error scenarios:

```python
#!/usr/bin/env python3
import sys

# Block with exit code 2
print("BLOCKED: Dangerous command detected", file=sys.stderr)
sys.exit(2)
```

#### Method 2: JSON Output (Exit Code 0)

Use structured JSON in `stdout` for sophisticated control:

```python
#!/usr/bin/env python3
import json
import sys

output = {
    "decision": "block",
    "reason": "Explanation for blocking"
}
print(json.dumps(output))
sys.exit(0)  # Must be exit code 0 for JSON processing
```

> **Important**: JSON output is only processed when the hook exits with code 0. Exit code 2 uses `stderr` directly—any JSON in `stdout` is ignored.

---

### Common JSON Fields

All hook types can include these optional fields:

```json
{
  "continue": true,
  "stopReason": "string",
  "suppressOutput": true,
  "systemMessage": "string"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `continue` | `boolean` | `true` | Whether Claude should continue after hook execution. If `false`, Claude stops processing. |
| `stopReason` | `string` | - | Message shown to user when `continue` is `false` (not shown to Claude) |
| `suppressOutput` | `boolean` | `false` | Hide `stdout` from transcript mode |
| `systemMessage` | `string` | - | Optional warning message shown to the user |

#### `continue` Field Behavior

When `continue` is `false`:
- **PreToolUse**: Different from `permissionDecision: "deny"` which only blocks a specific tool call
- **PostToolUse**: Different from `decision: "block"` which provides feedback to Claude
- **UserPromptSubmit**: Prevents the prompt from being processed
- **Stop/SubagentStop**: Takes precedence over any `decision: "block"` output

In all cases, `continue: false` takes precedence over any `decision: "block"` output.

---

### Hook-Specific Output Schemas

#### UserPromptSubmit Output

**Plain text method (simpler):**
```python
# Any non-JSON text written to stdout is added as context
print("Current time: 2025-12-17T10:30:00")
print("Git branch: feature/new-api")
sys.exit(0)
```

**JSON method (structured):**
```json
{
  "decision": "block",
  "reason": "Security policy violation: Prompt contains potential secrets",
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "Project: E-commerce API\nStandards: Follow REST conventions"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `decision` | `"block"` \| `undefined` | `"block"` prevents prompt processing and erases it from context |
| `reason` | `string` | Shown to user when blocking (not added to context) |
| `hookSpecificOutput.additionalContext` | `string` | Added to context if not blocked |

#### PreToolUse Output

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow",
    "permissionDecisionReason": "Documentation file auto-approved",
    "updatedInput": {
      "file_path": "/modified/path.txt",
      "content": "modified content"
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `permissionDecision` | `"allow"` \| `"deny"` \| `"ask"` | Controls tool execution |
| `permissionDecisionReason` | `string` | Explanation for decision |
| `updatedInput` | `object` | Modified tool parameters (merged with original) |

**`permissionDecision` values:**
- `"allow"` - Bypasses permission system. Reason shown to user, not Claude.
- `"deny"` - Prevents tool execution. Reason shown to Claude.
- `"ask"` - Prompts user to confirm. Reason shown to user, not Claude.

> **Note**: The deprecated `decision` and `reason` fields map `"approve"` → `"allow"` and `"block"` → `"deny"`.

#### PostToolUse Output

```json
{
  "decision": "block",
  "reason": "File write failed validation - missing required header",
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "Note: File was auto-formatted with prettier"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `decision` | `"block"` \| `undefined` | `"block"` automatically prompts Claude with the reason |
| `reason` | `string` | Explanation fed to Claude when blocking |
| `hookSpecificOutput.additionalContext` | `string` | Additional context for Claude |

#### PermissionRequest Output

**Allow with modification:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {
      "behavior": "allow",
      "updatedInput": {
        "command": "npm run lint -- --fix"
      }
    }
  }
}
```

**Deny with message:**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {
      "behavior": "deny",
      "message": "Network operations not permitted in this project",
      "interrupt": true
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `decision.behavior` | `"allow"` \| `"deny"` | Permission decision |
| `decision.updatedInput` | `object` | Modified parameters (when allowing) |
| `decision.message` | `string` | Reason for denial (when denying) |
| `decision.interrupt` | `boolean` | Stop Claude entirely (when denying) |

#### Stop/SubagentStop Output

```json
{
  "decision": "block",
  "reason": "Tests are failing. Please fix failing tests before completing."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `decision` | `"block"` \| `undefined` | `"block"` prevents Claude from stopping |
| `reason` | `string` | **Required when blocking** - tells Claude how to proceed |

#### SessionStart Output

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Git status:\n  M src/api.ts\n  M tests/api.test.ts\n\nCurrent sprint: Q4 Performance Optimization"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `hookSpecificOutput.additionalContext` | `string` | Added to session context. Multiple hooks' values are concatenated. |

---

## Context Steering Guide

Context steering allows hooks to influence Claude's behavior by injecting information, providing feedback, or controlling execution flow. This section covers the factual mechanisms available based on official documentation.

### Context Injection Points

There are three hooks that can inject context into Claude's awareness:

| Hook | Injection Mechanism | When Context is Added |
|------|---------------------|----------------------|
| `UserPromptSubmit` | `stdout` (plain text) or `additionalContext` (JSON) | Added to conversation along with user's prompt |
| `PostToolUse` | `additionalContext` in JSON output | Added after tool execution |
| `SessionStart` | `additionalContext` in JSON output | Added at session initialization |

### Steering Mechanisms

#### 1. Context Injection (UserPromptSubmit)

**Plain text stdout** - Simplest approach:
```python
#!/usr/bin/env python3
import sys

# Output added to Claude's context with the prompt
print("Current time: 2025-12-17T10:30:00")
print("Git branch: feature/new-api")
print("Active sprint: Q4 Performance")
sys.exit(0)
```

**JSON additionalContext** - More discrete:
```python
#!/usr/bin/env python3
import json
import sys

output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "Project: E-commerce API\nStandards: Follow REST conventions and OpenAPI 3.0"
    }
}
print(json.dumps(output))
sys.exit(0)
```

**Practical Example - Sprint Context Injection:**
```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cat ./current-sprint-context.md"
          }
        ]
      }
    ]
  }
}
```

This configuration causes Claude to receive the contents of `current-sprint-context.md` with every prompt.

#### 2. Session Initialization (SessionStart)

Load development context at session start:

```python
#!/usr/bin/env python3
import json
import subprocess
import sys

# Gather context
git_status = subprocess.run(
    ["git", "status", "--short"],
    capture_output=True, text=True
).stdout

git_branch = subprocess.run(
    ["git", "branch", "--show-current"],
    capture_output=True, text=True
).stdout.strip()

context = f"""Development Context:
- Current branch: {git_branch}
- Modified files:
{git_status}
"""

output = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context
    }
}
print(json.dumps(output))
sys.exit(0)
```

#### 3. Post-Execution Feedback (PostToolUse)

Provide feedback after tool operations:

```python
#!/usr/bin/env python3
import json
import sys

input_data = json.load(sys.stdin)
tool_name = input_data.get("tool_name", "")
tool_response = input_data.get("tool_response", {})

# Add context about the operation
if tool_name == "Write":
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "Note: File was auto-formatted with prettier"
        }
    }
    print(json.dumps(output))

sys.exit(0)
```

#### 4. Blocking with Feedback (Exit Code 2)

Exit code 2 creates a feedback loop to Claude:

```python
#!/usr/bin/env python3
import json
import sys

input_data = json.load(sys.stdin)
command = input_data.get("tool_input", {}).get("command", "")

if "rm -rf" in command:
    # stderr is fed back to Claude automatically
    print("BLOCKED: Dangerous rm command detected. Use safer alternatives.", file=sys.stderr)
    sys.exit(2)  # Claude sees the error and adjusts

sys.exit(0)
```

#### 5. Preventing Premature Completion (Stop Hook)

Force Claude to continue when work is incomplete:

```python
#!/usr/bin/env python3
import json
import subprocess
import sys

input_data = json.load(sys.stdin)

# Prevent infinite loops
if input_data.get("stop_hook_active", False):
    sys.exit(0)

# Check if tests pass
result = subprocess.run(["npm", "test"], capture_output=True)

if result.returncode != 0:
    output = {
        "decision": "block",
        "reason": "Tests are failing. Please fix failing tests before completing."
    }
    print(json.dumps(output))

sys.exit(0)
```

### Practical Patterns

#### Pattern 1: Dynamic Project Context

Inject relevant context based on prompt content:

```python
#!/usr/bin/env python3
import json
import os
import sys

input_data = json.load(sys.stdin)
prompt = input_data.get("prompt", "").lower()

context_parts = []

# Add coding standards for code-related prompts
if any(kw in prompt for kw in ["code", "implement", "function", "class", "write"]):
    project_name = os.getenv("PROJECT_NAME", "Unknown Project")
    context_parts.append(f"Project: {project_name}")
    context_parts.append("Standards: Follow PEP 8, include type hints, write docstrings")

# Add API context for API-related prompts
if any(kw in prompt for kw in ["api", "endpoint", "rest", "http"]):
    context_parts.append("API Standards: Use REST conventions, OpenAPI 3.0 spec")

if context_parts:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(context_parts)
        }
    }
    print(json.dumps(output))

sys.exit(0)
```

#### Pattern 2: Security Validation with Feedback

Block dangerous operations and explain why:

```python
#!/usr/bin/env python3
import json
import re
import sys

DANGEROUS_PATTERNS = [
    (r"rm\s+-rf\s+/", "Dangerous system deletion command"),
    (r"curl.*\|\s*sh", "Unsafe remote script execution"),
    (r"eval\s*\(", "Unsafe code evaluation"),
]

input_data = json.load(sys.stdin)
prompt = input_data.get("prompt", "")

for pattern, reason in DANGEROUS_PATTERNS:
    if re.search(pattern, prompt, re.IGNORECASE):
        output = {
            "decision": "block",
            "reason": f"Security Policy Violation: {reason}"
        }
        print(json.dumps(output))
        sys.exit(0)

sys.exit(0)
```

#### Pattern 3: File Protection

Prevent modifications to sensitive files:

```python
#!/usr/bin/env python3
import json
import sys

PROTECTED_PATTERNS = [".env", "package-lock.json", ".git/", "secrets.yaml"]

input_data = json.load(sys.stdin)
tool_name = input_data.get("tool_name", "")
file_path = input_data.get("tool_input", {}).get("file_path", "")

if tool_name in ["Write", "Edit", "MultiEdit"]:
    for pattern in PROTECTED_PATTERNS:
        if pattern in file_path:
            print(f"BLOCKED: Cannot modify protected file: {file_path}", file=sys.stderr)
            sys.exit(2)

sys.exit(0)
```

#### Pattern 4: Auto-Approve Safe Operations

Streamline workflows by auto-approving known-safe operations:

```python
#!/usr/bin/env python3
import json
import sys

SAFE_COMMANDS = [
    "npm test",
    "npm run lint",
    "git status",
    "git diff",
    "ls",
]

input_data = json.load(sys.stdin)
tool_name = input_data.get("tool_name", "")
command = input_data.get("tool_input", {}).get("command", "")

if tool_name == "Bash":
    for safe_cmd in SAFE_COMMANDS:
        if command.startswith(safe_cmd):
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": f"Auto-approved safe command: {safe_cmd}"
                }
            }
            print(json.dumps(output))
            sys.exit(0)

sys.exit(0)
```

#### Pattern 5: Intelligent Task Completion (Prompt Hook)

Use an LLM to evaluate task completion:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "You are evaluating whether Claude should stop working. Context: $ARGUMENTS\n\nAnalyze the conversation and determine if:\n1. All user-requested tasks are complete\n2. Any errors need to be addressed\n3. Follow-up work is needed\n\nRespond with JSON: {\"decision\": \"approve\" or \"block\", \"reason\": \"your explanation\"}",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

---

## Matcher Patterns

Matchers determine which events trigger a hook. They're case-sensitive regular expressions.

### Matcher Applicability

| Hook | Matcher Target | Required |
|------|---------------|----------|
| `PreToolUse` | `tool_name` | Yes |
| `PostToolUse` | `tool_name` | Yes |
| `PermissionRequest` | `tool_name` | Yes |
| `Notification` | `notification_type` | Yes |
| `SessionStart` | `source` | Yes |
| `PreCompact` | `trigger` | Yes |
| Others | N/A | No matcher needed |

### Pattern Syntax

| Pattern | Matches |
|---------|---------|
| `Write` | Exactly "Write" |
| `Write\|Edit` | "Write" or "Edit" |
| `Write\|Edit\|MultiEdit` | Any of the three |
| `.*` | Any tool (wildcard) |
| `""` (empty) | Any tool (same as `.*`) |
| `mcp__.*` | Any MCP tool |
| `mcp__memory__.*` | Any tool from memory MCP server |
| `Notebook.*` | NotebookRead, NotebookEdit |

### Built-in Tool Names

```
Read, Write, Edit, MultiEdit, Bash, Glob, Grep, LS, 
Task, WebFetch, WebSearch, TodoRead, TodoWrite,
NotebookRead, NotebookEdit
```

### MCP Tool Naming

MCP tools follow the pattern: `mcp__<server_name>__<tool_name>`

Examples:
- `mcp__memory__create_entities`
- `mcp__filesystem__read_file`
- `mcp__github__search_repositories`

---

## Environment Variables

### Available to All Hooks

| Variable | Description | Example |
|----------|-------------|---------|
| `CLAUDE_PROJECT_DIR` | Absolute path to the project root | `/Users/dev/my-project` |
| `CLAUDE_CODE_REMOTE` | `"true"` if running in web environment, unset for local CLI | `"true"` |

### SessionStart Only

| Variable | Description |
|----------|-------------|
| `CLAUDE_ENV_FILE` | Path for persisting environment variables for subsequent Bash commands |

### Plugin-Specific

| Variable | Description |
|----------|-------------|
| `CLAUDE_PLUGIN_ROOT` | Absolute path to the plugin directory |

### Persisting Environment Variables (SessionStart)

```bash
#!/bin/bash

if [ -n "$CLAUDE_ENV_FILE" ]; then
  echo 'export NODE_ENV=production' >> "$CLAUDE_ENV_FILE"
  echo 'export API_KEY=your-api-key' >> "$CLAUDE_ENV_FILE"
  echo 'export PATH="$PATH:./node_modules/.bin"' >> "$CLAUDE_ENV_FILE"
fi

exit 0
```

Variables written to `CLAUDE_ENV_FILE` are available in all subsequent Bash commands.

---

## Configuration Locations

Hooks can be configured at multiple levels:

| Level | Location | Scope |
|-------|----------|-------|
| User | `~/.claude/settings.json` | All projects for this user |
| Project (shared) | `.claude/settings.json` | All users of this project |
| Project (local) | `.claude/settings.local.json` | This user, this project only |
| Plugin | `~/.claude/plugins/<plugin>/plugin.json` | When plugin enabled |

### Precedence

- All matching hooks run in **parallel**
- Identical commands are **deduplicated**
- No guaranteed execution order

### Configuration Safety

Direct edits to hooks in settings files don't take effect immediately:
1. Claude Code captures a snapshot of hooks at startup
2. Uses this snapshot throughout the session
3. Warns if hooks are modified externally
4. Requires review in `/hooks` menu for changes to apply

---

## Hook Types

### Command Hooks

Execute a shell command:

```json
{
  "type": "command",
  "command": "python3 .claude/hooks/my-hook.py",
  "timeout": 30
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | `"command"` | Yes | - | Hook type identifier |
| `command` | `string` | Yes | - | Shell command to execute |
| `timeout` | `number` | No | 60 | Timeout in seconds |

### Prompt Hooks

Use an LLM (Haiku) to evaluate the event:

```json
{
  "type": "prompt",
  "prompt": "Evaluate if Claude should stop: $ARGUMENTS. Check if all tasks are complete.",
  "timeout": 30
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `type` | `"prompt"` | Yes | - | Hook type identifier |
| `prompt` | `string` | Yes | - | Prompt text sent to LLM |
| `timeout` | `number` | No | 30 | Timeout in seconds |

`$ARGUMENTS` is replaced with the JSON input. If omitted, JSON is appended.

**Expected LLM Response:**
```json
{
  "decision": "approve",
  "reason": "Explanation for the decision"
}
```

---

## Security Considerations

### Disclaimer

**USE AT YOUR OWN RISK**: Claude Code hooks execute arbitrary shell commands on your system automatically. By using hooks, you acknowledge that:

- You are solely responsible for the commands you configure
- Hooks can modify, delete, or access any files your user account can access
- Malicious or poorly written hooks can cause data loss or system damage
- You should thoroughly test hooks in a safe environment before production use

### Best Practices

1. **Validate and sanitize inputs** - Never trust input data blindly
2. **Always quote shell variables** - Use `"$VAR"` not `$VAR`
3. **Block path traversal** - Check for `..` in file paths
4. **Use absolute paths** - Specify full paths for scripts
5. **Skip sensitive files** - Avoid `.env`, `.git/`, keys

---

## Debugging

### Basic Troubleshooting

1. **Check configuration** - Run `/hooks` to see registered hooks
2. **Verify syntax** - Ensure JSON settings are valid
3. **Test commands** - Run hook commands manually first
4. **Check permissions** - Ensure scripts are executable
5. **Review logs** - Use `claude --debug` to see execution details

### Debug Output Example

```
[DEBUG] Executing hooks for PostToolUse:Write
[DEBUG] Getting matching hook commands for PostToolUse with query: Write
[DEBUG] Found 1 hook matchers in settings
[DEBUG] Matched 1 hooks for query "Write"
[DEBUG] Found 1 hook commands to execute
[DEBUG] Executing hook command: <Your command> with timeout 60000ms
[DEBUG] Hook command completed with status 0: <Your stdout>
```

---

## Quick Reference Card

| Event | When | Matcher | Blocks | Context Injection |
|-------|------|---------|--------|-------------------|
| `UserPromptSubmit` | User submits prompt | No | Yes | Yes (stdout or additionalContext) |
| `PreToolUse` | Before tool runs | `tool_name` | Yes | No |
| `PostToolUse` | After tool completes | `tool_name` | Feedback | Yes (additionalContext) |
| `PermissionRequest` | Permission needed | `tool_name` | Yes | No |
| `Notification` | Alert needed | `notification_type` | No | No |
| `Stop` | Agent finishing | No | Yes (continues) | No |
| `SubagentStop` | Subagent finishing | No | Yes (continues) | No |
| `PreCompact` | Before compaction | `trigger` | No | No |
| `SessionStart` | Session begins | `source` | No | Yes (additionalContext) |
| `SessionEnd` | Session ends | No | No | No |

---

## Appendix: Complete Configuration Example

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/validate_prompt.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/validate_bash.py"
          }
        ]
      },
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/validate_file_ops.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/auto_format.sh",
            "timeout": 30
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/auto_approve.py"
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "permission_prompt|idle_prompt",
        "hooks": [
          {
            "type": "command",
            "command": "notify-send 'Claude Code' 'Attention needed'"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/validate_completion.py"
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Evaluate subagent completion: $ARGUMENTS",
            "timeout": 30
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "matcher": "manual|auto",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/backup_transcript.py"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": ".claude/hooks/load_context.sh"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/log_session.py"
          }
        ]
      }
    ]
  }
}
```

---

*Last updated: December 2025*
*Based on official Claude Code hooks documentation at code.claude.com/docs/en/hooks*
