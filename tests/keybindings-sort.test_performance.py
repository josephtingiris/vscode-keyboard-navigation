#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Performance harness for `bin/keybindings-sort.py` with three run profiles.

Usage:
    ./tests/keybindings-sort.test_performance.py --mode quick
    ./tests/keybindings-sort.test_performance.py --mode small
    ./tests/keybindings-sort.test_performance.py --mode full

Profiles:
- quick: small perf gauge for rapid feedback
- small: medium matrix for trend checks
- full: complete 252-combination matrix
"""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PRIMARY_VALS = ["key", "when"]
SECONDARY_VALS: list[str | None] = [None, "key", "when"]
GROUP_SORTING_VALS = [
    "alpha",
    "beta",
    "natural",
    "positive-natural",
    "negative-natural",
    "positive",
    "negative",
]
WHEN_GROUPING_VALS = ["none", "config-first", "focal-invariant"]
OBJECT_CLONES_VALS = [False, True]

QUICK_CASES: list[tuple[str, str | None, str, str, bool]] = [
    ("key", "when", "alpha", "none", False),
    ("key", "when", "positive-natural", "focal-invariant", False),
    ("key", "when", "negative-natural", "focal-invariant", True),
    ("when", "key", "natural", "focal-invariant", False),
    ("when", None, "positive", "config-first", False),
    ("when", None, "negative", "none", True),
]

SMALL_GROUP_SORTING_VALS = ["alpha", "natural", "positive-natural", "negative-natural"]
SMALL_WHEN_GROUPING_VALS = ["none", "focal-invariant"]
DEFAULT_INPUT_QUICK_SMALL = "references/keybindings.surface.vi.jsonc"
DEFAULT_INPUT_FULL = "references/keybindings.surface.all.jsonc"


def build_combos(mode: str) -> list[tuple[str, str | None, str, str, bool]]:
    """Return the combination set for the selected run mode."""
    if mode == "quick":
        return QUICK_CASES
    if mode == "small":
        return list(
            itertools.product(
                PRIMARY_VALS,
                SECONDARY_VALS,
                SMALL_GROUP_SORTING_VALS,
                SMALL_WHEN_GROUPING_VALS,
                OBJECT_CLONES_VALS,
            )
        )
    return list(
        itertools.product(
            PRIMARY_VALS,
            SECONDARY_VALS,
            GROUP_SORTING_VALS,
            WHEN_GROUPING_VALS,
            OBJECT_CLONES_VALS,
        )
    )


def default_runs_for_mode(mode: str) -> int:
    """Return default measured runs per combination for a mode."""
    if mode == "quick":
        return 2
    if mode == "small":
        return 2
    return 3


def default_warmups_for_mode(mode: str) -> int:
    """Return default warmup runs per combination for a mode."""
    if mode == "quick":
        return 0
    return 1


def run_case(
    python_exe: str,
    script: Path,
    input_data: bytes,
    combo: tuple[str, str | None, str, str, bool],
    runs_per_combo: int,
    warmup_runs: int,
) -> dict[str, Any]:
    """Execute a single benchmark case and return timing stats."""
    primary, secondary, group_sorting, when_grouping, object_clones = combo

    args = [
        python_exe,
        str(script),
        "--primary",
        primary,
        "--group-sorting",
        group_sorting,
        "--when-grouping",
        when_grouping,
        "--color",
        "never",
    ]
    if secondary is not None:
        args.extend(["--secondary", secondary])
    if object_clones:
        args.append("--object-clones")

    for _ in range(warmup_runs):
        subprocess.run(
            args,
            input=input_data,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )

    timings_ms: list[float] = []
    for _ in range(runs_per_combo):
        t0 = time.perf_counter()
        subprocess.run(
            args,
            input=input_data,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        t1 = time.perf_counter()
        timings_ms.append((t1 - t0) * 1000.0)

    return {
        "primary": primary,
        "secondary": secondary,
        "group_sorting": group_sorting,
        "when_grouping": when_grouping,
        "object_clones": object_clones,
        "runs_ms": timings_ms,
        "mean_ms": statistics.fmean(timings_ms),
        "median_ms": statistics.median(timings_ms),
        "min_ms": min(timings_ms),
        "max_ms": max(timings_ms),
        "stdev_ms": statistics.pstdev(timings_ms),
    }


def write_outputs(summary: dict[str, Any], out_json: Path, out_csv: Path) -> None:
    """Write json and csv benchmark artifacts."""
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    header = [
        "primary",
        "secondary",
        "group_sorting",
        "when_grouping",
        "object_clones",
        "mean_ms",
        "median_ms",
        "min_ms",
        "max_ms",
        "stdev_ms",
    ]
    lines = [",".join(header)]
    for rec in summary["all_results"]:
        row = [
            rec["primary"],
            "" if rec["secondary"] is None else rec["secondary"],
            rec["group_sorting"],
            rec["when_grouping"],
            "1" if rec["object_clones"] else "0",
            f"{rec['mean_ms']:.3f}",
            f"{rec['median_ms']:.3f}",
            f"{rec['min_ms']:.3f}",
            f"{rec['max_ms']:.3f}",
            f"{rec['stdev_ms']:.3f}",
        ]
        lines.append(",".join(row))
    out_csv.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Benchmark keybindings-sort with quick/small/full profiles")
    parser.add_argument(
        "--mode",
        choices=["quick", "small", "full"],
        default="quick",
        help="run profile: quick perf gauge, smaller matrix, or full 252 matrix",
    )
    parser.add_argument(
        "--runs-per-combo",
        type=int,
        default=None,
        help="override measured runs per combination",
    )
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=None,
        help="override warmup runs per combination",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="input keybindings file path (default: vi for quick/small, all for full)",
    )
    parser.add_argument(
        "--out-prefix",
        default=None,
        help="output prefix path (without extension)",
    )
    parser.add_argument(
        "--max-overall-median-ms",
        type=float,
        default=None,
        help="optional budget check; fail if overall median-of-medians exceeds this",
    )
    return parser.parse_args()


def resolve_input_path(root: Path, mode: str, input_arg: str | None) -> Path:
    """Resolve input path using mode-aware defaults unless explicitly overridden."""
    if input_arg:
        return (root / input_arg).resolve()
    default_input = DEFAULT_INPUT_FULL if mode == "full" else DEFAULT_INPUT_QUICK_SMALL
    return (root / default_input).resolve()


def main() -> int:
    """Run selected benchmark mode and print summary."""
    args = parse_args()

    root = Path(__file__).resolve().parent.parent
    script = root / "bin" / "keybindings-sort.py"
    input_path = resolve_input_path(root, args.mode, args.input)

    if not script.exists():
        print(f"error: missing script: {script}", file=sys.stderr)
        return 2
    if not input_path.exists():
        print(f"error: missing input: {input_path}", file=sys.stderr)
        return 2

    combos = build_combos(args.mode)
    runs_per_combo = args.runs_per_combo if args.runs_per_combo is not None else default_runs_for_mode(args.mode)
    warmup_runs = args.warmup_runs if args.warmup_runs is not None else default_warmups_for_mode(args.mode)

    if runs_per_combo < 1:
        print("error: --runs-per-combo must be >= 1", file=sys.stderr)
        return 2
    if warmup_runs < 0:
        print("error: --warmup-runs must be >= 0", file=sys.stderr)
        return 2

    out_prefix = args.out_prefix
    if out_prefix is None:
        out_prefix = str(root / "tmp" / f"perf-keybindings-sort.{args.mode}")
    out_json = Path(f"{out_prefix}.json")
    out_csv = Path(f"{out_prefix}.csv")

    out_json.parent.mkdir(parents=True, exist_ok=True)

    input_data = input_path.read_bytes()
    results: list[dict[str, Any]] = []

    print(
        f"mode={args.mode} combos={len(combos)} runs_per_combo={runs_per_combo} warmup_runs={warmup_runs}",
        flush=True,
    )

    for idx, combo in enumerate(combos, 1):
        rec = run_case(
            python_exe=sys.executable,
            script=script,
            input_data=input_data,
            combo=combo,
            runs_per_combo=runs_per_combo,
            warmup_runs=warmup_runs,
        )
        results.append(rec)
        if idx % 10 == 0 or idx == len(combos):
            print(f"progress {idx}/{len(combos)}", flush=True)

    results_sorted = sorted(results, key=lambda item: item["median_ms"])
    overall_median_of_medians_ms = statistics.median(item["median_ms"] for item in results)

    summary = {
        "mode": args.mode,
        "input_file": str(input_path),
        "script": str(script),
        "combination_count": len(combos),
        "runs_per_combo": runs_per_combo,
        "warmup_runs": warmup_runs,
        "fastest": results_sorted[0],
        "slowest": results_sorted[-1],
        "overall_mean_of_medians_ms": statistics.fmean(item["median_ms"] for item in results),
        "overall_median_of_medians_ms": overall_median_of_medians_ms,
        "all_results": results,
    }

    write_outputs(summary, out_json, out_csv)

    print("done", flush=True)
    print(f"json={out_json}", flush=True)
    print(f"csv={out_csv}", flush=True)
    print(f"fastest_median_ms={summary['fastest']['median_ms']:.3f}", flush=True)
    print(f"slowest_median_ms={summary['slowest']['median_ms']:.3f}", flush=True)
    print(f"overall_median_of_medians_ms={overall_median_of_medians_ms:.3f}", flush=True)

    if args.max_overall_median_ms is not None and overall_median_of_medians_ms > args.max_overall_median_ms:
        print(
            "budget-exceeded "
            f"overall_median_of_medians_ms={overall_median_of_medians_ms:.3f} "
            f"threshold_ms={args.max_overall_median_ms:.3f}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
