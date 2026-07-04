"""Print the active workbook or export it to PDF (GUI-only, read-only).

Both entry points render the workbook to a self-contained HTML report with the
existing :func:`abax.core.io.html_report.workbook_to_html`, load that into a
``QTextDocument`` and hand it to a ``QPrinter``. Nothing here mutates the
document, so there is no checkpoint/dirty bookkeeping — printing and PDF export
are pure outputs.

The integrator wires these as File → Print (Ctrl+P) and File → Export PDF; they
take the :class:`MainWindow` so they can reach ``window._doc.workbook`` and pop
dialogs parented to the window.
"""

from __future__ import annotations

from ._qtcompat import (
    QFileDialog,
    QMessageBox,
    QPrintDialog,
    QPrinter,
    QTextDocument,
)
from ..core.io.html_report import workbook_to_html


def _render_document(window) -> QTextDocument:
    """Build a ``QTextDocument`` holding the HTML report for the workbook."""
    html = workbook_to_html(window._doc.workbook, title=window._doc.title)
    doc = QTextDocument()
    doc.setHtml(html)
    return doc


def print_document(window) -> None:
    """Open a ``QPrintDialog`` and print the active workbook if accepted."""
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    dialog = QPrintDialog(printer, window)
    if dialog.exec() != QPrintDialog.DialogCode.Accepted:
        return
    _render_document(window).print_(printer)
    status = getattr(window, "_set_status", None)
    if status is not None:
        status("sent to printer")


def export_pdf(window, path: str | None = None) -> str | None:
    """Render the workbook to a PDF file, returning the path (or ``None``).

    With ``path`` omitted the target is chosen via ``QFileDialog``; cancelling
    the dialog returns ``None`` and writes nothing.
    """
    if path is None:
        suggested = f"{_stem(window)}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            window, "Export PDF", suggested, "PDF documents (*.pdf);;All files (*)")
        if not path:
            return None

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    try:
        _render_document(window).print_(printer)
    except Exception as exc:  # pragma: no cover - printer/backend failures
        QMessageBox.critical(window, "Export PDF", str(exc))
        return None

    status = getattr(window, "_set_status", None)
    if status is not None:
        status(f"exported PDF to {path}")
    return path


def _stem(window) -> str:
    """A filename stem for the PDF, derived from the document title.

    Drops a single trailing extension (e.g. ``sales.csv`` → ``sales``); an
    untitled document keeps its ``untitled`` stem.
    """
    title = window._doc.title
    return title.rsplit(".", 1)[0] if "." in title else title
