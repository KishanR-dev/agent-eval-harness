"""Executable CLI for comparing evaluation runs against reference baselines.

Provides deterministic exit codes and structured markdown reports.

Exit codes:
    0: Success — Runs are compatible and zero regressions were detected.
    1: Regression — Critical deterministic or semantic regressions were detected.
    2: Incompatible — Runs cannot be compared due to schema, dataset, or rubric mismatch.
    3: Unavailable — Reference baseline file does not exist on disk.
    4: Invalid — Input JSON syntax error or contract validation error.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from agent_eval_harness.evaluation.baseline import (
    BaselineComparisonStatus,
    BaselineRecord,
    compare_against_baseline,
)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for baseline comparison."""
    parser = argparse.ArgumentParser(
        description="Compare evaluation run results against a reference baseline."
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
        help="Path to reference baseline JSON file.",
    )
    parser.add_argument(
        "--current",
        type=Path,
        required=True,
        help="Path to current evaluation run JSON file.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Enable strict comparison mode (fails on missing cases or incompatibility).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write markdown summary output.",
    )
    args = parser.parse_args(argv)

    baseline_path: Path = args.baseline
    current_path: Path = args.current

    # 1. Check baseline file existence
    if not baseline_path.is_file():
        print(
            f"[BASELINE COMPARISON ERROR] Reference baseline file not found: {baseline_path}",
            file=sys.stderr,
        )
        return 3

    # 2. Check current file existence
    if not current_path.is_file():
        print(
            f"[BASELINE COMPARISON ERROR] Current evaluation run file not found: {current_path}",
            file=sys.stderr,
        )
        return 4

    # 3. Load and validate baseline
    try:
        baseline_content = baseline_path.read_text(encoding="utf-8")
        baseline = BaselineRecord.model_validate_json(baseline_content)
    except (ValidationError, ValueError) as exc:
        print(
            f"[BASELINE COMPARISON ERROR] Failed to load baseline '{baseline_path}':\n  {exc}",
            file=sys.stderr,
        )
        return 4

    # 4. Load and validate current run
    try:
        current_content = current_path.read_text(encoding="utf-8")
        current = BaselineRecord.model_validate_json(current_content)
    except (ValidationError, ValueError) as exc:
        print(
            f"[BASELINE COMPARISON ERROR] Failed to load current file '{current_path}':\n  {exc}",
            file=sys.stderr,
        )
        return 4

    # 5. Execute comparison
    result = compare_against_baseline(current=current, baseline=baseline, strict=args.strict)

    # 6. Write optional output
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(result.summary, encoding="utf-8")
        except OSError as exc:
            print(f"[BASELINE WARNING] Failed to write output file: {exc}", file=sys.stderr)

    # 7. Print summary to stdout/stderr
    if result.status == BaselineComparisonStatus.INCOMPATIBLE:
        print(result.summary, file=sys.stderr)
        return 2

    print(result.summary)

    if result.has_regressions:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
