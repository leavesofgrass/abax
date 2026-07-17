"""Function metadata — categories, guidance blurbs, plain-English descriptions.

The Formula manager (GUI) and function browser (TUI) need more than a name and
a signature: *which family a function belongs to* and *what it is for*. This
module derives that for every registered function (built-ins **and** UDFs):

* **Category** — resolved by name first (curated lists below, matching the
  Excel-parity groupings the coverage dashboard uses), then by the module the
  function was registered from, then "Other". UDFs land in "User-defined".
* **Description** — a hand-written plain-English line for the everyday
  functions; then a line harvested from ``docs/formula-reference.md`` (the
  generated :mod:`._funcmeta_generated`, regenerate with
  ``py scripts/gen_funcmeta_descriptions.py``); anything else falls back to
  the function's docstring first line (when it isn't just a signature), else
  a category-level hint.

Pure stdlib (core). The data is deliberately compact: category lists name only
functions whose *module* wouldn't already place them correctly.
"""

from __future__ import annotations

from ._funcmeta_generated import GENERATED_DESCRIPTIONS
from .completion import function_names, signature

# --- categories -------------------------------------------------------------

# key -> (label, blurb). The blurb is the "what is this family for" guidance
# shown by the Formula manager when a category is selected.
CATEGORIES: dict[str, tuple[str, str]] = {
    "math": ("Math & trig",
             "Arithmetic, rounding, logarithms, combinatorics, and trigonometry "
             "— everyday numeric work on cells and ranges."),
    "stats": ("Statistics",
              "Descriptive statistics, distributions, hypothesis tests, and "
              "regression — summarize and analyze data ranges."),
    "text": ("Text",
             "Build, split, clean, and format strings — join cells, extract "
             "pieces, change case, substitute."),
    "datetime": ("Date & time",
                 "Serial dates and times: today/now, arithmetic across days and "
                 "months, business-day and weekday calculations."),
    "logical": ("Logical & information",
                "Conditions and tests: IF-family branching, error handling, and "
                "cell/type inspection."),
    "lookup": ("Lookup & reference",
               "Find values in tables and ranges — the VLOOKUP/XLOOKUP family, "
               "INDEX/MATCH, and reference helpers."),
    "arrays": ("Dynamic arrays",
               "Functions that return whole ranges and spill into neighbouring "
               "cells: filter, sort, sequence, stack, reshape."),
    "financial": ("Financial",
                  "Time-value-of-money, loan and annuity math, depreciation, "
                  "and bond/security calculations."),
    "engineering": ("Engineering",
                    "Complex numbers, number-base conversions, unit conversion, "
                    "and Bessel/error functions."),
    "database": ("Database",
                 "The D-functions: aggregate a table by criteria rows, like a "
                 "tiny query language over a range."),
    "rf": ("Radio & RF",
           "Amateur-radio and RF engineering: dB conversions, antennas, "
           "transmission lines, propagation, grid squares, and logging."),
    "lambda": ("LET & LAMBDA",
               "Functional building blocks: name intermediate values, define "
               "reusable in-formula functions, map/reduce over ranges."),
    "regex": ("Regular expressions",
              "Pattern matching over text: test, extract, and replace with "
              "regular expressions."),
    "live": ("Connected data",
             "Formulas that read the outside world: REST endpoints, WebSocket "
             "feeds, and closed-workbook references. Off by default; enable "
             "via Tools → live data."),
    "user": ("User-defined",
             "Functions registered by your macros or init.py — they behave "
             "like built-ins and autocomplete everywhere."),
    "other": ("Specialty",
              "Everything else: in-cell visuals and niche compatibility "
              "functions."),
}

# Module suffix -> category key (the cheap, automatic pass).
_MODULE_CATEGORIES: dict[str, str] = {
    "math_fns": "math", "gnumeric_math": "math",
    "stats_dist": "stats", "gnumeric_stats": "stats", "dist_dotted": "stats",
    "text_datetime_fns": "text",
    "finance_fns": "financial", "finance_bonds": "financial",
    "engineering_fns": "engineering",
    "reffuncs": "lookup",
    "arrayfuncs": "arrays",
    "lambda_fns": "lambda",
    "regex_fns": "regex",
    "rf": "rf", "hamlog": "rf",
    "livefuncs": "live", "livearray": "live",
    "sparkcell": "other",
}

# Name -> category overrides: functions whose module wouldn't place them right
# (mostly the builtins grab-bag and the mixed gnumeric/excel_modern packs).
_NAME_LISTS: dict[str, tuple[str, ...]] = {
    "math": ("ABS", "SIGN", "SQRT", "POWER", "EXP", "LN", "LOG", "LOG10", "MOD",
             "GCD", "LCM", "FACT", "COMBIN", "PERMUT", "PI", "PRODUCT", "SUM",
             "SUMSQ", "SUMPRODUCT", "ROUND", "ROUNDUP", "ROUNDDOWN", "MROUND",
             "CEILING", "FLOOR", "TRUNC", "INT", "EVEN", "ODD", "SIN", "COS",
             "TAN", "ASIN", "ACOS", "ATAN", "ATAN2", "SINH", "COSH", "TANH",
             "DEGREES", "RADIANS", "RAND", "RANDBETWEEN", "SUMIF", "SUMIFS",
             "SUBTOTAL", "AGGREGATE", "SERIESSUM", "SQRTPI"),
    "stats": ("AVERAGE", "AVERAGEA", "AVERAGEIF", "AVERAGEIFS", "MEDIAN", "MODE",
              "COUNT", "COUNTA", "COUNTBLANK", "COUNTIF", "COUNTIFS", "MAX",
              "MAXA", "MAXIFS", "MIN", "MINA", "MINIFS", "LARGE", "SMALL",
              "RANK", "PERCENTILE", "PERCENTRANK", "QUARTILE", "STDEV", "STDEVP",
              "VAR", "VARP", "GEOMEAN", "HARMEAN", "TRIMMEAN", "DEVSQ", "AVEDEV",
              "SKEW", "KURT", "STANDARDIZE", "CORREL", "COVAR", "FREQUENCY",
              "MODE.MULT", "TREND", "GROWTH", "LINEST", "LOGEST"),
    "text": ("CONCAT", "CONCATENATE", "TEXTJOIN", "TEXTSPLIT", "LEFT", "RIGHT",
             "MID", "LEN", "TRIM", "CLEAN", "UPPER", "LOWER", "PROPER",
             "SUBSTITUTE", "REPLACE", "REPT", "FIND", "SEARCH", "EXACT", "TEXT",
             "VALUE", "NUMBERVALUE", "CHAR", "CODE", "UNICHAR", "UNICODE",
             "FIXED", "DOLLAR", "T", "ENCODEURL"),
    "datetime": ("DATE", "TIME", "TODAY", "NOW", "YEAR", "MONTH", "DAY", "HOUR",
                 "MINUTE", "SECOND", "WEEKDAY", "WEEKNUM", "ISOWEEKNUM",
                 "DATEDIF", "DATEVALUE", "TIMEVALUE", "EDATE", "EOMONTH",
                 "NETWORKDAYS", "NETWORKDAYS.INTL", "WORKDAY", "WORKDAY.INTL",
                 "DAYS", "DAYS360", "YEARFRAC"),
    "logical": ("IF", "IFS", "IFERROR", "IFNA", "AND", "OR", "NOT", "XOR",
                "TRUE", "FALSE", "SWITCH", "ISBLANK", "ISNUMBER", "ISTEXT",
                "ISNONTEXT", "ISLOGICAL", "ISERROR", "ISERR", "ISNA", "ISEVEN",
                "ISODD", "ISFORMULA", "ISREF", "ISOMITTED", "NA", "ERROR.TYPE",
                "TYPE", "N", "CELL", "SHEET", "SHEETS", "FORMULATEXT", "INFO"),
    "lookup": ("VLOOKUP", "HLOOKUP", "XLOOKUP", "LOOKUP", "INDEX", "MATCH",
               "XMATCH", "CHOOSE", "OFFSET", "INDIRECT", "ROW", "ROWS", "COLUMN",
               "COLUMNS", "ADDRESS", "AREAS", "HYPERLINK", "GETPIVOTDATA",
               "TRANSPOSE"),
    "arrays": ("UNIQUE", "SORT", "SORTBY", "FILTER", "SEQUENCE", "RANDARRAY",
               "VSTACK", "HSTACK", "TAKE", "DROP", "CHOOSEROWS", "CHOOSECOLS",
               "TOROW", "TOCOL", "EXPAND", "WRAPROWS", "WRAPCOLS"),
    "database": ("DSUM", "DAVERAGE", "DCOUNT", "DCOUNTA", "DGET", "DMAX", "DMIN",
                 "DPRODUCT", "DSTDEV", "DSTDEVP", "DVAR", "DVARP"),
    "live": ("WEBSERVICE", "FILTERXML", "REST", "RESTTABLE", "WEBSOCKET"),
    "other": ("SPARKLINE",),
}
_NAME_CATEGORIES: dict[str, str] = {
    name: cat for cat, names in _NAME_LISTS.items() for name in names
}

# --- plain-English descriptions (the everyday surface) -----------------------

DESCRIPTIONS: dict[str, str] = {
    "SUM": "Adds all the numbers in the given cells or ranges.",
    "AVERAGE": "The arithmetic mean of the numbers — text and blanks are skipped.",
    "COUNT": "How many cells contain numbers.",
    "COUNTA": "How many cells are not empty (numbers or text).",
    "MIN": "The smallest number in the given values.",
    "MAX": "The largest number in the given values.",
    "MEDIAN": "The middle value — half the numbers are above it, half below.",
    "MODE": "The most frequent value in the data.",
    "IF": "Returns one value when a condition is true and another when false.",
    "IFS": "The first value whose condition is true — a cleaner nested IF.",
    "IFERROR": "Replaces an error with a fallback (great around lookups).",
    "IFNA": "Like IFERROR but only catches #N/A (missing lookup matches).",
    "SWITCH": "Compares one expression against cases and returns the match.",
    "CHOOSE": "Picks the Nth value from a list.",
    "AND": "TRUE when every condition is true.",
    "OR": "TRUE when at least one condition is true.",
    "NOT": "Flips TRUE to FALSE and back.",
    "VLOOKUP": "Finds a value in the first column of a table and returns a "
               "cell to its right. Prefer XLOOKUP for new sheets.",
    "XLOOKUP": "The modern lookup: search any range, return from another, with "
               "a built-in not-found fallback.",
    "INDEX": "Returns the cell at a given row/column of a range.",
    "MATCH": "The position of a value inside a range (pair with INDEX).",
    "XMATCH": "MATCH with modern matching and search modes.",
    "OFFSET": "A reference shifted rows/columns from a starting cell.",
    "INDIRECT": "Turns text like \"B\"&ROW() into a live reference.",
    "SUMIF": "Adds the cells that meet one criterion.",
    "SUMIFS": "Adds the cells that meet every criterion (multiple ranges).",
    "COUNTIF": "Counts the cells that meet one criterion.",
    "COUNTIFS": "Counts rows meeting every criterion.",
    "AVERAGEIF": "Averages the cells that meet one criterion.",
    "AVERAGEIFS": "Averages rows meeting every criterion.",
    "SUMPRODUCT": "Multiplies matching cells across ranges, then sums — "
                  "weighted sums and multi-condition counts in one call.",
    "ROUND": "Rounds a number to the given digits.",
    "ROUNDUP": "Rounds away from zero.",
    "ROUNDDOWN": "Rounds toward zero.",
    "INT": "Rounds down to the nearest whole number.",
    "TRUNC": "Drops the fractional part (no rounding).",
    "MOD": "The remainder after division.",
    "ABS": "The absolute value (drops the sign).",
    "SQRT": "The square root.",
    "POWER": "One number raised to another.",
    "EXP": "e raised to the given power.",
    "LN": "The natural logarithm.",
    "LOG": "Logarithm in any base (base 10 by default).",
    "PI": "The constant π.",
    "RAND": "A random number between 0 and 1 (changes every recalc).",
    "RANDBETWEEN": "A random whole number in a range (changes every recalc).",
    "CONCAT": "Joins text values together.",
    "TEXTJOIN": "Joins text with a delimiter, optionally skipping blanks.",
    "TEXTSPLIT": "Splits text into a spilled array by delimiters.",
    "LEFT": "The first N characters of a text.",
    "RIGHT": "The last N characters of a text.",
    "MID": "Characters from the middle of a text.",
    "LEN": "How many characters a text has.",
    "TRIM": "Removes extra spaces.",
    "UPPER": "Converts text to UPPER CASE.",
    "LOWER": "Converts text to lower case.",
    "PROPER": "Capitalizes Each Word.",
    "SUBSTITUTE": "Replaces occurrences of one text with another.",
    "FIND": "Where one text appears inside another (case-sensitive).",
    "SEARCH": "Like FIND but case-insensitive and wildcard-friendly.",
    "TEXT": "Formats a number or date as text with a format code.",
    "VALUE": "Converts number-looking text into a real number.",
    "DATE": "Builds a date from year, month, and day numbers.",
    "TODAY": "Today's date (updates on recalc).",
    "NOW": "The current date and time (updates on recalc).",
    "YEAR": "The year of a date.",
    "MONTH": "The month of a date (1–12).",
    "DAY": "The day of the month.",
    "WEEKDAY": "The day of the week as a number.",
    "DATEDIF": "The difference between two dates in days, months, or years.",
    "EDATE": "A date shifted by whole months.",
    "EOMONTH": "The last day of a month, shifted by whole months.",
    "NETWORKDAYS": "Business days between two dates (skips weekends/holidays).",
    "WORKDAY": "A date N business days away.",
    "STDEV": "Sample standard deviation — how spread out the data is.",
    "VAR": "Sample variance.",
    "CORREL": "Correlation between two ranges (−1 to 1).",
    "PERCENTILE": "The value below which a share of the data falls.",
    "QUARTILE": "Quartile boundaries of the data (0–4).",
    "RANK": "Where a value ranks within a range.",
    "LARGE": "The Nth largest value.",
    "SMALL": "The Nth smallest value.",
    "FREQUENCY": "Counts values into bins (spills an array).",
    "UNIQUE": "The distinct values of a range, spilled.",
    "SORT": "A sorted copy of a range, spilled.",
    "SORTBY": "Sorts one range by the values of another.",
    "FILTER": "The rows of a range that satisfy a condition, spilled.",
    "SEQUENCE": "A spilled series of numbers (rows × columns).",
    "TRANSPOSE": "Flips rows and columns.",
    "VSTACK": "Stacks ranges on top of each other.",
    "HSTACK": "Places ranges side by side.",
    "LET": "Names intermediate values so a formula reads clearly and "
           "computes each piece once.",
    "LAMBDA": "Defines a reusable function right inside a formula.",
    "MAP": "Applies a LAMBDA to each element of a range.",
    "REDUCE": "Folds a range into one value with a LAMBDA.",
    "PMT": "The periodic payment for a loan.",
    "FV": "Future value of an investment.",
    "PV": "Present value of an investment.",
    "NPV": "Net present value of a cash-flow series.",
    "IRR": "Internal rate of return of a cash-flow series.",
    "RATE": "The interest rate per period of an annuity.",
    "NPER": "How many periods an investment/loan runs.",
    "HYPERLINK": "A clickable link with optional friendly text.",
    "ISBLANK": "TRUE when a cell is empty.",
    "ISNUMBER": "TRUE when a value is a number.",
    "ISTEXT": "TRUE when a value is text.",
    "ISERROR": "TRUE when a value is any error.",
    "SPARKLINE": "A tiny in-cell chart of a range.",
    "WEBSERVICE": "Fetches text from a URL (needs live data enabled).",
    "REST": "Reads a JSON REST endpoint (needs live data enabled).",
    "DBM2W": "Converts power in dBm to watts.",
    "W2DBM": "Converts watts to dBm.",
    "VSWR": "Voltage standing-wave ratio from a load impedance.",
    "WAVELENGTH": "Wavelength in metres for a frequency.",
    "FSPL": "Free-space path loss between two points.",
    "GRIDSQUARE": "Maidenhead grid square for a latitude/longitude.",
}


def category_key(name: str) -> str:
    """The category key for a registered function name."""
    up = name.upper()
    if up in _NAME_CATEGORIES:
        return _NAME_CATEGORIES[up]
    from .functions import CONTEXT_FUNCTIONS, FUNCTIONS, LAZY_FUNCTIONS

    fn = FUNCTIONS.get(up) or LAZY_FUNCTIONS.get(up) or CONTEXT_FUNCTIONS.get(up)
    mod = getattr(fn, "__module__", "") or ""
    if not mod.startswith("abax."):
        return "user"                      # a macro / init.py UDF
    return _MODULE_CATEGORIES.get(mod.rsplit(".", 1)[-1], "other")


def describe(name: str) -> dict:
    """``{name, signature, category, category_blurb, description}`` for a
    function — the Formula manager's guidance pane in one call."""
    up = name.upper()
    key = category_key(up)
    label, blurb = CATEGORIES[key]
    desc = DESCRIPTIONS.get(up)
    if desc is None:
        # Harvested from docs/formula-reference.md — hand-written wins above.
        desc = GENERATED_DESCRIPTIONS.get(up)
    if desc is None:
        from .functions import FUNCTIONS

        fn = FUNCTIONS.get(up)
        doc = (fn.__doc__ or "").strip().splitlines()[0].strip() if fn and fn.__doc__ else ""
        # A signature-shaped docstring ("NAME(arg, ...)") is already shown as
        # the signature — don't repeat it as the description too.
        looks_like_sig = doc.upper().startswith(up + "(")
        desc = doc if doc and not looks_like_sig else (
            f"A {label} function — see the formula reference.")
    return {
        "name": up,
        "signature": signature(up),
        "category": label,
        "category_blurb": blurb,
        "description": desc,
    }


def catalog() -> dict[str, list[str]]:
    """``{category label: [function names]}`` over every registered function,
    categories in the curated order, names sorted."""
    by_key: dict[str, list[str]] = {k: [] for k in CATEGORIES}
    for name in function_names():
        by_key[category_key(name)].append(name)
    return {CATEGORIES[k][0]: sorted(v) for k, v in by_key.items() if v}
