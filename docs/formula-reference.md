# Formula reference

This is the complete reference for abax's formula engine: the syntax of
formulas, the value and error model, and every built-in function grouped by
family. It tracks the authoritative registries `FUNCTIONS`, `LAZY_FUNCTIONS` and
`CONTEXT_FUNCTIONS` in the `abax/core/functions/` package.

See also: [Documentation index](index.md) and
[Macros and scripting](macros-and-scripting.md).

> abax is free software licensed under **GPL-3.0-or-later**.

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
| `#` | spill range (postfix on an anchor) | `=SUM(A1#)` | sum of A1's spill |
| `@` | implicit intersection (prefix) | `=@A1:A10` | the row-aligned cell |

`^` is **right-associative**, so `2^3^2` is `2^(3^2)` = `512`, not `64`.
Arithmetic and comparison operators **broadcast** over ranges/arrays (see
[Dynamic arrays and spill](#dynamic-arrays-and-spill)).

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

`#CIRC!` is the **default** answer to a circular reference: normal evaluation
reports it rather than looping. A circular reference can instead be **resolved**
by opt-in **iterative calculation** — off by default, enabled with the
`calc_iterative` setting (with `calc_max_iterations`, default `100`, and
`calc_max_change`, default `0.001`). When enabled, pressing **F9** (Recalculate)
fixed-point iterates every formula cell: a circular read reads the previous
iteration's value instead of `#CIRC!`, so an accumulator (`B1 = A1 + B1`) or a
convergent model settles. Iteration stops once the largest change across a sweep
is within `calc_max_change`, or at the `calc_max_iterations` cap. With the
setting off, a genuine circular reference still reports `#CIRC!`.

## Functions

Function names are case-insensitive. Below, every built-in is grouped by
family with its signature, a one-line description, and an example. Optional
arguments are shown in `[brackets]`. There are **over 630 built-in functions** —
**591 eager** (counting aliases and modern dotted names), **6 lazy** control-flow
functions, and **21 reference/context** functions (`ROW`, `OFFSET`, `INDIRECT`,
`CELL`, `LET`, `LAMBDA`, …) — **618 names** in all; user macros can add more
(see the [UDFs](#user-defined-functions-udfs) note).

Coverage spans the everyday Excel / Gnumeric set: math and trigonometry
(including hyperbolic and reciprocal), combinatorics, a full statistical
distribution family, financial (time-value-of-money, cashflow, depreciation),
text, date/time, engineering (base conversions, bitwise, Bessel), database
(`D*`) functions, reference functions, and a large RF / amateur-radio set. Modern
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
| `SUBTOTAL` | Aggregate by function number 1–11 (AVERAGE…VARP; 101–111 accepted) | `SUBTOTAL(function_num, ref, ...)` | `=SUBTOTAL(9,A1:A4)` | sum of range |
| `AGGREGATE` | Like `SUBTOTAL` plus 12–19 (MEDIAN…QUARTILE.EXC); options 2/3/6/7 ignore errors in the data | `AGGREGATE(function_num, options, ref, [k])` | `=AGGREGATE(14,6,A1:A5,2)` | 2nd largest, errors skipped |

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
| `CEILING.MATH` | Ceiling to a multiple; `mode` sends negatives away from zero | `CEILING.MATH(num, [sig], [mode])` | `=CEILING.MATH(24.3,5)` | `25` |
| `FLOOR.MATH` | Floor to a multiple; `mode` sends negatives toward zero | `FLOOR.MATH(num, [sig], [mode])` | `=FLOOR.MATH(-8.1,2)` | `-10` |
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

Beyond the aggregate functions above, abax ships gnumeric-style statistics
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
| `MAXA` · `MINA` | Max / min, counting text as 0, TRUE as 1 | `MAXA(value, ...)` | `=MAXA(1,"x",TRUE)` | `1` |
| `VARA` · `VARPA` | Sample / population variance, text as 0 | `VARA(value, ...)` | `=VARPA(1,2,3)` | `0.667` |
| `STDEVA` · `STDEVPA` | Sample / population std dev, text as 0 | `STDEVA(value, ...)` | `=STDEVA(1,2,3,4)` | `1.291` |
| `SKEWP` | Population skewness | `SKEWP(value, ...)` | `=SKEWP(A1:A9)` | skewness |
| `KURTP` | Population (excess) kurtosis | `KURTP(value, ...)` | `=KURTP(A1:A9)` | kurtosis |
| `RANGE` | Spread `max − min` of the values | `RANGE(value, ...)` | `=RANGE(2,4,9)` | `7` |
| `COVARIANCE.S` | Sample covariance of two ranges | `COVARIANCE.S(range1, range2)` | `=COVARIANCE.S(A1:A9,B1:B9)` | covariance |
| `COVARIANCE.P` | Population covariance (= `COVAR`) | `COVARIANCE.P(range1, range2)` | `=COVARIANCE.P(A1:A9,B1:B9)` | covariance |
| `MODE.SNGL` | Single most frequent value (= `MODE`) | `MODE.SNGL(value, ...)` | `=MODE.SNGL(1,2,2,3)` | `2` |
| `PROB` | Total probability where x is in a range | `PROB(x_range, prob_range, lower, [upper])` | `=PROB(A1:A4,B1:B4,2,3)` | probability |
| `PERCENTILE.EXC` | k-th percentile, *exclusive* | `PERCENTILE.EXC(range, k)` | `=PERCENTILE.EXC(A1:A4,0.25)` | exclusive pct |
| `QUARTILE.EXC` | Quartile, exclusive | `QUARTILE.EXC(range, q)` | `=QUARTILE.EXC(A1:A4,1)` | exclusive Q1 |
| `PERCENTRANK.EXC` | Percent rank, exclusive | `PERCENTRANK.EXC(range, x)` | `=PERCENTRANK.EXC(A1:A4,2)` | `0`…`1` |

**Array-returning (spilling) statistics.** These produce an array and
[spill](#dynamic-arrays-and-spill) from their anchor cell:

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `FREQUENCY` | Counts of `data` falling in each bin | `FREQUENCY(data, bins)` | `=FREQUENCY(A1:A20,B1:B4)` | column of counts |
| `MODE.MULT` | Every value tied for most frequent | `MODE.MULT(range)` | `=MODE.MULT(A1:A9)` | column of modes |
| `TREND` | Linear fit predictions | `TREND(known_ys, [known_xs], [new_xs])` | `=TREND(B1:B9,A1:A9,A10:A12)` | predicted ys |
| `GROWTH` | Exponential fit predictions | `GROWTH(known_ys, [known_xs], [new_xs])` | `=GROWTH(B1:B9,A1:A9)` | predicted ys |
| `LINEST` | Least-squares coefficients (multiple regression) | `LINEST(known_ys, [known_xs])` | `=LINEST(C1:C9,A1:B9)` | `[b_k … b_1, intercept]` |
| `LOGEST` | Exponential fit `y = b·m1^x1·…` | `LOGEST(known_ys, [known_xs])` | `=LOGEST(C1:C9,A1:B9)` | `[m_k … m_1, b]` |

`LINEST`/`LOGEST` accept **multiple predictor columns** and return the
coefficients right-to-left (Excel order), intercept last. `TREND`/`GROWTH`
remain single-predictor.

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

**R-style distribution family (Gnumeric-compatible).** For users who think in
R's naming, every common distribution is also available as a density
(`R.D…`), a lower-tail cumulative (`R.P…`) and a quantile / inverse (`R.Q…`).
All three share the value/parameter order below (the `D`/`P`/`Q` prefix only
swaps density ↔ cumulative ↔ quantile). Example: `=R.QNORM(0.975,0,1)` → `1.96`;
`=R.PT(0,5)` → `0.5`; `=R.PGUMBEL(0,0,1)` → `0.3679`. Parameters shown in
`[brackets]` are optional with the noted default.

**Continuous** — call as `R.D…(x, …)`, `R.P…(x, …)`, `R.Q…(p, …)`:

| Distribution | Trio | Parameters (after `x`/`p`) |
|---|---|---|
| Normal | `R.DNORM` `R.PNORM` `R.QNORM` | `[mean=0]`, `[sd=1]` |
| Skew-normal | `R.DSNORM` `R.PSNORM` `R.QSNORM` | `[loc=0]`, `[scale=1]`, `[shape=0]` |
| Log-normal | `R.DLNORM` `R.PLNORM` `R.QLNORM` | `[meanlog=0]`, `[sdlog=1]` |
| Exponential | `R.DEXP` `R.PEXP` `R.QEXP` | `[rate=1]` |
| Gamma | `R.DGAMMA` `R.PGAMMA` `R.QGAMMA` | `shape`, `[scale=1]` |
| Beta | `R.DBETA` `R.PBETA` `R.QBETA` | `a`, `b` |
| Weibull | `R.DWEIBULL` `R.PWEIBULL` `R.QWEIBULL` | `shape`, `[scale=1]` |
| Chi-square | `R.DCHISQ` `R.PCHISQ` `R.QCHISQ` | `df` |
| Student-t | `R.DT` `R.PT` `R.QT` | `df` |
| F | `R.DF` `R.PF` `R.QF` | `df1`, `df2` |
| Uniform | `R.DUNIF` `R.PUNIF` `R.QUNIF` | `[min=0]`, `[max=1]` |
| Cauchy | `R.DCAUCHY` `R.PCAUCHY` `R.QCAUCHY` | `[loc=0]`, `[scale=1]` |
| Gumbel | `R.DGUMBEL` `R.PGUMBEL` `R.QGUMBEL` | `[loc=0]`, `[scale=1]` |
| Laplace | `R.DLAPLACE` `R.PLAPLACE` `R.QLAPLACE` | `[loc=0]`, `[scale=1]` |
| Logistic | `R.DLOGIS` `R.PLOGIS` `R.QLOGIS` | `[loc=0]`, `[scale=1]` |
| Rayleigh | `R.DRAYLEIGH` `R.PRAYLEIGH` `R.QRAYLEIGH` | `[scale=1]` |
| Pareto | `R.DPARETO` `R.PPARETO` `R.QPARETO` | `scale` (minimum), `shape` |

**Discrete** — `R.D…` is the PMF, `R.P…` the CDF, `R.Q…` the quantile:

| Distribution | Trio | Parameters (after `k`/`p`) |
|---|---|---|
| Binomial | `R.DBINOM` `R.PBINOM` `R.QBINOM` | `size`, `prob` |
| Poisson | `R.DPOIS` `R.PPOIS` `R.QPOIS` | `lambda` |
| Geometric | `R.DGEOM` `R.PGEOM` `R.QGEOM` | `prob` |
| Negative binomial | `R.DNBINOM` `R.PNBINOM` `R.QNBINOM` | `size`, `prob` |
| Hypergeometric | `R.DHYPER` `R.PHYPER` `R.QHYPER` | `m` (successes), `n` (failures), `k` (draws) |

**Modern dotted family (left-tail / density forms).** The legacy `TDIST` /
`FDIST` / `CHIDIST` names are Excel's *right-tail* probabilities; these are the
modern left-tail/density halves and their inverses, plus the hypothesis tests:

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `NORM.S.DIST` | Standard normal CDF or density | `NORM.S.DIST(z, cumulative)` | `=NORM.S.DIST(1.333333,TRUE)` | `0.9088` |
| `T.DIST` | Student-t left-tail CDF or density | `T.DIST(x, df, cumulative)` | `=T.DIST(60,1,TRUE)` | `0.9947` |
| `T.DIST.RT` | Student-t right tail | `T.DIST.RT(x, df)` | `=T.DIST.RT(1.96,60)` | `0.0273` |
| `T.DIST.2T` | Student-t two-tailed | `T.DIST.2T(x, df)` | `=T.DIST.2T(1.96,60)` | `0.0546` |
| `T.INV` | Left-tail t inverse | `T.INV(p, df)` | `=T.INV(0.75,2)` | `0.8165` |
| `T.INV.2T` | Two-tailed t inverse (= `TINV`) | `T.INV.2T(p, df)` | `=T.INV.2T(0.546449,60)` | `0.6065` |
| `CHISQ.DIST` | χ² left-tail CDF or density | `CHISQ.DIST(x, df, cumulative)` | `=CHISQ.DIST(0.5,1,TRUE)` | `0.5205` |
| `CHISQ.INV` | Left-tail χ² inverse | `CHISQ.INV(p, df)` | `=CHISQ.INV(0.93,1)` | `3.2830` |
| `F.DIST` | F left-tail CDF or density | `F.DIST(x, df1, df2, cumulative)` | `=F.DIST(15.207,6,4,TRUE)` | `0.99` |
| `F.INV` | Left-tail F inverse | `F.INV(p, df1, df2)` | `=F.INV(0.01,6,4)` | `0.1093` |
| `CONFIDENCE.T` | t-based confidence half-width | `CONFIDENCE.T(alpha, sd, n)` | `=CONFIDENCE.T(0.05,1,50)` | `0.2842` |
| `T.TEST` | t-test p-value (tails 1/2; type 1 paired, 2 pooled, 3 Welch) | `T.TEST(array1, array2, tails, type)` | `=T.TEST(A1:A9,B1:B9,2,1)` | p-value |
| `Z.TEST` | One-tailed z-test (alias `ZTEST`) | `Z.TEST(array, x, [sigma])` | `=Z.TEST(A1:A10,4)` | `0.0906` |
| `F.TEST` | Two-tailed variance-equality test (alias `FTEST`) | `F.TEST(array1, array2)` | `=F.TEST(A1:A5,B1:B5)` | p-value |
| `CHISQ.TEST` | Independence-test p-value (alias `CHITEST`) | `CHISQ.TEST(actual, expected)` | `=CHISQ.TEST(A1:B3,D1:E3)` | p-value |

**Modern dotted aliases.** Excel's newer `.` names are registered as exact
aliases of their legacy equivalents (same arguments and results):

| Dotted name | Legacy equivalent |
|---|---|
| `STDEV.S` · `STDEV.P` | `STDEV` · `STDEVP` |
| `VAR.S` · `VAR.P` | `VAR` · `VARP` |
| `NORM.DIST` · `NORM.INV` | `NORMDIST` · `NORMINV` |
| `NORM.S.INV` | `NORMSINV` |
| `PERCENTILE.INC` · `QUARTILE.INC` | `PERCENTILE` · `QUARTILE` |
| `PERCENTRANK.INC` | `PERCENTRANK` |
| `MODE.SNGL` | `MODE` |
| `COVARIANCE.P` | `COVAR` |
| `CONFIDENCE.NORM` | `CONFIDENCE` |
| `CHISQ.DIST.RT` · `CHISQ.INV.RT` | `CHIDIST` · `CHIINV` |
| `F.DIST.RT` · `F.INV.RT` | `FDIST` · `FINV` |
| `BINOM.DIST` · `BINOM.INV` | `BINOMDIST` · `CRITBINOM` |
| `POISSON.DIST` · `EXPON.DIST` | `POISSON` · `EXPONDIST` |
| `GAMMA.DIST` · `GAMMA.INV` | `GAMMADIST` · `GAMMAINV` |
| `BETA.DIST` · `BETA.INV` | `BETADIST` · `BETAINV` |
| `WEIBULL.DIST` | `WEIBULL` |
| `LOGNORM.DIST` · `LOGNORM.INV` | `LOGNORMDIST` · `LOGINV` |
| `NEGBINOM.DIST` · `HYPGEOM.DIST` | `NEGBINOMDIST` · `HYPGEOMDIST` |
| `ERF.PRECISE` · `ERFC.PRECISE` | `ERF` · `ERFC` |
| `FORECAST.LINEAR` | `FORECAST` |
| `SKEW.P` | `SKEWP` |
| `GAMMALN.PRECISE` | `GAMMALN` |

### Special math and number theory

Gnumeric-parity functions the standard set lacks.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `BETA` | Beta function `B(a,b)` | `BETA(a, b)` | `=BETA(2,3)` | `0.0833` |
| `BETALN` | Natural log of `B(a,b)` | `BETALN(a, b)` | `=BETALN(2,3)` | `-2.485` |
| `POCHHAMMER` | Rising factorial `(x)_n` | `POCHHAMMER(x, n)` | `=POCHHAMMER(5,3)` | `210` |
| `GD` | Gudermannian, `2·atan(tanh(x/2))` | `GD(x)` | `=GD(1)` | `0.8657` |
| `ITHPRIME` | The n-th prime | `ITHPRIME(n)` | `=ITHPRIME(10)` | `29` |
| `ISPRIME` | Is n prime? | `ISPRIME(n)` | `=ISPRIME(97)` | `TRUE` |
| `NT_PI` | Prime-counting function π(n) | `NT_PI(n)` | `=NT_PI(10)` | `4` |
| `NT_D` | Number of divisors of n | `NT_D(n)` | `=NT_D(12)` | `6` |
| `NT_SIGMA` | Sum of divisors of n | `NT_SIGMA(n)` | `=NT_SIGMA(12)` | `28` |
| `NT_PHI` | Euler totient φ(n) | `NT_PHI(n)` | `=NT_PHI(12)` | `4` |
| `NT_MU` | Möbius function μ(n) | `NT_MU(n)` | `=NT_MU(30)` | `-1` |

### Lookup and reference

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `VLOOKUP` | Vertical lookup in a table | `VLOOKUP(value, table, col_index, [approx])` | `=VLOOKUP("kiwi",A1:C9,3,FALSE)` | column-3 cell |
| `HLOOKUP` | Horizontal lookup in a table | `HLOOKUP(value, table, row_index, [approx])` | `=HLOOKUP("Q2",A1:E3,2,FALSE)` | row-2 cell |
| `MATCH` | Position of value (type 1/0/-1) | `MATCH(value, range, [match_type])` | `=MATCH(7,A1:A9,0)` | index of 7 |
| `INDEX` | Value at row/col of a range | `INDEX(range, row, [col])` | `=INDEX(A1:C9,2,3)` | cell at (2,3) |
| `XLOOKUP` | Modern lookup (exact by default) | `XLOOKUP(value, lookup_range, return_range, [if_missing], [match])` | `=XLOOKUP("kiwi",A1:A9,C1:C9)` | matched value |
| `XMATCH` | Modern position match (modes 0 exact / -1 next-smaller / 1 next-larger / 2 wildcard; search 1 forward, -1 reverse) | `XMATCH(value, range, [match_mode], [search_mode])` | `=XMATCH(25,{10,20,30},1)` | `3` |
| `LOOKUP` | Classic largest-value-≤ lookup (vector or array form) | `LOOKUP(value, lookup_vector, [result_vector])` | `=LOOKUP(5.75,A1:A5,B1:B5)` | matched value |

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
| `ISREF` | TRUE when the argument is a reference | `ISREF(value)` | `=ISREF(A1)` | `TRUE` |
| `ISFORMULA` | TRUE when the referenced cell holds a formula | `ISFORMULA(reference)` | `=ISFORMULA(D1)` | `TRUE`/`FALSE` |
| `FORMULATEXT` | The referenced cell's formula text (`#N/A` if none) | `FORMULATEXT(reference)` | `=FORMULATEXT(D1)` | `=SUM(A1:A3)` |
| `SHEET` | 1-based sheet index (of the caller, a reference, or a named sheet) | `SHEET([value])` | `=SHEET("Data")` | `2` |
| `SHEETS` | Sheet count of the workbook | `SHEETS([reference])` | `=SHEETS()` | `2` |
| `CELL` | Cell info: `address` / `row` / `col` / `contents` / `type` / `filename` | `CELL(info_type, [reference])` | `=CELL("address",C4)` | `$C$4` |
| `HYPERLINK` | A link's display value — the friendly name when given, else the link text (abax cells aren't clickable) | `HYPERLINK(link_location, [friendly_name])` | `=HYPERLINK("https://a.org","abax")` | `abax` |
| `ENCODEURL` | Percent-encode text as a URL component (everything outside `A–Z a–z 0–9 - _ . ~`, UTF-8 first) | `ENCODEURL(text)` | `=ENCODEURL("a b")` | `a%20b` |

For `VLOOKUP`/`HLOOKUP` the 4th argument defaults to **TRUE** (approximate,
assumes ascending order); pass `FALSE` for an exact match. `MATCH` defaults to
type `1` (largest value ≤ target, ascending); `0` is exact; `-1` is smallest
value ≥ target.

### Live data (network)

Two volatile functions turn a cell into a live view of an external JSON source.
They are **disabled by default**: nothing connects until you opt in via **Tools →
Enable live data** (GUI) or `:live on` (TUI) — so a workbook opened from disk can
never phone home. URLs are limited to `http` / `https` / `ws` / `wss`.

| Function | Description | Signature | Example |
|---|---|---|---|
| `REST` | Poll a JSON endpoint every *interval* seconds (default 5) and show a value dug out by *path* | `REST(url, [path], [interval])` | `=REST("https://api.example/quote","data.last",2)` |
| `WEBSOCKET` | Stream JSON text frames from a WebSocket, showing the latest *path* value | `WEBSOCKET(url, [path])` | `=WEBSOCKET("wss://api.example/ticks","[0].price")` |

*path* is a small JSON path: dotted keys and `[i]` indices (negative allowed),
e.g. `data.tickers[0].price`; omit it to show the whole document. Many cells
watching the same URL share one background connection. A cell shows `#OFF!` while
live data is disabled, `#N/A` until the first value arrives, then the value
(numbers stay numbers). The grid recalcs automatically when a source pushes an
update. Connection secrets are never persisted — put credentials in the URL only
for trusted, local endpoints.

### External workbook references

Reference a cell in another, **closed** workbook by qualifying the sheet with a
bracketed file name:

```
=[Budget.abax]Sheet1!B4
='[Q3 Results.abax]Summary'!A1      (quote when the name has spaces)
```

The referenced workbook is loaded **once, in the background**, and cached; the
cell shows `#N/A` until the load finishes, then the value (the grid refreshes on
its own). Like live data, this is **disabled by default**: until you opt in via
**Tools → Enable external references** (GUI) or `:extern on` (TUI), such a
reference resolves to `#OFF!` and no file is read — so opening an untrusted
workbook can never make abax read other files. Paths resolve **relative to the
open workbook's folder** (absolute paths are allowed too) and only `.abax` /
`.json` workbooks load; anything else, or a missing file/sheet/cell, yields
`#REF!`.

### Dynamic arrays and spill

A formula whose result is an *array* **spills**: the formula lives in the
top-left **anchor** cell and the remaining values fill the cells below and to
the right. You edit only the anchor; the spilled cells are computed, not stored,
so the workbook saves just the one source formula. If a cell the array needs to
fill already holds something, the anchor shows **`#SPILL!`**; an array that
comes out empty (e.g. `FILTER` with no matches) shows **`#CALC!`**. The GUI
draws a dashed blue outline around a spill range; the TUI tints it.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `UNIQUE` | Distinct values (first-seen order) | `UNIQUE(range)` | `=UNIQUE(A1:A9)` | column of distinct values |
| `SORT` | Sort a range | `SORT(range, [ascending])` | `=SORT(A1:A9)` | sorted column |
| `SORTBY` | Sort rows by one or more key arrays | `SORTBY(array, by1, [order1], …)` | `=SORTBY(A1:A9,B1:B9,-1)` | rows of `A` by `B` desc |
| `FILTER` | Keep values where a condition is truthy | `FILTER(range, condition_range)` | `=FILTER(A1:A9,B1:B9)` | matching values |
| `SEQUENCE` | Generate a run of numbers | `SEQUENCE(rows, [cols], [start], [step])` | `=SEQUENCE(2,3)` | 2×3 block `1..6` |
| `RANDARRAY` | Array of random numbers | `RANDARRAY([rows],[cols],[min],[max],[int])` | `=RANDARRAY(3,1,1,6,TRUE)` | random column |
| `TRANSPOSE` | Flip rows and columns | `TRANSPOSE(array)` | `=TRANSPOSE(A1:A3)` | one row |
| `VSTACK` / `HSTACK` | Stack arrays vertically / horizontally | `VSTACK(a, b, …)` | `=VSTACK(A1:A3,B1:B3)` | combined block |
| `TAKE` / `DROP` | Keep / remove first or last rows·cols | `TAKE(array, rows, [cols])` | `=TAKE(A1:A9,3)` | first 3 |
| `CHOOSEROWS` / `CHOOSECOLS` | Pick rows / columns (1-based, negatives from end) | `CHOOSEROWS(array, n1, …)` | `=CHOOSEROWS(A1:A9,1,-1)` | first and last |
| `TOROW` / `TOCOL` | Flatten to a single row / column | `TOCOL(array, [ignore], [by_col])` | `=TOCOL(A1:C3)` | one column |
| `EXPAND` | Grow to a size, padding | `EXPAND(array, rows, [cols], [pad])` | `=EXPAND(A1:A3,5,1,0)` | 5 rows, padded |
| `WRAPROWS` / `WRAPCOLS` | Wrap a vector into rows / columns | `WRAPROWS(vector, count, [pad])` | `=WRAPROWS(A1:F1,2)` | 3×2 block |
| `MMULT` | Matrix product | `MMULT(a, b)` | `=MMULT(A1:B2,D1:E2)` | product block |
| `MINVERSE` | Inverse of a square matrix | `MINVERSE(a)` | `=MINVERSE(A1:B2)` | inverse (or `#NUM!`) |
| `MUNIT` | The n×n identity matrix | `MUNIT(n)` | `=MUNIT(3)` | 3×3 identity |

These also compose when nested inside an aggregate without spilling — e.g.
`=SUM(UNIQUE(A1:A9))`, `=COUNT(FILTER(A1:A9,B1:B9))`, or `=SUM(MMULT(A1:B2,D1:E2))`.

**Array constants.** Write a literal array inline with braces: commas separate
columns, semicolons separate rows. `={1,2,3}` is a row, `={1;2;3}` a column, and
`={1,2;3,4}` a 2-D block. They spill and compose like any array — `=SORT({3,1,2})`,
`=SUM({1,2,3,4})`, `={1,2,3}*10`.

**Array arithmetic (broadcasting).** Operators apply element-wise across arrays
and spill the result. A scalar broadcasts against every element; two arrays
combine cell-by-cell; a row and a column form an outer product. Dimensions must
match or be 1 (numpy-style); otherwise the result is `#VALUE!`.

| Formula | Result |
|---|---|
| `=A1:A3*2` | each of A1:A3 doubled, spilled down |
| `=10+A1:A3` | 10 added to each |
| `=A1:A3>100` | a boolean array (feeds `FILTER`) |
| `=A1:C1*E1:E2` | a row × a column → a 2-D block |
| `=SUM(A1:A3*B1:B3)` | element-wise product, then summed (like `SUMPRODUCT`) |

**Spill-range reference `A1#`.** `A1#` is the whole array that spilled from the
anchor `A1`. It tracks the source as it resizes: `=SUM(A1#)` totals the spill,
`=A1#` mirrors it elsewhere. A `#` on a cell that isn't a spill anchor is
`#REF!`.

**Implicit intersection `@`.** `=@A1:A10` returns the one value from the range on
the calling cell's row (or column, for a horizontal range); `=@SEQUENCE(5)`
forces a function's first value so it does *not* spill.

**`IF` over an array** broadcasts element-wise: `=IF(A1:A9>0,"+","−")` spills a
label per row, and `=SUM(IF(A1:A9>0,A1:A9,0))` sums just the positives — the
classic array-formula pattern, no Ctrl+Shift+Enter needed.

### LET, LAMBDA and functional helpers

`LET` names intermediate results so a formula computes them once and reads
clearly; `LAMBDA` builds a reusable function value. A lambda is *used* by
passing it to one of the functional helpers below, by naming it with `LET`
and calling the name — `=LET(f, LAMBDA(x, x*x), f(5))` → `25` — or by
**calling it directly**: `=LAMBDA(x, x+1)(5)` → `6`, and calls chain
(`=LAMBDA(a, LAMBDA(b, a+b))(3)(4)` → `7`). A lambda may be called with **fewer
arguments than it declares**; the trailing parameters are then *omitted*, and
`ISOMITTED(param)` tests for that — the idiom for default arguments:
`=LAMBDA(a, b, IF(ISOMITTED(b), a, a+b))`. An un-applied lambda in a cell shows
`#CALC!`. Binding names may not look like cell references (`x` works, `x1` is the
reference X1) — the same restriction Excel imposes — and a workbook-defined name
takes precedence over a LET name.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `LET` | Bind names to values, then evaluate | `LET(name1, value1, [name2, value2, ...], calculation)` | `=LET(x, 2, y, x+1, x*y)` | `6` |
| `LAMBDA` | A function value (use via LET or the helpers) | `LAMBDA(param1, ..., body)` | `=LET(f, LAMBDA(x, x*x), f(5))` | `25` |
| `MAP` | Apply a lambda element-wise (spills) | `MAP(array1, [array2, ...], lambda)` | `=MAP(A1:A3, LAMBDA(x, x*2))` | doubled column |
| `REDUCE` | Fold an array to one value | `REDUCE(initial, array, lambda(acc, value))` | `=REDUCE(0, A1:A3, LAMBDA(a, v, a+v))` | the sum |
| `SCAN` | Fold, keeping every intermediate (spills) | `SCAN(initial, array, lambda(acc, value))` | `=SCAN(0, A1:A3, LAMBDA(a, v, a+v))` | running total |
| `BYROW` | One lambda result per row (spills a column) | `BYROW(array, lambda(row))` | `=BYROW(A1:B3, LAMBDA(r, SUM(r)))` | row sums |
| `BYCOL` | One lambda result per column (spills a row) | `BYCOL(array, lambda(column))` | `=BYCOL(A1:B3, LAMBDA(c, MAX(c)))` | column maxima |
| `MAKEARRAY` | Build an array from a lambda of (row, col) | `MAKEARRAY(rows, cols, lambda(r, c))` | `=MAKEARRAY(2, 3, LAMBDA(r, c, r*c))` | 2×3 times table |
| `ISOMITTED` | True if a LAMBDA parameter was omitted in the call | `ISOMITTED(param)` | `=LAMBDA(a,b,IF(ISOMITTED(b),a,a+b))(5)` | `5` |

### Logical and control flow

`AND`, `OR`, `XOR`, `NOT`, `TRUE`, `FALSE` are eager. `IF`, `IFERROR`, `IFNA`,
`IFS`, `SWITCH`, `CHOOSE` are **lazy** — they receive unevaluated branches, so
untaken branches never run (no spurious errors or side effects).

`IFERROR` and `IFNA` are **array-aware**: applied to a spilled array they catch
errors **element-wise**, so `=IFERROR(A1:A100/B1:B100, 0)` guards a whole column
and only the cells that actually error take the fallback.

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
| `TEXTSPLIT` | Split text into a spilled array (row and/or column delimiters, each a string or array of strings) | `TEXTSPLIT(text, col_delim, [row_delim], [ignore_empty], [match_mode], [pad_with])` | `=TEXTSPLIT("a,b;c,d",",",";")` | 2×2 spill |
| `ARRAYTOTEXT` | Render an array as text (`format` 1 = strict `{…}`) | `ARRAYTOTEXT(array, [format])` | `=ARRAYTOTEXT({1,2;3,4})` | `1, 2, 3, 4` |
| `VALUETOTEXT` | Render a value as text (`format` 1 quotes strings) | `VALUETOTEXT(value, [format])` | `=VALUETOTEXT("hi",1)` | `"hi"` |
| `REGEXTEST` | Does the regex match anywhere? (`case_sensitivity` 0 sensitive, 1 insensitive) | `REGEXTEST(text, pattern, [case_sensitivity])` | `=REGEXTEST("abc123","\d+")` | `TRUE` |
| `REGEXEXTRACT` | Extract matches (`return_mode` 0 first, 1 all → spills, 2 capture groups) | `REGEXEXTRACT(text, pattern, [return_mode], [case_sensitivity])` | `=REGEXEXTRACT("a1b2c3","\d",1)` | `1,2,3` spill |
| `REGEXREPLACE` | Replace every match globally | `REGEXREPLACE(text, pattern, replacement, [case_sensitivity])` | `=REGEXREPLACE("a1b2","\d","#")` | `a#b#` |

Regex functions use Python (PCRE-style) syntax. A bad pattern gives `#VALUE!`; `REGEXEXTRACT` mode 0 with no match gives `#N/A`.

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
| `WORKDAY.INTL` | `WORKDAY` with a configurable weekend (number 1–7 / 11–17, or a 7-char Mon-first mask like `"0000011"`) | `WORKDAY.INTL(start, days, [weekend], [holidays])` | `=WORKDAY.INTL("2026-01-01",5,11)` | `2026-01-07` |
| `NETWORKDAYS.INTL` | `NETWORKDAYS` with a configurable weekend | `NETWORKDAYS.INTL(start, end, [weekend], [holidays])` | `=NETWORKDAYS.INTL("2026-01-01","2026-01-31",11)` | `27` |

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

**Bonds and securities.** Dates are ISO strings; `frequency` is coupons per
year (1, 2 or 4); `basis` is the day-count convention (0 = US 30/360 default,
1 = actual/actual, 2 = actual/360, 3 = actual/365, 4 = European 30/360).
Coupon schedules walk back from maturity with Excel's end-of-month rule.

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `PRICE` | Price per 100 face of a coupon bond | `PRICE(settlement, maturity, rate, yld, redemption, frequency, [basis])` | `=PRICE("2008-02-15","2017-11-15",0.0575,0.065,100,2,0)` | `94.634` |
| `YIELD` | Yield of a coupon bond at a price | `YIELD(settlement, maturity, rate, pr, redemption, frequency, [basis])` | `=YIELD("2008-02-15","2016-11-15",0.0575,95.04287,100,2,0)` | `0.065` |
| `DURATION` | Macaulay duration (years) | `DURATION(settlement, maturity, coupon, yld, frequency, [basis])` | `=DURATION("2008-01-01","2016-01-01",0.08,0.09,2,1)` | `5.9938` |
| `MDURATION` | Modified duration | `MDURATION(settlement, maturity, coupon, yld, frequency, [basis])` | `=MDURATION("2008-01-01","2016-01-01",0.08,0.09,2,1)` | `5.7357` |
| `COUPPCD` / `COUPNCD` | Coupon date before / after settlement | `COUPPCD(settlement, maturity, frequency, [basis])` | `=COUPPCD("2011-01-25","2011-11-15",2,1)` | `2010-11-15` |
| `COUPNUM` | Coupons remaining to maturity | `COUPNUM(settlement, maturity, frequency, [basis])` | `=COUPNUM("2007-01-25","2008-11-15",2,1)` | `4` |
| `COUPDAYBS` / `COUPDAYS` / `COUPDAYSNC` | Days from period start to settlement / in the period / to the next coupon | `COUPDAYS(settlement, maturity, frequency, [basis])` | `=COUPDAYS("2011-01-25","2011-11-15",2,1)` | `181` |
| `DISC` | Discount rate of a discounted security | `DISC(settlement, maturity, pr, redemption, [basis])` | `=DISC("2007-01-25","2007-06-15",97.975,100,1)` | `0.0524` |
| `PRICEDISC` / `YIELDDISC` | Price / yield of a discounted security | `PRICEDISC(settlement, maturity, discount, redemption, [basis])` | `=PRICEDISC("2008-02-16","2008-03-01",0.0525,100,2)` | `99.796` |
| `INTRATE` | Interest rate of a fully-invested security | `INTRATE(settlement, maturity, investment, redemption, [basis])` | `=INTRATE("2008-02-15","2008-05-15",1000000,1014420,2)` | `0.0577` |
| `RECEIVED` | Amount received at maturity | `RECEIVED(settlement, maturity, investment, discount, [basis])` | `=RECEIVED("2008-02-15","2008-05-15",1000000,0.0575,2)` | `1014584.65` |
| `ACCRINT` | Accrued interest (periodic-interest security) | `ACCRINT(issue, first_interest, settlement, rate, par, frequency, [basis])` | `=ACCRINT("2008-03-01","2008-08-31","2008-05-01",0.1,1000,2,0)` | `16.667` |
| `ACCRINTM` | Accrued interest at maturity | `ACCRINTM(issue, settlement, rate, par, [basis])` | `=ACCRINTM("2008-04-01","2008-06-15",0.1,1000,3)` | `20.548` |
| `PRICEMAT` / `YIELDMAT` | Price / yield of an interest-at-maturity security | `PRICEMAT(settlement, maturity, issue, rate, yld, [basis])` | `=PRICEMAT("2008-02-15","2008-04-13","2007-11-11",0.061,0.061,0)` | `99.984` |
| `TBILLEQ` | T-bill bond-equivalent yield | `TBILLEQ(settlement, maturity, discount)` | `=TBILLEQ("2008-03-31","2008-06-01",0.0914)` | `0.0942` |
| `TBILLPRICE` / `TBILLYIELD` | T-bill price / discount yield | `TBILLPRICE(settlement, maturity, discount)` | `=TBILLPRICE("2008-03-31","2008-06-01",0.09)` | `98.45` |

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
| `IMDIV` | Quotient of two complex numbers | `IMDIV(c1, c2)` | `=IMDIV("4+2i","1+1i")` | `3-i` |
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
| `IMTAN` / `IMCOT` | Tangent / cotangent | `IMTAN(c)` | `=IMTAN("0")` | `0` |
| `IMSEC` / `IMCSC` | Secant / cosecant | `IMSEC(c)` | `=IMSEC("0")` | `1` |
| `IMSINH` / `IMCOSH` / `IMTANH` | Hyperbolic sine / cosine / tangent | `IMSINH(c)` | `=IMCOSH("0")` | `1` |
| `IMSECH` / `IMCSCH` | Hyperbolic secant / cosecant | `IMSECH(c)` | `=IMSECH("0")` | `1` |
| `IMLOG2` / `IMLOG10` | Base-2 / base-10 logarithm | `IMLOG2(c)` | `=IMLOG2("4")` | `2` |
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

## RF / amateur radio

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
| `DXCC` | DXCC entity for a callsign prefix | `DXCC(callsign)` | `=DXCC("W1AW")` → `United States` |
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
| `ZINLINER` / `ZINLINEX` | lossless-line input Z real / imag (Ω) | `ZINLINER(zl_r, zl_x, z0, elen_deg)` | `=ZINLINER(100,0,50,90)` → `25` |
| `LINELOSS` | matched line loss (dB) | `LINELOSS(length_m, freq_hz, loss_db_per_100m)` | `=LINELOSS(50,1e8,4)` → `2` |

**Contest / activation logging** — dupe detection and QSO point values for
POTA / SOTA / contest logs. Callsigns are normalised (uppercased, portable
`/P` and prefix/suffix decorations stripped) before comparison, and the
`once per band per mode` convention is the default.

| Function | Description | Syntax | Example |
| --- | --- | --- | --- |
| `ISDUPE` | TRUE if `(call, band, mode)` already appears in a prior-QSO range (one QSO per row as `call \| band \| mode`) | `ISDUPE(call, band, mode, [log_range])` | `=ISDUPE("W1AW","20m","SSB",A1:C50)` |
| `QSOPOINTS` | Point value of one QSO in `mode` under a named ruleset (default `generic` = 1 pt; `fieldday` scores CW/digital 2, phone 1) | `QSOPOINTS(mode, [ruleset])` | `=QSOPOINTS("CW","fieldday")` → `2` |

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
