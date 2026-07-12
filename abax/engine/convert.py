"""File-conversion facade — tabular formats via the workbook engine, documents
via pandoc.

Two backends behind one call:

* **Tabular** data (CSV/TSV, Excel, ODS, Parquet, JSON, Markdown tables, …) is
  converted by opening it as a :class:`~abax.engine.document.Document` and saving
  under the destination extension — the same path ``abax convert`` uses.
* **Documents** (Markdown ↔ Word/HTML/reStructuredText/LaTeX/EPUB/PDF/…, even
  non-tabular ones) go through **pandoc** when it is available
  (:mod:`abax.core.pandoc`).

The routing is by extension: a tabular→tabular pair uses the workbook engine;
anything else is handed to pandoc. :func:`batch_convert` applies this to many
files at once and returns a per-file result so the GUI can report successes and
failures together.
"""

from __future__ import annotations

import os
import subprocess

from ..core import pandoc


class ConvertError(Exception):
    """A single file could not be converted (bad format, missing pandoc, …)."""


# Extensions the workbook engine (Document) reads/writes as tabular data. A
# conversion whose source *and* target are both here uses that engine.
_TABULAR = frozenset({
    ".csv", ".tsv", ".tab", ".xlsx", ".xlsm", ".ods", ".parquet", ".pq",
    ".feather", ".ft", ".json", ".jsonl", ".ndjson", ".xml", ".md", ".markdown",
    ".r", ".rdata", ".ipynb", ".abax", ".fixed", ".db", ".sqlite", ".sqlite3",
    ".dta", ".sav", ".zsav", ".por", ".h5", ".hdf5", ".adi", ".adif",
})

# Document formats offered as conversion targets (pandoc handles these, plus the
# tabular ones above). Pairs the GUI shows in its "convert to…" list.
DOC_TARGETS = (
    ("Markdown (.md)", ".md"),
    ("HTML (.html)", ".html"),
    ("Word (.docx)", ".docx"),
    ("OpenDocument Text (.odt)", ".odt"),
    ("reStructuredText (.rst)", ".rst"),
    ("LaTeX (.tex)", ".tex"),
    ("EPUB (.epub)", ".epub"),
    ("Rich Text (.rtf)", ".rtf"),
    ("Plain text (.txt)", ".txt"),
    ("PDF (.pdf)", ".pdf"),
)

TABULAR_TARGETS = (
    ("CSV (.csv)", ".csv"),
    ("TSV (.tsv)", ".tsv"),
    ("Excel (.xlsx)", ".xlsx"),
    ("OpenDocument Sheet (.ods)", ".ods"),
    ("JSON (.json)", ".json"),
    ("Markdown table (.md)", ".md"),
)


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def pandoc_available() -> bool:
    """True when a pandoc executable can be resolved (see :mod:`abax.core.pandoc`)."""
    return pandoc.available()


def pandoc_convert(src: str, dst: str, timeout: int = 180) -> None:
    """Convert ``src`` → ``dst`` with pandoc (formats inferred from extensions).

    Raises :class:`ConvertError` if pandoc is unavailable or exits non-zero (its
    stderr is surfaced, e.g. "pdflatex not found" for PDF output).
    """
    exe = pandoc.pandoc_path()
    if not exe:
        raise ConvertError(
            "pandoc is not installed. Install it from Tools → Install optional "
            "features, or `pip install pypandoc_binary`.")
    try:
        proc = subprocess.run(
            [exe, "--standalone", src, "-o", dst],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConvertError(str(exc)) from exc
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise ConvertError(msg or f"pandoc exited with status {proc.returncode}")


def convert_file(src: str, dst: str) -> str:
    """Convert one file ``src`` → ``dst``, choosing the backend by extension.

    Returns ``"tabular"`` or ``"document"`` for the backend used. Raises
    :class:`ConvertError` on failure (including a clear message when a document
    conversion needs pandoc and it isn't installed).
    """
    if not os.path.isfile(src):
        raise ConvertError(f"no such file: {src}")
    if os.path.abspath(src) == os.path.abspath(dst):
        raise ConvertError("source and destination are the same file")

    s, d = _ext(src), _ext(dst)
    if s in _TABULAR and d in _TABULAR:
        from .document import Document

        try:
            Document.open(src).save(dst)
        except Exception as exc:  # noqa: BLE001 — surface any read/write failure
            raise ConvertError(str(exc)) from exc
        return "tabular"

    pandoc_convert(src, dst)
    return "document"


def batch_convert(
    paths: list[str], out_dir: str, out_ext: str,
) -> list[tuple[str, str | None, str | None]]:
    """Convert every path in ``paths`` into ``out_dir`` with extension ``out_ext``.

    Returns one ``(src, dst_or_None, error_or_None)`` tuple per input: on success
    ``dst`` is the written path and ``error`` is None; on failure ``dst`` is None
    and ``error`` is the message. One bad file never stops the rest.
    """
    ext = out_ext if out_ext.startswith(".") else "." + out_ext
    results: list[tuple[str, str | None, str | None]] = []
    for src in paths:
        base = os.path.splitext(os.path.basename(src))[0]
        dst = os.path.join(out_dir, base + ext)
        try:
            convert_file(src, dst)
            results.append((src, dst, None))
        except ConvertError as exc:
            results.append((src, None, str(exc)))
        except Exception as exc:  # noqa: BLE001 — defensive; report, don't abort the batch
            results.append((src, None, str(exc)))
    return results
