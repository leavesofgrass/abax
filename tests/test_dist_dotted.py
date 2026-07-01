"""Wave I — dotted distribution family + hypothesis tests (dist_dotted pack).

Oracle values come from the worked examples in the Microsoft function
documentation (and close cross-checks against the legacy right-tail
functions already in the registry).
"""

from __future__ import annotations

import math

from abax.core.errors import CellError
from abax.core.functions import FUNCTIONS
from abax.core.values import RangeValue


def v(name, *a):
    return FUNCTIONS[name](list(a))


def col(*xs):
    return RangeValue([[x] for x in xs])


def test_all_registered():
    for name in ("NORM.S.DIST", "T.DIST", "T.DIST.RT", "T.DIST.2T", "T.INV",
                 "T.INV.2T", "CHISQ.DIST", "CHISQ.INV", "F.DIST", "F.INV",
                 "CONFIDENCE.T", "T.TEST", "Z.TEST", "ZTEST", "F.TEST", "FTEST",
                 "CHISQ.TEST", "CHITEST"):
        assert name in FUNCTIONS, name


# --- normal -------------------------------------------------------------------


def test_norm_s_dist():
    # Excel doc: NORM.S.DIST(1.333333, TRUE) = 0.908788726
    assert math.isclose(v("NORM.S.DIST", 1.333333, True), 0.908788726, rel_tol=1e-6)
    # Excel doc: NORM.S.DIST(1.333333, FALSE) = 0.164010148
    assert math.isclose(v("NORM.S.DIST", 1.333333, False), 0.164010148, rel_tol=1e-6)
    # Agrees with the legacy NORMSDIST.
    assert math.isclose(v("NORM.S.DIST", 0.5, True), v("NORMSDIST", 0.5), rel_tol=1e-12)


# --- Student t -----------------------------------------------------------------


def test_t_dist():
    # Excel doc: T.DIST(60, 1, TRUE) = 0.99469533
    assert math.isclose(v("T.DIST", 60, 1, True), 0.99469533, rel_tol=1e-6)
    # Excel doc: T.DIST(8, 3, FALSE) = 0.00073691
    assert math.isclose(v("T.DIST", 8, 3, False), 0.00073691, rel_tol=1e-4)
    # Left + right tails sum to 1.
    assert math.isclose(v("T.DIST", 1.5, 7, True) + v("T.DIST.RT", 1.5, 7), 1.0,
                        rel_tol=1e-12)


def test_t_dist_tails():
    # Excel doc: T.DIST.2T(1.959999998, 60) = 0.054644930
    assert math.isclose(v("T.DIST.2T", 1.959999998, 60), 0.054644930, rel_tol=1e-6)
    # Excel doc: T.DIST.RT(1.959999998, 60) = 0.027322465
    assert math.isclose(v("T.DIST.RT", 1.959999998, 60), 0.027322465, rel_tol=1e-6)
    assert isinstance(v("T.DIST.2T", -1, 60), CellError)


def test_t_inv():
    # Excel doc: T.INV(0.75, 2) = 0.8164966
    assert math.isclose(v("T.INV", 0.75, 2), 0.8164966, rel_tol=1e-6)
    # Excel doc: T.INV.2T(0.546449, 60) = 0.606533
    assert math.isclose(v("T.INV.2T", 0.546449, 60), 0.606533, rel_tol=1e-5)
    # Round-trips through the CDF, and the negative tail works.
    assert math.isclose(v("T.DIST", v("T.INV", 0.1, 5), 5, True), 0.1, rel_tol=1e-9)
    assert v("T.INV", 0.1, 5) < 0
    # T.INV.2T is the legacy TINV.
    assert math.isclose(v("T.INV.2T", 0.05, 10), v("TINV", 0.05, 10), rel_tol=1e-6)


# --- chi-square -----------------------------------------------------------------


def test_chisq_dist():
    # Excel doc: CHISQ.DIST(0.5, 1, TRUE) = 0.52049988
    assert math.isclose(v("CHISQ.DIST", 0.5, 1, True), 0.52049988, rel_tol=1e-6)
    # Excel doc: CHISQ.DIST(2, 3, FALSE) = 0.20755375
    assert math.isclose(v("CHISQ.DIST", 2, 3, False), 0.20755375, rel_tol=1e-6)
    # Complements the legacy right-tail CHIDIST.
    assert math.isclose(v("CHISQ.DIST", 3, 4, True) + v("CHIDIST", 3, 4), 1.0,
                        rel_tol=1e-9)


def test_chisq_inv():
    # Excel doc: CHISQ.INV(0.93, 1) = 3.283020287
    assert math.isclose(v("CHISQ.INV", 0.93, 1), 3.283020287, rel_tol=1e-6)
    assert math.isclose(v("CHISQ.DIST", v("CHISQ.INV", 0.6, 8), 8, True), 0.6,
                        rel_tol=1e-9)


# --- F ---------------------------------------------------------------------------


def test_f_dist():
    # Excel doc: F.DIST(15.20686486, 6, 4, TRUE) = 0.99
    assert math.isclose(v("F.DIST", 15.20686486, 6, 4, True), 0.99, rel_tol=1e-6)
    # Excel doc: F.DIST(15.20686486, 6, 4, FALSE) = 0.0012238
    assert math.isclose(v("F.DIST", 15.20686486, 6, 4, False), 0.0012238, rel_tol=1e-4)


def test_f_inv():
    # Excel doc: F.INV(0.01, 6, 4) = 0.10930991
    assert math.isclose(v("F.INV", 0.01, 6, 4), 0.10930991, rel_tol=1e-6)
    assert math.isclose(v("F.DIST", v("F.INV", 0.95, 3, 9), 3, 9, True), 0.95,
                        rel_tol=1e-9)


# --- confidence -------------------------------------------------------------------


def test_confidence_t():
    # Excel doc: CONFIDENCE.T(0.05, 1, 50) = 0.284196855
    assert math.isclose(v("CONFIDENCE.T", 0.05, 1, 50), 0.284196855, rel_tol=1e-6)
    assert isinstance(v("CONFIDENCE.T", 0.05, 1, 1), CellError)


# --- hypothesis tests --------------------------------------------------------------


def test_t_test_paired():
    a = col(3, 4, 5, 8, 9, 1, 2, 4, 5)
    b = col(6, 19, 3, 2, 14, 4, 5, 17, 1)
    # Excel doc: T.TEST(A, B, 2, 1) = 0.196016
    assert math.isclose(v("T.TEST", a, b, 2, 1), 0.196016, rel_tol=1e-4)
    # One tail is half of two tails.
    assert math.isclose(v("T.TEST", a, b, 1, 1) * 2, v("T.TEST", a, b, 2, 1),
                        rel_tol=1e-12)


def test_t_test_two_sample():
    a = col(3, 4, 5, 8, 9, 1, 2, 4, 5)
    b = col(6, 19, 3, 2, 14, 4, 5, 17, 1)
    for kind in (2, 3):
        p = v("T.TEST", a, b, 2, kind)
        assert 0.0 < p < 1.0
        # Symmetric in its arguments.
        assert math.isclose(p, v("T.TEST", b, a, 2, kind), rel_tol=1e-12)
    # Paired test on different-length arrays is #N/A.
    assert isinstance(v("T.TEST", col(1, 2, 3), col(1, 2), 2, 1), CellError)


def test_z_test():
    data = col(3, 6, 7, 8, 6, 5, 4, 2, 1, 9)
    # Excel doc: Z.TEST(A2:A11, 4) = 0.090574
    assert math.isclose(v("Z.TEST", data, 4), 0.090574, rel_tol=1e-3)
    # With sigma supplied it uses it instead of the sample sd.
    p_sigma = v("Z.TEST", data, 4, 2.0)
    assert 0.0 < p_sigma < v("Z.TEST", data, 4)
    # Legacy name is the same function.
    assert v("ZTEST", data, 4) == v("Z.TEST", data, 4)


def test_f_test():
    a = col(6, 7, 9, 15, 21)
    b = col(20, 28, 31, 38, 40)
    # Excel doc: F.TEST(A, B) = 0.64831785
    assert math.isclose(v("F.TEST", a, b), 0.64831785, rel_tol=1e-6)
    # Symmetric, and the legacy alias matches.
    assert math.isclose(v("F.TEST", b, a), v("F.TEST", a, b), rel_tol=1e-9)
    assert v("FTEST", a, b) == v("F.TEST", a, b)


def test_chisq_test():
    actual = RangeValue([[58.0, 35.0], [11.0, 25.0], [10.0, 23.0]])
    expected = RangeValue([[45.35, 47.65], [17.56, 18.44], [16.09, 16.91]])
    # Excel doc: CHITEST(actual, expected) = 0.000308
    assert math.isclose(v("CHISQ.TEST", actual, expected), 0.000308, rel_tol=2e-3)
    assert v("CHITEST", actual, expected) == v("CHISQ.TEST", actual, expected)
    # Mismatched shapes are #N/A.
    assert isinstance(v("CHISQ.TEST", actual, RangeValue([[1.0, 2.0]])), CellError)
