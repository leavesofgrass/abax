# Licensing

abax is free software, licensed under the **GNU General Public License,
version 3.0 or later** (GPL-3.0-or-later). The full text is in
[`LICENSE`](../LICENSE), and the per-component attributions and trademark
disclaimers are in [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md). This
page is a plain-language summary of what that means in practice.

See also: [index](index.md) · [architecture](architecture.md) · [macros and scripting](macros-and-scripting.md).

## What GPL-3.0-or-later means here

You may use, study, modify, and redistribute abax, including modified versions,
provided you keep it under the GPL and pass the same freedoms on. "Or later"
means you may also comply with any later version of the GPL the Free Software
Foundation publishes. For the exact terms — including the source-availability
and notice requirements — read [`LICENSE`](../LICENSE).

## Third-party components

abax **bundles none** of the components below. They are either optional
dependencies you install yourself, or artifacts fetched on demand into your
local cache. abax only imports Qt through a single shim
(`abax/gui/_qtcompat.py`), and `abax/core/` imports nothing beyond the standard
library — so a base install carries no third-party code at all.

### The Qt binding (GUI)

The desktop GUI runs on a Qt for Python binding, and abax works on either:

- **PySide6 — LGPL-3.0 — the default.** Installed with `pip install abax[gui]`.
  Because it is LGPL, it is the friendliest default for redistribution.
- **PyQt6 — GPL-3.0 / commercial — optional.** Installed with
  `pip install abax[gui-pyqt]` and selected with `ABAX_QT_BINDING=PyQt6`.

abax's GPL-3.0 license is compatible with both. You supply Qt via pip; abax
ships no Qt binaries.

### Optional Python dependencies (permissive)

All optional, all user-installed, all GPL-compatible, each with a stdlib or
pure-Python fallback so the app still runs without them:

| Package | License | Used for |
|---------|---------|----------|
| openpyxl | MIT | Excel `.xlsx` import/export |
| msgspec | BSD-3-Clause | fast JSON I/O (stdlib `json` fallback) |
| platformdirs | MIT | config/data/cache dirs (stdlib fallback) |
| textual | MIT | rich TUI (curses fallback) |
| rich | MIT | TUI rendering |

Other libraries such as pandas are used only if they already happen to be
installed; they are never required.

### Fetched-on-demand components

- **OpenDyslexic font — SIL Open Font License 1.1.** Fetched from the upstream
  OpenDyslexic project into abax's cache only when you enable the
  dyslexia-friendly font. abax ships no font files. © the OpenDyslexic project,
  used under the OFL.
- **pandoc — GPL-2.0-or-later.** Used only if already present, or installed at
  your explicit request via the `pypandoc_binary` wheel. It is invoked as a
  **separate process** (for LaTeX → MathML); a pure-Python subset renderer is the
  fallback. Running pandoc as a separate process keeps it cleanly at arm's
  length.

## Trademarks and calculator emulation

abax includes RPN and algebraic calculator emulations. These reproduce
**functionality only** — abax bundles **no manufacturer artwork, ROMs, or
branding**.

- **HP**, **HP-12C**, **HP-15C**, **HP-16C** are trademarks of HP Inc. (or its
  affiliates). abax's built-in "Voyager" faceplate is an original, de-branded
  vector drawing using no HP or Nonpareil artwork. An optional photographic
  faceplate reads **user-supplied** asset files from a directory you configure
  (`ABAX_FACEPLATE_DIR` or settings); abax distributes none of those assets.
- **TI**, **TI-82**, **TI-83**, **TI-84** are trademarks of Texas Instruments.

abax is an independent project and is **not affiliated with, authorized,
sponsored, or endorsed by** HP Inc. or Texas Instruments. Those names are used
only descriptively, to identify the emulated functionality.

## Where to look

- [`LICENSE`](../LICENSE) — the full GPL-3.0-or-later text and binding terms.
- [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) — the authoritative
  component table, fetched-on-demand notes, trademark disclaimers, and
  attribution.
