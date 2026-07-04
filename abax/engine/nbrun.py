"""Headless notebook execution — run an ``.ipynb`` without nbclient/jupyter.

The counterpart to :mod:`abax.core.io.notebook_io` (which imports/exports the
*data*) and :mod:`abax.engine.nbvalidate` (which checks the *shape*): this module
*runs* a notebook. Each code cell is executed, in order, through abax's own
:class:`abax.kernel.AbaxShell` — the very same namespace the kernel and embedded
console use — so ``doc``, ``wb``, ``sheet()``, ``cell()`` and the science packs
are all bound, and state carries from one cell to the next. Captured stdout and
the last expression's rich mime-bundle are written back into the notebook as
nbformat ``stream`` / ``execute_result`` (or ``error``) outputs.

nbclient/jupyter-client spin up a ZMQ kernel in a subprocess; we deliberately do
not — abax already has an in-process shell, so notebook execution needs no extra
runtime and no ZMQ. ``nbformat`` is used when installed (authoritative
read/normalise), otherwise a stdlib ``json`` cold path produces the same cell and
output dicts.

Public entry point: :func:`run_notebook`.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    import nbformat as _nbformat
    HAS_NBFORMAT = True
except Exception:                          # nbformat is optional
    _nbformat = None
    HAS_NBFORMAT = False

from ..kernel import AbaxShell


def _read(path: str | Path) -> dict:
    """Load a notebook to a plain dict (nbformat when present, else json)."""
    if HAS_NBFORMAT:
        # as_version=4 upgrades older notebooks; NotebookNode is dict-compatible.
        return _nbformat.read(str(path), as_version=4)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(nb: dict, path: str | Path) -> None:
    if HAS_NBFORMAT:
        # We build outputs as plain dicts (so the stdlib cold path is identical);
        # from_dict re-wraps the whole tree as NotebookNodes, which nbformat.write
        # needs for its attribute-style line-splitting.
        _nbformat.write(_nbformat.from_dict(nb), str(path))
    else:
        Path(path).write_text(json.dumps(nb, indent=1), encoding="utf-8")


def _source_text(cell: dict) -> str:
    """Cell source as one string (nbformat stores it as a list of lines)."""
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def _cell_outputs(result: dict) -> list[dict]:
    """Turn one :meth:`AbaxShell.run_cell_block` result into nbformat outputs.

    Order matches a live kernel: any captured stream first, then the last
    expression's ``execute_result`` (or, if the cell raised, an ``error``).
    """
    outputs: list[dict] = []
    if result["stdout"]:
        outputs.append({"output_type": "stream", "name": "stdout",
                        "text": result["stdout"]})
    if result["error"]:
        # AbaxShell hands us a formatted traceback string; split to the list of
        # lines nbformat's 'traceback' field expects (kept ANSI-free — abax's
        # traceback is plain text).
        tb = result["error"].rstrip("\n").split("\n")
        ename, evalue = _split_error(tb)
        outputs.append({"output_type": "error", "ename": ename,
                        "evalue": evalue, "traceback": tb})
    elif result["data"]:
        outputs.append({"output_type": "execute_result",
                        "execution_count": result["execution_count"],
                        "data": result["data"], "metadata": {}})
    return outputs


def _split_error(tb_lines: list[str]) -> tuple[str, str]:
    """Best-effort ``(ename, evalue)`` from a traceback's last line.

    The final line of a Python traceback is ``ExceptionType: message`` (or just
    ``ExceptionType``). We don't hard-fail if it's shaped oddly.
    """
    last = tb_lines[-1] if tb_lines else ""
    if ": " in last:
        ename, evalue = last.split(": ", 1)
        return ename.strip(), evalue.strip()
    return last.strip(), ""


def run_notebook(path_in: str | Path, path_out: str | Path | None = None) -> dict:
    """Execute every code cell of ``path_in`` through :class:`AbaxShell`.

    Cells run in order in one shared shell, so bindings (and the workbook) persist
    across the notebook. Each executed code cell has its ``outputs`` replaced with
    freshly captured ``stream`` / ``execute_result`` / ``error`` outputs and its
    ``execution_count`` set.

    When ``path_out`` is given the executed notebook is written there (pass the
    same path as ``path_in`` to run in place); when it is ``None`` nothing is
    written — the executed notebook rides back in the summary for the caller to
    save or inspect. Returns a summary dict::

        {"notebook": <executed nb dict>, "path_in": str, "path_out": str | None,
         "cells": int,            # code cells executed
         "errors": int,           # code cells that raised
         "error_cells": [int],    # their indices within nb["cells"]
         "nbformat": bool}        # True if nbformat did the read/write
    """
    nb = _read(path_in)
    shell = AbaxShell()
    executed = 0
    error_indices: list[int] = []
    for index, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        result = shell.run_cell_block(_source_text(cell))
        cell["outputs"] = _cell_outputs(result)
        cell["execution_count"] = result["execution_count"]
        executed += 1
        if result["error"]:
            error_indices.append(index)

    if path_out is not None:
        _write(nb, path_out)

    return {
        "notebook": nb,
        "path_in": str(path_in),
        "path_out": str(path_out) if path_out is not None else None,
        "cells": executed,
        "errors": len(error_indices),
        "error_cells": error_indices,
        "nbformat": HAS_NBFORMAT,
    }
