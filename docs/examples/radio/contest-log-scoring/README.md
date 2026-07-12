# Score a contest log

Feed a QSO log to abax's contest engine: duplicate detection per
band/mode, per-QSO points, and running totals — the machinery behind the
`ISDUPE` / `QSOPOINTS` formula functions and the POTA/SOTA dialog.

**You'll need:** abax only.

## Run it

```sh
cd docs/examples/radio/contest-log-scoring
python run.py
```

## What you should see

```
K7ABC   20M  CW    1 pt   running: 1 QSOs / 1 pts
N0XYZ   20M  SSB   1 pt   running: 2 QSOs / 2 pts
K7ABC   40M  CW    1 pt   running: 3 QSOs / 3 pts
K7ABC   20M  CW    DUPE   running: 3 QSOs / 3 pts
W1AW    15M  CW    1 pt   running: 4 QSOs / 4 pts
N0XYZ   20M  SSB   DUPE   running: 4 QSOs / 4 pts
VE3DEF  20M  FT8   1 pt   running: 5 QSOs / 5 pts

5 QSOs, 2 dupes, 5 points -> score 5
```

(FT8 is normalized to its DATA mode category in the scored rows.)

## How it works

- A log is just a list of dicts with `CALL` / `BAND` / `MODE` keys —
  ADIF-style field names are recognized case-insensitively.
- `score_log(log, "generic")` walks the log once: working the same
  station again on the *same band and mode* is a dupe (0 points);
  a new band or mode counts fresh — K7ABC on 40m scores after 20m.
- The result carries per-row detail (`is_dupe`, `points`,
  `running_qsos`) plus totals and a final `score`.
- Other presets change the rules — points by mode, multipliers —
  via `ruleset(name)`; `available_rulesets()` lists them.

## Next steps

- Inside a sheet, the same engine powers
  `=ISDUPE(...)` and `=QSOPOINTS(...)` — see the
  [RF toolkit guide](../../../rf-toolkit.md) for the logging workflow,
  the activation dialog, and ADIF import.
- 60+ RF functions (link budget, VSWR, Maidenhead grid, band plan) are
  in the [formula reference](../../../formula-reference.md).
