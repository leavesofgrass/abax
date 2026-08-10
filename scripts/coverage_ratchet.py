#!/usr/bin/env python3
"""Coverage ratchet gate — fails when coverage drops **and when it drifts up**.

``coverage report --fail-under=N`` is a floor: it fails when coverage falls
below ``N`` and is silent forever after. That is not a ratchet, and the
difference is not academic. Both abax gates had been called ratchets since they
were created and neither had ever moved:

===============  ==========================  ========  =======
package          floor in ``ci.yml``         measured  drift
===============  ==========================  ========  =======
``abax/core``    81, set 2026-07-02          84%       3 points
``abax/engine``  57, moved once in 6 cycles  63%       6 points
===============  ==========================  ========  =======

A gate six points below reality permits a six-point regression while still
reporting success. Intent was never going to close that — the *mechanism* has to.

So this gate fails in both directions:

* **below the floor** — a real regression, same as ``--fail-under``.
* **further above the floor than ``--slack``** — the floor is stale. The build
  goes red and names the number to write, which is what makes the ratchet turn.

The second case fails a build that did nothing wrong, and that is deliberate:
raising the floor is a one-line edit, and the only alternatives are a bot with
write access to ``main`` (rejected — it fights tag pushes) or trusting that
someone will remember, which is exactly what produced the table above.

Slack exists so ordinary movement doesn't nag. Coverage wobbles by fractions
when an optional dependency changes which adapters import, so a floor sitting
1-2 points under measured is healthy; 3+ means real work landed and was never
banked.

Usage::

    py scripts/coverage_ratchet.py --include "abax/core/*" --floor 83
    py scripts/coverage_ratchet.py --include "abax/engine/*" --floor 62 --slack 4
    py scripts/coverage_ratchet.py --include "abax/core/*" --floor 83 --report

Reads the coverage data file the preceding ``pytest --cov`` run wrote; it does
not measure anything itself. Pure stdlib plus ``coverage`` itself.
"""

from __future__ import annotations

import argparse
import io
import sys

DEFAULT_SLACK = 3.0

# Exit codes, distinct so CI logs say which direction failed.
EXIT_OK = 0
EXIT_REGRESSED = 1
EXIT_STALE = 2


def _coverage(data_file: str | None):
    """A loaded ``Coverage`` for the data the preceding ``pytest --cov`` wrote.

    ``data_file`` is omitted rather than passed as ``None`` when unset: in
    coverage's API ``None`` is a meaningful value meaning *suppress the data
    file entirely*, not *use the default*. Passing it through raises
    ``NoDataError`` on a repo with perfectly good coverage data.
    """
    import coverage

    cov = (coverage.Coverage(data_file=data_file) if data_file
           else coverage.Coverage())
    cov.load()
    return cov


def measured_percent(include: str, data_file: str | None = None) -> float:
    """Total covered percent for files matching *include*, from existing data.

    Uses coverage's own API rather than parsing ``coverage report`` output, so
    the number here is the number that command prints — no format drift, and no
    dependence on ``--format=total`` being available.
    """
    # report() returns the total percent and writes the table; send the table
    # to a sink because the neighbouring `coverage report` step already prints
    # one and two copies in a CI log is noise.
    return _coverage(data_file).report(include=[include], file=io.StringIO())


def suggested_floor(measured: float) -> int:
    """The floor to write for *measured*: rounded DOWN, per house convention.

    Rounding down is what keeps a sub-point buffer under the measured value,
    the same rule the original floors used ("81.49 measured -> 81").
    """
    return int(measured)


def check(measured: float, floor: float, slack: float) -> tuple[int, str]:
    """Decide the gate. Returns ``(exit_code, message)``.

    Pure — no coverage data, no filesystem, no argv. That is the point: the
    branch that fires on drift is the one that has never fired in production,
    so it needs to be reachable from a test without staging a whole coverage
    run. A gate whose failure path cannot be exercised is not a gate.
    """
    if measured < floor:
        return EXIT_REGRESSED, (
            f"REGRESSED: {measured:.2f}% is below the floor of {floor:g}%.\n"
            f"    Coverage dropped. Add tests for what you changed, or say "
            f"explicitly why the floor should come down."
        )
    drift = measured - floor
    if drift > slack:
        new_floor = suggested_floor(measured)
        return EXIT_STALE, (
            f"STALE RATCHET: {measured:.2f}% is {drift:.2f} points above the "
            f"floor of {floor:g}% (slack {slack:g}).\n"
            f"    Coverage improved and was never banked, so the gate now "
            f"permits a {drift:.2f}-point regression.\n"
            f"    Turn the ratchet: raise the floor to {new_floor} in "
            f".github/workflows/ci.yml."
        )
    return EXIT_OK, (
        f"OK: {measured:.2f}%, floor {floor:g}%, drift {drift:.2f} "
        f"(slack {slack:g})."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--include", required=True,
        help='file pattern to measure, e.g. "abax/core/*"',
    )
    ap.add_argument(
        "--floor", type=float, required=True,
        help="minimum acceptable percent (the ratchet's current position)",
    )
    ap.add_argument(
        "--slack", type=float, default=DEFAULT_SLACK,
        help=f"points above the floor tolerated before the gate demands a bump "
             f"(default {DEFAULT_SLACK:g})",
    )
    ap.add_argument(
        "--data-file", default=None,
        help="coverage data file (default: coverage's own resolution)",
    )
    ap.add_argument(
        "--report", action="store_true",
        help="print the per-file coverage table before the verdict",
    )
    args = ap.parse_args(argv)

    try:
        measured = measured_percent(args.include, args.data_file)
    except Exception as exc:                      # no data file, bad pattern, ...
        print(f"coverage ratchet: could not read coverage data: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REGRESSED

    if args.report:
        _coverage(args.data_file).report(include=[args.include])

    code, message = check(measured, args.floor, args.slack)
    stream = sys.stdout if code == EXIT_OK else sys.stderr
    print(f"[{args.include}] {message}", file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
