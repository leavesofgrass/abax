# Formula reference

This is the complete reference for qcell's formula engine: the syntax of
formulas, the value and error model, and every built-in function grouped by
family. It is generated from the authoritative registries `FUNCTIONS` and
`LAZY_FUNCTIONS` in `qcell/core/functions.py`.

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
arguments are shown in `[brackets]`. There are **139 eager built-in function
names** (counting aliases `AVG`/`CONCATENATE`) plus **6 lazy control-flow
functions** — **145 names** in all; user macros can add more (see the
[UDFs](#user-defined-functions-udfs) note).

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

### Lookup and reference

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `VLOOKUP` | Vertical lookup in a table | `VLOOKUP(value, table, col_index, [approx])` | `=VLOOKUP("kiwi",A1:C9,3,FALSE)` | column-3 cell |
| `HLOOKUP` | Horizontal lookup in a table | `HLOOKUP(value, table, row_index, [approx])` | `=HLOOKUP("Q2",A1:E3,2,FALSE)` | row-2 cell |
| `MATCH` | Position of value (type 1/0/-1) | `MATCH(value, range, [match_type])` | `=MATCH(7,A1:A9,0)` | index of 7 |
| `INDEX` | Value at row/col of a range | `INDEX(range, row, [col])` | `=INDEX(A1:C9,2,3)` | cell at (2,3) |

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

### Information

| Function | Description | Signature | Example | Result |
|---|---|---|---|---|
| `NA` | The `#N/A` error value | `NA()` | `=NA()` | `#N/A` |
| `ISBLANK` | True if empty | `ISBLANK(value)` | `=ISBLANK(A1)` | `TRUE`/`FALSE` |
| `ISNUMBER` | True if numeric (not boolean) | `ISNUMBER(value)` | `=ISNUMBER(42)` | `TRUE` |
| `ISTEXT` | True if text | `ISTEXT(value)` | `=ISTEXT("x")` | `TRUE` |
| `ISLOGICAL` | True if boolean | `ISLOGICAL(value)` | `=ISLOGICAL(TRUE)` | `TRUE` |
| `ISERROR` | True if an error value | `ISERROR(value)` | `=ISERROR(1/0)` | `TRUE` |

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

## User-defined functions (UDFs)

User macros can register new functions that are callable in formulas exactly
like built-ins: `=NAME(...)`. A `@register_function("NAME")` macro installs a
Python callable into the same `FUNCTIONS` registry, using the same evaluated
arg-list convention. For example, the bundled `macros/sample.py` defines
`TAXED` and `REVERSE`, so `=TAXED(100)` and `=REVERSE("abc")` work in any cell.

See [Macros and scripting](macros-and-scripting.md) for how to write, discover,
and load macros.
