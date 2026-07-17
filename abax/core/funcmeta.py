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
    # gnumeric_fns registers only the R.* distribution family (R.DNORM, ...).
    "gnumeric_fns": "stats",
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
    "math": ("ABS", "ACOS", "AGGREGATE", "ASIN", "ATAN", "ATAN2",
             "CEILING", "CEILING.MATH", "COMBIN", "COS", "COSH",
             "DEGREES", "EVEN", "EXP", "FACT", "FLOOR", "FLOOR.MATH",
             "GCD", "INT", "INTERP", "LCM", "LN", "LOG", "LOG10",
             "MDETERM", "MOD", "MROUND", "ODD", "PERMUT", "PI", "POWER",
             "PRODUCT", "RADIANS", "RAND", "RANDBETWEEN", "ROUND",
             "ROUNDDOWN", "ROUNDUP", "SERIESSUM", "SIGN", "SIN", "SINH",
             "SQRT", "SQRTPI", "SUBTOTAL", "SUM", "SUMIF", "SUMIFS",
             "SUMPRODUCT", "SUMSQ", "TAN", "TANH", "TRUNC"),
    "stats": ("AVEDEV", "AVERAGE", "AVERAGEA", "AVERAGEIF", "AVERAGEIFS",
              "AVG", "CHIDIST", "CHIINV", "CHISQ.DIST.RT", "CHISQ.INV.RT",
              "CONFIDENCE", "CONFIDENCE.NORM", "CORREL", "COUNT", "COUNTA",
              "COUNTBLANK", "COUNTIF", "COUNTIFS", "COVAR", "COVARIANCE.P",
              "DEVSQ", "F.DIST.RT", "F.INV.RT", "FDIST", "FINV",
              "FORECAST", "FORECAST.LINEAR", "FREQUENCY", "GEOMEAN",
              "GROWTH", "HARMEAN", "INTERCEPT", "KURT", "LARGE", "LINEST",
              "LOGEST", "MAX", "MAXA", "MAXIFS", "MEDIAN", "MIN", "MINA",
              "MINIFS", "MODE", "MODE.MULT", "MODE.SNGL", "NORM.DIST",
              "NORM.INV", "NORM.S.INV", "NORMDIST", "NORMINV", "NORMSDIST",
              "NORMSINV", "PERCENTILE", "PERCENTILE.INC", "PERCENTRANK",
              "QUARTILE", "QUARTILE.INC", "RANK", "RMS", "RSQ", "SKEW",
              "SLOPE", "SMALL", "STANDARDIZE", "STDEV", "STDEV.P",
              "STDEV.S", "STDEVP", "TDIST", "TINV", "TREND", "TRIMMEAN",
              "TTEST", "VAR", "VAR.P", "VAR.S", "VARP"),
    "text": ("ARRAYTOTEXT", "CHAR", "CLEAN", "CODE", "CONCAT",
             "CONCATENATE", "DOLLAR", "ENCODEURL", "EXACT", "FIND", "FIXED",
             "LEFT", "LEN", "LOWER", "MID", "NUMBERVALUE", "PROPER",
             "REPLACE", "REPT", "RIGHT", "SEARCH", "SUBSTITUTE", "T",
             "TEXT", "TEXTJOIN", "TEXTSPLIT", "TRIM", "UNICHAR", "UNICODE",
             "UPPER", "VALUE", "VALUETOTEXT"),
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
    "engineering": ("COMPLEX", "CONVERT", "IMABS", "IMAGINARY",
                    "IMARGUMENT", "IMCONJUGATE", "IMCOS", "IMCOSH",
                    "IMCOT", "IMCSC", "IMCSCH", "IMDIV", "IMEXP", "IMLN",
                    "IMLOG10", "IMLOG2", "IMPOWER", "IMPRODUCT", "IMREAL",
                    "IMSEC", "IMSECH", "IMSIN", "IMSINH", "IMSQRT",
                    "IMSUB", "IMSUM", "IMTAN", "IMTANH"),
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


# --- curated usage examples -------------------------------------------------

EXAMPLES: dict[str, str] = {
    # Math & trig
    "SUM": "=SUM(B2:B100)",
    "SUMIF": '=SUMIF(A:A, ">0", B:B)',
    "SUMIFS": '=SUMIFS(C:C, A:A, "East", B:B, ">1000")',
    "SUMPRODUCT": "=SUMPRODUCT(A2:A10, B2:B10)",
    "ABS": "=ABS(A1)",
    "SQRT": "=SQRT(A1)",
    "POWER": "=POWER(A1, 3)",
    "ROUND": "=ROUND(A1, 2)",
    "ROUNDUP": "=ROUNDUP(A1, 0)",
    "ROUNDDOWN": "=ROUNDDOWN(A1, 2)",
    "MOD": "=MOD(A1, 7)",
    "INT": "=INT(A1)",
    "CEILING": "=CEILING(A1, 0.25)",
    "FLOOR": "=FLOOR(A1, 10)",
    "RAND": "=RAND()",
    "RANDBETWEEN": "=RANDBETWEEN(1, 100)",
    "LOG": "=LOG(A1, 2)",
    "LN": "=LN(A1)",
    "EXP": "=EXP(A1)",
    "PI": "=PI()",
    "PRODUCT": "=PRODUCT(B2:B20)",
    "GCD": "=GCD(A1, B1)",
    "LCM": "=LCM(A1, B1)",
    "FACT": "=FACT(A1)",
    "COMBIN": "=COMBIN(10, 3)",
    "TRUNC": "=TRUNC(A1, 2)",
    "SIGN": "=SIGN(A1)",
    "MROUND": "=MROUND(A1, 5)",
    "EVEN": "=EVEN(A1)",
    "ODD": "=ODD(A1)",
    "SUBTOTAL": "=SUBTOTAL(9, B2:B100)",
    "AGGREGATE": "=AGGREGATE(4, 6, B2:B100)",
    # Statistics
    "AVERAGE": "=AVERAGE(B2:B100)",
    "AVERAGEIF": '=AVERAGEIF(A:A, "East", B:B)',
    "AVERAGEIFS": '=AVERAGEIFS(C:C, A:A, "East", B:B, ">0")',
    "MEDIAN": "=MEDIAN(B2:B100)",
    "MODE": "=MODE(B2:B100)",
    "COUNT": "=COUNT(B2:B100)",
    "COUNTA": "=COUNTA(A2:A100)",
    "COUNTBLANK": "=COUNTBLANK(A2:A100)",
    "COUNTIF": '=COUNTIF(A:A, "yes")',
    "COUNTIFS": '=COUNTIFS(A:A, "East", B:B, ">100")',
    "MAX": "=MAX(B2:B100)",
    "MIN": "=MIN(B2:B100)",
    "LARGE": "=LARGE(B2:B100, 3)",
    "SMALL": "=SMALL(B2:B100, 1)",
    "STDEV": "=STDEV(B2:B100)",
    "STDEVP": "=STDEVP(B2:B100)",
    "VAR": "=VAR(B2:B100)",
    "VARP": "=VARP(B2:B100)",
    "CORREL": "=CORREL(A2:A100, B2:B100)",
    "PERCENTILE": "=PERCENTILE(B2:B100, 0.9)",
    "RANK": "=RANK(A1, B2:B100)",
    "FREQUENCY": "=FREQUENCY(A2:A100, C2:C10)",
    "QUARTILE": "=QUARTILE(B2:B100, 1)",
    "GEOMEAN": "=GEOMEAN(B2:B100)",
    "HARMEAN": "=HARMEAN(B2:B100)",
    "TRIMMEAN": "=TRIMMEAN(B2:B100, 0.1)",
    "SKEW": "=SKEW(B2:B100)",
    "KURT": "=KURT(B2:B100)",
    "MAXIFS": '=MAXIFS(B:B, A:A, "East")',
    "MINIFS": '=MINIFS(B:B, A:A, "East")',
    # Text
    "CONCAT": '=CONCAT(A1, " ", B1)',
    "TEXTJOIN": '=TEXTJOIN(", ", TRUE, A2:A100)',
    "TEXTSPLIT": '=TEXTSPLIT(A1, ",")',
    "LEFT": "=LEFT(A1, 3)",
    "RIGHT": "=RIGHT(A1, 4)",
    "MID": "=MID(A1, 2, 5)",
    "LEN": "=LEN(A1)",
    "TRIM": "=TRIM(A1)",
    "UPPER": "=UPPER(A1)",
    "LOWER": "=LOWER(A1)",
    "PROPER": "=PROPER(A1)",
    "SUBSTITUTE": '=SUBSTITUTE(A1, "old", "new")',
    "FIND": '=FIND("@", A1)',
    "SEARCH": '=SEARCH("widget", A1)',
    "TEXT": '=TEXT(A1, "yyyy-mm-dd")',
    "VALUE": "=VALUE(A1)",
    "REPLACE": '=REPLACE(A1, 1, 3, "new")',
    "REPT": '=REPT("*", A1)',
    "EXACT": "=EXACT(A1, B1)",
    "CLEAN": "=CLEAN(A1)",
    "CHAR": "=CHAR(10)",
    "CODE": "=CODE(A1)",
    "FIXED": "=FIXED(A1, 2)",
    "CONCATENATE": '=CONCATENATE(A1, " ", B1)',
    # Date & time
    "DATE": "=DATE(2025, 6, 15)",
    "TODAY": "=TODAY()",
    "NOW": "=NOW()",
    "YEAR": "=YEAR(A1)",
    "MONTH": "=MONTH(A1)",
    "DAY": "=DAY(A1)",
    "DATEDIF": '=DATEDIF(A1, B1, "Y")',
    "EDATE": "=EDATE(A1, 3)",
    "EOMONTH": "=EOMONTH(A1, 0)",
    "NETWORKDAYS": "=NETWORKDAYS(A1, B1)",
    "WORKDAY": "=WORKDAY(A1, 10)",
    "WEEKDAY": "=WEEKDAY(A1)",
    "WEEKNUM": "=WEEKNUM(A1)",
    "HOUR": "=HOUR(A1)",
    "MINUTE": "=MINUTE(A1)",
    "SECOND": "=SECOND(A1)",
    "DAYS": "=DAYS(B1, A1)",
    "YEARFRAC": "=YEARFRAC(A1, B1)",
    # Logical & information
    "IF": '=IF(A1>0, "positive", "zero or negative")',
    "IFS": '=IFS(A1>=90, "A", A1>=80, "B", TRUE, "C")',
    "IFERROR": '=IFERROR(A1/B1, "N/A")',
    "IFNA": '=IFNA(XLOOKUP(A1, B:B, C:C), "not found")',
    "AND": "=AND(A1>0, B1>0)",
    "OR": "=OR(A1>0, B1>0)",
    "NOT": "=NOT(A1)",
    "SWITCH": '=SWITCH(A1, 1, "Jan", 2, "Feb", 3, "Mar")',
    "ISBLANK": "=ISBLANK(A1)",
    "ISNUMBER": "=ISNUMBER(A1)",
    "ISTEXT": "=ISTEXT(A1)",
    "ISERROR": "=ISERROR(A1)",
    "ISNA": "=ISNA(A1)",
    "ISEVEN": "=ISEVEN(A1)",
    "ISODD": "=ISODD(A1)",
    "XOR": "=XOR(A1, B1)",
    # Lookup & reference
    "VLOOKUP": "=VLOOKUP(A1, Products!A:C, 2, FALSE)",
    "XLOOKUP": '=XLOOKUP(A1, B:B, C:C, "not found")',
    "HLOOKUP": "=HLOOKUP(A1, Data!1:3, 2, FALSE)",
    "INDEX": "=INDEX(B2:B100, MATCH(A1, A2:A100, 0))",
    "MATCH": "=MATCH(A1, B2:B100, 0)",
    "XMATCH": "=XMATCH(A1, B2:B100, 0)",
    "CHOOSE": '=CHOOSE(A1, "red", "green", "blue")',
    "OFFSET": "=OFFSET(A1, 2, 3)",
    "INDIRECT": '=INDIRECT("B" & ROW())',
    "ROW": "=ROW(A1)",
    "COLUMN": "=COLUMN(A1)",
    "ROWS": "=ROWS(A1:A10)",
    "COLUMNS": "=COLUMNS(A1:D1)",
    "ADDRESS": "=ADDRESS(1, 1)",
    "TRANSPOSE": "=TRANSPOSE(A1:D1)",
    "HYPERLINK": '=HYPERLINK("https://example.com", "Click here")',
    # Dynamic arrays
    "UNIQUE": "=UNIQUE(A2:A100)",
    "SORT": "=SORT(A2:B100, 2, -1)",
    "SORTBY": "=SORTBY(A2:B100, B2:B100, -1)",
    "FILTER": '=FILTER(A2:C100, B2:B100="East")',
    "SEQUENCE": "=SEQUENCE(10, 1, 1, 1)",
    "VSTACK": "=VSTACK(A1:A10, B1:B10)",
    "HSTACK": "=HSTACK(A1:A10, B1:B10)",
    "RANDARRAY": "=RANDARRAY(5, 3)",
    "TAKE": "=TAKE(A2:C100, 5)",
    "DROP": "=DROP(A2:C100, 1)",
    "CHOOSEROWS": "=CHOOSEROWS(A2:C100, 1, 3, 5)",
    "CHOOSECOLS": "=CHOOSECOLS(A1:E1, 1, 3)",
    "TOROW": "=TOROW(A1:C3)",
    "TOCOL": "=TOCOL(A1:C3)",
    "EXPAND": "=EXPAND(A1:B2, 5, 5)",
    "WRAPROWS": "=WRAPROWS(A1:A12, 4)",
    "WRAPCOLS": "=WRAPCOLS(A1:A12, 4)",
    # Financial
    "PMT": "=PMT(0.05/12, 360, -200000)",
    "FV": "=FV(0.06/12, 120, -500)",
    "PV": "=PV(0.08/12, 240, -1000)",
    "NPV": "=NPV(0.1, B2:B10)",
    "IRR": "=IRR(B2:B10)",
    "RATE": "=RATE(360, -1500, 250000)",
    "NPER": "=NPER(0.05/12, -500, 20000)",
    # LET & LAMBDA
    "LET": "=LET(total, SUM(B:B), total*1.1)",
    "LAMBDA": "=LAMBDA(x, x*2)(5)",
    "MAP": "=MAP(A2:A10, LAMBDA(x, x*2))",
    "REDUCE": "=REDUCE(0, A2:A10, LAMBDA(a, b, a+b))",
    # Database
    "DSUM": "=DSUM(A1:C100, 3, E1:E2)",
    "DAVERAGE": "=DAVERAGE(A1:C100, 2, E1:E2)",
    "DCOUNT": "=DCOUNT(A1:C100, 2, E1:E2)",
    "DMAX": "=DMAX(A1:C100, 2, E1:E2)",
    "DMIN": "=DMIN(A1:C100, 2, E1:E2)",
    # Connected data
    "REST": '=REST("https://api.example.com/data")',
    "WEBSERVICE": '=WEBSERVICE("https://example.com/api")',
    # Other / specialty
    "SPARKLINE": "=SPARKLINE(B2:B20)",
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
    """``{name, signature, category, category_blurb, description, example}``
    for a function — the Formula manager's guidance pane in one call."""
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
        "example": EXAMPLES.get(up, ""),
    }


def catalog() -> dict[str, list[str]]:
    """``{category label: [function names]}`` over every registered function,
    categories in the curated order, names sorted."""
    by_key: dict[str, list[str]] = {k: [] for k in CATEGORIES}
    for name in function_names():
        by_key[category_key(name)].append(name)
    return {CATEGORIES[k][0]: sorted(v) for k, v in by_key.items() if v}
