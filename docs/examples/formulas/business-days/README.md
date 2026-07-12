# Scheduling in business days

Chain project tasks so each starts after the previous one finishes —
skipping weekends and holidays with `WORKDAY.INTL`.

**You'll need:** abax only.

## Run it

```sh
cd docs/examples/formulas/business-days
python run.py
```

## What you should see

```
 Design ( 5d) finishes 2026-09-09
  Build (10d) finishes 2026-09-23
   Test ( 4d) finishes 2026-09-29
   Ship ( 1d) finishes 2026-09-30

Whole project: 21.0 working days
```

## How it works

- Dates in abax are ISO strings (`"2026-09-01"`) — no serial-number
  arithmetic to learn.
- Each task's finish is
  `=WORKDAY.INTL(previous_finish, days, 1, D1:D2)`: weekend spec `1`
  means Saturday+Sunday off, and `D1:D2` holds the holidays (Labor Day
  and Thanksgiving here — note the Design task takes 5 working days but
  lands 8 calendar days out).
- `=NETWORKDAYS.INTL(start, end, 1, D1:D2)` counts the working days in
  the whole span — 21, not the 30 calendar days.
- Other weekend specs handle Fri/Sat weekends, single days off, or a
  custom `"0000011"` mask — see the
  [formula reference](../../../formula-reference.md).

## Next steps

- [Descriptive statistics](../descriptive-statistics/README.md) — the
  statistical function family.
- `DATEDIF`, `EDATE`, `EOMONTH` and friends are in the
  [formula reference](../../../formula-reference.md).
