# Descriptive statistics with formulas

Summarize a column of measurements — mean, median, spread, percentiles,
and a correlation — using ordinary spreadsheet formulas.

**You'll need:** abax only; the statistics functions are built in.

## Run it

```sh
cd docs/examples/formulas/descriptive-statistics
python run.py
```

## What you should see

```
        Mean: 305.333
      Median: 303.0
     Std dev: 20.065
   Min / Max: 279 / 344
 90th pctile: 329.2
         IQR: 27.25
  r (A vs B): -0.925
```

## How it works

- Reaction times go in column A, scores in column B — plain values.
- Each summary line is one formula: `=AVERAGE(A1:A12)`, `=STDEV.S(…)`,
  `=PERCENTILE(A1:A12, 0.9)`, `=QUARTILE(…, 3) - QUARTILE(…, 1)`.
- `=CORREL(A1:A12, B1:B12)` returns −0.925: slower reactions, lower
  scores — a strong negative correlation.
- Text and numbers concatenate with `&`, as in
  `=MIN(A1:A12)&" / "&MAX(A1:A12)`.

## Next steps

- In the GUI, *Tools → Data analysis → Descriptive statistics* produces a
  full report sheet from a selection — see
  [data & analysis tools](../../../data-analysis.md).
- The [formula reference](../../../formula-reference.md) lists every
  statistical function, including the distributions and hypothesis tests.
- [Dynamic arrays](../dynamic-arrays/README.md) — SORT/UNIQUE/FILTER spills.
