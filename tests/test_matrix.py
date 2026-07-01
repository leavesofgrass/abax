"""Dense matrix operations (matmul / determinant / inverse / solve / trace)."""

from __future__ import annotations

import pytest

from abax.core.science.matrix import (
    MatrixError,
    add,
    determinant,
    identity,
    inverse,
    matmul,
    scalar_mul,
    shape,
    solve,
    sub,
    trace,
    transpose,
)


def _approx_identity(m, n):
    expected = identity(n)
    for i in range(n):
        for j in range(n):
            assert m[i][j] == pytest.approx(expected[i][j], abs=1e-9)


def test_shape():
    assert shape([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]) == (2, 3)


def test_identity():
    assert identity(3) == [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def test_transpose():
    assert transpose([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]) == [
        [1.0, 4.0],
        [2.0, 5.0],
        [3.0, 6.0],
    ]


def test_add_sub_scalar():
    a = [[1.0, 2.0], [3.0, 4.0]]
    b = [[5.0, 6.0], [7.0, 8.0]]
    assert add(a, b) == [[6.0, 8.0], [10.0, 12.0]]
    assert sub(b, a) == [[4.0, 4.0], [4.0, 4.0]]
    assert scalar_mul(a, 2.0) == [[2.0, 4.0], [6.0, 8.0]]


def test_matmul_known():
    a = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]  # 2x3
    b = [[7.0, 8.0], [9.0, 10.0], [11.0, 12.0]]  # 3x2
    assert matmul(a, b) == [[58.0, 64.0], [139.0, 154.0]]


def test_matmul_identity():
    a = [[1.0, 2.0], [3.0, 4.0]]
    assert matmul(a, identity(2)) == a


def test_determinant_2x2():
    assert determinant([[1.0, 2.0], [3.0, 4.0]]) == pytest.approx(-2.0)


def test_determinant_3x3():
    a = [[6.0, 1.0, 1.0], [4.0, -2.0, 5.0], [2.0, 8.0, 7.0]]
    assert determinant(a) == pytest.approx(-306.0)


def test_inverse_roundtrip():
    a = [[4.0, 7.0], [2.0, 6.0]]
    inv = inverse(a)
    expected = [[0.6, -0.7], [-0.2, 0.4]]
    for i in range(2):
        assert inv[i] == pytest.approx(expected[i])
    _approx_identity(matmul(a, inv), 2)
    _approx_identity(matmul(inv, a), 2)


def test_inverse_3x3_roundtrip():
    a = [[2.0, 1.0, 1.0], [1.0, 3.0, 2.0], [1.0, 0.0, 0.0]]
    _approx_identity(matmul(a, inverse(a)), 3)


def test_solve_2x2():
    a = [[2.0, 1.0], [1.0, 3.0]]
    b = [3.0, 4.0]
    x = solve(a, b)
    assert x == pytest.approx([1.0, 1.0])


def test_solve_3x3():
    a = [[2.0, 1.0, -1.0], [-3.0, -1.0, 2.0], [-2.0, 1.0, 2.0]]
    b = [8.0, -11.0, -3.0]
    x = solve(a, b)
    assert x == pytest.approx([2.0, 3.0, -1.0])
    # Residual check.
    for i in range(3):
        lhs = sum(a[i][j] * x[j] for j in range(3))
        assert lhs == pytest.approx(b[i])


def test_trace():
    assert trace([[1.0, 2.0], [3.0, 4.0]]) == pytest.approx(5.0)


def test_ragged_matrix_raises():
    with pytest.raises(MatrixError):
        shape([[1.0, 2.0], [3.0]])


def test_non_numeric_raises():
    with pytest.raises(MatrixError):
        shape([[1.0, "x"]])


def test_matmul_shape_mismatch_raises():
    with pytest.raises(MatrixError):
        matmul([[1.0, 2.0]], [[1.0, 2.0]])


def test_add_shape_mismatch_raises():
    with pytest.raises(MatrixError):
        add([[1.0, 2.0]], [[1.0, 2.0], [3.0, 4.0]])


def test_determinant_non_square_raises():
    with pytest.raises(MatrixError):
        determinant([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])


def test_inverse_singular_raises():
    with pytest.raises(MatrixError):
        inverse([[1.0, 2.0], [2.0, 4.0]])


def test_inverse_non_square_raises():
    with pytest.raises(MatrixError):
        inverse([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])


def test_solve_singular_raises():
    with pytest.raises(MatrixError):
        solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])


def test_solve_dimension_mismatch_raises():
    with pytest.raises(MatrixError):
        solve([[1.0, 2.0], [3.0, 4.0]], [1.0, 2.0, 3.0])
