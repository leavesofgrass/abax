# Built-in calculators

abax bundles a set of calculators that live beside the spreadsheet and can
exchange values with the grid. They're handy for a quick computation without
writing a formula, and the RPN and graphing models are faithful enough to be
enjoyable in their own right.

Open the calculator with `Ctrl+K` (*View → Calculator*), or "Show/hide
calculator" from the command palette. It opens as a floating, non-modal window
you can move beside the grid; press `Ctrl+K` again to hide it. The calculator is
**not** opened automatically on launch — it appears on demand and remembers the
model and style you last used.

See also: the [Desktop GUI guide](gui-guide.md), [Getting
started](getting-started.md), the [Formula reference](formula-reference.md),
[Configuration](configuration.md), and the
[goal-seek example](examples/analysis/goal-seek/README.md) (tested script).
The docs index is [here](index.md).

## Choosing a model

The calculator window has a **Model** dropdown at the top. abax offers eight
concrete models across three families:

| Model | Family | Engine | Notes |
| --- | --- | --- | --- |
| Algebraic | Infix | `core/calc/algebraic.py` | Ordinary `2 + 3 * sin(30)` entry with `=`, scientific keys, `Ans`, and `M` memory |
| HP-12C | RPN (financial) | `core/calc/rpn12.py` | Four-level stack, TVM, bonds, depreciation, cash flows, statistics |
| HP-15C | RPN (scientific) | `core/calc/voyager.py` over `core/calc/rpn.py` | Trig/hyperbolics, `yˣ`, `1/x`, combinatorics, DEG/RAD/GRD, `f`/`g` shift |
| HP-16C | RPN (programmer) | `core/calc/rpn16.py` | Integer & bitwise math, base switching — **opens in hexadecimal** |
| TI-82 | Graphing | `core/calc/ti_engine.py` | Home screen, `Y=`, graph, trace, table (`RANGE` key label) |
| TI-83 Plus | Graphing | `core/calc/ti_engine.py` | As above (`WINDOW` key label, yellow 2nd) |
| TI-84 Plus | Graphing | `core/calc/ti_engine.py` | As above (blue accents) |
| TI-84 Plus CE | Graphing | `core/calc/ti_engine.py` | As above, but a **colour** LCD with coloured graph traces |

The model list (`_MODELS` in `abax/gui/calc/calculator_panel.py`) is ordered
Algebraic, then the three HP Voyager models, then the four TI graphing skins. The
**default model is the HP-16C**, and both the chosen model and faceplate style
persist across sessions (they're saved as `calc_model` / `calc_style` in
settings).

Whatever model is showing, you can type on your keyboard — the faceplate has
focus, so digits, operators, `Enter`, and `Backspace` go straight to it. You can
also click the keys with the mouse. Below the faceplate are the
**⭱ Get from cell** / **Send to cell ⭳** interop buttons and a **Hide ▾** button.

## RPN calculators (HP Voyager: 12C, 15C, 16C)

The three HP models are Reverse Polish Notation calculators with the classic
four-level stack (**X, Y, Z, T**), where X is the displayed value (`stack[0]`).
Numbers always lift the stack (automatic stack lift), so `3` `Enter` `4` `+`
gives `7`, and an interleaved entry like `3` `Enter` `4` `+` `5` `*` evaluates to
`35`. The three models share the same 4×10 Voyager button grid; only their
legend tables differ.

### The RPN stack model

- **`ENTER`** duplicates X upward (`T←Z, Z←Y, Y←X`, X unchanged) — or, if you
  were typing a number, it commits that number and lifts.
- A binary operator (`+ − × ÷`, `yˣ`, …) consumes X and Y, drops the stack
  (`Y←Z, Z←T`, T retained), and leaves the result in X.
- **Stack manipulation** available on all three: `x↔y` (swap X and Y), `R↓`
  (roll down), and — on the 15C/16C — `R↑` (roll up).
- **`LSTx`** recalls the value that was in X before the last operation
  (`last_x`), pushing it onto the stack. Every unary/binary op and the percent
  keys update `last_x`.
- **`CHS`** negates: it flips the sign of a number you're typing, or negates X
  if you aren't mid-entry.
- **Registers**: `STO` *n* / `RCL` *n* store and recall from numbered registers
  `R0`–`R9` (press `STO`/`RCL` then a digit key). An unset register recalls as
  `0`.

Each key carries up to three legends: the white **primary**, the gold **f**
shift, and the blue **g** shift. Press `f` or `g` first to reach the shifted
function; the shift key glows while it's armed, and pressing the same shift key
again disarms it. The `ON` key clears any armed shift.

### HP-15C — scientific

The scientific member. Its keypad (`core/calc/voyager.py`) drives the float
engine in `core/calc/rpn.py`:

- **Arithmetic / powers**: `+ − × ÷`, `yˣ` (power), `1/x`, `x²`, `√x`.
- **Logs / exponentials**: `LN`, `LOG` (base-10), `eˣ`, `10ˣ`.
- **Trigonometry**: `SIN`/`COS`/`TAN` and their inverses `SIN⁻¹`/`COS⁻¹`/`TAN⁻¹`
  (the `g`-shifted legends), honoring the current angle mode.
- **Hyperbolics**: the **`HYP`** (`f`) and **`HYP⁻¹`** (`g`) keys are *prefixes*.
  Press `HYP` then `SIN`/`COS`/`TAN` for `sinh`/`cosh`/`tanh`; press `HYP⁻¹` then
  `SIN`/`COS`/`TAN` for `asinh`/`acosh`/`atanh`. Hyperbolics operate on the pure
  value, independent of the DEG/RAD/GRD angle mode.
- **Combinatorics**: `Cy,x` (combinations) and `Py,x` (permutations), with
  `y = n`, `x = r`. They require non-negative integers with `r ≤ n`.
- **Constants / misc**: `π`, `ABS`, `INT` (truncate), `FRAC` (fractional part),
  `x!` (factorial), `%` (`Y·X/100`, leaving Y in place).
- **Angle mode**: `DEG` / `RAD` / `GRD` (gradians, where 400 grad = 2π). The
  mode affects `SIN`/`COS`/`TAN` and their inverses; the default is DEG.

The 15C's **statistics registers** work like the 12C's: `Σ+` / `Σ−` accumulate
(or remove) paired points, and the gold-shifted keys return the mean, sample
standard deviation, the linear-regression fit (`L.R.`) and a linear estimate with
the correlation coefficient (`lin est,r`). The engine also gained a
single-expression **`SOLVE`** (robust root finder) and **`∫`** (adaptive-Simpson
integration) — the same primitives that power [Goal Seek](data-analysis.md).

The keypad still prints legends for the full solver/matrix subsystem
(`SOLVE`, `∫`/`INTEGRATE`, `MATRIX`, `DIM`, `RESULT`) plus the shift/flag/index
keys (`SST`, `BST`, `P/R`, `PSE`, `DSE`, `ISG`, `TEST`, `SF`, `CF`, `F?`, `USER`,
`MEM`, `(i)`, `I`). Pressing one of those directly on the immediate-mode keypad
still reports a short note ("*needs program/solver memory (use the console)*")
rather than acting — that keypad has no solver/matrix memory of its own.

The **flow-control** keys, however (`GTO`, `GSB`, `LBL`, `RTN`, and the `x≤y` /
`x=0` conditional tests), are no longer inert: they are the vocabulary of the
[program runner](#keystroke-programs-hp-15c-style) described below, which records
them and executes them against the live RPN engine like the real HP-15C's program
mode.

### HP-16C — programmer

Integer RPN with word-size-masked, two's-complement arithmetic
(`core/calc/rpn16.py`). Every value is stored *unsigned* and masked to the
current word size; the display can interpret the high bit as a sign.

- **Base switching**: `HEX` / `DEC` / `OCT` / `BIN` select base 16 / 10 / 8 / 2.
  The model **opens in hexadecimal**. The display shows the value followed by the
  base letter — `h` / `d` / `o` / `b` (e.g. `FF h`, `-1 d`, `377 o`,
  `11111111 b`). In hex/octal/binary the *raw two's-complement bit pattern* is
  shown; in decimal the *signed* value is shown with a leading `-` when negative.
- **Digit entry**: hex digits `A`–`F` are typed with the lowercase keyboard keys
  `a`–`f`. A digit legend that isn't valid in the current base is rejected with a
  message.
- **Word size** (`WSIZE`, `f`-shifted `STO`): sets the bit width and re-masks
  every stack level, `last_x`, and every register. `eval_line` also accepts a
  bare `wsize <bits>` token.
- **Integer arithmetic**: `+ − × ÷` operate on the signed interpretation;
  division truncates toward zero.
- **Bitwise logic**: `AND`, `OR`, `XOR`, `NOT` (`NOT` is one's complement).
- **Single-bit shifts / rotates** (unary, act on X): `SL` (shift left), `SR`
  (shift right, logical), `RL` (rotate left), `RR` (rotate right).

#### Immediate bit/word operations

These 16C keys are wired to *real* operations (not stubs). Several are binary
(they consume both X and Y):

| Key | Kind | Effect |
| --- | --- | --- |
| `MASKL` | unary | Mask of the X most-significant bits set |
| `MASKR` | unary | Mask of the X least-significant bits set |
| `#B` | unary | Population count — number of 1 bits in X |
| `ABS` | unary | Absolute value (of the signed interpretation) |
| `ASR` | unary | Arithmetic shift right (replicates the sign bit) |
| `RMD` | binary | Remainder; sign follows the dividend (C truncation) |
| `1's comp` | unary | One's complement (`~X`) |
| `2's comp` | unary | Two's complement (negate) |
| `SB` | binary | Set bit number X within word Y |
| `CB` | binary | Clear bit number X within word Y |
| `B?` | binary | Test bit X of Y — leaves a `1`/`0` result on the stack |
| `RLn` | binary | Rotate word Y left by X bit positions |
| `RRn` | binary | Rotate word Y right by X bit positions |

`B?` is the immediate-mode analogue of the hardware's program-mode conditional:
instead of skipping an instruction it simply leaves the boolean result in X.

#### Programming-mode keys

The 16C keypad prints many keys that need program memory, index registers, or
flow control that the immediate-mode engine doesn't provide. These are collected
in a `_PROGRAM_KEYS` set and, when pressed *directly* on the keypad, report
*"programming-mode key (no program memory)"* rather than acting or erroring:

`GSB`, `GTO`, `LBL`, `RTN`, `R/S`, `SST`, `BST`, `DSZ`, `ISZ`, `P/R`, `PSE`,
`(i)`, `I`, `x<>(i)`, `x<>I`, `x<=y`, `x<0`, `x>y`, `x=0`, `x>0`, `x/=y`,
`x/=0`, `x=y`, `SF`, `CF`, `F?`, `CLR PRGM`, `MEM`.

The flow-control and conditional-test keys in that list (`GSB`, `GTO`, `LBL`,
`RTN`, and the `x<=y` / `x=0`-style comparisons) *do* run once recorded into a
keystroke program — see [Keystroke programs](#keystroke-programs-hp-15c-style)
above. The remaining index-register and flag keys (`(i)`, `I`, `SF`, `CF`, `F?`,
`DSZ`, `ISZ`, …) stay immediate-mode notes.

Other printed-but-unmodelled legends (e.g. the double-word `DBL` variants,
`LJ`, `UNSIGN`, `FLOAT`, `STATUS`, `WINDOW`, display-shift keys) report a plain
*"not implemented"* note.

### HP-12C — financial

The financial Voyager (`core/calc/rpn12.py`), driving the same float engine plus
five Time-Value-of-Money registers and delegating the heavier math to
`core/science/financial.py`. The HP cash-flow sign convention applies throughout:
money received is positive, money paid out is negative.

- **TVM keys**: `n`, `i`, `PV`, `PMT`, `FV`. Each key **stores** X into its
  register when you've just entered a number, or **solves** for that register
  from the other four (end-of-period payments) and shows the result in X. The
  rate `i` is a per-period percentage as entered.
- **Cash-flow / DCF**: `CF0` (initial flow), `CFj` (append a flow), `Nj` (repeat
  the last flow), then `NPV` (uses the rate in `i`) and `IRR`.
- **Bonds** (SIA, dated): `BOND PRICE` takes yield in `i`, coupon in `PMT`,
  settlement date in Y and maturity date in X; it leaves the clean price in X and
  accrued interest in Y. `BOND YTM` takes price in `PV`, coupon in `PMT`, and the
  same date placement, returning the yield.
- **Depreciation**: `DEPR SL` (straight-line), `DEPR SOYD` (sum-of-years-digits),
  and `DEPR DB` (declining-balance). Cost is read from `PV`, salvage from `FV`,
  life from `n`, and the target year from X; `DEPR DB` takes its factor (as a
  percent) from `i`, defaulting to 200% (factor 2).
- **Statistics** (`Σ+` / `Σ−` accumulator): `Σ+`/`Σ−` add/remove paired points,
  `mean`, `std dev` (sample), `lin est x`/`lin est y` (least-squares forecast),
  and `n!`.
- **Percents**: `%` (percent of a number), `Δ%` (percent change), `%T` (part as
  a percent of the total).
- **Dates**: `M.DY` / `D.MY` set the date-entry format; `ΔDYS` gives the days
  between two dates (both actual and 30/360), and `DATE` adds days to a date and
  reports the resulting weekday. Dates are keyed as `MM.DDYYYY` (or `DD.MMYYYY`).

For scripted or batch financial work, the same routines are importable from
`abax.core.science.financial` in the Python console.

### Keystroke programs (HP-15C style)

Beyond immediate-mode entry, the RPN keypads can **record and run a keystroke
program**, the way the real HP-15C's program mode does. The program subsystem
lives in `core/calc/program.py` (`Program` / `ProgramRunner` / `Step`); the Qt
run/step panel is `abax/gui/calc/program_panel.py` (`ProgramPanel`). It is
model-agnostic — it drives whatever RPN faceplate it's handed, so it works with
the 12C, 15C, and 16C keypads unchanged.

A program is an ordered list of **steps**. Each step is one of: a recorded
keypad button press; a raw engine token (a keypad-independent keystroke like `5`,
`+`, or `sqrt`); a `LBL` label marker; a `GTO` (unconditional jump to a label); a
`GSB` *gosub* (jump to a label after pushing a return address); an `RTN` (return
— a top-level `RTN` stops the program); or a **conditional test**. When a program
runs, the steps execute against the *existing* RPN engine, so every operation
does exactly what pressing the same keys by hand would do.

- **Conditional tests** follow HP's *do-if-true* convention: when the test is
  true the next step runs; when it's false the next step is **skipped**. A guarded
  loop is a test placed immediately before a `GTO`. The supported tests compare X
  against Y — `x≤y`, `x<y`, `x>y`, `x≥y`, `x=y`, `x≠y` — or X against zero —
  `x≤0`, `x<0`, `x>0`, `x≥0`, `x=0`, `x≠0` (`TESTS` in `program.py`). On the
  HP-16C the comparisons use each value's *signed* interpretation.
- **Bounded execution.** Every run is capped by a step budget (10 000 steps by
  default), so an accidental infinite loop like `LBL a … GTO a` terminates with a
  clear "possible infinite loop" error instead of hanging the UI.

The **program panel** (`ProgramPanel`) sits beside the faceplate and gives it the
usual HP program controls. Open it with the **Program ▸** toggle next to the
model picker (it appears for the HP models only), or from the command palette —
*Calculator program memory (record / run)…* — which opens the calculator with
the panel showing:

- **● Record** — arm recording; every key you then press on the faceplate is
  captured into program memory (and still executes live as you go).
- **Clear** — erase program memory (HP `f CLEAR PRGM`).
- **▶ Run** — execute the program from the top (HP `R/S`), bounded by the cap.
- **Step** — execute a single instruction (HP `SST`); the highlighted listing row
  is the program counter.
- **Reset PC** — rewind the program counter to the top.

The listing mirrors the program back in an HP `P/R`-style numbered display
(`001 …`). Note that pressing a flow-control key *directly* on the immediate-mode
keypad — outside the program panel — still just reports a short note; recording it
into a program is what makes `LBL`/`GTO`/`GSB`/`RTN` and the tests actually run.

### Faceplate style: image or vector

For the three HP models a second **Style** dropdown appears (it's hidden for the
Algebraic and TI models). The order in the dropdown is **Image** then **Vector**:

- **Image** — composites photographic faceplate art (a `background.png`, an
  optional `overlay.png` of printed legends, and per-key cap PNGs, described by a
  Nonpareil KML) from an *external* folder. **No calculator artwork ships with
  abax.** If no usable assets are found, abax silently falls back to the vector
  faceplate and flips the dropdown back to Vector.
- **Vector** — a de-branded faceplate drawn entirely with Qt's painter: a dark
  two-tone body, sculpted trapezoidal key caps, the gold/blue shift legends, an
  LCD phosphor window, and a neutral **qv** badge (the project's own mark, never
  a manufacturer trademark).

Because the default style is *Image*, a fresh install with no configured artwork
shows the vector face automatically. Configuring photographic faceplate art is
described under [Photographic faceplate art](#photographic-faceplate-art) below.

## Graphing calculators (TI-82/83/84)

The four TI skins are driven by one engine (`core/calc/ti_engine.py`) rendered on
a procedurally-drawn faceplate (`abax/gui/calc/ti_faceplate.py`) with the blue/
yellow **2nd** legends printed above each key. The 82, 83 Plus, and 84 Plus
share a greenish mono LCD; the **TI-84 Plus CE** uses a white colour panel with
coloured graph traces. The skins differ only cosmetically — case colour, model
name, accent colours, and the TI-82's `RANGE` vs. the others' `WINDOW` key label.

The engine models a 96×64 screen; with a one-pixel border it leaves a 94×62
usable plot area.

### Home screen

Type an expression and press `Enter` to evaluate. `Ans` recalls the last result;
recent entries scroll up the screen. Evaluation reuses `core/graphing.compile_expr`,
which sandboxes the namespace and treats a caret `^` as `**`. Any error surfaces
as the TI string `ERR: SYNTAX` rather than raising — no exception propagates.

### `Y=` editor

Press `Y=` to define functions `Y1`…`Y6` (the engine has ten slots Y1..Y0
internally, but the editor exposes the first six). `Enter` or the `►`/`◄` arrows
move between slots; the current slot's expression is committed when you leave it.

### GRAPH / TRACE, WINDOW / ZOOM

- **`GRAPH`** plots the defined functions.
- **`TRACE`** shows a live cursor: `◄`/`►` move it along a curve; `▲`/`▼` switch
  between defined functions. The read-out shows the function number and the X/Y
  under the cursor.
- **`WINDOW`** (or `RANGE` on the TI-82) resets to the standard `ZStandard`
  −10..10 box and switches to the graph.
- **`ZOOM`** cycles standard → decimal → fit: `ZStandard` (−10..10),
  `ZDecimal` (−4.7..4.7 by −3.1..3.1), and `ZoomFit` (fit Y to the defined
  functions over the current X window).

### TABLE

`TABLE` (the `2nd` legend on the `GRAPH`/`WINDOW` keys) shows a table of X and
each defined Y over a range of X values.

### MATH / STAT / APPS menus

`MATH`, `STAT`, and `APPS` open faithful tabbed menus (MATH has MATH/NUM/CPX/PRB
tabs; STAT has EDIT/CALC/TESTS; APPS lists the classic app names). Navigate tabs
with `◄`/`►`, items with `▲`/`▼`, and select with `Enter` or the item's number
key. Selecting an item that maps to a function the evaluator supports **pastes
its token** onto the entry line (e.g. `abs(`, `round(`, `³√(` → `cbrt(`,
`ˣ√` → `xroot(`, `nCr` → `comb(`, `nPr` → `perm(`, `!` → `factorial(`). Items the
evaluator can't compute (calculus, complex, random, list, regression, tests) are
**display-only** — selecting them just echoes the label as a message.

### ALPHA + letter variables

Press **`ALPHA`** then a key to type its green letter. `ALPHA` cycles through
three states: off → **ALPHA** (types one letter, then reverts) → **A-LOCK**
(stays on until you press `ALPHA` again). The letter map follows the TI-83/84
layout (`MATH`=A … `STO→`=X, `1`=Y, `2`=Z, `3`=θ). A **physical letter key** on
your keyboard also types the upper-case variable directly.

Store into a variable with the **`STO→`** key: it inserts a `->` arrow, and the
engine parses `<expr> -> V`. For example, `5` `STO→` `ALPHA` `A` becomes `5→A`
and stores 5 into `A`; recall `A` in later expressions. An **unset variable reads
as `0`**, like the hardware. Storing a value also updates `Ans`.

### MODE and other keys

- **`MODE`** toggles the trig unit between radians and degrees (the read-out
  shows `RAD` / `DEG`).
- **`QUIT`**, **`CLEAR`**, **`DEL`**, `(-)` for a leading minus, `π`, `e`,
  `x⁻¹`, `x²`, `√`, `^`, `SIN`/`COS`/`TAN` (and inverses), `LOG`/`10ˣ`,
  `LN`/`eˣ`, and the `X,T,θ,n` key (which types `X`).
- **`ENTRY`** (`2nd` `ENTER`) recalls the last home-screen entry for editing.

Several TI subsystems abax doesn't model report a short note instead of acting:
`STAT PLOT` (no plotting subsystem), `FORMAT`, `CALC` (graph-analysis menu),
`INS` (insert/overwrite), `PRGM` (no program memory), and `VARS` (recall not
modeled — store A–Z with `ALPHA` + `STO→` instead).

## The algebraic calculator

Selectable as the **Algebraic** model: instead of RPN, you build an ordinary
infix expression — `2 + 3 * sin(30)` — and press `=`. The engine
(`core/calc/algebraic.py`) tokenizes the string, converts it to RPN with the
shunting-yard algorithm, and evaluates that. It **never** calls Python's `eval`
on the raw string; only the whitelisted functions/constants (plus `Ans` and `M`)
resolve.

- **Operators**: `+ − * / ^` (and `**`), `%`, unary `−`/`+`, and parentheses.
  `^` is power and right-associative, so `2^3^2 = 512`; unary minus binds looser
  than `^`, so `-2^2 = -4`.
- **`%` is modulo, not percent-of.** `10 % 3` is `1`. A trailing-`%`
  percent-of-a-number shorthand is deliberately *not* supported.
- **Functions**: `sin`/`cos`/`tan`, `asin`/`acos`/`atan`, `sinh`/`cosh`/`tanh`,
  `ln`, `log` (base-10), `log2`, `sqrt`, `cbrt`, `exp`, `abs`, `floor`, `ceil`,
  `round`, `fact`. (The button grid surfaces `sin`/`cos`/`tan`, `ln`, `log`,
  `sqrt`; the others are available by typing.)
- **Constants**: `pi`, `e`, `tau`.
- **`Ans`** recalls the last result; when a result is showing, starting with an
  operator continues from `Ans`, while a digit begins a fresh expression.
- **Memory**: `M+` adds the current value to `M`, `MR` recalls `M` into the
  expression, `MC` clears `M`.
- **Deg/Rad**: the `Deg` toggle switches trig between degrees and radians; the
  mode is shown next to the value and persists across sessions (`calc_degrees`).

On any error the display shows `Error` and `Ans` is left unchanged. Like the
other models it exposes its current value to the cell bridge, so "Get from cell"
/ "Send to cell" work the same way — and it sends the *currently shown/typed*
value, not just the last `Ans`.

## The calculator ↔ cell value bridge

Every model can move numbers to and from the active spreadsheet selection. At
the bottom of the calculator window:

- **⭱ Get from cell** — load the active cell's numeric value into the
  calculator. Shortcut: `Ctrl+Shift+G`. It opens the calculator first if it's
  hidden. (If the cell isn't a number, the status bar says so.)
- **Send to cell ⭳** — write the calculator's current value into the active
  cell (or every cell of a selected range). Shortcut: `Ctrl+Shift+H`. If the
  calculator isn't open, the status bar prompts you to press `Ctrl+K`.

Both actions are also in the command palette ("Get cell value → calculator" and
"Send calculator value → cell") and on the **View** menu.

Details worth knowing:

- **Send fills the whole selection.** If you have a range selected, the value is
  written into *every* cell in it — a quick way to stamp one number across a
  block. The status bar reports the anchor cell plus how many more were written.
- **Send is undoable.** It's recorded as a single checkpoint ("calculator ->
  cell"), so `Ctrl+Z` puts the cells back the way they were.
- **Send re-anchors and scrolls into view.** After writing, the target cell
  becomes the current cell (for a single-cell send) and is scrolled into view, so
  the value stays visible even if the floating calculator overlaps the grid, and
  a subsequent send has a valid anchor.
- **Send respects the current base.** On the HP-16C, if you're working in
  hexadecimal, octal, or binary, the value lands in the cell as **bare digits**
  in that base — `FF`, `377`, `11111111` — rather than converted to decimal (no
  `0x`/`0o`/`0b` prefix, so it stays compatible with other software). The digits
  match what's on the LCD, including the two's-complement bit pattern for
  negatives. In decimal mode it sends a plain number.

For the RPN keypads, "Get from cell" and "Send to cell" both **commit any digits
you're partway through typing** before reading, so the number on the LCD is what
gets used — not a stale X register. Sending writes a whole value as an integer,
otherwise as a precise decimal (or as a based literal when the programmer model
isn't in decimal, above). "Get from cell" loads the value by pushing it onto the
stack (as an integer on the 16C, matching its word size).

## Keyboard and numpad input

Whichever model is showing has keyboard focus, so you can drive it entirely from
the keyboard:

- **HP models** map the digit keys, `+ − * /`, and `.` from both the main
  keyboard and the numeric keypad; `Enter`/`Return` is `ENTER` and `Backspace`
  is the delete/`CLx` key. On the HP-16C, `a`–`f` type the hex digits `A`–`F`.
- **TI models** accept digits, `. + - * / ^ ( )`, `x`/`X` (the graphing
  variable), `Enter`, `Backspace`, and the arrow keys; a physical letter key
  types the corresponding upper-case A–Z variable on the home screen or in the
  `Y=` editor.
- **Algebraic** accepts digits, `. + - * / ^ ( ) %`, `Enter`/`=` to evaluate,
  `Backspace` to delete, and `Esc` to clear.

The floating calculator window is created once and reused; it defaults to a
compact 380×660 layout that sits comfortably beside the grid.

## Photographic faceplate art

abax **ships no calculator artwork** — the de-branded vector faceplate is always
available with no setup. If you have your own photographic faceplate assets, you
can point abax at them so the HP models render with image art instead.

abax looks for an assets folder holding per-model subfolders (each with a
`background.png` and a `*.kml` layout), in this order:

1. An explicit **image folder** you set in *Tools → Calculator faceplates → Set
   image folder…* (saved in settings as `faceplate_assets_dir`). abax checks both
   `<folder>/<model>` and `<folder>` itself.
2. The **`ABAX_FACEPLATE_DIR`** environment variable, pointing at the same kind
   of assets root.
3. A local **`qrpn-voyager`** (or `qv`) checkout next to your working directory
   or the abax tree — under `qrpn/assets/voyager/<model>` — so contributors who
   have it handy get the art with no configuration.
4. Assets fetched into abax's cache (via *Tools → Fetch…*, when available).

A usable model directory must contain a `background.png` and at least one `*.kml`
file. abax only **reads** these files in place — it never bundles or copies them,
and it never draws any manufacturer trademark. If no usable assets are found, it
quietly uses the vector faceplate. After setting a folder, an open calculator
rebuilds so the new art takes effect immediately. Set the **Style** dropdown to
*Image* to use them.

See [Configuration](configuration.md) for where settings and the cache live.

## Calculator shortcuts

| Action | Shortcut |
| --- | --- |
| Show / hide calculator | `Ctrl+K` |
| Get cell value → calculator | `Ctrl+Shift+G` |
| Send calculator value → cell | `Ctrl+Shift+H` |

RPN shift and prefix keys (mouse or on-screen): `f` / `g` arm the gold/blue
shift; on the 15C, `HYP` / `HYP⁻¹` prefix `SIN`/`COS`/`TAN`. On the TI models,
`2nd` arms the blue/yellow legend and `ALPHA` (or `ALPHA` twice for A-LOCK)
arms letter entry.

---

License: GPL-3.0-or-later.
