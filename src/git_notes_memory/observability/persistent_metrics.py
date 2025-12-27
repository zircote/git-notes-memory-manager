"""Persistent metrics storage for ephemeral hook processes.

Stores metric values in a JSON file to maintain cumulative counters
across separate Python process invocations (e.g., Claude Code hooks).

Uses file locking to prevent race conditions between concurrent hooks.

Usage:
    from git_notes_memory.observability.persistent_metrics import (
        load_persistent_metrics,
        save_persistent_metrics,
    )

    # At start of hook
    load_persistent_metrics()

    # At end of hook (after incrementing counters)
    save_persistent_metrics()
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from git_notes_memory.observability.metrics import get_metrics


def _get_metrics_file() -> Path:
    """Get the metrics file path, handling home directory expansion at runtime."""
    env_path = os.environ.get("MEMORY_PLUGIN_METRICS_FILE")
    if env_path:
        return Path(env_path)
    # Use Path.home() which is more robust than os.path.expanduser("~")
    return Path.home() / ".local" / "share" / "memory-plugin" / "metrics_state.json"


def load_persistent_metrics() -> None:
    """Load metric values from persistent storage into the in-memory collector.

    Reads counter and histogram values from the metrics state file and
    initializes the in-memory MetricsCollector with these values.

    This should be called at the start of hook execution to restore
    cumulative state from previous invocations.

    Thread-safe via file locking.
    """
    metrics_file = _get_metrics_file()
    if not metrics_file.exists():
        return

    try:
        with open(metrics_file) as f:
            # Shared lock for reading
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = json.load(f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        metrics = get_metrics()

        # Restore counter values
        for counter_name, counter_entries in data.get("counters", {}).items():
            for entry in counter_entries:
                labels = entry.get("labels", {})
                value = entry.get("value", 0.0)
                # Initialize counter with stored value (minus current value to get delta)
                current = metrics.get_counter_value(counter_name, labels)
                if value > current:
                    metrics.increment(
                        counter_name, amount=value - current, labels=labels
                    )

        # Restore histogram values
        for hist_name, hist_entries in data.get("histograms", {}).items():
            for entry in hist_entries:
                labels = entry.get("labels", {})
                # Restore sum and count by observing a synthetic value
                # This is a simplification - we can't fully restore histogram buckets
                count = entry.get("count", 0)
                sum_value = entry.get("sum", 0.0)
                if count > 0:
                    avg = sum_value / count
                    # Observe the average value 'count' times to approximate
                    for _ in range(count):
                        metrics.observe(hist_name, avg, labels=labels)

    except (json.JSONDecodeError, OSError, KeyError):
        # Silently ignore corrupt or inaccessible state file
        pass


def save_persistent_metrics() -> None:
    """Save current metric values to persistent storage.

    Writes counter and histogram values to the metrics state file for
    restoration by future process invocations.

    This should be called at the end of hook execution after all metrics
    have been recorded.

    Thread-safe via file locking.
    """
    metrics = get_metrics()
    metrics_file = _get_metrics_file()

    # Ensure directory exists
    metrics_file.parent.mkdir(parents=True, exist_ok=True)

    # Build state data
    data = json.loads(metrics.export_json())

    # Simplify for persistent storage (only need values, not samples)
    for hist_entries in data.get("histograms", {}).values():
        for entry in hist_entries:
            # Remove samples and bucket_counts for space efficiency
            entry.pop("bucket_counts", None)
            entry.pop("percentiles", None)

    try:
        # Use atomic write pattern: write to temp, then rename
        temp_file = metrics_file.with_suffix(".tmp")

        with open(temp_file, "w") as f:
            # Exclusive lock for writing
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Atomic rename
        temp_file.rename(metrics_file)

    except OSError:
        # Silently ignore write failures - metrics are best-effort
        pass


def reset_persistent_metrics() -> None:
    """Remove the persistent metrics file.

    Primarily for testing.
    """
    metrics_file = _get_metrics_file()
    if metrics_file.exists():
        metrics_file.unlink()
