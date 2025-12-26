#!/usr/bin/env python3
"""Health check with optional timing percentiles.

This script handles argument parsing safely via sys.argv,
avoiding command injection vulnerabilities from string interpolation.

Usage:
    python scripts/health.py [--timing] [--verbose]
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments safely."""
    parser = argparse.ArgumentParser(
        description="Health check with optional timing percentiles"
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Include latency percentiles from metrics",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed component status",
    )
    return parser.parse_args()


def main() -> int:
    """Run health check and display results."""
    args = parse_args()
    show_timing = args.timing
    verbose = args.verbose

    print("## Memory System Health\n")

    # Component checks
    checks: list[tuple[str, bool, str]] = []

    # 1. Git repository check
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],  # noqa: S607, S603
            capture_output=True,
            text=True,
            timeout=10,
        )
        git_ok = result.returncode == 0
        checks.append(
            ("Git Repository", git_ok, "Accessible" if git_ok else "Not found")
        )
    except Exception as e:
        checks.append(("Git Repository", False, str(e)))

    # 2. Git notes check
    try:
        result = subprocess.run(
            ["git", "notes", "list"],  # noqa: S607, S603
            capture_output=True,
            text=True,
            timeout=10,
        )
        notes_ok = result.returncode == 0
        checks.append(
            ("Git Notes", notes_ok, "Accessible" if notes_ok else "Not configured")
        )
    except Exception as e:
        checks.append(("Git Notes", False, str(e)))

    # 3. Index check
    try:
        from git_notes_memory.config import get_project_index_path

        index_path = get_project_index_path()
        index_ok = index_path.exists()
        checks.append(
            ("Index", index_ok, "Initialized" if index_ok else "Not initialized")
        )
    except Exception as e:
        checks.append(("Index", False, str(e)))

    # 4. Embedding model check
    try:
        from git_notes_memory.embedding import EmbeddingService

        _ = EmbeddingService()
        emb_ok = True
        checks.append(("Embedding Model", emb_ok, "Available"))
    except Exception:
        checks.append(("Embedding Model", False, "Not loaded"))

    # 5. Hook system check (just check if config loads)
    try:
        from git_notes_memory.hooks.config_loader import load_hook_config

        config = load_hook_config()
        hooks_ok = config.enabled
        checks.append(("Hook System", hooks_ok, "Enabled" if hooks_ok else "Disabled"))
    except Exception as e:
        checks.append(("Hook System", False, str(e)))

    # Display results
    print("| Component | Status | Details |")
    print("|-----------|--------|---------|")

    all_ok = True
    for name, ok, details in checks:
        status = "\u2713" if ok else "\u2717"
        if not ok:
            all_ok = False
        print(f"| {name} | {status} | {details} |")

    print()

    # Overall health
    if all_ok:
        print("**Overall**: \u2713 Healthy")
    else:
        print("**Overall**: \u26a0 Issues detected")
    print()

    # Timing section
    if show_timing:
        _display_timing()

    # Verbose details
    if verbose:
        _display_verbose()

    return 0


def _display_timing() -> None:
    """Display latency percentiles from metrics."""
    print("### Latency Percentiles\n")

    from git_notes_memory.observability.metrics import get_metrics

    metrics = get_metrics()

    # Get histogram stats
    with metrics._lock:
        histograms = list(metrics._histograms.items())

    if not histograms:
        print("No timing data collected yet. Run some memory commands first.")
    else:
        print("| Metric | p50 | p95 | p99 | Avg |")
        print("|--------|-----|-----|-----|-----|")

        for hist_name, hist_label_values in sorted(histograms):
            for labels, histogram in hist_label_values.items():
                if histogram.count == 0:
                    continue

                samples = histogram.samples
                if samples:
                    sorted_samples = sorted(samples)
                    n = len(sorted_samples)
                    p50 = sorted_samples[int(n * 0.5)] if n > 0 else 0
                    p95 = sorted_samples[int(n * 0.95)] if n > 0 else 0
                    p99 = sorted_samples[int(n * 0.99)] if n > 0 else 0
                    avg = (
                        histogram.sum_value / histogram.count
                        if histogram.count > 0
                        else 0
                    )

                    # Format label info
                    label_str = ""
                    if labels:
                        label_parts = [f"{k}={v}" for k, v in sorted(labels)]
                        label_str = f" ({label_parts[0]})" if label_parts else ""

                    print(
                        f"| {hist_name}{label_str} | {p50:.1f}ms | {p95:.1f}ms | {p99:.1f}ms | {avg:.1f}ms |"
                    )

    print()

    # Hook timeout rate
    print("### Hook Timeout Rate\n")

    with metrics._lock:
        timeouts = metrics._counters.get("hook_timeouts_total", {})
        executions = metrics._counters.get("hook_executions_total", {})

    timeout_count = sum(c.value for c in timeouts.values()) if timeouts else 0
    exec_count = sum(c.value for c in executions.values()) if executions else 0

    if exec_count > 0:
        rate = (timeout_count / exec_count) * 100
        print(
            f"- Timeouts: {int(timeout_count)} / {int(exec_count)} executions ({rate:.1f}%)"
        )
    else:
        print("- No hook executions recorded yet")

    print()


def _display_verbose() -> None:
    """Display detailed component information."""
    print("### Component Details\n")

    # Index stats if available
    try:
        from git_notes_memory.config import get_project_index_path
        from git_notes_memory.index import IndexService

        index_path = get_project_index_path()
        if index_path.exists():
            index = IndexService(index_path)
            index.initialize()
            stats = index.get_stats()

            print("**Index**:")
            print(f"- Memories: {stats.total_memories}")
            size_kb = stats.index_size_bytes / 1024
            size_str = (
                f"{size_kb / 1024:.1f} MB" if size_kb > 1024 else f"{size_kb:.1f} KB"
            )
            print(f"- Size: {size_str}")
            if stats.last_sync:
                print(f"- Last sync: {stats.last_sync.strftime('%Y-%m-%d %H:%M:%S')}")
            index.close()
            print()
    except Exception as e:
        print(f"**Index**: Unable to retrieve stats ({e})")
        print()

    # Git notes namespaces
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)", "refs/notes/mem/"],  # noqa: S607, S603
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            namespaces = [r.split("/")[-1] for r in result.stdout.strip().split("\n")]
            print("**Namespaces**: " + ", ".join(namespaces))
        else:
            print("**Namespaces**: (none configured)")
        print()
    except Exception:  # noqa: S110
        # Silently ignore git namespace listing errors - non-critical
        pass


if __name__ == "__main__":
    sys.exit(main())
