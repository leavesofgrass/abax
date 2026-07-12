"""CLI entry point.

Lazy imports only — never import Qt, Textual, or curses at module top level.
The ``--help``/``--version``/``--deps`` fast paths respond instantly without
touching the GUI/TUI stacks (and never create a venv).
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="abax",
        description="abax — a keyboard-first statistics and data-science workstation.",
    )
    p.add_argument("--version", action="store_true", help="print version and exit")
    p.add_argument("--deps", action="store_true", help="print optional-dependency status and exit")
    p.add_argument(
        "--macros",
        action="append",
        default=[],
        metavar="PATH",
        help="macro file or directory to load (repeatable); adds UDFs and macros",
    )
    sub = p.add_subparsers(dest="command")

    pg = sub.add_parser("gui", help="launch the Qt GUI")
    pg.add_argument("file", nargs="?", help="spreadsheet to open")

    pt = sub.add_parser("tui", help="launch the curses TUI")
    pt.add_argument("file", nargs="?", help="spreadsheet to open")

    pv = sub.add_parser("view", help="print a spreadsheet as a table")
    pv.add_argument("file", help="spreadsheet to open (.csv/.xlsx/.json)")
    pv.add_argument("--sheet", help="sheet name (default: active)")

    pc = sub.add_parser("convert", help="convert between formats by extension")
    pc.add_argument("src")
    pc.add_argument("dst")
    pc.add_argument("--values", action="store_true", help="write computed values, not formulas")

    pe = sub.add_parser("get", help="print one cell's computed value")
    pe.add_argument("file")
    pe.add_argument("ref", help="A1 reference, e.g. B7")

    sub.add_parser("deps", help="install the optional dependencies (full-fat)")

    pm = sub.add_parser("macro", help="list or run macros")
    msub = pm.add_subparsers(dest="macro_cmd")
    msub.add_parser("list", help="list discovered macros and user functions")
    mr = msub.add_parser("run", help="run a macro against a file")
    mr.add_argument("name")
    mr.add_argument("file")
    mr.add_argument("-o", "--output", help="save path (default: overwrite the input file)")
    mr.add_argument("--at", metavar="A1", help="anchor cell for relative macros (e.g. C5)")

    sub.add_parser("doctor", help="print an environment / health diagnostic report")

    pn = sub.add_parser("notebook", help="run a Jupyter notebook headlessly")
    nsub = pn.add_subparsers(dest="notebook_cmd")
    nr = nsub.add_parser("run", help="execute a notebook and write results back")
    nr.add_argument("path", help="the .ipynb file to execute")
    nr.add_argument("-o", "--output", metavar="OUT",
                    help="write the executed notebook here (default: overwrite in place)")

    pf = sub.add_parser("fetch", help="download a data URL and print it as a table")
    pf.add_argument("url", help="http(s) URL of a CSV/JSON/Excel/… data file or web page")
    pf.add_argument("--sheet", help="sheet to print (default: the first)")

    ps = sub.add_parser("sql", help="run a read-only SQL query against a SQLite database")
    ps.add_argument("db", help="path to a .db / .sqlite file")
    ps.add_argument("query", help="the SQL SELECT to run")

    pd = sub.add_parser("diff", help="show cell-level differences between two workbooks")
    pd.add_argument("old", help="the older / left .abax or .json workbook")
    pd.add_argument("new", help="the newer / right .abax or .json workbook")

    pp = sub.add_parser("pipe", help="stream stdin into a workbook range and save")
    pp.add_argument("target", help="anchor cell / range, e.g. Sheet1!A1 or B2")
    pp.add_argument("file", help="workbook to write into (.abax/.json/.csv/…)")
    pp.add_argument("--tsv", action="store_true", help="force tab-separated columns")
    pp.add_argument("--csv", action="store_true", help="force comma-separated columns")

    pr = sub.add_parser("profile", help="report the slowest formula cells in a workbook")
    pr.add_argument("file", help="workbook to profile (.abax/.json/.xlsx/…)")
    pr.add_argument("--sheet", help="restrict to one sheet (default: every sheet)")
    pr.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="average N timing passes for a steadier estimate (default: 1)")
    pr.add_argument("--limit", type=int, default=20, metavar="N",
                    help="show at most N rows (default: 20; 0 = all)")

    return p


_SUBCOMMANDS = frozenset(
    {"gui", "tui", "view", "convert", "get", "macro", "deps", "doctor", "notebook",
     "fetch", "sql", "diff", "pipe", "profile"})


def _normalize_argv(argv: list[str]) -> list[str]:
    """A bare file path (no subcommand) opens it in the GUI, so `abax data.csv`
    behaves like `abax gui data.csv`. Flags and real subcommands pass through."""
    if argv and not argv[0].startswith("-") and argv[0] not in _SUBCOMMANDS:
        return ["gui", *argv]
    return argv


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Frozen-app escape hatch (PyInstaller): in a bundled build sys.executable
    # is this exe, so the console bridge can't spawn ``python -c ...`` — it
    # relaunches *us* with this sentinel instead, and we become the isolated
    # code-execution worker and nothing else (no Qt, no CLI parsing).
    if argv and argv[0] == "--run-console-worker":
        from .console_worker import main as _worker_main

        _worker_main()
        return 0
    argv = _normalize_argv(argv)
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --- fast paths (no heavy imports) ---
    if args.version:
        print(f"abax {__version__}")
        return 0
    if args.deps:
        from .diagnostics import format_deps

        print(format_deps())
        return 0

    # Load macros (and their UDFs) so every command — view/get/gui/tui — can use
    # them. Cheap when no macro files exist; runs after the fast paths above.
    from .macros import default_macro_dirs, discover_macros, install_functions

    registry = discover_macros([*default_macro_dirs(), *args.macros])
    udfs = install_functions(registry)

    cmd = args.command
    if cmd == "gui":
        from .gui.runner import run_gui

        return run_gui(args.file, registry)
    if cmd == "tui":
        from .tui import run_tui

        return run_tui(args.file, registry)
    if cmd == "view":
        return _cmd_view(args.file, args.sheet)
    if cmd == "convert":
        return _cmd_convert(args.src, args.dst, args.values)
    if cmd == "get":
        return _cmd_get(args.file, args.ref)
    if cmd == "deps":
        return _cmd_deps()
    if cmd == "macro":
        return _cmd_macro(args, registry, udfs)
    if cmd == "doctor":
        from .doctor import run_doctor

        return run_doctor()
    if cmd == "notebook":
        return _cmd_notebook(args)
    if cmd == "fetch":
        return _cmd_fetch(args)
    if cmd == "sql":
        return _cmd_sql(args)
    if cmd == "diff":
        return _cmd_diff(args.old, args.new)
    if cmd == "pipe":
        return _cmd_pipe(args)
    if cmd == "profile":
        return _cmd_profile(args)

    # No subcommand: prefer GUI, fall back to TUI, then help.
    from . import _runtime as rt

    if rt._HAS_QT:
        from .gui.runner import run_gui

        return run_gui(None, registry)
    if sys.stdout.isatty():
        from .tui import run_tui

        return run_tui(None, registry)
    parser.print_help()
    return 0


def _cmd_diff(old: str, new: str) -> int:
    """``abax diff OLD NEW`` — a cell-level workbook diff, ``diff(1)``-style exit
    codes: 0 = identical, 1 = differences found, 2 = error."""
    from .core.abaxdiff import DiffError, diff_files, render_text

    try:
        d = diff_files(old, new)
    except DiffError as exc:
        print(f"diff: {exc}", file=sys.stderr)
        return 2
    if d.is_empty:
        print("no differences")
        return 0
    print(render_text(d, color=sys.stdout.isatty()))
    return 1


def _cmd_pipe(args) -> int:
    """``abax pipe TARGET FILE`` — stream stdin into a workbook range and save."""
    from .core.pipe import PipeError, apply_stream, parse_target
    from .engine.document import Document

    try:
        sheet_name, _r, _c = parse_target(args.target)
    except PipeError as exc:
        print(f"pipe: {exc}", file=sys.stderr)
        return 2
    try:
        doc = Document.open(args.file)
    except Exception as exc:  # noqa: BLE001
        print(f"pipe: cannot open {args.file}: {exc}", file=sys.stderr)
        return 2
    wb = doc.workbook
    sheet = (wb.get_sheet(sheet_name) or wb.sheet) if sheet_name else wb.sheet
    delimiter = "\t" if args.tsv else ("," if args.csv else None)
    text = sys.stdin.read()
    rows, cells = apply_stream(sheet, args.target, text, delimiter=delimiter)
    try:
        doc.save()
    except Exception as exc:  # noqa: BLE001
        print(f"pipe: cannot save {args.file}: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {cells} cell(s) across {rows} row(s) at {args.target}")
    return 0


def _cmd_profile(args) -> int:
    """``abax profile FILE`` — time every formula cell and print the slowest.

    Mirrors the GUI formula profiler headlessly (same `core.profile` engine).
    Exit codes: 0 = report printed, 2 = open error / unknown sheet.
    """
    from .core import profile
    from .engine.document import Document

    try:
        doc = Document.open(args.file)
    except Exception as exc:  # noqa: BLE001 — surface any open failure cleanly
        print(f"profile: cannot open {args.file}: {exc}", file=sys.stderr)
        return 2
    if args.sheet is not None and doc.workbook.get_sheet(args.sheet) is None:
        print(f"profile: no such sheet: {args.sheet!r}", file=sys.stderr)
        return 2
    timings = profile.profile_recalc(
        doc.workbook, sheet=args.sheet, repeat=max(1, args.repeat))
    print(profile.format_report(timings, limit=args.limit))
    return 0


def _cmd_deps() -> int:
    """Install every optional dependency (full-fat), blocking with progress."""
    from . import autodeps

    autodeps.set_enabled(True)
    todo = autodeps.prefetch_all(background=False, force=True)
    if todo:
        print(f"Attempted {len(todo)} package(s): {', '.join(todo)}")
    have = sum(1 for _pip, mod in autodeps.ALL if autodeps.installed(mod))
    print(f"Optional dependencies present: {have}/{len(autodeps.ALL)}")
    return 0


def _cmd_view(path: str, sheet_name: str | None) -> int:
    from .engine.document import Document

    doc = Document.open(path)
    sheet = doc.workbook.get_sheet(sheet_name) if sheet_name else doc.workbook.sheet
    if sheet is None:
        print(f"no such sheet: {sheet_name}", file=sys.stderr)
        return 2
    print(_render_table(sheet))
    return 0


def _cmd_convert(src: str, dst: str, values: bool) -> int:
    from .engine.document import Document

    doc = Document.open(src)
    try:
        doc.save(dst)
    except RuntimeError as exc:  # e.g. openpyxl missing
        print(str(exc), file=sys.stderr)
        return 3
    print(f"converted {src} -> {dst}")
    return 0


def _cmd_get(path: str, ref: str) -> int:
    from .engine.document import Document

    doc = Document.open(path)
    print(doc.workbook.sheet.format_value(doc.workbook.sheet.get(ref)))
    return 0


def _cmd_macro(args, registry, udfs) -> int:
    if args.macro_cmd == "run":
        from .engine.document import Document
        from .macros import MacroError, run_macro

        cursor = None
        if args.at:
            from .core.reference import parse_a1

            cursor = parse_a1(args.at)
        doc = Document.open(args.file)
        try:
            ctx = run_macro(registry, args.name, doc.workbook, cursor=cursor)
        except MacroError as exc:
            print(str(exc), file=sys.stderr)
            return 4
        for msg in ctx.messages:
            print(msg)
        out = args.output or args.file
        doc.save(out)
        print(f"ran macro {args.name!r}; saved {out}")
        return 0

    # default / "list"
    if registry.macros:
        print("macros:")
        for name in sorted(registry.macros):
            print(f"  {name}")
    else:
        print("no macros found (drop .py files in CONFIG_DIR/macros or pass --macros PATH)")
    if udfs:
        print("user functions:")
        for name in udfs:
            print(f"  {name}()")
    return 0


def _cmd_notebook(args) -> int:
    if args.notebook_cmd != "run":
        print("usage: abax notebook run FILE [-o OUT]", file=sys.stderr)
        return 2
    from .engine.nbrun import run_notebook

    # No -o means overwrite in place, so always pass a concrete output path
    # (run_notebook writes only when path_out is given).
    out = args.output or args.path
    try:
        summary = run_notebook(args.path, out)
    except Exception as exc:  # noqa: BLE001 - surface any read/execute failure cleanly
        print(f"notebook run failed: {exc}", file=sys.stderr)
        return 4
    ran = summary.get("cells", "?")
    errs = summary.get("error_cells") or []
    msg = f"executed {ran} cell(s); wrote {out}"
    if errs:
        msg += f" ({len(errs)} cell(s) raised — see the notebook outputs)"
    print(msg)
    return 0


def _cmd_fetch(args) -> int:
    from .core.io import urlfetch
    from .engine.document import Document

    try:
        path = urlfetch.fetch_url(args.url)
        doc = Document.open(str(path))
    except Exception as exc:  # noqa: BLE001 - surface network/parse failures cleanly
        print(f"fetch failed: {exc}", file=sys.stderr)
        return 4
    sheet = doc.workbook.get_sheet(args.sheet) if args.sheet else doc.workbook.sheet
    if sheet is None:
        print(f"no such sheet: {args.sheet!r}", file=sys.stderr)
        return 2
    print(_render_table(sheet))
    return 0


def _cmd_sql(args) -> int:
    import sqlite3

    from .engine import dbapi

    try:
        conn = sqlite3.connect(args.db)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot open database: {exc}", file=sys.stderr)
        return 4
    try:
        headers, rows = dbapi.query(conn, args.query)
    except Exception as exc:  # noqa: BLE001 - bad SQL / unreadable db
        print(f"query failed: {exc}", file=sys.stderr)
        return 4
    finally:
        conn.close()
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)))
    return 0


def _render_table(sheet) -> str:
    from .core.reference import index_to_col

    n_rows, n_cols = sheet.used_bounds()
    if n_rows == 0:
        return "(empty)"
    cells = [[sheet.display(r, c) for c in range(n_cols)] for r in range(n_rows)]
    headers = [index_to_col(c) for c in range(n_cols)]
    row_label_w = len(str(n_rows))
    widths = [
        max(len(headers[c]), max((len(cells[r][c]) for r in range(n_rows)), default=0))
        for c in range(n_cols)
    ]
    out = [" " * row_label_w + " | " + " | ".join(h.ljust(widths[c]) for c, h in enumerate(headers))]
    out.append("-" * len(out[0]))
    for r in range(n_rows):
        line = str(r + 1).rjust(row_label_w) + " | "
        line += " | ".join(cells[r][c].ljust(widths[c]) for c in range(n_cols))
        out.append(line)
    return "\n".join(out)


if __name__ == "__main__":
    raise SystemExit(main())
