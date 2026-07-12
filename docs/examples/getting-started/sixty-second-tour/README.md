# The sixty-second tour

What to press in your first minute inside the abax GUI. **Nothing to run
here** — this is a walkthrough; launch the app and follow along.

**You'll need:** the GUI installed — `pipx install "abax[all]"` (or
`pip install "abax[gui]"`), then run `abax`.

## The first minute

1. **Move**: arrow keys walk the grid; vim keys work too (`h j k l`,
   `g`/`G`, `/` to search).
2. **Type**: just start typing in any cell and press `Enter`. Numbers,
   text, and ISO dates (`2026-07-12`) are recognized automatically.
3. **A formula**: type `=SUM(A1:A5)` — anything starting with `=` computes.
   While you type, function names autocomplete and a tooltip shows the
   current argument.
4. **The command palette**: press `Ctrl+Shift+P` (or just `:` on the
   grid). Every action in the app is in there — start typing to filter.
5. **Help**: `F1` lists the keyboard shortcuts. *Help → Documentation
   (online)* opens the full manual.
6. **Save**: `Ctrl+S` writes wherever the extension says — `.abax`
   (native), `.csv`, `.xlsx`, `.md`, …

## Worth knowing on day one

- **Themes**: *View → Theme* — twelve presets (Obsidian, Dracula, Tokyo
  Night, Gruvbox Dark, Monokai, Nord, Solarized, CRT green/amber,
  High-contrast, Light, Dark One) with a live preview.
- **The RPN calculator**: `Ctrl+K` — an HP-style keypad that can pull the
  active cell onto its stack and write results back.
- **The Python console**: `Ctrl+Shift+Y` — a REPL wired to the live
  workbook.
- **The file manager**: `Ctrl+Shift+F` — a dual-pane browser with
  archiving and search.
- **Recalculate**: `F9` (matters when calculation mode is manual).

## Next steps

- [Your first workbook](../first-workbook/README.md) — build a sheet from
  Python instead.
- The [GUI guide](../../../gui-guide.md) covers every menu, and the
  [getting-started guide](../../../getting-started.md) the install options.
