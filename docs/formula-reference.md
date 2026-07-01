# Formula reference

This is the complete reference for qcell's formula engine: the syntax of
formulas, the value and error model, and every built-in function grouped by
family. It tracks the authoritative registries `FUNCTIONS`, `LAZY_FUNCTIONS` and
`CONTEXT_FUNCTIONS` in the `qcell/core/functions/` package.

See also: [Documentation index](index.md) and
[Macros and scripting](macros-and-scripting.md).

> qcell is free software licensed under **GPL-3.0-or-later**.

## Formula basics

A cell becomes a formula when its text starts with `=`. Everything after the
`=` is parsed as an expression: literals, cell references, operators, and
function calls.

```
=1 + 2 * 3          → 7
=A1 + B1            → sum of two cells
=SUM(A1:A10)        → aggregate over a range
="Hello " & C2      → text concatenation
```

### Cell references and ranges

- **A1 references** name a single cell by column letter(s) and row number:
  `A1`, `B7`, `AA100`.
- **Ranges** name a rectangular block with a colon: `A1:C3` covers three
  columns by three rows. A range evaluates to a 2-D `RangeValue`; aggregate
  functions flatten it, while lookup functions use its shape.
- **Absolute markers** — a `$` before the column and/or row freezes that axis
  when a formula is copied, filled, or recorded relative: `$A$1` (both fixed),
  `$A1` (column fixed), `A$1` (row fixed). The `$` is tolerated everywhere a
  reference is accepted.

### Operators

| Operator | Meaning | Example | Result |
|---|---|---|---|
| `+` | add | `=2+3` | `5` |
| `-` | subtract / negate | `=5-2` | `3` |
| `*` | multiply | `=4*3` | `12` |
| `/` | divide | `=10/4` | `2.5` |
| `^` | power (right-associative) | `=2^3^2` | `512` |
| `%` | percent (postfix) | `=50%` | `0.5` |
| `&` | text concatenation | `="a"&"b"` | `ab` |
| `=` | equal | `=2=2` | `TRUE` |
| `<>` | not equal | `=2<>3` | `TRUE` |
| `<` | less than | `=1<2` | `TRUE` |
| `>` | greater than | `=2>1` | `TRUE` |
| `<=` | less or equal | `=2<=2` | `TRUE` |
| `>=` | greater or equal | `=3>=4` | `FALSE` |

`^` is **right-associative**, so `2^3^2` is `2^(3^2)` = `512`, not `64`.

### Literals and values

- **Numbers** — integer and floating point: `42`, `3.14`, `1e6`.
- **Text** — double-quoted strings: `"hello"`.
- **Boolean literals** — bare `TRUE` and `FALSE` are boolean values (not cell
  references). `TRUE()` / `FALSE()` also exist as functions.
- **Dates** are ISO-8601 strings such as `"2026-06-29"` (or
  `"2026-06-29T13:45:00"` for date-times). Date functions parse and produce
  these strings. Numerically, booleans coerce to `1`/`0` in arithmetic.

### Error values

Errors are first-class values (`CellError`). Most functions short-circuit on
the first error found in their arguments, so an error propagates outward unless
trapped by `IFERROR` / `IFNA` / `ISERROR`.

| Error | Meaning |
|---|---|
| `#DIV/0!` | Division by zero, or an aggregate with no data (e.g. `AVERAGE` of nothing) |
| `#NAME?` | Unknown function or name |
| `#VALUE!` | Wrong type / un-coercible argument |
| `#REF!` | Reference out of range (bad column/row index, off-edge shift) |
| `#NUM!` | Numeric domain error (e.g. `SQRT` of a negative) |
| `#N/A` | No match / value not available (lookups, `NA()`) |
| `#CIRC!` | Circular reference (surfaced as a value, never a crash) |

## Functions

Function names are case-insensitive. Below, every built-in is grouped by
family with its signature, a one-line description, and an example. Optional
arguments are shown in `[brackets]`. There are **over 400 built-in functions** —
**405 eager** (counting aliases and modern dotted names), **6 lazy** control-flow
functions, and **7 reference/context** functions (`ROW`, `OFFSET`, `INDIRECT`, …)
— **418 names** in all; user macros can add more (see the
[UDFs](#user-defined-functions-udfs) note).

Coverage spans the everyday Excel / Gnumeric set: math and trigonometry
(including hyperbolic and reciprocal), combinatorics, a full statistical
distribution family, financial (time-value-of-money, cashflow, depreciation),
text, date/time, engineering (base conversions, bitwise, Bessel), database
(`D*`) functions, reference functions, and a large RF / ham-radio set. Modern
dotted names (`STDEV.S`, `NORM.DIST`, `PERCENTILE.INC`, …) are accepted as
aliases of their legacy names.

### Aggregate

These flatten all range/scalar arguments and keep only numeric values (Excel
SUM/AVERAGE rules; booleans count as `1`/`0`).

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `SUM` | Sum of numbers | `SUM(value, ...)` | `=SUM(1,2,3)` | `6` |
| `SUMSQ` | Sum of squares | `SUMSQ(value, ...)` | `=SUMSQ(3,4)` | `25` |
| `AVERAGE` | Arithmetic mean (alias `AVG`) | `AVERAGE(value, ...)` | `=AVERAGE(2,4,6)` | `4` |
| `AVG` | Alias of `AVERAGE` | `AVG(value, ...)` | `=AVG(2,4,6)` | `4` |
| `COUNT` | Count of numeric values | `COUNT(value, ...)` | `=COUNT(1,"x",3)` | `2` |
| `COUNTA` | Count of non-empty values | `COUNTA(value, ...)` | `=COUNTA(1,"x","")` | `2` |
| `COUNTBLANK` | Count of empty values | `COUNTBLANK(value, ...)` | `=COUNTBLANK(1,"","")` | `2` |
| `MIN` | Minimum (0 if no numbers) | `MIN(value, ...)` | `=MIN(3,1,2)` | `1` |
| `MAX` | Maximum (0 if no numbers) | `MAX(value, ...)` | `=MAX(3,1,2)` | `3` |
| `MEDIAN` | Median value | `MEDIAN(value, ...)` | `=MEDIAN(1,2,4)` | `2` |
| `MODE` | Most frequent value | `MODE(value, ...)` | `=MODE(1,2,2,3)` | `2` |
| `PRODUCT` | Product of numbers | `PRODUCT(value, ...)` | `=PRODUCT(2,3,4)` | `24` |
| `STDEV` | Sample standard deviation | `STDEV(value, ...)` | `=STDEV(2,4,6)` | `2` |
| `STDEVP` | Population standard deviation | `STDEVP(value, ...)` | `=STDEVP(2,4,6)` | `1.633` |
| `VAR` | Sample variance | `VAR(value, ...)` | `=VAR(2,4,6)` | `4` |
| `VARP` | Population variance | `VARP(value, ...)` | `=VARP(2,4,6)` | `2.667` |
| `LARGE` | k-th largest value | `LARGE(range, k)` | `=LARGE({3,1,2},1)` | `3` |
| `SMALL` | k-th smallest value | `SMALL(range, k)` | `=SMALL({3,1,2},1)` | `1` |
| `RANK` | Rank of a value (order: 0=desc, 1=asc) | `RANK(value, range, [order])` | `=RANK(2,{1,2,3},0)` | `2` |
| `SUMPRODUCT` | Sum of element-wise products | `SUMPRODUCT(range, range, ...)` | `=SUMPRODUCT(A1:A3,B1:B3)` | dot product |

### Conditional aggregate

These take a range, a **criteria** expression, and (optionally) a second range
of values to operate on. Criteria syntax:

- A bare number or text matches by equality (text is case-insensitive).
- A comparison operator prefix: `">5"`, `"<=10"`, `"<>0"`.
- Text wildcards: `*` (any run of characters) and `?` (one character), e.g.
  `"ap*"` matches `apple`, `apricot`.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `SUMIF` | Sum where criteria matches | `SUMIF(range, criteria, [sum_range])` | `=SUMIF(A1:A9,">5")` | sum of cells > 5 |
| `COUNTIF` | Count where criteria matches | `COUNTIF(range, criteria)` | `=COUNTIF(A1:A9,"ap*")` | count of `ap…` cells |
| `AVERAGEIF` | Average where criteria matches | `AVERAGEIF(range, criteria, [avg_range])` | `=AVERAGEIF(A1:A9,">=0")` | mean of non-negatives |

The **`*IFS`** functions take one or more `(criteria_range, criteria)` pairs and
match a row only when **every** pair matches (logical AND across pairs).

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `SUMIFS` | Sum where all criteria match | `SUMIFS(sum_range, crit_range1, crit1, ...)` | `=SUMIFS(C1:C9,A1:A9,"ap*",B1:B9,">5")` | conditional sum |
| `COUNTIFS` | Count where all criteria match | `COUNTIFS(crit_range1, crit1, ...)` | `=COUNTIFS(A1:A9,">0",B1:B9,"<10")` | conditional count |
| `AVERAGEIFS` | Average where all criteria match | `AVERAGEIFS(avg_range, crit_range1, crit1, ...)` | `=AVERAGEIFS(C1:C9,A1:A9,"x")` | conditional mean |
| `MAXIFS` | Max where all criteria match | `MAXIFS(max_range, crit_range1, crit1, ...)` | `=MAXIFS(C1:C9,A1:A9,">0")` | conditional max |
| `MINIFS` | Min where all criteria match | `MINIFS(min_range, crit_range1, crit1, ...)` | `=MINIFS(C1:C9,A1:A9,">0")` | conditional min |

### Math

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `ROUND` | Round to digits (banker's) | `ROUND(num, [digits])` | `=ROUND(2.567,1)` | `2.6` |
| `ROUNDUP` | Round away from zero | `ROUNDUP(num, [digits])` | `=ROUNDUP(2.01,0)` | `3` |
| `ROUNDDOWN` | Round toward zero | `ROUNDDOWN(num, [digits])` | `=ROUNDDOWN(2.99,0)` | `2` |
| `CEILING` | Round up to multiple | `CEILING(num, [significance])` | `=CEILING(7,5)` | `10` |
| `FLOOR` | Round down to multiple | `FLOOR(num, [significance])` | `=FLOOR(7,5)` | `5` |
| `TRUNC` | Truncate to digits | `TRUNC(num, [digits])` | `=TRUNC(3.78)` | `3` |
| `INT` | Floor to integer | `INT(num)` | `=INT(-1.5)` | `-2` |
| `ABS` | Absolute value | `ABS(num)` | `=ABS(-4)` | `4` |
| `SIGN` | Sign (-1/0/1) | `SIGN(num)` | `=SIGN(-9)` | `-1` |
| `SQRT` | Square root | `SQRT(num)` | `=SQRT(9)` | `3` |
| `POWER` | Raise to power | `POWER(base, exp)` | `=POWER(2,10)` | `1024` |
| `EXP` | e raised to power | `EXP(num)` | `=EXP(1)` | `2.718` |
| `LN` | Natural log | `LN(num)` | `=LN(2.718)` | `1` |
| `LOG` | Log to base (default 10) | `LOG(num, [base])` | `=LOG(8,2)` | `3` |
| `LOG10` | Base-10 log | `LOG10(num)` | `=LOG10(1000)` | `3` |
| `MOD` | Modulo (sign follows divisor) | `MOD(num, divisor)` | `=MOD(-3,4)` | `1` |
| `GCD` | Greatest common divisor | `GCD(num, ...)` | `=GCD(12,18)` | `6` |
| `LCM` | Least common multiple | `LCM(num, ...)` | `=LCM(4,6)` | `12` |
| `FACT` | Factorial | `FACT(num)` | `=FACT(5)` | `120` |
| `PI` | Constant π | `PI()` | `=PI()` | `3.14159…` |
| `RAND` | Random in [0,1) | `RAND()` | `=RAND()` | e.g. `0.473` |
| `RANDBETWEEN` | Random integer in range | `RANDBETWEEN(lo, hi)` | `=RANDBETWEEN(1,6)` | e.g. `4` |
| `EVEN` | Round away from zero to even integer | `EVEN(num)` | `=EVEN(3)` | `4` |
| `ODD` | Round away from zero to odd integer | `ODD(num)` | `=ODD(2)` | `3` |
| `MROUND` | Round to nearest multiple | `MROUND(num, multiple)` | `=MROUND(10,3)` | `9` |
| `QUOTIENT` | Integer part of a division | `QUOTIENT(num, div)` | `=QUOTIENT(7,2)` | `3` |
| `SQRTPI` | Square root of `num * π` | `SQRTPI(num)` | `=SQRTPI(1)` | `1.7725` |
| `ISO.CEILING` | Ceiling to a multiple (ISO) | `ISO.CEILING(num, [sig])` | `=ISO.CEILING(4.3)` | `5` |
| `GAMMA` | Gamma function Γ(x) | `GAMMA(num)` | `=GAMMA(5)` | `24` |
| `GAMMALN` | Natural log of Γ(x) | `GAMMALN(num)` | `=GAMMALN(5)` | `3.178` |

**Combinatorics.**

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `COMBIN` | Combinations C(n,k) | `COMBIN(n, k)` | `=COMBIN(8,2)` | `28` |
| `COMBINA` | Combinations with repetition | `COMBINA(n, k)` | `=COMBINA(4,3)` | `20` |
| `PERMUT` | Permutations P(n,k) | `PERMUT(n, k)` | `=PERMUT(5,2)` | `20` |
| `PERMUTATIONA` | Permutations with repetition (`n^k`) | `PERMUTATIONA(n, k)` | `=PERMUTATIONA(3,2)` | `9` |
| `MULTINOMIAL` | Multinomial coefficient | `MULTINOMIAL(num, ...)` | `=MULTINOMIAL(2,3,4)` | `1260` |
| `FACTDOUBLE` | Double factorial `n!!` | `FACTDOUBLE(num)` | `=FACTDOUBLE(7)` | `105` |

**Sum families and numerals.**

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `SUMX2MY2` | Σ(x²−y²) over two ranges | `SUMX2MY2(array_x, array_y)` | `=SUMX2MY2(A1:A9,B1:B9)` | Σ(x²−y²) |
| `SUMX2PY2` | Σ(x²+y²) over two ranges | `SUMX2PY2(array_x, array_y)` | `=SUMX2PY2(A1:A9,B1:B9)` | Σ(x²+y²) |
| `SUMXMY2` | Σ(x−y)² over two ranges | `SUMXMY2(array_x, array_y)` | `=SUMXMY2(A1:A9,B1:B9)` | Σ(x−y)² |
| `SERIESSUM` | Power series Σ cᵢ·x^(n+i·m) | `SERIESSUM(x, n, m, coeffs)` | `=SERIESSUM(2,0,1,A1:A4)` | series value |
| `ROMAN` | Integer → Roman numeral | `ROMAN(num)` | `=ROMAN(1994)` | `MCMXCIV` |
| `ARABIC` | Roman numeral → integer | `ARABIC(text)` | `=ARABIC("MCMXCIV")` | `1994` |
| `BASE` | Integer → text in a radix | `BASE(num, radix, [min_len])` | `=BASE(15,2)` | `1111` |
| `DECIMAL` | Text in a radix → integer | `DECIMAL(text, radix)` | `=DECIMAL("FF",16)` | `255` |

### Trigonometry

Angles are in radians; use `DEGREES` / `RADIANS` to convert.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `SIN` | Sine | `SIN(angle)` | `=SIN(0)` | `0` |
| `COS` | Cosine | `COS(angle)` | `=COS(0)` | `1` |
| `TAN` | Tangent | `TAN(angle)` | `=TAN(0)` | `0` |
| `ASIN` | Arcsine | `ASIN(num)` | `=ASIN(1)` | `1.5708` |
| `ACOS` | Arccosine | `ACOS(num)` | `=ACOS(1)` | `0` |
| `ATAN` | Arctangent | `ATAN(num)` | `=ATAN(1)` | `0.7854` |
| `ATAN2` | Arctangent of x,y (Excel order) | `ATAN2(x, y)` | `=ATAN2(1,1)` | `0.7854` |
| `DEGREES` | Radians → degrees | `DEGREES(radians)` | `=DEGREES(PI())` | `180` |
| `RADIANS` | Degrees → radians | `RADIANS(degrees)` | `=RADIANS(180)` | `3.14159…` |

**Hyperbolic and reciprocal.** `SINH`/`COSH`/`TANH` and their inverses
`ASINH`/`ACOSH`/`ATANH`; the reciprocal functions `SEC`, `CSC`, `COT` (and
hyperbolic `SECH`, `CSCH`, `COTH`) plus `ACOT`.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `SINH` `COSH` `TANH` | Hyperbolic sine / cosine / tangent | `SINH(num)` | `=COSH(0)` | `1` |
| `ASINH` `ACOSH` `ATANH` | Inverse hyperbolic | `ACOSH(num)` | `=ASINH(0)` | `0` |
| `SEC` `CSC` `COT` | Reciprocal trig (1/cos, 1/sin, 1/tan) | `SEC(angle)` | `=SEC(0)` | `1` |
| `SECH` `CSCH` `COTH` | Reciprocal hyperbolic | `SECH(num)` | `=SECH(0)` | `1` |
| `ACOT` | Inverse cotangent | `ACOT(num)` | `=ACOT(1)` | `0.7854` |

### Statistics

Beyond the aggregate functions above, qcell ships gnumeric-style statistics
and lightweight regression / distribution helpers.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `GEOMEAN` | Geometric mean (positive values) | `GEOMEAN(value, ...)` | `=GEOMEAN(1,4,16)` | `4` |
| `HARMEAN` | Harmonic mean (non-zero values) | `HARMEAN(value, ...)` | `=HARMEAN(1,2,4)` | `1.714` |
| `PERCENTILE` | k-th percentile, k in [0,1] (inclusive) | `PERCENTILE(range, k)` | `=PERCENTILE(A1:A9,0.9)` | 90th pct |
| `QUARTILE` | Quartile, q in 0..4 | `QUARTILE(range, q)` | `=QUARTILE(A1:A9,2)` | median |
| `CORREL` | Pearson correlation | `CORREL(range1, range2)` | `=CORREL(A1:A9,B1:B9)` | `-1`…`1` |
| `COVAR` | Covariance of two ranges | `COVAR(range1, range2)` | `=COVAR(A1:A9,B1:B9)` | covariance |
| `SLOPE` | Linear-regression slope of (ys, xs) | `SLOPE(known_ys, known_xs)` | `=SLOPE(B1:B9,A1:A9)` | slope |
| `INTERCEPT` | Linear-regression intercept | `INTERCEPT(known_ys, known_xs)` | `=INTERCEPT(B1:B9,A1:A9)` | intercept |
| `RSQ` | R² coefficient of determination | `RSQ(known_ys, known_xs)` | `=RSQ(B1:B9,A1:A9)` | `0`…`1` |
| `FORECAST` | Predict y at x by linear fit | `FORECAST(x, known_ys, known_xs)` | `=FORECAST(10,B1:B9,A1:A9)` | predicted y |
| `SKEW` | Skewness | `SKEW(value, ...)` | `=SKEW(A1:A9)` | skewness |
| `KURT` | Kurtosis | `KURT(value, ...)` | `=KURT(A1:A9)` | kurtosis |
| `TTEST` | p-value of two-sample t-test | `TTEST(range1, range2)` | `=TTEST(A1:A9,B1:B9)` | p-value |
| `NORMSDIST` | Standard normal CDF | `NORMSDIST(z)` | `=NORMSDIST(0)` | `0.5` |
| `NORMSINV` | Inverse standard normal CDF | `NORMSINV(p)` | `=NORMSINV(0.975)` | `1.96` |
| `RMS` | Root mean square | `RMS(value, ...)` | `=RMS(3,4)` | `3.536` |
| `AVERAGEA` | Mean, counting text as 0 and TRUE as 1 | `AVERAGEA(value, ...)` | `=AVERAGEA(2,"x",4)` | `2` |
| `DEVSQ` | Sum of squared deviations from the mean | `DEVSQ(value, ...)` | `=DEVSQ(2,4,6)` | `8` |
| `AVEDEV` | Mean absolute deviation | `AVEDEV(value, ...)` | `=AVEDEV(2,4,6)` | `1.333` |
| `TRIMMEAN` | Mean after trimming a fraction of extremes | `TRIMMEAN(range, fraction)` | `=TRIMMEAN(A1:A9,0.2)` | trimmed mean |
| `STANDARDIZE` | Z-score `(x−mean)/sd` | `STANDARDIZE(x, mean, sd)` | `=STANDARDIZE(42,40,1.5)` | `1.333` |
| `PERCENTRANK` | Rank of a value as a percent | `PERCENTRANK(range, x, [sig])` | `=PERCENTRANK(A1:A9,7)` | `0`…`1` |
| `STEYX` | Standard error of the regression | `STEYX(known_ys, known_xs)` | `=STEYX(B1:B9,A1:A9)` | std error |
| `PEARSON` | Pearson correlation (= `CORREL`) | `PEARSON(array1, array2)` | `=PEARSON(A1:A9,B1:B9)` | `-1`…`1` |
| `FISHER` | Fisher transform `atanh(x)` | `FISHER(x)` | `=FISHER(0.75)` | `0.9730` |
| `FISHERINV` | Inverse Fisher `tanh(y)` | `FISHERINV(y)` | `=FISHERINV(0.973)` | `0.75` |
| `RANK.EQ` | Rank (ties share the top rank) | `RANK.EQ(value, range, [order])` | `=RANK.EQ(2,A1:A9)` | rank |
| `RANK.AVG` | Rank (ties share the average rank) | `RANK.AVG(value, range, [order])` | `=RANK.AVG(2,A1:A9)` | rank |

### Statistical distributions

Distribution and confidence functions (Excel-named; familiar to spreadsheet and
R/RStudio users). `TDIST`/`FDIST`/`CHIDIST` return right-tail probabilities;
`TINV` is two-tailed (Excel convention).

| Function | Description | Signature | Example | Result |
|----------|-------------|-----------|---------|--------|
| `NORMDIST` | Normal CDF (or PDF) | `NORMDIST(x, mean, sd, cumulative)` | `=NORMDIST(0,0,1,TRUE)` | `0.5` |
| `NORMINV` | Inverse normal CDF | `NORMINV(p, mean, sd)` | `=NORMINV(0.975,0,1)` | `1.96` |
| `TDIST` | Student-t tail prob. (tails=1 or 2) | `TDIST(x, df, tails)` | `=TDIST(2.2281,10,2)` | `0.05` |
| `TINV` | Two-tailed inverse t | `TINV(p, df)` | `=TINV(0.05,10)` | `2.228` |
| `FDIST` | F right-tail probability | `FDIST(x, df1, df2)` | `=FDIST(3.3258,5,10)` | `0.05` |
| `FINV` | Inverse F right-tail | `FINV(p, df1, df2)` | `=FINV(0.05,5,10)` | `3.326` |
| `CHIDIST` | Chi-square right-tail prob. | `CHIDIST(x, df)` | `=CHIDIST(3.8415,1)` | `0.05` |
| `CHIINV` | Inverse chi-square right-tail | `CHIINV(p, df)` | `=CHIINV(0.05,1)` | `3.841` |
| `CONFIDENCE` | Normal confidence-interval half-width | `CONFIDENCE(alpha, sd, n)` | `=CONFIDENCE(0.05,1,100)` | `0.196` |

The full distribution family — discrete and continuous, each with a `cumulative`
flag (TRUE → CDF, FALSE → PMF/PDF) and, where applicable, an inverse. Both the
legacy names and the modern dotted names (e.g. `BINOM.DIST`) are registered.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `BINOMDIST` · `BINOM.DIST` | Binomial | `BINOMDIST(x, n, p, cumulative)` | `=BINOMDIST(6,10,0.5,FALSE)` | `0.2051` |
| `CRITBINOM` · `BINOM.INV` | Smallest x with CDF ≥ α | `BINOM.INV(n, p, alpha)` | `=BINOM.INV(10,0.5,0.9)` | `7` |
| `NEGBINOMDIST` · `NEGBINOM.DIST` | Negative binomial | `NEGBINOMDIST(f, s, p)` | `=NEGBINOMDIST(2,3,0.5)` | prob. |
| `POISSON` · `POISSON.DIST` | Poisson | `POISSON(x, mean, cumulative)` | `=POISSON(2,5,FALSE)` | `0.0842` |
| `HYPGEOMDIST` · `HYPGEOM.DIST` | Hypergeometric | `HYPGEOMDIST(x, n, pop_s, pop_n)` | `=HYPGEOMDIST(1,4,8,20)` | `0.3633` |
| `EXPONDIST` · `EXPON.DIST` | Exponential | `EXPONDIST(x, lambda, cumulative)` | `=EXPONDIST(0.2,10,TRUE)` | `0.8647` |
| `GAMMADIST` · `GAMMA.DIST` | Gamma (and `GAMMAINV`/`GAMMA.INV`) | `GAMMADIST(x, a, b, cumulative)` | `=GAMMADIST(10,9,2,TRUE)` | `0.0681` |
| `BETADIST` · `BETA.DIST` | Beta (and `BETAINV`/`BETA.INV`) | `BETADIST(x, a, b, [cum], [A], [B])` | `=BETADIST(0.5,8,10,TRUE)` | `0.6855` |
| `WEIBULL` · `WEIBULL.DIST` | Weibull | `WEIBULL(x, a, b, cumulative)` | `=WEIBULL(105,20,100,TRUE)` | `0.9296` |
| `LOGNORMDIST` · `LOGNORM.DIST` | Log-normal (and `LOGINV`/`LOGNORM.INV`) | `LOGNORMDIST(x, mean, sd)` | `=LOGNORMDIST(4,3.5,1.2)` | prob. |
| `PHI` | Standard normal PDF | `PHI(x)` | `=PHI(0)` | `0.3989` |
| `GAUSS` | `Φ(z) − 0.5` | `GAUSS(z)` | `=GAUSS(2)` | `0.4772` |

### Lookup and reference

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `VLOOKUP` | Vertical lookup in a table | `VLOOKUP(value, table, col_index, [approx])` | `=VLOOKUP("kiwi",A1:C9,3,FALSE)` | column-3 cell |
| `HLOOKUP` | Horizontal lookup in a table | `HLOOKUP(value, table, row_index, [approx])` | `=HLOOKUP("Q2",A1:E3,2,FALSE)` | row-2 cell |
| `MATCH` | Position of value (type 1/0/-1) | `MATCH(value, range, [match_type])` | `=MATCH(7,A1:A9,0)` | index of 7 |
| `INDEX` | Value at row/col of a range | `INDEX(range, row, [col])` | `=INDEX(A1:C9,2,3)` | cell at (2,3) |
| `XLOOKUP` | Modern lookup (exact by default) | `XLOOKUP(value, lookup_range, return_range, [if_missing], [match])` | `=XLOOKUP("kiwi",A1:A9,C1:C9)` | matched value |

**Reference / context functions.** These see the *calling cell* and the raw
**reference** rather than its value. `OFFSET` and `INDIRECT` return a live range
that composes inside aggregates (`=SUM(OFFSET(A1,0,0,3,1))`).

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `ROW` | Row number of a reference (or this cell) | `ROW([reference])` | `=ROW(C4)` | `4` |
| `COLUMN` | Column number of a reference (or this cell) | `COLUMN([reference])` | `=COLUMN(C4)` | `3` |
| `ROWS` | Number of rows in a range | `ROWS(range)` | `=ROWS(A1:A10)` | `10` |
| `COLUMNS` | Number of columns in a range | `COLUMNS(range)` | `=COLUMNS(A1:C1)` | `3` |
| `OFFSET` | Reference shifted from a base cell | `OFFSET(reference, rows, cols, [height], [width])` | `=OFFSET(A1,1,1)` | cell `B2` |
| `INDIRECT` | Reference from a text string | `INDIRECT(ref_text, [a1])` | `=INDIRECT("A"&2)` | value of `A2` |
| `ADDRESS` | Build an address string | `ADDRESS(row, col, [abs], [a1], [sheet])` | `=ADDRESS(2,3)` | `$C$2` |

For `VLOOKUP`/`HLOOKUP` the 4th argument defaults to **TRUE** (approximate,
assumes ascending order); pass `FALSE` for an exact match. `MATCH` defaults to
type `1` (largest value ≤ target, ascending); `0` is exact; `-1` is smallest
value ≥ target.

### Logical and control flow

`AND`, `OR`, `XOR`, `NOT`, `TRUE`, `FALSE` are eager. `IF`, `IFERROR`, `IFNA`,
`IFS`, `SWITCH`, `CHOOSE` are **lazy** — they receive unevaluated branches, so
untaken branches never run (no spurious errors or side effects).

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `IF` | Conditional value (lazy) | `IF(cond, [then], [else])` | `=IF(A1>0,"pos","neg")` | one branch |
| `IFERROR` | Fallback on any error (lazy) | `IFERROR(value, [fallback])` | `=IFERROR(1/0,"oops")` | `oops` |
| `IFNA` | Fallback on `#N/A` only (lazy) | `IFNA(value, [fallback])` | `=IFNA(NA(),0)` | `0` |
| `IFS` | First matching condition (lazy) | `IFS(cond1, val1, ...)` | `=IFS(A1>9,"hi",TRUE,"lo")` | matched value |
| `SWITCH` | Match target to cases (lazy) | `SWITCH(target, case, val, ..., [default])` | `=SWITCH(2,1,"a",2,"b")` | `b` |
| `CHOOSE` | Pick the n-th argument (lazy) | `CHOOSE(index, val1, val2, ...)` | `=CHOOSE(2,"a","b","c")` | `b` |
| `AND` | True if all truthy | `AND(value, ...)` | `=AND(TRUE,1>0)` | `TRUE` |
| `OR` | True if any truthy | `OR(value, ...)` | `=OR(FALSE,1>0)` | `TRUE` |
| `XOR` | True if odd number truthy | `XOR(TRUE, FALSE, TRUE)` | `=XOR(TRUE,TRUE)` | `FALSE` |
| `NOT` | Logical negation | `NOT(value)` | `=NOT(FALSE)` | `TRUE` |
| `TRUE` | Boolean true | `TRUE()` | `=TRUE()` | `TRUE` |
| `FALSE` | Boolean false | `FALSE()` | `=FALSE()` | `FALSE` |

### Text

`CONCATENATE` is an alias of `CONCAT`. String positions are 1-based.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `CONCAT` | Join values into text | `CONCAT(value, ...)` | `=CONCAT("a","b","c")` | `abc` |
| `CONCATENATE` | Alias of `CONCAT` | `CONCATENATE(value, ...)` | `=CONCATENATE("a",1)` | `a1` |
| `LEN` | Length of text | `LEN(text)` | `=LEN("hello")` | `5` |
| `LEFT` | Leftmost n characters | `LEFT(text, [n])` | `=LEFT("hello",2)` | `he` |
| `RIGHT` | Rightmost n characters | `RIGHT(text, [n])` | `=RIGHT("hello",2)` | `lo` |
| `MID` | Substring from start, length | `MID(text, start, length)` | `=MID("hello",2,3)` | `ell` |
| `UPPER` | Uppercase | `UPPER(text)` | `=UPPER("hi")` | `HI` |
| `LOWER` | Lowercase | `LOWER(text)` | `=LOWER("HI")` | `hi` |
| `PROPER` | Title case | `PROPER(text)` | `=PROPER("foo bar")` | `Foo Bar` |
| `TRIM` | Collapse whitespace | `TRIM(text)` | `=TRIM("  a   b ")` | `a b` |
| `FIND` | Position of substring (case-sensitive) | `FIND(needle, haystack, [start])` | `=FIND("l","hello")` | `3` |
| `SEARCH` | Position of substring (case-insensitive) | `SEARCH(needle, haystack, [start])` | `=SEARCH("L","hello")` | `3` |
| `REPLACE` | Replace by position/length | `REPLACE(text, start, length, new)` | `=REPLACE("hello",1,1,"j")` | `jello` |
| `SUBSTITUTE` | Replace text (optionally nth) | `SUBSTITUTE(text, old, new, [instance])` | `=SUBSTITUTE("a-a-a","a","b",2)` | `a-b-a` |
| `REPT` | Repeat text n times | `REPT(text, n)` | `=REPT("ab",3)` | `ababab` |
| `EXACT` | Case-sensitive equality | `EXACT(text1, text2)` | `=EXACT("a","A")` | `FALSE` |
| `CHAR` | Character from code point | `CHAR(code)` | `=CHAR(65)` | `A` |
| `CODE` | Code point of first char | `CODE(text)` | `=CODE("A")` | `65` |
| `TEXT` | Format a number as text | `TEXT(value, format)` | `=TEXT(0.5,"0.0%")` | `50.0%` |
| `VALUE` | Parse text to number | `VALUE(text)` | `=VALUE("42")` | `42` |
| `T` | Text passthrough (else empty) | `T(value)` | `=T("hi")` | `hi` |
| `TEXTJOIN` | Join with a delimiter (optionally skip blanks) | `TEXTJOIN(delim, ignore_empty, text, ...)` | `=TEXTJOIN("-",TRUE,"a","","b")` | `a-b` |
| `TEXTBEFORE` | Text before the nth delimiter | `TEXTBEFORE(text, delim, [instance])` | `=TEXTBEFORE("a.b.c",".",2)` | `a.b` |
| `TEXTAFTER` | Text after the nth delimiter | `TEXTAFTER(text, delim, [instance])` | `=TEXTAFTER("a.b.c",".")` | `b.c` |
| `CLEAN` | Strip non-printable characters | `CLEAN(text)` | `=CLEAN("a"&CHAR(7)&"b")` | `ab` |
| `UNICHAR` | Character from a Unicode code point | `UNICHAR(number)` | `=UNICHAR(65)` | `A` |
| `UNICODE` | Code point of the first character | `UNICODE(text)` | `=UNICODE("A")` | `65` |
| `DOLLAR` | Format as currency text | `DOLLAR(num, [decimals])` | `=DOLLAR(1234.567)` | `$1,234.57` |
| `FIXED` | Fixed-decimal text | `FIXED(num, [decimals], [no_commas])` | `=FIXED(1234.567,1)` | `1,234.6` |
| `NUMBERVALUE` | Parse localized number text | `NUMBERVALUE(text, [dec_sep], [grp_sep])` | `=NUMBERVALUE("1,234.5")` | `1234.5` |

### Date and time

Dates are ISO strings. `NOW` returns a date-time; `TODAY` returns a date.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `NOW` | Current date and time | `NOW()` | `=NOW()` | `2026-06-29T13:45:00` |
| `TODAY` | Current date | `TODAY()` | `=TODAY()` | `2026-06-29` |
| `DATE` | Build a date | `DATE(year, month, day)` | `=DATE(2026,6,29)` | `2026-06-29` |
| `YEAR` | Year part | `YEAR(date)` | `=YEAR("2026-06-29")` | `2026` |
| `MONTH` | Month part | `MONTH(date)` | `=MONTH("2026-06-29")` | `6` |
| `DAY` | Day part | `DAY(date)` | `=DAY("2026-06-29")` | `29` |
| `HOUR` | Hour part | `HOUR(datetime)` | `=HOUR("2026-06-29T13:45")` | `13` |
| `MINUTE` | Minute part | `MINUTE(datetime)` | `=MINUTE("2026-06-29T13:45")` | `45` |
| `SECOND` | Second part | `SECOND(datetime)` | `=SECOND("2026-06-29T13:45:30")` | `30` |
| `WEEKDAY` | Day of week (Sun=1…Sat=7) | `WEEKDAY(date)` | `=WEEKDAY("2026-06-29")` | `2` |
| `DATEDIF` | Difference in D / M / Y | `DATEDIF(start, end, unit)` | `=DATEDIF("2026-01-01","2026-06-29","M")` | `5` |
| `EDATE` | Shift date by months | `EDATE(start, months)` | `=EDATE("2026-01-31",1)` | `2026-02-28` |
| `DAYS` | Days between two dates | `DAYS(end, start)` | `=DAYS("2026-06-29","2026-06-01")` | `28` |
| `TIME` | Time of day as a day fraction | `TIME(hour, minute, second)` | `=TIME(12,0,0)` | `0.5` |
| `TIMEVALUE` | Parse a time string to a fraction | `TIMEVALUE(text)` | `=TIMEVALUE("18:00")` | `0.75` |
| `DATEVALUE` | Parse a date string to an ISO date | `DATEVALUE(text)` | `=DATEVALUE("2026-06-30")` | `2026-06-30` |
| `EOMONTH` | Last day of the month, n months out | `EOMONTH(start, months)` | `=EOMONTH("2026-01-15",1)` | `2026-02-28` |
| `WORKDAY` | Date n working days out (skip weekends/holidays) | `WORKDAY(start, days, [holidays])` | `=WORKDAY("2026-06-30",3)` | `2026-07-03` |
| `NETWORKDAYS` | Count working days between two dates | `NETWORKDAYS(start, end, [holidays])` | `=NETWORKDAYS("2026-06-01","2026-06-05")` | `5` |
| `WEEKNUM` | Week of the year | `WEEKNUM(date, [type])` | `=WEEKNUM("2026-01-01")` | `1` |
| `ISOWEEKNUM` | ISO-8601 week of the year | `ISOWEEKNUM(date)` | `=ISOWEEKNUM("2026-01-01")` | `1` |
| `YEARFRAC` | Year fraction between two dates (basis 0–4) | `YEARFRAC(start, end, [basis])` | `=YEARFRAC("2026-01-01","2026-07-01")` | `0.5` |
| `DAYS360` | Days on a 360-day basis | `DAYS360(start, end, [method])` | `=DAYS360("2026-01-01","2026-02-01")` | `30` |

### Financial

Time-value-of-money, cashflow analysis, and depreciation. Cash **out** is
negative and cash **in** positive (Excel sign convention); the `type` argument is
`0` for end-of-period (default) or `1` for beginning-of-period payments.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `FV` | Future value of an annuity | `FV(rate, nper, pmt, [pv], [type])` | `=FV(0.06/12,120,-100)` | `16387.93` |
| `PV` | Present value | `PV(rate, nper, pmt, [fv], [type])` | `=PV(0.08,20,500)` | `-4909.07` |
| `PMT` | Payment per period | `PMT(rate, nper, pv, [fv], [type])` | `=PMT(0.08/12,120,10000)` | `-121.33` |
| `IPMT` | Interest part of a payment | `IPMT(rate, per, nper, pv, [fv], [type])` | `=IPMT(0.08/12,1,120,10000)` | interest |
| `PPMT` | Principal part of a payment | `PPMT(rate, per, nper, pv, [fv], [type])` | `=PPMT(0.08/12,1,120,10000)` | principal |
| `NPER` | Number of periods | `NPER(rate, pmt, pv, [fv], [type])` | `=NPER(0.01,-100,-1000,10000)` | periods |
| `RATE` | Rate per period (iterative) | `RATE(nper, pmt, pv, [fv], [type], [guess])` | `=RATE(60,-200,10000)` | rate |
| `NPV` | Net present value of a cashflow | `NPV(rate, value, ...)` | `=NPV(0.1,-10000,3000,4200,6800)` | `1188.44` |
| `IRR` | Internal rate of return | `IRR(values, [guess])` | `=IRR(A1:A6)` | rate |
| `XNPV` | NPV with explicit dates | `XNPV(rate, values, dates)` | `=XNPV(0.09,A1:A5,B1:B5)` | NPV |
| `XIRR` | IRR with explicit dates | `XIRR(values, dates, [guess])` | `=XIRR(A1:A5,B1:B5)` | rate |
| `MIRR` | Modified IRR | `MIRR(values, finance_rate, reinvest_rate)` | `=MIRR(A1:A6,0.1,0.12)` | rate |
| `CUMIPMT` | Cumulative interest over a span | `CUMIPMT(rate, nper, pv, start, end, type)` | `=CUMIPMT(0.09/12,360,125000,13,24,0)` | interest |
| `CUMPRINC` | Cumulative principal over a span | `CUMPRINC(rate, nper, pv, start, end, type)` | `=CUMPRINC(0.09/12,360,125000,13,24,0)` | principal |
| `SLN` | Straight-line depreciation | `SLN(cost, salvage, life)` | `=SLN(30000,7500,10)` | `2250` |
| `SYD` | Sum-of-years'-digits depreciation | `SYD(cost, salvage, life, per)` | `=SYD(30000,7500,10,1)` | `4090.91` |
| `DB` | Fixed-declining-balance depreciation | `DB(cost, salvage, life, period, [month])` | `=DB(1e6,1e5,6,1)` | depreciation |
| `DDB` | Double-declining-balance depreciation | `DDB(cost, salvage, life, period, [factor])` | `=DDB(2400,300,10,1)` | `480` |
| `VDB` | Variable-declining-balance depreciation | `VDB(cost, salvage, life, start, end, [factor], [no_switch])` | `=VDB(2400,300,10,0,1)` | depreciation |
| `EFFECT` | Effective annual rate | `EFFECT(nominal, npery)` | `=EFFECT(0.0525,4)` | `0.05354` |
| `NOMINAL` | Nominal annual rate | `NOMINAL(effect, npery)` | `=NOMINAL(0.05354,4)` | `0.0525` |
| `DOLLARDE` | Fractional dollar → decimal | `DOLLARDE(fractional, fraction)` | `=DOLLARDE(1.02,16)` | `1.125` |
| `DOLLARFR` | Decimal dollar → fractional | `DOLLARFR(decimal, fraction)` | `=DOLLARFR(1.125,16)` | `1.02` |
| `PDURATION` | Periods to reach a future value | `PDURATION(rate, pv, fv)` | `=PDURATION(0.025,1000,2000)` | periods |
| `RRI` | Equivalent interest rate for growth | `RRI(nper, pv, fv)` | `=RRI(96,10000,11000)` | rate |

### Information

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `NA` | The `#N/A` error value | `NA()` | `=NA()` | `#N/A` |
| `ISBLANK` | True if empty | `ISBLANK(value)` | `=ISBLANK(A1)` | `TRUE`/`FALSE` |
| `ISNUMBER` | True if numeric (not boolean) | `ISNUMBER(value)` | `=ISNUMBER(42)` | `TRUE` |
| `ISTEXT` | True if text | `ISTEXT(value)` | `=ISTEXT("x")` | `TRUE` |
| `ISLOGICAL` | True if boolean | `ISLOGICAL(value)` | `=ISLOGICAL(TRUE)` | `TRUE` |
| `ISERROR` | True if an error value | `ISERROR(value)` | `=ISERROR(1/0)` | `TRUE` |
| `ISERR` | True if an error other than `#N/A` | `ISERR(value)` | `=ISERR(1/0)` | `TRUE` |
| `ISNA` | True if the `#N/A` error | `ISNA(value)` | `=ISNA(NA())` | `TRUE` |
| `ISNONTEXT` | True if not text | `ISNONTEXT(value)` | `=ISNONTEXT(42)` | `TRUE` |
| `ISEVEN` | True if the (truncated) number is even | `ISEVEN(number)` | `=ISEVEN(4)` | `TRUE` |
| `ISODD` | True if the (truncated) number is odd | `ISODD(number)` | `=ISODD(3)` | `TRUE` |
| `N` | Coerce to a number (TRUE→1, text→0) | `N(value)` | `=N(TRUE)` | `1` |
| `TYPE` | Type code (1 num, 2 text, 4 logical, 16 error) | `TYPE(value)` | `=TYPE("x")` | `2` |
| `ERROR.TYPE` | Numeric code for an error value | `ERROR.TYPE(value)` | `=ERROR.TYPE(1/0)` | `2` |

### Engineering and units

These return scalars; complex numbers are encoded as text such as `"3+4i"`
(Excel `IM*` convention).

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `COMPLEX` | Build a complex number from parts | `COMPLEX(real, imag)` | `=COMPLEX(3,4)` | `3+4i` |
| `IMSUM` | Sum of complex numbers | `IMSUM(c, ...)` | `=IMSUM("3+4i","1+2i")` | `4+6i` |
| `IMSUB` | Difference of two complex numbers | `IMSUB(c1, c2)` | `=IMSUB("3+4i","1+2i")` | `2+2i` |
| `IMPRODUCT` | Product of complex numbers | `IMPRODUCT(c, ...)` | `=IMPRODUCT("1+1i","1+1i")` | `2i` |
| `IMDIV` | Quotient of two complex numbers | `IMDIV(c1, c2)` | `=IMDIV("4+2i","1+1i")` | `3-1i` |
| `IMABS` | Modulus (magnitude) | `IMABS(c)` | `=IMABS("3+4i")` | `5` |
| `IMREAL` | Real part | `IMREAL(c)` | `=IMREAL("3+4i")` | `3` |
| `IMAGINARY` | Imaginary part | `IMAGINARY(c)` | `=IMAGINARY("3+4i")` | `4` |
| `IMCONJUGATE` | Complex conjugate | `IMCONJUGATE(c)` | `=IMCONJUGATE("3+4i")` | `3-4i` |
| `IMARGUMENT` | Argument (angle, radians) | `IMARGUMENT(c)` | `=IMARGUMENT("0+1i")` | `1.5708` |
| `IMSQRT` | Square root | `IMSQRT(c)` | `=IMSQRT("-1")` | `i` |
| `IMEXP` | Exponential | `IMEXP(c)` | `=IMEXP("0")` | `1` |
| `IMLN` | Natural log | `IMLN(c)` | `=IMLN("1")` | `0` |
| `IMSIN` | Sine | `IMSIN(c)` | `=IMSIN("0")` | `0` |
| `IMCOS` | Cosine | `IMCOS(c)` | `=IMCOS("0")` | `1` |
| `IMPOWER` | Raise to a real power | `IMPOWER(c, power)` | `=IMPOWER("1+1i",2)` | `2i` |
| `MDETERM` | Determinant of a square range | `MDETERM(range)` | `=MDETERM(A1:B2)` | determinant |
| `CONVERT` | Convert between units | `CONVERT(num, from_unit, to_unit)` | `=CONVERT(1,"mi","km")` | `1.609` |
| `INTERP` | Linear interpolation at x | `INTERP(x, known_xs, known_ys)` | `=INTERP(2.5,A1:A9,B1:B9)` | interpolated y |

**Number-base conversions.** Negative inputs use two's-complement (Excel rules);
an optional `places` argument zero-pads the result. The 12 functions convert
between binary, octal, decimal and hexadecimal.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `DEC2BIN` `DEC2OCT` `DEC2HEX` | Decimal → binary / octal / hex | `DEC2HEX(num, [places])` | `=DEC2BIN(9)` | `1001` |
| `BIN2DEC` `BIN2OCT` `BIN2HEX` | Binary → decimal / octal / hex | `BIN2DEC(text)` | `=BIN2DEC("1111111111")` | `-1` |
| `OCT2DEC` `OCT2BIN` `OCT2HEX` | Octal → decimal / binary / hex | `OCT2DEC(text)` | `=OCT2DEC("10")` | `8` |
| `HEX2DEC` `HEX2BIN` `HEX2OCT` | Hex → decimal / binary / octal | `HEX2DEC(text)` | `=HEX2DEC("FF")` | `255` |

**Bitwise and special functions.**

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `BITAND` `BITOR` `BITXOR` | Bitwise AND / OR / XOR | `BITAND(a, b)` | `=BITXOR(6,10)` | `12` |
| `BITLSHIFT` `BITRSHIFT` | Bit shift left / right | `BITLSHIFT(num, shift)` | `=BITLSHIFT(4,2)` | `16` |
| `DELTA` | Kronecker delta (1 if equal) | `DELTA(num1, [num2])` | `=DELTA(5,5)` | `1` |
| `GESTEP` | Step (1 if num ≥ step) | `GESTEP(num, [step])` | `=GESTEP(5,4)` | `1` |
| `ERF` | Error function (1- or 2-limit) | `ERF(lower, [upper])` | `=ERF(1)` | `0.8427` |
| `ERFC` | Complementary error function | `ERFC(x)` | `=ERFC(1)` | `0.1573` |
| `BESSELJ` `BESSELY` | Bessel functions of the 1st / 2nd kind | `BESSELJ(x, n)` | `=BESSELJ(1,0)` | `0.7652` |
| `BESSELI` `BESSELK` | Modified Bessel functions | `BESSELI(x, n)` | `=BESSELI(1,0)` | `1.2661` |

`ERF.PRECISE` and `ERFC.PRECISE` are single-argument aliases.

### Database

The classic database functions operate on a table whose first row is column
headers. `field` is a column header (text) or a 1-based index; `criteria` is a
small range whose first row names columns and whose following rows hold criteria
(AND across a row, OR across rows).

| Function | Description | Signature |
|---|---|---|
| `DSUM` | Sum of a field over matching records | `DSUM(database, field, criteria)` |
| `DCOUNT` | Count of numeric field values | `DCOUNT(database, field, criteria)` |
| `DCOUNTA` | Count of non-blank field values | `DCOUNTA(database, field, criteria)` |
| `DAVERAGE` | Average of a field | `DAVERAGE(database, field, criteria)` |
| `DMAX` / `DMIN` | Max / min of a field | `DMAX(database, field, criteria)` |
| `DGET` | The single matching field value | `DGET(database, field, criteria)` |
| `DPRODUCT` | Product of a field | `DPRODUCT(database, field, criteria)` |
| `DSTDEV` / `DSTDEVP` | Sample / population standard deviation | `DSTDEV(database, field, criteria)` |
| `DVAR` / `DVARP` | Sample / population variance | `DVAR(database, field, criteria)` |

Example: with a `Tree`/`Height` table in `A1:B4` and a criteria range `D1:D2`
of `Tree` / `Apple`, `=DSUM(A1:B4,"Height",D1:D2)` sums the heights of apples.

## RF / ham radio

SI base units (frequency in Hz, length in m, power in W; levels in dB). Full guide,
units note, and worked examples in [RF toolkit](rf-toolkit.md).

| Function | Description | Syntax | Example |
| --- | --- | --- | --- |
| `DBM2W` / `W2DBM` | dBm ↔ watts | `W2DBM(watts)` | `=DBM2W(30)` → `1` |
| `DBW2W` / `W2DBW` | dBW ↔ watts | `DBW2W(dbw)` | |
| `DB2RATIO` / `RATIO2DB` | dB ↔ power ratio | `RATIO2DB(r)` | `=RATIO2DB(2)` → `3.01` |
| `DBADD` | combine two dB(m) powers | `DBADD(d1, d2)` | `=DBADD(0,0)` → `3.01` |
| `DBUV2DBM` | dBµV → dBm | `DBUV2DBM(dbuv, [z=50])` | |
| `SUNIT2DBM` | S-meter → dBm | `SUNIT2DBM(s)` | `=SUNIT2DBM(9)` → `-73` |
| `NOISEFLOOR` | thermal noise kTB (dBm) | `NOISEFLOOR(bw_hz, [t=290])` | `=NOISEFLOOR(1)` → `-174` |
| `NF2NT` / `NT2NF` | noise figure ↔ temp | `NF2NT(nf_db, [t0])` | |
| `WAVELENGTH` / `WL2FREQ` | λ ↔ f | `WAVELENGTH(freq_hz, [vf=1])` | `=WAVELENGTH(3e8)` → `1` |
| `DIPOLELEN` / `MONOPOLELEN` | physical antenna length (m) | `DIPOLELEN(freq_hz, [k=0.95])` | |
| `XL` / `XC` | reactance (Ω) | `XL(freq_hz, L)` · `XC(freq_hz, C)` | |
| `RESFREQ` | LC resonant freq (Hz) | `RESFREQ(L, C)` | |
| `VSWR` / `VSWRG` | VSWR from Z or \|Γ\| | `VSWR(z_load, [z0=50])` | `=VSWR(75,50)` → `1.5` |
| `REFLCOEF` | reflection coefficient Γ | `REFLCOEF(z_load, [z0=50])` | |
| `RETURNLOSS` / `MISMATCHLOSS` | dB from \|Γ\| | `RETURNLOSS(gamma)` | |
| `VSWR2GAMMA` | \|Γ\| from VSWR | `VSWR2GAMMA(vswr)` | |
| `Z0COAX` / `VELFACTOR` | coax Z0 / velocity factor | `Z0COAX(D, d, [eps_r=1])` | |
| `FSPL` | free-space path loss (dB) | `FSPL(dist_m, freq_hz)` | `=FSPL(1000,2.4e9)` → `100.05` |
| `FRIIS` | received power (dBm) | `FRIIS(ptx, gtx, grx, dist_m, freq_hz)` | |
| `EIRP` | EIRP (dBm) | `EIRP(ptx_dbm, gain_dbi, [loss=0])` | |
| `FRESNEL` | Fresnel-zone radius (m) | `FRESNEL(d1, d2, freq_hz, [zone=1])` | |
| `RADIOHORIZON` | LOS distance (km) | `RADIOHORIZON(h1_m, [h2_m=0])` | |
| `SKINDEPTH` | skin depth (m) | `SKINDEPTH(freq_hz, [sigma], [mu_r])` | |
| `DBI2DBD` / `DBD2DBI` | antenna gain reference | `DBI2DBD(dbi)` | `=DBI2DBD(2.15)` → `0` |
| `GRIDSQUARE` | Maidenhead locator | `GRIDSQUARE(lat, lon, [precision=6])` | `=GRIDSQUARE(48.15,11.6)` → `JN58td` |
| `GRIDLAT` / `GRIDLON` | locator → centre lat/lon | `GRIDLAT(grid)` | |
| `GRIDDIST` / `GRIDBEARING` | distance (km) / bearing (°) | `GRIDDIST(a, b)` | `=GRIDDIST("JN58","IO91")` |
| `HAMBAND` | US amateur band name | `HAMBAND(freq_hz)` | `=HAMBAND(14.1e6)` → `20m` |
| `CTCSSTONE` | standard CTCSS tone (1–50) | `CTCSSTONE(n)` | `=CTCSSTONE(13)` → `100` |
| `NEARESTCTCSS` | nearest standard CTCSS tone | `NEARESTCTCSS(freq_hz)` | `=NEARESTCTCSS(100.1)` → `100` |
| `DIPOLER` / `DIPOLEX` | dipole input R / X (Ω) | `DIPOLER(length_wl, [radius_wl])` | `=DIPOLER(0.5)` → `~73` |
| `RADRESIST` | radiation resistance (Ω) | `RADRESIST(length_wl)` | `=RADRESIST(0.5)` → `73.1` |
| `RESONANTLEN` | resonant dipole length (λ) | `RESONANTLEN([radius_wl])` | `≈0.48` |

**Radio math** — resonance, Q, inductor design, matching and propagation.

| Function | Description | Syntax | Example |
| --- | --- | --- | --- |
| `CFROMXC` / `LFROMXL` | C from Xc / L from Xl | `CFROMXC(xc, freq_hz)` | |
| `RESONANTC` / `RESONANTL` | C or L to resonate at a frequency | `RESONANTL(freq_hz, C)` | |
| `QBW` / `BWQ` | loaded Q ↔ bandwidth | `QBW(center_hz, bw_hz)` | `=QBW(14e6,14e3)` → `1000` |
| `AIRCOILL` / `AIRCOILN` | air-core inductor (Wheeler) | `AIRCOILL(diam_m, len_m, turns)` | |
| `TOROIDL` / `TOROIDN` | toroid from an AL value | `TOROIDL(al_nh, turns)` | |
| `QWMATCH` | quarter-wave transformer Z₀ | `QWMATCH(z1, z2)` | `=QWMATCH(50,200)` → `100` |
| `SWRPWR` | SWR from forward/reflected power | `SWRPWR(fwd_w, refl_w)` | |
| `LOOPLEN` | full-wave loop length (m) | `LOOPLEN(freq_hz)` | |
| `DISHGAIN` / `DISHBW` | parabolic-dish gain / beamwidth | `DISHGAIN(diam_m, freq_hz, [eff])` | |
| `DOPPLER` | Doppler shift (Hz) | `DOPPLER(freq_hz, velocity_mps)` | |

For antenna modeling beyond these closed-form functions — the thin-wire Method of
Moments solver and NEC `.nec` I/O — see [RF toolkit](rf-toolkit.md).

## User-defined functions (UDFs)

User macros can register new functions that are callable in formulas exactly
like built-ins: `=NAME(...)`. A `@register_function("NAME")` macro installs a
Python callable into the same `FUNCTIONS` registry, using the same evaluated
arg-list convention. For example, the bundled `macros/sample.py` defines
`TAXED` and `REVERSE`, so `=TAXED(100)` and `=REVERSE("abc")` work in any cell.

See [Macros and scripting](macros-and-scripting.md) for how to write, discover,
and load macros.
