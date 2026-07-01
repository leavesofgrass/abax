"""Tests for :mod:`abax.core.science.eigen` — eigenvalues and matrix decompositions."""

from __future__ import annotations

import math

import pytest

from abax.core.science.eigen import (
    EigenError,
    cholesky,
    condition_number,
    eigen_symmetric,
    eigenvalues,
    lu,
    qr,
)


def _matmul(a, b):
    return [
        [sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))]
        for i in range(len(a))
    ]


def _transpose(a):
    return [[a[i][j] for i in range(len(a))] for j in range(len(a[0]))]


# --------------------------------------------------------------------------- #
# eigenvalues
# --------------------------------------------------------------------------- #

def test_eigenvalues_diagonal():
    vals = eigenvalues([[2, 0, 0], [0, 3, 0], [0, 0, 5]])
    assert vals == pytest.approx([5.0, 3.0, 2.0], abs=1e-6)


def test_eigenvalues_symmetric_2x2():
    vals = eigenvalues([[2, 1], [1, 2]])
    assert vals == pytest.approx([3.0, 1.0], abs=1e-6)


def test_eigenvalues_nonsymmetric_2x2():
    vals = eigenvalues([[4, 1], [2, 3]])
    assert vals == pytest.approx([5.0, 2.0], abs=1e-6)


def test_eigenvalues_non_square_raises():
    with pytest.raises(EigenError):
        eigenvalues([[1, 2, 3], [4, 5, 6]])


# --------------------------------------------------------------------------- #
# eigen_symmetric
# --------------------------------------------------------------------------- #

def test_eigen_symmetric_values():
    vals, _vecs = eigen_symmetric([[2, 1], [1, 2]])
    assert vals == pytest.approx([3.0, 1.0], abs=1e-6)


def test_eigen_symmetric_vectors_satisfy_eigen_equation():
    A = [[2, 1], [1, 2]]
    vals, vecs = eigen_symmetric(A)
    n = len(A)
    for c in range(n):
        v = [vecs[r][c] for r in range(n)]
        av = [sum(A[i][k] * v[k] for k in range(n)) for i in range(n)]
        lam_v = [vals[c] * v[i] for i in range(n)]
        assert av == pytest.approx(lam_v, abs=1e-6)


def test_eigen_symmetric_vectors_normalised():
    _vals, vecs = eigen_symmetric([[2, 1], [1, 2]])
    n = len(vecs)
    for c in range(n):
        norm = math.sqrt(sum(vecs[r][c] ** 2 for r in range(n)))
        assert norm == pytest.approx(1.0, abs=1e-6)


def test_eigen_symmetric_non_symmetric_raises():
    with pytest.raises(EigenError):
        eigen_symmetric([[1, 2], [3, 4]])


# --------------------------------------------------------------------------- #
# lu
# --------------------------------------------------------------------------- #

def test_lu_reconstructs_pa_equals_lu():
    A = [[2, 1, 1], [4, -6, 0], [-2, 7, 2]]
    L, U, perm = lu(A)
    n = len(A)
    # P·A
    pa = [A[perm[i]] for i in range(n)]
    lu_prod = _matmul(L, U)
    for i in range(n):
        assert pa[i] == pytest.approx(lu_prod[i], abs=1e-6)


def test_lu_l_is_unit_lower():
    A = [[2, 1, 1], [4, -6, 0], [-2, 7, 2]]
    L, _U, _perm = lu(A)
    n = len(A)
    for i in range(n):
        assert L[i][i] == pytest.approx(1.0, abs=1e-6)
        for j in range(i + 1, n):
            assert L[i][j] == pytest.approx(0.0, abs=1e-6)


def test_lu_u_is_upper():
    A = [[2, 1, 1], [4, -6, 0], [-2, 7, 2]]
    _L, U, _perm = lu(A)
    n = len(A)
    for i in range(n):
        for j in range(i):
            assert U[i][j] == pytest.approx(0.0, abs=1e-6)


def test_lu_singular_raises():
    with pytest.raises(EigenError):
        lu([[1, 2], [2, 4]])


# --------------------------------------------------------------------------- #
# qr
# --------------------------------------------------------------------------- #

def test_qr_reconstructs_a():
    A = [[12, -51, 4], [6, 167, -68], [-4, 24, -41]]
    Q, R = qr(A)
    prod = _matmul(Q, R)
    n = len(A)
    for i in range(n):
        assert prod[i] == pytest.approx([float(x) for x in A[i]], abs=1e-6)


def test_qr_q_orthonormal():
    A = [[12, -51, 4], [6, 167, -68], [-4, 24, -41]]
    Q, _R = qr(A)
    qtq = _matmul(_transpose(Q), Q)
    n = len(A)
    for i in range(n):
        for j in range(n):
            expected = 1.0 if i == j else 0.0
            assert qtq[i][j] == pytest.approx(expected, abs=1e-6)


def test_qr_r_upper():
    A = [[12, -51, 4], [6, 167, -68], [-4, 24, -41]]
    _Q, R = qr(A)
    n = len(A)
    for i in range(n):
        for j in range(i):
            assert R[i][j] == pytest.approx(0.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# cholesky
# --------------------------------------------------------------------------- #

def test_cholesky_reconstructs_spd():
    A = [[4, 2], [2, 3]]
    L = cholesky(A)
    llt = _matmul(L, _transpose(L))
    n = len(A)
    for i in range(n):
        assert llt[i] == pytest.approx([float(x) for x in A[i]], abs=1e-6)


def test_cholesky_lower_triangular():
    L = cholesky([[4, 2], [2, 3]])
    n = len(L)
    for i in range(n):
        for j in range(i + 1, n):
            assert L[i][j] == pytest.approx(0.0, abs=1e-6)


def test_cholesky_non_spd_raises():
    with pytest.raises(EigenError):
        cholesky([[1, 2], [2, 1]])


# --------------------------------------------------------------------------- #
# condition_number
# --------------------------------------------------------------------------- #

def test_condition_number_identity():
    assert condition_number([[1, 0], [0, 1]]) == pytest.approx(1.0, abs=1e-6)


def test_condition_number_diagonal():
    assert condition_number([[2, 0], [0, 1]]) == pytest.approx(2.0, abs=1e-6)


def test_condition_number_singular_raises():
    with pytest.raises(EigenError):
        condition_number([[1, 1], [1, 1]])
