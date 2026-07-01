"""The IPython/Jupyter rich-display protocol, in pure stdlib.

Collects an object's representations the way Jupyter does: ``_repr_mimebundle_``
first, then the per-format ``_repr_html_`` / ``_repr_markdown_`` / ``_repr_latex_``
/ ``_repr_svg_`` / ``_repr_json_`` hooks, always with a ``text/plain`` fallback.

:func:`mime_bundle` is what a rich frontend (a real Jupyter kernel, or a future
HTML console) would render. :func:`best_text` picks the most readable *plain-text*
form for the embedded console: a Markdown representation if the object offers one,
otherwise its ``repr``. Objects in abax that implement these hooks (e.g.
:class:`abax.core.sheet.Sheet`) therefore display nicely in Jupyter, IPython and
the abax console alike.
"""

from __future__ import annotations

from typing import Any

# (mime type, dunder method) in priority order for the per-format hooks.
_REPR_METHODS = (
    ("text/html", "_repr_html_"),
    ("text/markdown", "_repr_markdown_"),
    ("text/latex", "_repr_latex_"),
    ("image/svg+xml", "_repr_svg_"),
    ("application/json", "_repr_json_"),
)


def _safe_repr(obj: Any) -> str:
    try:
        return repr(obj)
    except Exception as exc:               # a broken __repr__ must not crash display
        return f"<unreprable {type(obj).__name__}: {exc}>"


def mime_bundle(obj: Any) -> dict:
    """Return a ``{mime_type: representation}`` bundle for ``obj``.

    Honors a ``_repr_mimebundle_`` method first (Jupyter's combined hook), then
    fills in any missing formats from the individual ``_repr_*_`` hooks, and always
    includes ``text/plain``. Hooks that raise or return ``None`` are skipped.
    """
    bundle: dict = {}
    combined = getattr(obj, "_repr_mimebundle_", None)
    if callable(combined):
        try:
            res = combined()
            if isinstance(res, tuple):     # (data, metadata)
                res = res[0]
            if isinstance(res, dict):
                bundle.update(res)
        except Exception:
            pass
    for mime, method_name in _REPR_METHODS:
        if mime in bundle:
            continue
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                value = method()
            except Exception:
                continue
            if value is not None:
                bundle[mime] = value
    bundle.setdefault("text/plain", _safe_repr(obj))
    return bundle


def best_text(obj: Any) -> str:
    """The most readable plain-text rendering for a text console.

    Prefers a Markdown representation (readable as-is in a terminal) over the bare
    ``repr``; never returns HTML/LaTeX, which a text console can't render.
    """
    bundle = mime_bundle(obj)
    md = bundle.get("text/markdown")
    if isinstance(md, str) and md.strip():
        return md
    return bundle.get("text/plain", _safe_repr(obj))
