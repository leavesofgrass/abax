"""Budget visualisation widget: bars, EVM KPI tiles, and forecast label."""

from __future__ import annotations

from abax.gui._qtcompat import (
    QColor,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    Qt,
    QVBoxLayout,
    QWidget,
)


class _KpiTile(QWidget):
    """Small labelled-value tile (like dashboard KPI cards)."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        self._title = QLabel(title)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value = QLabel("--")
        self._value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._value.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        self._value.setFont(font)
        layout.addWidget(self._title)
        layout.addWidget(self._value)

    def setValue(self, text: str) -> None:  # noqa: N802
        self._value.setText(text)


class FinanceView(QWidget):
    """Budget-vs-actual bars, EVM KPI tiles, and forecast line."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        # -- section: budget bars --
        self._bars_label = QLabel("<b>Budget vs Actual</b>")
        root.addWidget(self._bars_label)
        self._bars_area = QVBoxLayout()
        root.addLayout(self._bars_area)
        self._bar_widgets: list[tuple[QLabel, QProgressBar]] = []

        # -- section: EVM tiles --
        evm_label = QLabel("<b>Earned Value Metrics</b>")
        root.addWidget(evm_label)
        tile_grid = QGridLayout()
        root.addLayout(tile_grid)
        self._tiles: dict[str, _KpiTile] = {}
        for idx, key in enumerate(("PV", "EV", "AC", "SPI", "CPI", "EAC")):
            tile = _KpiTile(key)
            self._tiles[key] = tile
            tile_grid.addWidget(tile, idx // 3, idx % 3)

        # -- section: forecast --
        self._forecast = QLabel("")
        self._forecast.setWordWrap(True)
        root.addWidget(self._forecast)
        root.addStretch()

    # ------------------------------------------------------------------
    def setData(  # noqa: N802
        self,
        budget_data: dict,
        evm_data: dict,
    ) -> None:
        """Populate the view from *budget_rollup()* and *evm()* results."""
        self._set_bars(budget_data)
        self._set_evm(evm_data)
        self._set_forecast(budget_data, evm_data)

    # ------------------------------------------------------------------
    def _set_bars(self, bd: dict) -> None:
        # Clear previous bar widgets
        for lbl, bar in self._bar_widgets:
            self._bars_area.removeWidget(lbl)
            self._bars_area.removeWidget(bar)
            lbl.deleteLater()
            bar.deleteLater()
        self._bar_widgets.clear()

        for proj in bd.get("per_project", []):
            name = proj.get("name", "?")
            budget = proj.get("budget", 0)
            cost = proj.get("cost", 0)
            pct = int(proj.get("pct_used", 0))

            row = QHBoxLayout()
            lbl = QLabel(name)
            lbl.setMinimumWidth(100)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(min(pct, 100))
            bar.setFormat(f"{cost:,.0f} / {budget:,.0f}  ({pct}%)")

            # Green if under budget, red if over
            colour = QColor(76, 175, 80) if pct <= 100 else QColor(244, 67, 54)
            bar.setStyleSheet(
                f"QProgressBar::chunk {{ background-color: {colour.name()}; }}"
            )

            row.addWidget(lbl)
            row.addWidget(bar, stretch=1)
            container = QWidget()
            container.setLayout(row)
            self._bars_area.addWidget(container)
            self._bar_widgets.append((lbl, bar))

    def _set_evm(self, ed: dict) -> None:
        for key, tile in self._tiles.items():
            val = ed.get(key)
            if val is None:
                tile.setValue("--")
            elif isinstance(val, float):
                tile.setValue(f"{val:,.2f}")
            else:
                tile.setValue(str(val))

    def _set_forecast(self, bd: dict, ed: dict) -> None:
        eac = ed.get("EAC")
        total = bd.get("total_budget", 0)
        if eac is None:
            self._forecast.setText("Forecast: insufficient data")
            return
        if eac < total:
            status = "UNDER budget"
        elif eac > total:
            status = "OVER budget"
        else:
            status = "ON budget"
        self._forecast.setText(
            f"Forecast: EAC = {eac:,.2f}  —  project is {status}"
        )
