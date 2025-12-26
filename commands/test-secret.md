---
description: Test if a value would be detected as a secret
argument-hint: "<value>"
allowed-tools: ["Bash", "Read"]
---

<help_check>
## Help Check

If `$ARGUMENTS` contains `--help` or `-h`:

**Output this help and HALT (do not proceed further):**

<help_output>
```
TEST-SECRET(1)                                   User Commands                                   TEST-SECRET(1)

NAME
    test-secret - Test if a value would be detected as a secret

SYNOPSIS
    /memory:test-secret <value>

DESCRIPTION
    Test if a given value would be detected as a secret by the filtering system.
    Shows the detection type, confidence score, and what filtering strategy would apply.

    This is useful for:
    - Verifying detection rules work correctly
    - Understanding why content was blocked/redacted
    - Testing before adding to allowlist

OPTIONS
    --help, -h            Show this help message

EXAMPLES
    /memory:test-secret "AKIAIOSFODNN7EXAMPLE"
        Test if this looks like an AWS access key

    /memory:test-secret "123-45-6789"
        Test if this looks like a US SSN

    /memory:test-secret "4111111111111111"
        Test if this looks like a credit card number

    /memory:test-secret "sk-proj-abc123xyz"
        Test if this looks like an OpenAI API key

NOTES
    The value is not stored anywhere - this is purely for testing.
    Use quotes around values containing spaces or special characters.

SEE ALSO
    /memory:scan-secrets - Scan memories for secrets
    /memory:secrets-allowlist - Manage allowlist

                                                                                               TEST-SECRET(1)
```
</help_output>

**After outputting help, HALT immediately. Do not proceed with command execution.**
</help_check>

---

# /memory:test-secret - Test Secret Detection

Test if a value would be detected as a secret by the filtering system.

## Your Task

You will analyze a value and report whether it would be detected as a secret.

<step number="1" name="Parse Arguments">

**Arguments format**: `$ARGUMENTS`

The entire argument is the value to test. Handle quoted strings.

</step>

<step number="2" name="Test Detection">

**Analyze the value**:

```bash
TEST_VALUE="${TEST_VALUE}"  # From arguments

uv run --directory "${CLAUDE_PLUGIN_ROOT}" python3 -c "
import sys
from git_notes_memory.security import get_secrets_filtering_service
from git_notes_memory.security.models import FilterAction

# Get the test value - passed as environment or inline
test_value = '''${TEST_VALUE}'''

if not test_value.strip():
    print('❌ Error: No value provided to test')
    print()
    print('Usage: /memory:test-secret <value>')
    sys.exit(1)

service = get_secrets_filtering_service()

if not service.enabled:
    print('⚠️  Secrets filtering is disabled.')
    print('Enable it to test detection.')
    sys.exit(0)

print('## Secret Detection Test\n')
print(f'**Testing value:** \`{test_value[:30]}...\` (truncated for display)\n')

# Scan without filtering
result = service.scan(test_value)

if not result.had_secrets:
    print('### Result: ✅ Not Detected\n')
    print('This value does **not** appear to be a secret.')
    print()
    print('It would be allowed through without modification.')
else:
    print('### Result: 🔒 Secret Detected\n')
    print('| Property | Value |')
    print('|----------|-------|')

    for detection in result.detections:
        print(f'| Secret Type | {detection.secret_type.value} |')
        print(f'| Confidence | {detection.confidence:.1%} |')
        print(f'| Detector | {detection.detector} |')
        print(f'| Position | chars {detection.start}-{detection.end} |')

        # Get strategy that would apply
        from git_notes_memory.security import get_redactor
        redactor = get_redactor()
        strategy = redactor.get_strategy(detection.secret_type)
        print(f'| Strategy | {strategy.value} |')
        print()

    # Show what would happen
    filter_result = service.filter(test_value, source='test')
    print('### What Would Happen\n')
    print(f'**Action:** {filter_result.action.value.upper()}')
    print()

    if filter_result.action == FilterAction.REDACTED:
        print('The secret would be replaced with:')
        print(f'\`{filter_result.content}\`')
    elif filter_result.action == FilterAction.MASKED:
        print('The secret would be masked as:')
        print(f'\`{filter_result.content}\`')
    elif filter_result.action == FilterAction.BLOCKED:
        print('⛔ The content would be **blocked** entirely.')
        print('You would see a BlockedContentError.')
    elif filter_result.action == FilterAction.WARNED:
        print('⚠️  A warning would be logged but content passes through unchanged.')

    print()
    print('### Hash for Allowlisting')
    print()
    print('If this is a false positive, you can add it to the allowlist:')
    print(f'\`\`\`')
    print(f'/memory:secrets-allowlist add --hash {result.detections[0].secret_hash} --reason \"<your reason>\"')
    print(f'\`\`\`')
"
```

</step>

## Output Sections

| Section | Description |
|---------|-------------|
| Result | Whether the value was detected |
| Detection Details | Type, confidence, detector |
| Strategy | What would happen if captured |
| Allowlist Info | How to allowlist if false positive |

## Examples

**User**: `/memory:test-secret "AKIAIOSFODNN7EXAMPLE"`
**Action**: Test AWS access key pattern

**User**: `/memory:test-secret "123-45-6789"`
**Action**: Test SSN pattern

**User**: `/memory:test-secret "hello world"`
**Action**: Test non-secret value (should pass)

## Related Commands

| Command | Description |
|---------|-------------|
| `/memory:scan-secrets` | Scan existing memories |
| `/memory:secrets-allowlist` | Manage allowlist |
| `/memory:audit-log` | View detection history |
