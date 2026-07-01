"""Eigenvalues and matrix decompositions — a no-numpy linear-algebra module.

Everything here is implemented by hand with the standard library only (``math``,
no numpy). A matrix is a ``list[list[float]]`` of rows; every row must have the
same length. The surface covers the decompositions a spreadsheet might want:

* :func:`eigenvalues` — real eigenvalues via the (Wilkinson-shifted) QR algorithm
* :func:`eigen_symmetric` — eigenvalues + eigenvectors via cyclic Jacobi rotation
* :func:`lu` — LU factorisation with partial pivoting (``P·A = L·U``)
* :func:`qr` — QR factorisation via Householder reflections (``A = Q·R``)
* :func:`cholesky` — ``L`` with ``A = L·Lᵀ`` for symmetric positive-definite ``A``
* :func:`condition_number` — 2-norm condition number ``σmax/σmin``

Bad input (non-rectangular, non-square where square is required) and failures
(non-convergence, singularity, non-SPD) raise :class:`EigenError`. This module
is deliberately self-contained: it does not import :mod:`abax.core.science.matrix`.

Pure stdlib → core.
"""

from __future__ import annotations

import math

Matrix = list[list[float]]
Vector = list[float]

EPS = 1e-12


class EigenError(Exception):
    """Raised for invalid matrices, non-convergence, or singular/non-SPD input."""


# --------------------------------------------------------------------------- #
# Local helpers (self-contained — no matrix.py import).
# --------------------------------------------------------------------------- #

def _validate(a: Matrix) -> tuple[int, int]:
    """Validate that ``a`` is a non-empty rectangular numeric matrix.

    Returns ``(rows, cols)``. Raises :class:`EigenError` otherwise.
    """
    if not isinstance(a, list) or not a:
        raise EigenError("matrix must be a non-empty list of rows")
    rows = len(a)
    cols: int | None = None
    for row in a:
        if not isinstance(row, list) or not row:
            raise EigenError("each row must be a non-empty list")
        if cols is None:
            cols = len(row)
        elif len(row) != cols:
            raise EigenError("matrix is not rectangular (ragged rows)")
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EigenError("matrix entries must be numeric")
    assert cols is not None
    return rows, cols


def _require_square(a: Matrix) -> int:
    """Validate that ``a`` is square; return its dimension ``n``."""
    rows, cols = _validate(a)
    if rows != cols:
        raise EigenError("matrix must be square")
    return rows


def _copy(a: Matrix) -> Matrix:
    """Return a float-typed deep copy of ``a``."""
    return [[float(x) for x in row] for row in a]


def _identity(n: int) -> Matrix:
    """Return the ``n x n`` identity matrix."""
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _transpose(a: Matrix) -> Matrix:
    """Return the transpose of ``a``."""
    rows = len(a)
    cols = len(a[0])
    return [[float(a[i][j]) for i in range(rows)] for j in range(cols)]


def _matmul(a: Matrix, b: Matrix) -> Matrix:
    """Return the matrix product ``a @ b``."""
    ra = len(a)
    ca = len(a[0])
    rb = len(b)
    cb = len(b[0])
    if ca != rb:
        raise EigenError(f"matmul: inner dimensions disagree ({ra}x{ca} @ {rb}x{cb})")
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


def _is_symmetric(a: Matrix, n: int, tol: float) -> bool:
    """Return ``True`` if ``a`` is symmetric to within ``tol`` (absolute/relative)."""
    for i in range(n):
        for j in range(i + 1, n):
            diff = abs(a[i][j] - a[j][i])
            scale = max(abs(a[i][j]), abs(a[j][i]), 1.0)
            if diff > tol * scale:
                return False
    return True


# --------------------------------------------------------------------------- #
# LU with partial pivoting.
# --------------------------------------------------------------------------- #

def lu(A: Matrix) -> tuple[Matrix, Matrix, list[int]]:
    """LU factorisation with partial pivoting.

    Returns ``(L, U, perm)`` where ``L`` is unit-lower-triangular, ``U`` is
    upper-triangular, and ``perm`` is the row permutation such that
    ``P·A = L·U`` (``perm[i]`` is the original row now sitting at position ``i``).

    Raises :class:`EigenError` if ``A`` is non-square or singular.
    """
    n = _require_square(A)
    u = _copy(A)
    l = _identity(n)
    perm = list(range(n))

    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(u[r][col]))
        if abs(u[pivot_row][col]) < EPS:
            raise EigenError("lu: matrix is singular")
        if pivot_row != col:
            u[col], u[pivot_row] = u[pivot_row], u[col]
            perm[col], perm[pivot_row] = perm[pivot_row], perm[col]
            # Swap the already-computed multipliers in L (columns < col).
            for k in range(col):
                l[col][k], l[pivot_row][k] = l[pivot_row][k], l[col][k]

        pivot = u[col][col]
        for r in range(col + 1, n):
            factor = u[r][col] / pivot
            l[r][col] = factor
            if factor == 0.0:
                continue
            for c in range(col, n):
                u[r][c] -= factor * u[col][c]

    return l, u, perm


# --------------------------------------------------------------------------- #
# QR via Householder reflections.
# --------------------------------------------------------------------------- #

def qr(A: Matrix) -> tuple[Matrix, Matrix]:
    """QR factorisation via Householder reflections.

    Returns ``(Q, R)`` with ``Q`` orthonormal, ``R`` upper-triangular, and
    ``A = Q·R``. Works for square matrices (the typical use here).
    """
    n = _require_square(A)
    r = _copy(A)
    q = _identity(n)

    for k in range(n - 1):
        # Build the Householder vector for column k below the diagonal.
        norm = math.sqrt(sum(r[i][k] ** 2 for i in range(k, n)))
        if norm < EPS:
            continue
        # Choose sign to avoid cancellation.
        alpha = -norm if r[k][k] >= 0 else norm
        v = [0.0] * n
        v[k] = r[k][k] - alpha
        for i in range(k + 1, n):
            v[i] = r[i][k]
        vnorm2 = sum(v[i] ** 2 for i in range(k, n))
        if vnorm2 < EPS:
            continue

        # Apply H = I - 2 v vᵀ / (vᵀv) to R (from the left).
        for j in range(n):
            dot = sum(v[i] * r[i][j] for i in range(k, n))
            factor = 2.0 * dot / vnorm2
            for i in range(k, n):
                r[i][j] -= factor * v[i]

        # Accumulate Q: Q = Q · H  (H symmetric, so apply to columns of Q).
        for i in range(n):
            dot = sum(q[i][j] * v[j] for j in range(k, n))
            factor = 2.0 * dot / vnorm2
            for j in range(k, n):
                q[i][j] -= factor * v[j]

    # Clean tiny sub-diagonal noise in R.
    for i in range(n):
        for j in range(i):
            r[i][j] = 0.0
    return q, r


# --------------------------------------------------------------------------- #
# Cholesky.
# --------------------------------------------------------------------------- #

def cholesky(A: Matrix) -> Matrix:
    """Return the lower-triangular ``L`` with ``A = L·Lᵀ`` for SPD ``A``.

    Raises :class:`EigenError` if ``A`` is not square, not symmetric, or not
    positive-definite (a non-positive pivot is encountered).
    """
    n = _require_square(A)
    if not _is_symmetric(A, n, 1e-9):
        raise EigenError("cholesky: matrix is not symmetric")

    l = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(l[i][k] * l[j][k] for k in range(j))
            if i == j:
                diag = float(A[i][i]) - s
                if diag <= EPS:
                    raise EigenError("cholesky: matrix is not positive-definite")
                l[i][j] = math.sqrt(diag)
            else:
                l[i][j] = (float(A[i][j]) - s) / l[j][j]
    return l


# --------------------------------------------------------------------------- #
# Eigenvalues via shifted QR iteration.
# --------------------------------------------------------------------------- #

def eigenvalues(A: Matrix, max_iter: int = 500, tol: float = 1e-12) -> Vector:
    """Real eigenvalues of a square matrix via the (shifted) QR algorithm.

    Iterates ``A_{k+1} = R_k Q_k`` (with a Wilkinson shift) on the active
    leading submatrix, deflating once the trailing sub-diagonal entry is below
    ``tol``. The eigenvalues are read off the diagonal and returned sorted
    descending. Assumes a real spectrum (use :func:`eigen_symmetric` for the
    symmetric case).

    Raises :class:`EigenError` if ``A`` is not square or fails to converge.
    """
    n = _require_square(A)
    if n == 1:
        return [float(A[0][0])]

    a = _copy(A)
    eigs: Vector = []
    m = n  # active submatrix is a[0:m][0:m]

    total_iter = 0
    while m > 1:
        iters = 0
        while iters < max_iter:
            # Largest off-diagonal magnitude on the trailing sub-diagonal.
            sub = abs(a[m - 1][m - 2])
            scale = abs(a[m - 1][m - 1]) + abs(a[m - 2][m - 2])
            if sub <= tol * max(scale, 1.0):
                break

            # Wilkinson shift from the trailing 2x2 block.
            d = (a[m - 2][m - 2] - a[m - 1][m - 1]) / 2.0
            off = a[m - 1][m - 2] * a[m - 2][m - 1]
            denom = abs(d) + math.sqrt(d * d + off) if (d * d + off) >= 0 else abs(d)
            if denom < EPS:
                mu = a[m - 1][m - 1]
            else:
                sign = 1.0 if d >= 0 else -1.0
                mu = a[m - 1][m - 1] - sign * off / denom

            sub_a = [row[:m] for row in a[:m]]
            for i in range(m):
                sub_a[i][i] -= mu
            qk, rk = qr(sub_a)
            new = _matmul(rk, qk)
            for i in range(m):
                new[i][i] += mu
                for j in range(m):
                    a[i][j] = new[i][j]

            iters += 1
            total_iter += 1

        if iters >= max_iter:
            raise EigenError("eigenvalues: QR iteration did not converge")

        eigs.append(float(a[m - 1][m - 1]))
        m -= 1

    eigs.append(float(a[0][0]))
    eigs.sort(reverse=True)
    return eigs


# --------------------------------------------------------------------------- #
# Symmetric eigensystem via cyclic Jacobi rotation.
# --------------------------------------------------------------------------- #

def eigen_symmetric(
    A: Matrix, tol: float = 1e-12, max_iter: int = 200
) -> tuple[Vector, Matrix]:
    """Eigenvalues and eigenvectors of a symmetric matrix via cyclic Jacobi.

    Returns ``(eigenvalues, eigenvectors)`` where the eigenvalues are sorted
    descending and the eigenvectors form the **columns** of the returned
    matrix, aligned to that order and normalised.

    Raises :class:`EigenError` if ``A`` is not square or not (near-)symmetric.
    """
    n = _require_square(A)
    if not _is_symmetric(A, n, 1e-9):
        raise EigenError("eigen_symmetric: matrix is not symmetric")

    a = _copy(A)
    v = _identity(n)

    for _ in range(max_iter):
        # Off-diagonal Frobenius norm.
        off = math.sqrt(sum(a[p][q] ** 2 for p in range(n) for q in range(n) if p != q))
        if off <= tol:
            break
        # One full cyclic sweep over the upper triangle.
        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = a[p][q]
                if abs(apq) <= EPS:
                    continue
                app = a[p][p]
                aqq = a[q][q]
                theta = (aqq - app) / (2.0 * apq)
                t_sign = 1.0 if theta >= 0 else -1.0
                t = t_sign / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c

                # Rotate rows/columns p, q.
                for k in range(n):
                    akp = a[k][p]
                    akq = a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk = a[p][k]
                    aqk = a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk

                # Accumulate eigenvectors.
                for k in range(n):
                    vkp = v[k][p]
                    vkq = v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    else:
        raise EigenError("eigen_symmetric: Jacobi iteration did not converge")

    vals = [float(a[i][i]) for i in range(n)]
    # Sort descending, reorder eigenvector columns to match.
    order = sorted(range(n), key=lambda i: vals[i], reverse=True)
    sorted_vals = [vals[i] for i in order]
    vecs = [[v[r][order[c]] for c in range(n)] for r in range(n)]

    # Normalise each eigenvector column.
    for c in range(n):
        norm = math.sqrt(sum(vecs[r][c] ** 2 for r in range(n)))
        if norm > EPS:
            for r in range(n):
                vecs[r][c] /= norm
    return sorted_vals, vecs


# --------------------------------------------------------------------------- #
# Condition number.
# --------------------------------------------------------------------------- #

def condition_number(A: Matrix) -> float:
    """Return the 2-norm condition number ``σmax/σmin`` of ``A``.

    Computed as ``sqrt(λmax/λmin)`` of the symmetric matrix ``AᵀA`` (whose
    eigenvalues are the squared singular values of ``A``).

    Raises :class:`EigenError` if ``A`` is singular (a near-zero singular value).
    """
    _validate(A)
    at = _transpose(A)
    ata = _matmul(at, A)
    vals, _ = eigen_symmetric(ata)
    lam_max = vals[0]
    lam_min = vals[-1]
    if lam_min <= EPS or lam_max <= EPS:
        raise EigenError("condition_number: matrix is singular")
    return math.sqrt(lam_max / lam_min)
