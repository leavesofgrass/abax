"""GUI bootstrap: QApplication, excepthook, settings, theme, window.

Installs ``sys.excepthook`` at startup (Qt swallows worker exceptions) and
performs an emergency settings flush on uncaught errors (spec §8).
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("qcell.gui")


# The data-science / biostatistics stack auto-installed on first GUI run.
# Split into groups so a failure of a heavy/optional one doesn't block the rest.
_SCI_STACK = [
    ["numpy", "pandas", "scipy"],            # core
    ["pyarrow"],                             # Parquet / Feather IO
    ["statsmodels", "scikit-learn"],         # stats + ML
    ["pingouin"],                            # effect-size statistics
    ["lifelines", "scikit-survival"],        # survival analysis (biostatistics)
    ["pymc"],                                # probabilistic programming (heavy; last)
]


def _ensure_scientific_stack() -> None:
    """Best-effort, once-per-machine background install of the data-science stack.

    No-op if pandas is already importable. Installs numpy/pandas/scipy/statsmodels/
    scikit-learn/lifelines in a daemon thread so startup never blocks; a marker file
    in CACHE_DIR ensures it's only attempted once. Silent on any failure.
    """
    import importlib.util

    if importlib.util.find_spec("pandas") is not None:
        return
    try:
        from .. import _runtime as rt

        marker = rt.CACHE_DIR / "scistack_install_attempted"
        if marker.exists():
            return
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except Exception:
        return

    def _install() -> None:
        import subprocess

        for group in _SCI_STACK:
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet", *group],
                    capture_output=True, timeout=1200)
            except Exception:
                pass

    import threading

    threading.Thread(target=_install, daemon=True).start()


def run_gui(file: str | None = None, registry=None) -> int:
    from .. import _runtime as rt

    if not rt._HAS_QT:
        print(
            "PyQt6 is not installed. Install it with:  pip install qcell[gui]\n"
            "or use the TUI:  qcell tui",
            file=sys.stderr,
        )
        return 1

    from ._qtcompat import QApplication
    from .main_window import MainWindow
    from ..settings import load_settings, save_settings
    from ..state import StateManager

    settings = load_settings(rt.CONFIG_DIR / "settings.json")
    state = StateManager.load(rt.DATA_DIR / "state.json")
    _ensure_scientific_stack()   # best-effort one-time background install (no-op if present)

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
    app.setApplicationName("qcell")
    window = MainWindow(settings, state, registry)
    if file:
        window.open_document(file)
    window.show()
    # Launch to a clean grid: the calculator, console, and terminal are opened on
    # demand (shortcuts or View → Open default workspace), so a first run isn't a
    # pile of panels — and the code-execution consent prompt only appears when the
    # user actually opens the console/terminal.
    try:
        rc = app.exec()
    finally:
        save_settings(settings, rt.CONFIG_DIR / "settings.json")
        state.flush()
    return rc
