"""Built-in spreadsheet functions — the two registries.

* :data:`FUNCTIONS` — eager functions; each receives a list of evaluated args
  (a range arrives as a :class:`RangeValue`; aggregates flatten via
  :func:`_flatten`).
* :data:`LAZY_FUNCTIONS` — control-flow (IF/IFERROR/IFS/SWITCH/CHOOSE); each
  receives ``(arg_nodes, ev)`` so untaken branches never run.

Implementations live in :mod:`.helpers`, :mod:`.builtins` and :mod:`.rf`;
this module assembles the registries. User macros extend FUNCTIONS at runtime.
"""

# ruff: noqa: F405  (names come from the `import *` lines below)
from __future__ import annotations

import math
from typing import Any, Callable

from .builtins import *  # noqa: F403
from .helpers import *  # noqa: F403
from .rf import *  # noqa: F403

# --- registries ------------------------------------------------------------

FUNCTIONS: dict[str, Callable[[list], Any]] = {
    # aggregate
    "SUM": _sum, "SUMSQ": _sumsq, "AVERAGE": _average, "AVG": _average,
    "COUNT": _count, "COUNTA": _counta, "COUNTBLANK": _countblank,
    "MIN": _min, "MAX": _max, "MEDIAN": _median, "MODE": _mode, "PRODUCT": _product,
    "STDEV": _stdev, "STDEVP": _stdevp, "VAR": _var, "VARP": _varp,
    "GEOMEAN": _geomean, "HARMEAN": _harmean,
    "PERCENTILE": _percentile, "QUARTILE": _quartile,
    "CORREL": _correl, "COVAR": _covar,
    "SLOPE": _slope, "INTERCEPT": _intercept, "RSQ": _rsq, "FORECAST": _forecast,
    # complex numbers
    "COMPLEX": _complex_build, "IMSUM": _c_variadic("im_sum"),
    "IMPRODUCT": _c_variadic("im_product"), "IMSUB": _c_binary("im_sub"),
    "IMDIV": _c_binary("im_div"), "IMABS": _c_unary("im_abs"),
    "IMREAL": _c_unary("im_real"), "IMAGINARY": _c_unary("im_imaginary"),
    "IMCONJUGATE": _c_unary("im_conjugate"), "IMARGUMENT": _c_unary("im_argument"),
    "IMSQRT": _c_unary("im_sqrt"), "IMEXP": _c_unary("im_exp"), "IMLN": _c_unary("im_ln"),
    "IMSIN": _c_unary("im_sin"), "IMCOS": _c_unary("im_cos"), "IMPOWER": _impower,
    # matrix (scalar)
    "MDETERM": _mdeterm,
    # units
    "CONVERT": _convert,
    # signal / data
    "INTERP": _interp, "RMS": _rms,
    # statistics
    "SKEW": _skew, "KURT": _kurt, "TTEST": _ttest,
    "NORMSDIST": _normsdist, "NORMSINV": _normsinv,
    # distribution functions (normal / t / F / chi-square) + confidence interval
    "NORMDIST": _normdist, "NORMINV": _norminv,
    "TDIST": _tdist, "TINV": _tinv,
    "FDIST": _fdist, "FINV": _finv,
    "CHIDIST": _chidist, "CHIINV": _chiinv,
    "CONFIDENCE": _confidence,
    "LARGE": _large, "SMALL": _small, "RANK": _rank,
    "SUMPRODUCT": _sumproduct,
    # conditional aggregate
    "SUMIF": _sumif, "COUNTIF": _countif, "AVERAGEIF": _averageif,
    # math
    "ROUND": _round, "ROUNDUP": _roundup, "ROUNDDOWN": _rounddown,
    "CEILING": _ceiling, "FLOOR": _floor, "TRUNC": _trunc, "INT": _int,
    "ABS": _abs, "SIGN": _sign, "SQRT": _sqrt, "POWER": _power,
    "EXP": _exp, "LN": _ln, "LOG": _log, "LOG10": _log10, "MOD": _mod,
    "GCD": _gcd, "LCM": _lcm, "FACT": _fact, "PI": _pi,
    "RAND": _rand, "RANDBETWEEN": _randbetween,
    "SIN": _trig(math.sin), "COS": _trig(math.cos), "TAN": _trig(math.tan),
    "ASIN": _trig(math.asin), "ACOS": _trig(math.acos), "ATAN": _trig(math.atan),
    "ATAN2": _atan2, "DEGREES": _trig(math.degrees), "RADIANS": _trig(math.radians),
    # lookup
    "VLOOKUP": _vlookup, "HLOOKUP": _hlookup, "MATCH": _match, "INDEX": _index,
    # text
    "CONCAT": _concat, "CONCATENATE": _concat, "LEN": _len,
    "LEFT": _left, "RIGHT": _right, "MID": _mid,
    "UPPER": _upper, "LOWER": _lower, "PROPER": _proper, "TRIM": _trim,
    "FIND": _find, "SEARCH": _search, "REPLACE": _replace, "SUBSTITUTE": _substitute,
    "REPT": _rept, "EXACT": _exact, "CHAR": _char, "CODE": _code,
    "TEXT": _text_fn, "VALUE": _value, "T": _t,
    # date/time
    "NOW": _now, "TODAY": _today, "DATE": _date,
    "YEAR": _date_part(lambda d: d.year), "MONTH": _date_part(lambda d: d.month),
    "DAY": _date_part(lambda d: d.day), "HOUR": _date_part(lambda d: d.hour),
    "MINUTE": _date_part(lambda d: d.minute), "SECOND": _date_part(lambda d: d.second),
    "WEEKDAY": _weekday, "DATEDIF": _datedif, "EDATE": _edate, "DAYS": _days,
    # logical / info
    "AND": _and, "OR": _or, "XOR": _xor, "NOT": _not, "TRUE": _true, "FALSE": _false,
    "NA": _na, "ISBLANK": _isblank, "ISNUMBER": _isnumber, "ISTEXT": _istext,
    "ISLOGICAL": _islogical, "ISERROR": _iserror,
}

LAZY_FUNCTIONS: dict[str, Callable] = {
    "IF": _lazy_if,
    "IFERROR": _lazy_iferror,
    "IFNA": _lazy_ifna,
    "IFS": _lazy_ifs,
    "SWITCH": _lazy_switch,
    "CHOOSE": _lazy_choose,
}



FUNCTIONS.update({
    "DBM2W": _rf_numeric("dbm_to_w", (_R,)),
    "W2DBM": _rf_numeric("w_to_dbm", (_R,)),
    "DBW2W": _rf_numeric("dbw_to_w", (_R,)),
    "W2DBW": _rf_numeric("w_to_dbw", (_R,)),
    "DB2RATIO": _rf_numeric("db_to_ratio", (_R,)),
    "RATIO2DB": _rf_numeric("ratio_to_db", (_R,)),
    "DBADD": _rf_numeric("db_add", (_R, _R)),
    "DBUV2DBM": _rf_numeric("dbuv_to_dbm", (_R, 50.0)),
    "SUNIT2DBM": _rf_numeric("s_unit_to_dbm", (_R,)),
    "NOISEFLOOR": _rf_numeric("noise_floor_dbm", (_R, 290.0)),
    "NF2NT": _rf_numeric("nf_to_noise_temp", (_R, 290.0)),
    "NT2NF": _rf_numeric("noise_temp_to_nf", (_R, 290.0)),
    "WAVELENGTH": _rf_numeric("wavelength", (_R, 1.0)),
    "WL2FREQ": _rf_numeric("freq_from_wavelength", (_R, 1.0)),
    "DIPOLELEN": _rf_numeric("dipole_length", (_R, 0.95)),
    "MONOPOLELEN": _rf_numeric("monopole_length", (_R, 0.95)),
    "XL": _rf_numeric("reactance_inductive", (_R, _R)),
    "XC": _rf_numeric("reactance_capacitive", (_R, _R)),
    "RESFREQ": _rf_numeric("resonant_freq", (_R, _R)),
    "VSWR": _rf_numeric("vswr_from_z", (_R, 50.0)),
    "VSWRG": _rf_numeric("vswr_from_gamma", (_R,)),
    "REFLCOEF": _rf_numeric("reflection_coefficient", (_R, 50.0)),
    "RETURNLOSS": _rf_numeric("return_loss_db", (_R,)),
    "MISMATCHLOSS": _rf_numeric("mismatch_loss_db", (_R,)),
    "VSWR2GAMMA": _rf_numeric("vswr_to_gamma", (_R,)),
    "Z0COAX": _rf_numeric("z0_coax", (_R, _R, 1.0)),
    "VELFACTOR": _rf_numeric("velocity_factor", (_R,)),
    "FSPL": _rf_numeric("fspl_db", (_R, _R)),
    "FRIIS": _rf_numeric("friis_rx_dbm", (_R, _R, _R, _R, _R)),
    "EIRP": _rf_numeric("eirp_dbm", (_R, _R, 0.0)),
    "FRESNEL": _rf_numeric("fresnel_radius", (_R, _R, _R, 1)),
    "RADIOHORIZON": _rf_numeric("radio_horizon_km", (_R, 0.0)),
    "SKINDEPTH": _rf_numeric("skin_depth", (_R, 5.8e7, 1.0)),
    "DBI2DBD": _rf_numeric("dbi_to_dbd", (_R,)),
    "DBD2DBI": _rf_numeric("dbd_to_dbi", (_R,)),
    "GRIDSQUARE": _rf_gridsquare,
    "GRIDLAT": _rf_grid_component(0),
    "GRIDLON": _rf_grid_component(1),
    "GRIDDIST": _rf_grid_pair("grid_distance_km"),
    "GRIDBEARING": _rf_grid_pair("grid_bearing_deg"),
    "HAMBAND": _rf_hamband,
    "DXCC": _rf_dxcc,
    "CTCSSTONE": _rf_ctcss_tone,
    "NEARESTCTCSS": _rf_nearest_ctcss,
    "DIPOLER": _ant_z_component("r"),
    "DIPOLEX": _ant_z_component("x"),
    "RADRESIST": _ant_radres,
    "RESONANTLEN": _ant_resonant,
})

# Additional radio math (resonance, Q/BW, inductor design, matching, antennas,
# Doppler) — backed by core.science.rf_math.
FUNCTIONS.update({
    "CFROMXC": _rfm_numeric("capacitance_from_reactance", (_R, _R)),
    "LFROMXL": _rfm_numeric("inductance_from_reactance", (_R, _R)),
    "RESONANTC": _rfm_numeric("resonant_capacitance", (_R, _R)),
    "RESONANTL": _rfm_numeric("resonant_inductance", (_R, _R)),
    "QBW": _rfm_numeric("q_from_bandwidth", (_R, _R)),
    "BWQ": _rfm_numeric("bandwidth_from_q", (_R, _R)),
    "AIRCOILL": _rfm_numeric("air_core_inductance", (_R, _R, _R)),
    "AIRCOILN": _rfm_numeric("air_core_turns", (_R, _R, _R)),
    "TOROIDL": _rfm_numeric("toroid_inductance", (_R, _R)),
    "TOROIDN": _rfm_numeric("toroid_turns", (_R, _R)),
    "QWMATCH": _rfm_numeric("quarter_wave_z0", (_R, _R)),
    "SWRPWR": _rfm_numeric("swr_from_power", (_R, _R)),
    "LOOPLEN": _rfm_numeric("loop_length", (_R,)),
    "DISHGAIN": _rfm_numeric("parabolic_gain_dbi", (_R, _R, 0.55)),
    "DISHBW": _rfm_numeric("parabolic_beamwidth_deg", (_R, _R)),
    "DOPPLER": _rfm_numeric("doppler_shift_hz", (_R, _R)),
})

# Modern array functions (UNIQUE/SORT/FILTER/SEQUENCE/TRANSPOSE/VSTACK/TAKE/…)
# live in their own module and register themselves here. They return arrays that
# *spill* when they are a cell's top-level result (see abax.core.spill and the
# spill engine on Sheet) and compose inside aggregates via _flatten.
from .. import arrayfuncs as _arrayfuncs  # noqa: E402

_arrayfuncs.register(FUNCTIONS)

# Excel/Gnumeric-parity function packs — each a pure-stdlib core module that
# registers its own names (math/trig/info, statistics + distributions, text +
# date/time, financial, engineering + database). Optional at import: a missing
# pack is skipped so a partial checkout still loads.
for _pack in ("math_fns", "stats_dist", "text_datetime_fns", "finance_fns",
              "finance_bonds", "engineering_fns", "gnumeric_fns", "gnumeric_math",
              "gnumeric_stats", "excel_modern", "dist_dotted"):
    try:
        _mod = __import__(f"abax.core.{_pack}", fromlist=["register"])
        _mod.register(FUNCTIONS)
    except Exception:  # noqa: BLE001 — a broken/absent pack must not kill the engine
        pass

# Modern dotted aliases (Excel 2010+) for functions that already exist under their
# legacy name with an identical signature — point both names at the same callable.
for _dotted, _canon in {
    "STDEV.S": "STDEV", "STDEV.P": "STDEVP", "VAR.S": "VAR", "VAR.P": "VARP",
    "MODE.SNGL": "MODE", "PERCENTILE.INC": "PERCENTILE", "QUARTILE.INC": "QUARTILE",
    "COVARIANCE.P": "COVAR", "NORM.DIST": "NORMDIST", "NORM.INV": "NORMINV",
    "NORM.S.INV": "NORMSINV", "CONFIDENCE.NORM": "CONFIDENCE",
    "CHISQ.DIST.RT": "CHIDIST", "CHISQ.INV.RT": "CHIINV",
    "F.DIST.RT": "FDIST", "F.INV.RT": "FINV",
    "FORECAST.LINEAR": "FORECAST", "SKEW.P": "SKEWP",
    "GAMMALN.PRECISE": "GAMMALN",
}.items():
    if _canon in FUNCTIONS:
        FUNCTIONS[_dotted] = FUNCTIONS[_canon]

# Context/reference functions (ROW, COLUMN, OFFSET, INDIRECT, ...) use a third
# calling convention: they receive the raw argument AST plus an EvalContext (the
# calling cell + resolver), so they can see references rather than values.
CONTEXT_FUNCTIONS: dict = {}
try:
    from .. import reffuncs as _reffuncs  # noqa: E402
    _reffuncs.register(CONTEXT_FUNCTIONS)
except Exception:  # noqa: BLE001
    pass

# LET / LAMBDA and the functional array helpers (MAP/REDUCE/SCAN/BYROW/BYCOL/
# MAKEARRAY) also use the context convention — they evaluate sub-expressions
# under name bindings carried on the EvalContext.
try:
    from .. import lambda_fns as _lambda_fns  # noqa: E402
    _lambda_fns.register(CONTEXT_FUNCTIONS)
except Exception:  # noqa: BLE001
    pass
