"""Preferences — the one place to manage every persistent abax setting.

A tabbed dialog over everything stored in ``settings.json``, grouped into logical
sections:

* **Appearance** — GUI theme, TUI theme, OpenDyslexic font, default zoom, and the
  interface toggles (toolbar, vim-style keys).
* **Calculator** — default model, faceplate style, angle mode, and the optional
  faceplate-art folder / repository.
* **System** — autosave cadence, code-execution isolation, and whether optional
  dependencies auto-install.

It reuses the existing persistence and live-apply machinery — the same
``settings.json`` and the window's own ``set_theme`` / ``apply_dyslexic_font`` /
``_set_zoom`` / ``set_toolbar_visible`` / ``set_vim_mode`` / ``set_code_isolation``
/ ``restart_autosave`` methods — rather than inventing a parallel mechanism.

* **OK / Apply** write the values back through those methods and persist to
  ``settings.json``.
* **Cancel** discards pending changes and restores the live appearance (theme,
  font, zoom, toolbar, vim mode) that was active when the dialog opened.

Live vs deferred: appearance/interface changes apply immediately; autosave, code
isolation, and auto-install take effect on the next tick / run; calculator and TUI
settings take effect the next time you open the calculator / launch the TUI.
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# (settings key, label) for the theme pickers — order matches the Format > Theme menu.
_THEMES = [
    ("obsidian", "Obsidian (default)"),
    ("dark_one", "Dark One"),
    ("nord", "Nord"),
    ("solarized", "Solarized"),
    ("crt_green", "CRT — green"),
    ("crt_amber", "CRT — amber"),
    ("light", "Light"),
    ("high_contrast", "High contrast"),
]

# The three code-isolation levels, matching mixin_console._ISOLATION_ORDER.
_ISOLATION = [
    ("off", "Off — in-process (no isolation)"),
    ("isolated", "Isolated — worker + resource limits (default)"),
    ("strict", "Strict — OS sandbox (no network, scratch-only writes)"),
]

# (calc_model key, label) — mirrors calculator_panel._MODELS (key = its 3rd field).
_CALC_MODELS = [
    ("alg", "Algebraic"),
    ("12c", "HP-12C"),
    ("15c", "HP-15C"),
    ("16c", "HP-16C"),
    ("ti82", "TI-82"),
    ("ti83", "TI-83 Plus"),
    ("ti84", "TI-84 Plus"),
    ("ti84ce", "TI-84 Plus CE"),
]
_CALC_DEFAULT_MODEL = "16c"   # calculator_panel's fallback when none is saved


class PreferencesDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._settings = window._settings
        self.setWindowTitle("Preferences")
        self.resize(520, 500)
        # Snapshot the live appearance we might change, so Cancel can revert it.
        self._orig_theme = getattr(self._settings, "theme", "obsidian")
        self._orig_zoom = float(getattr(self._settings, "zoom", 1.0) or 1.0)
        self._orig_dyslexic = bool(getattr(self._settings, "dyslexic_font", False))
        self._orig_toolbar = bool(getattr(self._settings, "show_toolbar", True))
        self._orig_vim = bool(getattr(self._settings, "vim_mode", True))
        self._build()
        self._load()

    # --- construction -----------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.addTab(self._appearance_tab(), "Appearance")
        tabs.addTab(self._accessibility_tab(), "Accessibility")
        tabs.addTab(self._calculator_tab(), "Calculator")
        tabs.addTab(self._system_tab(), "System")
        root.addWidget(tabs)

        note = QLabel(
            "Appearance applies live. Autosave, isolation, and auto-install take "
            "effect on the next tick / run; calculator and TUI settings apply the "
            "next time you open the calculator / launch the TUI.", self)
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel,
            self)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self._on_cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply)
        self._buttons = buttons
        root.addWidget(buttons)

    def _appearance_tab(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)

        text_box = QGroupBox("Theme & text", page)
        form = QFormLayout(text_box)
        self._theme = QComboBox(text_box)
        for key, label in _THEMES:
            self._theme.addItem(label, key)
        form.addRow("GUI theme:", self._theme)
        self._tui_theme = QComboBox(text_box)
        for key, label in _THEMES:
            self._tui_theme.addItem(label, key)
        form.addRow("TUI theme:", self._tui_theme)
        self._dyslexic = QCheckBox("Use the OpenDyslexic font across the UI", text_box)
        form.addRow("Font:", self._dyslexic)
        self._zoom = QDoubleSpinBox(text_box)
        self._zoom.setRange(0.5, 3.0)
        self._zoom.setSingleStep(0.1)
        self._zoom.setDecimals(1)
        self._zoom.setSuffix("x")
        form.addRow("Default zoom:", self._zoom)
        outer.addWidget(text_box)

        iface_box = QGroupBox("Interface", page)
        iform = QFormLayout(iface_box)
        self._show_toolbar = QCheckBox("Show the main toolbar", iface_box)
        iform.addRow(self._show_toolbar)
        self._vim = QCheckBox("Vim-style modal keys (Normal / Insert / Visual)", iface_box)
        iform.addRow(self._vim)
        outer.addWidget(iface_box)
        outer.addStretch(1)
        return page

    def _accessibility_tab(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)

        a11y_box = QGroupBox("Accessibility", page)
        form = QFormLayout(a11y_box)
        self._high_contrast = QCheckBox(
            "High-contrast mode (bolder colours, stronger focus outline)", a11y_box)
        form.addRow(self._high_contrast)
        self._speak_on_move = QCheckBox(
            "Speak the active cell as I move (text-to-speech)", a11y_box)
        form.addRow(self._speak_on_move)
        self._tui_screen_reader = QCheckBox(
            "Screen-reader-friendly TUI (single-line, reader-first rendering)", a11y_box)
        form.addRow(self._tui_screen_reader)
        outer.addWidget(a11y_box)

        # Surface whether the TTS backend is actually installed, so speak-on-move
        # doesn't silently do nothing. Importing engine.tts is cheap and never
        # fails (it no-ops without pyttsx3).
        try:
            from ...engine import tts
            tts_ok = tts.available()
        except Exception:
            tts_ok = False
        if tts_ok:
            tts_msg = ("Speech uses your system's built-in voice — nothing is sent "
                       "over the network.")
        else:
            tts_msg = ("Speak-on-move needs the optional 'pyttsx3' speech package "
                       "(pip install pyttsx3). Without it, this option is silent; "
                       "the high-contrast and screen-reader options work regardless.")
        hint = QLabel(tts_msg, a11y_box)
        hint.setWordWrap(True)
        form.addRow(hint)

        outer.addStretch(1)
        return page

    def _calculator_tab(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)

        model_box = QGroupBox("Calculator", page)
        form = QFormLayout(model_box)
        self._calc_model = QComboBox(model_box)
        for key, label in _CALC_MODELS:
            self._calc_model.addItem(label, key)
        form.addRow("Default model:", self._calc_model)
        self._calc_style = QComboBox(model_box)
        self._calc_style.addItem("Image (photoreal faceplate)", "image")
        self._calc_style.addItem("Vector (drawn faceplate)", "vector")
        form.addRow("Faceplate style:", self._calc_style)
        self._calc_degrees = QComboBox(model_box)
        self._calc_degrees.addItem("Radians", False)
        self._calc_degrees.addItem("Degrees", True)
        form.addRow("Angle mode:", self._calc_degrees)
        outer.addWidget(model_box)

        art_box = QGroupBox("Faceplate art (optional)", page)
        aform = QFormLayout(art_box)
        dir_row = QHBoxLayout()
        self._faceplate_dir = QLineEdit(art_box)
        self._faceplate_dir.setPlaceholderText("Folder with faceplate images (blank = bundled)")
        browse = QPushButton("Browse...", art_box)
        browse.clicked.connect(self._pick_faceplate_dir)
        dir_row.addWidget(self._faceplate_dir, 1)
        dir_row.addWidget(browse)
        dir_holder = QWidget(art_box)
        dir_holder.setLayout(dir_row)
        aform.addRow("Assets folder:", dir_holder)
        outer.addWidget(art_box)
        outer.addStretch(1)
        return page

    def _system_tab(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)

        auto_box = QGroupBox("Autosave", page)
        auto_form = QFormLayout(auto_box)
        self._autosave_on = QCheckBox("Periodically save settings", auto_box)
        auto_form.addRow(self._autosave_on)
        self._autosave_interval = QSpinBox(auto_box)
        self._autosave_interval.setRange(5, 3600)
        self._autosave_interval.setSuffix(" s")
        auto_form.addRow("Interval:", self._autosave_interval)
        self._autosave_on.toggled.connect(self._autosave_interval.setEnabled)
        outer.addWidget(auto_box)

        iso_box = QGroupBox("Code execution", page)
        iso_form = QFormLayout(iso_box)
        self._code_consent = QCheckBox(
            "Allow code execution (console, terminal, scripts, macros)", iso_box)
        iso_form.addRow(self._code_consent)
        self._isolation = QComboBox(iso_box)
        for key, label in _ISOLATION:
            self._isolation.addItem(label, key)
        iso_form.addRow("Isolation:", self._isolation)
        hint = QLabel("Whether code may run at all, and how the console, scripts, and "
                      "macros are isolated when it does.", iso_box)
        hint.setWordWrap(True)
        iso_form.addRow(hint)
        outer.addWidget(iso_box)

        dep_box = QGroupBox("Optional dependencies", page)
        dep_form = QFormLayout(dep_box)
        manage = QPushButton("Manage optional features…", dep_box)
        manage.clicked.connect(self._manage_features)
        dep_form.addRow(manage)
        self._auto_install = QCheckBox("Let abax install the optional features I choose", dep_box)
        dep_form.addRow(self._auto_install)
        dep_hint = QLabel(
            "abax is complete on its own and never installs anything unprompted. Use "
            "“Manage optional features…” to pick add-ons (Excel, data science, "
            "Jupyter…). Unchecking this keeps every install fully manual "
            "(pip install abax[…]).", dep_box)
        dep_hint.setWordWrap(True)
        dep_form.addRow(dep_hint)
        outer.addWidget(dep_box)

        perf_box = QGroupBox("Performance", page)
        perf_form = QFormLayout(perf_box)
        self._windowed_capacity = QSpinBox(perf_box)
        self._windowed_capacity.setRange(0, 100_000_000)
        self._windowed_capacity.setSingleStep(10_000)
        self._windowed_capacity.setGroupSeparatorShown(True)
        # value 0 shows as the "off" label instead of "0"
        self._windowed_capacity.setSpecialValueText("Off — keep every cell in RAM")
        self._windowed_capacity.setSuffix(" cells / sheet")
        perf_form.addRow("Windowed cell store:", self._windowed_capacity)
        perf_hint = QLabel(
            "Keep at most this many cells resident per sheet and spill the rest to a "
            "temp file — trades memory for latency, worth it only for very large data "
            "imports (applies to files opened afterwards). Set it comfortably above your "
            "deepest formula-dependency chain: a chain longer than the capacity can "
            "surface #CIRC!. Leave it Off unless you actually hit a memory ceiling.",
            perf_box)
        perf_hint.setWordWrap(True)
        perf_form.addRow(perf_hint)
        outer.addWidget(perf_box)

        outer.addStretch(1)
        return page

    # --- load / apply -----------------------------------------------------

    def _load(self) -> None:
        """Populate the widgets from the current settings."""
        s = self._settings
        self._select(self._theme, getattr(s, "theme", "obsidian"))
        self._select(self._tui_theme, getattr(s, "tui_theme", "obsidian"))
        self._dyslexic.setChecked(bool(getattr(s, "dyslexic_font", False)))
        self._zoom.setValue(float(getattr(s, "zoom", 1.0) or 1.0))
        self._show_toolbar.setChecked(bool(getattr(s, "show_toolbar", True)))
        self._vim.setChecked(bool(getattr(s, "vim_mode", True)))

        self._high_contrast.setChecked(bool(getattr(s, "high_contrast", False)))
        self._speak_on_move.setChecked(bool(getattr(s, "speak_on_move", False)))
        self._tui_screen_reader.setChecked(bool(getattr(s, "tui_screen_reader", False)))

        self._select(self._calc_model, getattr(s, "calc_model", "") or _CALC_DEFAULT_MODEL)
        self._select(self._calc_style, getattr(s, "calc_style", "image") or "image")
        self._select(self._calc_degrees, bool(getattr(s, "calc_degrees", False)))
        self._faceplate_dir.setText(getattr(s, "faceplate_assets_dir", "") or "")

        on = bool(getattr(s, "autosave_enabled", True))
        self._autosave_on.setChecked(on)
        self._autosave_interval.setValue(int(getattr(s, "autosave_interval", 30) or 30))
        self._autosave_interval.setEnabled(on)
        self._code_consent.setChecked(bool(getattr(s, "code_consent", False)))
        self._select(self._isolation, getattr(s, "code_isolation", "isolated"))
        self._auto_install.setChecked(bool(getattr(s, "auto_install", True)))
        self._windowed_capacity.setValue(int(getattr(s, "windowed_store_capacity", 0) or 0))

    @staticmethod
    def _select(combo: QComboBox, key) -> None:
        idx = combo.findData(key)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _pick_faceplate_dir(self) -> None:
        start = self._faceplate_dir.text().strip()
        chosen = QFileDialog.getExistingDirectory(self, "Faceplate assets folder", start)
        if chosen:
            self._faceplate_dir.setText(chosen)

    def _manage_features(self) -> None:
        """Open the optional-feature chooser (also on Tools → Install optional features)."""
        if hasattr(self._win, "install_optional_features"):
            self._win.install_optional_features()

    def _apply(self) -> None:
        """Write every widget value back through the window's live-apply methods
        (for appearance) or straight to settings (deferred), then persist."""
        win = self._win
        s = self._settings

        # --- live appearance -------------------------------------------------
        theme = self._theme.currentData()
        if theme != getattr(s, "theme", None):
            win.set_theme(theme)

        want_font = self._dyslexic.isChecked()
        if want_font != bool(getattr(s, "dyslexic_font", False)):
            win.apply_dyslexic_font(want_font)

        zoom = float(self._zoom.value())
        if abs(zoom - float(getattr(s, "zoom", 1.0) or 1.0)) > 1e-9:
            win._set_zoom(zoom)

        show_tb = self._show_toolbar.isChecked()
        if show_tb != bool(getattr(s, "show_toolbar", True)) and hasattr(win, "set_toolbar_visible"):
            win.set_toolbar_visible(show_tb)

        vim = self._vim.isChecked()
        if vim != bool(getattr(s, "vim_mode", True)) and hasattr(win, "set_vim_mode"):
            win.set_vim_mode(vim)

        # --- deferred (persist now; take effect on next use) -----------------
        # Accessibility toggles: persisted here; the front-ends read them live
        # (the GUI speak-on-move hook lives in the grid view, the TUI reader mode
        # in the TUI). high_contrast is honoured on the next theme apply / launch.
        s.high_contrast = self._high_contrast.isChecked()
        s.speak_on_move = self._speak_on_move.isChecked()
        s.tui_screen_reader = self._tui_screen_reader.isChecked()

        s.tui_theme = self._tui_theme.currentData()
        s.calc_model = self._calc_model.currentData()
        s.calc_style = self._calc_style.currentData()
        s.calc_degrees = bool(self._calc_degrees.currentData())
        s.faceplate_assets_dir = self._faceplate_dir.text().strip()

        s.autosave_enabled = self._autosave_on.isChecked()
        s.autosave_interval = int(self._autosave_interval.value())
        if hasattr(win, "restart_autosave"):
            win.restart_autosave()

        # Windowed cell store: persist-only — it's applied when a file is opened,
        # so a change here takes effect on the next open (no live remap).
        s.windowed_store_capacity = int(self._windowed_capacity.value())

        level = self._isolation.currentData()
        if level != getattr(s, "code_isolation", None):
            win.set_code_isolation(level)

        # Code-execution consent — persist-only (the runtime gate reads it live).
        # Revoking is free; enabling here confirms first, since it bypasses the
        # runtime consent prompt's warning.
        want_consent = self._code_consent.isChecked()
        if want_consent and not bool(getattr(s, "code_consent", False)):
            ok = QMessageBox.warning(
                self, "Enable code execution",
                "This lets the console, terminal, scripts, and macros run Python on "
                "your machine. Only enable it if you trust the code you will run.\n\n"
                "Enable?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if ok == QMessageBox.StandardButton.Yes:
                s.code_consent = True
            else:
                self._code_consent.setChecked(False)
        else:
            s.code_consent = want_consent

        auto = self._auto_install.isChecked()
        s.auto_install = auto
        try:
            from ... import autodeps
            autodeps.set_enabled(auto)
        except Exception:
            pass

        self._persist()
        # Re-snapshot: a later Cancel reverts to *this* applied state.
        self._orig_theme = theme
        self._orig_zoom = zoom
        # apply_dyslexic_font may no-op (e.g. offline); snapshot the real state.
        self._orig_dyslexic = bool(getattr(s, "dyslexic_font", False))
        self._orig_toolbar = show_tb
        self._orig_vim = vim

    def _persist(self) -> None:
        from ... import _runtime as rt
        from ...settings import save_settings

        try:
            save_settings(self._settings, rt.CONFIG_DIR / "settings.json")
        except Exception:
            # Persistence is best-effort here; closing the window saves too.
            pass

    # --- button handlers --------------------------------------------------

    def _on_ok(self) -> None:
        self._apply()
        self.accept()

    def _on_cancel(self) -> None:
        # Revert any live appearance changes made via Apply back to the snapshot.
        win = self._win
        s = self._settings
        if getattr(s, "theme", None) != self._orig_theme:
            win.set_theme(self._orig_theme)
        if bool(getattr(s, "dyslexic_font", False)) != self._orig_dyslexic:
            win.apply_dyslexic_font(self._orig_dyslexic)
        if abs(float(getattr(s, "zoom", 1.0) or 1.0) - self._orig_zoom) > 1e-9:
            win._set_zoom(self._orig_zoom)
        if bool(getattr(s, "show_toolbar", True)) != self._orig_toolbar and hasattr(win, "set_toolbar_visible"):
            win.set_toolbar_visible(self._orig_toolbar)
        if bool(getattr(s, "vim_mode", True)) != self._orig_vim and hasattr(win, "set_vim_mode"):
            win.set_vim_mode(self._orig_vim)
        self.reject()
