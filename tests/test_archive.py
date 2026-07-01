"""Archive creation / listing / safe extraction."""

from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from abax.core import archive as A


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / "a.txt").write_text("alpha")
    d = tmp_path / "d"
    d.mkdir()
    (d / "b.txt").write_text("beta")
    return tmp_path


@pytest.mark.parametrize("ext", [".zip", ".tar.gz", ".tgz", ".tar", ".tar.bz2"])
def test_create_list_extract_roundtrip(tree, tmp_path, ext):
    dest = tmp_path / f"bundle{ext}"
    A.create_archive([tree / "a.txt", tree / "d"], dest)
    assert dest.exists()
    members = A.list_archive(dest)
    assert any(m.endswith("a.txt") for m in members)
    assert any("b.txt" in m for m in members)

    out = tmp_path / "out"
    A.extract_archive(dest, out)
    assert (out / "a.txt").read_text() == "alpha"
    assert (out / "d" / "b.txt").read_text() == "beta"


def test_zip_is_deflated(tree, tmp_path):
    dest = tmp_path / "z.zip"
    A.create_archive([tree / "a.txt"], dest)
    with zipfile.ZipFile(dest) as zf:
        assert zf.getinfo("a.txt").compress_type == zipfile.ZIP_DEFLATED


def test_unsupported_format(tmp_path):
    with pytest.raises(A.ArchiveError):
        A.create_archive([tmp_path], tmp_path / "x.rar")


def test_empty_sources(tmp_path):
    with pytest.raises(A.ArchiveError):
        A.create_archive([], tmp_path / "x.zip")


def test_list_non_archive(tmp_path):
    f = tmp_path / "plain.txt"
    f.write_text("hi")
    with pytest.raises(A.ArchiveError):
        A.list_archive(f)


def test_zip_slip_is_blocked(tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../escape.txt", "pwned")
    with pytest.raises(A.ArchiveError):
        A.extract_archive(evil, tmp_path / "dest")
    assert not (tmp_path / "escape.txt").exists()


def test_tar_slip_is_blocked(tmp_path):
    evil = tmp_path / "evil.tar"
    with tarfile.open(evil, "w") as tf:
        info = tarfile.TarInfo("../escape.txt")
        data = b"pwned"
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    with pytest.raises(A.ArchiveError):
        A.extract_archive(evil, tmp_path / "dest")
    assert not (tmp_path / "escape.txt").exists()
