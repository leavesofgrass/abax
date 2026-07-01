"""Configurable command buttons: placeholder expansion + running."""

from __future__ import annotations

from abax.core import fmbuttons as B


def _ctx(tmp_path):
    sel = [str(tmp_path / "a b.txt"), str(tmp_path / "c.txt")]
    return B.Context(directory=str(tmp_path), selection=sel,
                     dest_dir=str(tmp_path / "other"))


def test_expand_placeholders(tmp_path):
    ctx = _ctx(tmp_path)
    assert B.expand("{name}", ctx) == "a b.txt"
    assert B.expand("{stem}", ctx) == "a b"
    assert B.expand("{ext}", ctx) == ".txt"
    # paths with spaces are quoted
    assert B.expand("open {path}", ctx) == f'open "{tmp_path / "a b.txt"}"'
    # {sel} joins every selection, quoting as needed
    expanded = B.expand("zip out.zip {sel}", ctx)
    assert '"' in expanded and "c.txt" in expanded and "a b.txt" in expanded


def test_expand_dir_and_dest(tmp_path):
    ctx = _ctx(tmp_path)
    assert str(tmp_path) in B.expand("cd {dir}", ctx)
    assert "other" in B.expand("cp {path} {dest}", ctx)


def test_expand_empty_selection(tmp_path):
    ctx = B.Context(directory=str(tmp_path))
    assert B.expand("x {path} {name} {sel}", ctx) == "x   "


def test_button_roundtrip():
    b = B.Button("Zip", "zip {sel}", confirm=True, capture=False)
    again = B.Button.from_dict(b.to_dict())
    assert again == b


def test_run_button_captures_output(tmp_path):
    res = B.run_button(B.Button("echo", "echo hello-fm"), _ctx(tmp_path))
    assert res.ok
    assert "hello-fm" in res.stdout


def test_run_button_reports_failure(tmp_path):
    res = B.run_button(B.Button("bad", "this_command_does_not_exist_xyz"),
                       _ctx(tmp_path))
    assert not res.ok                                  # non-zero return code


def test_run_button_runs_in_directory(tmp_path):
    sub = tmp_path / "work"
    sub.mkdir()
    marker = sub / "here.txt"
    marker.write_text("x")
    cmd = "dir" if __import__("os").name == "nt" else "ls"
    res = B.run_button(B.Button("list", cmd),
                       B.Context(directory=str(sub), selection=[]))
    assert res.ok and "here.txt" in res.stdout


def test_default_buttons_are_valid():
    buttons = B.default_buttons()
    assert buttons and all(isinstance(x, B.Button) for x in buttons)
    assert all(x.label and x.command for x in buttons)
