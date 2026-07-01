"""Decision-tree classification (CART) and a small random forest — no numpy.

Everything here is implemented by hand with the standard library only
(``math``, ``random``, ``collections``). Data is plain Python:

* ``X`` is a ``list[list[float]]`` — rows are samples, columns are numeric
  features.
* ``y`` is a ``list`` of class labels (any hashable: ``str`` or ``int``).

The surface covers the classic teaching staples:

* :class:`DecisionTreeClassifier` — CART greedy binary splits on
  ``x[f] <= threshold``, choosing the (feature, threshold) pair that maximises
  the weighted impurity decrease (Gini or entropy). Leaves predict the
  majority class.
* :class:`RandomForestClassifier` — an ensemble of trees, each fitted on a
  bootstrap sample of the rows and a random subset of the features, combined
  by majority vote.

Determinism is total: every random choice flows through
:class:`random.Random` seeded by the caller-supplied ``seed`` (per-tree seeds
are derived from it). Two fits with the same seed produce identical models.

Bad input (empty/ragged ``X``, shape mismatch ``len(X) != len(y)``) raises
:class:`TreeError`.

Pure stdlib → core.
"""

from __future__ import annotations

import math
import random
from collections import Counter

Matrix = list[list[float]]


class TreeError(Exception):
    """Raised for invalid data or shape mismatches."""


# --------------------------------------------------------------------------- #
# Validation helpers.
# --------------------------------------------------------------------------- #

def _validate_fit(X: Matrix, y: list) -> tuple[int, int]:
    """Validate training data; return ``(n_samples, n_features)``.

    Raises :class:`TreeError` on empty/ragged ``X`` or ``len(X) != len(y)``.
    """
    if not isinstance(X, list) or not X:
        raise TreeError("X must be a non-empty list of rows")
    n_features: int | None = None
    for row in X:
        if not isinstance(row, list) or not row:
            raise TreeError("each row of X must be a non-empty list")
        if n_features is None:
            n_features = len(row)
        elif len(row) != n_features:
            raise TreeError("X is ragged (rows of differing length)")
    if not isinstance(y, list) or len(y) != len(X):
        raise TreeError("len(X) must equal len(y)")
    assert n_features is not None
    return len(X), n_features


# --------------------------------------------------------------------------- #
# Impurity.
# --------------------------------------------------------------------------- #

def _gini(labels: list) -> float:
    """Gini impurity of a label list (0.0 for an empty or pure list)."""
    n = len(labels)
    if n == 0:
        return 0.0
    total = 0.0
    for count in Counter(labels).values():
        p = count / n
        total += p * p
    return 1.0 - total


def _entropy(labels: list) -> float:
    """Shannon entropy (base 2) of a label list (0.0 if empty/pure)."""
    n = len(labels)
    if n == 0:
        return 0.0
    total = 0.0
    for count in Counter(labels).values():
        p = count / n
        total -= p * math.log2(p)
    return total


_IMPURITY = {"gini": _gini, "entropy": _entropy}


def _majority(labels: list) -> object:
    """Most common label; ties broken by first-seen order (stable)."""
    counts = Counter(labels)
    best = counts.most_common(1)[0][1]
    for label in labels:
        if counts[label] == best:
            return label
    return labels[0]


# --------------------------------------------------------------------------- #
# Node.
# --------------------------------------------------------------------------- #

class _Node:
    """A decision-tree node: either an internal split or a leaf."""

    __slots__ = ("feature", "threshold", "left", "right", "label")

    def __init__(self) -> None:
        self.feature: int | None = None
        self.threshold: float = 0.0
        self.left: _Node | None = None
        self.right: _Node | None = None
        self.label: object = None

    @property
    def is_leaf(self) -> bool:
        return self.feature is None


# --------------------------------------------------------------------------- #
# Decision tree.
# --------------------------------------------------------------------------- #

class DecisionTreeClassifier:
    """CART decision-tree classifier (binary numeric splits)."""

    def __init__(self, max_depth: int | None = None, min_samples_split: int = 2,
                 criterion: str = "gini", seed: int = 0) -> None:
        if criterion not in _IMPURITY:
            raise TreeError(f"unknown criterion: {criterion!r}")
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.criterion = criterion
        self.seed = seed
        self._impurity = _IMPURITY[criterion]
        self._root: _Node | None = None
        # Features considered at each split. ``None`` means "all of them";
        # the random forest passes an explicit subset per tree.
        self._features: list[int] | None = None

    # -- public API -------------------------------------------------------- #

    def fit(self, X: Matrix, y: list) -> "DecisionTreeClassifier":
        """Grow the tree from training data; returns ``self``."""
        n_samples, n_features = _validate_fit(X, y)
        if self._features is None:
            features = list(range(n_features))
        else:
            features = [f for f in self._features if 0 <= f < n_features]
            if not features:
                features = list(range(n_features))
        rows = list(range(n_samples))
        self._root = self._build(X, y, rows, features, depth=0)
        return self

    def predict(self, X: Matrix) -> list:
        """Predict labels for every row of ``X``."""
        if self._root is None:
            raise TreeError("model is not fitted")
        if not isinstance(X, list):
            raise TreeError("X must be a list of rows")
        return [self.predict_one(x) for x in X]

    def predict_one(self, x: list[float]) -> object:
        """Predict the label for a single feature vector."""
        node = self._root
        if node is None:
            raise TreeError("model is not fitted")
        while not node.is_leaf:
            assert node.feature is not None
            if x[node.feature] <= node.threshold:
                node = node.left  # type: ignore[assignment]
            else:
                node = node.right  # type: ignore[assignment]
            assert node is not None
        return node.label

    def depth(self) -> int:
        """Depth of the fitted tree (0 for a single leaf)."""
        if self._root is None:
            raise TreeError("model is not fitted")
        return self._depth(self._root)

    # -- internals --------------------------------------------------------- #

    def _depth(self, node: _Node) -> int:
        if node.is_leaf:
            return 0
        assert node.left is not None and node.right is not None
        return 1 + max(self._depth(node.left), self._depth(node.right))

    def _build(self, X: Matrix, y: list, rows: list[int],
               features: list[int], depth: int) -> _Node:
        node = _Node()
        labels = [y[i] for i in rows]
        node.label = _majority(labels)

        # Stop: pure node, depth cap, too few samples to split.
        if len(set(labels)) <= 1:
            return node
        if self.max_depth is not None and depth >= self.max_depth:
            return node
        if len(rows) < self.min_samples_split:
            return node

        split = self._best_split(X, y, rows, features)
        if split is None:
            return node
        feature, threshold, left_rows, right_rows = split

        node.feature = feature
        node.threshold = threshold
        node.left = self._build(X, y, left_rows, features, depth + 1)
        node.right = self._build(X, y, right_rows, features, depth + 1)
        return node

    def _best_split(self, X: Matrix, y: list, rows: list[int],
                    features: list[int]):
        """Find the split that minimises weighted child impurity.

        Returns ``(feature, threshold, left_rows, right_rows)`` or ``None``.

        The split with the largest weighted impurity decrease wins. When no
        split yields a *positive* decrease (e.g. balanced XOR at the root,
        where every axis-aligned split alone is uninformative) but the node
        is impure, the best zero-gain split is still taken so that deeper
        levels can separate the classes — this is what lets a greedy tree
        recover XOR. A split is only accepted if at least one child is
        strictly purer than the parent, which prevents infinite recursion on
        truly inseparable rows.
        """
        n = len(rows)
        parent_labels = [y[i] for i in rows]
        parent_impurity = self._impurity(parent_labels)

        best_weighted = parent_impurity
        best: tuple[int, float, list[int], list[int]] | None = None

        for f in features:
            # Candidate thresholds: midpoints of consecutive sorted unique
            # values of this feature over the node's rows.
            values = sorted({X[i][f] for i in rows})
            if len(values) < 2:
                continue
            thresholds = [
                (values[k] + values[k + 1]) / 2.0
                for k in range(len(values) - 1)
            ]
            for threshold in thresholds:
                left_rows: list[int] = []
                right_rows: list[int] = []
                for i in rows:
                    if X[i][f] <= threshold:
                        left_rows.append(i)
                    else:
                        right_rows.append(i)
                if not left_rows or not right_rows:
                    continue
                left_labels = [y[i] for i in left_rows]
                right_labels = [y[i] for i in right_rows]
                left_imp = self._impurity(left_labels)
                right_imp = self._impurity(right_labels)
                weighted = (
                    len(left_rows) / n * left_imp
                    + len(right_rows) / n * right_imp
                )
                if weighted < best_weighted - 1e-12:
                    best_weighted = weighted
                    best = (f, threshold, left_rows, right_rows)

        if best is not None:
            return best

        # No strictly-improving split. The node is impure but every
        # axis-aligned split alone is uninformative (the classic balanced-XOR
        # root). Take the best *zero-gain* split — one that actually
        # partitions the rows — so deeper levels can finish separating the
        # classes. Recursion still terminates: a child either becomes pure or
        # eventually has < 2 unique values on every feature (identical rows),
        # at which point this search returns ``None`` and the node is a leaf.
        for f in features:
            values = sorted({X[i][f] for i in rows})
            if len(values) < 2:
                continue
            threshold = (values[0] + values[1]) / 2.0
            left_rows = [i for i in rows if X[i][f] <= threshold]
            right_rows = [i for i in rows if X[i][f] > threshold]
            if left_rows and right_rows:
                return (f, threshold, left_rows, right_rows)

        return None


# --------------------------------------------------------------------------- #
# Random forest.
# --------------------------------------------------------------------------- #

class RandomForestClassifier:
    """A small bagged ensemble of :class:`DecisionTreeClassifier` trees."""

    def __init__(self, n_trees: int = 10, max_depth: int | None = None,
                 min_samples_split: int = 2, sample_frac: float = 1.0,
                 feature_frac: float | None = None, seed: int = 0) -> None:
        if n_trees < 1:
            raise TreeError("n_trees must be >= 1")
        if not 0.0 < sample_frac <= 1.0:
            raise TreeError("sample_frac must be in (0, 1]")
        if feature_frac is not None and not 0.0 < feature_frac <= 1.0:
            raise TreeError("feature_frac must be in (0, 1]")
        self.n_trees = n_trees
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.sample_frac = sample_frac
        self.feature_frac = feature_frac
        self.seed = seed
        self._trees: list[DecisionTreeClassifier] = []

    def fit(self, X: Matrix, y: list) -> "RandomForestClassifier":
        """Fit ``n_trees`` trees on bootstrap samples; returns ``self``."""
        n_samples, n_features = _validate_fit(X, y)
        rng = random.Random(self.seed)

        if self.feature_frac is None:
            k_features = max(1, int(math.isqrt(n_features)))
        else:
            k_features = max(1, int(round(self.feature_frac * n_features)))
        k_features = min(k_features, n_features)

        n_sample = max(1, int(round(self.sample_frac * n_samples)))

        self._trees = []
        for t in range(self.n_trees):
            # Per-tree derived seed keeps each tree independent yet
            # reproducible across fits with the same forest seed.
            tree_seed = rng.randrange(2**31)
            tree_rng = random.Random(tree_seed)

            # Bootstrap sample of rows (with replacement).
            idx = [tree_rng.randrange(n_samples) for _ in range(n_sample)]
            Xb = [X[i] for i in idx]
            yb = [y[i] for i in idx]

            # Random feature subset considered at every split of this tree.
            feats = sorted(tree_rng.sample(range(n_features), k_features))

            tree = DecisionTreeClassifier(
                max_depth=self.max_depth,
                min_samples_split=self.min_samples_split,
                criterion="gini",
                seed=tree_seed,
            )
            tree._features = feats
            tree.fit(Xb, yb)
            self._trees.append(tree)
        return self

    def predict(self, X: Matrix) -> list:
        """Majority vote across all trees for every row of ``X``."""
        if not self._trees:
            raise TreeError("model is not fitted")
        if not isinstance(X, list):
            raise TreeError("X must be a list of rows")
        per_tree = [tree.predict(X) for tree in self._trees]
        result: list = []
        for row_idx in range(len(X)):
            votes = [per_tree[t][row_idx] for t in range(len(self._trees))]
            result.append(_majority(votes))
        return result
