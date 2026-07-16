"""ViewMixin — Appearance and window chrome: theme, UI font/zoom, vim mode, toolbar, docks."""

from __future__ import annotations

from .theming import apply_theme, theme_for


class ViewMixin:
    def apply_current_theme(self) -> None:
        from ._qtcompat import QApplication

        name = getattr(self._settings, "theme", "galaxy")
        theme = theme_for(name)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, name, theme.tokens(),
                        self._base_font_qss() + self._ui_font_qss() + self._zoom_qss()
                        + self._menu_qss())
        self._theme = theme  # custom-painted surfaces read this
        # Re-tint the hand-drawn icons to the theme fg. They're QPainter glyphs
        # baked into each QAction at build time, so a stylesheet can't recolour
        # them — regenerate every registered icon (see gui/icons.py).
        from . import icons as _icons
        _icons.set_icon_color(theme.q_color("fg_primary"))
        for _iact, _iname in getattr(self, "_icon_actions", ()):
            _iact.setIcon(_icons.make_icon(_iname))
        self._update_status_cluster()

    def _base_font_qss(self) -> str:
        """A known-good UI font family for the chrome when the dyslexia font is OFF.

        The theme ``.qss`` sets ``font-size`` with no ``font-family``, so on some
        setups Qt resolves the menu/list font to a poorly-hinted fallback that
        renders even ASCII text with overlapping metrics. Pin an explicit
        sans-serif stack (Qt picks the first present; ``sans-serif`` backstops every
        platform). Skipped when OpenDyslexic is active — there ``app.setFont`` and
        ``_ui_font_qss`` govern. Deliberately excludes the monospace console/terminal
        (``QPlainTextEdit``/``QTextEdit``) and the QPainter calculator faceplates.
        """
        if getattr(self, "_ui_font_family", ""):
            return ""
        fam = ('"Segoe UI", "Helvetica Neue", "Cantarell", "DejaVu Sans", '
               '"Noto Sans", "Arial", sans-serif')
        return ("\nQMenuBar, QMenu, QStatusBar, QToolBar, QTabBar, QHeaderView, QLabel, "
                "QPushButton, QToolButton, QCheckBox, QRadioButton, QLineEdit, QComboBox, "
                "QSpinBox, QListWidget, QListView, QTreeView, QGroupBox, QMessageBox "
                f"{{ font-family: {fam}; }}\n")

    def _ui_font_qss(self) -> str:
        """Stylesheet layer forcing the dyslexia font on text-heavy widgets (cells,
        console, terminal, lists) when enabled — applied over the theme.

        A stylesheet beats ``setFont()``, so this reaches widgets that set their own
        font (the terminal/console). ``QLabel`` and the QPainter-drawn calculator
        faceplates are deliberately excluded, so the LCD/keypad keep their display
        fonts.
        """
        fam = getattr(self, "_ui_font_family", "")
        if not fam:
            return ""
        return ("\nQAbstractItemView, QHeaderView, QTableView, QTableWidget, "
                "QListView, QTreeView, QPlainTextEdit, QTextEdit "
                f'{{ font-family: "{fam}"; }}\n')

    def _menu_qss(self) -> str:
        """Give ``QMenu`` items explicit padding so labels and their right-aligned
        shortcuts both fit — **on Windows only**.

        Styling ``QMenu`` / ``QMenu::item:selected`` in the theme ``.qss`` routes
        menu rendering through Qt's stylesheet style, whose item metrics differ by
        base style. On the **windows11** style that under-sizes the item by a few
        px, clipping the shortcut on items with wide ones (e.g. *Sheet* →
        ``Ctrl+PgDown``, ``Shift+F11``; *Help* → ``F1``); explicit horizontal
        padding restores comfortable width. On the **Fusion** style (Linux/macOS)
        menus already size correctly *and* item padding there drops the shortcut
        column — so the rule is scoped to Windows to avoid regressing them.
        """
        import sys

        if sys.platform != "win32":
            return ""
        return ("\nQMenu::item { padding: 4px 18px; }\n"
                "QMenu::separator { height: 1px; margin: 4px 8px; }\n")

    def _zoom_qss(self) -> str:
        """Stylesheet layer scaling the base font size by ``settings.zoom``. The
        theme .qss sets ``font-size`` on the base selector, so zoom must go through
        the stylesheet (a ``setFont`` would be overridden)."""
        z = float(getattr(self._settings, "zoom", 1.0) or 1.0)
        if abs(z - 1.0) < 1e-6:
            return ""
        return f"\n* {{ font-size: {max(6, round(13 * z))}px; }}\n"

    def _set_zoom(self, z: float) -> None:
        z = max(0.5, min(3.0, round(z, 1)))
        self._settings.zoom = z
        self.apply_current_theme()
        self._set_status(f"zoom {int(z * 100)}%")

    def zoom_in(self) -> None:
        self._set_zoom(float(getattr(self._settings, "zoom", 1.0) or 1.0) + 0.1)

    def zoom_out(self) -> None:
        self._set_zoom(float(getattr(self._settings, "zoom", 1.0) or 1.0) - 0.1)

    def reset_zoom(self) -> None:
        self._set_zoom(1.0)

    def choose_theme(self) -> None:
        from .dialogs.theme_dialog import ThemeDialog

        ThemeDialog(self).exec()

    def show_preferences(self) -> None:
        """Open the Preferences dialog (theme, font, zoom, autosave, isolation)."""
        from .dialogs.preferences_dialog import PreferencesDialog

        PreferencesDialog(self).exec()

    def set_theme(self, name: str) -> None:
        self._settings.theme = name
        self.apply_current_theme()
        self._set_status(f"theme: {name}")

    def set_vim_mode(self, on: bool) -> None:
        self._settings.vim_mode = bool(on)
        self._set_status(f"vim mode: {'on' if on else 'off'}")
        self._update_status_cluster()

    def toggle_vim_mode(self) -> None:
        self.set_vim_mode(not getattr(self._settings, "vim_mode", True))

    def set_toolbar_visible(self, on: bool) -> None:
        tb = getattr(self, "_toolbar", None)
        if tb is None:
            return
        tb.setVisible(bool(on))
        self._settings.show_toolbar = bool(on)
        act = getattr(self, "_act_toolbar", None)   # keep the View-menu check in sync
        if act is not None and act.isChecked() != bool(on):
            act.setChecked(bool(on))
        self._set_status(f"toolbar {'shown' if on else 'hidden'}")

    def toggle_toolbar(self) -> None:
        tb = getattr(self, "_toolbar", None)
        self.set_toolbar_visible(not tb.isVisible() if tb is not None else True)

    def apply_dyslexic_font(self, on: bool, fetch: bool = True) -> None:
        from ._qtcompat import QApplication, QFont, QFontDatabase
        from ..core import fonts as fontmod

        app = QApplication.instance()
        if not on:
            self._ui_font_family = ""
            if app is not None:
                app.setFont(QFont())
            self._settings.dyslexic_font = False
            self.apply_current_theme()           # drop the font layer from the QSS
            if getattr(self, "_model", None) is not None:
                self.refresh_table()             # re-query cell FontRole
            self._set_status("default font")
            return
        paths = fontmod.fetched_paths()
        if not paths and fetch:
            self._set_status("fetching OpenDyslexic...")
            paths = fontmod.fetch()
        if not paths:
            self._set_status("OpenDyslexic unavailable (offline?)")
            return
        family = None
        for p in paths:
            fid = QFontDatabase.addApplicationFont(str(p))
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams:
                family = fams[0]
        if family and app is not None:
            app.setFont(QFont(family, 11))          # menus, dialogs, buttons, labels
            self._ui_font_family = family
            self._settings.dyslexic_font = True
            self.apply_current_theme()              # + console, terminal, lists
            if getattr(self, "_model", None) is not None:
                self.refresh_table()                # cells pick up the family via FontRole
            self._set_status(f"font: {family} (applied across the UI)")

    def toggle_dyslexic_font(self) -> None:
        self.apply_dyslexic_font(not getattr(self._settings, "dyslexic_font", False))

    def _show_dock(self, attr: str, title: str, build_content, area):
        """Create (once) a movable/floatable QDockWidget panel and show it."""
        from ._qtcompat import QDockWidget, Qt

        dock = getattr(self, attr, None)
        if dock is None:
            dock = QDockWidget(title, self)
            dock.setObjectName(title.replace(" ", "_"))
            dock.setWidget(build_content())
            dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
            dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                | QDockWidget.DockWidgetFeature.DockWidgetClosable)
            self.addDockWidget(area, dock)
            setattr(self, attr, dock)
        dock.show()
        dock.raise_()
        return dock
