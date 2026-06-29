"""Unified, dockable calculator panel.

A model picker over every calculator qcell offers — the HP Voyager RPN line
(16C/15C/12C, image or vector faceplate), a plain Algebraic calculator, and the
TI-82/83/84 graphing calculators — plus ←/→ Cell interop with the active cell.
Hosted in a QDockWidget so it can sit beside the grid (default: right side).
"""

from __future__ import annotations

from ._qtcompat import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# (display, kind, key) — kind in {"hp","alg","ti"}
_MODELS = [
    ("HP-16C", "hp", "16c"),
    ("HP-15C", "hp", "15c"),
    ("HP-12C", "hp", "12c"),
    ("TI-83 Plus", "ti", "ti83"),
    ("TI-82", "ti", "ti82"),
    ("TI-84 Plus", "ti", "ti84"),
    ("TI-84 Plus CE", "ti", "ti84ce"),
    ("Algebraic", "alg", "alg"),
]


class CalculatorPanel(QWidget):
    def __init__(self, window) -> None:
        super().__init__()
        self._window = window
        self._widget = None
        self._kind = "hp"
        self._key = "16c"
        self._style = "image"
        self._build()

    def _build(self) -> None:
        self._vbox = QVBoxLayout(self)
        row = QHBoxLayout()
        self._model_box = QComboBox(self)
        for name, kind, key in _MODELS:
            self._model_box.addItem(name, (kind, key))
        self._model_box.currentIndexChanged.connect(self._on_model)
        self._style_box = QComboBox(self)
        self._style_box.addItem("Image", "image")
        self._style_box.addItem("Vector", "vector")
        self._style_box.currentIndexChanged.connect(self._on_style)
        row.addWidget(QLabel("Model:", self))
        row.addWidget(self._model_box, 1)
        row.addWidget(self._style_box)
        self._vbox.addLayout(row)
        self._rebuild()
        interop = QHBoxLayout()
        get_btn = QPushButton("⭱ Get from cell", self)
        get_btn.setToolTip("Load the active cell's value into the calculator (Ctrl+Shift+G)")
        get_btn.clicked.connect(self._window.cell_to_calc)
        send_btn = QPushButton("Send to cell ⭳", self)
        send_btn.setToolTip("Write the calculator's value into the selected cell(s) (Ctrl+Shift+H)")
        send_btn.clicked.connect(self._window.calc_to_cells)
        interop.addWidget(get_btn)
        interop.addWidget(send_btn)
        interop.addStretch(1)
        hide = QPushButton("Hide ▾", self)
        hide.setToolTip("Hide the calculator (Ctrl+K to bring it back)")
        hide.clicked.connect(self._hide_window)
        interop.addWidget(hide)
        self._vbox.addLayout(interop)

    def _hide_window(self) -> None:
        top = self.window()
        if top is not None:
            top.hide()

    def _on_model(self, _i: int) -> None:
        self._kind, self._key = self._model_box.currentData()
        self._rebuild()

    def _on_style(self, _i: int) -> None:
        self._style = self._style_box.currentData()
        if self._kind == "hp":
            self._rebuild()

    def _rebuild(self) -> None:
        if self._widget is not None:
            self._vbox.removeWidget(self._widget)
            self._widget.deleteLater()
            self._widget = None
        self._style_box.setVisible(self._kind == "hp")
        self._widget = self._make_widget()
        self._vbox.insertWidget(1, self._widget, 1)
        self._widget.setFocus()

    def _make_widget(self):
        if self._kind == "alg":
            from .algebraic_faceplate import AlgebraicFaceplate

            return AlgebraicFaceplate(self)
        if self._kind == "ti":
            from .ti_faceplate import TIFaceplate

            ti = TIFaceplate(self, skin=self._key)
            ti._host = self
            return ti
        # HP Voyager: image (if assets) else vector
        from .faceplate import MODELS, VoyagerFaceplate
        from .image_faceplate import ImageFaceplate, find_assets_dir

        legends, factory, name = MODELS[self._key]
        keypad = factory()
        if self._style == "image":
            settings = getattr(self._window, "_settings", None)
            sdir = getattr(settings, "faceplate_assets_dir", "") if settings else ""
            adir = find_assets_dir(sdir, self._key)
            if adir is not None:
                try:
                    return ImageFaceplate(keypad, adir, self, legends=legends)
                except Exception:
                    pass
            self._style_box.setCurrentIndex(1)  # reflect vector fallback
        return VoyagerFaceplate(keypad, legends, self, model_name=name.replace("HP-", ""))

    # -- value bridge (driven by the window's calc<->cell actions) ---------

    def current_value(self):
        """The calculator's current numeric value, or None.

        For the HP keypad, any in-progress digit entry is committed first, so the
        number on the LCD is what gets read — not a stale X register (the old
        ``Cell →`` button read X directly, which is why a freshly-typed value
        "did nothing").
        """
        w = self._widget
        if w is None:
            return None
        if hasattr(w, "value"):           # TI / algebraic: display == value()
            try:
                return float(w.value())
            except (TypeError, ValueError):
                return None
        if hasattr(w, "keypad"):          # HP Voyager (vector or image)
            kp = w.keypad
            commit = getattr(kp, "_commit_entry", None)
            if commit is not None:
                commit()
                if hasattr(w, "_refresh_lcd"):
                    w._refresh_lcd()
            try:
                return float(kp.rpn.x)
            except (TypeError, ValueError, AttributeError):
                return None
        return None

    def load_value(self, v: float) -> None:
        """Load ``v`` into the calculator's current model."""
        w = self._widget
        if w is None:
            return
        if hasattr(w, "set_value"):       # TI / algebraic
            w.set_value(v)
        elif hasattr(w, "keypad"):        # HP Voyager
            kp = w.keypad
            kp.entry = ""
            rpn = kp.rpn
            rpn.push(int(v) if hasattr(rpn, "word_size") else v)
            if hasattr(w, "_refresh_lcd"):
                w._refresh_lcd()
