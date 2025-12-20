---
description: Validate memory system hooks, capture pipeline, and recall functionality
argument-hint: "[--verbose] [--fix]"
allowed-tools: ["Bash", "Read"]
---

# /memory:validate - Memory System Validation

Run comprehensive validation of the memory plugin, including all hooks and the capture/recall pipeline.

## Your Task

You will validate that the memory system is functioning correctly by testing all components.

### Step 1: Parse Arguments

**Arguments format**: `$ARGUMENTS`

- `--verbose`: Show detailed output for each test
- `--fix`: Attempt to fix issues found (e.g., repair index, sync after capture)

### Step 2: Run Validation Suite

Execute the validation script:

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/git-notes-memory/memory-capture/*/ 2>/dev/null | head -1)}"
uv run --directory "$PLUGIN_ROOT" python3 << 'VALIDATION_SCRIPT'
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv
FIX_ISSUES = "--fix" in sys.argv

validation_results = {
    "passed": [],
    "failed": [],
    "warnings": [],
}

def log(msg, indent=0):
    if VERBOSE:
        print("  " * indent + msg)

def test_pass(name, detail=None):
    validation_results["passed"].append({"name": name, "detail": detail})
    print(f"✓ {name}")
    if detail and VERBOSE:
        print(f"    {detail}")

def test_fail(name, error):
    validation_results["failed"].append({"name": name, "error": str(error)})
    print(f"✗ {name}")
    print(f"    Error: {error}")

def test_warn(name, warning):
    validation_results["warnings"].append({"name": name, "warning": str(warning)})
    print(f"⚠ {name}")
    print(f"    Warning: {warning}")

print("=" * 60)
print("MEMORY SYSTEM VALIDATION")
print("=" * 60)
print()

# ============================================================================
# TEST 1: Library Import
# ============================================================================
print("## 1. Core Library")
print("-" * 40)

try:
    from git_notes_memory import get_capture_service, get_recall_service, get_sync_service
    test_pass("Library import")
except ImportError as e:
    test_fail("Library import", e)
    print("\nFATAL: Cannot continue without core library.")
    sys.exit(1)

try:
    from git_notes_memory.config import get_index_path, get_data_path, NAMESPACES
    test_pass("Config module", f"Data path: {get_data_path()}")
except Exception as e:
    test_fail("Config module", e)

try:
    from git_notes_memory.index import IndexService
    test_pass("Index module")
except Exception as e:
    test_fail("Index module", e)

try:
    from git_notes_memory.embedding import EmbeddingService
    emb = EmbeddingService()
    test_pass("Embedding service", f"Model loaded")
except Exception as e:
    test_warn("Embedding service", f"Degraded mode - {e}")

print()

# ============================================================================
# TEST 2: Git Repository
# ============================================================================
print("## 2. Git Repository")
print("-" * 40)

try:
    result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, text=True)
    if result.returncode == 0:
        test_pass("Git repository detected", result.stdout.strip())
    else:
        test_fail("Git repository", "Not in a git repository")
except Exception as e:
    test_fail("Git repository", e)

try:
    result = subprocess.run(["git", "notes", "list"], capture_output=True, text=True)
    if result.returncode == 0:
        test_pass("Git notes accessible")
    else:
        test_warn("Git notes", "No notes found or notes not accessible")
except Exception as e:
    test_fail("Git notes", e)

print()

# ============================================================================
# TEST 3: Index Health
# ============================================================================
print("## 3. Index Health")
print("-" * 40)

try:
    index_path = get_index_path()
    if index_path.exists():
        test_pass("Index file exists", str(index_path))
        index = IndexService(index_path)
        index.initialize()
        stats = index.get_stats()
        test_pass("Index readable", f"{stats.total_memories} memories indexed")

        # Check consistency
        sync = get_sync_service()
        verification = sync.verify_consistency()

        if verification.is_consistent:
            test_pass("Index consistency")
        else:
            orphaned = len(verification.orphaned_in_index)
            missing = len(verification.missing_in_index)
            if FIX_ISSUES:
                log(f"Repairing: {orphaned} orphaned, {missing} missing...", 1)
                sync.repair()
                # Re-verify after repair
                verification2 = sync.verify_consistency()
                if verification2.is_consistent:
                    test_pass("Index consistency", f"Repaired {orphaned} orphaned, {missing} missing")
                else:
                    test_warn("Index consistency", f"Repair incomplete - re-run validation")
            else:
                test_warn("Index consistency", f"{orphaned} orphaned, {missing} missing (run with --fix)")

        index.close()
    else:
        test_warn("Index file", "Not initialized - run /memory:sync")
except Exception as e:
    test_fail("Index health", e)

print()

# ============================================================================
# TEST 4: Hook Entry Points
# ============================================================================
print("## 4. Hook Entry Points")
print("-" * 40)

# Discover plugin root dynamically (version-agnostic)
plugin_cache = Path.home() / '.claude/plugins/cache/git-notes-memory/memory-capture'
plugin_versions = sorted(plugin_cache.glob('*/'), key=lambda p: p.name, reverse=True) if plugin_cache.exists() else []
plugin_root = plugin_versions[0] if plugin_versions else plugin_cache / '0.3.0'
hooks_dir = plugin_root / "hooks"
hooks = [
    ("sessionstart.py", "SessionStart", "Context injection at session start"),
    ("userpromptsubmit.py", "UserPromptSubmit", "Capture marker detection"),
    ("posttooluse.py", "PostToolUse", "Related memory injection after edits"),
    ("precompact.py", "PreCompact", "Memory preservation before compaction"),
    ("stop.py", "Stop", "Session analysis and index sync"),
]

for filename, hook_name, description in hooks:
    hook_path = hooks_dir / filename
    if hook_path.exists():
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(filename.replace('.py', ''), hook_path)
            if spec and spec.loader:
                test_pass(f"{hook_name} hook", description)
            else:
                test_warn(f"{hook_name} hook", "Could not load module spec")
        except SyntaxError as e:
            test_fail(f"{hook_name} hook", f"Syntax error: {e}")
        except Exception as e:
            test_warn(f"{hook_name} hook", f"Load warning: {e}")
    else:
        test_fail(f"{hook_name} hook", f"File not found: {hook_path}")

print()

# ============================================================================
# TEST 5: Hook Handler Imports
# ============================================================================
print("## 5. Hook Handlers")
print("-" * 40)

handlers = [
    ("git_notes_memory.hooks.stop_handler", "Stop handler"),
    ("git_notes_memory.hooks.post_tool_use_handler", "PostToolUse handler"),
    ("git_notes_memory.hooks.pre_compact_handler", "PreCompact handler"),
]

for module_name, handler_name in handlers:
    try:
        import importlib
        mod = importlib.import_module(module_name)
        if hasattr(mod, 'main'):
            test_pass(handler_name, "main() available")
        else:
            test_warn(handler_name, "Imported but no main()")
    except ImportError as e:
        test_warn(handler_name, f"Import failed: {e}")
    except Exception as e:
        test_fail(handler_name, e)

print()

# ============================================================================
# TEST 6: Capture Pipeline
# ============================================================================
print("## 6. Capture Pipeline")
print("-" * 40)

test_memory_id = None
test_marker = f"VALIDATION_TEST_{uuid.uuid4().hex[:8]}"

try:
    capture = get_capture_service()

    result = capture.capture(
        namespace="learnings",
        summary=f"Validation test memory {test_marker}",
        content=f"Test memory created by /memory:validate at {datetime.now().isoformat()}. Marker: {test_marker}",
        tags=["validation", "test"],
    )

    if result.success:
        test_memory_id = result.memory.id
        test_pass("Memory capture", f"ID: {test_memory_id[:20]}...")

        # If --fix, reindex immediately so recall test works
        if FIX_ISSUES:
            try:
                sync_svc = get_sync_service()
                sync_svc.reindex()
                log("Index reindexed for recall test", 1)
            except Exception as sync_err:
                log(f"Reindex failed: {sync_err}", 1)
    else:
        test_fail("Memory capture", result.warning or "Unknown error")
except Exception as e:
    test_fail("Memory capture", e)

print()

# ============================================================================
# TEST 7: Recall Pipeline
# ============================================================================
print("## 7. Recall Pipeline")
print("-" * 40)

if test_memory_id:
    try:
        recall = get_recall_service()

        # Test semantic search
        search_results = recall.search(
            query=f"validation test {test_marker}",
            k=5,
            namespace="learnings",
        )

        found = any(test_marker in (r.content or '') for r in search_results)
        if found:
            test_pass("Semantic search", f"Found test memory in {len(search_results)} results")
        else:
            if FIX_ISSUES:
                test_warn("Semantic search", "Test memory not found even after sync")
            else:
                test_warn("Semantic search", "Not found - run with --fix to sync first")

        # Test text search if available
        try:
            text_results = recall.search_text(
                query=test_marker,
                limit=5,
                namespace="learnings",
            )
            if text_results:
                test_pass("Text search", f"Found {len(text_results)} results")
            else:
                if FIX_ISSUES:
                    test_warn("Text search", "No results even after sync")
                else:
                    test_warn("Text search", "No results - run with --fix to sync first")
        except AttributeError:
            log("Text search method not available", 1)
        except Exception as e:
            test_warn("Text search", str(e))

    except Exception as e:
        test_fail("Recall pipeline", e)
else:
    test_warn("Recall pipeline", "Skipped - no test memory was captured")

print()

# ============================================================================
# TEST 8: Cleanup
# ============================================================================
print("## 8. Cleanup")
print("-" * 40)

if test_memory_id:
    try:
        # Parse memory ID: {namespace}:{commit_sha}:{index}
        parts = test_memory_id.split(":")
        if len(parts) >= 2:
            namespace = parts[0]
            commit_sha = parts[1]

            # Remove the git note
            log(f"Removing test note from refs/notes/mem/{namespace}...", 1)
            rm_result = subprocess.run(
                ["git", "notes", f"--ref=refs/notes/mem/{namespace}", "remove", commit_sha],
                capture_output=True, text=True
            )

            if rm_result.returncode == 0:
                # Reindex to update SQLite index
                sync_svc = get_sync_service()
                sync_svc.reindex()

                # Verify the test note is gone by searching for the marker
                verify_results = recall.search(query=test_marker, k=5, namespace=namespace)
                still_exists = any(test_marker in (r.content or '') for r in verify_results)

                if not still_exists:
                    test_pass("Test cleanup", f"Removed {test_memory_id[:20]}...")
                else:
                    test_warn("Test cleanup", "Note removed but still in index")
            else:
                test_warn("Test cleanup", f"git notes remove failed: {rm_result.stderr.strip()}")
        else:
            test_warn("Test cleanup", f"Invalid memory ID format: {test_memory_id}")
    except Exception as e:
        test_warn("Test cleanup", f"Cleanup failed: {e}")
else:
    test_pass("Test cleanup", "No test memory to clean up")

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("=" * 60)
print("VALIDATION SUMMARY")
print("=" * 60)
print()

total = len(validation_results["passed"]) + len(validation_results["failed"]) + len(validation_results["warnings"])
print(f"Total tests: {total}")
print(f"  ✓ Passed:   {len(validation_results['passed'])}")
print(f"  ✗ Failed:   {len(validation_results['failed'])}")
print(f"  ⚠ Warnings: {len(validation_results['warnings'])}")
print()

if validation_results["failed"]:
    print("FAILED TESTS:")
    for item in validation_results["failed"]:
        print(f"  - {item['name']}: {item['error']}")
    print()

if validation_results["warnings"]:
    print("WARNINGS:")
    for item in validation_results["warnings"]:
        print(f"  - {item['name']}: {item['warning']}")
    print()

if not validation_results["failed"]:
    print("✓ Memory system is operational")
else:
    print("✗ Memory system has issues that need attention")
    sys.exit(1)
VALIDATION_SCRIPT
```

### Step 3: Present Results

The validation script outputs a formatted report with test results.

**If all tests pass:**
```
✓ Memory system is operational

All hooks are configured and the capture/recall pipeline is functioning.
```

**If there are failures:**
```
✗ Memory system has issues

Review the failed tests above. Common fixes:
- "Library import" failed: Ensure git-notes-memory is installed
- "Git repository" failed: Run from within a git repository
- "Index consistency" warning: Run `/memory:sync repair` or use `--fix`
- "Hook entry point" failed: Check plugin installation
```

## Validation Tests

| Test | What It Checks |
|------|---------------|
| **Core Library** | Python imports, config, index, embedding modules |
| **Git Repository** | Running in a git repo, git notes accessible |
| **Index Health** | Index exists, readable, consistent with git notes |
| **Hook Entry Points** | All 5 hook files exist and have valid syntax |
| **Hook Handlers** | Internal handler modules can be imported |
| **Capture Pipeline** | Can capture a test memory to git notes |
| **Recall Pipeline** | Can search and find the test memory |
| **Cleanup** | Reports any test artifacts created |

## Examples

**User**: `/memory:validate`
**Action**: Run standard validation suite

**User**: `/memory:validate --verbose`
**Action**: Run with detailed output for each test

**User**: `/memory:validate --fix`
**Action**: Repair index, sync after capture for accurate recall testing

## Troubleshooting

If validation fails, common remediation steps:

| Failure | Fix |
|---------|-----|
| Library import | `uv sync` in plugin directory |
| Not in git repo | Navigate to a git repository |
| Index not initialized | `/memory:sync` |
| Index inconsistency | `/memory:sync repair` or use `--fix` |
| Hook file missing | Reinstall plugin |
| Capture failed | Check git permissions, disk space |
| Search failed | Use `--fix` to sync before search, or run `/memory:sync` |
