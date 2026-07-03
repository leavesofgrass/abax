"""MainWindow — composes the mixins and owns the shared widgets.

Mixin order matters only for MRO; no mixin calls another (spec §2). The window
sets up: a formula bar, the cell grid, the status bar, menu actions with the
mandatory keybindings, and a 30s autosave timer.
"""

from __future__ import annotations

from ._qtcompat import (
    QAction,
    QKeySequence,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QStatusBar,
    Qt,
    QTabBar,
    QTimer,
    QVBoxLayout,
    QWidget,
)
from .mixin_document import DocumentMixin
from .mixin_io import DocumentIOMixin
from .mixin_navigation import NavigationMixin
from .mixin_settings import SettingsMixin
from ..core.reference import to_a1


def _as_number(val) -> float | None:
    """Coerce a computed cell value to a float for status-bar aggregates.

    Booleans and error values are not counted as numbers (Excel-like)."""
    if isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fmt_num(x: float) -> str:
    """Compact numeric formatting: integers print plainly, else ~6 sig figs."""
    if x == int(x) and abs(x) < 1e15:
        return f"{int(x):,}"
    return f"{x:,.6g}"


class MainWindow(NavigationMixin, DocumentMixin, DocumentIOMixin, SettingsMixin, QMainWindow):
    def __init__(self, settings, state=None, registry=None) -> None:
        super().__init__()
        self._settings = settings
        self._state = state
        self._macro_registry = registry
        self._theme = None
        self._icon_actions: list = []   # (QAction, glyph name) — re-tinted on theme change
        # Pin the icon tint to the theme fg up front so menus/toolbar build with
        # theme-correct glyphs (not the OS palette); apply_current_theme re-tints.
        from . import icons as _icons
        from .theming import theme_for as _theme_for
        _icons.set_icon_color(
            _theme_for(getattr(self._settings, "theme", "obsidian")).q_color("fg_primary"))
        from ..core.clipboard import ClipboardManager
        from ..engine.document import Document
        from ..recorder import MacroRecorder

        self._doc = Document()
        self._recorder = MacroRecorder()
        self._clip = None  # last copied region (core.fill.Clip)
        self._clipboard = ClipboardManager()  # text/copy history
        self._setup_ui()
        from .grid.frozen_panes import FrozenPanes
        from .grid.grid_view import GridDelegate

        self._frozen = FrozenPanes(self)
        self._table.setItemDelegate(GridDelegate(self))
        self._setup_menus()
        self._setup_toolbar()
        self.apply_current_theme()
        if getattr(self._settings, "dyslexic_font", False):
            self.apply_dyslexic_font(True, fetch=False)
        self.refresh_table()
        self._update_title()
        self._start_autosave()
        self._update_status_cluster()
        self._restore_window_state()
        # The calculator is NOT auto-opened on launch — open it on demand (Ctrl+K).
        # Its model/style are still remembered for when it is opened.

    # --- construction -----------------------------------------------------

    def _setup_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        self._formula_bar = QLineEdit(self)
        self._formula_bar.setAccessibleName("Formula bar")
        self._formula_bar.setPlaceholderText("Enter value or =formula, press Enter")
        self._formula_bar.returnPressed.connect(self._commit_formula_bar)
        self._formula_bar.textChanged.connect(self._update_arg_hint)
        self._formula_bar.cursorPositionChanged.connect(lambda *_: self._update_arg_hint())
        from .completion import FormulaCompleter

        self._completer = FormulaCompleter(self._formula_bar, context=self._completion_context)
        layout.addWidget(self._formula_bar)

        from .grid.grid_model import AbaxTableModel
        from .grid.grid_view import CellTableView

        self._model = AbaxTableModel(self)
        self._table = CellTableView(self, self._model)
        self._table.setAccessibleName("Cell grid")
        self._table.setAlternatingRowColors(True)
        # Virtualized grid: the model reports a generous extent (used range plus
        # headroom) and the view renders only the viewport, so big files scroll
        # without materializing a widget per cell. These minimums still grow on
        # demand (append/scroll-to-edge) but never cap what is rendered.
        self._grid_min_rows = 200
        self._grid_min_cols = 26
        self._table.currentCellChanged.connect(self._on_current_cell_changed)
        # Excel-style status-bar readout (Sum/Avg/Count/...) for the live selection.
        self._table.selectionModel().selectionChanged.connect(
            lambda *_: self._update_selection_status())
        # Edits commit through AbaxTableModel.setData -> _commit_cell (below).
        self._table.verticalScrollBar().valueChanged.connect(self._maybe_grow_rows)
        self._table.horizontalScrollBar().valueChanged.connect(self._maybe_grow_cols)
        for header, handler in (
            (self._table.verticalHeader(), self._row_header_menu),
            (self._table.horizontalHeader(), self._column_header_menu),
        ):
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            header.customContextMenuRequested.connect(handler)
        # Right-click on the cells -> the sheet context menu (clipboard / structure /
        # formatting / data tools), wired to the same actions as the menu bar.
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._cell_context_menu)
        layout.addWidget(self._table)

        # Sheet tabs with a "+" add button and a right-click management menu.
        from ._qtcompat import QHBoxLayout, QPushButton

        self._tabs = QTabBar(self)
        self._tabs.setExpanding(False)
        self._tabs.setMovable(True)   # drag to reorder sheets
        self._tabs.setAccessibleName("Sheet tabs")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._tabs.tabMoved.connect(self._on_tab_moved)
        self._tabs.tabBarDoubleClicked.connect(lambda _i: self.rename_sheet())
        self._tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tabs.customContextMenuRequested.connect(self._sheet_tab_menu)
        add_sheet_btn = QPushButton("+", self)
        add_sheet_btn.setFixedWidth(26)
        add_sheet_btn.setToolTip("Add a sheet")
        add_sheet_btn.clicked.connect(self.insert_sheet)
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.addWidget(self._tabs)
        tab_row.addWidget(add_sheet_btn)
        tab_row.addStretch(1)
        tab_holder = QWidget(self)
        tab_holder.setLayout(tab_row)
        layout.addWidget(tab_holder)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar(self))
        # Compact progress bar in the status bar, shown only during async I/O.
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setMaximumWidth(160)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        self.statusBar().addPermanentWidget(self._progress)
        # State cluster on the right: vim mode - theme - saved/unsaved.
        from ._qtcompat import QLabel

        self._sb_vim = QLabel("", self)
        self._sb_theme = QLabel("", self)
        self._sb_dirty = QLabel("", self)
        for w, nm in ((self._sb_vim, "vim mode"), (self._sb_theme, "theme"),
                      (self._sb_dirty, "saved state")):
            w.setAccessibleName(nm)
            w.setStyleSheet("padding:0 8px;")
            self.statusBar().addPermanentWidget(w)
        self.resize(900, 600)

    # a soft palette so sheet tabs are visually distinguishable
    _TAB_COLORS = ["#7fb6e8", "#a3d977", "#e8b06a", "#d98fb0", "#9b8fe8",
                   "#6fd0c0", "#e87f7f", "#c0c060"]

    def _rebuild_tabs(self) -> None:
        from ._qtcompat import QColor

        self._tabs.blockSignals(True)
        while self._tabs.count():
            self._tabs.removeTab(0)
        for i, s in enumerate(self._doc.workbook.sheets):
            self._tabs.addTab(s.name)
            self._tabs.setTabTextColor(i, QColor(self._TAB_COLORS[i % len(self._TAB_COLORS)]))
        self._tabs.setCurrentIndex(self._doc.workbook.active)
        self._tabs.blockSignals(False)

    def _on_tab_moved(self, frm: int, to: int) -> None:
        """Keep the workbook's sheet order in sync when a tab is dragged."""
        wb = self._doc.workbook
        if not (0 <= frm < len(wb.sheets) and 0 <= to < len(wb.sheets)):
            return
        active_name = wb.sheet.name
        sheet = wb.sheets.pop(frm)
        wb.sheets.insert(to, sheet)
        wb.active = wb.sheets.index(next(s for s in wb.sheets if s.name == active_name))
        self._doc.mark_dirty()
        self._rebuild_tabs()

    def _on_tab_changed(self, idx: int) -> None:
        wb = self._doc.workbook
        if 0 <= idx < len(wb.sheets) and idx != wb.active:
            wb.active = idx
            self.refresh_table()
            self._update_title()
            self._set_status(f"sheet: {wb.sheet.name}")

    def _sheet_tab_menu(self, pos) -> None:
        """Right-click a sheet tab -> add / rename / duplicate / delete."""
        from ._qtcompat import QMenu

        idx = self._tabs.tabAt(pos)
        menu = QMenu(self)
        menu.addAction("New sheet", self.insert_sheet)
        if idx >= 0:
            if idx != self._doc.workbook.active:
                self._doc.workbook.active = idx
                self.refresh_table()
                self._update_title()
            menu.addAction("Rename...", self.rename_sheet)
            menu.addAction("Duplicate", self.duplicate_sheet)
            menu.addSeparator()
            menu.addAction("Delete", self.delete_sheet)
        menu.exec(self._tabs.mapToGlobal(pos))

    def _act(self, menu, label: str, slot, shortcut: str | None = None):
        """Create a menu action (shortcuts use stable English strings)."""
        act = QAction(label, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        menu.addAction(act)
        return act

    def _reg_icon(self, action, name: str):
        """Set a persistent action's themed icon and register it so it re-tints
        when the theme changes (see ViewMixin.apply_current_theme)."""
        from .icons import make_icon

        action.setIcon(make_icon(name))
        self._icon_actions.append((action, name))
        return action

    def _setup_menus(self) -> None:
        """Menu bar organised by the standard desktop convention (File - Edit - View -
        Insert - Format - Data - Sheet - Tools - Help), grouped into short logical
        sections. Every action is also reachable by shortcut and the command palette."""
        from ..core.format.cellformat import FORMATS

        mb = self.menuBar()

        # --- File ---------------------------------------------------------
        m_file = mb.addMenu("&File")
        self._reg_icon(self._act(m_file, "&New", self.new_document, "Ctrl+N"), "new")
        self._reg_icon(self._act(m_file, "&Open...", lambda: self.open_document(None), "Ctrl+O"), "open")
        self._act(m_file, "Import &large CSV...", self.import_large_csv)
        self._act(m_file, "Import from &URL...", lambda: self.import_from_url(None))
        m_file.addSeparator()
        self._reg_icon(self._act(m_file, "&Save", lambda: self.save_document(None), "Ctrl+S"), "save")
        self._act(m_file, "Save &As...", self.save_document_as, "Ctrl+Shift+S")
        self._act(m_file, "Export as &HTML report...", self.export_html_report)
        m_file.addSeparator()
        self._act(m_file, "&Quit", self.close, "Ctrl+Q")

        # --- Edit (clipboard - fill - find) -------------------------------
        m_edit = mb.addMenu("&Edit")
        self._reg_icon(self._act(m_edit, "&Undo", self.undo_edit, "Ctrl+Z"), "undo")
        self._reg_icon(self._act(m_edit, "&Redo", self.redo_edit, "Ctrl+Y"), "redo")
        self._act(m_edit, "Undo &history...", self.show_undo_history, "Ctrl+Shift+Z")
        m_edit.addSeparator()
        self._reg_icon(self._act(m_edit, "Cu&t", self.cut_selection, "Ctrl+X"), "cut")
        self._reg_icon(self._act(m_edit, "&Copy", self.copy_selection, "Ctrl+C"), "copy")
        self._reg_icon(self._act(m_edit, "&Paste", self.paste_at_cursor, "Ctrl+V"), "paste")
        self._act(m_edit, "Clea&r (Del)", self._clear_selection)
        m_edit.addSeparator()
        self._reg_icon(self._act(m_edit, "Fill &Down", self.fill_down_selection, "Ctrl+D"), "fill_down")
        self._act(m_edit, "Fill &Right", self.fill_right_selection, "Ctrl+R")
        self._act(m_edit, "Fill &series", self._fill_series_selection)
        m_edit.addSeparator()
        self._reg_icon(self._act(m_edit, "&Find / Replace...", self.show_find_replace, "Ctrl+F"), "find")
        self._act(m_edit, "&Go to...", self.show_goto, "Ctrl+G")
        self._reg_icon(self._act(m_edit, "Command &Palette...", self.show_command_palette, "Ctrl+Shift+P"), "palette")
        m_edit.addSeparator()
        self._act(m_edit, "Pre&ferences...", self.show_preferences, "Ctrl+,")

        # --- View (freeze - panels - display) -----------------------------
        m_view = mb.addMenu("&View")
        m_freeze = m_view.addMenu("&Freeze panes")
        self._act(m_freeze, "Freeze panes (at cursor)", lambda: self._freeze(None))
        self._act(m_freeze, "Freeze top &row", lambda: self._freeze("row"))
        self._act(m_freeze, "Freeze first &column", lambda: self._freeze("col"))
        self._act(m_freeze, "&Unfreeze", lambda: self._freeze("none"))
        m_view.addSeparator()
        self._reg_icon(self._act(m_view, "&Calculator", self.toggle_calculator, "Ctrl+K"), "hp16c")
        self._act(m_view, "Get cell value -> calculator", self.cell_to_calc, "Ctrl+Shift+G")
        self._act(m_view, "Send calculator value -> cell", self.calc_to_cells, "Ctrl+Shift+H")
        self._reg_icon(self._act(m_view, "&Terminal", self.show_terminal, "Ctrl+`"), "terminal")
        self._reg_icon(self._act(m_view, "&Python console", self.show_pyconsole, "Ctrl+Shift+Y"), "python")
        self._act(m_view, "Clip&board history", self.show_clipboard, "Ctrl+Shift+V")
        self._act(m_view, "Manage clip&board...", self.manage_clipboard)
        self._act(m_view, "Open default &workspace", self.open_default_workspace)
        m_view.addSeparator()
        act_tb = self._act(m_view, "Show &toolbar", self.toggle_toolbar)
        act_tb.setCheckable(True)
        act_tb.setChecked(getattr(self._settings, "show_toolbar", True))
        self._act_toolbar = act_tb   # kept so set_toolbar_visible can sync the check state
        m_view.addSeparator()
        self._act(m_view, "Show formula &precedents", self.show_precedents, "Ctrl+[")
        m_view.addSeparator()
        self._act(m_view, "Toggle &vim mode", self.toggle_vim_mode)
        self._act(m_view, "Toggle &OpenDyslexic font", self.toggle_dyslexic_font)
        m_view.addSeparator()
        self._act(m_view, "Zoom &in", self.zoom_in, "Ctrl+=")
        self._act(m_view, "Zoom &out", self.zoom_out, "Ctrl+-")
        self._act(m_view, "&Reset zoom", self.reset_zoom, "Ctrl+0")

        # --- Insert (rows/cols - objects) ---------------------------------
        m_insert = mb.addMenu("&Insert")
        m_rows = m_insert.addMenu("&Rows / columns")
        self._reg_icon(self._act(m_rows, "Row &above", lambda: self.insert_row(above=True), "Ctrl++"), "insert_row_above")
        self._reg_icon(self._act(m_rows, "Row &below", lambda: self.insert_row(above=False)), "insert_row_below")
        self._reg_icon(self._act(m_rows, "Column &left", lambda: self.insert_column(left=True)), "insert_col_left")
        self._reg_icon(self._act(m_rows, "Column &right", lambda: self.insert_column(left=False)), "insert_col_right")
        m_rows.addSeparator()
        self._act(m_rows, "Append row (end)", self.append_row)
        self._act(m_rows, "Append column (end)", self.append_column)
        m_rows.addSeparator()
        self._reg_icon(self._act(m_rows, "&Delete row(s)", self.delete_row, "Ctrl+-"), "delete_row")
        self._reg_icon(self._act(m_rows, "Delete &column(s)", self.delete_column), "delete_col")
        m_insert.addSeparator()
        self._act(m_insert, "&Function...", self.show_formula_browser, "Shift+F3")
        self._reg_icon(self._act(m_insert, "&Equation...", self.show_equation), "equation")
        self._reg_icon(self._act(m_insert, "C&hart / graph...", self.show_graph), "graph")
        self._act(m_insert, "Export chart as &SVG...", self.export_chart_svg)

        # --- Format (font - alignment - number - theme) -------------------
        m_format = mb.addMenu("F&ormat")
        self._reg_icon(self._act(m_format, "&Bold", lambda: self.toggle_style("bold"), "Ctrl+B"), "bold")
        self._reg_icon(self._act(m_format, "&Italic", lambda: self.toggle_style("italic"), "Ctrl+I"), "italic")
        self._reg_icon(self._act(m_format, "&Underline", lambda: self.toggle_style("underline"), "Ctrl+U"), "underline")
        m_align = m_format.addMenu("&Align")
        self._reg_icon(self._act(m_align, "&Left", lambda: self.set_alignment("left")), "align_left")
        self._reg_icon(self._act(m_align, "&Center", lambda: self.set_alignment("center")), "align_center")
        self._reg_icon(self._act(m_align, "&Right", lambda: self.set_alignment("right")), "align_right")
        self._reg_icon(self._act(m_format, "&Text colour...", self.pick_text_color), "text_color")
        self._reg_icon(self._act(m_format, "&Fill colour...", self.pick_fill_color), "fill_color")
        self._act(m_format, "Clear cell st&yles", self.clear_styles)
        m_format.addSeparator()
        m_num = m_format.addMenu("&Number")
        for spec, label in FORMATS:
            self._act(m_num, label, lambda checked=False, s=spec: self.set_number_format(s))
        self._reg_icon(self._act(m_format, "&Conditional format...", self.add_conditional_format), "condformat")
        self._act(m_format, "Clear conditional formats", self.clear_conditional_formats)
        m_format.addSeparator()
        m_theme = m_format.addMenu("&Theme")
        for label, key in [
            ("Obsidian", "obsidian"), ("Dark One", "dark_one"), ("Nord", "nord"),
            ("Solarized", "solarized"), ("CRT green", "crt_green"),
            ("CRT amber", "crt_amber"), ("Light", "light"),
            ("High contrast", "high_contrast"),
        ]:
            self._act(m_theme, label, lambda checked=False, k=key: self.set_theme(k))
        self._act(m_format, "Choose th&eme...", self.choose_theme, "Ctrl+T")

        # --- Data (sort/filter - names - recalc - analyze) ----------------
        m_data = mb.addMenu("&Data")
        self._reg_icon(self._act(m_data, "&Sort...", self.show_sort_dialog), "sort")
        self._act(m_data, "Sort &ascending", lambda: self._sort_selection(False))
        self._act(m_data, "Sort &descending", lambda: self._sort_selection(True))
        self._reg_icon(self._act(m_data, "&Filter...", self.show_filter_dialog), "filter")
        self._act(m_data, "Clear filter", self.clear_filter)
        m_data.addSeparator()
        self._act(m_data, "&Name range...", self.define_name)
        self._act(m_data, "Name &manager...", self.show_name_manager)
        self._act(m_data, "Data &validation...", self.show_validation_dialog)
        self._act(m_data, "&Compare workbook...", self.compare_workbook)
        m_data.addSeparator()
        self._act(m_data, "&Recalculate", self._recalculate, "F9")
        self._act(m_data, "Recalculate &sheet", self._recalculate_sheet, "Shift+F9")
        self._act(m_data, "Calculation: auto / &manual", self._toggle_calc_mode)
        m_data.addSeparator()
        m_analyze = m_data.addMenu("&Analyze")
        self._reg_icon(self._act(m_analyze, "&Descriptive Statistics...", self.show_describe), "histogram")
        self._act(m_analyze, "&Statistics / analysis...", self.show_stats_tool)
        self._act(m_analyze, "&SQL query...", self.show_sql_query)
        self._reg_icon(self._act(m_analyze, "&Profile columns", self.profile_columns), "stats")
        self._act(m_analyze, "Open selection in &pandas...", self.show_dataframe)
        self._act(m_analyze, "&Recode / clean column...", self.show_recode)
        self._act(m_analyze, "Pi&vot / group-by...", self.show_pivot)
        self._act(m_analyze, "&Curve fit...", self.show_curve_fit)
        m_analyze.addSeparator()
        self._act(m_analyze, "&Goal seek...", self.show_goal_seek)

        # --- Sheet (multi-sheet management) -------------------------------
        m_sheet = mb.addMenu("S&heet")
        self._reg_icon(self._act(m_sheet, "&New sheet", self.insert_sheet, "Shift+F11"), "sheets")
        self._act(m_sheet, "&Duplicate sheet", self.duplicate_sheet)
        self._act(m_sheet, "&Rename sheet...", self.rename_sheet)
        self._act(m_sheet, "De&lete sheet", self.delete_sheet)
        m_sheet.addSeparator()
        self._act(m_sheet, "Ne&xt sheet", self.next_sheet, "Ctrl+PgDown")
        self._act(m_sheet, "&Previous sheet", self.prev_sheet, "Ctrl+PgUp")

        # --- Tools (scientific - macros/scripts - calculator art) ---------
        m_tools = mb.addMenu("&Tools")
        m_sci = m_tools.addMenu("&Scientific")
        self._act(m_sci, "&Matrix tool...", self.show_matrix_tool)
        self._act(m_sci, "Numerical &solver...", self.show_solver)
        self._act(m_sci, "Si&gnal / data tool...", self.show_signal_tool)
        self._act(m_sci, "&ODE solver...", self.show_ode_solver)
        self._act(m_sci, "M&L tool (PCA / k-means / regression)...", self.show_ml_tool)
        m_tools.addSeparator()
        self._act(m_tools, "Install optional features now", self.install_optional_features)
        self._act(m_tools, "&Budget wizard...", self.show_budget_wizard)
        self._act(m_tools, "&File manager...", self.show_file_manager, "Ctrl+Shift+F")
        m_tools.addSeparator()
        self._macros_menu = m_tools.addMenu("&Macros")
        self._rebuild_macros_menu()
        m_rec = m_tools.addMenu("&Recording")
        self._act(m_rec, "Start/stop recording", self._toggle_recording)
        self._act(m_rec, "Start relative recording", self._start_relative_recording)
        self._act(m_rec, "Save recorded macro...", self._save_recording)
        self._act(m_rec, "Replay recording", self._replay_recording)
        self._act(m_tools, "&Load macro / UDF file...", self.load_macros)
        self._act(m_tools, "Run Python &script...", self.run_script)
        # Code-execution isolation (sandbox) level — checkable submenu.
        m_iso = m_tools.addMenu("Code &isolation (sandbox)")
        self._build_isolation_menu(m_iso)
        m_tools.addSeparator()

        # Radio (amateur / RF suite) — a Tools submenu.
        m_radio = m_tools.addMenu("&Radio")
        self._act(m_radio, "&RF toolkit...", self.show_rf_tool)
        self._act(m_radio, "Smith &chart...", self.show_smith_chart)
        self._act(m_radio, "&Antenna pattern...", self.show_antenna_pattern)
        self._act(m_radio, "Antenna &modeler...", self.show_antenna_modeler)
        self._act(m_radio, "Open &logbook (ADIF)...", self.show_adif_logbook)
        m_radio.addSeparator()
        self._act(m_radio, "RF re&ference (bands / CTCSS)...", self.show_rf_reference)
        self._act(m_radio, "&I/Q constellation -> SVG", self.export_iq_svg)
        self._act(m_radio, "Smith chart -> S&VG...", self.export_smith_svg)
        self._act(m_radio, "Solve &NEC deck (PyNEC)...", self.solve_nec_pynec)

        m_tools.addSeparator()
        m_face = m_tools.addMenu("Calculator &faceplates")
        self._act(m_face, "Set image folder...", self.set_faceplate_folder)
        self._act(m_tools, "Copy selection as &Markdown", self._copy_as_markdown)

        # --- Help ---------------------------------------------------------
        m_help = mb.addMenu("&Help")
        self._act(m_help, "&Keyboard shortcuts", self.show_shortcuts, "F1")
        self._act(m_help, "&About abax", self.show_about)

    def _setup_toolbar(self) -> None:
        from ._qtcompat import Qt
        from .icons import make_icon

        tb = self.addToolBar("Main")
        self._toolbar = tb
        tb.setMovable(False)
        tb.setAccessibleName("Main toolbar")
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        if not getattr(self._settings, "show_toolbar", True):
            tb.setVisible(False)

        def add(label, slot, icon):
            act = QAction(make_icon(icon), label, self)
            act.setToolTip(label)
            act.triggered.connect(slot)
            tb.addAction(act)
            self._icon_actions.append((act, icon))

        add("New", self.new_document, "new")
        add("Open", lambda: self.open_document(None), "open")
        add("Save", lambda: self.save_document(None), "save")
        tb.addSeparator()
        add("Undo", self.undo_edit, "undo")
        add("Redo", self.redo_edit, "redo")
        tb.addSeparator()
        add("Copy", self.copy_selection, "copy")
        add("Paste", self.paste_at_cursor, "paste")
        add("Fill down", self.fill_down_selection, "fill_down")
        tb.addSeparator()
        add("Insert row above", lambda: self.insert_row(above=True), "insert_row")
        add("Insert column left", lambda: self.insert_column(left=True), "insert_col")
        add("Delete row", self.delete_row, "delete_row")
        add("Delete column", self.delete_column, "delete_col")
        tb.addSeparator()
        add("Bold", lambda: self.toggle_style("bold"), "bold")
        add("Italic", lambda: self.toggle_style("italic"), "italic")
        add("Align left", lambda: self.set_alignment("left"), "align_left")
        add("Align center", lambda: self.set_alignment("center"), "align_center")
        add("Align right", lambda: self.set_alignment("right"), "align_right")
        add("Text colour", self.pick_text_color, "text_color")
        add("Fill colour", self.pick_fill_color, "fill_color")
        tb.addSeparator()
        add("Sort", self.show_sort_dialog, "sort")
        add("Filter", self.show_filter_dialog, "filter")
        add("Statistics / analysis", self.show_stats_tool, "stats")
        add("Pivot / group-by", self.show_pivot, "pivot")
        tb.addSeparator()
        add("Find / replace", self.show_find_replace, "find")
        add("Calculator", self.toggle_calculator, "hp16c")
        add("Graph", self.show_graph, "graph")
        add("Equation editor", self.show_equation, "equation")
        add("Terminal", self.show_terminal, "terminal")
        add("Python console", self.show_pyconsole, "python")
        tb.addSeparator()
        add("Command palette", self.show_command_palette, "palette")

    def _rebuild_macros_menu(self) -> None:
        self._macros_menu.clear()
        reg = self._macro_registry
        if not reg or not reg.macros:
            act = self._macros_menu.addAction("(no macros loaded)")
            act.setEnabled(False)
            return
        for name in sorted(reg.macros):
            self._act(self._macros_menu, name, lambda checked=False, n=name: self._run_macro(n))

    def _start_autosave(self) -> None:
        from .. import _runtime as rt
        from ..settings import save_settings

        self._autosave = QTimer(self)
        self._autosave.timeout.connect(
            lambda: save_settings(self._settings, rt.CONFIG_DIR / "settings.json")
        )
        self.restart_autosave()

    def restart_autosave(self) -> None:
        """(Re)apply the autosave settings to the running timer.

        Honours ``settings.autosave_enabled`` and ``settings.autosave_interval``
        (seconds), so the Preferences dialog can change the cadence live. When
        disabled the timer is simply stopped; settings still persist on close.
        """
        timer = getattr(self, "_autosave", None)
        if timer is None:
            return
        if getattr(self._settings, "autosave_enabled", True):
            secs = int(getattr(self._settings, "autosave_interval", 30) or 30)
            timer.start(max(1, secs) * 1000)
        else:
            timer.stop()

    # --- window state + status cluster -----------------------------------

    def _update_status_cluster(self) -> None:
        """Refresh the right-side status indicators (vim - theme - saved state)."""
        if getattr(self, "_sb_vim", None) is None:
            return
        self._sb_vim.setText("VIM" if getattr(self._settings, "vim_mode", False) else "INS")
        self._sb_theme.setText(getattr(self._settings, "theme", ""))
        self._sb_dirty.setText("* unsaved" if getattr(self._doc, "dirty", False) else "o saved")

    def _save_window_state(self) -> None:
        """Persist window geometry, the active sheet, and the cursor cell."""
        try:
            g = self.geometry()
            self._settings.window_geometry = {"x": g.x(), "y": g.y(),
                                              "w": g.width(), "h": g.height()}
            if getattr(self, "_tabs", None) is not None:
                self._settings.last_sheet = self._tabs.currentIndex()
            self._settings.last_cell = to_a1(max(0, self._table.currentRow()),
                                             max(0, self._table.currentColumn()))
        except Exception:
            pass

    def _restore_window_state(self) -> None:
        """Restore geometry / active sheet / cursor cell saved last session."""
        try:
            gd = getattr(self._settings, "window_geometry", {}) or {}
            if all(k in gd for k in ("x", "y", "w", "h")):
                self.resize(int(gd["w"]), int(gd["h"]))
                self.move(int(gd["x"]), int(gd["y"]))
            si = int(getattr(self._settings, "last_sheet", 0) or 0)
            if getattr(self, "_tabs", None) is not None and 0 <= si < self._tabs.count():
                self._tabs.setCurrentIndex(si)
            cell = getattr(self._settings, "last_cell", "") or ""
            if cell:
                from ..core.reference import parse_a1

                r, c = parse_a1(cell)
                self._table.setCurrentCell(r, c)
        except Exception:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        from .. import _runtime as rt
        from ..settings import save_settings

        # Stop the sandboxed console's worker thread + subprocess before teardown.
        dock = getattr(self, "_pyconsole_dock", None)
        if dock is not None and dock.widget() is not None:
            try:
                dock.widget()._shutdown()
            except Exception:
                pass
        # ... and the macro/script runner's worker, if one was ever spawned.
        bridge = getattr(self, "_macro_bridge", None)
        if bridge is not None:
            try:
                bridge.close()
            except Exception:
                pass
        self._save_window_state()
        try:
            save_settings(self._settings, rt.CONFIG_DIR / "settings.json")
        except Exception:
            pass
        super().closeEvent(event)

    # --- formula bar / selection -----------------------------------------

    def _on_current_cell_changed(self, row: int, col: int, *_prev) -> None:
        if row < 0 or col < 0:
            return
        self._formula_bar.setText(self._doc.workbook.sheet.get_raw(row, col))
        # Both currentChanged and selectionChanged route here so the status line
        # is consistent regardless of which Qt signal fires last.
        self._update_selection_status()

    def _update_selection_status(self) -> None:
        """Show the active cell's A1 ref, or Sum/Avg/Count/Min/Max for a range.

        Mirrors Excel's status bar. Aggregates over numeric cells only; Count is
        of non-blank cells. Capped so selecting a whole column never stalls.
        """
        row = max(0, self._table.currentRow())
        col = max(0, self._table.currentColumn())
        ranges = self._table.selectedRanges()
        total = sum((r.bottomRow() - r.topRow() + 1) * (r.rightColumn() - r.leftColumn() + 1)
                    for r in ranges)
        if total <= 1:
            self._set_status(to_a1(row, col))
            return
        if total > 200_000:  # avoid scanning a full-column/select-all on every change
            self._set_status(f"{to_a1(row, col)}  ({total:,} cells selected)")
            return
        sheet = self._doc.workbook.sheet
        seen: set[tuple[int, int]] = set()
        nonblank = 0
        nums: list[float] = []
        for rng in ranges:
            for r in range(rng.topRow(), rng.bottomRow() + 1):
                for c in range(rng.leftColumn(), rng.rightColumn() + 1):
                    if (r, c) in seen:
                        continue
                    seen.add((r, c))
                    val = sheet.get_value(r, c)
                    if val is None or val == "":
                        continue
                    nonblank += 1
                    x = _as_number(val)
                    if x is not None:
                        nums.append(x)
        if nums:
            total_sum = sum(nums)
            self._set_status(
                f"Sum {_fmt_num(total_sum)}   Avg {_fmt_num(total_sum / len(nums))}   "
                f"Min {_fmt_num(min(nums))}   Max {_fmt_num(max(nums))}   Count {nonblank}")
        else:
            self._set_status(f"Count {nonblank}")

    def _commit_formula_bar(self) -> None:
        row, col = self._table.currentRow(), self._table.currentColumn()
        if row < 0 or col < 0:
            return
        raw = self._formula_bar.text()
        if raw != self._doc.workbook.sheet.get_raw(row, col):
            self._doc.checkpoint(f"edit {to_a1(row, col)}", coalesce_key="edit")
            self._doc.workbook.sheet.set_cell(row, col, raw)
            self._recorder.record_set(to_a1(row, col), raw)
            self._doc.mark_dirty()
            self.refresh_table()
        # Excel feel: Enter in the formula bar commits and advances one row down,
        # even when the value is unchanged.
        self._table.setCurrentCell(row + 1, col)
        self._table.setFocus()

    def _row_header_menu(self, pos) -> None:
        from ._qtcompat import QMenu
        from .icons import make_icon

        header = self._table.verticalHeader()
        idx = header.logicalIndexAt(pos)
        if idx < 0:
            return
        menu = QMenu(self)
        menu.addAction(make_icon("insert_row_above"), f"Insert row above {idx + 1}",
                       lambda: self.insert_row(at=idx))
        menu.addAction(make_icon("insert_row_below"), f"Insert row below {idx + 1}",
                       lambda: self.insert_row(at=idx + 1))
        menu.addSeparator()
        menu.addAction(make_icon("delete_row"), f"Delete row {idx + 1}",
                       lambda: self.delete_row(at=idx))
        menu.exec(header.mapToGlobal(pos))

    def _build_cell_context_menu(self):
        """The grid right-click menu — clipboard, structure, formatting, and data
        tools, all wired to the existing actions (no duplicated logic)."""
        from ._qtcompat import QMenu
        from .icons import make_icon
        from ..core.format.cellformat import FORMATS

        m = QMenu(self)
        m.addAction(make_icon("cut"), "Cu&t", self.cut_selection)
        m.addAction(make_icon("copy"), "&Copy", self.copy_selection)
        m.addAction(make_icon("paste"), "&Paste", self.paste_at_cursor)
        m.addAction("Copy as &Markdown", self._copy_as_markdown)
        m.addSeparator()

        ins = m.addMenu("Insert")
        ins.addAction(make_icon("insert_row_above"), "Row above", lambda: self.insert_row(above=True))
        ins.addAction(make_icon("insert_row_below"), "Row below", lambda: self.insert_row(above=False))
        ins.addAction(make_icon("insert_col_left"), "Column left", lambda: self.insert_column(left=True))
        ins.addAction(make_icon("insert_col_right"), "Column right", lambda: self.insert_column(left=False))
        dele = m.addMenu("Delete")
        dele.addAction(make_icon("delete_row"), "Row(s)", self.delete_row)
        dele.addAction(make_icon("delete_col"), "Column(s)", self.delete_column)
        m.addAction("Clear contents", self._clear_selection)
        m.addSeparator()

        fmt = m.addMenu("Format")
        fmt.addAction(make_icon("bold"), "Bold", lambda: self.toggle_style("bold"))
        fmt.addAction(make_icon("italic"), "Italic", lambda: self.toggle_style("italic"))
        fmt.addAction(make_icon("underline"), "Underline", lambda: self.toggle_style("underline"))
        fmt.addSeparator()
        fmt.addAction(make_icon("text_color"), "Text colour...", self.pick_text_color)
        fmt.addAction(make_icon("fill_color"), "Fill colour...", self.pick_fill_color)
        fmt.addAction("Clear cell styles", self.clear_styles)
        num = m.addMenu("Number format")
        for spec, label in FORMATS:
            num.addAction(label, lambda checked=False, s=spec: self.set_number_format(s))
        m.addAction(make_icon("condformat"), "Conditional format...", self.add_conditional_format)
        m.addSeparator()

        row, col = self._table.currentRow(), self._table.currentColumn()
        has_comment = (row >= 0 and col >= 0
                       and self._doc.workbook.sheet.get_comment(row, col) is not None)
        if has_comment:
            m.addAction("Edit comment...", self.edit_comment)
            m.addAction("Delete comment", self.delete_comment)
        else:
            m.addAction("Insert comment...", self.edit_comment)
        m.addSeparator()

        data = m.addMenu("Data")
        data.addAction(make_icon("sort_asc"), "Sort ascending", lambda: self._sort_selection(False))
        data.addAction(make_icon("sort_desc"), "Sort descending", lambda: self._sort_selection(True))
        data.addAction("Fill series", self._fill_series_selection)
        data.addAction("Recode / clean...", self.show_recode)
        data.addAction("Open selection in pandas...", self.show_dataframe)
        # Retain a Python ref to every submenu + action wrapper: PySide6 otherwise
        # GCs the wrappers once the build locals drop and deletes the C++ objects,
        # emptying the menu. Holding them on `m` keeps them alive as long as it is.
        keep: list = []
        stack = [m]
        while stack:
            menu = stack.pop()
            for a in menu.actions():
                keep.append(a)
                if a.menu() is not None:
                    keep.append(a.menu())
                    stack.append(a.menu())
        m._keep = keep
        return m

    def _completion_context(self):
        """``(names, sheets)`` for formula autocomplete — the workbook's defined
        names and sheet names, offered alongside function names."""
        wb = self._doc.workbook
        reg = getattr(wb, "names", None)
        names = tuple(n for n, _ in reg.names()) if reg is not None else ()
        sheets = tuple(s.name for s in wb.sheets)
        return names, sheets

    def _cell_context_menu(self, pos) -> None:
        # Right-clicking a cell outside the current selection moves to it (Excel /
        # gnumeric behaviour) so Paste / Clear / Format target where you clicked;
        # right-clicking inside a multi-cell selection keeps it.
        idx = self._table.indexAt(pos)
        if idx.isValid() and not self._table.selectionModel().isSelected(idx):
            self._table.setCurrentIndex(idx)
        self._build_cell_context_menu().exec(self._table.viewport().mapToGlobal(pos))

    def _column_header_menu(self, pos) -> None:
        from ._qtcompat import QMenu
        from .icons import make_icon
        from ..core.reference import index_to_col

        header = self._table.horizontalHeader()
        idx = header.logicalIndexAt(pos)
        if idx < 0:
            return
        name = index_to_col(idx)
        menu = QMenu(self)
        menu.addAction(make_icon("sort_asc"), f"Sort asc by column {name}",
                       lambda: self._sort_region_by(idx, False))
        menu.addAction(make_icon("sort_desc"), f"Sort desc by column {name}",
                       lambda: self._sort_region_by(idx, True))
        menu.addAction(make_icon("filter"), "Filter...", self.show_filter_dialog)
        menu.addSeparator()
        menu.addAction(make_icon("insert_col_left"), f"Insert column left of {name}",
                       lambda: self.insert_column(at=idx))
        menu.addAction(make_icon("insert_col_right"), f"Insert column right of {name}",
                       lambda: self.insert_column(at=idx + 1))
        menu.addSeparator()
        menu.addAction(make_icon("delete_col"), f"Delete column {name}",
                       lambda: self.delete_column(at=idx))
        menu.exec(header.mapToGlobal(pos))

    def _sort_region_by(self, col: int, descending: bool) -> None:
        bounds = self._sort_region_bounds()
        self.apply_sort(bounds, [(col, descending)], has_header=False)

    def _freeze(self, mode) -> None:
        if mode == "row":
            self._frozen.freeze(1, 0)
            msg = "froze top row"
        elif mode == "col":
            self._frozen.freeze(0, 1)
            msg = "froze first column"
        elif mode == "none":
            self._frozen.unfreeze()
            msg = "unfroze panes"
        else:
            self._frozen.freeze_at_cursor()
            msg = "froze panes at cursor"
        self._set_status(msg)

    def _set_status(self, msg: str) -> None:
        self.statusBar().showMessage(msg)

    def _update_arg_hint(self, *_) -> None:
        """Floating tooltip showing the signature + current argument."""
        from ._qtcompat import QToolTip
        from ..core.completion import format_hint, signature_hint

        text = self._formula_bar.text()
        hint = signature_hint(text, self._formula_bar.cursorPosition())
        if hint is None:
            QToolTip.hideText()
            return
        pos = self._formula_bar.mapToGlobal(self._formula_bar.rect().bottomLeft())
        QToolTip.showText(pos, format_hint(hint, ("<b>", "</b>")), self._formula_bar)

    # --- keyboard ---------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if self._formula_bar.hasFocus():
            super().keyPressEvent(event)
            return
        editing = self._table.state() == self._table.State.EditingState
        if not editing:
            # ':' opens the command palette (gnumeric/vim feel); Del clears.
            if event.text() == ":":
                self.show_command_palette()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Delete:
                self._clear_selection()
                event.accept()
                return
        if self.handle_vim_key(event.key(), event.text()):
            event.accept()
            return
        super().keyPressEvent(event)
