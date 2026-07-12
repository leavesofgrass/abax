# Goal Seek: solve for an input

You know the answer you want — Goal Seek finds the input that produces
it. Here: "what loan gives a $400/month payment?"

**You'll need:** abax only.

## Run it

```sh
cd docs/examples/analysis/goal-seek
python run.py
```

## What you should see

```
Borrowing 25000 costs 495.03/month
For a 400.00/month budget you can borrow 20200.80
Check: the sheet now shows payment = 400.00
```

## How it works

- The sheet computes a payment with `=-PMT(B2/12, B3*12, B1)` — rate per
  month, number of months, principal (PMT returns a negative cash flow,
  so the leading `-` flips it for display).
- `goal_seek(sheet, "B4", 400.0, "B1", lo=1000, hi=100000)` varies B1
  until B4 equals 400, writes the solution into the sheet, and returns it.
- On failure (target can't be reached inside `lo..hi`) the original cell
  value is restored and a `GoalSeekError` is raised — the sheet is never
  left half-solved.

## Next steps

- In the GUI: *Data → Goal seek* does this from a dialog.
- For multi-scenario planning, the what-if scenario manager is covered in
  [data & analysis tools](../../../data-analysis.md).
- The financial family (`PMT`, `PV`, `FV`, `NPV`, `IRR`, bonds) is in the
  [formula reference](../../../formula-reference.md).
