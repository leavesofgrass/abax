# Conditional formatting

Conditional formatting colours cells automatically based on what they contain —
so failing scores go red, the top ten deals stand out, duplicates light up, and
a column reads as a heat-map. Rules are defined once, stored **per sheet**, and
saved in the workbook, so they travel with the file and re-apply every time it
opens.

See also: [GUI guide](gui-guide.md) (cell styles, number formats) · [Data &
analysis tools](data-analysis.md) · [Formula reference](formula-reference.md) ·
[Python console](python-console.md) (scripting rules).

## Opening the dialog

*Format → Conditional format…* opens the rule builder. The form **reshapes
itself to the rule you pick** — it shows only the fields that rule needs (a
value, two values, a count, a percentage, a pattern, or colours), each with a
one-line description — so the long list of rule types stays approachable.

1. **Range** — defaults to your current selection (e.g. `B2:B200`); edit it if
   you want.
2. **Condition** — choose a rule kind (see the reference below).
3. Fill in the value(s), pick a **fill colour** (or enter **CSS** for a richer
   style), and click **OK**. The rule applies immediately.

Remove every rule on the sheet with *Format → Clear conditional formats*.

## How a rule works

- A rule colours cells **within its range** whose value matches its condition.
- **Colour or CSS.** A plain rule paints a background fill. Any match-based rule
  can instead carry a small **CSS declaration** to set text colour, bold,
  italic, underline, and/or background together (see [CSS styling](#css-styling)).
- **Overlapping rules layer.** When more than one rule touches a cell, their
  styles combine — a fill from one rule and bold red text from another apply
  together — with **later rules winning** on any direct conflict (e.g. two fills).
- **Range-aware kinds** (colour scales, ranking, above/below average,
  duplicate/unique) look at the *whole range* to decide each cell — the min/max,
  the average, a cut-off, or how often a value repeats.
- Rules render in the **GUI** (true cell colours) and in the **TUI** (a
  nearest-ANSI approximation of the fill).

## Rule reference

| Condition | Highlights… | You provide |
|-----------|-------------|-------------|
| **Greater than** / **Less than** / **≥** / **≤** | numbers on one side of a threshold | a value |
| **Equal to** / **Not equal to** | cells equal (or not) to a value | a number, or text (case-insensitive) |
| **Between** | numbers within an inclusive range | low + high values |
| **Text contains** | text containing a substring | text (case-insensitive) |
| **Text begins with** / **Text ends with** | text with a given prefix / suffix | text (case-insensitive) |
| **Matches regex** | text matching a regular expression | a pattern (case-sensitive; `(?i)` for insensitive) |
| **Is blank** / **Is not blank** | empty / non-empty cells | — |
| **Duplicate values** / **Unique values** | values that repeat / appear once in the range | — |
| **Above average** / **Below average** | numbers above / below the range mean | — |
| **Top N items** / **Bottom N items** | the N largest / smallest numbers (ties at the cut-off included) | a count |
| **Top N%** / **Bottom N%** | the top / bottom slice by value | a percentage |
| **2-colour scale** | a gradient from a min colour to a max colour | min + max colours |
| **3-colour scale** | a min → midpoint → max gradient | min + mid + max colours |

Numbers ignore blanks, text, booleans, and error cells; text rules ignore error
cells. Rankings and averages are computed over the numeric cells in the range.

## Worked examples

### Comparisons

- **Flag failing scores** — range `B2:B200`, *Less than*, value `60`, red fill.
- **Highlight amounts in a band** — range `D2:D500`, *Between*, low `1000`,
  high `5000`, yellow fill.
- **Mark a specific status** — range `F2:F200`, *Equal to*, value `Overdue`
  (text match is case-insensitive), orange fill.

### Text and regex

- **Find a keyword** — range `A2:A1000`, *Text contains*, text `error`.
- **Phone numbers** — range `C2:C500`, *Matches regex*, pattern
  `^\d{3}-\d{4}$` (three digits, a dash, four digits).
- **Case-insensitive prefix** — *Matches regex*, pattern `(?i)^err` to catch
  `ERR`, `Err`, `error`, … at the start of the text.
- **Emails** — *Matches regex*, pattern `@` (contains an at-sign) or a stricter
  `^[^@\s]+@[^@\s]+\.[^@\s]+$`.

> Regex matching is **case-sensitive** by default — prefix the pattern with
> `(?i)` for case-insensitive. An **invalid** pattern simply never matches
> (nothing is coloured) rather than raising an error.

### Duplicates and ranking

- **Spot duplicate SKUs** — range `A2:A1000`, *Duplicate values*, amber fill;
  every value that appears more than once is highlighted (case-insensitive).
- **Top 10 deals** — range `D2:D500`, *Top N items*, count `10`. Ties at the
  cut-off are all included (Excel-style), so you may see a few more than ten.
- **Bottom 25%** — range `E2:E200`, *Bottom N%*, percent `25`.
- **Above-average performers** — range `C2:C100`, *Above average* (no value —
  abax reads the range's mean for you), green fill.

### Colour scales (heat-maps)

- **Two-colour heat-map** — range `E2:E200`, *2-colour scale*, min = white,
  max = green; every value is shaded on the gradient between its column's
  smallest and largest number.
- **Diverging three-colour** — range `E2:E200`, *3-colour scale*, min = blue,
  midpoint = white, max = red — ideal for values that are meaningfully high or
  low around a centre.

## CSS styling

Every match-based rule (all but the colour scales) has an optional **Style
(CSS)** field. Fill it in to apply a full style instead of just a background:

```css
color: white; background: #c00; font-weight: bold
```

Understood properties:

| Property | Effect | Example values |
|----------|--------|----------------|
| `color` | text colour | `#fff`, `#ff0000`, `navy` |
| `background` / `background-color` | fill colour | `#c00`, `yellow` |
| `font-weight` | bold when `bold` or ≥ `600` | `bold`, `700` |
| `font-style` | italic | `italic` |
| `text-decoration` | underline | `underline` |

Colours may be `#rgb`, `#rrggbb`, or a basic CSS colour name (`red`, `lime`,
`navy`, `teal`, `orange`, …). Unknown properties and unrecognised colours are
ignored, so a partial or mistyped declaration still applies what it can.

Because [overlapping rules layer](#how-a-rule-works), you can compose effects —
e.g. a *2-colour scale* for the background plus a separate *Matches regex* rule
whose CSS is `font-weight: bold; color: #900` to bold-and-redden the cells that
also match a pattern.

## Performance

The grid evaluates rules **lazily, per painted cell, and caches the result** for
the current refresh, so a rule spanning tens of thousands of cells is cheap —
only the cells actually on screen are ever coloured. Range-aware rules do **one**
range scan per refresh, cached and reused across the viewport. For workbooks
large enough to page cells to disk, see the windowed cell store in
[Configuration](configuration.md).

## Scripting rules

Conditional-format rules are plain data on the sheet (`sheet.cond_rules`), so
you can add them from the [Python console](python-console.md) or a
[macro](macros-and-scripting.md) — handy for applying the same rules across many
sheets:

```python
>>> from abax.core.format.condformat import CondRule
>>> sheet().cond_rules.append(
...     CondRule(range="A1:A1000", kind="top_n", value=10, color="#a6e3a1"))
>>> sheet().cond_rules.append(
...     CondRule(range="B1:B1000", kind="regex", value=r"(?i)fail",
...              css="color: white; background: #c00; font-weight: bold"))
>>> refresh()   # repaint with the new rules
```

A `CondRule` takes `range`, `kind` (any condition token from the reference —
`">"`, `"between"`, `"contains"`, `"regex"`, `"top_n"`, `"above_avg"`,
`"duplicate"`, `"colorscale"`, `"colorscale3"`, …), the `value` / `value2` a
kind needs, a `color` fill, and an optional `css` string. Rules serialize with
the workbook automatically.

## See also

- [GUI guide](gui-guide.md) — cell styles, number formats, and the rest of the grid.
- [Data & analysis tools](data-analysis.md) — descriptive stats, pivots, and reshaping.
- [Formula reference](formula-reference.md) — the functions used in the examples above.
- [Python console](python-console.md) · [Macros & scripting](macros-and-scripting.md) — scripting rules across sheets.
