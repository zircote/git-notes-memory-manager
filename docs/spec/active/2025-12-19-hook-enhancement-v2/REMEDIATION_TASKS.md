# Remediation Tasks

Generated from code review on 2025-12-19.

## Critical (Do Immediately)

- [ ] `domain_extractor.py:259-260` - Fix singleton pattern for DomainExtractor - [Performance]
  ```python
  _default_extractor: DomainExtractor | None = None
  def extract_domain_terms(file_path: str) -> list[str]:
      global _default_extractor
      if _default_extractor is None:
          _default_extractor = DomainExtractor()
      return _default_extractor.extract(file_path)
  ```

## High Priority (This Sprint)

- [ ] `hooks/*.py` - Extract common utilities to shared `hook_utils.py` - [Code Quality]
  - `_setup_logging()`, `_setup_timeout()`, `_cancel_timeout()`, `_read_input()`
  - Affects: pre_compact_handler, post_tool_use_handler, stop_handler, session_start_handler, user_prompt_handler

- [ ] `novelty_checker.py:253-277` - Implement true batch embedding and search - [Performance]

- [ ] `README.md` - Add PostToolUse and PreCompact hooks documentation - [Documentation]

- [ ] `docs/USER_GUIDE.md` - Add complete hook sections for PostToolUse and PreCompact - [Documentation]
  - Include all configuration environment variables
  - Add usage examples

## Medium Priority (Next 2-3 Sprints)

- [ ] `session_analyzer.py:145-152` - Add path validation for transcript paths - [Security]
  ```python
  # Validate path is within expected directory
  allowed_base = Path(os.environ.get("CLAUDE_CODE_TRANSCRIPTS_DIR", "/tmp"))
  try:
      path.relative_to(allowed_base)
  except ValueError:
      logger.warning("Transcript path outside allowed directory")
      return None
  ```

- [ ] `pre_compact_handler.py:94-112`, `post_tool_use_handler.py:97-115` - Add JSON input size limits - [Security]
  ```python
  MAX_INPUT_SIZE = 10 * 1024 * 1024  # 10MB
  input_text = sys.stdin.read(MAX_INPUT_SIZE + 1)
  if len(input_text) > MAX_INPUT_SIZE:
      raise ValueError("Input too large")
  ```

- [ ] `guidance_builder.py:119`, `namespace_parser.py:30` - Consolidate VALID_NAMESPACES - [Code Quality]

- [ ] `config_loader.py:272-418` - Refactor to use declarative config schema - [Code Quality]

- [ ] `tests/test_hooks.py` - Add tests for PostToolUse configuration loading - [Test Coverage]

- [ ] `docs/USER_GUIDE.md` - Document SessionStart guidance configuration - [Documentation]
  - `HOOK_SESSION_START_INCLUDE_GUIDANCE`
  - `HOOK_SESSION_START_GUIDANCE_DETAIL`

- [ ] `docs/USER_GUIDE.md:566-576` - Document namespace-aware inline markers - [Documentation]
  - `[remember:namespace]`, `[capture:namespace]`, `@memory:namespace`

## Low Priority (Backlog)

- [ ] `signal_detector.py:67` - Review regex pattern for ReDoS risk - [Security]

- [ ] `pre_compact_handler.py:75-80` - Use async-signal-safe functions in timeout handler - [Security]

- [ ] `signal_detector.py:341-343` - Move reinforcers to module-level constant - [Performance]

- [ ] `session_analyzer.py:151-152` - Add transcript size limit check - [Performance]

- [ ] `pre_compact_handler.py:132-135` - Remove or fix dead code in prefix stripping - [Code Quality]

- [ ] Various handlers - Replace magic numbers with named constants - [Code Quality]

- [ ] `tests/test_pre_compact_handler.py` - Add timeout function tests - [Test Coverage]

- [ ] `tests/test_post_tool_use_handler.py` - Add timeout function tests - [Test Coverage]

- [ ] `tests/test_hooks.py` - Add direct tests for config parsing helpers - [Test Coverage]

- [ ] `docs/DEVELOPER_GUIDE.md` - Update hooks/ package structure - [Documentation]

- [ ] `docs/DEVELOPER_GUIDE.md` - Document hook models (SignalType, CaptureSignal, etc.) - [Documentation]

- [ ] `docs/DEVELOPER_GUIDE.md` - Document XMLBuilder API - [Documentation]

---

## Notes

- All critical and high priority items should be addressed before merging
- Medium priority items can be tracked as follow-up issues
- Low priority items are nice-to-haves for ongoing maintenance
