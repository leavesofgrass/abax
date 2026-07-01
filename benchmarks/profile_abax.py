#!/usr/bin/env python3
"""Reusable performance benchmark + profiler for the abax core engine.

Pure stdlib (cProfile / pstats / time / tracemalloc). Builds synthetic
workloads, measures throughput, and prints the top cumulative-time functions
under cProfile so we can ground any decision about native acceleration
(ctypes / Cython / C extensions).

Run::

    py -3.13 benchmarks/profile_abax.py
    py -3.13 benchmarks/profile_abax.py --rows 400 --cols 80   # bigger recalc
    py -3.13 benchmarks/profile_abax.py --csv-rows 100000      # bigger CSV
    py -3.13 benchmarks/profile_abax.py --only recalc          # one workload
    py -3.13 benchmarks/profile_abax.py --top 20               # deeper hot list

Self-contained: generates its own data in a tempdir and cleans up. No
third-party deps, no optional abax deps (touches only ``abax.core``).
"""

from __future__ import annotations

import argparse
import cProfile
import gc
import io
import pstats
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

# Make ``abax`` importable when run from the repo root or from benchmarks/.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from abax.core.io import csv_io  # noqa: E402
from abax.core.parser import parse  # noqa: E402
from abax.core.tokenizer import tokenize  # noqa: E402
from abax.core.evaluator import evaluate  # noqa: E402
from abax.core.workbook import Workbook  # noqa: E402
from abax.core.reference import to_a1  # noqa: E402


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _fmt(n: float) -> str:
    """Human-friendly thousands separators for throughput numbers."""
    return f"{n:,.0f}"


def _profile_top(fn, top: int) -> str:
    """Run ``fn`` under cProfile, return the top-``top`` cumulative-time table."""
    pr = cProfile.Profile()
    pr.enable()
    fn()
    pr.disable()
    buf = io.StringIO()
    st = pstats.Stats(pr, stream=buf)
    st.strip_dirs().sort_stats("cumulative").print_stats(top)
    return buf.getvalue()


def _hot_lines(profile_text: str, top: int) -> list[str]:
    """Extract just the ranked function rows from a pstats dump."""
    lines = profile_text.splitlines()
    out: list[str] = []
    started = False
    for ln in lines:
        s = ln.strip()
        if s.startswith("ncalls"):
            started = True
            out.append(ln)
            continue
        if started and s:
            out.append(ln)
        if started and len(out) > top + 1:
            break
    return out


def _section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


# --------------------------------------------------------------------------
# workload builders
# --------------------------------------------------------------------------

def build_recalc_workbook(rows: int, cols: int) -> Workbook:
    """An rows x cols sheet wired so most cells depend on neighbors.

    Column A: incrementing literals (seed data).
    Columns B..: a rotating mix of dependent formulas:
        =A{r}+B{r-ish}  neighbor arithmetic
        =SUM(A1:A{r})   growing aggregate over a range
        =IF(A{r}>0, ..) lazy branch
        =A{r}*C{r}-...  multi-ref arithmetic
    This produces a realistic dependency graph (chains + ranges) rather than
    a trivially-parallel grid.
    """
    wb = Workbook()
    sh = wb.sheet
    # Seed column A with literals.
    for r in range(rows):
        sh.set_cell(r, 0, str((r % 97) + 1))
    # Fill the rest with formulas referencing neighbors / ranges.
    for r in range(rows):
        a1 = to_a1(r, 0)
        prev = to_a1(max(r - 1, 0), 0)
        for c in range(1, cols):
            here_left = to_a1(r, c - 1)
            kind = (r + c) % 5
            if kind == 0:
                raw = f"={a1}+{here_left}"
            elif kind == 1:
                top = to_a1(0, 0)
                raw = f"=SUM({top}:{a1})"
            elif kind == 2:
                raw = f"=IF({a1}>50,{here_left}*2,{here_left}+1)"
            elif kind == 3:
                raw = f"={a1}*2-{prev}"
            else:
                raw = f"=ROUND({here_left}/3,2)+{a1}"
            sh.set_cell(r, c, raw)
    return wb


def _gen_csv(path: Path, rows: int, cols: int) -> int:
    """Write a rows x cols CSV of mixed literals; return byte size."""
    import csv as _csv

    with path.open("w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        header = [f"col{c}" for c in range(cols)]
        w.writerow(header)
        for r in range(rows):
            row = []
            for c in range(cols):
                if c % 3 == 0:
                    row.append(str(r * cols + c))
                elif c % 3 == 1:
                    row.append(f"{(r + c) * 0.5:.3f}")
                else:
                    row.append(f"text_{r}_{c}")
            w.writerow(row)
    return path.stat().st_size


# --------------------------------------------------------------------------
# benchmark 1: recalc throughput
# --------------------------------------------------------------------------

def bench_recalc(rows: int, cols: int, top: int) -> None:
    _section(f"1) RECALC THROUGHPUT  ({rows} x {cols} = {rows * cols:,} cells)")
    wb = build_recalc_workbook(rows, cols)
    sh = wb.sheet
    n_cells = sum(1 for _ in sh.iter_cells())

    gc.collect()
    # Cold recalc: caches empty, AST parsed for each formula on first eval.
    t0 = time.perf_counter()
    wb.recalculate()
    cold = time.perf_counter() - t0

    # Warm recalc: recalculate() clears the value cache but AST cache survives,
    # so this isolates eval cost from parse cost.
    t0 = time.perf_counter()
    wb.recalculate()
    warm = time.perf_counter() - t0

    print(f"populated cells     : {n_cells:,}")
    print(f"cold recalc (parse+eval): {cold * 1000:9.2f} ms"
          f"   -> {_fmt(n_cells / cold)} cells/sec")
    print(f"warm recalc (eval only) : {warm * 1000:9.2f} ms"
          f"   -> {_fmt(n_cells / warm)} cells/sec")
    print(f"parse share of cold     : {max(cold - warm, 0) / cold * 100:5.1f}%"
          f"  (cold - warm)")

    print("\n-- cProfile (warm recalc, top cumulative) --")
    txt = _profile_top(lambda: wb.recalculate(), top)
    for ln in _hot_lines(txt, top):
        print(ln)


# --------------------------------------------------------------------------
# benchmark 2: formula engine throughput (tokenize / parse / eval split)
# --------------------------------------------------------------------------

def bench_engine(iters: int, top: int) -> None:
    _section(f"2) FORMULA ENGINE THROUGHPUT  ({iters:,} iterations)")

    # A representative formula: refs, a range aggregate, arithmetic, a lazy IF,
    # nested function, comparison + concat.
    formula = "IF(A1>SUM(B1:B10),ROUND(A1*C3/2,2)+MAX(D1:D5),A1&\"-lo\")"

    # Build a small backing grid so the resolver returns real numbers.
    wb = Workbook()
    sh = wb.sheet
    for r in range(12):
        for c in range(5):
            sh.set_cell(r, c, str((r * 5 + c) % 17 + 1))
    wb.recalculate()
    resolver = sh._resolve  # (sheet_name, row, col) -> value

    ast = parse(formula)

    # --- timed phases ---
    gc.collect()
    t0 = time.perf_counter()
    for _ in range(iters):
        tokenize(formula)
    t_tok = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(iters):
        parse(formula)            # includes its own tokenize call
    t_parse = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(iters):
        evaluate(ast, resolver)   # pre-parsed AST, eval only
    t_eval = time.perf_counter() - t0

    # Full pipeline (parse fresh + eval) — the "no AST cache" cost.
    t0 = time.perf_counter()
    for _ in range(iters):
        evaluate(parse(formula), resolver)
    t_full = time.perf_counter() - t0

    print(f"formula: {formula}")
    print(f"tokenize only        : {t_tok * 1e9 / iters:9.0f} ns/op"
          f"   -> {_fmt(iters / t_tok)} ops/sec")
    print(f"parse  (tok+parse)   : {t_parse * 1e9 / iters:9.0f} ns/op"
          f"   -> {_fmt(iters / t_parse)} ops/sec")
    print(f"  parse-only (minus tok): {max(t_parse - t_tok, 0) * 1e9 / iters:9.0f} ns/op")
    print(f"eval   (cached AST)  : {t_eval * 1e9 / iters:9.0f} ns/op"
          f"   -> {_fmt(iters / t_eval)} ops/sec")
    print(f"full   (parse+eval)  : {t_full * 1e9 / iters:9.0f} ns/op"
          f"   -> {_fmt(iters / t_full)} ops/sec")
    tot = t_tok + max(t_parse - t_tok, 0) + t_eval
    print(f"\ntime split (tokenize / parse-only / eval):"
          f" {t_tok / tot * 100:4.1f}% / "
          f"{max(t_parse - t_tok, 0) / tot * 100:4.1f}% / "
          f"{t_eval / tot * 100:4.1f}%")

    print("\n-- cProfile (full parse+eval pipeline, top cumulative) --")

    def _run() -> None:
        for _ in range(iters):
            evaluate(parse(formula), resolver)

    txt = _profile_top(_run, top)
    for ln in _hot_lines(txt, top):
        print(ln)


# --------------------------------------------------------------------------
# benchmark 3: CSV load throughput + peak memory
# --------------------------------------------------------------------------

def bench_csv(rows: int, cols: int, top: int, tmp: Path) -> None:
    _section(f"3) CSV LOAD  ({rows:,} rows x {cols} cols)")
    path = tmp / "bench.csv"
    size = _gen_csv(path, rows, cols)
    print(f"file: {path.name}  ({size / 1e6:.1f} MB on disk)")

    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    sheet = csv_io.load_csv(path)
    dt = time.perf_counter() - t0
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    n_cells = sum(1 for _ in sheet.iter_cells())
    print(f"load_csv             : {dt * 1000:9.2f} ms"
          f"   -> {_fmt(rows / dt)} rows/sec, {_fmt(n_cells / dt)} cells/sec")
    print(f"populated cells      : {n_cells:,}")
    print(f"peak python heap     : {peak / 1e6:.1f} MB"
          f"   ({peak / max(n_cells, 1):.0f} bytes/cell)")

    print("\n-- cProfile (load_csv, top cumulative) --")
    txt = _profile_top(lambda: csv_io.load_csv(path), top)
    for ln in _hot_lines(txt, top):
        print(ln)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", type=int, default=200, help="recalc sheet rows")
    ap.add_argument("--cols", type=int, default=50, help="recalc sheet cols")
    ap.add_argument("--engine-iters", type=int, default=20000,
                    help="formula-engine iterations")
    ap.add_argument("--csv-rows", type=int, default=50000, help="CSV rows")
    ap.add_argument("--csv-cols", type=int, default=12, help="CSV cols")
    ap.add_argument("--top", type=int, default=15, help="hot functions to show")
    ap.add_argument("--only", choices=["recalc", "engine", "csv"],
                    help="run only one workload")
    args = ap.parse_args(argv)

    print(f"abax perf profile  |  python {sys.version.split()[0]}  "
          f"|  {time.strftime('%Y-%m-%d %H:%M:%S')}")

    with tempfile.TemporaryDirectory(prefix="abax_bench_") as td:
        tmp = Path(td)
        if args.only in (None, "recalc"):
            bench_recalc(args.rows, args.cols, args.top)
        if args.only in (None, "engine"):
            bench_engine(args.engine_iters, args.top)
        if args.only in (None, "csv"):
            bench_csv(args.csv_rows, args.csv_cols, args.top, tmp)

    print("\nDone. (synthetic data generated in a tempdir, now cleaned up)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
