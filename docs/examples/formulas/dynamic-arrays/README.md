# Dynamic arrays: formulas that spill

One formula, many results: `=SORT(UNIQUE(...))` writes its whole answer
across neighbouring cells, Excel-style.

**You'll need:** abax only.

## Run it

```sh
cd docs/examples/formulas/dynamic-arrays
python run.py
```

## What you should see

```
A1:A8            : [70, 20, 70, 55, 20, 90, 55, 40]
SORT(UNIQUE(...)) : [20, 40, 55, 70, 90]
FILTER(... > 50)  : [70, 70, 55, 90, 55]
SEQUENCE(3, 3)    :
    [1.0, 2.0, 3.0]
    [4.0, 5.0, 6.0]
    [7.0, 8.0, 9.0]
```

## How it works

- `=SORT(UNIQUE(A1:A8))` in C1 *spills* downward — C2, C3, … hold the
  rest of the result without containing any formula of their own.
- `=FILTER(A1:A8, A1:A8>50)` keeps the rows where the condition holds.
- `=SEQUENCE(3, 3)` spills a 3×3 block to the right and down.
- Reading a spilled cell is just `sheet.get_value(row, col)` — the script
  walks down each column until it hits an empty cell.
- In the grid, `A1#` references a whole spill range, and a blocked spill
  shows `#SPILL!` instead of overwriting your data.

## Next steps

- The full reshaping family (`TRANSPOSE`, `VSTACK`, `TAKE`, `MMULT`, …)
  is in the [formula reference](../../../formula-reference.md).
- [Structured tables](../../data/structured-tables/README.md) — name a
  region and query it by column label.
