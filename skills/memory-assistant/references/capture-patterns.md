# Capture Pattern Recognition

This reference documents patterns for recognizing memory capture opportunities during conversations.

## Signal Detection Framework

The memory assistant skill uses linguistic signal detection to identify capture-worthy content. Each namespace has characteristic patterns.

---

## Decision Signals

Decisions represent architectural, design, or technology choices that should be preserved with their rationale.

### Strong Signals (High Confidence)
```
- "we decided to..."
- "let's go with..."
- "choosing X over Y because..."
- "the trade-off is..."
- "after evaluating, we'll use..."
- "the approach will be..."
```

### Moderate Signals (Context-Dependent)
```
- "we should use..."
- "I think we need..."
- "probably best to..."
- "let's try..."
```

### Capture Template
```
/memory:capture decisions <what was decided> -- <rationale and context>
```

### Quality Criteria
- Includes the "why" not just the "what"
- Mentions alternatives considered
- Notes key trade-offs
- Provides enough context to understand standalone

---

## Learning Signals

Learnings capture new knowledge, discoveries, and insights gained during work.

### Strong Signals (High Confidence)
```
- "TIL..."
- "learned that..."
- "discovered..."
- "found out..."
- "realized..."
- "turns out..."
- "didn't know that..."
```

### Moderate Signals (Context-Dependent)
```
- "interesting that..."
- "apparently..."
- "so that's why..."
- "oh, that explains..."
```

### Capture Template
```
/memory:capture learnings <insight> -- <context and application>
```

Or inline: `[remember] <learning>`

### Quality Criteria
- Actionable or applicable insight
- Not trivially discoverable in docs
- Specific enough to be useful later
- Includes context where learned

---

## Blocker Signals

Blockers document obstacles, impediments, and their resolutions for future reference.

### Strong Signals (High Confidence)
```
- "blocked by..."
- "stuck on..."
- "cannot..."
- "failing because..."
- "impediment..."
- "preventing progress..."
```

### Resolution Signals
```
- "fixed by..."
- "resolved with..."
- "the solution was..."
- "workaround is..."
```

### Capture Template
```
/memory:capture blockers <issue summary> -- <description, impact, resolution if known>
```

### Quality Criteria
- Clear description of the obstacle
- Impact on progress documented
- Resolution included when known
- Root cause if identified

---

## Progress Signals

Progress captures milestones, completions, and achievements worth noting.

### Strong Signals (High Confidence)
```
- "completed..."
- "finished..."
- "milestone reached..."
- "done with..."
- "shipped..."
- "deployed..."
```

### Moderate Signals (Context-Dependent)
```
- "working now..."
- "tests passing..."
- "ready for review..."
```

### Capture Template
```
/memory:capture progress <milestone> -- <deliverables and next steps>
```

### Quality Criteria
- Specific deliverable identified
- Date/version context
- Notes on what comes next
- Links to related decisions/specs

---

## Pattern Signals

Patterns document recurring solutions, approaches, and idioms that prove useful.

### Strong Signals (High Confidence)
```
- "this pattern..."
- "we always..."
- "recurring approach..."
- "common solution..."
- "standard way to..."
- "idiom for..."
```

### Moderate Signals (Context-Dependent)
```
- "usually do..."
- "typical approach..."
- "best practice..."
- "recommended way..."
```

### Capture Template
```
/memory:capture patterns <pattern name> -- <when to use, how to apply, examples>
```

### Quality Criteria
- Clearly named pattern
- When/where to apply
- Code example if applicable
- Evidence of reuse

---

## Research Signals

Research captures external findings, technology evaluations, and benchmark results.

### Strong Signals (High Confidence)
```
- "evaluated..."
- "compared..."
- "benchmarked..."
- "researched..."
- "found in docs..."
- "according to..."
```

### Capture Template
```
/memory:capture research <finding summary> -- <sources, methodology, conclusions>
```

### Quality Criteria
- Sources cited or referenced
- Methodology noted
- Clear conclusions
- Relevance to project stated

---

## Review Signals

Reviews capture code review findings, security issues, and quality observations.

### Strong Signals (High Confidence)
```
- "found in review..."
- "security issue..."
- "code smell..."
- "should refactor..."
- "vulnerability..."
- "review feedback..."
```

### Capture Template
```
/memory:capture reviews <finding> -- <severity, location, remediation>
```

### Quality Criteria
- Severity/priority indicated
- Location in codebase
- Suggested remediation
- Category (security, quality, performance)

---

## Inception Signals

Inception captures project definitions, scope, and success criteria.

### Strong Signals (High Confidence)
```
- "building a..."
- "project goal is..."
- "success means..."
- "scope includes..."
- "we're creating..."
```

### Capture Template
```
/memory:capture inception <project summary> -- <goals, scope, success criteria>
```

### Quality Criteria
- Clear problem statement
- Defined success criteria
- Explicit scope boundaries
- Stakeholder context

---

## Elicitation Signals

Elicitation captures requirements clarifications and constraints discovered.

### Strong Signals (High Confidence)
```
- "must support..."
- "requirement is..."
- "constraint..."
- "needs to..."
- "won't work without..."
```

### Capture Template
```
/memory:capture elicitation <requirement> -- <source, rationale, impact>
```

### Quality Criteria
- Source of requirement
- Rationale understood
- Impact on design noted
- Priority if known

---

## Retrospective Signals

Retrospectives capture post-mortems, lessons learned, and process improvements.

### Strong Signals (High Confidence)
```
- "retrospective..."
- "lessons learned..."
- "what went well..."
- "what to improve..."
- "post-mortem..."
```

### Capture Template
```
/memory:capture retrospective <summary> -- <what went well, what to improve, lessons>
```

### Quality Criteria
- Balanced (not just negatives)
- Actionable improvements
- Specific examples
- Timeline context

---

## Confidence Scoring

The signal detection system uses confidence scoring:

| Confidence | Threshold | Action |
|------------|-----------|--------|
| High (≥0.90) | Strong signal + context match | Auto-suggest capture with template |
| Medium (0.70-0.89) | Moderate signal or partial context | Offer capture option |
| Low (0.50-0.69) | Weak signal | No proactive suggestion |
| None (<0.50) | No signals detected | Silent |

### Multi-Signal Boost
When multiple signals align:
- 2 signals: +0.1 confidence
- 3+ signals: +0.15 confidence

Example: "We decided to use PostgreSQL after evaluating SQLite" contains:
- Decision signal: "decided to" (+0.85)
- Research signal: "after evaluating" (+0.1 boost)
- Final confidence: 0.95 (auto-suggest)

---

## Anti-Patterns

Content that should NOT be captured:

### Trivial Content
```
- Basic syntax questions
- Typo fixes
- Import statements
- Single-line changes without context
```

### Sensitive Content
```
- API keys or secrets
- Passwords or credentials
- Personal information
- Internal URLs or endpoints
```

### Ephemeral Content
```
- Temporary debugging statements
- Draft implementations marked for removal
- Test data
- WIP notes without lasting value
```

### Duplicative Content
```
- Already captured insights
- Information in project docs
- Standard library behavior
- Well-known best practices
```

---

## Integration Example

```python
def detect_capture_opportunity(message: str) -> CaptureSignal | None:
    """Detect if a message contains capture-worthy content."""

    signals = []

    # Check each namespace's signals
    for namespace, patterns in SIGNAL_PATTERNS.items():
        for pattern, base_confidence in patterns:
            if pattern.lower() in message.lower():
                signals.append(CaptureSignal(
                    namespace=namespace,
                    pattern=pattern,
                    confidence=base_confidence,
                    context=message
                ))

    if not signals:
        return None

    # Sort by confidence, apply multi-signal boost
    signals.sort(key=lambda s: s.confidence, reverse=True)
    best = signals[0]

    if len(signals) > 1:
        best.confidence = min(1.0, best.confidence + 0.1)
    if len(signals) > 2:
        best.confidence = min(1.0, best.confidence + 0.05)

    return best if best.confidence >= 0.7 else None
```
