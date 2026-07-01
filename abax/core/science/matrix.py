"""Dense matrix operations — a small linear-algebra engine.

Everything is implemented by hand with the standard library only (``math``,
no numpy). A matrix is a ``list[list[float]]`` of rows; every row must have the
same length. The surface covers the spreadsheet/linear-algebra staples:

* :func:`shape` / :func:`identity` / :func:`transpose` / :func:`trace`
* :func:`add` / :func:`sub` / :func:`scalar_mul` / :func:`matmul`
* :func:`determinant` — square only, via LU decomposition with partial pivoting
* :func:`inverse` — Gauss-Jordan elimination
* :func:`solve` — solve ``A x = b`` for a vector ``b``

Bad input (non-rectangular, dimension mismatch, non-square where square is
required) and singular matrices raise :class:`MatrixError`. A pivot magnitude
below ``EPS`` (1e-12) during elimination is treated as singular.

Pure stdlib → core.
"""

from __future__ import annotations

Matrix = list[list[float]]
Vector = list[float]

EPS = 1e-12


class MatrixError(Exception):
    """Raised for invalid matrices, dimension mismatches, or singularity."""


def _validate(a: Matrix) -> tuple[int, int]:
    """Validate that ``a`` is a non-empty rectangular numeric matrix.

    Returns ``(rows, cols)``. Raises :class:`MatrixError` otherwise.
    """
    if not isinstance(a, list) or not a:
        raise MatrixError("matrix must be a non-empty list of rows")
    rows = len(a)
    cols: int | None = None
    for row in a:
        if not isinstance(row, list) or not row:
            raise MatrixError("each row must be a non-empty list")
        if cols is None:
            cols = len(row)
        elif len(row) != cols:
            raise MatrixError("matrix is not rectangular (ragged rows)")
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MatrixError("matrix entries must be numeric")
    assert cols is not None
    return rows, cols


def shape(a: Matrix) -> tuple[int, int]:
    """Return ``(rows, cols)`` of a validated matrix."""
    return _validate(a)


def identity(n: int) -> Matrix:
    """Return the ``n x n`` identity matrix."""
    if n < 1:
        raise MatrixError("identity size must be a positive integer")
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def transpose(a: Matrix) -> Matrix:
    """Return the transpose of ``a``."""
    rows, cols = _validate(a)
    return [[float(a[i][j]) for i in range(rows)] for j in range(cols)]


def add(a: Matrix, b: Matrix) -> Matrix:
    """Return the element-wise sum ``a + b`` (same shape required)."""
    ra, ca = _validate(a)
    rb, cb = _validate(b)
    if (ra, ca) != (rb, cb):
        raise MatrixError("add: matrices must have the same shape")
    return [[float(a[i][j]) + float(b[i][j]) for j in range(ca)] for i in range(ra)]


def sub(a: Matrix, b: Matrix) -> Matrix:
    """Return the element-wise difference ``a - b`` (same shape required)."""
    ra, ca = _validate(a)
    rb, cb = _validate(b)
    if (ra, ca) != (rb, cb):
        raise MatrixError("sub: matrices must have the same shape")
    return [[float(a[i][j]) - float(b[i][j]) for j in range(ca)] for i in range(ra)]


def scalar_mul(a: Matrix, k: float) -> Matrix:
    """Return ``a`` scaled element-wise by ``k``."""
    rows, cols = _validate(a)
    return [[float(a[i][j]) * float(k) for j in range(cols)] for i in range(rows)]


def matmul(a: Matrix, b: Matrix) -> Matrix:
    """Return the matrix product ``a @ b`` for ``(m x n)(n x p) -> m x p``.

    Raises :class:`MatrixError` if the inner dimensions disagree.
    """
    ra, ca = _validate(a)
    rb, cb = _validate(b)
    if ca != rb:
        raise MatrixError(
            f"matmul: inner dimensions disagree ({ra}x{ca} @ {rb}x{cb})"
        )
    result: Matrix = []
    for i in range(ra):
        row_i = a[i]
        out_row = [0.0] * cb
        for k in range(ca):
            aik = float(row_i[k])
            if aik == 0.0:
                continue
            brow = b[k]
            for j in range(cb):
                out_row[j] += aik * float(brow[j])
        result.append(out_row)
    return result


def _require_square(a: Matrix) -> int:
    """Validate that ``a`` is square; return its dimension ``n``."""
    rows, cols = _validate(a)
    if rows != cols:
        raise MatrixError("matrix must be square")
    return rows


def trace(a: Matrix) -> float:
    """Return the trace (sum of the diagonal) of a square matrix."""
    n = _require_square(a)
    return float(sum(a[i][i] for i in range(n)))


def determinant(a: Matrix) -> float:
    """Return the determinant of a square matrix via LU with partial pivoting."""
    n = _require_square(a)
    m = [[float(x) for x in row] for row in a]
    det = 1.0
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot_row][col]) < EPS:
            return 0.0
        if pivot_row != col:
            m[col], m[pivot_row] = m[pivot_row], m[col]
            det = -det
        pivot = m[col][col]
        det *= pivot
        for r in range(col + 1, n):
            factor = m[r][col] / pivot
            if factor == 0.0:
                continue
            for c in range(col, n):
                m[r][c] -= factor * m[col][c]
    return det


def inverse(a: Matrix) -> Matrix:
    """Return the inverse of a square matrix via Gauss-Jordan elimination.

    Raises :class:`MatrixError` if ``a`` is non-square or singular.
    """
    n = _require_square(a)
    # Augment [A | I] and reduce the left block to the identity.
    m = [[float(x) for x in row] + [1.0 if i == j else 0.0 for j in range(n)]
         for i, row in enumerate(a)]

    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot_row][col]) < EPS:
            raise MatrixError("matrix is singular and cannot be inverted")
        m[col], m[pivot_row] = m[pivot_row], m[col]

        pivot = m[col][col]
        inv_pivot = 1.0 / pivot
        for c in range(2 * n):
            m[col][c] *= inv_pivot

        for r in range(n):
            if r == col:
                continue
            factor = m[r][col]
            if factor == 0.0:
                continue
            for c in range(2 * n):
                m[r][c] -= factor * m[col][c]

    return [row[n:] for row in m]


def solve(a: Matrix, b: Vector) -> Vector:
    """Solve ``A x = b`` for the vector ``x`` via Gaussian elimination.

    ``b`` is a flat vector with one entry per row of the square matrix ``a``.
    Raises :class:`MatrixError` on shape mismatch or a singular system.
    """
    n = _require_square(a)
    if not isinstance(b, list) or len(b) != n:
        raise MatrixError("solve: b must be a vector of length n")
    for value in b:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MatrixError("solve: b entries must be numeric")

    m = [[float(x) for x in row] + [float(b[i])] for i, row in enumerate(a)]

    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot_row][col]) < EPS:
            raise MatrixError("solve: matrix is singular")
        m[col], m[pivot_row] = m[pivot_row], m[col]

        pivot = m[col][col]
        for r in range(col + 1, n):
            factor = m[r][col] / pivot
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]

    # Back-substitution.
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        total = m[i][n]
        for j in range(i + 1, n):
            total -= m[i][j] * x[j]
        x[i] = total / m[i][i]
    return x
