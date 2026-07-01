"""The Python-console namespace, factored out so it can be built around any
``Workbook`` — the live one (in-process) or a child process's copy (the sandbox
worker, :mod:`qcell.console_worker`).

Pure stdlib + ``qcell.core`` (no Qt), so it imports cleanly in a headless child.
``build_namespace`` binds the workbook-facing helpers to the given workbook and a
``refresh`` callback (a no-op in the worker; the GUI refresh in-process).
"""

from __future__ import annotations

import types


class _LazyModule:
    """A stand-in that imports its module on first attribute access, so heavy
    optional packages (pymc, scikit-survival) can sit in the namespace without
    paying their import cost until actually used."""

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_mod", None)

    def _load(self):
        mod = object.__getattribute__(self, "_mod")
        if mod is None:
            import importlib

            mod = importlib.import_module(object.__getattribute__(self, "_name"))
            object.__setattr__(self, "_mod", mod)
        return mod

    def __getattr__(self, attr):
        return getattr(self._load(), attr)

    def __repr__(self) -> str:
        name = object.__getattribute__(self, "_name")
        return f"<module {name!r} (qcell lazy — imports on first use)>"


def _opt(name: str):
    """Import a scientific package if present, else None."""
    try:
        return __import__(name)
    except Exception:
        return None


def build_namespace(workbook, refresh=None) -> dict:
    """Build the console namespace bound to ``workbook``.

    ``refresh`` (if given) is called by helpers that write cells; in the sandbox
    worker it is a no-op (the parent refreshes after applying the returned
    workbook), in-process it is the GUI's ``refresh_table``.
    """
    if refresh is None:
        def refresh():  # noqa: E306
            return None

    sheet_of = lambda: workbook.sheet  # noqa: E731
    doc = types.SimpleNamespace(workbook=workbook, mark_dirty=lambda: None)

    def cell(ref):
        return workbook.sheet.get(ref)

    def put(ref, value):
        workbook.sheet.set(ref, value if isinstance(value, str) else str(value))

    def read_matrix(rng):
        """Read a range like 'A1:C3' into a list-of-lists of floats."""
        from .reference import parse_range

        r1, c1, r2, c2 = parse_range(rng)
        sh = workbook.sheet
        return [[float(sh.get_value(r, c) or 0) for c in range(c1, c2 + 1)]
                for r in range(r1, r2 + 1)]

    def write_matrix(top_left, mat):
        """Write a list-of-lists starting at a cell like 'E1'."""
        from .reference import parse_a1

        r0, c0 = parse_a1(top_left)
        sh = workbook.sheet
        for i, row in enumerate(mat):
            for j, v in enumerate(row):
                sh.set_cell(r0 + i, c0 + j, repr(v))
        refresh()

    def sheet_to_df(rng=None, header=True):
        """Read the sheet (or an 'A1:C9' range) into a pandas DataFrame."""
        if _pd is None:
            raise RuntimeError("pandas is not installed")
        from .reference import parse_range

        sh = workbook.sheet
        if rng:
            r1, c1, r2, c2 = parse_range(rng)
        else:
            nr, nc = sh.used_bounds()
            r1, c1, r2, c2 = 0, 0, nr - 1, nc - 1
        rows = [[sh.get_value(r, c) for c in range(c1, c2 + 1)]
                for r in range(r1, r2 + 1)]
        if header and rows:
            return _pd.DataFrame(rows[1:], columns=[str(x) for x in rows[0]])
        return _pd.DataFrame(rows)

    def df_to_sheet(df, top_left="A1", header=True):
        """Write a pandas DataFrame to the sheet starting at ``top_left``."""
        from .reference import parse_a1

        r0, c0 = parse_a1(top_left)
        sh = workbook.sheet
        r = r0
        if header:
            for j, name in enumerate(df.columns):
                sh.set_cell(r, c0 + j, str(name))
            r += 1
        for i in range(len(df)):
            for j, v in enumerate(df.iloc[i]):
                sh.set_cell(r + i, c0 + j, "" if v is None else str(v))
        refresh()

    def sql(query):
        """Run SQL over the workbook's sheets; returns ``(columns, rows)``."""
        from . import sqlsheets

        return sqlsheets.run_sql({s.name: s for s in workbook.sheets}, query)

    def describe():
        """Profile every column of the active sheet (list of stat dicts)."""
        from . import profile

        return profile.profile_sheet(workbook.sheet)

    from . import profile, sqlsheets
    from .calc import algebraic, ti_engine
    from .calc.rpn import RPN
    from .graphing import compile_expr
    from .io import adif_io
    from .science import (
        antenna,
        antenna_impedance,
        bayes,
        chartsvg,
        cluster,
        complexnum,
        dxcc,
        eigen,
        fft,
        filters,
        financial,
        gmm,
        interp,
        matrix,
        metrics,
        ml,
        mom,
        nec,
        numeric,
        ode,
        ode_implicit,
        resynth,
        rf,
        rf_bands,
        signal,
        spectral,
        stats,
        trees,
        units,
        wire_mom,
    )

    _np = _opt("numpy")
    _pd = _opt("pandas")
    _scipy = _opt("scipy")
    _sklearn = _opt("sklearn")
    _pingouin = _opt("pingouin")
    _pymc = _LazyModule("pymc")
    _sksurv = _LazyModule("sksurv")
    try:
        import statsmodels.api as _sm
    except Exception:
        _sm = None

    return {
        "doc": doc, "wb": workbook, "sheet": sheet_of, "cell": cell, "put": put,
        "refresh": refresh,
        "rpn": RPN(),
        "matrix": matrix, "eigen": eigen, "units": units, "numeric": numeric,
        "complexnum": complexnum, "fft": fft, "interp": interp, "signal": signal,
        "spectral": spectral, "filters": filters, "ode": ode,
        "ode_implicit": ode_implicit, "resynth": resynth, "stats": stats,
        "cluster": cluster, "ml": ml, "trees": trees, "bayes": bayes,
        "metrics": metrics, "gmm": gmm, "financial": financial,
        "rf": rf, "rf_bands": rf_bands, "antenna": antenna,
        "antenna_impedance": antenna_impedance, "mom": mom, "wire_mom": wire_mom,
        "nec": nec,
        "sql": sql, "sqlsheets": sqlsheets, "profile": profile,
        "describe": describe, "chartsvg": chartsvg, "dxcc": dxcc, "adif": adif_io,
        "algebraic": algebraic, "ti_engine": ti_engine,
        "np": _np, "numpy": _np, "pd": _pd, "pandas": _pd, "scipy": _scipy,
        "sm": _sm, "statsmodels": _sm, "sklearn": _sklearn,
        "pingouin": _pingouin, "pg": _pingouin, "pymc": _pymc, "pm": _pymc,
        "sksurv": _sksurv, "compile_expr": compile_expr,
        "read_matrix": read_matrix, "write_matrix": write_matrix,
        "sheet_to_df": sheet_to_df, "df_to_sheet": df_to_sheet,
        "__name__": "qcell_console",
    }
