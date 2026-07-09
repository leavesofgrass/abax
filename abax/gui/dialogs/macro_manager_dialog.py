"""Macro manager — a central panel to view and run every available macro.

Lists every macro the window knows about in one place: the command macros
registered in ``window._macro_registry`` (tagged *macro*) and the entries the
user wired into ``window.user_config.macro_menu`` from their ``init.py`` (tagged
*init.py*). Select one to read its description, then **Run** it — registry
macros go through ``window._run_macro`` (out-of-process, like everywhere else),
init.py entries call their own ``.action(window)`` callable.

**Load file…** reuses the window's macro loader (file picker + consent gate)
and refreshes; **Open macros folder** reveals ``CONFIG_DIR/macros`` in the OS
file manager so users can drop ``.py`` files there. The panel is defensive: no
registry or an empty list shows a "no macros" note and disables Run, and a
macro that raises on Run is caught and surfaced in the status line rather than
crashing the GUI.
"""

from __future__ import annotations

import os

from .._qtcompat import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

# QDesktopServices / QUrl are not re-exported by _qtcompat, so "Open macros
# folder" falls back to os.startfile on Windows (see _open_macros_folder).
try:  # pragma: no cover - depends on which names _qtcompat exports
    from .._qtcompat import QDesktopServices, QUrl  # type: ignore

    _HAVE_DESKTOP_SERVICES = True
except ImportError:  # pragma: no cover
    QDesktopServices = None  # type: ignore
    QUrl = None  # type: ignore
    _HAVE_DESKTOP_SERVICES = False


def _first_doc_line(fn) -> str:
    """First non-blank line of a callable's docstring, or a stand-in."""
    doc = (getattr(fn, "__doc__", None) or "").strip()
    if not doc:
        return "(no description)"
    return doc.splitlines()[0].strip()


class MacroManagerDialog(QDialog):
    """View and run every macro known to the window from a single panel."""

    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        # Rows currently shown, parallel to the list widget: each is
        # (name, source, description, runner) where runner() executes it.
        self._rows: list[tuple[str, str, str, object]] = []
        self.setWindowTitle("Macro manager")
        self.resize(560, 460)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        root = QVBoxLayout(self)

        root.addWidget(QLabel("Macros:", self))
        self._list = QListWidget(self)
        self._list.currentRowChanged.connect(self._on_selection)
        self._list.itemDoubleClicked.connect(lambda _i: self.run_selected())
        root.addWidget(self._list, 1)

        self._desc = QPlainTextEdit(self)
        self._desc.setReadOnly(True)
        self._desc.setMaximumHeight(90)
        self._desc.setPlaceholderText("Select a macro to see its description.")
        root.addWidget(self._desc)

        bar = QHBoxLayout()
        self._run_btn = QPushButton("Run", self)
        self._run_btn.clicked.connect(self.run_selected)
        load_btn = QPushButton("Load file…", self)
        load_btn.clicked.connect(self._load_file)
        folder_btn = QPushButton("Open macros folder", self)
        folder_btn.clicked.connect(self._open_macros_folder)
        close_btn = QPushButton("Close", self)
        close_btn.clicked.connect(self.reject)
        bar.addWidget(self._run_btn)
        bar.addWidget(load_btn)
        bar.addWidget(folder_btn)
        bar.addStretch(1)
        bar.addWidget(close_btn)
        root.addLayout(bar)

        self._status = QLabel("", self)
        root.addWidget(self._status)

    # ------------------------------------------------------------------ #
    def _gather(self) -> list[tuple[str, str, str, object]]:
        """Build the (name, source, description, runner) rows to display."""
        rows: list[tuple[str, str, str, object]] = []

        registry = getattr(self._win, "_macro_registry", None)
        macros = getattr(registry, "macros", None) or {}
        for name in sorted(macros):
            fn = macros[name]
            desc = _first_doc_line(fn)
            rows.append((name, "macro", desc, self._make_registry_runner(name)))

        user_config = getattr(self._win, "user_config", None)
        menu = getattr(user_config, "macro_menu", None) or []
        for entry in menu:
            name = getattr(entry, "name", "") or "(unnamed)"
            desc = (getattr(entry, "desc", "") or "").strip() or "(no description)"
            rows.append((name, "init.py", desc, self._make_entry_runner(entry)))

        return rows

    def _make_registry_runner(self, name: str):
        return lambda: self._win._run_macro(name)

    def _make_entry_runner(self, entry):
        def _run() -> None:
            action = getattr(entry, "action", None)
            if action is None:
                raise RuntimeError(f"init.py entry {getattr(entry, 'name', '?')!r} has no action")
            action(self._win)

        return _run

    def refresh(self) -> None:
        """Re-read the registry and init.py menu and repopulate the list."""
        self._rows = self._gather()
        self._list.clear()
        for name, source, _desc, _runner in self._rows:
            self._list.addItem(f"{name}    [{source}]")
        self._desc.setPlainText("")
        if self._rows:
            self._list.setCurrentRow(0)
            self._run_btn.setEnabled(True)
            self._status.setText(f"{len(self._rows)} macro(s)")
        else:
            self._run_btn.setEnabled(False)
            self._status.setText("no macros — load a macro file or drop one in the macros folder")

    # ------------------------------------------------------------------ #
    def _on_selection(self, row: int) -> None:
        if 0 <= row < len(self._rows):
            self._desc.setPlainText(self._rows[row][2])
        else:
            self._desc.setPlainText("")

    def _current(self) -> tuple[str, str, str, object] | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def run_selected(self) -> None:
        """Run the selected macro, catching and surfacing any error."""
        current = self._current()
        if current is None:
            self._status.setText("nothing selected")
            return
        name, source, _desc, runner = current
        try:
            runner()
        except Exception as exc:  # never let a bad macro crash the GUI
            self._status.setText(f"error running {name!r}: {exc}")
            return
        self._status.setText(f"ran {source} macro {name!r}")

    # ------------------------------------------------------------------ #
    def _load_file(self) -> None:
        loader = getattr(self._win, "load_macros", None)
        if callable(loader):
            loader()
        self.refresh()

    def _open_macros_folder(self):
        from .. import _qtcompat  # noqa: F401 - kept for parity with imports
        from ... import _runtime

        path = _runtime.CONFIG_DIR / "macros"
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if _HAVE_DESKTOP_SERVICES:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            self._status.setText(f"opened {path}")
            return
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]  # Windows only
            self._status.setText(f"opened {path}")
        except (AttributeError, OSError) as exc:
            # Non-Windows or no handler — surface the path, don't crash.
            self._status.setText(f"macros folder: {path} ({exc})")

    # ------------------------------------------------------------------ #
    def _macro_names(self) -> list[tuple[str, str]]:
        """Testable seam: the (name, source) pairs currently shown."""
        return [(name, source) for name, source, _desc, _runner in self._rows]
