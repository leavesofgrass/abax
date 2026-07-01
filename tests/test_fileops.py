"""File-manager core operations against a temp tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from abax.core import fileops as F


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / "a.txt").write_text("alpha")
    (tmp_path / "b.log").write_text("beta beta")
    (tmp_path / ".hidden").write_text("secret")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("gamma")
    return tmp_path


def test_human_size():
    assert F.human_size(0) == "0 B"
    assert F.human_size(512) == "512 B"
    assert F.human_size(1536) == "1.5 KB"
    assert F.human_size(5 * 1024 * 1024) == "5.0 MB"


def test_list_dir_hides_dotfiles_and_sorts_dirs_first(tree):
    entries = F.list_dir(tree)
    names = [e.name for e in entries]
    assert ".hidden" not in names
    assert names[0] == "sub"                       # directory first
    assert {"a.txt", "b.log"} <= set(names)
    sub = next(e for e in entries if e.name == "sub")
    assert sub.is_dir and sub.size == 0


def test_list_dir_show_hidden_and_sort_by_size(tree):
    entries = F.list_dir(tree, show_hidden=True, sort_key="size", dirs_first=False)
    assert ".hidden" in [e.name for e in entries]


def test_list_dir_errors_on_nondir(tree):
    with pytest.raises(NotADirectoryError):
        F.list_dir(tree / "a.txt")


def test_copy_rename_on_conflict(tree):
    dest = tree / "sub"
    res = F.copy_paths([tree / "a.txt"], dest)
    assert res.ok and (dest / "a.txt").exists()
    # second copy renames rather than clobbering
    res2 = F.copy_paths([tree / "a.txt"], dest)
    assert res2.ok and (dest / "a (1).txt").exists()


def test_copy_directory_tree(tree):
    out = tree / "out"
    out.mkdir()
    res = F.copy_paths([tree / "sub"], out)
    assert res.ok and (out / "sub" / "c.txt").read_text() == "gamma"


def test_move_paths(tree):
    out = tree / "out"
    out.mkdir()
    res = F.move_paths([tree / "b.log"], out)
    assert res.ok
    assert not (tree / "b.log").exists()
    assert (out / "b.log").exists()


def test_delete_paths_file_and_dir(tree):
    res = F.delete_paths([tree / "a.txt", tree / "sub"])
    assert res.ok
    assert not (tree / "a.txt").exists()
    assert not (tree / "sub").exists()


def test_delete_reports_failures(tree):
    res = F.delete_paths([tree / "nope.txt"])
    assert not res.ok
    assert res.failed and "nope.txt" in res.failed[0][0]
    assert "1 succeeded, 1 failed" not in res.summary()   # 0 succeeded


def test_make_dir_and_rename(tree):
    new = F.make_dir(tree, "fresh")
    assert Path(new).is_dir()
    with pytest.raises(FileExistsError):
        F.make_dir(tree, "fresh")
    renamed = F.rename_path(tree / "a.txt", "renamed.txt")
    assert Path(renamed).name == "renamed.txt"
    assert not (tree / "a.txt").exists()
    with pytest.raises(ValueError):
        F.rename_path(renamed, "bad/name.txt")


def test_unique_path(tmp_path):
    f = tmp_path / "x.txt"
    assert F.unique_path(f) == f                    # free name unchanged
    f.write_text("1")
    assert F.unique_path(f).name == "x (1).txt"
