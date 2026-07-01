"""An editable abax sheet as a Jupyter widget (optional, via anywidget).

Same split as :mod:`abax.kernel`: the data-sync core is pure and tested, the
widget glue is thin and optional.

* :func:`sheet_state` serializes a bounded view of a sheet for the front-end grid;
  :func:`apply_edit` / :func:`apply_edits` write edits coming back from it. These
  are plain functions over a :class:`abax.core.sheet.Sheet` -- unit-tested without
  any browser or widget runtime.
* :func:`sheet_widget` returns an ``anywidget.AnyWidget`` that renders an editable
  HTML grid (the ``_ESM`` module) and round-trips each cell edit through
  :func:`apply_edit` back into the live sheet, recomputing formulas. anywidget is
  imported only here, so it stays an opt-in dependency.
"""

from __future__ import annotations

# The front-end ES module: a minimal editable grid. Each cell is an <input>; a
# change sets the `edit` trait and saves it, which the Python side applies to the
# sheet and pushes refreshed `cells` back, re-rendering.
_ESM = r"""
function render({ model, el }) {
  function draw() {
    const rows = model.get("rows"), cols = model.get("cols");
    const cells = model.get("cells") || [];
    el.innerHTML = "";
    const title = document.createElement("b");
    title.textContent = model.get("name");
    el.appendChild(title);
    const table = document.createElement("table");
    table.style.borderCollapse = "collapse";
    for (let r = 0; r < rows; r++) {
      const tr = document.createElement("tr");
      for (let c = 0; c < cols; c++) {
        const td = document.createElement("td");
        td.style.border = "1px solid #ccc";
        const inp = document.createElement("input");
        inp.value = (cells[r] && cells[r][c] != null) ? cells[r][c] : "";
        inp.style.width = "72px";
        inp.style.border = "none";
        inp.addEventListener("change", () => {
          model.set("edit", { row: r, col: c, raw: inp.value });
          model.save_changes();
        });
        td.appendChild(inp);
        tr.appendChild(td);
      }
      table.appendChild(tr);
    }
    el.appendChild(table);
  }
  model.on("change:cells", draw);
  draw();
}
export default { render };
"""


def sheet_state(sheet, max_rows: int = 200, max_cols: int = 26) -> dict:
    """A bounded ``{name, rows, cols, cells}`` snapshot of ``sheet`` for the grid.

    ``cells`` holds the *displayed* (computed) value of each cell, row-major.
    """
    nr, nc = sheet.used_bounds()
    rows = min(max(nr, 1), max_rows)
    cols = min(max(nc, 1), max_cols)
    cells = [[sheet.display(r, c) for c in range(cols)] for r in range(rows)]
    return {"name": sheet.name, "rows": rows, "cols": cols, "cells": cells}


def apply_edit(sheet, row, col, raw) -> None:
    """Write a single edit (raw text -> cell) back into the sheet."""
    sheet.set_cell(int(row), int(col), "" if raw is None else str(raw))


def apply_edits(sheet, edits) -> int:
    """Apply a list of ``{"row", "col", "raw"}`` edits; return how many landed."""
    count = 0
    for e in edits:
        apply_edit(sheet, e["row"], e["col"], e.get("raw", ""))
        count += 1
    return count


def _make_widget_class():
    """Build the AnyWidget subclass (anywidget imported lazily so it stays optional)."""
    import anywidget
    import traitlets

    class SheetWidget(anywidget.AnyWidget):
        _esm = _ESM
        name = traitlets.Unicode("Sheet").tag(sync=True)
        rows = traitlets.Int(1).tag(sync=True)
        cols = traitlets.Int(1).tag(sync=True)
        cells = traitlets.List().tag(sync=True)
        edit = traitlets.Dict().tag(sync=True)

        def __init__(self, sheet, **kwargs):
            super().__init__(**kwargs)
            self._sheet = sheet
            self.refresh()
            self.observe(self._on_edit, names="edit")

        def refresh(self):
            state = sheet_state(self._sheet)
            self.name = state["name"]
            self.rows = state["rows"]
            self.cols = state["cols"]
            self.cells = state["cells"]

        def _on_edit(self, change):
            edit = change["new"]
            if edit and "row" in edit and "col" in edit:
                apply_edit(self._sheet, edit["row"], edit["col"], edit.get("raw", ""))
                self.refresh()

    return SheetWidget


def sheet_widget(sheet):
    """Return an editable :class:`anywidget.AnyWidget` bound to ``sheet``.

    Raises a clear error if anywidget is not installed.
    """
    try:
        cls = _make_widget_class()
    except ImportError:
        raise SystemExit(
            "the editable sheet widget needs anywidget — install it with "
            "`pip install anywidget` (abax itself needs no extra deps)")
    return cls(sheet)
