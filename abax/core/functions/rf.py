"""RF / amateur-radio spreadsheet functions (backed by abax.core.science.rf).

SI base units (Hz, m, W, H, F). Registered into FUNCTIONS by the package
__init__ via RF_NAMES-style update kept in the registry.
"""

# ruff: noqa: F405  (names come from `from .helpers import *`)
from __future__ import annotations

from .helpers import *  # noqa: F403
from ..errors import CellError

# --- RF / amateur-radio functions (backed by core.science.rf) --------------
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


def _txline_z_component(part: str):
    """Real/imag part of a lossless-line input impedance ``Zin`` from the load
    resistance/reactance, characteristic impedance and electrical length (deg).
    Mirrors :func:`_ant_z_component` — keeps the formula layer real-valued by
    returning the parts separately (see ZINLINER / ZINLINEX)."""
    def wrapper(args):
        from ..science import rf_math as M
        try:
            r = _as_number(_arg(args, 0))
            x = _as_number(_arg(args, 1))
            z0 = _as_number(_arg(args, 2))
            elen = _as_number(_arg(args, 3))
        except (ValueError, TypeError):
            return CellError(CellError.VALUE)
        try:
            z = M.zin_line(complex(r, x), z0, elen)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
        return z.real if part == "r" else z.imag
    return wrapper


_R = _RF_REQUIRED


# --- circuit & radio-system math (core.science.circuits / radio_calc) -------

def _sci_numeric(module: str, name: str, spec: tuple):
    """Like :func:`_rf_numeric` for any ``core.science`` module: numeric args by
    ``spec`` (``_R`` = required, else the default), ``ValueError`` → ``#NUM!``."""
    def wrapper(args):
        import importlib

        mod = importlib.import_module(f"..science.{module}", __package__)
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
            return getattr(mod, name)(*vals)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
    return wrapper


def _z_from_args(args, start: int = 0) -> complex:
    """An impedance from the formula args, in either style:

    * one arg — an Excel complex string (``"75+25j"``, ``"50-25i"``) or a plain
      number (a pure resistance); or
    * two args — ``R`` and ``X`` as numbers.

    Raises ``ValueError`` for anything else (mapped to ``#VALUE!``).
    """
    from ..science.complexnum import ComplexError, parse

    a = _arg(args, start, None)
    b = _arg(args, start + 1, None)
    if a is None or a == "" or isinstance(a, CellError):
        raise ValueError("impedance is required")
    if b is None or b == "":
        if isinstance(a, str):
            try:
                return parse(a)
            except ComplexError as exc:
                raise ValueError(str(exc)) from exc
        return complex(_as_number(a), 0.0)
    return complex(_as_number(a), _as_number(b))


def _clean_part(x: float, scale: float) -> float:
    """Drop floating-point dust: parts below 1e-12 of |z| become 0, the rest
    are rounded to 12 significant digits so results read cleanly in a cell."""
    if abs(x) <= 1e-12 * scale:
        return 0.0
    return float(f"{x:.12g}")


def _fmt_z(z: complex) -> str:
    """A complex result as an Excel complex string with the ``j`` suffix
    (IMREAL / IMAGINARY / IMABS read it back)."""
    from ..science.complexnum import fmt

    scale = abs(z)
    return fmt(complex(_clean_part(z.real, scale), _clean_part(z.imag, scale)), "j")


def _z_real(fn_name: str):
    """Real-valued function of one impedance (``z`` string/number, or ``R, X``)."""
    def wrapper(args):
        from ..science import circuits

        try:
            z = _z_from_args(args)
        except (ValueError, TypeError):
            return CellError(CellError.VALUE)
        try:
            if fn_name == "abs":
                return abs(z)
            if fn_name == "conductance":
                return circuits.admittance(z).real
            if fn_name == "susceptance":
                return circuits.admittance(z).imag
            return getattr(circuits, fn_name)(z)
        except (ValueError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
    return wrapper


def _circ_admittance(args):
    from ..science import circuits

    try:
        z = _z_from_args(args)
    except (ValueError, TypeError):
        return CellError(CellError.VALUE)
    try:
        return _fmt_z(circuits.admittance(z))
    except (ValueError, ZeroDivisionError, OverflowError):
        return CellError(CellError.NUM)


def _circ_complex(fn_name: str, nargs: int):
    """A ``circuits`` function of ``nargs`` numbers that returns a complex
    impedance, surfaced as an Excel complex string."""
    def wrapper(args):
        from ..science import circuits

        if any(_arg(args, i, None) in (None, "") for i in range(nargs)):
            return CellError(CellError.VALUE)
        try:
            vals = [_as_number(args[i]) for i in range(nargs)]
        except (ValueError, TypeError):
            return CellError(CellError.VALUE)
        try:
            return _fmt_z(getattr(circuits, fn_name)(*vals))
        except (ValueError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
    return wrapper


def _circ_combine(fn_name: str):
    """Series / parallel combination over any mix of values and ranges."""
    def wrapper(args):
        from ..science import circuits

        err, nums = _numbers_checked(args)
        if err is not None:
            return err
        try:
            return getattr(circuits, fn_name)(nums)
        except (ValueError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
    return wrapper


def _rc_power_chain(args):
    """ERPW / EIRPW(power_w, gain_db, [loss_db, …]) — losses are positive dB."""
    from ..science import radio_calc

    if _arg(args, 0, None) in (None, "") or _arg(args, 1, None) in (None, ""):
        return CellError(CellError.VALUE)
    try:
        power = _as_number(args[0])
        gain = _as_number(args[1])
    except (ValueError, TypeError):
        return CellError(CellError.VALUE)
    err, losses = _numbers_checked(args[2:])
    if err is not None:
        return err
    try:
        return radio_calc.power_through_chain(power, gain, losses)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _rc_imd3(index: int):
    def wrapper(args):
        from ..science import radio_calc

        if _arg(args, 0, None) in (None, "") or _arg(args, 1, None) in (None, ""):
            return CellError(CellError.VALUE)
        try:
            f1, f2 = _as_number(args[0]), _as_number(args[1])
        except (ValueError, TypeError):
            return CellError(CellError.VALUE)
        return radio_calc.imd3_products(f1, f2)[index]
    return wrapper


def _rc_flagged(fn_name: str, nnum: int, flag_default: bool):
    """``nnum`` required numbers followed by an optional TRUE/FALSE flag."""
    def wrapper(args):
        from ..science import radio_calc

        if any(_arg(args, i, None) in (None, "") for i in range(nnum)):
            return CellError(CellError.VALUE)
        try:
            vals = [_as_number(args[i]) for i in range(nnum)]
        except (ValueError, TypeError):
            return CellError(CellError.VALUE)
        raw = _arg(args, nnum, None)
        flag = flag_default if raw in (None, "") else _truthy(raw)
        try:
            return getattr(radio_calc, fn_name)(*vals, flag)
        except (ValueError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
    return wrapper


# --- RF exposure (core.science.rf_exposure) ---------------------------------
# Frequencies arrive in Hz (SI, like every other RF function) and are converted
# to the MHz the FCC tables use. Power density is in mW/cm², the FCC unit.

def _rx_args(args, spec):
    """Parse ``spec`` entries: ("num", default|_R), ("tier", default) or
    ("text", default). Returns the values or a CellError."""
    vals = []
    for i, (kind, dflt) in enumerate(spec):
        raw = _arg(args, i, None)
        if isinstance(raw, CellError):
            return raw
        if raw is None or raw == "":
            if dflt is _RF_REQUIRED:
                return CellError(CellError.VALUE)
            vals.append(dflt)
        elif kind == "num":
            try:
                vals.append(_as_number(raw))
            except (ValueError, TypeError):
                return CellError(CellError.VALUE)
        else:
            # a misspelled tier or SAR kind is a bad argument, not a domain error
            from ..science import rf_exposure as X

            text = _text(raw)
            try:
                if kind == "tier":
                    X.normalize_tier(text)
                elif kind == "sarkind":
                    X.sar_limit("uncontrolled", text)
            except ValueError:
                return CellError(CellError.VALUE)
            vals.append(text)
    return vals


def _rx_call(fn_name: str, spec, *, hz_arg: int | None = None, none_is_na: bool = False,
             pick: str | None = None):
    def wrapper(args):
        from ..science import rf_exposure as X

        vals = _rx_args(args, spec)
        if isinstance(vals, CellError):
            return vals
        if hz_arg is not None:
            vals[hz_arg] = vals[hz_arg] / 1e6
        try:
            out = getattr(X, fn_name)(*vals)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
        if pick is not None:
            out = out[pick]
        if out is None and none_is_na:
            return CellError(CellError.NA)
        return out
    return wrapper


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
    "_txline_z_component",
    "_R",
    "_sci_numeric",
    "_z_from_args",
    "_fmt_z",
    "_z_real",
    "_circ_admittance",
    "_circ_complex",
    "_circ_combine",
    "_rc_power_chain",
    "_rc_imd3",
    "_rc_flagged",
    "_rx_call",
]
