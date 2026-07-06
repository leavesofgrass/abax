"""Unified, dockable calculator panel.

A model picker over every calculator abax offers — the HP Voyager RPN line
(16C/15C/12C, image or vector faceplate), a plain Algebraic calculator, and the
TI-82/83/84 graphing calculators — plus ←/→ Cell interop with the active cell.
Hosted in a QDockWidget so it can sit beside the grid (default: right side).
"""

from __future__ import annotations

from .._qtcompat import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# (display, kind, key) — kind in {"hp","alg","ti"}
_MODELS = [
    ("Algebraic", "alg", "alg"),
    ("HP-12C", "hp", "12c"),
    ("HP-15C", "hp", "15c"),
    ("HP-16C", "hp", "16c"),
    ("TI-82", "ti", "ti82"),
    ("TI-83 Plus", "ti", "ti83"),
    ("TI-84 Plus", "ti", "ti84"),
    ("TI-84 Plus CE", "ti", "ti84ce"),
]


class CalculatorPanel(QWidget):
    def __init__(self, window) -> None:
        super().__init__()
        self._window = window
        self._widget = None
        self._kind, self._key, self._style = "hp", "16c", "image"
        # Restore the last-used model + style (persisted across sessions).
        s = getattr(window, "_settings", None)
        saved_key = getattr(s, "calc_model", "") if s is not None else ""
        for _name, kind, key in _MODELS:
            if key == saved_key:
                self._kind, self._key = kind, key
                break
        if getattr(s, "calc_style", "") in ("image", "vector"):
            self._style = s.calc_style
        self._build()

    def _build(self) -> None:
        self._vbox = QVBoxLayout(self)
        row = QHBoxLayout()
        self._model_box = QComboBox(self)
        for name, kind, key in _MODELS:
            self._model_box.addItem(name, (kind, key))
        # Select the default model (HP-16C) before wiring the change signal, so the
        # dropdown matches the faceplate built below — the list is ordered
        # Algebraic, HP, TI, which is not where the default sits.
        default_ix = next((i for i, (_n, k, key) in enumerate(_MODELS)
                           if (k, key) == (self._kind, self._key)), 0)
        self._model_box.setCurrentIndex(default_ix)
        self._model_box.currentIndexChanged.connect(self._on_model)
        self._style_box = QComboBox(self)
        self._style_box.addItem("Image", "image")
        self._style_box.addItem("Vector", "vector")
        self._style_box.setCurrentIndex(1 if self._style == "vector" else 0)
        self._style_box.currentIndexChanged.connect(self._on_style)
        self._prog_btn = QPushButton("Program ▸", self)
        self._prog_btn.setCheckable(True)
        self._prog_btn.setToolTip(
            "Show/hide HP program memory — record, run, and single-step "
            "keystroke programs (LBL/GTO/GSB/RTN)")
        self._prog_btn.toggled.connect(self.toggle_program_panel)
        row.addWidget(QLabel("Model:", self))
        row.addWidget(self._model_box, 1)
        row.addWidget(self._style_box)
        row.addWidget(self._prog_btn)
        self._vbox.addLayout(row)
        # The faceplate and (when shown) the program panel sit side by side.
        self._body = QHBoxLayout()
        self._vbox.addLayout(self._body, 1)
        self._prog_panel = None
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

    # -- HP program memory (record / run / step) ---------------------------

    #: Width added to the floating window while the program panel is shown, so
    #: the faceplate keeps its size instead of being squeezed.
    _PROG_WIDTH = 260

    def toggle_program_panel(self, show: "bool | None" = None) -> None:
        """Show/hide the HP keystroke-program panel beside the faceplate.

        Only meaningful for the HP (RPN) models — the TI/algebraic keypads have
        no program memory, so the request is ignored there. The panel is created
        lazily on first show and re-pointed at the current faceplate.
        """
        visible = self._prog_panel is not None and self._prog_panel.isVisible()
        if show is None:
            show = not visible
        show = bool(show)
        if show and self._kind != "hp":
            show = False           # RPN-only; fall through to sync the button off
        if self._prog_panel is None:
            if not show:
                self._sync_prog_btn(False)
                return
            from .program_panel import ProgramPanel

            self._prog_panel = ProgramPanel(self._widget, self)
            self._prog_panel.setMaximumWidth(self._PROG_WIDTH)
            self._body.addWidget(self._prog_panel)
        if show == visible:        # nothing to change — just keep the button honest
            self._sync_prog_btn(show)
            return
        if show:
            self._prog_panel.set_faceplate(self._widget)
        self._prog_panel.setVisible(show)
        self._sync_prog_btn(show)
        # Widen/narrow the floating window so the faceplate isn't squeezed.
        top = self.window()
        if top is not None and top.isVisible():
            delta = self._PROG_WIDTH if show else -self._PROG_WIDTH
            top.resize(max(320, top.width() + delta), top.height())

    def _sync_prog_btn(self, checked: bool) -> None:
        """Reflect state on the toggle button without re-firing the signal."""
        self._prog_btn.blockSignals(True)
        self._prog_btn.setChecked(checked)
        self._prog_btn.blockSignals(False)

    def _on_model(self, _i: int) -> None:
        self._kind, self._key = self._model_box.currentData()
        self._save_prefs()
        self._rebuild()

    def _on_style(self, _i: int) -> None:
        self._style = self._style_box.currentData()
        self._save_prefs()
        if self._kind == "hp":
            self._rebuild()

    def _save_prefs(self) -> None:
        """Remember the chosen model + style so they persist across sessions."""
        s = getattr(self._window, "_settings", None)
        if s is not None:
            s.calc_model = self._key
            s.calc_style = self._style

    def _rebuild(self) -> None:
        # Re-entrancy guard: a combobox signal fired from inside this method
        # (e.g. a widget factory adjusting the style box) must never start a
        # second rebuild — that stacks an orphaned duplicate faceplate.
        if getattr(self, "_rebuilding", False):
            return
        self._rebuilding = True
        try:
            self._rebuild_inner()
        finally:
            self._rebuilding = False

    def _rebuild_inner(self) -> None:
        if self._widget is not None:
            self._body.removeWidget(self._widget)
            self._widget.deleteLater()
            self._widget = None
        self._style_box.setVisible(self._kind == "hp")
        # Program memory is an HP (RPN keypad) feature — hide the toggle (and any
        # open panel) for the TI / algebraic models.
        self._prog_btn.setVisible(self._kind == "hp")
        self._widget = self._make_widget()
        self._body.insertWidget(0, self._widget, 1)
        self._widget.setFocus()
        if self._prog_panel is not None:
            if self._kind == "hp":
                # Re-point the recorder/runner at the new faceplate (this also
                # stops any in-flight recording safely).
                self._prog_panel.set_faceplate(self._widget)
            else:
                self.toggle_program_panel(False)
                self._prog_panel.set_faceplate(None)

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
            # Reflect the vector fallback in the UI and prefs WITHOUT firing
            # currentIndexChanged: we are inside _rebuild here, and the signal
            # would re-enter it — the re-entrant pass inserts one faceplate and
            # this pass a second, leaving an orphaned duplicate on screen (seen
            # on any machine without faceplate art, e.g. the frozen bundle).
            self._style_box.blockSignals(True)
            self._style_box.setCurrentIndex(1)
            self._style_box.blockSignals(False)
            self._style = "vector"
            self._save_prefs()
            # Say WHY the choice snapped back, so the fallback isn't a silent
            # mystery — abax bundles no artwork; the user has to point at some.
            status = getattr(self._window, "_set_status", None)
            if status is not None:
                status("no faceplate images found — using the vector faceplate "
                       "(Tools → Calculator faceplates → set the image folder)")
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

    def current_text(self):
        """The string ``Send to cell`` writes.

        Same as ``current_value()`` for most models, but for the programmer
        (HP-16C / RPN16) keypad in a **non-decimal base** it returns the value in
        that base as **bare digits** — ``FF`` / ``377`` / ``1010`` (no
        ``0x``/``0o``/``0b`` prefix, for compatibility with other software) —
        rather than the decimal conversion, matching the LCD's two's-complement
        bit pattern.
        """
        w = self._widget
        if w is not None and hasattr(w, "keypad"):
            kp = w.keypad
            commit = getattr(kp, "_commit_entry", None)
            if commit is not None:                # flush any in-progress entry
                commit()
                if hasattr(w, "_refresh_lcd"):
                    w._refresh_lcd()
            rpn = getattr(kp, "rpn", None)
            base = getattr(rpn, "base", 10) if rpn is not None else 10
            if rpn is not None and hasattr(rpn, "word_size") and base != 10:
                try:
                    # Bare digits in the current base (no 0x/0o/0b prefix),
                    # matching the LCD — most portable to other software.
                    return rpn.display().split()[0]
                except Exception:
                    pass
        v = self.current_value()
        if v is None:
            return None
        return str(int(v)) if float(v).is_integer() else repr(v)

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
