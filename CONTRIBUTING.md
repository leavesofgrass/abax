# Contributing to abax

abax is a keyboard-first statistics / data-science / RF spreadsheet: pure-Python
core, optional accelerators, three front-ends (Qt GUI, Textual/curses TUI, CLI).

This page is the short list of things that are easy to get wrong here and are
not obvious from reading the code. The architecture itself — the layering, the
invariants, how the GUI is composed — is documented in
[docs/architecture.md](docs/architecture.md); start there for *what the code is*,
and here for *how to work on it*.

## Getting set up

```bash
just install          # pip install -e ".[dev,thin]"
just test-fast        # the full suite across all cores (a few minutes)
just check            # lint + test + build the zipapp + smoke it
```

Without `just`, every recipe is one line in the [justfile](justfile).

`just lint` checks `abax/` only. Before opening a pull request, run
`ruff check .` so `tests/` and `scripts/` are covered too.

The suite runs headless and needs no display, but Qt has to be told:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -n auto
```

On Linux, wrap it in `xvfb-run -a` — PySide6 wants an X server surrogate even
offscreen, and also needs `libegl1` and `libgl1` installed.

**The suite must pass with zero optional dependencies.** That is the point of
the `core` layer, and it is enforced by `tests/test_dependencies.py`. If a test
needs numpy, gate it with `pytest.importorskip`.

## Text encoding — read this one

**Every file in this repository is UTF-8 without a BOM, and every read and write
in the codebase states its encoding explicitly.**

Python's `open()`, `Path.read_text()` and `Path.write_text()` use the *platform
default* encoding when you don't pass one. On a machine whose default is not
UTF-8 — plenty of Windows installs, and any box with an ASCII default — that
silently corrupts or crashes on any non-ASCII byte. This is not hypothetical:
the zipapp build once read a source file containing a single em dash with the
default encoding, so `make_pyz.py` died outright wherever the default was not
UTF-8, while working perfectly for everyone who tested it.

So:

- Use `abax._runtime.read_text_utf8()` / `write_text_utf8()`, or pass
  `encoding="utf-8"` yourself. Never rely on the default.
- Reading files that may carry a BOM (settings written by an older build,
  anything a user hands you) uses `utf-8-sig`; writing always uses plain
  `utf-8`.
- Console output is a separate problem from file I/O — see
  `_runtime.console_encoding()`.

**Editing hazard:** some editors and shells rewrite encoding or line endings on
save. Windows PowerShell 5.1 is the notable one — `Set-Content` and
`Add-Content` default to the system ANSI codepage, and `-Encoding utf8` there
means *UTF-8 with a BOM*. Either will mangle these files, and appending can flip
the file's line endings on the way through. Use an editor, or `python`, not a
shell redirect.

## Tests

New behaviour needs a test, and the test needs to be able to fail. That sounds
obvious; it is the single most common defect found in this repo's own test
suite. Seven separate cases have been found where a test was green and
*structurally incapable* of failing — a spy on the wrong function, an assertion
on a value the code always returns, a fixture that stubbed the thing under test.

The cheap check: break the code on purpose and confirm the test goes red. If it
doesn't, the test isn't testing.

**A skipped test is silent.** The suite reports success either way, so a skip
that shouldn't be there can survive for months. Eight Windows sandbox
confinement tests — the ones backing a *security* promise — were skipped in CI
for exactly that long, on a claim about hosted runners that took one two-minute
job to disprove. `tests/test_sandbox_gate.py` now exists solely to keep that
tier un-skippable; if you find yourself adding a `pytestmark` or a collection
hook that skips tests, read that file's docstring first.

Prefer `-n auto`. Anything that mutates process-global state (resource limits,
environment, working directory) must do it in a subprocess, or it leaks into
whichever parallel worker happened to run it.

## Coverage ratchets

CI gates `abax/core` and `abax/engine` with `scripts/coverage_ratchet.py`. It
fails in **both** directions:

- **below the floor** — coverage regressed. Add tests, or make the case for
  lowering it.
- **too far above the floor** — coverage improved and the floor was never
  raised, so the gate has gone slack and now permits a regression it should
  catch. The failure message names the number; raise it in
  `.github/workflows/ci.yml`.

The second one fails a build that did nothing wrong, and that is deliberate: it
is what makes the number a ratchet rather than a floor that drifts for a year.
It is a one-line edit.

Note that the coverage job installs only `[dev,thin]`, so the `abax/engine`
number is the *thin-environment* number — adapters needing numpy/pandas/pymc are
skipped there. Only ever compare it against another thin run.

## Pull requests

- Keep the diff to one concern. Stage files explicitly rather than `git add -A`,
  which has more than once swept unrelated work into a commit under a message
  that didn't describe it.
- Update [CHANGELOG.md](CHANGELOG.md) under `## [Unreleased]`.
- Documentation lives in `docs/` and is built with `mkdocs build --strict`,
  which fails on a broken internal link. Run it if you touched docs.

## Reporting bugs

Open an issue: <https://github.com/leavesofgrass/abax/issues>.

The most useful thing you can attach is the output of `abax --version` together
with `abax doctor`, which reports your Python and platform, which optional
dependencies are present, the active code-isolation level, and where abax keeps
its config, data, cache and log directories. Please say what you expected and
what happened instead — for anything involving the GUI, which front-end and Qt
binding you're on.
