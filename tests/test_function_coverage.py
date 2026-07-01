"""Excel/Gnumeric coverage gate — track how much of the common function set abax
implements, and pin that the parity packs (math/stats/text-date/finance/eng) and
their headline functions are actually registered and evaluate."""

from __future__ import annotations

import math

from abax.core.functions import FUNCTIONS
from abax.core.workbook import Workbook

# A representative slice of the everyday Excel function set across categories.
# Not exhaustive — a canary that the parity waves stayed wired up.
COMMON = {
    # math / trig / info
    "SINH", "COSH", "TANH", "COMBIN", "PERMUT", "GAMMA", "ROMAN", "BASE",
    "EVEN", "ODD", "MROUND", "QUOTIENT", "ISEVEN", "ISODD", "ERROR.TYPE",
    # statistics / distributions
    "BINOMDIST", "POISSON", "EXPONDIST", "GAMMADIST", "BETADIST", "WEIBULL",
    "HYPGEOMDIST", "STANDARDIZE", "DEVSQ", "AVEDEV", "RANK.EQ",
    "SUMIFS", "COUNTIFS", "AVERAGEIFS", "MAXIFS", "MINIFS",
    # text / date-time
    "TEXTJOIN", "TEXTBEFORE", "TEXTAFTER", "UNICHAR", "FIXED", "NUMBERVALUE",
    "EOMONTH", "WORKDAY", "NETWORKDAYS", "YEARFRAC", "ISOWEEKNUM", "TIME",
    # financial
    "PMT", "PV", "FV", "NPV", "IRR", "XIRR", "RATE", "NPER", "SLN", "DDB",
    "EFFECT", "NOMINAL",
    # engineering / database
    "DEC2BIN", "HEX2DEC", "BITAND", "BITOR", "DELTA", "ERF", "BESSELJ",
    "DSUM", "DCOUNT", "DAVERAGE", "DGET",
    # modern dotted aliases
    "STDEV.S", "VAR.P", "NORM.DIST", "PERCENTILE.INC",
    # Wave I — modern-Excel completeness
    "TEXTSPLIT", "XMATCH", "LOOKUP", "SUBTOTAL", "AGGREGATE",
    "CEILING.MATH", "FLOOR.MATH", "WORKDAY.INTL", "NETWORKDAYS.INTL",
    "IMTAN", "IMLOG10", "ARRAYTOTEXT",
    "NORM.S.DIST", "T.DIST", "T.INV", "CHISQ.DIST", "CHISQ.INV",
    "F.DIST", "F.INV", "CONFIDENCE.T", "T.TEST", "Z.TEST", "F.TEST",
    "CHISQ.TEST", "FORECAST.LINEAR",
    # Wave D tail — bond / security financial
    "PRICE", "YIELD", "DURATION", "MDURATION", "DISC", "INTRATE",
    "RECEIVED", "ACCRINT", "ACCRINTM", "PRICEMAT", "YIELDMAT",
    "TBILLEQ", "TBILLPRICE", "TBILLYIELD", "COUPNUM", "COUPDAYS",
}


def test_common_functions_registered():
    missing = sorted(n for n in COMMON if n not in FUNCTIONS)
    assert not missing, f"missing common functions: {missing}"


def test_registry_reaches_target():
    # Past Excel's ~500 after Waves A-I; Gnumeric's ~640 is the remaining target.
    assert len(FUNCTIONS) >= 560


def _val(formula):
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", formula)
    return s.get("A1")


def test_headline_functions_evaluate():
    assert _val("=COMBIN(8,2)") == 28
    assert _val("=ROMAN(1994)") == "MCMXCIV"
    assert _val("=DEC2BIN(9)") == "1001"
    assert _val("=BITAND(6,10)") == 2
    assert abs(_val("=PMT(0.08/12,120,10000)") + 121.33) < 0.5
    assert _val("=EOMONTH(\"2026-01-15\",1)") == "2026-02-28"
    assert _val("=TEXTJOIN(\"-\",TRUE,\"a\",\"\",\"b\")") == "a-b"
    assert math.isclose(_val("=BINOMDIST(6,10,0.5,FALSE)"), 0.205078, rel_tol=1e-4)
