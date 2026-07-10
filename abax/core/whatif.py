"""What-if analysis — Data Tables and Scenarios.

Two classic spreadsheet what-if tools, both driving the real recalculation
engine (so numbers stay numbers and cross-sheet dependents update):

* **Data tables** substitute a series of trial values into one or two *input*
  cells and record what a *formula* cell evaluates to for each combination.
  :func:`one_var_data_table` sweeps a single input; :func:`two_var_data_table`
  builds the classic grid over two inputs. Both **always restore** the input
  cells to their original raw contents (``try``/``finally``) and recompute, so
  the sheet is left exactly as it was found — even if a trial value makes the
  formula error out mid-run.

* **Scenarios** are named bundles of cell overrides (``A1`` -> value text).
  :class:`Scenario` holds one bundle; :class:`ScenarioSet` is a persistable,
  non-secret registry of them (the same add/get/remove/names/version/
  to_dict/from_dict shape as :class:`abax.core.names.NameRegistry`, so it can be
  attached to a :class:`~abax.core.workbook.Workbook` and round-tripped through
  the JSON envelope). :func:`apply` writes a scenario's cells and returns the
  *prior* values so the change can be undone; :func:`capture` snapshots the
  current values of a set of cells into a new :class:`Scenario`.

Pure stdlib -> lives in ``core``. Input/formula cells are addressed by A1
strings (``"A1"``, ``"$B$2"``); ranges are expanded by :mod:`abax.core.reference`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .reference import iter_range, parse_a1, to_a1


def _value_to_text(value) -> str:
    """Convert a trial/override *value* to the raw text stored in a cell.

    Numbers are emitted with :func:`repr` so they round-trip losslessly and the
    engine reads them back as numbers; booleans become ``TRUE``/``FALSE``;
    anything else is stringified as-is (a caller may already pass cell text).
    """
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return str(value)


def _recalc(sheet) -> None:
    """Recompute through the real engine.

    Prefers the owning workbook's :meth:`~abax.core.workbook.Workbook.recalculate`
    (so cross-sheet dependents and manual-calc workbooks update); falls back to
    the sheet's own recalc for a standalone sheet with no workbook.
    """
    workbook = getattr(sheet, "workbook", None)
    if workbook is not None:
        workbook.recalculate()
    else:
        sheet.recalculate()


def one_var_data_table(sheet, input_cell: str, values, formula_cell: str) -> list:
    """Evaluate *formula_cell* once per trial value fed into *input_cell*.

    For each ``v`` in *values*, write ``v`` into ``input_cell``, recompute the
    workbook, and read ``formula_cell``. Returns the list of results, one per
    input value, in order (numbers stay numbers; an errored formula yields its
    :class:`~abax.core.errors.CellError`).

    ``input_cell`` and ``formula_cell`` are A1 strings. The original raw content
    of ``input_cell`` is **always** restored and the workbook recomputed on the
    way out (``try``/``finally``), so the sheet is unchanged whether the sweep
    finishes normally or an exception propagates from a trial value.
    """
    ir, ic = parse_a1(input_cell)
    fr, fc = parse_a1(formula_cell)
    original = sheet.get_raw(ir, ic)
    results: list = []
    try:
        for v in values:
            sheet.set_cell(ir, ic, _value_to_text(v))
            _recalc(sheet)
            results.append(sheet.get_value(fr, fc))
        return results
    finally:
        sheet.set_cell(ir, ic, original)
        _recalc(sheet)


def two_var_data_table(
    sheet,
    row_input_cell: str,
    row_values,
    col_input_cell: str,
    col_values,
    formula_cell: str,
) -> list[list]:
    """Build the classic two-variable data table over two inputs.

    The result is a grid whose **rows correspond to** ``col_values`` and whose
    **columns correspond to** ``row_values`` — matching Excel's layout, where the
    row-input series runs across the top and the column-input series runs down
    the side. ``result[i][j]`` is ``formula_cell`` evaluated with
    ``row_input_cell = row_values[j]`` and ``col_input_cell = col_values[i]``.

    All arguments naming cells are A1 strings. Both input cells are **always**
    restored to their original raw contents and the workbook recomputed on the
    way out (``try``/``finally``), so the sheet is left unchanged.
    """
    rr, rc = parse_a1(row_input_cell)
    cr, cc = parse_a1(col_input_cell)
    fr, fc = parse_a1(formula_cell)
    row_orig = sheet.get_raw(rr, rc)
    col_orig = sheet.get_raw(cr, cc)
    col_values = list(col_values)
    row_values = list(row_values)
    grid: list[list] = []
    try:
        for cv in col_values:
            sheet.set_cell(cr, cc, _value_to_text(cv))
            row: list = []
            for rv in row_values:
                sheet.set_cell(rr, rc, _value_to_text(rv))
                _recalc(sheet)
                row.append(sheet.get_value(fr, fc))
            grid.append(row)
        return grid
    finally:
        sheet.set_cell(rr, rc, row_orig)
        sheet.set_cell(cr, cc, col_orig)
        _recalc(sheet)


@dataclass
class Scenario:
    """A named bundle of cell overrides — ``changes`` maps A1 -> value text.

    Values are stored as the *raw text* a cell would hold (so ``"=A1+1"`` is a
    formula override and ``"42"`` a number), which is exactly what
    :meth:`Sheet.set_cell <abax.core.sheet.Sheet.set_cell>` consumes.
    """

    name: str
    changes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """JSON-friendly ``{"name", "changes"}`` mapping."""
        return {"name": self.name, "changes": dict(self.changes)}

    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        """Rebuild a scenario from :meth:`to_dict` output."""
        return cls(str(d.get("name", "")), dict(d.get("changes", {})))


def apply(scenario: Scenario, sheet) -> dict[str, str]:
    """Write *scenario*'s overrides into *sheet* and recompute.

    Returns a ``{A1: prior_raw}`` mapping of the values that were overwritten, so
    the change can be undone — feed it straight back through a scenario, e.g.
    ``apply(Scenario("undo", prior), sheet)``.
    """
    prior: dict[str, str] = {}
    for ref, text in scenario.changes.items():
        r, c = parse_a1(ref)
        prior[ref] = sheet.get_raw(r, c)
        sheet.set_cell(r, c, text)
    _recalc(sheet)
    return prior


def capture(sheet, cells, name: str = "Scenario") -> Scenario:
    """Snapshot the current raw contents of *cells* into a new :class:`Scenario`.

    ``cells`` is an iterable of A1 strings; a range string (``"A1:B2"``) is
    expanded to its constituent cells. The returned scenario, when applied,
    reproduces exactly what the named cells held at capture time.
    """
    changes: dict[str, str] = {}
    for ref in cells:
        if ":" in ref:
            for r, c in iter_range(ref):
                changes[to_a1(r, c)] = sheet.get_raw(r, c)
        else:
            r, c = parse_a1(ref)
            changes[ref] = sheet.get_raw(r, c)
    return Scenario(name, changes)


class ScenarioSet:
    """An ordered, persistable registry of :class:`Scenario` objects.

    Mirrors :class:`abax.core.names.NameRegistry`'s surface — ``add``/``get``/
    ``remove``/``names``/:attr:`version`/``to_dict``/``from_dict`` — so it can be
    attached to a :class:`~abax.core.workbook.Workbook` and serialized in the
    JSON envelope. Scenario overrides are ordinary cell text (non-secret), safe
    to persist. Insertion order is preserved (Excel keeps scenarios in creation
    order).
    """

    def __init__(self) -> None:
        self._scenarios: dict[str, Scenario] = {}
        # Bumped on every mutation, so callers can invalidate caches cheaply
        # (same contract as NameRegistry.version).
        self._version = 0

    @property
    def version(self) -> int:
        """A counter bumped on every mutation (add/remove)."""
        return self._version

    def __len__(self) -> int:
        return len(self._scenarios)

    def __contains__(self, name: str) -> bool:
        return name in self._scenarios

    def add(self, scenario: Scenario) -> None:
        """Add (or replace by name) a scenario."""
        self._scenarios[scenario.name] = scenario
        self._version += 1

    def get(self, name: str) -> "Scenario | None":
        """Return the scenario named *name*, or ``None``."""
        return self._scenarios.get(name)

    def remove(self, name: str) -> None:
        """Remove the scenario named *name*. :class:`KeyError` if absent."""
        del self._scenarios[name]
        self._version += 1

    def names(self) -> list[str]:
        """Scenario names in insertion order."""
        return list(self._scenarios)

    def scenarios(self) -> list[Scenario]:
        """The scenarios in insertion order."""
        return list(self._scenarios.values())

    def to_dict(self) -> dict:
        """JSON-friendly ``{name: {A1: text}}`` mapping (order preserved)."""
        return {name: dict(s.changes) for name, s in self._scenarios.items()}

    @classmethod
    def from_dict(cls, d: dict) -> "ScenarioSet":
        """Build a set from :meth:`to_dict` output (or a ``{name: {A1: text}}``)."""
        registry = cls()
        for name, changes in (d or {}).items():
            registry.add(Scenario(str(name), dict(changes)))
        return registry
