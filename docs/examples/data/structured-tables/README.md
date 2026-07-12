# Structured tables: query columns by name

Name a region as a Table and formulas read like English —
`=SUM(Sales[Amount])` instead of `=SUM(B2:B5)`.

**You'll need:** abax only.

## Run it

```sh
cd docs/examples/data/structured-tables
python run.py
```

## What you should see

```
 Total amount: 4650.0
  Average qty: 2.75
         Rows: 4.0
    West only: 1600.0
```

## How it works

- `detect_table(sheet, r1, c1, r2, c2, "Sales", headers)` builds a Table
  whose first row is the header; `wb.tables.add(table)` registers it.
- From then on any formula can use structured references:
  `=SUM(Sales[Amount])`, `=SUMIF(Sales[Region], "West", Sales[Amount])`.
- The reference survives edits that would break `B2:B5` — insert a row
  above the table and the label still points at the right data.
- Inside the table, `[@Amount]` means "this row's Amount", and
  `Sales[#Headers]` / `Sales[#Totals]` address the special rows.

## Next steps

- In the GUI, select a region and use the command palette
  (`Ctrl+Shift+P`) → *Create table* to do the same interactively.
- [Dynamic arrays](../../formulas/dynamic-arrays/README.md) pair well
  with tables: `=SORT(UNIQUE(Sales[Region]))`.
- The automation surface is in [Automation API](../../../automation.md).
