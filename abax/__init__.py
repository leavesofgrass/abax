"""abax — a keyboard-first statistics and data-science workstation.

The package top level doubles as the public automation API::

    import abax
    with abax.open("book.abax") as book:
        book["Sheet1"]["A1"] = "=SUM(B1:B3)"
        print(book["Sheet1"]["A1"])
        book.save()

See :mod:`abax.api` (and docs/automation.md) for the full surface.
"""

__version__ = "0.1.15"
__all__ = ["__version__", "Book", "Sheet", "new", "open"]

_API_NAMES = ("Book", "Sheet", "new", "open")


def __getattr__(name: str):
    """Lazily expose the automation API (PEP 562).

    ``import abax`` must stay near-free (tools read ``__version__`` in tight
    paths), but :mod:`abax.api` pulls the whole engine (~1 s). Deferring the
    import to first attribute use keeps both properties. ``abax.open`` shadows
    the builtin deliberately — module-scoped only.
    """
    if name in _API_NAMES:
        from . import api

        return getattr(api, name)
    raise AttributeError(f"module 'abax' has no attribute {name!r}")
