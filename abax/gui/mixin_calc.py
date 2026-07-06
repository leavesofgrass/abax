"""CalcMixin — The floating calculator: window/panel lifecycle, cell interop, faceplate folder."""

from __future__ import annotations

from ..core.reference import to_a1


class CalcMixin:
    def _calculator_window(self):
        """The floating calculator window (created once)."""
        win = getattr(self, "_calc_window", None)
        if win is None:
            from ._qtcompat import QDialog, QVBoxLayout
            from .calc.calculator_panel import CalculatorPanel

            win = QDialog(self)
            win.setWindowTitle("Calculator")
            win.setModal(False)
            lay = QVBoxLayout(win)
            lay.setContentsMargins(0, 0, 0, 0)
            panel = CalculatorPanel(self)
            lay.addWidget(panel)
            win._panel = panel
            win.resize(380, 660)
            self._calc_window = win
        return win

    def show_calculator(self) -> None:
        win = self._calculator_window()
        win.show()
        win.raise_()
        win.activateWindow()
        if getattr(win._panel, "_widget", None) is not None:
            win._panel._widget.setFocus()   # so the keyboard drives the calculator

    def toggle_calculator(self) -> None:
        """Pop the floating calculator in or out (Ctrl+K / menu)."""
        win = self._calculator_window()
        if win.isVisible():
            win.hide()
        else:
            self.show_calculator()

    def _refresh_calculator(self) -> None:
        """Rebuild the calculator's current faceplate (e.g. after new HP art)."""
        win = getattr(self, "_calc_window", None)
        if win is not None and getattr(win, "_panel", None) is not None:
            win._panel._rebuild()

    def show_program_panel(self) -> None:
        """Open the calculator with the HP keystroke-program panel visible.

        Program memory (record / run / step, LBL/GTO/GSB/RTN) is an RPN feature,
        so this needs one of the HP models selected in the calculator.
        """
        self.show_calculator()
        panel = self._calc_panel()
        if panel is None:
            return
        if panel._kind != "hp":
            self._set_status(
                "program memory is for the HP (RPN) models — pick 12C / 15C / 16C")
            return
        panel.toggle_program_panel(True)

    def _calc_panel(self):
        win = getattr(self, "_calc_window", None)
        return getattr(win, "_panel", None) if win is not None else None

    def calc_to_cells(self) -> None:
        """Write the calculator's current value into every selected cell (undoable)."""
        panel = self._calc_panel()
        if panel is None:
            self._set_status("calculator isn't open — press Ctrl+K")
            return
        text = panel.current_text()
        if text is None:
            self._set_status("the calculator has no numeric value")
            return

        r1, c1, r2, c2 = self._selected_bounds()
        self._doc.checkpoint("calculator -> cell")
        sheet = self._doc.workbook.sheet
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                sheet.set_cell(r, c, text)
                self._record(to_a1(r, c), text)
        self._doc.mark_dirty()
        self.refresh_table()
        # Re-anchor the target as the current cell and scroll it into view: the
        # written value stays visible even if the floating calculator overlaps the
        # grid, and the next send has a valid anchor (guards a "second send did
        # nothing" report where the current cell/selection had gone stale).
        if r1 == r2 and c1 == c2:
            self._table.setCurrentCell(r1, c1)
        self._table.scrollTo(self._model.index(r1, c1))
        count = (r2 - r1 + 1) * (c2 - c1 + 1)
        self._set_status(f"wrote {text} to {to_a1(r1, c1)}"
                         + (f" +{count - 1} more cell(s)" if count > 1 else ""))

    def cell_to_calc(self) -> None:
        """Load the active cell's numeric value into the calculator."""
        self.show_calculator()   # make sure it's visible first
        panel = self._calc_panel()
        if panel is None:
            return
        table = self._table
        item = table.item(max(0, table.currentRow()), max(0, table.currentColumn()))
        try:
            v = float(item.text()) if item is not None else None
        except (TypeError, ValueError):
            v = None
        if v is None:
            self._set_status("the active cell isn't a number")
            return
        panel.load_value(v)
        self._set_status(f"loaded {item.text()} into the calculator")

    def set_faceplate_folder(self) -> None:
        from ._qtcompat import QFileDialog

        start = getattr(self._settings, "faceplate_assets_dir", "") or ""
        chosen = QFileDialog.getExistingDirectory(
            self, "Select faceplate image folder (e.g. qv assets/voyager)", start)
        if not chosen:
            return
        self._settings.faceplate_assets_dir = chosen
        from .. import _runtime as rt
        from ..settings import save_settings

        save_settings(self._settings, rt.CONFIG_DIR / "settings.json")
        # rebuild an open faceplate so the new art takes effect immediately
        self._refresh_calculator()
        self._set_status(f"faceplate folder: {chosen}")

    show_faceplate = toggle_calculator
