# Built-in calculators

abax bundles a set of calculators that live beside the spreadsheet and can
exchange values with the grid. They're handy for a quick computation without
writing a formula, and the RPN and graphing models are faithful enough to be
enjoyable in their own right.

Open the calculator with `Ctrl+K` (*View → Calculator*), or "Show/hide
calculator" from the command palette. It opens as a floating window you can move
beside the grid; press `Ctrl+K` again to hide it.

See also: the [Desktop GUI guide](gui-guide.md), [Getting
started](getting-started.md), the [Formula reference](formula-reference.md),
and [Configuration](configuration.md). The docs index is [here](index.md).

## Choosing a model

The calculator window has a **Model** dropdown at the top. Pick from:

| Model | Kind | Notes |
| --- | --- | --- |
| Programmer (RPN) | RPN | Integer & bitwise math, base switching — **opens in hexadecimal** |
| Scientific (RPN) | RPN | Trig, `yˣ`, `1/x`, `f`/`g` shift keys |
| Financial (RPN) | RPN | Time-value-of-money keys |
| Graphing | Graphing | Home screen, `Y=` editor, graph, trace, table (offered in several skins) |
| Algebraic | Infix | Ordinary `2 + 3 × sin(30)` entry with scientific keys, `Ans`, and memory |

Whatever model is showing, you can type on your keyboard — the faceplate has
focus, so digits, operators, `Enter`, and `Backspace` go straight to it. You can
also click the keys with the mouse.

## RPN calculators

These are Reverse Polish Notation calculators with the classic four-level stack
(**X, Y, Z, T**), where X is the displayed value. Numbers always lift the stack
(automatic stack lift), so `3` `Enter` `4` `+` gives `7`, and an interleaved
entry like `3 4 + 5 *` evaluates to `35`.

Each key carries three legends: the white **primary**, the gold **f**
shift, and the blue **g** shift. Press `f` or `g` first to reach the shifted
function; the shift key glows while it's armed.

- **Scientific** — `√x`, `x²`, `1/x`, `yˣ`, `sin`/`cos`/`tan` (and inverses via
  `g`), `ln`/`log`, `eˣ`/`10ˣ`, `π`, `LSTx`, stack roll and swap, registers, and a
  DEG/RAD angle mode.
- **Programmer** — integer arithmetic, bitwise operations, shifts and rotates, a
  configurable word size, and base switching between hex, decimal, octal, and
  binary. It **opens in hexadecimal**, and the display shows the base letter
  (`h`/`d`/`o`/`b`) after the value.
- **Financial** — time-value-of-money keys.

On the programmer model, the hex digits `A`–`F` are typed with the lowercase keys
`a`–`f`.

### Faceplate style: vector or image

For the RPN models there's a second **Style** dropdown:

- **Vector** (the default) — a de-branded faceplate drawn entirely with Qt's
  painter: a dark two-tone body, sculpted key caps, the gold/blue shift legends,
  an LCD window, and a neutral badge. **No calculator artwork ships with abax.**
- **Image** — composites photographic faceplate art (a background plus per-key
  cap images, described by a Nonpareil KML) from an external folder. If you
  haven't configured one, abax falls back to the vector face automatically and
  flips the dropdown back to Vector.

Configuring photographic faceplate art is described under
[Photographic faceplate art](#photographic-faceplate-art) below.

## Graphing calculators

The graphing models are driven by one engine that renders a home screen, a `Y=`
function editor, a graph with a live **TRACE**
cursor, and a table — all on a procedurally-drawn faceplate with the blue **2nd**
legends printed above each key.

Highlights:

- **Home screen** — type an expression and press `Enter` to evaluate; recent
  entries scroll up the screen.
- **`Y=` editor** — define functions `Y1`…`Y6`; press `Enter` or the arrows to
  move between slots.
- **GRAPH / TRACE** — plot the defined functions; in TRACE, the left/right
  arrows move the cursor along a curve and up/down switch between functions.
- **ZOOM / WINDOW** — cycle standard / decimal / fit zoom.
- **MATH / STAT / APPS menus** — faithful tabbed menus; items that map to
  functions the evaluator supports paste their token onto the entry line.
- **MODE** toggles degrees/radians.

One skin uses a colour screen with coloured graph traces; the others use the
classic greenish mono LCD.

## The algebraic calculator

Selectable as the **Algebraic** model in the dropdown: instead of RPN, you build
an ordinary infix expression — `2 + 3 × sin(30)` — and press `=`. It has
the usual scientific keys (`sin`/`cos`/`tan`, `ln`/`log`, `sqrt`, `^`, `π`,
`e`, `%`), an `Ans` key that recalls the last result, and `M+`/`MR`/`MC` memory
keys, plus a Deg/Rad toggle. Like the other models it exposes its current value
to the cell bridge, so "Get from cell" / "Send to cell" work the same way.

## The calculator ↔ cell value bridge

Every model can move numbers to and from the active spreadsheet selection. At
the bottom of the calculator window:

- **⭱ Get from cell** — load the active cell's numeric value into the
  calculator. Shortcut: `Ctrl+Shift+G`. (If the cell isn't a number, the status
  bar says so.)
- **Send to cell ⭳** — write the calculator's current value into the active
  cell (or every cell of a selected range). Shortcut: `Ctrl+Shift+H`.

Both actions are also in the command palette ("Get cell value → calculator" and
"Send calculator value → cell").

Two details worth knowing:

- **Send fills the whole selection.** If you have a range selected, the value is
  written into *every* cell in it — a quick way to stamp one number across a
  block.
- **Send is undoable.** It's recorded as a single checkpoint, so `Ctrl+Z` puts
  the cells back the way they were.
- **Send respects the current base.** On the programmer RPN model, if you're
  working in hexadecimal, octal, or binary, the value lands in the cell as **bare
  digits** in that base — `FF`, `377`, `11111111` — rather than being converted
  to decimal (no `0x`/`0o`/`0b` prefix, so it stays compatible with other
  software). In decimal mode it sends a plain number. The digits match what's on
  the LCD, including the two's-complement bit
  pattern for negatives.

For the RPN keypad, "Get from cell" commits any digits you're partway through
typing before reading, so the number on the LCD is what gets used (not a stale X
register). Sending writes a whole decimal value as an integer, otherwise as a
precise decimal — or as a based literal when the programmer model isn't in
decimal (above).

## Photographic faceplate art

abax **ships no calculator artwork** — the de-branded vector faceplate is the
default and is always available with no setup. If you have your own photographic
faceplate assets, you can point abax at them so the RPN models render with image
art instead.

abax looks for an assets folder holding per-model subfolders (each with a
`background.png` and a `*.kml` layout), in this order:

1. An explicit **image folder** you set in *Tools → Calculator faceplates → Set
   image folder…* (saved in settings).
2. The **`ABAX_FACEPLATE_DIR`** environment variable, pointing at the same kind
   of assets root.
3. A local **`qrpn-voyager`** (or `qv`) checkout next to your working directory
   or the abax tree — under `qrpn/assets/voyager/<model>` — so contributors who
   have it handy get the art with no configuration.

abax only **reads** these files in place — it never bundles or copies them, and
it never draws any manufacturer trademark. If no usable assets are found, it quietly uses
the vector faceplate. After setting a folder, an open calculator
rebuilds so the new art takes effect immediately. Set the **Style** dropdown to
*Image* to use them.

See [Configuration](configuration.md) for where settings and the cache live.

## Calculator shortcuts

| Action | Shortcut |
| --- | --- |
| Show / hide calculator | `Ctrl+K` |
| Get cell value → calculator | `Ctrl+Shift+G` |
| Send calculator value → cell | `Ctrl+Shift+H` |

---

License: GPL-3.0-or-later.
