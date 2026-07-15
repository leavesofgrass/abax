"""Shared TUI session setup — front-end-agnostic.

Both front-ends (the curses :mod:`~abax.tui.app` and the Textual
:mod:`~abax.tui.textual_app`) need the same preamble: load settings, honour the
first-run dependency prompt and the persisted live-data / external-ref consent,
open the document under the windowing policy, and build the :class:`TuiEditor`
with the accessibility flags and theme applied. This module is the single source
of that wiring so the two entry points can never drift.
"""

from __future__ import annotations


def build_session(file: str | None = None, registry=None, *, announce_deps: bool = True):
    """Build the :class:`~abax.tui.editor.TuiEditor` for a TUI session.

    ``announce_deps`` prints the one-time optional-dependency hint on first run
    (the curses front-end does this before taking over the screen); a front-end
    that would rather not print to the raw terminal can pass ``False``. Returns
    the ready-to-drive editor.
    """
    from .editor import TuiEditor
    from .themes import THEMES
    from .. import _runtime as rt
    from ..engine.document import Document
    from ..settings import load_settings

    settings = load_settings(rt.CONFIG_DIR / "settings.json")

    # First run: point the user at their choices instead of silently installing.
    from .. import autodeps
    autodeps.set_enabled(getattr(settings, "auto_install", True))
    if announce_deps and autodeps.enabled() and not getattr(settings, "deps_prompted", False):
        print("abax: optional features (data science, Excel/Parquet, Jupyter, "
              "terminal) are not installed yet.")
        print("  Install everything:  abax deps        (or launch the GUI for a "
              "chooser)")
        print("  Pick specific ones:  pip install abax[science]  /  [excel]  /  "
              "[jupyter]  ...")
        settings.deps_prompted = True
        try:
            from ..settings import save_settings
            save_settings(settings, rt.CONFIG_DIR / "settings.json")
        except Exception:
            pass

    # Honour the persisted live-data consent so REST/WEBSOCKET formulas work in
    # the TUI too (off unless the user opted in; a loaded file can't phone home).
    from ..core.externref import HUB as EXT
    from ..core.livedata import HUB
    HUB.set_enabled(bool(getattr(settings, "live_data_enabled", False)))
    EXT.set_enabled(bool(getattr(settings, "external_refs_enabled", False)))

    doc = (Document.open(file, windowed_capacity=getattr(settings, "windowed_store_capacity", 0))
           if file else Document())
    # Anchor external-ref paths at the open workbook's directory.
    EXT.set_base_dir(doc.path.parent if getattr(doc, "path", None) else None)
    editor = TuiEditor(doc, registry, settings)
    theme_name = getattr(settings, "tui_theme", "obsidian")
    editor.theme_name = theme_name if theme_name in THEMES else "obsidian"
    return editor
