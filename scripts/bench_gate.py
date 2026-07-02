#!/usr/bin/env python3
"""Benchmark regression gate for the abax core recalc engine.

Measures the headline recalc metrics with the same synthetic workload the
profiler (``benchmarks/profile_abax.py``) uses, compares them to a committed
baseline (``scripts/bench_baseline.json``), and exits non-zero only if a metric
regresses beyond a lenient threshold. Prints a clear before/after table.

The "metric" here is *throughput* (cells/sec) for two phases:

* ``cold`` — first recalc: parse + eval for every formula (no AST cache warm).
* ``warm`` — second recalc: eval only (AST cache populated). This isolates the
  hot path a user hits on every edit-driven recalc.

A regression = throughput dropped below ``baseline * (1 - threshold)``. The
default threshold is lenient (30%) so ordinary run-to-run timing noise and
slower CI runners don't fail the build — the gate exists to catch a *real*
algorithmic regression, not to police jitter.

Usage::

    py scripts/bench_gate.py                 # measure + compare to baseline
    py scripts/bench_gate.py --update-baseline   # (re)capture this machine's numbers
    py scripts/bench_gate.py --threshold 0.4     # allow a 40% slowdown
    py scripts/bench_gate.py --repeat 7          # more timing samples (median wins)
    py scripts/bench_gate.py --json              # machine-readable result on stdout

Pure stdlib; touches only ``abax.core`` (via the profiler's workload builder).
No optional abax deps required — safe to run on a lean CI matrix runner.
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import sys
import time
from pathlib import Path

# Make ``abax`` and the ``benchmarks`` package importable from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_BENCH_DIR = _REPO_ROOT / "benchmarks"
for _p in (_REPO_ROOT, _BENCH_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Reuse the exact recalc workload the profiler builds, so the gate and the
# profiler never drift apart.
from profile_abax import build_recalc_workbook  # noqa: E402

BASELINE_PATH = Path(__file__).resolve().parent / "bench_baseline.json"

# Workload size: matches the profiler's defaults (200 x 50 = 10k cells). Fixed
# here so the baseline is comparable run-to-run and machine-to-machine (up to a
# constant CPU factor absorbed by the lenient threshold).
DEFAULT_ROWS = 200
DEFAULT_COLS = 50
DEFAULT_THRESHOLD = 0.30  # allow up to a 30% throughput drop before failing
DEFAULT_REPEAT = 5


def measure(rows: int, cols: int, repeat: int) -> dict:
    """Measure cold and warm recalc throughput (cells/sec), median of ``repeat``.

    Each sample rebuilds the workbook fresh so the "cold" phase is genuinely
    cold (empty value + AST caches). Median over several samples damps the
    occasional GC/scheduler hiccup without hiding a real regression.
    """
    cold_rates: list[float] = []
    warm_rates: list[float] = []
    n_cells = 0

    for _ in range(repeat):
        wb = build_recalc_workbook(rows, cols)
        sh = wb.sheet
        n_cells = sum(1 for _ in sh.iter_cells())

        gc.collect()
        t0 = time.perf_counter()
        wb.recalculate()
        cold = time.perf_counter() - t0

        t0 = time.perf_counter()
        wb.recalculate()
        warm = time.perf_counter() - t0

        cold_rates.append(n_cells / cold if cold > 0 else float("inf"))
        warm_rates.append(n_cells / warm if warm > 0 else float("inf"))

    cold_rates.sort()
    warm_rates.sort()
    mid = repeat // 2
    return {
        "rows": rows,
        "cols": cols,
        "cells": n_cells,
        "repeat": repeat,
        "cold_cells_per_sec": cold_rates[mid],
        "warm_cells_per_sec": warm_rates[mid],
    }


def _machine() -> dict:
    """A small provenance stamp so a baseline records where it was captured."""
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "captured": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def write_baseline(result: dict, path: Path = BASELINE_PATH) -> None:
    payload = {
        "schema": 1,
        "metrics": {
            "cold_cells_per_sec": result["cold_cells_per_sec"],
            "warm_cells_per_sec": result["warm_cells_per_sec"],
        },
        "workload": {
            "rows": result["rows"],
            "cols": result["cols"],
            "cells": result["cells"],
        },
        "machine": _machine(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_baseline(path: Path = BASELINE_PATH) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# Metrics the gate checks. name -> (result key, baseline key, label).
_METRICS = [
    ("cold recalc (parse+eval)", "cold_cells_per_sec"),
    ("warm recalc (eval only)", "warm_cells_per_sec"),
]


def _fmt(n: float) -> str:
    return f"{n:,.0f}"


def compare_and_report(result: dict, baseline: dict, threshold: float) -> bool:
    """Print a before/after table; return True if all metrics pass the gate."""
    base_metrics = baseline.get("metrics", {})
    base_machine = baseline.get("machine", {})

    print("=" * 74)
    print("abax benchmark regression gate")
    print("=" * 74)
    print(
        f"workload : {result['rows']} x {result['cols']} = "
        f"{result['cells']:,} cells   (median of {result['repeat']} runs)"
    )
    print(f"threshold: {threshold * 100:.0f}% throughput drop tolerated")
    print(
        f"baseline : {base_machine.get('python', '?')} on "
        f"{base_machine.get('platform', '?')}  "
        f"(captured {base_machine.get('captured', '?')})"
    )
    print(f"current  : {platform.python_version()} on {platform.platform()}")
    print()
    header = f"{'metric':<28}{'baseline':>16}{'current':>16}{'change':>10}  status"
    print(header)
    print("-" * len(header))

    all_ok = True
    for label, key in _METRICS:
        cur = result[key]
        base = base_metrics.get(key)
        if base is None:
            print(f"{label:<28}{'n/a':>16}{_fmt(cur):>16}{'--':>10}  (new)")
            continue
        # Throughput ratio: <1 means we got slower. delta_pct is signed
        # (positive = faster, negative = slower).
        ratio = cur / base if base > 0 else float("inf")
        delta_pct = (ratio - 1.0) * 100.0
        floor = base * (1.0 - threshold)
        ok = cur >= floor
        all_ok = all_ok and ok
        status = "OK" if ok else "REGRESSED"
        sign = "+" if delta_pct >= 0 else ""
        print(
            f"{label:<28}{_fmt(base):>16}{_fmt(cur):>16}"
            f"{sign}{delta_pct:>8.1f}%  {status}"
        )
        if not ok:
            print(
                f"    -> below floor {_fmt(floor)} cells/sec "
                f"(baseline {_fmt(base)} - {threshold * 100:.0f}%)"
            )

    print("-" * len(header))
    print("RESULT:", "PASS" if all_ok else "FAIL (a metric regressed)")
    return all_ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="recalc sheet rows")
    ap.add_argument("--cols", type=int, default=DEFAULT_COLS, help="recalc sheet cols")
    ap.add_argument(
        "--repeat", type=int, default=DEFAULT_REPEAT,
        help="timing samples per metric (median wins)",
    )
    ap.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help="max tolerated throughput drop as a fraction (0.30 = 30%%)",
    )
    ap.add_argument(
        "--update-baseline", action="store_true",
        help="measure and (over)write scripts/bench_baseline.json, then exit 0",
    )
    ap.add_argument(
        "--json", action="store_true",
        help="also print the measured result as JSON on stdout",
    )
    args = ap.parse_args(argv)

    result = measure(args.rows, args.cols, args.repeat)

    if args.update_baseline:
        write_baseline(result)
        print(f"Wrote baseline -> {BASELINE_PATH}")
        print(
            f"  cold {_fmt(result['cold_cells_per_sec'])} cells/sec, "
            f"warm {_fmt(result['warm_cells_per_sec'])} cells/sec"
        )
        if args.json:
            print(json.dumps(result, indent=2))
        return 0

    baseline = load_baseline()
    if baseline is None:
        print(
            f"No baseline at {BASELINE_PATH}. Run "
            f"`py scripts/bench_gate.py --update-baseline` to capture one.",
            file=sys.stderr,
        )
        return 2

    ok = compare_and_report(result, baseline, args.threshold)
    if args.json:
        print(json.dumps(result, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
