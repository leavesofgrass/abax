# Terminal

abax has an **in-app system terminal** so you can run shell commands — `git`,
`grep`, `python`, your own scripts — without leaving the workbook. Crucially, abax
hands the shell a set of **`$ABAX_*` environment variables describing the current
selection**, so a command can see and act on the cells you have highlighted.

See also: [Python console](python-console.md) (for driving the sheet *in* Python)
· [Command-line interface](cli.md) · [Macros & scripting](macros-and-scripting.md)
· [File manager](file-manager.md).

> **Security.** The terminal runs shell commands with **your full user
> privileges**, so it is gated behind the same one-time **consent prompt** as the
> [Python console](python-console.md) and macros. Only run commands you understand.
> See [Macros & scripting → security](macros-and-scripting.md) for the isolation
> model.

## Opening the terminal

| Surface | How |
|---------|-----|
| **GUI** | **View → Terminal** (`` Ctrl+` ``), the toolbar "Terminal" button, or the command palette (*Terminal…*). It docks at the bottom; **View → Open default workspace** places it beside the [Python console](python-console.md). |
| **TUI** | `:!<command>` runs a single command, e.g. `:!ls -la` or `:!git status`. |

The GUI prefers a **true PTY terminal** — a full colour terminal where interactive
programs (`vim`, `htop`, `ssh`, a Python REPL) work normally. If a PTY back-end
isn't available it falls back to a simpler **line terminal** that runs one command
at a time and prints its output (this fallback tracks `cd`/`pwd` itself and applies
a 30-second per-command timeout).

## The `$ABAX_*` selection context

When the terminal starts (GUI) or a `:!` command runs (TUI), abax exports the
current selection as environment variables the command can read:

| Variable | Value |
|----------|-------|
| `ABAX_ACTIVE_CELL` | the top-left cell in A1 notation, e.g. `B2` |
| `ABAX_SELECTION_RANGE` | the selection as `B2:D5` (or bare `B2` for a single cell) |
| `ABAX_SELECTION_JSON` | the **computed** values as a compact one-line JSON 2-D array |
| `ABAX_SELECTION_TSV` | the same block as tab-separated **raw** text (one row per line) |
| `ABAX_SELECTION_TRUNCATED` | `1` — present only when the selection exceeded 10,000 cells and the JSON/TSV were capped |

Two things worth knowing:

- **The context is captured when the GUI terminal starts.** Select your data
  *first*, then open the terminal (or reopen it to refresh after changing the
  selection).
- **In the TUI, `:!` exports the single active cell**, not a multi-cell selection —
  `ABAX_SELECTION_RANGE` is the cell under the cursor and the TSV/JSON hold just
  that one value.

### Referencing the variables per platform

The PTY runs your default shell, so use that shell's syntax:

| Shell | Read a variable |
|-------|-----------------|
| bash / zsh / sh (Linux, macOS) | `"$ABAX_SELECTION_TSV"` |
| PowerShell (Windows) | `$env:ABAX_SELECTION_TSV` |
| cmd.exe (Windows) | `%ABAX_SELECTION_RANGE%` |

`ABAX_SELECTION_JSON` is a single line (safe to pipe anywhere); `ABAX_SELECTION_TSV`
contains real newlines, so it's most useful piped into a tool, as below.

## Recipes (bash / zsh)

**See what's selected:**

```sh
echo "$ABAX_SELECTION_RANGE"          # e.g. B2:D5
echo "$ABAX_SELECTION_TSV" | column -t   # pretty-print the block
```

**Count the selected rows:**

```sh
echo "$ABAX_SELECTION_TSV" | wc -l
```

**Save the selection to a file** (TSV or JSON):

```sh
echo "$ABAX_SELECTION_TSV"  > selection.tsv
echo "$ABAX_SELECTION_JSON" > selection.json
```

**Sum the selected numbers with a Python one-liner** (works without leaving the
terminal, and without any optional deps):

```sh
echo "$ABAX_SELECTION_JSON" | python -c "import sys, json; \
d = json.load(sys.stdin); \
print(sum(x for row in d for x in row if isinstance(x, (int, float))))"
```

**Filter the block with `jq`** (if installed) — e.g. the first row:

```sh
echo "$ABAX_SELECTION_JSON" | jq '.[0]'
```

**Feed the selection to any tool** that reads TSV/CSV on stdin — sort, awk, a
plotting script, `csvlook`, etc.:

```sh
echo "$ABAX_SELECTION_TSV" | sort -t$'\t' -k2 -n     # sort rows by column 2
```

## Working with the files around your workbook

The terminal opens in a normal working directory, so it doubles as a project shell:

```sh
pwd
ls -la
git status
python analyze.py data.csv          # run a script that lives beside your data
wc -l < big.csv                     # how many rows does that CSV have?
```

Combine the two: write the selection out, process it with an external tool, then
read the result back in via **File → Open** or the [Python console](python-console.md):

```sh
echo "$ABAX_SELECTION_TSV" > /tmp/sel.tsv
some-model-tool --input /tmp/sel.tsv --output /tmp/scored.csv
# then: File -> Open /tmp/scored.csv, or in the console: df_to_sheet(pd.read_csv('/tmp/scored.csv'), 'F1')
```

## TUI: `:!`

In the terminal UI, `:!<command>` runs one shell command and shows a trimmed line
of its output on the status line:

```
:!echo $ABAX_ACTIVE_CELL
:!git log --oneline -5
:!wc -l < data.csv
```

For interactive programs or longer sessions, use the GUI terminal (a real PTY) or
suspend abax and use your own shell.

## Terminal vs. Python console

Reach for the **terminal** when the tool you want already exists as a shell command
(`git`, `grep`, `ffmpeg`, a model runner) and you want to feed it the selection.
Reach for the **[Python console](python-console.md)** when you want to manipulate
the *sheet itself* — read/write cells, pandas, SQL — from inside abax.
