"""Optional numpy accelerator for large all-numeric range aggregates.

The middle-layer (engine) counterpart to the stdlib aggregate fast-path in
:mod:`abax.core.functions`. When numpy is present and an entire range coerces to
a finite float array -- i.e. every cell is a plain number, with no errors, text,
blanks or NaNs -- it reduces the column-major block with numpy's vectorized
kernels (3-4x faster than the Python loop on 100k+ cells). Anything else returns
``(False, None)`` so the caller falls back to the exact stdlib semantics (which
skip text/blanks and propagate the first error).

Registered into :data:`abax._runtime` by :func:`register`, called from
``abax.engine`` import. Correctness is guaranteed by construction: the numpy path
only runs when the block is wholly finite-numeric, where SUM / MEAN / MIN / MAX /
PRODUCT / SUMSQ / COUNT are identical to the stdlib reduction. The same
finite-numeric gate widens to more shapes -- a *sequence* of ranges (multi-
range SUM/AVERAGE/MIN/MAX/COUNT/PRODUCT, the argument list Excel treats as one
concatenated pool), equal-shaped operand ranges for SUMPRODUCT, and the criteria
family (COUNTIFS / SUMIFS / AVERAGEIFS) whenever every criteria/value range is
finite-numeric and every criterion is a numeric comparison -- so those too
vectorize when every block is clean and fall back to the exact stdlib loop
otherwise (text and wildcard criteria always fall back).
"""

from __future__ import annotations

try:
    import numpy as _np
except Exception:                       # numpy is optional
    _np = None


def _finite_array(grid):
    """Coerce a RangeValue ``grid`` to a finite float array, or ``None``.

    Returns the numpy array only when every cell is a plain finite number (so
    ``dtype=float`` coercion succeeds and no cell is a blank->NaN, genuine NaN or
    inf). Text / error objects raise on coercion; ``None`` becomes NaN. In every
    such case we return ``None`` so the caller bails to the exact stdlib loop.
    Booleans coerce to 1.0/0.0, matching the stdlib ``_numbers`` rules."""
    if _np is None:
        return None
    try:
        a = _np.asarray(grid, dtype=float)
    except (ValueError, TypeError):
        return None                     # text / error objects -> stdlib handles it
    if a.size == 0:
        return None
    if not _np.isfinite(a).all():
        return None                     # None->NaN or genuine NaN/inf -> stdlib
    return a


def _reduce_array(a, op: str):
    """Apply a named reduction to a validated finite float array."""
    if op == "sum":
        return True, float(_np.sum(a))
    if op == "mean":
        return True, float(_np.mean(a))
    if op == "min":
        return True, float(_np.min(a))
    if op == "max":
        return True, float(_np.max(a))
    if op == "product":
        return True, float(_np.prod(a))
    if op == "sumsq":
        return True, float(_np.sum(a * a))
    if op == "count":
        return True, float(a.size)
    return False, None


def reduce_range(rangevalue, op: str):
    """Reduce a single :class:`abax.core.values.RangeValue` with numpy.

    Returns ``(handled, value)``. ``handled`` is ``True`` only when numpy is
    available and the whole block is finite-numeric; otherwise ``(False, None)``.
    """
    a = _finite_array(rangevalue.grid)
    if a is None:
        return False, None
    return _reduce_array(a, op)


def reduce_ranges(rangevalues, op: str):
    """Reduce a *sequence* of ranges as one concatenated numeric pool.

    Excel aggregates ``SUM(A1:A9, C1:C9)`` over the union of the argument cells,
    so the numpy path flattens every block into one 1-D array and reduces that --
    matching ``sum``/``mean``/``min``/``max``/``product``/``count`` over the
    stdlib ``_numbers_checked`` list, whose order is block-then-block, row-major.
    ``handled`` is ``True`` only when numpy is available and *every* block is
    finite-numeric; a single dirty block bails the whole call to stdlib so the
    text/blank/error semantics are never bypassed."""
    if _np is None:
        return False, None
    parts = []
    for rv in rangevalues:
        a = _finite_array(rv.grid)
        if a is None:
            return False, None          # any dirty block -> stdlib for the lot
        parts.append(a.reshape(-1))
    if not parts:
        return False, None
    pooled = parts[0] if len(parts) == 1 else _np.concatenate(parts)
    return _reduce_array(pooled, op)


def sumproduct(rangevalues):
    """Vectorized SUMPRODUCT of equal-shaped finite-numeric ranges.

    Returns ``(handled, value)``. Mirrors the stdlib ``_sumproduct``: multiply the
    operand ranges position-wise (row-major flatten) and sum. ``handled`` is
    ``True`` only when numpy is present, there is at least one range, all ranges
    share one flat length, and every block is finite-numeric -- otherwise the
    stdlib path (which coerces stray text/blanks to 0.0 and range-shape mismatch
    to ``#VALUE!``) must run instead, so we bail."""
    if _np is None or not rangevalues:
        return False, None
    arrays = []
    length = None
    for rv in rangevalues:
        a = _finite_array(rv.grid)
        if a is None:
            return False, None
        flat = a.reshape(-1)
        if length is None:
            length = flat.size
        elif flat.size != length:
            return False, None          # shape mismatch -> stdlib (#VALUE!)
        arrays.append(flat)
    prod = arrays[0]
    for a in arrays[1:]:
        prod = prod * a
    return True, float(_np.sum(prod))


# ---------------------------------------------------------------------------
# Criteria family: SUMIF(S) / COUNTIF(S) / AVERAGEIF(S)
# ---------------------------------------------------------------------------
#
# The conditional aggregates loop in pure Python (abax.core.stats_dist and the
# single-criterion versions in abax.core.functions.builtins). When every
# criteria range is finite-numeric AND every criterion is a NUMERIC comparison
# (=, <>, <, >, <=, >= against a number -- reported by
# ``abax.core.criteria.numeric_criterion``), the whole predicate reduces to a
# numpy boolean mask, and the sum/average/count reduces over that mask. Text
# criteria, wildcards (``*``/``?``), and any block with text/blank/error make a
# block non-coercible or a criterion non-numeric, and the caller bails to the
# exact stdlib loop -- so semantics never change, this is pure speed.


def _criteria_mask(crit_grids, ops_thresholds):
    """Build the AND-ed boolean mask for numeric ``*IFS`` criteria, or ``None``.

    ``crit_grids`` is a sequence of RangeValue grids (one per criterion) and
    ``ops_thresholds`` the matching ``(op, threshold)`` pairs from
    :func:`abax.core.criteria.numeric_criterion`. Returns a 1-D bool array over
    the shared flat length when every block is finite-numeric and equal-length --
    the same length/mismatch rule as the stdlib ``_qualifying_indices`` -- and
    ``None`` otherwise so the caller runs the exact stdlib predicate loop. The
    per-cell test ``cmp(block, threshold)`` mirrors ``make_predicate``'s numeric
    branch on a non-string numeric cell, so the mask is bit-for-bit the stdlib
    membership set."""
    if _np is None:
        return None
    mask = None
    length = None
    for grid, (op, thr) in zip(crit_grids, ops_thresholds):
        a = _finite_array(grid)
        if a is None:
            return None                 # text/blank/error block -> stdlib loop
        flat = a.reshape(-1)
        if length is None:
            length = flat.size
        elif flat.size != length:
            return None                 # ragged criteria ranges -> stdlib (#VALUE!)
        if op == "=":
            m = flat == thr
        elif op == "<>":
            m = flat != thr
        elif op == "<":
            m = flat < thr
        elif op == ">":
            m = flat > thr
        elif op == "<=":
            m = flat <= thr
        elif op == ">=":
            m = flat >= thr
        else:
            return None
        mask = m if mask is None else (mask & m)
    if mask is None:
        return None                     # no criteria at all -> stdlib
    return mask


def countifs(crit_grids, ops_thresholds):
    """Vectorised COUNTIFS: count of cells where every numeric criterion holds.

    Returns ``(handled, value)``. ``handled`` is ``True`` only when numpy is
    present and :func:`_criteria_mask` succeeds (all blocks finite-numeric,
    equal-length); otherwise ``(False, None)`` and the stdlib loop runs."""
    mask = _criteria_mask(crit_grids, ops_thresholds)
    if mask is None:
        return False, None
    return True, float(int(mask.sum()))


def sumifs(value_grid, crit_grids, ops_thresholds):
    """Vectorised SUMIFS: sum of ``value_grid`` where every criterion holds.

    The value block must itself be finite-numeric (so every masked cell adds
    ``float(v)`` exactly as the stdlib loop does -- text/blank cells there add
    nothing, which only a clean block reproduces). Returns ``(handled, value)``;
    bails to ``(False, None)`` if numpy is absent, the mask can't be built, or the
    value block isn't finite-numeric or is a different length than the mask."""
    mask = _criteria_mask(crit_grids, ops_thresholds)
    if mask is None:
        return False, None
    vals = _finite_array(value_grid)
    if vals is None:
        return False, None
    flat = vals.reshape(-1)
    if flat.size != mask.size:
        return False, None              # sum_range shape differs -> stdlib
    return True, float(_np.sum(flat[mask]))


def averageifs(value_grid, crit_grids, ops_thresholds):
    """Vectorised AVERAGEIFS: mean of ``value_grid`` where every criterion holds.

    Returns ``(handled, value)``. ``value`` is ``None`` with ``handled=True`` only
    when the mask matched *zero* numeric cells -- the caller maps that to the
    stdlib ``#DIV/0!``. Same finite-numeric / equal-length gate as
    :func:`sumifs`; anything dirty bails to ``(False, None)``."""
    mask = _criteria_mask(crit_grids, ops_thresholds)
    if mask is None:
        return False, None
    vals = _finite_array(value_grid)
    if vals is None:
        return False, None
    flat = vals.reshape(-1)
    if flat.size != mask.size:
        return False, None
    picked = flat[mask]
    if picked.size == 0:
        return True, None               # -> caller returns #DIV/0!
    return True, float(_np.sum(picked) / picked.size)


def register() -> None:
    """Install the numpy reducers as the core aggregate accelerator.

    ``abax._runtime`` exposes a single accelerator slot, so the widened kernels
    ride along as attributes of the registered ``reduce_range`` callable: core
    reads ``accel.multi`` / ``accel.sumproduct`` / ``accel.countifs`` /
    ``accel.sumifs`` / ``accel.averageifs`` off whatever object it fetched through
    the seam, keeping ``_runtime`` unchanged and the whole surface behind one
    on/off toggle (clearing the slot disables every path at once)."""
    from .._runtime import set_aggregate_accelerator

    reduce_range.multi = reduce_ranges
    reduce_range.sumproduct = sumproduct
    reduce_range.countifs = countifs
    reduce_range.sumifs = sumifs
    reduce_range.averageifs = averageifs
    set_aggregate_accelerator(reduce_range)
