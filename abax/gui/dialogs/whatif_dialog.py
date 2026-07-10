"""What-if analysis dialog — data tables and scenarios.

A tabbed front-end over :mod:`abax.core.whatif`:

* **One-variable data table** — sweep a series of values through one input cell
  and lay the input/result pairs into the grid.
* **Two-variable data table** — the classic grid over two inputs.
* **Scenarios** — capture, apply, and undo named bundles of cell overrides,
  backed by a :class:`~abax.core.whatif.ScenarioSet` lazily attached to the
  workbook (so scenarios persist across dialog sessions and can be serialized).

The heavy lifting lives in the programmatic API (:meth:`run_one_var`,
:meth:`run_two_var`, :meth:`add_scenario`, :meth:`apply_scenario`,
:meth:`undo_scenario`) so the dialog is fully driveable headlessly in tests; the
Qt handlers just marshal widget text into those calls. Qt is imported only via
``.._qtcompat`` (the single binding shim).
"""

from __future__ import annotations

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from ...core import whatif
from ...core.errors import FormulaError
from ...core.reference import iter_range, parse_a1, to_a1


def _parse_values(text: str, sheet) -> list:
    """Parse the *values* field into a list of trial values.

    A range (``"A1:A5"``) is read from the sheet; otherwise the text is split on
    commas/whitespace and each token is coerced to a number when it looks like
    one (so ``"1, 2, 3.5"`` -> ``[1.0, 2.0, 3.5]``), else kept as text.
    """
    text = text.strip()
    if not text:
        return []
    if ":" in text:
        return [sheet.get_value(r, c) for r, c in iter_range(text)]
    out: list = []
    for tok in text.replace(";", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(float(tok))
        except ValueError:
            out.append(tok)
    return out


def _parse_changes(text: str) -> dict[str, str]:
    """Parse ``A1=value`` pairs (comma- or newline-separated) into a dict."""
    changes: dict[str, str] = {}
    for line in text.replace(",", "\n").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        ref, _, val = line.partition("=")
        changes[ref.strip()] = val.strip()
    return changes


class WhatIfDialog(QDialog):
    """Data-table + scenario what-if analysis over the active sheet."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("What-if analysis")
        # Lazily attach a ScenarioSet to the workbook so scenarios survive across
        # dialog sessions (and can be serialized alongside the workbook). No edit
        # to workbook.py is needed — the attribute is created on first use.
        wb = self._win._doc.workbook
        self.scenarios = getattr(wb, "scenarios", None)
        if not isinstance(self.scenarios, whatif.ScenarioSet):
            self.scenarios = whatif.ScenarioSet()
            wb.scenarios = self.scenarios
        self._last_prior: dict[str, str] = {}
        self._build()

    # --- sheet access -----------------------------------------------------

    @property
    def _sheet(self):
        return self._win._doc.workbook.sheet

    def _after_write(self, message: str = "") -> None:
        """Mark the document dirty and repaint the grid after writing results."""
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        if message:
            self._readout.setText(message)

    @staticmethod
    def _cell_text(sheet, val) -> str:
        """Render a computed value as the raw text to drop into a cell."""
        return sheet.format_value(val)

    # --- programmatic API (testable headlessly) ---------------------------

    def run_one_var(
        self,
        input_cell: str,
        values,
        formula_cell: str,
        output_cell: str,
        orientation: str = "column",
    ) -> list:
        """Run a one-variable data table and write the input/result pairs.

        Sweeps *values* through ``input_cell``, reading ``formula_cell`` for each
        (via :func:`abax.core.whatif.one_var_data_table`, which restores the
        input afterwards), then lays the pairs out starting at ``output_cell``:
        inputs in the first column/row and results in the next, per
        *orientation* (``"column"`` or ``"row"``). Returns the results list.
        """
        sheet = self._sheet
        values = list(values)
        results = whatif.one_var_data_table(sheet, input_cell, values, formula_cell)
        r0, c0 = parse_a1(output_cell)
        for i, (v, res) in enumerate(zip(values, results)):
            if orientation == "row":
                sheet.set_cell(r0, c0 + i, whatif._value_to_text(v))
                sheet.set_cell(r0 + 1, c0 + i, self._cell_text(sheet, res))
            else:
                sheet.set_cell(r0 + i, c0, whatif._value_to_text(v))
                sheet.set_cell(r0 + i, c0 + 1, self._cell_text(sheet, res))
        self._after_write(f"One-variable table: {len(results)} rows written.")
        return results

    def run_two_var(
        self,
        row_input_cell: str,
        row_values,
        col_input_cell: str,
        col_values,
        formula_cell: str,
        output_cell: str,
    ) -> list[list]:
        """Run a two-variable data table and write the grid (with headers).

        Delegates to :func:`abax.core.whatif.two_var_data_table` (which restores
        both inputs), then writes the grid at ``output_cell``: ``row_values``
        across the top edge, ``col_values`` down the left edge, and results in
        the interior. Returns the result grid (rows = col_values).
        """
        sheet = self._sheet
        row_values = list(row_values)
        col_values = list(col_values)
        grid = whatif.two_var_data_table(
            sheet, row_input_cell, row_values, col_input_cell, col_values, formula_cell
        )
        r0, c0 = parse_a1(output_cell)
        for j, rv in enumerate(row_values):
            sheet.set_cell(r0, c0 + 1 + j, whatif._value_to_text(rv))
        for i, cv in enumerate(col_values):
            sheet.set_cell(r0 + 1 + i, c0, whatif._value_to_text(cv))
            for j, res in enumerate(grid[i]):
                sheet.set_cell(r0 + 1 + i, c0 + 1 + j, self._cell_text(sheet, res))
        self._after_write(
            f"Two-variable table: {len(col_values)}x{len(row_values)} grid written."
        )
        return grid

    def add_scenario(self, name: str, changes: dict[str, str]) -> whatif.Scenario:
        """Register a named scenario (A1 -> value text) and return it."""
        scenario = whatif.Scenario(name, dict(changes))
        self.scenarios.add(scenario)
        self._refresh_scenario_list()
        return scenario

    def capture_scenario(self, name: str, cells) -> whatif.Scenario:
        """Snapshot *cells* from the sheet into a scenario and register it."""
        scenario = whatif.capture(self._sheet, cells, name)
        self.scenarios.add(scenario)
        self._refresh_scenario_list()
        return scenario

    def apply_scenario(self, name: str) -> dict[str, str]:
        """Apply the named scenario to the sheet; return the prior values.

        The prior values are also stashed so :meth:`undo_scenario` can restore
        them. Raises :class:`KeyError` if no such scenario exists.
        """
        scenario = self.scenarios.get(name)
        if scenario is None:
            raise KeyError(name)
        self._last_prior = whatif.apply(scenario, self._sheet)
        self._after_write(f"Applied scenario {name!r}.")
        return self._last_prior

    def undo_scenario(self) -> None:
        """Restore the values captured by the most recent :meth:`apply_scenario`."""
        if not self._last_prior:
            return
        whatif.apply(whatif.Scenario("undo", dict(self._last_prior)), self._sheet)
        self._last_prior = {}
        self._after_write("Scenario undone.")

    # --- UI ---------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.addTab(self._build_one_var_tab(), "One-variable")
        tabs.addTab(self._build_two_var_tab(), "Two-variable")
        tabs.addTab(self._build_scenario_tab(), "Scenarios")
        root.addWidget(tabs)
        self._readout = QLabel("", self)
        self._readout.setWordWrap(True)
        root.addWidget(self._readout)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(close)
        root.addLayout(bar)

    def _build_one_var_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        r, c = self._win._current_cell()
        self._ov_input = QLineEdit("A1", page)
        self._ov_values = QLineEdit("", page)
        self._ov_values.setToolTip("Comma-separated values, or a range like A1:A5")
        self._ov_formula = QLineEdit(to_a1(r, c), page)
        self._ov_output = QLineEdit(to_a1(r, c + 1), page)
        self._ov_orient = QComboBox(page)
        self._ov_orient.addItems(["column", "row"])
        form.addRow("Input cell:", self._ov_input)
        form.addRow("Values:", self._ov_values)
        form.addRow("Formula cell:", self._ov_formula)
        form.addRow("Output top-left:", self._ov_output)
        form.addRow("Orientation:", self._ov_orient)
        run = QPushButton("Run one-variable table", page)
        run.clicked.connect(self._on_run_one_var)
        form.addRow(run)
        return page

    def _build_two_var_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        self._tv_row_input = QLineEdit("A1", page)
        self._tv_row_values = QLineEdit("", page)
        self._tv_col_input = QLineEdit("B1", page)
        self._tv_col_values = QLineEdit("", page)
        self._tv_formula = QLineEdit("C1", page)
        self._tv_output = QLineEdit("E1", page)
        form.addRow("Row input cell:", self._tv_row_input)
        form.addRow("Row values:", self._tv_row_values)
        form.addRow("Column input cell:", self._tv_col_input)
        form.addRow("Column values:", self._tv_col_values)
        form.addRow("Formula cell:", self._tv_formula)
        form.addRow("Output top-left:", self._tv_output)
        run = QPushButton("Run two-variable table", page)
        run.clicked.connect(self._on_run_two_var)
        form.addRow(run)
        return page

    def _build_scenario_tab(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        form = QFormLayout()
        self._sc_name = QLineEdit("Scenario 1", page)
        self._sc_changes = QPlainTextEdit(page)
        self._sc_changes.setPlaceholderText("A1=100\nB2=0.05")
        self._sc_changes.setFixedHeight(80)
        form.addRow("Name:", self._sc_name)
        form.addRow("Changes:", self._sc_changes)
        outer.addLayout(form)
        add = QPushButton("Add / update scenario", page)
        add.clicked.connect(self._on_add_scenario)
        outer.addWidget(add)
        self._sc_list = QComboBox(page)
        outer.addWidget(self._sc_list)
        bar = QHBoxLayout()
        apply_btn = QPushButton("Apply", page)
        apply_btn.clicked.connect(self._on_apply_scenario)
        undo_btn = QPushButton("Undo last", page)
        undo_btn.clicked.connect(lambda: self.undo_scenario())
        bar.addWidget(apply_btn)
        bar.addWidget(undo_btn)
        bar.addStretch(1)
        outer.addLayout(bar)
        self._refresh_scenario_list()
        return page

    def _refresh_scenario_list(self) -> None:
        combo = getattr(self, "_sc_list", None)
        if combo is None:
            return
        current = combo.currentText()
        combo.clear()
        combo.addItems(self.scenarios.names())
        idx = combo.findText(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    # --- UI handlers ------------------------------------------------------

    def _on_run_one_var(self) -> None:
        sheet = self._sheet
        try:
            parse_a1(self._ov_input.text().strip())
            parse_a1(self._ov_formula.text().strip())
            parse_a1(self._ov_output.text().strip())
            values = _parse_values(self._ov_values.text(), sheet)
        except FormulaError:
            QMessageBox.warning(self, "What-if", "Enter valid cell references.")
            return
        if not values:
            QMessageBox.warning(self, "What-if", "Enter at least one value.")
            return
        self.run_one_var(
            self._ov_input.text().strip(),
            values,
            self._ov_formula.text().strip(),
            self._ov_output.text().strip(),
            self._ov_orient.currentText(),
        )

    def _on_run_two_var(self) -> None:
        sheet = self._sheet
        try:
            parse_a1(self._tv_row_input.text().strip())
            parse_a1(self._tv_col_input.text().strip())
            parse_a1(self._tv_formula.text().strip())
            parse_a1(self._tv_output.text().strip())
            row_values = _parse_values(self._tv_row_values.text(), sheet)
            col_values = _parse_values(self._tv_col_values.text(), sheet)
        except FormulaError:
            QMessageBox.warning(self, "What-if", "Enter valid cell references.")
            return
        if not row_values or not col_values:
            QMessageBox.warning(self, "What-if", "Enter row and column values.")
            return
        self.run_two_var(
            self._tv_row_input.text().strip(),
            row_values,
            self._tv_col_input.text().strip(),
            col_values,
            self._tv_formula.text().strip(),
            self._tv_output.text().strip(),
        )

    def _on_add_scenario(self) -> None:
        name = self._sc_name.text().strip()
        if not name:
            QMessageBox.warning(self, "What-if", "Name the scenario.")
            return
        changes = _parse_changes(self._sc_changes.toPlainText())
        if not changes:
            QMessageBox.warning(self, "What-if", "Enter at least one A1=value change.")
            return
        self.add_scenario(name, changes)
        self._readout.setText(f"Scenario {name!r} saved ({len(changes)} cells).")

    def _on_apply_scenario(self) -> None:
        name = self._sc_list.currentText().strip()
        if not name:
            return
        try:
            self.apply_scenario(name)
        except KeyError:
            QMessageBox.warning(self, "What-if", f"No scenario named {name!r}.")
