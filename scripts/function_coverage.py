#!/usr/bin/env python3
"""Function-coverage dashboard — a read-only parity report.

Compares abax's live function registries against a curated target list of common
Excel/Gnumeric function names (organized by category) and reports how much of that
target set is implemented, plus a categorized list of what is still MISSING.

This is *purely* a reporting tool: it imports the registries, it never mutates
them and never registers anything. Run it directly for a terminal summary::

    py scripts/function_coverage.py

or regenerate the Markdown dashboard::

    py scripts/function_coverage.py --markdown

which writes ``docs/function-coverage.md`` relative to the repo root.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a plain script (`py scripts/function_coverage.py`) — put the
# repo root on the path so `import abax` resolves regardless of the cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Live registries — the three calling-convention buckets the engine exposes.
from abax.core.functions import CONTEXT_FUNCTIONS, FUNCTIONS, LAZY_FUNCTIONS  # noqa: E402

# --- curated target list ---------------------------------------------------
#
# A few hundred well-known Excel/Gnumeric function names, grouped by category.
# Seeded from tests/test_function_coverage.py's COMMON canary and expanded with
# the everyday Excel surface. These are *targets*, not a claim of implementation —
# the report is exactly the diff between this list and the live registries.
TARGETS: dict[str, list[str]] = {
    "math": [
        "ABS", "SIGN", "SQRT", "SQRTPI", "POWER", "EXP", "LN", "LOG", "LOG10",
        "MOD", "QUOTIENT", "GCD", "LCM", "FACT", "FACTDOUBLE", "MULTINOMIAL",
        "COMBIN", "COMBINA", "PERMUT", "PERMUTATIONA", "PI", "PRODUCT", "SUM",
        "SUMSQ", "SUMPRODUCT", "SUMX2MY2", "SUMX2PY2", "SUMXMY2", "SERIESSUM",
        "ROUND", "ROUNDUP", "ROUNDDOWN", "MROUND", "CEILING", "CEILING.MATH",
        "FLOOR", "FLOOR.MATH", "TRUNC", "INT", "EVEN", "ODD", "GAMMA", "GAMMALN",
        "ROMAN", "ARABIC", "BASE", "DECIMAL", "SIN", "COS", "TAN", "ASIN",
        "ACOS", "ATAN", "ATAN2", "SINH", "COSH", "TANH", "ASINH", "ACOSH",
        "ATANH", "COT", "COTH", "SEC", "CSC", "DEGREES", "RADIANS", "RAND",
        "RANDBETWEEN", "SUMIF", "SUMIFS",
    ],
    "stats": [
        "AVERAGE", "AVERAGEA", "AVERAGEIF", "AVERAGEIFS", "MEDIAN", "MODE",
        "MODE.SNGL", "MODE.MULT", "COUNT", "COUNTA", "COUNTBLANK", "COUNTIF",
        "COUNTIFS", "MAX", "MAXA", "MAXIFS", "MIN", "MINA", "MINIFS", "LARGE",
        "SMALL", "RANK", "RANK.EQ", "RANK.AVG", "PERCENTILE", "PERCENTILE.INC",
        "PERCENTILE.EXC", "PERCENTRANK", "QUARTILE", "QUARTILE.INC",
        "QUARTILE.EXC", "STDEV", "STDEV.S", "STDEVP", "STDEV.P", "STDEVA",
        "VAR", "VAR.S", "VARP", "VAR.P", "VARA", "GEOMEAN", "HARMEAN",
        "TRIMMEAN", "DEVSQ", "AVEDEV", "SKEW", "KURT", "STANDARDIZE", "CORREL",
        "COVAR", "COVARIANCE.P", "PEARSON", "RSQ", "SLOPE", "INTERCEPT", "STEYX",
        "FORECAST", "FORECAST.LINEAR", "TREND", "GROWTH", "LINEST", "LOGEST",
        "FREQUENCY", "PROB", "FISHER", "FISHERINV",
        # distributions
        "NORMDIST", "NORM.DIST", "NORMINV", "NORM.INV", "NORMSDIST",
        "NORM.S.DIST", "NORMSINV", "NORM.S.INV", "BINOMDIST", "BINOM.DIST",
        "NEGBINOMDIST", "POISSON", "POISSON.DIST", "EXPONDIST", "EXPON.DIST",
        "GAMMADIST", "GAMMA.DIST", "GAMMAINV", "GAMMA.INV", "BETADIST",
        "BETA.DIST", "BETAINV", "BETA.INV", "WEIBULL", "WEIBULL.DIST",
        "HYPGEOMDIST", "HYPGEOM.DIST", "LOGNORMDIST", "LOGNORM.DIST",
        "CHIDIST", "CHISQ.DIST", "CHIINV", "CHISQ.INV", "CHITEST", "CHISQ.TEST",
        "TDIST", "T.DIST", "TINV", "T.INV", "TTEST", "T.TEST", "FDIST",
        "F.DIST", "FINV", "F.INV", "FTEST", "F.TEST", "ZTEST", "Z.TEST",
        "CONFIDENCE", "CONFIDENCE.NORM", "CONFIDENCE.T", "CRITBINOM",
    ],
    "text": [
        "CONCAT", "CONCATENATE", "TEXTJOIN", "TEXTSPLIT", "TEXTBEFORE",
        "TEXTAFTER", "LEN", "LEFT", "RIGHT", "MID", "UPPER", "LOWER", "PROPER",
        "TRIM", "CLEAN", "FIND", "SEARCH", "REPLACE", "SUBSTITUTE", "REPT",
        "EXACT", "CHAR", "CODE", "UNICHAR", "UNICODE", "TEXT", "FIXED", "DOLLAR",
        "VALUE", "NUMBERVALUE", "T", "ARRAYTOTEXT", "VALUETOTEXT",
        # classic Excel text functions not yet in abax
        "ASC", "DBCS", "BAHTTEXT", "PHONETIC",
    ],
    "date": [
        "NOW", "TODAY", "DATE", "TIME", "DATEVALUE", "TIMEVALUE", "YEAR",
        "MONTH", "DAY", "HOUR", "MINUTE", "SECOND", "WEEKDAY", "WEEKNUM",
        "ISOWEEKNUM", "DATEDIF", "EDATE", "EOMONTH", "DAYS", "DAYS360",
        "YEARFRAC", "WORKDAY", "WORKDAY.INTL", "NETWORKDAYS", "NETWORKDAYS.INTL",
    ],
    "logical_info": [
        "IF", "IFS", "IFERROR", "IFNA", "SWITCH", "CHOOSE", "AND", "OR", "XOR",
        "NOT", "TRUE", "FALSE", "NA", "N", "TYPE", "ERROR.TYPE", "ISBLANK",
        "ISNUMBER", "ISTEXT", "ISNONTEXT", "ISLOGICAL", "ISERROR", "ISERR",
        "ISNA", "ISEVEN", "ISODD", "ISREF", "ISFORMULA", "CELL", "SHEET",
        "SHEETS", "FORMULATEXT",
        # common info/web functions not yet in abax
        "HYPERLINK", "GETPIVOTDATA", "ENCODEURL", "WEBSERVICE", "FILTERXML",
    ],
    "lookup": [
        "VLOOKUP", "HLOOKUP", "XLOOKUP", "LOOKUP", "MATCH", "XMATCH", "INDEX",
        "OFFSET", "INDIRECT", "ADDRESS", "ROW", "ROWS", "COLUMN", "COLUMNS",
        "TRANSPOSE", "UNIQUE", "SORT", "SORTBY", "FILTER", "SEQUENCE",
        "SUBTOTAL", "AGGREGATE",
    ],
    "financial": [
        "PMT", "IPMT", "PPMT", "PV", "FV", "NPV", "XNPV", "IRR", "XIRR", "MIRR",
        "RATE", "NPER", "SLN", "SYD", "DDB", "DB", "VDB", "EFFECT", "NOMINAL",
        "CUMIPMT", "CUMPRINC", "RRI", "PDURATION", "DOLLARDE", "DOLLARFR",
        # bond / security
        "PRICE", "PRICEDISC", "PRICEMAT", "YIELD", "YIELDDISC", "YIELDMAT",
        "DISC", "INTRATE", "RECEIVED", "DURATION", "MDURATION", "ACCRINT",
        "ACCRINTM", "TBILLEQ", "TBILLPRICE", "TBILLYIELD", "COUPNUM", "COUPDAYS",
        "COUPDAYBS", "COUPDAYSNC", "COUPNCD", "COUPPCD",
        # classic Excel financial functions not yet in abax
        "ISPMT", "FVSCHEDULE", "AMORDEGRC", "AMORLINC", "ODDFPRICE", "ODDLPRICE",
        "ODDFYIELD", "ODDLYIELD",
    ],
    "engineering": [
        "CONVERT", "DELTA", "GESTEP", "ERF", "ERFC", "BESSELI", "BESSELJ",
        "BESSELK", "BESSELY", "DEC2BIN", "DEC2HEX", "DEC2OCT", "BIN2DEC",
        "BIN2HEX", "BIN2OCT", "HEX2BIN", "HEX2DEC", "HEX2OCT", "OCT2BIN",
        "OCT2DEC", "OCT2HEX", "BITAND", "BITOR", "BITXOR", "BITLSHIFT",
        "BITRSHIFT", "COMPLEX", "IMABS", "IMSUM", "IMPRODUCT", "IMSUB", "IMDIV",
        "IMREAL", "IMAGINARY", "IMCONJUGATE", "IMARGUMENT", "IMSQRT", "IMEXP",
        "IMLN", "IMLOG10", "IMLOG2", "IMPOWER", "IMSIN", "IMCOS", "IMTAN",
        "MMULT", "MINVERSE", "MUNIT", "MDETERM",
    ],
    "database": [
        "DSUM", "DCOUNT", "DCOUNTA", "DAVERAGE", "DMAX", "DMIN", "DGET",
        "DPRODUCT", "DSTDEV", "DSTDEVP", "DVAR", "DVARP",
    ],
}


def _all_registered() -> set[str]:
    """Union of every live registry — the full set of names abax can evaluate."""
    return set(FUNCTIONS) | set(LAZY_FUNCTIONS) | set(CONTEXT_FUNCTIONS)


def build_report() -> dict:
    """Compute the coverage report. Pure read-only — returns a data structure.

    Keys:
      ``implemented`` (int)  — size of the live registry union,
      ``target_total`` (int) — size of the curated target list (deduped),
      ``covered`` (int)      — targets that are implemented,
      ``coverage`` (float)   — percent of the target list implemented (0..100),
      ``by_category`` (dict) — per-category {implemented, total, missing[]},
      ``missing`` (dict)     — {category: sorted missing names},
      ``targets`` (dict)     — the curated list, echoed back.
    """
    registered = _all_registered()

    # Dedupe the target list across categories for the headline totals.
    target_names: set[str] = set()
    for names in TARGETS.values():
        target_names.update(names)

    covered = {n for n in target_names if n in registered}

    by_category: dict[str, dict] = {}
    missing: dict[str, list[str]] = {}
    for cat, names in TARGETS.items():
        uniq = sorted(set(names))
        miss = sorted(n for n in uniq if n not in registered)
        by_category[cat] = {
            "implemented": len(uniq) - len(miss),
            "total": len(uniq),
            "missing": miss,
        }
        if miss:
            missing[cat] = miss

    total = len(target_names)
    coverage = (100.0 * len(covered) / total) if total else 0.0
    return {
        "implemented": len(registered),
        "target_total": total,
        "covered": len(covered),
        "coverage": round(coverage, 1),
        "by_category": by_category,
        "missing": missing,
        "targets": TARGETS,
    }


def format_text(report: dict) -> str:
    """Human-readable terminal summary + categorized MISSING list."""
    lines: list[str] = []
    lines.append("abax function-coverage dashboard")
    lines.append("=" * 34)
    lines.append(f"Implemented (live registries): {report['implemented']}")
    lines.append(f"Curated target set:            {report['target_total']}")
    lines.append(
        f"Target coverage:              {report['covered']}/{report['target_total']}"
        f"  ({report['coverage']}%)"
    )
    lines.append("")
    lines.append("Per-category coverage:")
    for cat, info in report["by_category"].items():
        lines.append(f"  {cat:<14} {info['implemented']:>3}/{info['total']:<3}")

    if report["missing"]:
        lines.append("")
        lines.append("MISSING target functions:")
        for cat, names in report["missing"].items():
            lines.append(f"  [{cat}] {', '.join(names)}")
    else:
        lines.append("")
        lines.append("No missing target functions — full parity with the target list.")
    return "\n".join(lines)


def format_markdown(report: dict) -> str:
    """Markdown dashboard for docs/function-coverage.md."""
    lines: list[str] = []
    lines.append("# Function-coverage dashboard")
    lines.append("")
    lines.append(
        "Generated by `scripts/function_coverage.py` — a read-only parity report of "
        "which spreadsheet functions abax implements versus a curated target set of "
        "common Excel/Gnumeric functions. Regenerate with `py "
        "scripts/function_coverage.py --markdown`."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Implemented (live registries) | {report['implemented']} |")
    lines.append(f"| Curated target set | {report['target_total']} |")
    lines.append(f"| Target coverage | {report['covered']}/{report['target_total']} |")
    lines.append(f"| Coverage % | {report['coverage']}% |")
    lines.append("")
    lines.append("## Per-category coverage")
    lines.append("")
    lines.append("| Category | Implemented | Target |")
    lines.append("| --- | --- | --- |")
    for cat, info in report["by_category"].items():
        lines.append(f"| {cat} | {info['implemented']} | {info['total']} |")
    lines.append("")
    lines.append("## Missing target functions")
    lines.append("")
    if report["missing"]:
        for cat, names in report["missing"].items():
            joined = ", ".join(f"`{n}`" for n in names)
            lines.append(f"- **{cat}**: {joined}")
    else:
        lines.append("None — every function in the curated target list is implemented.")
    lines.append("")
    return "\n".join(lines)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="write docs/function-coverage.md instead of printing to stdout",
    )
    args = parser.parse_args(argv)

    report = build_report()
    if args.markdown:
        out = _repo_root() / "docs" / "function-coverage.md"
        out.write_text(format_markdown(report), encoding="utf-8")
        print(f"wrote {out}  ({report['coverage']}% coverage)")
    else:
        print(format_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
