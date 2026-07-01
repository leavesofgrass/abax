"""Validate Jupyter notebooks — against the real nbformat schema when available,
else with stdlib structural checks.

Engine layer: may use the optional ``nbformat`` package. When it is installed the
notebook is checked against the official JSON schema (the authoritative answer);
otherwise a focused set of structural checks catches the mistakes that actually
break notebooks — missing ``nbformat`` version, non-list ``cells``, a bad
``cell_type``, an absent ``source``, the per-cell ``id`` that **nbformat 4.5**
requires, and the ``outputs`` / ``execution_count`` keys a code cell must carry.

This guards abax's own ``.ipynb`` export (which must stay valid) and lets a user
check a notebook before relying on it. Returns a list of human-readable problems;
an empty list means valid.
"""

from __future__ import annotations

try:
    import nbformat as _nbformat
    HAS_NBFORMAT = True
except Exception:                          # nbformat is optional
    _nbformat = None
    HAS_NBFORMAT = False

_CELL_TYPES = {"code", "markdown", "raw"}


def validate_notebook(nb: dict) -> list[str]:
    """Return a list of validation problems for a notebook dict (empty = valid).

    Uses ``nbformat.validate`` when available, else the stdlib structural checks.
    """
    if HAS_NBFORMAT:
        try:
            _nbformat.validate(nb)
            return []
        except Exception as exc:           # ValidationError and friends
            return [str(exc).strip().splitlines()[0]]
    return _structural_checks(nb)


def _structural_checks(nb: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(nb, dict):
        return ["notebook is not a JSON object"]
    if nb.get("nbformat") != 4:
        errors.append(f"nbformat must be 4 (got {nb.get('nbformat')!r})")
    minor = nb.get("nbformat_minor", 0)
    if not isinstance(minor, int):
        errors.append("nbformat_minor must be an integer")
        minor = 0
    if not isinstance(nb.get("metadata"), dict):
        errors.append("metadata must be an object")
    cells = nb.get("cells")
    if not isinstance(cells, list):
        errors.append("cells must be a list")
        return errors
    for i, cell in enumerate(cells):
        if not isinstance(cell, dict):
            errors.append(f"cell {i}: not an object")
            continue
        ctype = cell.get("cell_type")
        if ctype not in _CELL_TYPES:
            errors.append(f"cell {i}: invalid cell_type {ctype!r}")
        if "source" not in cell:
            errors.append(f"cell {i}: missing 'source'")
        if minor >= 5 and ctype in _CELL_TYPES and "id" not in cell:
            errors.append(f"cell {i}: missing 'id' (required by nbformat 4.5)")
        if ctype == "code":
            if "outputs" not in cell:
                errors.append(f"cell {i}: code cell missing 'outputs'")
            if "execution_count" not in cell:
                errors.append(f"cell {i}: code cell missing 'execution_count'")
    return errors


def validate_workbook(workbook) -> list[str]:
    """Validate the notebook abax would export for ``workbook``."""
    from ..core.io.notebook_io import to_notebook

    return validate_notebook(to_notebook(workbook))
