"""GUI bootstrap: QApplication, excepthook, settings, theme, window.

Installs ``sys.excepthook`` at startup (Qt swallows worker exceptions) and
performs an emergency settings flush on uncaught errors (spec §8).
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("abax.gui")


def run_gui(file: str | None = None, registry=None) -> int:
    from .. import _runtime as rt

    if not rt._HAS_QT:
        print(
            "PyQt6 is not installed. Install it with:  pip install abax[gui]\n"
            "or use the TUI:  abax tui",
            file=sys.stderr,
        )
        return 1

    from ._qtcompat import QApplication
    from .main_window import MainWindow
    from ..settings import load_settings, save_settings
    from ..state import StateManager

    settings = load_settings(rt.CONFIG_DIR / "settings.json")
    state = StateManager.load(rt.DATA_DIR / "state.json")

    # Optional dependencies are fetched on demand (best-effort, background). On the
    # very first launch abax asks the user what to install via a chooser (Thin /
    # All / custom) — see below, after the window is shown; honors the auto_install
    # setting and ABAX_NO_AUTOINSTALL.
    from .. import autodeps
    autodeps.set_enabled(settings.auto_install)

    def _excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))
        try:
            save_settings(settings, rt.CONFIG_DIR / "settings.json")
            state.flush()
        except Exception:
            pass
        sys.exit(1)

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setApplicationName("abax")
    window = MainWindow(settings, state, registry)
    if file:
        window.open_document(file)
    window.show()
    # First launch: ask which optional features to install (Thin / All / custom).
    from .dialogs.deps_dialog import maybe_prompt
    maybe_prompt(window)
    # Launch to a clean grid: the calculator, console, and terminal are opened on
    # demand (shortcuts or View -> Open default workspace), so a first run isn't a
    # pile of panels — and the code-execution consent prompt only appears when the
    # user actually opens the console/terminal.
    try:
        rc = app.exec()
    finally:
        save_settings(settings, rt.CONFIG_DIR / "settings.json")
        state.flush()
    return rc
