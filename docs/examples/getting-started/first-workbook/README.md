# Your first workbook

Build a tiny grocery sheet from Python — values, formulas, a saved
`.abax` file — in under 40 lines of pure-stdlib code.

**You'll need:** abax installed (`pipx install "abax[all]"` or plain
`pip install abax`) — this example uses no optional packages.

## Run it

```sh
cd docs/examples/getting-started/first-workbook
python run.py
```

## What you should see

```
   Item      Qty    Price    Total
 Apples        4      0.6      2.4
  Bread        2      2.1      4.2
 Coffee        1     8.75     8.75
  TOTAL                      15.35

Saved out/first-workbook.abax — open it in the GUI with:
  abax out/first-workbook.abax
```

## How it works

- `Workbook()` starts with one sheet; `sheet.set_cell(row, col, text)`
  fills it — anything starting with `=` is a formula.
- Formulas compute lazily on read: `sheet.get_value(r, c)` returns the
  calculated number, not the formula text.
- `wb.save_json(path)` writes the native `.abax` format — a plain JSON
  envelope you can open in the GUI, the TUI, or version control.
- The saved file keeps the *formulas*, so editing a price in the GUI
  recalculates the totals.

## Next steps

- [Take the sixty-second tour](../sixty-second-tour/README.md) of the GUI
  you just opened.
- [Descriptive statistics](../../formulas/descriptive-statistics/README.md)
  — summarize a data column with formulas.
- The [getting-started guide](../../../getting-started.md) covers installs,
  launch modes, and a five-minute walkthrough.
