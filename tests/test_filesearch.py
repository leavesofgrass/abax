"""Recursive file search: name globs, content grep, filters, bounds."""

from __future__ import annotations

import pytest

from abax.core import filesearch as S


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / "alpha.txt").write_text("hello world\nsecond line\n")
    (tmp_path / "beta.log").write_text("error: boom\nok\n")
    (tmp_path / "notes.md").write_text("nothing here")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "gamma.txt").write_text("deep hello\n")
    (sub / "big.bin").write_bytes(b"\x00" * 4096)
    hidden = tmp_path / ".secret"
    hidden.write_text("hidden hello")
    return tmp_path


def test_name_glob_recurses(tree):
    hits = S.search(tree, name_glob="*.txt")
    names = sorted(p.path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for p in hits)
    assert names == ["alpha.txt", "gamma.txt"]


def test_directories_included_and_excluded(tree):
    with_dirs = S.search(tree, name_glob="sub")
    assert any(m.is_dir for m in with_dirs)
    without = S.search(tree, name_glob="sub", include_dirs=False)
    assert without == []


def test_content_substring_search(tree):
    hits = S.search(tree, name_glob="*", contains="hello")
    files = {m.path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for m in hits}
    assert "alpha.txt" in files and "gamma.txt" in files
    assert all(not m.is_dir for m in hits)            # content search = files only
    a = next(m for m in hits if m.path.endswith("alpha.txt"))
    assert a.line_no == 1 and "hello world" in a.line


def test_content_regex(tree):
    hits = S.search(tree, name_glob="*.log", contains=r"error:\s*\w+", regex=True)
    assert len(hits) == 1 and "boom" in hits[0].line


def test_case_sensitivity(tree):
    assert S.search(tree, name_glob="*", contains="HELLO", ignore_case=True)
    assert S.search(tree, name_glob="*", contains="HELLO", ignore_case=False) == []


def test_binary_file_yields_nothing(tree):
    assert S.search(tree, name_glob="big.bin", contains="hello") == []


def test_size_filter(tree):
    big = S.search(tree, name_glob="*", min_size=1000, include_dirs=False)
    assert [m.path for m in big] and all(m.size >= 1000 for m in big)
    assert any(m.path.endswith("big.bin") for m in big)


def test_hidden_excluded_by_default(tree):
    assert S.search(tree, name_glob="*", contains="hello",
                    show_hidden=False) and not any(
        ".secret" in m.path for m in S.search(tree, name_glob="*", contains="hello"))
    assert any(".secret" in m.path
               for m in S.search(tree, name_glob="*", contains="hello", show_hidden=True))


def test_max_depth(tree):
    shallow = S.search(tree, name_glob="*.txt", max_depth=1)
    assert all("sub" not in m.path for m in shallow)


def test_limit_caps_results(tree):
    capped = S.search(tree, name_glob="*", limit=2)
    assert len(capped) == 2
