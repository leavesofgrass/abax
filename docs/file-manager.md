# File manager

A dual-pane file manager modeled on **Worker** and **Directory Opus**, for
managing files without leaving abax. Open it from *Tools → File manager* or with
`Ctrl+Shift+F` (also in the command palette).

## Layout

Two independent panes sit side by side, each with an address bar, an **Up**
button, and a sortable file table (name / size / modified). The pane you last
clicked in is the **active** pane; file operations act on its selection with the
**other** pane as the target — the classic two-pane workflow (copy from the active
pane into the other).

- Double-click a folder to enter it; **Up** goes to the parent; type a path in the
  address bar and press Enter to jump.
- Multi-select rows with `Ctrl`/`Shift` click.

## Operations (toolbar)

| Button | Action |
|---|---|
| **Refresh** | re-read both panes |
| **New folder** | create a folder in the active pane |
| **Rename** | rename the selected item |
| **Copy →** / **Move →** | copy or move the selection into the other pane (auto-renames on name clash) |
| **Delete** | delete the selection (files and folders; confirms first) |
| **Zip** / **Tar.gz** / **7z** | compress the selection to a `.zip`, `.tar.gz`, or `.7z` archive |
| **Extract** | extract the selected archive into the other pane (path-traversal safe) |
| **Open in archive** | list a `.zip`/`.tar`/`.7z`'s contents and open a supported file (CSV, Excel, Parquet, ODS, JSON/`.abax`, …) straight into the grid |
| **Convert** | open the [batch file-conversion](file-formats.md#converting-files) dialog pre-filled with the selection — tabular formats via the engine, documents (Word/HTML/Markdown/…) via pandoc |
| **Find** | recursive search from the active folder |

Archive creation supports `.zip`, `.tar`, `.tar.gz`/`.tgz`, `.tar.bz2`,
`.tar.xz`, and **`.7z`**. Extraction rejects any member that would escape the
destination directory (the "zip-slip" / "tar-slip" guard).

**`.7z` support** needs the optional **`py7zr`** package (`pip install abax[sevenzip]`;
it's in the `thin` and `all` feature sets). Without it,
`.zip`/`.tar` still work and the 7z actions report a clear "install `abax[sevenzip]`"
message. **Open in archive** extracts the chosen member to a temporary file and
loads it like any other spreadsheet — so you can open a CSV or workbook from
inside a `.zip`/`.tar`/`.7z` without unpacking the whole archive first.

## Find

**Find** searches recursively from the active folder by name pattern (shell
wildcards like `*.py`) and, optionally, by **file contents** (a substring; content
matches show the line). Double-click a result to jump to its folder with the file
selected.

## Command buttons (configurable)

Below the panes is a row of **command buttons** that run shell commands — the
signature Worker / Directory Opus feature, in Python instead of Lua. A button's
command is a template with placeholders filled from the current context:

| Placeholder | Expands to |
|---|---|
| `{dir}` | active pane's directory |
| `{dest}` | the other pane's directory |
| `{path}` | first selected path |
| `{name}` / `{stem}` / `{ext}` | its base name / stem / extension |
| `{sel}` | every selected path, space-joined and quoted |

Click **+ Add…** to define your own (label + command); it's saved in your settings
(`fm_buttons`) and appears every session. Command output shows in a non-modal pane
at the bottom. A command can be a shell one-liner or, naturally, `python -c …`.

Examples: `git status -s` (runs in `{dir}`), `echo {path}`, `open {path}`,
`ffmpeg -i {path} {stem}.mp3`.

The file operations, archiving, search, and button model are all pure-stdlib
(`core/fileops.py`, `core/archive.py`, `core/filesearch.py`, `core/fmbuttons.py`),
so they're scriptable from the Python console too.
