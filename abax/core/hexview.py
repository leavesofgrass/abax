"""Streaming binary / hex inspector model.

A :class:`HexView` browses the raw bytes of a file the way a classic hex
editor does — offset column, hex pairs, ASCII gutter — *without ever loading
the whole file into memory*.

Why the windowed read matters: these files can be gigabytes (disk images,
memory dumps, packet captures) and dwarf available RAM. A viewer only ever
shows a screenful of rows at a time, so the model seeks to the requested byte
offset and reads exactly the bytes for that window (``count * width`` at most).
Scrolling is just another :meth:`HexView.rows` call at a new offset; memory use
stays constant regardless of file size. This is deliberately a seek/read
window rather than ``mmap`` — it is the simplest thing that satisfies the
"bigger than RAM" requirement and imposes no address-space limits.

Public API:

* :class:`HexRow` — one decoded row (offset, hex pairs, ASCII rendering).
* :class:`HexView` — the model; ``rows`` / ``format_rows`` page through it.
  Construct from a path, or :meth:`HexView.from_bytes` for in-memory data.
"""

from __future__ import annotations

import io
import os
import string
from dataclasses import dataclass

# Bytes that render literally in the ASCII gutter. Everything else (control
# chars, high bytes) collapses to '.' so the gutter stays a fixed-width,
# copy-pasteable block. string.printable includes whitespace like \n/\t which
# would break row alignment, so we intersect with the "visible" range instead.
_PRINTABLE = frozenset(
    b for b in range(0x20, 0x7F) if chr(b) in string.printable
)


@dataclass
class HexRow:
    """One row of a hex dump.

    Attributes:
        offset: Absolute byte offset of the first byte in this row.
        hexes: One two-char uppercase hex string per byte, e.g. ``["0A", "FF"]``.
            A short final row (near EOF) simply has fewer entries.
        ascii: The row's bytes rendered for the ASCII gutter — printable bytes
            as their character, all others as ``'.'``.
    """

    offset: int
    hexes: list[str]
    ascii: str


class HexView:
    """Random-access, memory-bounded view over a file's bytes.

    The file is opened once for buffered binary reads; each :meth:`rows` call
    seeks to the requested offset and reads only that window. Use as a context
    manager, or call :meth:`close` when done.
    """

    def __init__(self, path: str | os.PathLike) -> None:
        # Open in buffered binary mode for cheap seek()/read(). We keep the
        # handle open for the life of the view so repeated paging (scrolling)
        # does not re-open the file on every frame.
        self._fh: io.BufferedReader = open(os.fspath(path), "rb")
        self._fh.seek(0, os.SEEK_END)
        self.size: int = self._fh.tell()
        self._fh.seek(0)

    @classmethod
    def from_bytes(cls, data: bytes) -> "HexView":
        """Build a view backed by an in-memory ``bytes`` buffer.

        Handy for tests and for inspecting clipboard / generated data that
        never touched disk. The buffer is wrapped in :class:`io.BytesIO`, so it
        supports the same seek/read window path as a real file.
        """
        view = cls.__new__(cls)
        view._fh = io.BytesIO(data)
        view.size = len(data)
        return view

    def rows(
        self, start_offset: int, count: int, *, width: int = 16
    ) -> list["HexRow"]:
        """Return up to ``count`` decoded rows of ``width`` bytes each.

        Only the ``count * width`` byte window starting at ``start_offset`` is
        read from the backing store — never the whole file. Requests that run
        past EOF are clamped: the last row may be short, and a start at or past
        EOF yields an empty list. A zero-byte file always yields ``[]``.
        """
        if width <= 0:
            raise ValueError("width must be positive")
        if count <= 0 or start_offset >= self.size:
            return []
        start = max(start_offset, 0)

        # Read exactly the window (clamped to what remains). This is the whole
        # point of the model: a bounded read no matter how large the file is.
        want = count * width
        remaining = self.size - start
        to_read = min(want, remaining)
        self._fh.seek(start)
        buf = self._fh.read(to_read)

        rows: list[HexRow] = []
        for i in range(0, len(buf), width):
            chunk = buf[i : i + width]
            hexes = [f"{b:02X}" for b in chunk]
            ascii_repr = "".join(
                chr(b) if b in _PRINTABLE else "." for b in chunk
            )
            rows.append(HexRow(offset=start + i, hexes=hexes, ascii=ascii_repr))
        return rows

    def format_rows(
        self, start_offset: int, count: int, *, width: int = 16
    ) -> str:
        """Render rows as a classic three-column hex dump string.

        Layout per line: an 8-digit hex offset, the hex pairs (space-separated
        and right-padded so short final rows still align the gutter), then the
        ASCII gutter wrapped in ``|...|``. Example::

            00000000  48 65 6C 6C 6F 00 FF                              |Hello..|
        """
        # Width of the hex-pairs column: `width` pairs of 2 chars plus a space
        # after each, minus the trailing space. Padding a short last row to
        # this width keeps every gutter starting in the same column.
        hex_col_width = width * 3 - 1
        lines: list[str] = []
        for row in self.rows(start_offset, count, width=width):
            hex_part = " ".join(row.hexes).ljust(hex_col_width)
            lines.append(f"{row.offset:08X}  {hex_part}  |{row.ascii}|")
        return "\n".join(lines)

    def close(self) -> None:
        """Close the backing file handle. Idempotent."""
        if getattr(self, "_fh", None) is not None:
            self._fh.close()
            self._fh = None  # type: ignore[assignment]

    def __enter__(self) -> "HexView":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
