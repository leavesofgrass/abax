# Conditional formatting from a script

Regex rules, CSS styling, top-N and below-average highlighting — the
same rules the GUI dialog builds, created headlessly and saved with the
workbook.

**You'll need:** abax only.

## Run it

```sh
cd docs/examples/analysis/conditional-formatting
python run.py
```

## What you should see

```
C2  88           -> fill #2e7d32
B3  BLOCKED      -> fill #c62828, text #ffffff, bold
C3  35           -> fill #ff8f00
C4  72           -> fill #2e7d32
B5  blocked      -> fill #c62828, text #ffffff, bold
C5  41           -> fill #ff8f00
C6  95           -> fill #2e7d32
C7  60           -> fill #ff8f00

Saved out/formatted.abax — open it to see the colours:
  abax out/formatted.abax
```

## How it works

- A `CondRule` is range + kind + value: `kind="regex"` with
  `value="(?i)blocked"` matches any case of "blocked".
- The regex rule uses `css=` instead of a plain fill — white bold text on
  red, exactly like typing that CSS in the GUI dialog.
- `kind="top_n"` (value 3) and `kind="below_avg"` are *range-aware*: they
  need one scan of the whole range, which `scale_context()` precomputes
  once so `style_at()` stays cheap per cell — the same pattern the GUI
  grid uses on every repaint.
- Rules live on `sheet.cond_rules` and persist inside the `.abax` file;
  opening `out/formatted.abax` shows the colours in the grid.

## Next steps

- The [conditional-formatting guide](../../../conditional-formatting.md)
  documents every rule kind (comparisons, between, contains, duplicates,
  colour scales, …) with worked examples.
- In the GUI: *Format → Conditional formatting…*.
