"""Preferences — configure abax's user settings through a UI.

A single dialog over the settings that most users want to change: appearance
(theme, OpenDyslexic font, default zoom), autosave (on/off + interval), and the
code-execution isolation level (off / isolated / strict, matching the Tools menu
and the command palette).

It reuses the existing persistence and live-apply machinery — the same
``settings.json`` written everywhere else, and the window's own ``set_theme`` /
``apply_dyslexic_font`` / ``set_code_isolation`` / ``restart_autosave`` methods —
rather than inventing a parallel mechanism.

* **OK / Apply** write the values back through those methods and persist to
  ``settings.json`` (via :func:`abax.settings.save_settings`).
* **Cancel** discards every pending change and restores the appearance (theme,
  font, zoom) that was live when the dialog opened.

Appearance changes (theme, font, zoom) apply live. Autosave and code isolation
persist immediately and take effect for the next autosave tick / next code run.
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# (settings key, label) for the theme picker — order matches the Format > Theme menu.
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


class PreferencesDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._settings = window._settings
        self.setWindowTitle("Preferences")
        self.resize(460, 380)
        # Snapshot the appearance we might change live, so Cancel can revert it.
        self._orig_theme = getattr(self._settings, "theme", "obsidian")
        self._orig_zoom = float(getattr(self._settings, "zoom", 1.0) or 1.0)
        self._orig_dyslexic = bool(getattr(self._settings, "dyslexic_font", False))
        self._build()
        self._load()

    # --- construction -----------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        tabs = QTabWidget(self)
        tabs.addTab(self._appearance_tab(), "Appearance")
        tabs.addTab(self._behaviour_tab(), "Behaviour")
        root.addWidget(tabs)

        note = QLabel(
            "Theme, font, and zoom apply live. Autosave and code isolation take "
            "effect for the next autosave tick / next code you run.", self)
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
        form = QFormLayout(page)

        self._theme = QComboBox(page)
        for key, label in _THEMES:
            self._theme.addItem(label, key)
        form.addRow("Theme:", self._theme)

        self._dyslexic = QCheckBox("Use the OpenDyslexic font across the UI", page)
        form.addRow("Font:", self._dyslexic)

        self._zoom = QDoubleSpinBox(page)
        self._zoom.setRange(0.5, 3.0)
        self._zoom.setSingleStep(0.1)
        self._zoom.setDecimals(1)
        self._zoom.setSuffix("x")
        form.addRow("Default zoom:", self._zoom)
        return page

    def _behaviour_tab(self) -> QWidget:
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
        # Grey out the interval when autosave is off.
        self._autosave_on.toggled.connect(self._autosave_interval.setEnabled)
        outer.addWidget(auto_box)

        iso_box = QGroupBox("Code isolation (sandbox)", page)
        iso_form = QFormLayout(iso_box)
        self._isolation = QComboBox(iso_box)
        for key, label in _ISOLATION:
            self._isolation.addItem(label, key)
        iso_form.addRow("Level:", self._isolation)
        hint = QLabel(
            "How the Python console, scripts, and macros are isolated.", iso_box)
        hint.setWordWrap(True)
        iso_form.addRow(hint)
        outer.addWidget(iso_box)
        outer.addStretch(1)
        return page

    # --- load / apply -----------------------------------------------------

    def _load(self) -> None:
        """Populate the widgets from the current settings."""
        s = self._settings
        self._select(self._theme, getattr(s, "theme", "obsidian"))
        self._dyslexic.setChecked(bool(getattr(s, "dyslexic_font", False)))
        self._zoom.setValue(float(getattr(s, "zoom", 1.0) or 1.0))
        on = bool(getattr(s, "autosave_enabled", True))
        self._autosave_on.setChecked(on)
        self._autosave_interval.setValue(int(getattr(s, "autosave_interval", 30) or 30))
        self._autosave_interval.setEnabled(on)
        self._select(self._isolation, getattr(s, "code_isolation", "isolated"))

    @staticmethod
    def _select(combo: QComboBox, key: str) -> None:
        idx = combo.findData(key)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _apply(self) -> None:
        """Write every widget value back through the window's live-apply methods,
        then persist settings.json."""
        win = self._win

        # Theme — set_theme re-applies the stylesheet live.
        theme = self._theme.currentData()
        if theme != getattr(self._settings, "theme", None):
            win.set_theme(theme)

        # OpenDyslexic font — apply_dyslexic_font fetches (if needed) and restyles.
        want_font = self._dyslexic.isChecked()
        if want_font != bool(getattr(self._settings, "dyslexic_font", False)):
            win.apply_dyslexic_font(want_font)

        # Zoom — _set_zoom clamps + re-applies the theme.
        zoom = float(self._zoom.value())
        if abs(zoom - float(getattr(self._settings, "zoom", 1.0) or 1.0)) > 1e-9:
            win._set_zoom(zoom)

        # Autosave — persist and restart the timer with the new cadence.
        self._settings.autosave_enabled = self._autosave_on.isChecked()
        self._settings.autosave_interval = int(self._autosave_interval.value())
        if hasattr(win, "restart_autosave"):
            win.restart_autosave()

        # Code isolation — set_code_isolation keeps the Tools menu checkmarks in
        # sync and resets the worker.
        level = self._isolation.currentData()
        if level != getattr(self._settings, "code_isolation", None):
            win.set_code_isolation(level)

        self._persist()
        # Re-snapshot: a further Cancel should revert to *this* applied state.
        self._orig_theme = self._theme.currentData()
        self._orig_zoom = zoom
        self._orig_dyslexic = want_font

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
        self.reject()
