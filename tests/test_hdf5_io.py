"""Tests for abax.engine.hdf5_io — HDF5 (.h5 / .hdf5) dataset import.

The round-trip test requires h5py (plus numpy); it skips cleanly when those
optional deps are absent, so the suite still passes with zero optional packages
installed (a core invariant). The graceful missing-dep message, the extension
routing, and the three registrations are ALWAYS tested — no dep required.
"""

from __future__ import annotations

import pytest

from abax.engine import hdf5_io
from abax.engine.hdf5_io import Hdf5Error

# --- dep-free contract tests (always run) -----------------------------------


def test_available_returns_bool():
    # Importable without any optional dep; available() is always a plain bool.
    assert isinstance(hdf5_io.available(), bool)


def test_module_imports_without_h5py():
    # The module and Hdf5Error exist regardless of h5py being installed.
    assert issubclass(Hdf5Error, Exception)


def test_missing_dep_message_points_at_extra(monkeypatch):
    # Force the "h5py absent" path and assert the message names the pip extra,
    # matching the statfiles/parquet missing-dep idiom. This runs even when
    # h5py IS installed, so the contract is always exercised.
    import builtins

    real_import = builtins.__import__

    def _no_h5py(name, *args, **kwargs):
        if name == "h5py" or name.startswith("h5py."):
            raise ImportError("no h5py")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_h5py)
    with pytest.raises(Hdf5Error) as exc:
        hdf5_io.load_hdf5("whatever.h5")
    msg = str(exc.value)
    assert "pip install abax[hdf5]" in msg
    assert "h5py" in msg


# --- routing (always run) ---------------------------------------------------


def test_document_open_routes_h5_extensions(monkeypatch):
    # .h5 and .hdf5 must dispatch into hdf5_io.load_hdf5 from Document.open,
    # regardless of whether h5py is installed.
    from abax.engine import document

    seen = []
    monkeypatch.setattr(
        hdf5_io, "load_hdf5", lambda p: seen.append(str(p)) or _stub_workbook()
    )
    for ext in (".h5", ".hdf5"):
        doc = document.Document.open(f"sample{ext}")
        assert doc.path.suffix == ext
    assert seen == ["sample.h5", "sample.hdf5"]


def _stub_workbook():
    from abax.core.sheet import Sheet
    from abax.core.workbook import Workbook

    return Workbook.from_sheets([Sheet("s")])


# --- the three registrations (always run) -----------------------------------


def test_registered_in_diagnostics():
    from abax import diagnostics

    assert "h5py" in diagnostics.OPTIONAL_DEPENDENCIES
    info = diagnostics.OPTIONAL_DEPENDENCIES["h5py"]
    assert "available" in info and isinstance(info["available"], bool)
    assert "fallback" in info


def test_registered_in_autodeps_before_pynec():
    from abax import autodeps

    # New 'hdf5' feature exists and resolves to h5py.
    assert autodeps.FEATURES["hdf5"] == [("h5py", "h5py")]
    # Folded into the full-fat set...
    assert ("h5py", "h5py") in autodeps.ALL
    # ...but PyNEC stays dead last (compiled build can't block the rest).
    assert autodeps.ALL[-1] == ("PyNEC", "PyNEC")
    assert autodeps.ALL.index(("h5py", "h5py")) < autodeps.ALL.index(("PyNEC", "PyNEC"))
    # Chooser metadata is present.
    assert "hdf5" in autodeps.FEATURE_INFO
    label, detail, mb = autodeps.FEATURE_INFO["hdf5"]
    assert label and detail and isinstance(mb, int)
    # 'all' preset includes it; 'thin' does not.
    assert "hdf5" in autodeps.preset("all")
    assert "hdf5" not in autodeps.preset("thin")


def test_registered_in_pyproject():
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert extras["hdf5"] == ["h5py"]
    # Folded into `all`.
    assert any("hdf5" in dep for dep in extras["all"])


# --- round-trip (only when h5py + numpy are installed) ----------------------


def test_hdf5_roundtrip_2d(tmp_path):
    h5py = pytest.importorskip("h5py")
    np = pytest.importorskip("numpy")

    path = tmp_path / "data.h5"
    with h5py.File(str(path), "w") as f:
        f.create_dataset("table", data=np.array([[1, 2, 3], [4, 5, 6]]))

    wb = hdf5_io.load_hdf5(path)
    sheet = wb.sheets[0]
    # Synthetic header row for a plain (non-structured) dataset.
    assert sheet.get_raw(0, 0) == "col1"
    assert sheet.get_raw(0, 2) == "col3"
    # First data row lands at row 1.
    assert sheet.get_raw(1, 0) == "1"
    assert sheet.get_raw(1, 2) == "3"
    assert sheet.get_raw(2, 1) == "5"


def test_hdf5_structured_dataset_uses_field_names(tmp_path):
    h5py = pytest.importorskip("h5py")
    np = pytest.importorskip("numpy")

    path = tmp_path / "people.h5"
    dtype = np.dtype([("name", "S10"), ("age", "i4")])
    records = np.array([(b"Alice", 30), (b"Bob", 25)], dtype=dtype)
    with h5py.File(str(path), "w") as f:
        f.create_dataset("people", data=records)

    wb = hdf5_io.load_hdf5(path)
    sheet = wb.sheets[0]
    assert sheet.get_raw(0, 0) == "name"
    assert sheet.get_raw(0, 1) == "age"
    assert sheet.get_raw(1, 0) == "Alice"
    assert sheet.get_raw(1, 1) == "30"
    assert sheet.get_raw(2, 0) == "Bob"


def test_hdf5_multiple_datasets_become_multiple_sheets(tmp_path):
    h5py = pytest.importorskip("h5py")
    np = pytest.importorskip("numpy")

    path = tmp_path / "multi.h5"
    with h5py.File(str(path), "w") as f:
        f.create_dataset("a", data=np.array([10, 20, 30]))
        grp = f.create_group("g")
        grp.create_dataset("b", data=np.array([[1, 2], [3, 4]]))

    wb = hdf5_io.load_hdf5(path)
    names = {s.name for s in wb.sheets}
    assert names == {"/a", "/g/b"}


def test_hdf5_no_tabular_dataset_raises(tmp_path):
    h5py = pytest.importorskip("h5py")
    np = pytest.importorskip("numpy")

    path = tmp_path / "scalar.h5"
    with h5py.File(str(path), "w") as f:
        f.create_dataset("scalar", data=np.int64(42))  # 0-D, not tabular

    with pytest.raises(Hdf5Error):
        hdf5_io.load_hdf5(path)


def test_list_datasets(tmp_path):
    h5py = pytest.importorskip("h5py")
    np = pytest.importorskip("numpy")

    path = tmp_path / "list.h5"
    with h5py.File(str(path), "w") as f:
        f.create_dataset("x", data=np.array([1, 2]))
        f.create_group("g").create_dataset("y", data=np.array([3, 4]))

    assert set(hdf5_io.list_datasets(path)) == {"/x", "/g/y"}
