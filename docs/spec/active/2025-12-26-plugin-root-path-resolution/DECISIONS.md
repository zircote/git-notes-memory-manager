---
document_type: decisions
project_id: SPEC-2025-12-26-002
---

# PLUGIN_ROOT Path Resolution Fix - Architecture Decision Records

## ADR-001: Use Python Module Imports Instead of Script Execution

**Date**: 2025-12-26
**Status**: Accepted
**Deciders**: Based on Issue #31 investigation

### Context

Commands currently resolve `PLUGIN_ROOT` via filesystem glob and execute external Python scripts. This fails for marketplace installations because the path pattern hardcodes `git-notes-memory/` instead of the marketplace namespace.

Three options were identified in Issue #31:
1. Fix the glob pattern to use wildcards
2. Use Python module imports (recommended)
3. Implement robust multi-fallback hybrid

### Decision

Use Python module imports (Option 2) for all command file script execution.

**Pattern change:**
```bash
# FROM (filesystem-based):
PLUGIN_ROOT="..."
uv run --directory "$PLUGIN_ROOT" python3 "$PLUGIN_ROOT/scripts/foo.py"

# TO (module-based):
uv run python3 -c "from git_notes_memory.module import func; func()"
```

### Consequences

**Positive:**
- Installation-agnostic (works for marketplace, direct, and source)
- No dependency on `scripts/` directory in distribution
- Simpler command files (no path resolution logic)
- More robust and maintainable
- Aligns with Python best practices

**Negative:**
- Slightly more verbose inline Python in command files
- All needed functions must be exported from package

**Neutral:**
- Still uses `uv run` for dependency management
- Command behavior unchanged

### Alternatives Considered

1. **Fix glob pattern**: `$(ls -d ~/.claude/plugins/cache/*/memory-capture ...)`
   - Pros: Minimal change
   - Cons: Still depends on filesystem structure, doesn't solve missing scripts/

2. **Robust hybrid fallback**: Multiple fallback paths with final PWD fallback
   - Pros: Handles all scenarios
   - Cons: Still requires scripts/ in distribution, more complex

---

## ADR-002: Inline Python via -c Flag for Simple Operations

**Date**: 2025-12-26
**Status**: Accepted
**Deciders**: Implementation team

### Context

With module imports, we need a way to execute Python code from bash command files. Options include:
1. `python3 -c "inline code"`
2. Heredoc with `python3 << 'EOF'`
3. Temporary script files

### Decision

Use `python3 -c "..."` for operations that fit on a few lines, and heredoc for complex multi-line operations.

### Consequences

**Positive:**
- No temporary files created
- Clear and readable for simple operations
- Argument passing via `$ARGUMENTS` works naturally

**Negative:**
- Quote escaping can be tricky
- Very long inline code becomes hard to read

---

## ADR-003: No Fallback to CLAUDE_PLUGIN_ROOT

**Date**: 2025-12-26
**Status**: Accepted
**Deciders**: Implementation team

### Context

Should we keep `CLAUDE_PLUGIN_ROOT` as a fallback even with module imports?

### Decision

Remove `CLAUDE_PLUGIN_ROOT` references entirely. Module imports don't need it.

### Consequences

**Positive:**
- Simpler command files
- No environment variable dependency
- Works identically in all environments

**Negative:**
- Users who set CLAUDE_PLUGIN_ROOT for other reasons won't benefit from it

**Neutral:**
- The environment variable can still be set but is simply unused

---

## ADR-004: Keep uv run for Dependency Management

**Date**: 2025-12-26
**Status**: Accepted
**Deciders**: Implementation team

### Context

Should commands use `uv run python3` or direct `python3`?

### Decision

Continue using `uv run python3` to ensure dependencies are available.

### Consequences

**Positive:**
- Automatic dependency resolution
- Works in virtual environments
- Consistent with existing pattern

**Negative:**
- Requires uv to be installed
- Slightly slower startup

---

## ADR-005: Verify Module Exports Before Implementation

**Date**: 2025-12-26
**Status**: Accepted
**Deciders**: Implementation team

### Context

Not all functions may be properly exported from the package. This could cause import errors in commands.

### Decision

Before changing each command file:
1. Verify the required function is exported
2. Check import path is correct
3. Test import in isolation

### Consequences

**Positive:**
- Prevents broken commands
- Identifies missing exports early
- Documents actual module structure

**Negative:**
- Slightly more verification work per task
