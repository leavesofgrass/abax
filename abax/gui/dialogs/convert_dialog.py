"""Batch file-conversion dialog — convert many files to another format at once.

Tabular files (CSV/Excel/ODS/Parquet/JSON/Markdown tables) go through abax's
workbook engine; document formats (Markdown ↔ Word/HTML/RST/LaTeX/EPUB/PDF/…)
go through **pandoc** when it's installed. See :mod:`abax.engine.convert`.
"""

from __future__ import annotations

import os

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class ConvertDialog(QDialog):
    """Pick files + a target format; convert them all, reporting each result."""

    def __init__(self, window, paths: "list[str] | None" = None) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Convert files")
        self.resize(560, 460)
        self._build()
        for p in paths or []:
            if os.path.isfile(p):
                self._files.addItem(p)
        self._sync_out_dir()

    def _build(self) -> None:
        from ...engine.convert import DOC_TARGETS, TABULAR_TARGETS, pandoc_available

        outer = QVBoxLayout(self)

        outer.addWidget(QLabel("Files to convert:", self))
        self._files = QListWidget(self)
        self._files.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        outer.addWidget(self._files, 1)

        row = QHBoxLayout()
        add = QPushButton("Add files…", self)
        add.clicked.connect(self._add_files)
        rm = QPushButton("Remove", self)
        rm.clicked.connect(self._remove_selected)
        clear = QPushButton("Clear", self)
        clear.clicked.connect(self._files.clear)
        row.addWidget(add)
        row.addWidget(rm)
        row.addWidget(clear)
        row.addStretch(1)
        outer.addLayout(row)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Convert to:", self))
        self._fmt = QComboBox(self)
        for label, ext in TABULAR_TARGETS:
            self._fmt.addItem(label, ext)
        self._fmt.insertSeparator(self._fmt.count())
        for label, ext in DOC_TARGETS:
            self._fmt.addItem(label, ext)
        fmt_row.addWidget(self._fmt, 1)
        outer.addLayout(fmt_row)

        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Output folder:", self))
        self._out_dir = QLineEdit(self)
        browse = QPushButton("Browse…", self)
        browse.clicked.connect(self._pick_out_dir)
        dir_row.addWidget(self._out_dir, 1)
        dir_row.addWidget(browse)
        outer.addLayout(dir_row)

        note = QLabel(
            "Tabular files (CSV, Excel, ODS, Parquet, JSON, Markdown tables) use "
            "the built-in engine. Document formats (Word, HTML, RST, LaTeX, EPUB, "
            "PDF…) need pandoc — "
            + ("pandoc is available." if pandoc_available()
               else "pandoc is NOT installed (install it from Tools → Install "
                    "optional features)."),
            self)
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid); font-size: 11px;")
        outer.addWidget(note)

        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Results appear here after converting.")
        outer.addWidget(self._log, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._convert_btn = QPushButton("Convert", self)
        self._convert_btn.setDefault(True)
        self._convert_btn.clicked.connect(self._do_convert)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        btn_row.addWidget(self._convert_btn)
        btn_row.addWidget(close)
        outer.addLayout(btn_row)

    # -- helpers -----------------------------------------------------------

    def _paths(self) -> list[str]:
        return [self._files.item(i).text() for i in range(self._files.count())]

    def _sync_out_dir(self) -> None:
        if self._out_dir.text().strip():
            return
        paths = self._paths()
        base = os.path.dirname(paths[0]) if paths else os.path.expanduser("~")
        self._out_dir.setText(base)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add files to convert")
        for f in files:
            if f and f not in self._paths():
                self._files.addItem(f)
        self._sync_out_dir()

    def _remove_selected(self) -> None:
        for item in self._files.selectedItems():
            self._files.takeItem(self._files.row(item))

    def _pick_out_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Output folder", self._out_dir.text())
        if d:
            self._out_dir.setText(d)

    def _do_convert(self) -> None:
        from ...engine.convert import batch_convert

        paths = self._paths()
        if not paths:
            self._log.setPlainText("Add some files first.")
            return
        out_dir = self._out_dir.text().strip() or os.path.dirname(paths[0])
        if not os.path.isdir(out_dir):
            self._log.setPlainText(f"Output folder does not exist: {out_dir}")
            return
        out_ext = self._fmt.currentData()

        results = batch_convert(paths, out_dir, out_ext)
        ok = sum(1 for _s, _d, err in results if err is None)
        lines = []
        for src, dst, err in results:
            name = os.path.basename(src)
            if err is None:
                lines.append(f"✓  {name}  →  {os.path.basename(dst)}")
            else:
                lines.append(f"✗  {name}  —  {err}")
        self._log.setPlainText("\n".join(lines))
        self._win._set_status(f"converted {ok}/{len(results)} file(s) → {out_dir}")
        if hasattr(self._win, "_file_manager") and self._win._file_manager is not None:
            try:
                self._win._file_manager.refresh_both()
            except Exception:  # noqa: BLE001 — refresh is best-effort
                pass
