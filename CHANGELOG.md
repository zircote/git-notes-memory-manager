# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Add GitHub release creation to Makefile release workflow

## [0.11.0] - 2025-12-25

### Added
- Add warnings when git version detection fails for better debugging
- Configure git identity in bare remote for CI test robustness

### Fixed
- Address Copilot code review: safer regex fallback for older git versions
- Address Copilot code review: branch detection error handling in tests
- Extract SYNC_CORE_KEYS as module constant for DRY

## [0.10.0] - 2025-12-25

### Added
- Fix git notes fetch refspec for multi-machine sync (closes #18)
- Use remote tracking refs pattern (`+refs/notes/mem/*:refs/notes/origin/mem/*`)
- Add git version detection for backwards compatibility (git < 2.37)
- Auto-migrate from old refspec pattern on session start
- Hook-based auto-sync (opt-in via `HOOK_SESSION_START_FETCH_REMOTE` and `HOOK_STOP_PUSH_REMOTE`)

### Security
- Fix TOCTOU race condition in file locking with O_NOFOLLOW flag
- Add subprocess timeout (30s) to prevent indefinite hangs
- Restrict lock file permissions to 0o600
- Add thread-safe locking to ServiceRegistry and IndexService

### Fixed
- Fix missing `repo_path` in batch insert operations
- Fix blocking lock acquisition with timeout mechanism

### Changed
- Enable SQLite WAL mode for better concurrent access

## [0.9.1] - 2025-12-24

### Fixed
- Add .DS_Store to gitignore

### Changed
- Update guidance builder tests to match new templates

## [0.9.0] - 2025-12-24

### Added
- Pyright type checker configuration
- Project hooks for Python code quality (format, lint, typecheck)

### Fixed
- Use project-specific index path in status and validate commands
- Correct byte counting in batch content parsing

### Changed
- Strengthen memory block guidance with balanced requirements

## [0.8.0] - 2025-12-22

### Added
- Comprehensive tests for hook_utils and session_analyzer
- API Reference documentation
- Environment variables documentation
- Command help documentation

### Fixed
- Address code review findings for performance and quality
- Address GitHub Copilot code review feedback
- Fix unused variables and redundant imports

### Changed
- Simplify ServiceRegistry by removing over-engineering
- Archive code review artifacts to docs/code-review/

## [0.7.1] - 2025-12-21

### Fixed
- Update dependencies for ARM64 compatibility

## [0.7.0] - 2025-12-21

### Added
- Auto-configure git notes sync on session start
- Research paper on git-native semantic memory for LLM agents

## [0.6.2] - 2025-12-20

### Fixed
- Minor bug fixes

## [0.6.1] - 2025-12-20

### Added
- Rotating file logging
- Increased capture limits

## [0.6.0] - 2025-12-19

### Changed
- Replace ANSI colors with unicode block markers for terminal output

## [0.5.4] - 2025-12-19

### Added
- Colored ::: block markers for terminal output

## [0.5.3] - 2025-12-19

### Fixed
- Remove duplicate hooks reference from plugin manifest

## [0.5.2] - 2025-12-19

### Fixed
- Complete hook-based memory capture with block markers

## [0.5.1] - 2025-12-19

### Added
- Enhanced auto-capture across all hook events

## [0.5.0] - 2025-12-19

### Added
- Enable hooks by default
- Enhanced memory capture system

## [0.4.1] - 2025-12-18

### Fixed
- Add --python flag to uv pip install for correct venv targeting

## [0.4.0] - 2025-12-18

### Added
- Release workflow targets to Makefile

### Changed
- Replace Python bootstrap with bash shell wrapper for hook venv management

### Fixed
- Correct plugin.json path in bumpversion config
- Add explanatory comments to remaining bare exception handlers
- Address GitHub Copilot code review findings

## [0.3.1] - 2025-12-17

### Fixed
- Initial stable release with core memory capture functionality

[Unreleased]: https://github.com/zircote/git-notes-memory/compare/v0.11.0...HEAD
[0.11.0]: https://github.com/zircote/git-notes-memory/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/zircote/git-notes-memory/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/zircote/git-notes-memory/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/zircote/git-notes-memory/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/zircote/git-notes-memory/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/zircote/git-notes-memory/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/zircote/git-notes-memory/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/zircote/git-notes-memory/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/zircote/git-notes-memory/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/zircote/git-notes-memory/compare/v0.5.4...v0.6.0
[0.5.4]: https://github.com/zircote/git-notes-memory/compare/v0.5.3...v0.5.4
[0.5.3]: https://github.com/zircote/git-notes-memory/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/zircote/git-notes-memory/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/zircote/git-notes-memory/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/zircote/git-notes-memory/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/zircote/git-notes-memory/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/zircote/git-notes-memory/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/zircote/git-notes-memory/releases/tag/v0.3.1
