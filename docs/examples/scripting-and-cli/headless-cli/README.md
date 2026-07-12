# The headless CLI: view, get, convert, profile

Use abax with no screen at all — print a sheet in a terminal, compute
one cell, convert formats, and profile slow formulas. Ideal for
pipelines and cron jobs.

**You'll need:** abax on your PATH (`pipx install "abax[all]"` puts the
`abax` command there; `python -m abax` is always equivalent).

## Run it

```sh
cd docs/examples/scripting-and-cli/headless-cli
python run.py
```

The script generates `out/sales.csv` and then drives the CLI in-process;
each block of output is exactly what the shell command in its `$` line
prints.

## What you should see

```
$ abax view out/sales.csv
  | A       | B     | C     | D
-------------------------------------
1 | Product | Units | Price | Revenue
2 | Widget  | 10    | 2.5   | 25
3 | Gadget  | 4     | 11    | 44
4 | Doodad  | 25    | 0.8   | 20
5 | TOTAL   |       |       | 89

$ abax get out/sales.csv D5
89

$ abax convert out/sales.csv out/sales.md
converted out\sales.csv -> out\sales.md
| Product | Units | Price | Revenue |
| :------ | :---- | :---- | :------ |
| Widget  | 10    | 2.5   | 25      |
...

$ abax profile out/sales.csv --limit 3
  #  Cell       Time (ms)  Formula
----------------------------------
  1  sales!D2      0.0747  =B2*C2
  2  sales!D5      0.0395  =SUM(D2:D4)
  3  sales!D3      0.0260  =B3*C3
```

## How it works

- Formulas travel inside CSVs: the generated file's `Revenue` column is
  `=B2*C2`, and every subcommand computes it on load.
- `view` prints any supported format as a table; `get FILE D5` computes
  a single cell — perfect for shell scripts
  (`total=$(abax get sales.csv D5)`).
- `convert` routes by extension — the same file becomes a GitHub
  Markdown table, `.xlsx`, `.ipynb`, or a native `.abax`.
- `profile` times every formula cell and ranks the slowest — your first
  stop when a big workbook feels sluggish.
- More subcommands: `sql`, `diff`, `pipe` (stream stdin into a range),
  `macro run`, `fetch`, `doctor` — see the [CLI guide](../../../cli.md).

## Next steps

- The in-app [terminal](../../../terminal.md) exports your current
  selection to shell commands as `$ABAX_*` variables.
- [Macros & scripting](../../../macros-and-scripting.md) for automation
  that edits workbooks.
