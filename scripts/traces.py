#!/usr/bin/env python3
"""Display recent trace spans for debugging.

This script handles argument parsing safely via sys.argv,
avoiding command injection vulnerabilities from string interpolation.

Usage:
    python scripts/traces.py [--operation=<name>] [--status=ok|error] [--limit=<n>]
"""

from __future__ import annotations

import argparse
import sys


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments safely."""
    parser = argparse.ArgumentParser(
        description="Display recent trace spans for debugging"
    )
    parser.add_argument(
        "--operation",
        type=str,
        default=None,
        help="Filter by operation name",
    )
    parser.add_argument(
        "--status",
        choices=["ok", "error"],
        default=None,
        help="Filter by status",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum traces to show (default: 10)",
    )
    return parser.parse_args()


def main() -> int:
    """Display traces in table format."""
    args = parse_args()
    operation_filter = args.operation
    status_filter = args.status
    limit = args.limit

    # Import after parsing to avoid slow imports if --help is used
    from git_notes_memory.observability.tracing import get_completed_spans

    spans = get_completed_spans()

    # Apply filters
    if operation_filter:
        spans = [s for s in spans if operation_filter.lower() in s.operation.lower()]
    if status_filter:
        spans = [s for s in spans if s.status == status_filter]

    # Sort by end time (most recent first) and apply limit
    spans = sorted(spans, key=lambda s: s.end_time or s.start_time, reverse=True)[
        :limit
    ]

    if not spans:
        print("## Recent Traces\n")
        print("No traces recorded yet. Traces are captured during:")
        print("- /memory:capture operations")
        print("- /memory:recall searches")
        print("- Hook executions")
        print("- Index operations")
        print()
        print("Run some memory commands to generate traces.")
    else:
        print("## Recent Traces\n")
        filter_msg = " (filtered)" if operation_filter or status_filter else ""
        print(f"Showing {len(spans)} trace(s){filter_msg}")
        print()

        print("| Operation | Duration | Status | Time | Details |")
        print("|-----------|----------|--------|------|---------|")

        for span in spans:
            duration = f"{span.duration_ms:.1f}ms" if span.duration_ms else "-"
            if span.status == "ok":
                status = "\u2713"  # checkmark
            elif span.status == "error":
                status = "\u2717"  # x mark
            else:
                status = "\u25cb"  # circle
            time_str = (
                span.start_datetime.strftime("%H:%M:%S") if span.start_datetime else "-"
            )

            # Build details from tags
            details = []
            for key, value in sorted(span.tags.items()):
                if len(str(value)) > 20:
                    value = str(value)[:17] + "..."
                details.append(f"{key}={value}")
            details_str = ", ".join(details[:3]) if details else "-"

            print(
                f"| {span.operation} | {duration} | {status} | {time_str} | {details_str} |"
            )

        print()

        # Show summary stats
        total_duration = sum(s.duration_ms or 0 for s in spans)
        error_count = sum(1 for s in spans if s.status == "error")

        print("### Summary")
        print(f"- Total traces: {len(spans)}")
        print(f"- Total duration: {total_duration:.1f}ms")
        if error_count:
            print(f"- Errors: {error_count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
