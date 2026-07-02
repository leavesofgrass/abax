"""HDF5 (.h5 / .hdf5) read adapter via h5py — optional, with a clear fallback.

HDF5 is a hierarchical binary container: a file holds a tree of *groups* and
*datasets*, where a dataset is an n-dimensional typed array. Reading one needs
the ``h5py`` package (which wraps the libhdf5 C library). Like the Parquet
adapter, this module imports gracefully: importing it never fails when h5py is
absent, and any operation that actually needs h5py raises a descriptive
:class:`Hdf5Error` telling the user how to enable it. This keeps ``abax/core/``
free of any hard third-party dependency (see docs/architecture.md).

Loading behaviour — a file may contain many datasets, so we build one
:class:`~abax.core.sheet.Sheet` per *tabular* dataset (1-D or 2-D), in the order
they are discovered by a depth-first walk of the group tree. Each dataset's full
path (e.g. ``/group/table``) names its sheet. A 2-D dataset becomes rows and
columns directly; a 1-D dataset becomes a single column. If the dataset is a
NumPy *structured* array (named fields), the field names become the header row.
Otherwise a synthetic ``col1``.. header row is emitted so the sheet always has a
header, matching the CSV/Parquet importers. Datasets with 3+ dimensions or zero
elements are skipped. If no tabular dataset exists, :class:`Hdf5Error` is raised.

Read-only: HDF5 export is intentionally out of scope (abax's native formats and
Parquet cover binary round-tripping).
"""

from __future__ import annotations

from pathlib import Path

from ..core.sheet import Sheet
from ..core.workbook import Workbook


class Hdf5Error(Exception):
    """Raised when an HDF5 operation cannot proceed (missing dep or bad file)."""


_FALLBACK_MSG = (
    "HDF5 (.h5 / .hdf5) import requires the 'h5py' package. Install it with:\n"
    "    pip install h5py\n"
    "or install abax's hdf5 extra:  pip install abax[hdf5]"
)


def _import_h5py():
    """Lazy-import h5py, raising :class:`Hdf5Error` if unavailable."""
    try:
        import h5py  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise Hdf5Error(_FALLBACK_MSG) from exc
    return h5py


def available() -> bool:
    """True if h5py is importable."""
    try:
        import h5py  # type: ignore  # noqa: F401
    except ImportError:
        return False
    return True


def _stringify(value) -> str:
    """Render one HDF5 array element as abax cell text.

    Bytes (h5py's default for string datasets) are decoded as UTF-8; NumPy
    floats that are whole numbers are normalized to integers (``3.0`` -> ``3``)
    to match how abax stores integers elsewhere.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, str):
        return value
    if isinstance(value, bool):  # bool before int/float (bool is a subclass)
        return str(value)
    # NumPy integer / floating pass through str() cleanly, but normalize
    # whole-valued floats so 3.0 shows as 3, matching the other importers.
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f.is_integer():
        return str(int(f))
    return str(value)


def _cell_text(value) -> str:
    """A safe stringification that never blows up on exotic dtypes."""
    try:
        return _stringify(value)
    except Exception:
        return str(value)


def _dataset_to_sheet(name: str, dset) -> Sheet | None:
    """Build a Sheet from one h5py dataset, or ``None`` if it isn't tabular.

    Handles 1-D and 2-D datasets, including NumPy structured (compound) arrays
    whose field names become the header row. Returns ``None`` for scalar,
    3-D+, or empty datasets so the caller can skip them.
    """
    ndim = getattr(dset, "ndim", None)
    if ndim not in (1, 2):
        return None
    if getattr(dset, "size", 0) == 0:
        return None

    data = dset[()]  # materialize into a NumPy array
    fields = getattr(getattr(data, "dtype", None), "names", None)
    sheet = Sheet(name)

    def _items():
        if fields:
            # Structured / compound dtype: field names are the header, one row
            # per record. Only 1-D compound arrays are meaningfully tabular.
            for c, field in enumerate(fields):
                yield 0, c, str(field)
            records = data if data.ndim == 1 else data.ravel()
            for r, record in enumerate(records, start=1):
                for c, field in enumerate(fields):
                    text = _cell_text(record[field])
                    if text != "":
                        yield r, c, text
            return

        if ndim == 1:
            n_cols = 1
        else:
            n_cols = int(data.shape[1])
        # Synthetic header so the sheet always has column names.
        for c in range(n_cols):
            yield 0, c, f"col{c + 1}"
        if ndim == 1:
            for r, value in enumerate(data, start=1):
                text = _cell_text(value)
                if text != "":
                    yield r, 0, text
        else:
            for r in range(data.shape[0]):
                for c in range(n_cols):
                    text = _cell_text(data[r, c])
                    if text != "":
                        yield r + 1, c, text

    sheet.set_cells_bulk(_items())
    return sheet


def list_datasets(path: str | Path) -> list[str]:
    """Return the paths of every dataset in the file (depth-first order)."""
    h5py = _import_h5py()
    path = Path(path)
    found: list[str] = []
    try:
        with h5py.File(str(path), "r") as f:
            def _visit(name, obj):
                if isinstance(obj, h5py.Dataset):
                    found.append("/" + name)
            f.visititems(_visit)
    except (OSError, Hdf5Error):
        raise
    except Exception as exc:  # h5py raises its own errors for malformed files
        raise Hdf5Error(f"not a valid HDF5 file: {path}: {exc}") from exc
    return found


def load_hdf5(path: str | Path) -> Workbook:
    """Read an ``.h5`` / ``.hdf5`` file into a multi-sheet workbook.

    Every tabular (1-D or 2-D) dataset becomes one sheet named by its full path.
    Datasets are discovered by a depth-first walk of the group tree, so sheet
    order follows the file's own structure. Non-tabular datasets (scalars,
    3-D+, or empty) are skipped. Raises :class:`Hdf5Error` if h5py is missing,
    the file is malformed, or it contains no tabular dataset.
    """
    h5py = _import_h5py()
    path = Path(path)

    sheets: list[Sheet] = []
    try:
        with h5py.File(str(path), "r") as f:
            pending: list[tuple[str, object]] = []

            def _visit(name, obj):
                if isinstance(obj, h5py.Dataset):
                    pending.append(("/" + name, obj))

            f.visititems(_visit)
            for full_name, dset in pending:
                sheet = _dataset_to_sheet(full_name, dset)
                if sheet is not None:
                    sheets.append(sheet)
    except (OSError, Hdf5Error):
        raise
    except Exception as exc:  # malformed file / unexpected h5py error
        raise Hdf5Error(f"not a valid HDF5 file: {path}: {exc}") from exc

    if not sheets:
        raise Hdf5Error(f"no tabular (1-D/2-D) dataset found in {path}")
    return Workbook.from_sheets(sheets)


__all__ = [
    "Hdf5Error",
    "available",
    "list_datasets",
    "load_hdf5",
]
