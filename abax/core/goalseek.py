"""Goal Seek — find the input-cell value that drives a formula cell to a target.

The public entry point is :func:`goal_seek`. Given a *target* cell (typically a
formula), a desired numeric result, and a *changing* cell to vary, it searches
for the value of the changing cell that makes the target cell equal the goal.

It works by defining ``g(x)`` = "write ``x`` into the changing cell, recompute,
read the target cell, subtract the desired value" and handing ``g`` to
:func:`abax.core.science.numeric.solve_root` (a self-bracketing hybrid
secant/bisection solver). On success the changing cell is left holding the
solution; on failure it is restored to its original raw text so the sheet is
unchanged, and :class:`GoalSeekError` is raised.

Pure stdlib -> lives in ``core``.
"""

from __future__ import annotations

from .reference import parse_a1
from .science.numeric import NumericError, solve_root


class GoalSeekError(Exception):
    """Raised when Goal Seek cannot find a value satisfying the goal.

    Covers convergence failure, an un-bracketable target, and the case where the
    target cell never evaluates to a number. On failure the changing cell is
    restored to its original contents.
    """


def goal_seek(
    sheet,
    target_ref: str,
    target_value: float,
    changing_ref: str,
    lo: float = -1.0e6,
    hi: float = 1.0e6,
    tol: float = 1e-9,
) -> float:
    """Return the ``changing_ref`` value that makes ``target_ref`` == ``target_value``.

    ``target_ref`` and ``changing_ref`` are A1 strings (e.g. ``"B1"``, ``"A1"``).
    ``lo`` and ``hi`` seed the solver's search bracket. On success the changing
    cell is written with the found solution and the sheet is recomputed; the
    solution ``x`` is returned.

    :raises GoalSeekError: if the target never evaluates to a number, or the
        solver cannot bracket / converge on a solution. In that case the
        changing cell is restored to its original raw text.
    """
    tr, tc = parse_a1(target_ref)
    cr, cc = parse_a1(changing_ref)
    target_value = float(target_value)

    original = sheet.get_raw(cr, cc)

    def g(x: float) -> float:
        sheet.set_cell(cr, cc, repr(float(x)))
        value = sheet.get_value(tr, tc)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise GoalSeekError(
                f"target cell {target_ref} is not numeric (got {value!r})"
            )
        return float(value) - target_value

    try:
        root, _residual = solve_root(g, float(lo), float(hi), tol=tol)
    except (NumericError, GoalSeekError) as exc:
        sheet.set_cell(cr, cc, original)  # restore -> sheet unchanged on failure
        raise GoalSeekError(f"goal seek failed: {exc}") from exc

    # Keep the solution in the changing cell and recompute dependents.
    sheet.set_cell(cr, cc, repr(root))
    return root
