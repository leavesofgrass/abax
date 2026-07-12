# Clean a messy CSV and export it

Real-world CSVs arrive with stray spaces, SHOUTING case, and `$1,200.50`
amounts stored as text. Fix all of it with three formulas and export a
clean file.

**You'll need:** abax only. The sample data is `messy.csv` in this folder.

## Run it

```sh
cd docs/examples/data/csv-clean-and-export
python run.py
```

## What you should see

```
raw name            raw amount   ->  clean             amount
'  alice JOHNSON '   $1,200.50   ->  Alice Johnson     1200.5
'BOB  smith'           $980.00   ->  Bob Smith          980.0
' carol WHITE'       $2,340.75   ->  Carol White      2340.75
'dave brown  '         $415.25   ->  Dave Brown        415.25

Wrote out/cleaned.csv — 4 rows, total 4936.50
```

## How it works

- The raw CSV loads into columns A–B with Python's `csv` module —
  nothing special, cells are just strings.
- Names: `=PROPER(TRIM(A2))` strips the padding and fixes the case.
- Amounts: `=VALUE(SUBSTITUTE(SUBSTITUTE(B2, "$", ""), ",", ""))` peels
  off the `$` and the thousands comma, then converts to a real number.
- The export loop writes `sheet.get_value(...)` — computed values, not
  formulas — through `csv.writer`.

## Next steps

- Convert the result to other formats with one CLI call:
  `abax convert out/cleaned.csv cleaned.xlsx` — see the
  [headless CLI example](../../scripting-and-cli/headless-cli/README.md)
  and [file formats](../../../file-formats.md).
- For bigger jobs, the *Data* menu has recode, sort, and group-by — see
  [data & analysis tools](../../../data-analysis.md).
