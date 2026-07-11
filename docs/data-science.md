# Data science with abax

abax is an integrated environment for working with data: a fast, keyboard-first
spreadsheet with statistics, analysis, visualization, and scripting built in. You
can take a dataset from raw file to finished analysis without leaving the window —
and drop into Python or pandas the moment you want to. This page walks the
end-to-end workflow and then documents the **deep numeric stack**: descriptive
stats and distributions, hypothesis tests, regression, the machine-learning
models, model evaluation, the linear-algebra/engineering toolkit, and the
signal/DSP + ODE solvers.

Everything here works with abax's **pure-stdlib core**; heavier libraries
(`scipy`, `statsmodels`, `pandas`, …) make some tools richer but are almost never
required — abax degrades gracefully when they're absent. The everyday
reshaping/cleaning/reporting tools (pivots, recode, profiling, SQL, goal seek,
compare, HTML export, charts, the pandas hand-off) are documented in the
companion page, [data & analysis](data-analysis.md); this page cross-links to it
rather than repeating them.

## The design: pure-stdlib core, optional acceleration

The scientific engines live in `abax/core/science/` and are written **by hand
against the standard library only** — `math`, `cmath`, `statistics`, `random`,
`bisect` — with **no numpy or scipy import**. That means the statistics,
regression, ML, clustering, naive Bayes, trees, linear algebra, FFT/DSP, ODE,
and unit-conversion engines all run headless, offline, with nothing installed.

Optional packages are upgrades, not requirements, and abax tells you (and falls
back) when one is missing:

- The **Statistics / analysis GUI tool** ([`abax/engine/analysis.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/analysis.py))
  prefers `scipy` / `statsmodels` / `pingouin` / `lifelines` for a few tests but
  keeps stdlib fallbacks where it can.
- When `numpy` is present it **accelerates large aggregate reductions**
  (`SUM`/`AVERAGE`/`MIN`/`MAX`/`COUNT`/… over big all-numeric ranges) ~3–4× —
  automatically and with identical results to the pure-Python path.
- The `core/science` engines themselves stay stdlib-only regardless.

Run `abax --deps` to see what's available. See [configuration](configuration.md).

## The workflow

### 1. Import

Open or import data in almost any tabular format — CSV/TSV, Excel `.xlsx`,
LibreOffice `.ods`, Parquet/Feather, SQLite, JSON / JSON Lines, R `data.frame`,
Jupyter notebooks, Markdown tables, or the native `.abax` workbook. Large CSVs
stream in with type inference and an optional row cap. See
[file formats](file-formats.md). From the shell, `abax data.csv` opens it
straight in the GUI.

### 2. Explore

- **Selection statistics** — select a range and the status bar shows Sum,
  Average, Min, Max, and Count instantly (see the [GUI guide](gui-guide.md)).
- **Formula functions** — 642 of them (100% of the curated Excel/Gnumeric target),
  including the full aggregate and statistics families (`AVERAGE`, `MEDIAN`,
  `STDEV`, `VAR`, `PERCENTILE`, `QUARTILE`, `CORREL`, `COVAR`, `SKEW`, `KURT`,
  `RANK`, …) and statistical distributions (`NORMDIST`, `TDIST`, `FDIST`,
  `CHIDIST` and their inverses, `CONFIDENCE`). See the
  [formula reference](formula-reference.md).
- **Descriptive Statistics** and **Profile columns** (both Data → Analyze) give a
  one-click summary — the former a full 16-measure describe of one range, the
  latter a per-column describe of the whole sheet — see
  [data & analysis](data-analysis.md#descriptive-statistics).

### 3. Analyze

- The **Statistics / analysis tool** (Data → Analyze) runs descriptive
  statistics, linear regression, t-tests, one-way ANOVA, correlation, normality,
  and Kaplan–Meier survival on the selected columns — see below.
- **Nonparametric / rank tests** — when normality is in doubt, the `nonparam`
  console engine adds Mann-Whitney, Wilcoxon signed-rank, Kruskal-Wallis,
  Spearman, and Kendall (pure stdlib, real p-values) — see below.
- **Curve fit** and **Goal seek** (Data → Analyze) fit a model to XY data or solve
  for the input that hits a target — see
  [data & analysis](data-analysis.md#curve-fit).
- **Distribution formulas** give you critical values and p-values directly in
  cells — e.g. `=TINV(0.05,10)` for a t critical value, `=CHIDIST(x,df)` for a
  chi-square tail probability.
- The **calculators** (RPN, graphing, and algebraic) sit beside the grid with a
  two-way value bridge — pull a cell into the calculator and send a result back.
  See [calculators](calculators.md).

### 4. Reshape & clean

- **Pivot / group-by**, **Recode / clean column**, **SQL query**, sort, filter,
  fill, and conditional formatting for fast tidying — all in
  [data & analysis](data-analysis.md).

### 5. Visualize

The built-in grapher renders scatter plots, histograms, regression lines, FFT and
spectrograms, PCA projections, clustering, and ROC curves — no matplotlib
required — and `chartsvg` exports standalone SVG line/bar/scatter/histogram
charts. See [data & analysis](data-analysis.md#graph--chart). The ML tool adds
PCA, k-means, GMM, regression, decision trees/forests, and naive Bayes (below).

### 6. Script & extend

- **Open selection in pandas** hands a range to a pandas `DataFrame`; the
  **embedded Python console** is wired to the live workbook with every science
  engine in scope (see [the console namespace](data-analysis.md#the-console-namespace)).
- **Macros and UDFs** (`@macro`, `@register_function`) automate workflows and add
  your own formula functions; the **recorder** captures edits as a runnable macro.
  See [macros & scripting](macros-and-scripting.md). *(Macros and the console run
  untrusted code — only run scripts you trust.)*

### 7. Export & share

Save to any supported format (computed values or formulas), export an
[HTML report](data-analysis.md#export-as-html-report), or convert headlessly with
`abax convert in.csv out.parquet`. See the [CLI](cli.md).

## Coming from R or a spreadsheet?

| You want… | In abax |
|-----------|----------|
| `mean`, `sd`, `median`, `quantile` | `AVERAGE`, `STDEV`, `MEDIAN`, `PERCENTILE`/`QUARTILE` |
| `lm()` / trendline | Analysis tool → regression, or `SLOPE`/`INTERCEPT`/`RSQ`/`FORECAST` |
| `t.test`, `aov`, `cor.test` | Analysis tool (t-tests, ANOVA, correlation), or `TTEST` |
| `wilcox.test`, `kruskal.test`, `cor.test(method=…)` | `nonparam` (Mann-Whitney, Wilcoxon, Kruskal-Wallis, Spearman, Kendall) |
| `pnorm`/`qnorm`, `pt`/`qt`, `pf`, `pchisq` | `NORMDIST`/`NORMINV`, `TDIST`/`TINV`, `FDIST`, `CHIDIST` |
| `chisq.test` | `stats.chi_square` (console), or `CHIDIST` for the tail |
| `nls()` / `lm(y ~ poly(x))` / curve fitting | Curve fit tool, or `curvefit` (poly / exp / power) |
| `prcomp` / `kmeans` | ML tool → PCA / k-means, or `ml.pca` / `cluster.kmeans` |
| `randomForest` / `rpart` / `naiveBayes` | ML tool, or `trees` / `bayes` (console) |
| `solve()` / `eigen()` / `qr()` / `chol()` | Matrix tool, or `matrix` / `eigen` |
| `fft` / `filter` / `spec.pgram` | Signal tool, or `fft` / `filters` / `spectral` |
| `deSolve` / `ode()` | ODE solver, or `ode` / `ode_implicit` |
| a data frame | Open selection in pandas, or the embedded Python console |
| `dplyr` group/summarize | Pivot / group-by |
| `ggplot`-style quick plots | The grapher, or `chartsvg` for exportable SVG |
| scripting a pipeline | Macros + UDFs, or the Python console |

## The Statistics / analysis tool

The GUI tool at **Data → Analyze → Statistics / analysis…** is backed by
[`abax/engine/analysis.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/analysis.py). Select a numeric range
(non-numeric first row = column names), pick an analysis, choose an output cell,
and run. The dialog shows a **summary** (statistic, p-value, effect size, and a
plain-English interpretation) and writes a result **table** back into the grid.

| Analysis | Needs | Reports |
| --- | --- | --- |
| Descriptive statistics | — (stdlib) | per column: n, mean, stdev, min, Q1, median, Q3, max |
| t-test (two columns) | `scipy` (or `pingouin`) | independent (Welch) or paired t, df, p, Cohen's d |
| One-way ANOVA | `scipy` | F, df, p, eta-squared |
| Correlation matrix | `scipy` | Pearson or Spearman r matrix + p-values |
| Linear regression (OLS) | — (fallbacks) | coefficients, std err, t, p, R², adj-R² |
| Normality (Shapiro–Wilk) | `scipy` | W, p, pass/fail at α = 0.05 |
| Kaplan–Meier survival | `lifelines` | time / at-risk / survival rows + median survival |

Graceful degradation is the rule:

- **Descriptive statistics** uses only stdlib `statistics` — it always runs.
- **Linear regression** prefers `statsmodels`, then a `numpy` least-squares
  solve, then a **pure-Python normal-equations** solve — so it also always runs,
  reporting coefficients, standard errors, t and p (via a stdlib incomplete-beta
  p-value in the pure path), R² and adjusted R².
- The **t-test** uses `pingouin` when present (tidy output with the effect size),
  otherwise `scipy.stats` with a hand-computed Cohen's d and Welch–Satterthwaite
  df; the effect is labelled negligible / small / medium / large.
- Analyses whose package is missing report a clear "… requires *pkg*" message
  rather than failing. `analysis.requirements_met(key)` reports readiness.

If you want the same tests **without any optional packages**, use the
dependency-free engine below — it is what powers the formula-level statistical
functions and returns real p-values.

## Descriptive statistics & distributions (pure stdlib)

[`abax/core/science/stats.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/stats.py) is a
dependency-free statistics toolkit computed entirely in IEEE doubles via
`math` — leaning on `math.erf` (normal CDF), `math.lgamma` (incomplete beta),
and `math.fsum` (compensated summation). It underpins the spreadsheet stats/
distribution functions and is available as `stats` in the console.

- **Descriptive** — `mean`, `median`, `mode`, `variance`, `stdev` (sample or
  population), `quantile`/`percentile`, `iqr`, `skewness`, `kurtosis` (excess by
  default), `covariance`, `correlation`, `correlation_matrix`, `describe`.
- **Distributions** — the normal `normal_pdf`/`normal_cdf`/`normal_ppf` (Acklam
  rational approximation with a Halley refinement), the Student-`t_cdf`/`t_ppf`,
  the `f_cdf`/`f_ppf`, and `chi_square_cdf`/`chi_square_ppf`. The t and F CDFs go
  through the regularized incomplete beta (`betai`, Lentz continued fraction);
  chi-square through the regularized lower incomplete gamma.

Bad input (empty data, `q`/`p` out of range, `df ≤ 0`) raises `StatsError`.

## Hypothesis tests with real p-values (pure stdlib)

Also in `stats.py` — no scipy needed, each returning `(statistic, p_value)` with
a two-sided p where applicable:

- `t_test_1samp(xs, popmean)` — one-sample t-test.
- `t_test_ind(xs, ys, equal_var=False)` — two independent samples, **Welch by
  default** (with Welch–Satterthwaite df), or pooled when `equal_var=True`.
- `t_test_paired(xs, ys)` — paired t-test on the differences.
- `anova_oneway(*groups)` — one-way ANOVA across ≥ 2 groups → `(F, p)`.
- `chi_square(observed, expected=None)` — a flat `observed` runs a
  goodness-of-fit test (uniform `expected` by default); a 2-D `observed` runs a
  **test of independence** on the contingency table (expected from the margins).
- `confidence_interval_mean(xs, confidence=0.95)` — a t-based CI for the mean.

```python
# console
t, p = stats.t_test_ind(control, treatment)      # Welch two-sample
f, p = stats.anova_oneway(g1, g2, g3)            # one-way ANOVA
chi2, p = stats.chi_square([[12, 5], [3, 20]])   # 2x2 independence test
```

## Nonparametric & rank statistics (pure stdlib)

[`abax/core/science/nonparam.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/nonparam.py) (`nonparam`
in the console) is a dependency-free companion to `stats.py` that fills the
rank-based gap — the distribution-free tests you reach for when normality is in
doubt. Everything is computed in IEEE doubles via `math` only (no scipy), reusing
the `stats` CDFs (`normal_cdf`, `t_cdf`, `chi_square_cdf`) for the p-values. Ties
are resolved with average (fractional) ranks throughout, and each test returns a
small namedtuple with the statistic plus a **two-sided** p-value:

- `mann_whitney_u(a, b)` → `(U, p)` — the Mann-Whitney U (Wilcoxon rank-sum) test
  for two independent samples; the tie correction is applied to the variance and
  a continuity correction to the z-score. `U` is the smaller of the two group U's.
- `wilcoxon_signed_rank(a, b)` → `(W, p)` — the paired signed-rank test on the
  nonzero differences (zeros dropped), tie- and continuity-corrected.
- `kruskal_wallis(*groups)` → `(H, df, p)` — the nonparametric one-way ANOVA
  across ≥ 2 groups, tie-corrected, with a chi-square p-value on `k − 1` df.
- `spearman_rho(a, b)` → `(rho, p)` — Spearman's rank correlation, with a
  Student-t approximation on `n − 2` df.
- `kendall_tau(a, b)` → `(tau, p)` — Kendall's tie-adjusted **tau-b**, with a
  normal-approximation p-value.

Degenerate inputs — empty or mismatched samples, or all-tied data where a
statistic is undefined — raise `StatsError` rather than returning a bogus number.

```python
# console
u, p = nonparam.mann_whitney_u(control, treatment)   # rank-sum, two-sided
h, df, p = nonparam.kruskal_wallis(g1, g2, g3)       # nonparametric ANOVA
rho, p = nonparam.spearman_rho(x, y)                 # rank correlation
```

## Regression, forecasting & curve fitting (pure stdlib)

[`abax/core/science/regression.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/regression.py) mirrors
the familiar spreadsheet trend/forecast/linest family, hand-solved with the
standard library:

- `linregress(xs, ys)` — simple OLS via the closed-form normal equations →
  `{slope, intercept, r, r2, stderr, n}` (stderr is the standard error of the
  slope). Convenience wrappers `slope`, `intercept`, `rsq`, `correl`.
- `forecast(x, xs, ys)` / `trend(xs, ys, new_xs)` — linear prediction at new x.
- `polyfit(xs, ys, degree)` / `polyval(coeffs, x)` — least-squares polynomial fit
  (Gaussian elimination with partial pivoting) and Horner evaluation.

For **multiple** regression (many predictors) use `ml.linear_regression` (below)
or the OLS analysis tool. These functions back `SLOPE`, `INTERCEPT`, `RSQ`,
`CORREL`, `FORECAST`, `TREND`, and the polynomial helpers in the
[formula reference](formula-reference.md).

**Curve fitting** — [`abax/core/science/curvefit.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/curvefit.py)
builds on the same least-squares machinery to fit named models and report their
goodness-of-fit, and is what the [Curve fit tool](data-analysis.md#curve-fit)
calls:

- `polyfit(xs, ys, degree)` → `(coeffs, r2)` — a polynomial of any degree
  (degree 1 agrees exactly with `linregress`); solved by Gaussian elimination
  with partial pivoting. `polyval(coeffs, x)` evaluates it (Horner).
- `expfit(xs, ys)` → `(a, b, r2)` — `y = a·e^(b·x)` by log-linear regression on
  `ln(y)` (requires every `y > 0`).
- `powerfit(xs, ys)` → `(a, b, r2)` — `y = a·x^b` by log-log regression
  (requires every `x > 0` and `y > 0`).

Crucially, `r_squared` (and every fit's reported `r2`) is computed on the
**original** `y` values, not the transformed logs, so the goodness-of-fit is
directly comparable across the linear, polynomial, exponential, and power models.
Bad input (mismatched lengths, `degree < 0`, `n ≤ degree`, a non-positive value
for a log model, or a singular system) raises `RegressionError`.

## The machine-learning stack

The **ML tool** at **Tools → Scientific → ML tool…**
([`gui/dialogs/ml_dialog.py`](https://github.com/leavesofgrass/abax/blob/main/abax/gui/dialogs/ml_dialog.py)) works over a
numeric samples × features matrix and writes scores/labels/coefficients back to
the grid. Its operations are: **PCA** (param = #components), **K-means**
(param = k), **Suggest #clusters** (param = max k), **GMM cluster**
(param = #components), **Linear regression** (last column = `y`), **Standardize**
(z-score), and **Decision tree / Random forest / Naive Bayes** classification
(last column = the label `y`). All of it is pure-Python — **no numpy or
scikit-learn required**. *Suggest #clusters* sweeps `k = 2…max_k` and writes a
per-*k* table of inertia, mean silhouette, and (when the GMM fits) BIC/AIC, then
reports the recommended *k* — see [choosing the cluster count](#choosing-the-cluster-count)
below. The same engines are in the console:

**`ml`** ([`ml.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/ml.py)) — `standardize` (column z-score),
`pca` (covariance eigendecomposition via the in-house symmetric eigensolver,
returning components, explained-variance ratios, and the projected data),
`linear_regression`/`predict_linear`/`r_squared` (multiple OLS via the normal
equations), `knn_classify`/`knn_predict` (k-nearest-neighbours voting), and
`logistic_regression`/`logistic_predict[_proba]` (binary logistic regression by
gradient descent, features standardised internally then mapped back).

**`cluster`** ([`cluster.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/cluster.py)) — `kmeans`
(Lloyd's iteration with **k-means++** seeding, returning labels, centroids, and
inertia; empty clusters re-seeded), `kmeans_predict`, `agglomerative`
(bottom-up hierarchical with single/complete/average linkage), `dbscan`
(density-based, noise labelled `-1`), and `silhouette_score` for cluster quality.
Two helpers pick the cluster count: `elbow(points, k_range)` returns the
`(k, inertia)` curve (the drop flattens at a good `k`), and
`best_k_silhouette(points, k_range)` returns `(best_k, scores)`, the `k` that
maximises the mean silhouette (each `k ≥ 2`). Randomness flows through a seeded
`random.Random`, so results are reproducible.

**`gmm`** ([`gmm.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/gmm.py)) — `GaussianMixture`, a
diagonal-covariance mixture fitted by **Expectation-Maximization** (E-step in log
space with per-row max subtraction for stability, k-means++-style init). Exposes
`means_`, `covariances_`, `weights_`, `converged_`, `predict[_proba]`, `score`,
and `bic`/`aic` for model selection (choosing the number of components).
`gmm_model_selection(points, k_range)` fits a mixture at every `k` and returns the
per-`k` BIC/AIC scores together with the `k` each criterion prefers.

**`trees`** ([`trees.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/trees.py)) —
`DecisionTreeClassifier` (CART greedy binary splits on `x[f] <= threshold`,
Gini or entropy impurity, majority-class leaves) and `RandomForestClassifier`
(bagged ensemble: each tree on a bootstrap row sample and a random feature
subset, combined by majority vote). Fully deterministic under a `seed`.

**`bayes`** ([`bayes.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/bayes.py)) — `GaussianNB`
(continuous features as per-class Gaussians, with variance smoothing) and
`MultinomialNB` (non-negative counts / bag-of-words with Laplace smoothing).
Both work in log-space and softmax-normalise; `predict`, `predict_proba`, and
`classes` follow the familiar scikit-learn surface.

```python
# console: fit a random forest, then score it
model = trees.RandomForestClassifier(n_trees=50, seed=0).fit(X_train, y_train)
preds = model.predict(X_test)
```

### Choosing the cluster count

k-means and GMM both need you to *pick* the number of clusters, so abax ships
three helpers to guide that choice — the same ones the ML tool's
**Suggest #clusters** operation drives:

- `cluster.elbow(points, k_range)` — the `(k, inertia)` **elbow curve**. Inertia
  (within-cluster sum of squared distances) always falls as `k` grows; the
  "elbow", where the drop flattens, is the visual cue for a good `k`.
- `cluster.best_k_silhouette(points, k_range)` — `(best_k, scores)`, where each
  candidate `k ≥ 2` is scored by its **mean silhouette** and `best_k` is the
  maximiser (higher is better; the first wins on ties).
- `gmm.gmm_model_selection(points, k_range)` — fits a Gaussian mixture at every
  `k` and returns each `k`'s **BIC** and **AIC** plus `best_bic` / `best_aic`
  (both criteria trade fit against complexity, so the *smallest* is best).

The GUI operation sweeps `k = 2…max_k` (from the Param box, capped at n−1), writes
a per-`k` table of inertia, silhouette, and — when the mixtures fit — GMM BIC/AIC,
and reports the recommended `k` in the status bar. Together, an elbow, the
silhouette peak, and the information criteria usually agree on a sensible count.

## Model evaluation (pure stdlib)

[`abax/core/science/metrics.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/metrics.py) (`metrics` in
the console) covers the common evaluation chores, all from raw counts — no numpy
or sklearn — and seedable for reproducible splits:

- `train_test_split(X, y, test_frac=0.25, seed=0)` — reproducible shuffle/split.
- `kfold_indices(n, k=5, seed=0)` — disjoint, near-equal `(train, test)` folds;
  `cross_val_score(model_factory, X, y, k)` fits a fresh model per fold and
  returns the per-fold accuracies (any object with `.fit`/`.predict`).
- `confusion_matrix(y_true, y_pred)` → `(labels, matrix)`.
- `accuracy`, and `precision_recall_f1(…, average="binary"|"macro")`.
- `roc_curve(y_true, scores)` → `(fpr, tpr, thresholds)` and `auc(fpr, tpr)`
  (trapezoidal). The grapher's **ROC curve** plot uses this.

## Distribution & diagnostic charts

Beyond the line/bar/scatter/histogram charts, the pure-stdlib SVG generator
[`abax/core/science/chartsvg.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/chartsvg.py) (`chartsvg`
in the console) renders the diagnostic plots a statistician reaches for — each a
complete, self-contained `<svg>…</svg>` string with no rendering backend:

- `box_svg(series)` — a **box-and-whisker** plot per named series
  (`[(name, values), …]`): the box spans Q1–Q3 with a median line, whiskers reach
  the extremes within 1.5·IQR, and points beyond are drawn as outlier dots.
- `violin_svg(series)` — a **violin** plot: a mirrored density silhouette per
  series from a small stdlib Gaussian **KDE** (Silverman-rule bandwidth), with the
  median marked.
- `ecdf_svg(series)` — the **empirical CDF** as a right-continuous step curve per
  series (rising 0 → 1), each in its own colour with a legend.
- `qq_svg(values)` — a **normal Q-Q** plot of sample vs theoretical quantiles
  (Blom plotting positions through `stats.normal_ppf`) with a reference line — a
  quick visual normality check to pair with the Shapiro–Wilk test above.
- `heatmap_svg(matrix, labels=…)` — a **heatmap** of a 2-D matrix on the viridis
  colormap with a value scale; pass a square matrix plus `labels` to render a
  **correlation heatmap** (e.g. from `stats.correlation_matrix`).

```python
# console: a correlation heatmap from the stats engine
rows = read_matrix("A2:C100")             # list of [x, y, z] rows
cols = list(map(list, zip(*rows)))        # -> three columns
svg = chartsvg.heatmap_svg(stats.correlation_matrix(cols),
                           labels=["x", "y", "z"], title="correlation")
```

## Linear algebra & the engineering toolkit

The **Matrix tool** at **Tools → Scientific → Matrix tool…**
([`gui/dialogs/matrix_dialog.py`](https://github.com/leavesofgrass/abax/blob/main/abax/gui/dialogs/matrix_dialog.py)) reads
numeric ranges and computes transpose, inverse, determinant, multiply (A·B),
solve (A·x = b), eigenvalues, Cholesky factor, QR (Q and R), and condition
number. Matrix results are written back from a target cell; scalars (determinant,
condition number) go to the status line. Two engines back it, both **no-numpy**:

- **`matrix`** ([`matrix.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/matrix.py)) — `shape`,
  `identity`, `transpose`, `trace`, `add`/`sub`/`scalar_mul`/`matmul`,
  `determinant` (LU with partial pivoting), `inverse` (Gauss–Jordan), and `solve`
  for `A x = b`. Singular/mismatched inputs raise `MatrixError`.
- **`eigen`** ([`eigen.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/eigen.py)) — `eigenvalues`
  (Wilkinson-shifted QR algorithm), `eigen_symmetric` (eigenpairs via cyclic
  **Jacobi** rotation), `lu` (P·A = L·U), `qr` (Householder reflections),
  `cholesky` (for symmetric positive-definite A), and `condition_number` (2-norm
  σmax/σmin).

**Numerical solver** — **Tools → Scientific → Numerical solver…**
([`solver_dialog.py`](https://github.com/leavesofgrass/abax/blob/main/abax/gui/dialogs/solver_dialog.py)) solves an expression
`f(x)`: **root** by bisection `[a,b]` or **Newton** (`x₀`), definite **integral**
over `[a,b]`, or **derivative** at `x₀`. Backed by
[`numeric.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/numeric.py): `bisection`, `newton` (analytic
or auto central-difference derivative), `secant`, `integrate` (composite Simpson
/ trapezoid), `trapz` (over sampled columns), and `derivative`. All guard against
non-finite intermediates and raise `NumericError` rather than returning garbage.

**Unit conversion** — the `CONVERT` **formula function**
([`core/functions`](https://github.com/leavesofgrass/abax/blob/main/abax/core/functions), engine
[`units.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/units.py)) converts a value between two units in
one physical category: length, mass, time, area, volume, energy, power, pressure,
speed, angle, temperature, and data. Scale categories use a base-unit factor;
temperature is affine (offset + scale) and special-cased. Canonical symbols are
case-sensitive (`km`, `KiB`) with common aliases accepted; an unknown unit or a
cross-category pair raises `UnitError`.

## Signal processing & DSP

The **Signal / data tool** at **Tools → Scientific → Signal / data tool…**
([`signal_dialog.py`](https://github.com/leavesofgrass/abax/blob/main/abax/gui/dialogs/signal_dialog.py)) applies a chosen
operation to the selected column(s): FFT magnitude / phase, power spectrum,
moving average, exponential smoothing, min-max / z-score normalize, detrend,
cumulative sum, autocorrelation, a Hann window, Butterworth low/high-pass, FIR
low-pass, a spectrogram (dB), a Welch PSD (dB; two columns = I/Q), and RMS. All
pure-stdlib, drawn from these engines (also in the console):

- **`signal`** ([`signal.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/signal.py)) —
  `moving_average`, `exponential_smoothing`, `cumulative_sum`, `diff`,
  `hann`/`hamming`/`blackman` windows + `apply_window`, `normalize`
  (minmax/zscore/peak), `detrend`, `rms`, `autocorrelation`. (This is a package
  submodule, so it does not shadow the stdlib `signal` module.)
- **`fft`** ([`fft.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/fft.py)) — `dft`, radix-2
  Cooley–Tukey `fft` (falling back to `dft` for non-power-of-two lengths),
  `ifft`, plus `magnitude`, `phase`, `power_spectrum`, `frequencies`,
  `rfft_magnitude` (one-sided real spectrum), and `convolve`. Works in Python
  `complex` via `cmath` — no numpy.
- **`spectral`** ([`spectral.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/spectral.py)) — `stft`
  and `spectrogram` (power in dB) over sliding windowed frames, `fft_convolve`
  (FFT-based linear convolution), and `next_pow2`.
- **`filters`** ([`filters.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/filters.py)) — Butterworth
  IIR design (`butter_lowpass`/`butter_highpass`/`butter_bandpass` via the analog
  prototype + bilinear transform), `lfilter` (direct-form-II transposed),
  `filtfilt` (zero-phase forward-then-reverse), and windowed-sinc FIR
  (`fir_lowpass`, `fir_filter`).
- **`interp`** ([`interp.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/interp.py)) — 1-D `linear`,
  `nearest`, `lagrange`, and natural cubic spline
  (`cubic_spline_coeffs`/`cubic_spline`), plus `resample`.
- **`resynth`** ([`resynth.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/resynth.py)) — the full
  complex STFT (`stft_complex`), inverse STFT by weighted overlap-add (`istft`),
  round-trip `reconstruct`, and `griffin_lim` (recover a signal from
  magnitude-only spectra by alternating projection).

## ODE solvers (including stiff)

The **ODE solver** at **Tools → Scientific → ODE solver…**
([`ode_dialog.py`](https://github.com/leavesofgrass/abax/blob/main/abax/gui/dialogs/ode_dialog.py)) integrates an
initial-value problem `dy/dt = f(t, y)` and writes the trajectory to the sheet,
choosing an explicit or a stiff method:

- **`ode`** ([`ode.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/ode.py)) — fixed-step `euler` and
  classic 4th-order `rk4`, plus adaptive `rk45` (Runge–Kutta–Fehlberg with
  step-size control that lands exactly on `t1`). `solve(...)` dispatches by name.
- **`ode_implicit`** ([`ode_implicit.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/ode_implicit.py))
  — implicit/**stiff** solvers for problems where explicit steps must be
  absurdly tiny to stay stable: `backward_euler` (L-stable, 1st order),
  `implicit_trapezoid` (Crank–Nicolson, A-stable, 2nd order), and `bdf2`. Each
  step solves its nonlinear system by Newton iteration with a finite-difference
  Jacobian; `solve_stiff(...)` dispatches by name.

The state is always a vector (`list[float]`); a scalar ODE is a one-element list.
Bad arguments or a step that can't make progress raise `ODEError` / `StiffODEError`.

## Optional dependencies

abax works headless and offline with nothing but the standard library — every
`core/science` engine on this page runs with zero optional packages. Installing
`scipy`/`statsmodels`/`pingouin`/`lifelines` deepens the **Statistics / analysis
GUI tool**, `pandas` enables the DataFrame hand-off and Parquet, and `openpyxl`
enables Excel — but each is optional, and abax tells you (and falls back) when
one is missing. Run `abax --deps` to see what's available.

abax installs **nothing on its own**: on first launch it shows a chooser where you
pick the optional features you want — **nothing is selected by default.** Choose the
**All** preset (or tick *Data science*) to get this analysis stack, add it later from
**Tools → Install optional features** / **Preferences → System**, or install it up
front with `abax deps` (disable installs entirely with `auto_install: false` or
`ABAX_NO_AUTOINSTALL=1`). When `numpy` is present abax also **accelerates large
aggregate reductions** ~3–4× — automatically and with the exact same results as the
pure-Python path.

The heaviest optional piece — **`pymc`** (Bayesian / probabilistic programming,
which pulls pytensor + arviz + numba/llvmlite, ~150 MB; exposed lazily as `pymc`
in the console) — is a separate **`bayes`** extra. It's included in `all` (and
the **All** chooser preset), but you can install everything *except* it
with `pip install ".[thin,parquet,science,jupyter]"` to save ~0.15 GB. *(Not to
be confused with the stdlib-only naive-Bayes `bayes` engine above.)*

See also: [data & analysis](data-analysis.md) for the reshaping/reporting tools
and the console namespace · [formula reference](formula-reference.md) for the
function-level detail · [gui guide](gui-guide.md) for menu navigation.
