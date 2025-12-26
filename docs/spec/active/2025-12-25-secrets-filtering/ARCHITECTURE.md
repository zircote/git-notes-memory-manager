# Architecture: Secrets Filtering and Sensitive Data Protection

## Overview

This document describes the technical architecture for implementing secrets filtering in the git-notes-memory system. The design follows the existing service layer pattern and integrates with the capture pipeline before embedding generation.

## System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                     Memory Capture Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Input                                                      │
│      │                                                           │
│      ▼                                                           │
│  CaptureService.capture()                                        │
│      │                                                           │
│      ├── validate_namespace()                                    │
│      ├── validate_summary()                                      │
│      ├── validate_content()                                      │
│      │                                                           │
│      ▼                                                           │
│  ┌─────────────────────────────────────────┐                    │
│  │     SecretsFilteringService            │ ◄── NEW             │
│  │  ┌─────────────────────────────────┐   │                     │
│  │  │ PatternDetector                 │   │                     │
│  │  │ EntropyAnalyzer                 │   │                     │
│  │  │ PIIDetector                     │   │                     │
│  │  │ AllowlistManager                │   │                     │
│  │  │ Redactor                        │   │                     │
│  │  │ AuditLogger                     │   │                     │
│  │  └─────────────────────────────────┘   │                     │
│  └─────────────────────────────────────────┘                    │
│      │                                                           │
│      ▼                                                           │
│  serialize_note()                                                │
│      │                                                           │
│      ▼                                                           │
│  EmbeddingService.embed()  ◄── Uses filtered content            │
│      │                                                           │
│      ▼                                                           │
│  GitOps.append_note()                                           │
│      │                                                           │
│      ▼                                                           │
│  IndexService.insert()                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. SecretsFilteringService

**Responsibility**: Orchestrate detection and filtering across all components.

**Location**: `src/git_notes_memory/security/service.py`

**Interface**:
```python
@dataclass(frozen=True)
class FilterResult:
    """Result of filtering operation."""
    original_text: str
    filtered_text: str
    detections: tuple[SecretDetection, ...]
    was_modified: bool
    action_taken: FilterAction

@dataclass(frozen=True)
class SecretDetection:
    """A detected secret."""
    secret_type: SecretType
    detector: str  # "pattern", "entropy", "pii"
    start_pos: int
    end_pos: int
    confidence: float  # 0.0-1.0
    context: str  # Surrounding text for audit

class SecretsFilteringService:
    def __init__(
        self,
        strategy: FilterStrategy = FilterStrategy.REDACT,
        config: SecretsConfig | None = None,
    ) -> None: ...

    def filter(
        self,
        text: str,
        field_name: str = "content",
        namespace: str | None = None,
    ) -> FilterResult: ...

    def scan(
        self,
        text: str,
    ) -> tuple[SecretDetection, ...]: ...
```

### 2. PatternDetector

**Responsibility**: Detect secrets using compiled regex patterns.

**Location**: `src/git_notes_memory/security/patterns.py`

**Patterns Included**:

| Category | Pattern Name | Example Match |
|----------|--------------|---------------|
| API Keys | OpenAI | `sk-proj-...`, `sk-...` |
| API Keys | Anthropic | `sk-ant-...` |
| API Keys | GitHub | `ghp_...`, `gho_...`, `ghu_...`, `ghs_...`, `ghr_...` |
| API Keys | AWS Access Key | `AKIA...` |
| API Keys | AWS Secret Key | 40-char base64 after `aws_secret` |
| API Keys | Stripe | `sk_live_...`, `pk_live_...` |
| API Keys | Slack | `xoxb-...`, `xoxp-...`, `xoxa-...` |
| Credentials | Generic Password | `password=...`, `passwd:...` |
| Credentials | Basic Auth | `://user:pass@` |
| Credentials | Bearer Token | `Bearer ...` |
| Keys | RSA Private | `-----BEGIN RSA PRIVATE KEY-----` |
| Keys | DSA Private | `-----BEGIN DSA PRIVATE KEY-----` |
| Keys | EC Private | `-----BEGIN EC PRIVATE KEY-----` |
| Keys | OpenSSH | `-----BEGIN OPENSSH PRIVATE KEY-----` |
| Connection | Database URL | `postgres://...`, `mysql://...`, `mongodb://...` |

**Implementation**:
```python
@dataclass(frozen=True)
class PatternRule:
    """A detection pattern rule."""
    name: str
    pattern: re.Pattern[str]
    secret_type: SecretType
    confidence: float
    description: str

class PatternDetector:
    def __init__(self) -> None:
        self._patterns: tuple[PatternRule, ...] = self._compile_patterns()

    def detect(self, text: str) -> tuple[SecretDetection, ...]: ...

    @staticmethod
    def _compile_patterns() -> tuple[PatternRule, ...]:
        # Compiled at init, cached for performance
        ...
```

### 3. EntropyAnalyzer

**Responsibility**: Detect high-entropy strings that may be secrets.

**Location**: `src/git_notes_memory/security/entropy.py`

**Algorithm**:
```python
def shannon_entropy(data: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not data:
        return 0.0

    frequency = {}
    for char in data:
        frequency[char] = frequency.get(char, 0) + 1

    length = len(data)
    entropy = 0.0
    for count in frequency.values():
        probability = count / length
        entropy -= probability * math.log2(probability)

    return entropy
```

**Thresholds**:
| String Type | Threshold | Rationale |
|-------------|-----------|-----------|
| Base64-like | 4.5 | Random base64 averages ~5.17 |
| Hex | 3.0 | Random hex averages ~4.0 |
| Alphanumeric | 4.0 | Balanced threshold |

**Configuration**:
```python
class EntropyAnalyzer:
    def __init__(
        self,
        base64_threshold: float = 4.5,
        hex_threshold: float = 3.0,
        min_length: int = 16,
    ) -> None: ...

    def analyze(self, text: str) -> tuple[SecretDetection, ...]: ...
```

### 4. PIIDetector

**Responsibility**: Detect personally identifiable information.

**Location**: `src/git_notes_memory/security/pii.py`

**Patterns**:
| Type | Pattern | Validation |
|------|---------|------------|
| SSN | `\d{3}-\d{2}-\d{4}` | Format only |
| Credit Card | `\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}` | Luhn algorithm |
| Phone (US) | `(\+1)?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}` | Format only |

**Implementation**:
```python
class PIIDetector:
    def detect(self, text: str) -> tuple[SecretDetection, ...]: ...

    @staticmethod
    def luhn_check(number: str) -> bool:
        """Validate credit card number using Luhn algorithm."""
        digits = [int(d) for d in number if d.isdigit()]
        checksum = 0
        for i, digit in enumerate(reversed(digits)):
            if i % 2 == 1:
                digit *= 2
                if digit > 9:
                    digit -= 9
            checksum += digit
        return checksum % 10 == 0
```

### 5. AllowlistManager

**Responsibility**: Manage hash-based allowlist for known-safe values.

**Location**: `src/git_notes_memory/security/allowlist.py`

**Storage Format** (`~/.config/memory-plugin/secrets-allowlist.yaml`):
```yaml
# Allowlist configuration
# Values are stored as SHA-256 hashes, never plaintext

global:
  # Example API key from documentation
  - hash: "a1b2c3d4..."
    added: "2025-01-15T10:30:00Z"
    reason: "Documentation example"
    added_by: "developer@example.com"

namespaces:
  decisions:
    - hash: "e5f6g7h8..."
      added: "2025-01-16T11:00:00Z"
      reason: "Test fixture"
```

**Implementation**:
```python
class AllowlistManager:
    def __init__(self, config_path: Path | None = None) -> None: ...

    def is_allowed(self, value: str, namespace: str | None = None) -> bool:
        """Check if value hash is in allowlist."""
        value_hash = hashlib.sha256(value.encode()).hexdigest()
        return value_hash in self._allowed_hashes

    def add(
        self,
        value: str,
        reason: str,
        namespace: str | None = None,
    ) -> str:
        """Add value to allowlist, return hash."""
        ...

    def remove(self, value_hash: str) -> bool:
        """Remove entry by hash."""
        ...

    def list_entries(self, namespace: str | None = None) -> list[AllowlistEntry]:
        """List all allowlist entries."""
        ...
```

### 6. Redactor

**Responsibility**: Apply filtering strategies to detected secrets.

**Location**: `src/git_notes_memory/security/redactor.py`

**Strategies**:
```python
class FilterStrategy(Enum):
    REDACT = "redact"   # Replace with [REDACTED:{type}]
    MASK = "mask"       # Show first/last 4 chars
    BLOCK = "block"     # Reject entire content
    WARN = "warn"       # Allow but log warning

class Redactor:
    def __init__(self, strategy: FilterStrategy) -> None: ...

    def apply(
        self,
        text: str,
        detections: tuple[SecretDetection, ...],
    ) -> tuple[str, FilterAction]:
        """Apply redaction strategy to text."""
        ...
```

**Examples**:
| Strategy | Input | Output |
|----------|-------|--------|
| REDACT | `sk-proj-abc123xyz` | `[REDACTED:openai_api_key]` |
| MASK | `sk-proj-abc123xyz789` | `sk-p****789` |
| BLOCK | `sk-proj-abc123xyz` | (raises BlockedContentError) |
| WARN | `sk-proj-abc123xyz` | `sk-proj-abc123xyz` (logs warning) |

### 7. AuditLogger

**Responsibility**: Log all detection events for compliance.

**Location**: `src/git_notes_memory/security/audit.py`

**Log Format** (JSON Lines):
```json
{"timestamp": "2025-01-15T10:30:00.123Z", "event": "secret_detected", "namespace": "decisions", "detector": "pattern", "secret_type": "openai_api_key", "action": "redact", "field": "content", "hash": "sha256:abc123...", "confidence": 0.95}
```

**Implementation**:
```python
class AuditLogger:
    def __init__(self, log_path: Path | None = None) -> None: ...

    def log_detection(
        self,
        detection: SecretDetection,
        action: FilterAction,
        namespace: str,
        field: str,
    ) -> None: ...

    def log_scan(
        self,
        memory_id: str,
        findings: int,
        remediated: int,
    ) -> None: ...

    def query(
        self,
        since: datetime | None = None,
        namespace: str | None = None,
        secret_type: SecretType | None = None,
    ) -> list[AuditEntry]: ...
```

---

## Integration Points

### CaptureService Integration

**Location**: `src/git_notes_memory/capture.py` (lines 281-300, 530-532)

**Before** (current):
```python
def capture(
    self,
    namespace: str,
    summary: str,
    content: str,
    ...
) -> CaptureResult:
    # Validation
    self._validate_namespace(namespace)
    self._validate_summary(summary)
    self._validate_content(content)

    # Serialize and store
    note = serialize_note(...)
    self._git_ops.append_note(...)
    embedding = self._embedding_service.embed(content)
    ...
```

**After** (with filtering):
```python
def capture(
    self,
    namespace: str,
    summary: str,
    content: str,
    ...
) -> CaptureResult:
    # Validation
    self._validate_namespace(namespace)
    self._validate_summary(summary)
    self._validate_content(content)

    # NEW: Filter secrets before processing
    if self._secrets_service is not None:
        summary_result = self._secrets_service.filter(summary, "summary", namespace)
        content_result = self._secrets_service.filter(content, "content", namespace)

        if summary_result.action_taken == FilterAction.BLOCKED:
            return CaptureResult(
                success=False,
                error="Content blocked: secrets detected in summary",
            )
        if content_result.action_taken == FilterAction.BLOCKED:
            return CaptureResult(
                success=False,
                error="Content blocked: secrets detected in content",
            )

        summary = summary_result.filtered_text
        content = content_result.filtered_text

    # Serialize and store (using filtered content)
    note = serialize_note(...)
    self._git_ops.append_note(...)
    embedding = self._embedding_service.embed(content)  # Filtered!
    ...
```

### Command Integration

**New Commands**:

| Command | Description |
|---------|-------------|
| `/memory:scan-secrets` | Scan existing memories |
| `/memory:secrets-allowlist` | Manage allowlist |
| `/memory:test-secret` | Test if value is detected |
| `/memory:audit-log` | View audit logs |

**Hook Integration**:
- PreCapture hook to enable early detection
- Stop hook to report session statistics

---

## Module Structure

```
src/git_notes_memory/
├── security/
│   ├── __init__.py         # Public exports
│   ├── service.py          # SecretsFilteringService
│   ├── patterns.py         # PatternDetector
│   ├── entropy.py          # EntropyAnalyzer
│   ├── pii.py              # PIIDetector
│   ├── allowlist.py        # AllowlistManager
│   ├── redactor.py         # Redactor
│   ├── audit.py            # AuditLogger
│   ├── models.py           # FilterResult, SecretDetection, etc.
│   ├── config.py           # SecretsConfig
│   └── exceptions.py       # BlockedContentError, etc.
├── commands/
│   ├── scan_secrets.py     # /memory:scan-secrets
│   ├── allowlist.py        # /memory:secrets-allowlist
│   ├── test_secret.py      # /memory:test-secret
│   └── audit_log.py        # /memory:audit-log
└── capture.py              # Modified to integrate filtering
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRETS_FILTER_ENABLED` | Enable/disable filtering | `true` |
| `SECRETS_FILTER_STRATEGY` | Default strategy | `redact` |
| `SECRETS_ENTROPY_THRESHOLD_BASE64` | Base64 threshold | `4.5` |
| `SECRETS_ENTROPY_THRESHOLD_HEX` | Hex threshold | `3.0` |
| `SECRETS_AUDIT_LOG_PATH` | Audit log location | `~/.local/share/memory-plugin/audit.jsonl` |
| `SECRETS_ALLOWLIST_PATH` | Allowlist config | `~/.config/memory-plugin/secrets-allowlist.yaml` |

### Configuration File

**Location**: `~/.config/memory-plugin/secrets.yaml`

```yaml
# Secrets filtering configuration

enabled: true
default_strategy: redact

# Per-namespace overrides
namespaces:
  decisions:
    strategy: block  # Stricter for decisions
  progress:
    strategy: redact

# Detector settings
detectors:
  patterns:
    enabled: true
    custom_patterns:
      - name: internal_api_key
        pattern: "int-api-[a-zA-Z0-9]{32}"
        description: "Internal API key format"

  entropy:
    enabled: true
    base64_threshold: 4.5
    hex_threshold: 3.0
    min_length: 16

  pii:
    enabled: true
    types:
      - ssn
      - credit_card
      - phone

# Audit settings
audit:
  enabled: true
  log_path: ~/.local/share/memory-plugin/audit.jsonl
  retention_days: 90
```

---

## Error Handling

### Exception Hierarchy

```python
class SecretsFilteringError(Exception):
    """Base exception for secrets filtering."""
    pass

class BlockedContentError(SecretsFilteringError):
    """Raised when content is blocked due to secrets."""
    def __init__(self, detections: tuple[SecretDetection, ...]) -> None:
        self.detections = detections
        super().__init__(f"Content blocked: {len(detections)} secret(s) detected")

class AllowlistError(SecretsFilteringError):
    """Raised for allowlist operations."""
    pass

class AuditLogError(SecretsFilteringError):
    """Raised for audit logging failures."""
    pass
```

### Graceful Degradation

If the secrets filtering service fails:
1. Log error to stderr
2. Continue with original content
3. Set warning flag in CaptureResult
4. Never block capture due to filter failure

```python
try:
    result = self._secrets_service.filter(content, "content")
    content = result.filtered_text
except SecretsFilteringError as e:
    logger.warning(f"Secrets filtering failed: {e}")
    # Continue with original content
```

---

## Performance Considerations

### Optimizations

1. **Compiled Regex**: All patterns compiled at service initialization
2. **Lazy Loading**: Patterns loaded on first use, not import
3. **Short-Circuit**: Skip entropy analysis if pattern already matched
4. **Caching**: LRU cache for allowlist hash lookups

### Benchmarks

| Operation | Target | Rationale |
|-----------|--------|-----------|
| Pattern detection | <3ms | Compiled regex is fast |
| Entropy analysis | <2ms | Simple math |
| PII detection | <2ms | Few patterns |
| Total filtering | <10ms | Sum of above + overhead |

---

## Security Considerations

### Defense in Depth

1. **Multiple Detectors**: Pattern + Entropy + PII
2. **Hash-Only Allowlist**: Never store plaintext secrets
3. **Audit Everything**: Full trail for compliance
4. **Fail Secure**: BLOCK on uncertainty (configurable)

### Known Limitations

1. **Encoded Secrets**: Base64/URL encoded secrets may evade pattern detection
2. **Custom Formats**: Organization-specific secrets need custom patterns
3. **False Positives**: High-entropy code (UUIDs, hashes) may trigger

### Mitigation

- Entropy thresholds tuned to reduce false positives
- Allowlist for known-safe values
- Test command for debugging
