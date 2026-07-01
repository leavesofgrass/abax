"""RF / ham-radio spreadsheet functions (backed by qcell.core.science.rf).

SI base units (Hz, m, W, H, F). Registered into FUNCTIONS by the package
__init__ via RF_NAMES-style update kept in the registry.
"""

# ruff: noqa: F405  (names come from `from .helpers import *`)
from __future__ import annotations

from .helpers import *  # noqa: F403
from ..errors import CellError

# --- RF / ham-radio functions (backed by core.science.rf) ------------------
# SI base units (Hz, m, W, H, F); see docs/rf-toolkit.md. The GUI presents
# metric + imperial, but the formula layer stays unit-neutral.

_RF_REQUIRED = object()


def _rf_numeric(name: str, spec: tuple):
    """Wrap a numeric ``core.science.rf`` function for the formula layer.

    ``spec`` is one entry per positional argument: ``_RF_REQUIRED`` for a required
    arg, or a default value for an optional one. Missing/blank required args →
    ``#VALUE!``; domain errors (rf raises ``ValueError``) → ``#NUM!``.
    """
    def wrapper(args):
        from ..science import rf as R

        vals = []
        for i, dflt in enumerate(spec):
            raw = _arg(args, i, None)
            if raw is None or raw == "":
                if dflt is _RF_REQUIRED:
                    return CellError(CellError.VALUE)
                vals.append(dflt)
            else:
                try:
                    vals.append(_as_number(raw))
                except (ValueError, TypeError):
                    return CellError(CellError.VALUE)
        try:
            return getattr(R, name)(*vals)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
    return wrapper


def _rf_gridsquare(args):
    from ..science import rf as R
    try:
        prec = int(_as_number(_arg(args, 2, 6)))
        return R.grid_square(_as_number(_arg(args, 0)), _as_number(_arg(args, 1)), prec)
    except (ValueError, TypeError):
        return CellError(CellError.NUM)


def _rf_grid_component(idx: int):
    def wrapper(args):
        from ..science import rf as R
        try:
            return R.grid_to_latlon(_text(_arg(args, 0)))[idx]
        except (ValueError, TypeError):
            return CellError(CellError.NUM)
    return wrapper


def _rf_grid_pair(fn: str):
    def wrapper(args):
        from ..science import rf as R
        try:
            return getattr(R, fn)(_text(_arg(args, 0)), _text(_arg(args, 1)))
        except (ValueError, TypeError):
            return CellError(CellError.NUM)
    return wrapper


def _rf_hamband(args):
    from ..science import rf_bands as B
    try:
        name = B.band_for_frequency(_as_number(_arg(args, 0)))
    except (ValueError, TypeError):
        return CellError(CellError.VALUE)
    return name if name is not None else CellError(CellError.NA)


def _rf_dxcc(args):
    from ..science import dxcc
    entity = dxcc.entity_for_call(_text(_arg(args, 0)))
    return entity if entity is not None else CellError(CellError.NA)


def _rf_ctcss_tone(args):
    from ..science import rf_bands as B
    try:
        return B.ctcss_tone(int(_as_number(_arg(args, 0))))
    except (ValueError, TypeError):
        return CellError(CellError.NUM)


def _rf_nearest_ctcss(args):
    from ..science import rf_bands as B
    try:
        return B.nearest_ctcss(_as_number(_arg(args, 0)))
    except (ValueError, TypeError):
        return CellError(CellError.VALUE)


def _ant_z_component(part: str):
    def wrapper(args):
        from ..science import antenna_impedance as A
        try:
            length = _as_number(_arg(args, 0))
            rad = _arg(args, 1, None)
            radius = _as_number(rad) if rad not in (None, "") else 1e-4
            z = A.dipole_input_impedance(length, radius)
        except (ValueError, TypeError, ZeroDivisionError):
            return CellError(CellError.NUM)
        return z.real if part == "r" else z.imag
    return wrapper


def _ant_radres(args):
    from ..science import antenna_impedance as A
    try:
        return A.radiation_resistance(_as_number(_arg(args, 0)))
    except (ValueError, TypeError):
        return CellError(CellError.NUM)


def _ant_resonant(args):
    from ..science import antenna_impedance as A
    try:
        rad = _arg(args, 0, None)
        radius = _as_number(rad) if rad not in (None, "") else 1e-4
        return A.resonant_length(radius)
    except (ValueError, TypeError):
        return CellError(CellError.NUM)


def _rfm_numeric(name: str, spec: tuple):
    """Like :func:`_rf_numeric` but backed by ``core.science.rf_math`` (the
    additional radio-math: resonance, Q/BW, inductor design, matching, Doppler)."""
    def wrapper(args):
        from ..science import rf_math as M

        vals = []
        for i, dflt in enumerate(spec):
            raw = _arg(args, i, None)
            if raw is None or raw == "":
                if dflt is _RF_REQUIRED:
                    return CellError(CellError.VALUE)
                vals.append(dflt)
            else:
                try:
                    vals.append(_as_number(raw))
                except (ValueError, TypeError):
                    return CellError(CellError.VALUE)
        try:
            return getattr(M, name)(*vals)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
    return wrapper


_R = _RF_REQUIRED


__all__ = [
    "_RF_REQUIRED",
    "_rf_numeric",
    "_rfm_numeric",
    "_rf_gridsquare",
    "_rf_grid_component",
    "_rf_grid_pair",
    "_rf_hamband",
    "_rf_dxcc",
    "_rf_ctcss_tone",
    "_rf_nearest_ctcss",
    "_ant_z_component",
    "_ant_radres",
    "_ant_resonant",
    "_R",
]
