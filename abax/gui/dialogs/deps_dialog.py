"""First-run optional-feature chooser.

abax's core is stdlib-only; the heavier capabilities are optional packages. Rather
than silently installing everything, this dialog explains each feature group, offers
two common presets (**Thin** and **All**), and lets the user pick exactly what to
fetch. It's shown once on first launch and re-openable from *Tools → Install
optional features*. Installation itself is delegated to
:mod:`abax.autodeps` (background, best-effort).
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from ... import autodeps


class DependencyChooser(QDialog):
    def __init__(self, window=None) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("abax — optional features")
        self.resize(560, 520)
        self._boxes: dict[str, QCheckBox] = {}
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        intro = QLabel(
            "<b>abax is already complete.</b> The keyboard-first spreadsheet, 600+ "
            "formula functions, statistics, calculators, and the RF tools all work "
            "right now with no extra packages.<br><br>"
            "The features below are <b>optional</b> add-ons — each fetches a few "
            "Python packages to unlock a capability (Excel files, the data-science "
            "stack, Jupyter…). <b>Nothing is selected by default</b>; pick only what "
            "you want. You can reopen this any time from "
            "<i>Tools → Install optional features</i> or <i>Preferences → System</i>, "
            "so adding more later is easy.<br><br>"
            "Shortcuts:&nbsp; <b>Thin</b> — the lightweight everyday conveniences."
            "&nbsp; <b>All</b> — everything abax can use.", self)
        intro.setWordWrap(True)
        root.addWidget(intro)

        presets = QHBoxLayout()
        thin = QPushButton("Thin  (~25 MB)", self)
        thin.setToolTip("Everyday conveniences only — Excel, terminal, richer TUI, "
                        "fast settings. No data-science or Jupyter stack.")
        thin.clicked.connect(lambda: self._apply_preset("thin"))
        allb = QPushButton("All  (~0.6 GB)", self)
        allb.setToolTip("Everything abax can use: the full data-science / ML "
                        "stack, Parquet, Jupyter, and Bayesian modeling.")
        allb.clicked.connect(lambda: self._apply_preset("all"))
        presets.addWidget(thin)
        presets.addWidget(allb)
        presets.addStretch(1)
        root.addLayout(presets)

        # one checkbox per feature, light -> heavy, with purpose + size + status
        grid = QWidget(self)
        col = QVBoxLayout(grid)
        col.setContentsMargins(4, 4, 4, 4)
        for key in autodeps.FEATURE_INFO:
            label, detail, mb = autodeps.FEATURE_INFO[key]
            present = all(autodeps.installed(mod)
                          for _pip, mod in autodeps.FEATURES.get(key, []))
            size = "installed" if present else (f"~{mb} MB" if mb < 1000 else
                                                f"~{mb / 1000:.1f} GB")
            cb = QCheckBox(f"{label}   ({size})", self)
            cb.setToolTip(detail)
            sub = QLabel(f"    {detail}", self)
            sub.setWordWrap(True)
            sub.setStyleSheet("color: gray; font-size: 11px;")
            if present:
                cb.setChecked(True)
                cb.setEnabled(False)                 # already there
            self._boxes[key] = cb
            col.addWidget(cb)
            col.addWidget(sub)
        col.addStretch(1)
        root.addWidget(grid, 1)

        actions = QHBoxLayout()
        actions.addStretch(1)
        later = QPushButton("Not now", self)
        later.clicked.connect(self._skip)
        install = QPushButton("Install selected", self)
        install.setDefault(True)
        install.clicked.connect(self._install)
        actions.addWidget(later)
        actions.addWidget(install)
        root.addLayout(actions)

        # Nothing is pre-selected: the base is complete and features are opt-in.
        # The Thin / All buttons make choosing a whole set a single click.

    # --- behaviour ------------------------------------------------------
    def _apply_preset(self, name: str) -> None:
        chosen = set(autodeps.preset(name))
        for key, cb in self._boxes.items():
            if cb.isEnabled():                       # don't touch already-installed
                cb.setChecked(key in chosen)

    def selected(self) -> list[str]:
        """Feature keys currently checked (whether enabled or already installed)."""
        return [k for k, cb in self._boxes.items() if cb.isChecked()]

    def _mark_prompted(self) -> None:
        settings = getattr(self._win, "_settings", None)
        if settings is None:
            return
        settings.deps_prompted = True
        try:
            from ... import _runtime as rt
            from ...settings import save_settings
            save_settings(settings, rt.CONFIG_DIR / "settings.json")
        except Exception:
            pass

    def done(self, result: int) -> None:  # noqa: N802 (Qt override)
        # One-shot, like the code-consent / terminal gate: however the chooser is
        # dismissed — Install, Skip, Esc, or the window's close button — don't
        # auto-open it again. It stays reachable on demand via
        # Tools -> Install optional features.
        self._mark_prompted()
        super().done(result)

    def _install(self) -> list[str]:
        autodeps.set_enabled(True)
        started: list[str] = []
        for key in self.selected():
            started += autodeps.ensure_feature(key)
        if self._win is not None and hasattr(self._win, "_set_status"):
            if started:
                self._win._set_status(
                    f"installing {len(started)} optional package(s) in the "
                    "background...")
            else:
                self._win._set_status("selected optional features already installed")
        self.accept()
        return started

    def _skip(self) -> None:
        self.reject()                                # done() marks it prompted


def maybe_prompt(window) -> None:
    """Show the chooser once, on first launch (unless auto-install is disabled)."""
    settings = getattr(window, "_settings", None)
    if settings is None:
        return
    if getattr(settings, "deps_prompted", False) or not getattr(
            settings, "auto_install", True):
        return
    DependencyChooser(window).exec()
