"""Example abax macros.

Load with:  abax --macros macros/ macro list
Or drop this file in CONFIG_DIR/macros/ to have it loaded automatically.

Two kinds of extension are shown:
  * @macro            — a command that mutates the workbook via `ctx`
  * @register_function — a UDF callable inside formulas, e.g. =TAXED(A1)

The names `macro`, `register_function`, `flatten`, `numbers`, `as_number`,
`text`, `CellError`, and `RangeValue` are injected by the loader.
"""


@macro("totals")
def totals(ctx):
    """Append a SUM row beneath each used column of the active sheet."""
    n_rows, n_cols = ctx.sheet.used_bounds()
    if n_rows == 0:
        ctx.log("sheet is empty; nothing to total")
        return
    for c in range(n_cols):
        col_letter = _col(c)
        ctx.set(f"{col_letter}{n_rows + 1}", f"=SUM({col_letter}1:{col_letter}{n_rows})")
    ctx.recalc()
    ctx.log(f"added totals across {n_cols} column(s) in row {n_rows + 1}")


@macro("uppercase_headers")
def uppercase_headers(ctx):
    """Upper-case every cell in row 1 (the header row)."""
    _, n_cols = ctx.sheet.used_bounds()
    changed = 0
    for c in range(n_cols):
        ref = f"{_col(c)}1"
        raw = ctx.sheet.get_raw(*_rc(ref))
        if raw and not raw.startswith("="):
            ctx.set(ref, raw.upper())
            changed += 1
    ctx.log(f"upper-cased {changed} header cell(s)")


@register_function("TAXED")
def taxed(args):
    """=TAXED(amount, [rate]) — amount plus tax (rate default 0.08)."""
    nums = numbers([args[0]]) if args else []
    if not nums:
        return CellError("#VALUE!")
    rate = as_number(args[1]) if len(args) > 1 else 0.08
    return nums[0] * (1 + rate)


@register_function("REVERSE")
def reverse(args):
    """=REVERSE(text) — reverse a string."""
    return text(args[0])[::-1] if args else ""


# --- tiny A1 helpers so the macro file stays self-contained ---------------


def _col(idx):
    out = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def _rc(ref):
    i = 0
    while i < len(ref) and ref[i].isalpha():
        i += 1
    col = 0
    for ch in ref[:i].upper():
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return int(ref[i:]) - 1, col - 1
