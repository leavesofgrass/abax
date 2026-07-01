"""Dual-pane file manager — a Worker / Directory Opus-style browser.

Two independent panes side by side; operations act on the *active* pane's
selection with the *other* pane as the target (the classic two-pane workflow).
A toolbar offers copy/move/delete/new-folder/rename/refresh, one-click
zip/tar.gz creation and extraction, and recursive find; a second row holds the
configurable command buttons (:mod:`qcell.core.fmbuttons`). All the heavy lifting
is the pure-stdlib core (:mod:`qcell.core.fileops` / ``archive`` / ``filesearch``),
so this file is just wiring and Qt.
"""

from __future__ import annotations

import os
import time

from .._qtcompat import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ...core import archive, filesearch, fmbuttons
from ...core import fileops as F


class _Pane(QWidget):
    """One directory view: address bar, an Up button, and a file table."""

    def __init__(self, start_dir: str, on_active) -> None:
        super().__init__()
        self._dir = os.path.abspath(start_dir)
        self._on_active = on_active
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        bar = QHBoxLayout()
        self._up = QPushButton("Up", self)
        self._up.clicked.connect(self.go_up)
        self._address = QLineEdit(self._dir, self)
        self._address.returnPressed.connect(self._address_entered)
        bar.addWidget(self._up)
        bar.addWidget(self._address, 1)
        layout.addLayout(bar)

        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["Name", "Size", "Modified"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.cellDoubleClicked.connect(self._activated)
        self._table.itemSelectionChanged.connect(lambda: self._on_active(self))
        layout.addWidget(self._table, 1)
        self.refresh()

    # --- state ----------------------------------------------------------
    def current_dir(self) -> str:
        return self._dir

    def selected_paths(self) -> list[str]:
        rows = sorted({i.row() for i in self._table.selectedItems()})
        out = []
        for r in rows:
            item = self._table.item(r, 0)
            if item is not None:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out

    def set_dir(self, path: str) -> None:
        path = os.path.abspath(path)
        if os.path.isdir(path):
            self._dir = path
            self._address.setText(path)
            self.refresh()
            self._on_active(self)

    def go_up(self) -> None:
        self.set_dir(os.path.dirname(self._dir.rstrip(os.sep)) or self._dir)

    def select_names(self, names) -> None:
        """Test/programmatic helper: select rows by entry name."""
        wanted = set(names)
        self._table.clearSelection()
        for r in range(self._table.rowCount()):
            item = self._table.item(r, 0)
            if item is not None and os.path.basename(
                    item.data(Qt.ItemDataRole.UserRole)) in wanted:
                # set each cell selected (selectRow would *replace* the selection
                # in extended-selection mode, dropping earlier rows)
                for c in range(self._table.columnCount()):
                    cell = self._table.item(r, c)
                    if cell is not None:
                        cell.setSelected(True)

    def select_all(self) -> None:
        self._table.selectAll()

    def invert_selection(self) -> None:
        selected = {i.row() for i in self._table.selectedItems()}
        self._table.clearSelection()
        for r in range(self._table.rowCount()):
            if r not in selected:
                for c in range(self._table.columnCount()):
                    cell = self._table.item(r, c)
                    if cell is not None:
                        cell.setSelected(True)

    def refresh(self) -> None:
        try:
            entries = F.list_dir(self._dir)
        except OSError as exc:
            QMessageBox.warning(self, "File manager", str(exc))
            return
        self._table.setRowCount(len(entries))
        for r, e in enumerate(entries):
            name = QTableWidgetItem(("[ ] " if e.is_dir else "") + e.name)
            name.setData(Qt.ItemDataRole.UserRole, e.path)
            size = QTableWidgetItem("<dir>" if e.is_dir else F.human_size(e.size))
            mod = QTableWidgetItem(time.strftime("%Y-%m-%d %H:%M",
                                                 time.localtime(e.mtime)))
            self._table.setItem(r, 0, name)
            self._table.setItem(r, 1, size)
            self._table.setItem(r, 2, mod)

    # --- interaction ----------------------------------------------------
    def _address_entered(self) -> None:
        self.set_dir(self._address.text())

    def _activated(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if os.path.isdir(path):
            self.set_dir(path)


class FileManagerDialog(QDialog):
    def __init__(self, window=None, start_dir: str | None = None) -> None:
        super().__init__(window)
        self.setWindowTitle("File manager")
        self.resize(900, 540)
        self._win = window
        start = start_dir or os.getcwd()

        root = QVBoxLayout(self)
        root.addLayout(self._build_toolbars())

        self.left = _Pane(start, self._set_active)
        self.right = _Pane(start, self._set_active)
        split = QSplitter(Qt.Orientation.Horizontal, self)
        split.addWidget(self.left)
        split.addWidget(self.right)
        split.setSizes([450, 450])
        root.addWidget(split, 1)

        self._active = self.left
        root.addWidget(self._build_command_buttons())
        self._output = QPlainTextEdit(self)
        self._output.setReadOnly(True)
        self._output.setMaximumHeight(110)
        self._output.setPlaceholderText("command output")
        root.addWidget(self._output)
        self._status = QLabel("", self)
        root.addWidget(self._status)

    # --- layout ---------------------------------------------------------
    def _build_toolbars(self):
        """Worker-style two-row button bank (plus a utilities row).

        Row 1 mirrors Worker's primary keys (Home, F3-View … F8-Delete); row 2
        its secondary bank (root, select-all/invert, start-program, duplicate,
        reload, find, dir-size). The F-keys are live shortcuts on the buttons."""
        self._buttons_by_label = {}
        col = QVBoxLayout()
        col.addLayout(self._button_row((
            ("Home", self._go_home, None),
            ("F3 View", self._view, "F3"),
            ("F4 Edit", self._edit, "F4"),
            ("F5 Copy ->", self._copy, "F5"),
            ("F6 Move ->", self._move, "F6"),
            ("F7 New dir", self._new_folder, "F7"),
            ("F8 Delete", self._delete, "F8"),
        )))
        col.addLayout(self._button_row((
            ("/", self._go_root, None),
            ("All", self._select_all, None),
            ("Invert", self._invert_selection, None),
            ("Start prog", self._start_program, None),
            ("Duplicate", self._duplicate, None),
            ("Reload", self.refresh_both, "F2"),
            ("Find file", self._find, None),
            ("Dirsize", self._dirsize, None),
        )))
        col.addLayout(self._button_row((
            ("Rename", self._rename, None),
            ("Zip", lambda: self._archive(".zip"), None),
            ("Tar.gz", lambda: self._archive(".tar.gz"), None),
            ("Extract", self._extract, None),
        )))
        return col

    def _button_row(self, specs):
        bar = QHBoxLayout()
        for label, slot, shortcut in specs:
            btn = QPushButton(label, self)
            btn.clicked.connect(slot)
            if shortcut:
                btn.setShortcut(shortcut)
                btn.setToolTip(f"{label.split(' ', 1)[-1]}  ({shortcut})")
            bar.addWidget(btn)
            self._buttons_by_label[label] = btn
        bar.addStretch(1)
        return bar

    def _build_command_buttons(self):
        self._cmd_row = QWidget(self)
        self._cmd_layout = QHBoxLayout(self._cmd_row)
        self._cmd_layout.setContentsMargins(0, 0, 0, 0)
        self._reload_command_buttons()
        return self._cmd_row

    def _user_buttons(self) -> list[fmbuttons.Button]:
        raw = getattr(getattr(self._win, "_settings", None), "fm_buttons", []) or []
        out = []
        for data in raw:
            try:
                out.append(fmbuttons.Button.from_dict(data))
            except (KeyError, TypeError):
                continue
        return out

    def _reload_command_buttons(self) -> None:
        while self._cmd_layout.count():
            item = self._cmd_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cmd_layout.addWidget(QLabel("Commands:", self))
        self._buttons = fmbuttons.default_buttons() + self._user_buttons()
        for b in self._buttons:
            btn = QPushButton(b.label, self)
            btn.setToolTip(b.command)
            btn.clicked.connect(lambda _=False, bb=b: self._run_button(bb))
            self._cmd_layout.addWidget(btn)
        add = QPushButton("+ Add...", self)
        add.setToolTip("Add a custom command button")
        add.clicked.connect(self._add_button)
        self._cmd_layout.addWidget(add)
        self._cmd_layout.addStretch(1)

    def _add_button(self) -> None:
        label, ok = QInputDialog.getText(self, "Add command button", "Button label:")
        if not ok or not label.strip():
            return
        command, ok2 = QInputDialog.getText(
            self, "Add command button",
            "Command (placeholders: {dir} {path} {name} {sel} {dest}):")
        if not ok2 or not command.strip():
            return
        settings = getattr(self._win, "_settings", None)
        if settings is not None:
            settings.fm_buttons = list(getattr(settings, "fm_buttons", []) or []) + [
                {"label": label.strip(), "command": command.strip()}]
            self._persist_settings()
        self._reload_command_buttons()
        self._set_status(f"added command button '{label.strip()}'")

    def _persist_settings(self) -> None:
        settings = getattr(self._win, "_settings", None)
        if settings is None:
            return
        try:
            from .. import _runtime as rt
            from ...settings import save_settings
            save_settings(settings, rt.CONFIG_DIR / "settings.json")
        except Exception:
            pass

    # --- helpers --------------------------------------------------------
    def _set_active(self, pane: _Pane) -> None:
        self._active = pane

    def _other(self, pane: _Pane) -> _Pane:
        return self.right if pane is self.left else self.left

    def refresh_both(self) -> None:
        self.left.refresh()
        self.right.refresh()

    def _set_status(self, msg: str) -> None:
        self._status.setText(msg)

    def _context(self) -> fmbuttons.Context:
        return fmbuttons.Context(
            directory=self._active.current_dir(),
            selection=self._active.selected_paths(),
            dest_dir=self._other(self._active).current_dir())

    # --- navigation / selection (Worker rows) ---------------------------
    def _go_home(self) -> None:
        self._active.set_dir(os.path.expanduser("~"))

    def _go_root(self) -> None:
        drive = os.path.splitdrive(self._active.current_dir())[0]
        self._active.set_dir(drive + os.sep if drive else os.sep)

    def _select_all(self) -> None:
        self._active.select_all()

    def _invert_selection(self) -> None:
        self._active.invert_selection()

    def _duplicate(self) -> None:
        """Copy the active selection back into the SAME pane (Worker 'Duplicate');
        name conflicts auto-rename via fileops.unique_path."""
        sel = self._active.selected_paths()
        if not sel:
            self._set_status("nothing selected to duplicate")
            return
        res = F.copy_paths(sel, self._active.current_dir())
        self._active.refresh()
        self._set_status("duplicated: " + res.summary())

    def _dirsize(self) -> None:
        """Recursive size of the selection (or the active directory if nothing is
        selected)."""
        targets = self._active.selected_paths() or [self._active.current_dir()]
        total = sum(F.tree_size(p) for p in targets)
        self._set_status(
            f"{len(targets)} item(s): {F.human_size(total)} ({total:,} bytes)")

    def _start_program(self) -> None:
        """Run a program/command in the active directory (Worker 'Start prog').

        Placeholders {dir}/{path}/{name}/{sel}/{dest} are expanded via the same
        fmbuttons machinery as the command buttons, so quoting/joins are shared."""
        command, ok = QInputDialog.getText(
            self, "Start program",
            "Command (placeholders: {dir} {path} {name} {sel} {dest}):")
        if not ok or not command.strip():
            return
        self._run_button(fmbuttons.Button(label="start", command=command.strip()))

    def _view(self) -> None:
        self._open_file_editor(read_only=True)

    def _edit(self) -> None:
        self._open_file_editor(read_only=False)

    def _open_file_editor(self, *, read_only: bool) -> None:
        sel = self._active.selected_paths()
        if not sel:
            self._set_status("select a file to " + ("view" if read_only else "edit"))
            return
        path = sel[0]
        if os.path.isdir(path):
            self._set_status("that is a directory")
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read(1_000_000)
        except OSError as exc:
            QMessageBox.warning(self, "Open file", str(exc))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(("View: " if read_only else "Edit: ") + os.path.basename(path))
        dlg.resize(760, 520)
        lay = QVBoxLayout(dlg)
        editor = QPlainTextEdit(dlg)
        editor.setPlainText(text)
        editor.setReadOnly(read_only)
        lay.addWidget(editor, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        if not read_only:
            save = QPushButton("Save", dlg)

            def do_save():
                try:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(editor.toPlainText())
                except OSError as exc:
                    QMessageBox.warning(dlg, "Save", str(exc))
                    return
                self._active.refresh()
                self._set_status(f"saved {os.path.basename(path)}")
                dlg.accept()

            save.clicked.connect(do_save)
            row.addWidget(save)
        close = QPushButton("Close", dlg)
        close.clicked.connect(dlg.accept)
        row.addWidget(close)
        lay.addLayout(row)
        dlg.exec()

    # --- operations -----------------------------------------------------
    def _copy(self) -> None:
        dest = self._other(self._active).current_dir()
        res = F.copy_paths(self._active.selected_paths(), dest)
        self.refresh_both()
        self._set_status("copied: " + res.summary())

    def _move(self) -> None:
        dest = self._other(self._active).current_dir()
        res = F.move_paths(self._active.selected_paths(), dest)
        self.refresh_both()
        self._set_status("moved: " + res.summary())

    def _delete(self) -> None:
        paths = self._active.selected_paths()
        if not paths:
            return
        if QMessageBox.question(self, "Delete",
                                f"Delete {len(paths)} item(s)?") \
                != QMessageBox.StandardButton.Yes:
            return
        res = F.delete_paths(paths)
        self.refresh_both()
        self._set_status("deleted: " + res.summary())

    def _new_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "New folder", "Name:")
        if ok and name:
            try:
                F.make_dir(self._active.current_dir(), name)
            except OSError as exc:
                QMessageBox.warning(self, "New folder", str(exc))
            self._active.refresh()

    def _rename(self) -> None:
        sel = self._active.selected_paths()
        if not sel:
            return
        old = os.path.basename(sel[0])
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old)
        if ok and name and name != old:
            try:
                F.rename_path(sel[0], name)
            except OSError as exc:
                QMessageBox.warning(self, "Rename", str(exc))
            self._active.refresh()

    def _archive(self, ext: str) -> None:
        sel = self._active.selected_paths()
        if not sel:
            self._set_status("nothing selected to archive")
            return
        default = os.path.join(self._active.current_dir(), "archive" + ext)
        dest, _ = QFileDialog.getSaveFileName(self, "Create archive", default)
        if not dest:
            return
        try:
            archive.create_archive(sel, dest)
        except (OSError, archive.ArchiveError) as exc:
            QMessageBox.warning(self, "Archive", str(exc))
            return
        self.refresh_both()
        self._set_status(f"created {os.path.basename(dest)}")

    def _extract(self) -> None:
        sel = self._active.selected_paths()
        if not sel:
            return
        dest = self._other(self._active).current_dir()
        try:
            names = archive.extract_archive(sel[0], dest)
        except (OSError, archive.ArchiveError) as exc:
            QMessageBox.warning(self, "Extract", str(exc))
            return
        self.refresh_both()
        self._set_status(f"extracted {len(names)} item(s) -> {dest}")

    def _find(self) -> None:
        pattern, ok = QInputDialog.getText(
            self, "Find", "Name pattern (e.g. *.py):", text="*")
        if not ok or not pattern:
            return
        contains, ok2 = QInputDialog.getText(
            self, "Find", "Containing text (optional):")
        kw = {"name_glob": pattern}
        if ok2 and contains:
            kw["contains"] = contains
        hits = filesearch.search(self._active.current_dir(), **kw)
        self._show_results(hits)

    def _show_results(self, hits) -> None:
        from .._qtcompat import QListWidget

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Find results ({len(hits)})")
        dlg.resize(700, 400)
        lay = QVBoxLayout(dlg)
        lst = QListWidget(dlg)
        for m in hits:
            label = m.path + (f":{m.line_no}: {m.line.strip()}" if m.line_no else "")
            lst.addItem(label)
        lay.addWidget(lst)

        def jump():
            row = lst.currentRow()
            if 0 <= row < len(hits):
                folder = os.path.dirname(hits[row].path)
                self._active.set_dir(folder)
                self._active.select_names([os.path.basename(hits[row].path)])
                dlg.accept()

        lst.itemDoubleClicked.connect(jump)
        dlg.exec()

    def _run_button(self, button: fmbuttons.Button) -> None:
        if button.confirm and QMessageBox.question(
                self, button.label, f"Run: {button.command}?") \
                != QMessageBox.StandardButton.Yes:
            return
        res = fmbuttons.run_button(button, self._context(), timeout=60)
        self.refresh_both()
        out = (res.stdout or res.stderr or "").rstrip()
        # Non-modal: command output goes to the output pane, not a blocking popup.
        self._output.appendPlainText(f"$ {res.command}")
        if out:
            self._output.appendPlainText(out[:8000])
        self._set_status(f"{button.label}: exit {res.returncode}")
