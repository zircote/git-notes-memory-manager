#!/usr/bin/env python3
"""Display observability metrics for the memory system.

This script handles argument parsing safely via sys.argv,
avoiding command injection vulnerabilities from string interpolation.

Usage:
    python scripts/metrics.py [--format=text|json|prometheus] [--filter=<pattern>]
"""

from __future__ import annotations

import argparse
import json
import sys


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments safely."""
    parser = argparse.ArgumentParser(
        description="Display observability metrics for the memory system"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "prometheus"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default=None,
        help="Filter metrics by name pattern",
    )
    return parser.parse_args()


def main() -> int:
    """Display metrics in the requested format."""
    args = parse_args()
    format_type = args.format
    filter_pattern = args.filter

    # Import after parsing to avoid slow imports if --help is used
    from git_notes_memory.observability.metrics import get_metrics

    metrics = get_metrics()

    if format_type == "json":
        output = metrics.export_json()
        if filter_pattern:
            data = json.loads(output)
            data["counters"] = {
                k: v for k, v in data.get("counters", {}).items() if filter_pattern in k
            }
            data["histograms"] = {
                k: v
                for k, v in data.get("histograms", {}).items()
                if filter_pattern in k
            }
            data["gauges"] = {
                k: v for k, v in data.get("gauges", {}).items() if filter_pattern in k
            }
            output = json.dumps(data, indent=2)
        print(output)

    elif format_type == "prometheus":
        from git_notes_memory.observability.exporters.prometheus import (
            PrometheusExporter,
        )

        exporter = PrometheusExporter()
        output = exporter.export(metrics)
        if filter_pattern:
            lines = output.split("\n")
            filtered = [
                line
                for line in lines
                if not line.strip() or line.startswith("#") or filter_pattern in line
            ]
            output = "\n".join(filtered)
        print(output)

    else:
        # Text format (default)
        output = metrics.export_text()
        if filter_pattern:
            lines = output.split("\n")
            filtered = [
                line
                for line in lines
                if not line.strip() or filter_pattern.lower() in line.lower()
            ]
            output = "\n".join(filtered)
        print("## Observability Metrics\n")
        print(output if output.strip() else "(No metrics collected yet)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
