"""Optional-dependency registry and ``--deps`` output.

Single source of truth for which optional packages are present and what
abax falls back to without them. Printed by ``abax --deps`` (a fast path
that must never create a venv).
"""

from __future__ import annotations

import importlib.util as _ilu

from . import _runtime as rt


def _has(module: str) -> bool:
    """True if *module* is importable (without importing it)."""
    try:
        return _ilu.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


OPTIONAL_DEPENDENCIES = {
    "msgspec": {
        "available": rt._HAS_MSGSPEC,
        "fallback": "stdlib json (slower, no schema validation)",
        "purpose": "fast settings/state serialization",
    },
    "platformdirs": {
        "available": rt._HAS_PLATFORMDIRS,
        "fallback": "stdlib path logic",
        "purpose": "cross-platform config/data/cache directories",
    },
    "openpyxl": {
        "available": rt._HAS_OPENPYXL,
        "fallback": "CSV / native JSON only (no .xlsx import/export)",
        "purpose": "Excel import and export",
    },
    "py7zr": {
        "available": _has("py7zr"),
        "fallback": "zip / tar archives only (no .7z create/extract/open)",
        "purpose": "7-Zip (.7z) archives in the file manager",
    },
    "Qt (PySide6/PyQt6)": {
        "available": rt._HAS_QT,
        "fallback": "TUI / CLI only",
        "purpose": "desktop GUI (PySide6 preferred; PyQt6 also works)",
    },
    "textual": {
        "available": rt._HAS_TEXTUAL,
        "fallback": "curses TUI",
        "purpose": "rich async TUI",
    },
    "numpy": {
        "available": _has("numpy"),
        "fallback": "pure-Python core engines (np absent from the console)",
        "purpose": "fast arrays / linear algebra in the Python console",
    },
    "pandas": {
        "available": _has("pandas"),
        "fallback": "stdlib + core engines (no DataFrames in the console)",
        "purpose": "DataFrames & data wrangling (sheet_to_df / df_to_sheet)",
    },
    "scipy": {
        "available": _has("scipy"),
        "fallback": "abax core stats engines",
        "purpose": "scientific computing — scipy.stats / optimize / signal",
    },
    "statsmodels": {
        "available": _has("statsmodels"),
        "fallback": "abax core regression only",
        "purpose": "regression, GLM, ANOVA, time series, biostatistics",
    },
    "scikit-learn": {
        "available": _has("sklearn"),
        "fallback": "abax core ML engines (ml/trees/cluster/gmm)",
        "purpose": "machine learning toolkit (sklearn)",
    },
    "lifelines": {
        "available": _has("lifelines"),
        "fallback": "no survival analysis",
        "purpose": "survival analysis / Kaplan–Meier / Cox (biostatistics)",
    },
    "pingouin": {
        "available": _has("pingouin"),
        "fallback": "scipy.stats / statsmodels",
        "purpose": "clean statistics API with effect sizes & power",
    },
    "scikit-survival": {
        "available": _has("sksurv"),
        "fallback": "lifelines",
        "purpose": "ML-based survival analysis (random survival forests, etc.)",
    },
    "pymc": {
        "available": _has("pymc"),
        "fallback": "no probabilistic programming",
        "purpose": "Bayesian / probabilistic programming (MCMC)",
    },
    "PyNEC": {
        "available": _has("PyNEC"),
        "fallback": "built-in method-of-moments antenna solver",
        "purpose": "reference-grade NEC antenna field solving",
    },
    "pyreadstat": {
        "available": _has("pyreadstat"),
        "fallback": "no Stata (.dta) / SPSS (.sav) import",
        "purpose": "read Stata / SPSS statistical data files",
    },
}


def format_deps() -> str:
    lines = [f"abax optional dependencies (Python {rt.PY_VERSION.major}.{rt.PY_VERSION.minor}):", ""]
    width = max(len(n) for n in OPTIONAL_DEPENDENCIES)
    for name, info in OPTIONAL_DEPENDENCIES.items():
        mark = "OK " if info["available"] else "-- "
        status = "available" if info["available"] else f"missing  (fallback: {info['fallback']})"
        lines.append(f"  [{mark}] {name.ljust(width)}  {status}")
    # External tool (not a Python package): pandoc for LaTeX → MathML equations.
    try:
        from .core import pandoc as _pandoc

        has_pandoc = _pandoc.available()
    except Exception:
        has_pandoc = False
    pmark = "OK " if has_pandoc else "-- "
    pstat = "available" if has_pandoc else "missing  (fallback: built-in subset MathML)"
    lines.append(f"  [{pmark}] {'pandoc'.ljust(width)}  {pstat}")
    # True PTY terminal: pywinpty (Windows) / os.openpty (POSIX) + pyte.
    try:
        from .core.ptyterm import pty_available

        has_pty = pty_available()
    except Exception:
        has_pty = False
    ptymark = "OK " if has_pty else "-- "
    ptystat = "available" if has_pty else "missing  (fallback: line-oriented terminal)"
    lines.append(f"  [{ptymark}] {'PTY (pyte)'.ljust(width)}  {ptystat}  (true terminal)")
    lines.append("")
    try:
        from . import autodeps

        present = sum(1 for _pip, mod in autodeps.ALL if autodeps.installed(mod))
        on = "on" if autodeps.enabled() else "off"
        lines.append(f"  auto-install: {on}  ({present}/{len(autodeps.ALL)} optional "
                     "packages present; run 'abax deps' to fetch the rest)")
    except Exception:
        pass
    lines.append("")
    lines.append(f"  config: {rt.CONFIG_DIR}")
    lines.append(f"  data:   {rt.DATA_DIR}")
    lines.append(f"  cache:  {rt.CACHE_DIR}")
    lines.append(f"  log:    {rt.LOG_DIR}")
    return "\n".join(lines)
