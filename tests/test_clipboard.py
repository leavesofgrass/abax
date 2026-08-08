"""Clipboard history manager and OS clipboard bridge."""

from __future__ import annotations

import io
import subprocess

import pytest

import abax.core.clipboard as clip
from abax._runtime import console_encoding
from abax.core.clipboard import ClipboardManager, ClipEntry


def test_add_order_newest_first():
    m = ClipboardManager()
    m.add("a")
    m.add("b")
    m.add("c")
    assert [e.text for e in m.entries()] == ["c", "b", "a"]


def test_add_returns_entry_blank_ignored():
    m = ClipboardManager()
    assert m.add("hello") is not None
    assert m.add("") is None
    assert m.add("   \n\t ") is None
    assert [e.text for e in m.entries()] == ["hello"]


def test_dedup_moves_to_front_keeps_pin():
    m = ClipboardManager()
    m.add("a")
    m.add("b")
    m.add("c")
    m.pin(m.entries().index(next(e for e in m.entries() if e.text == "a")))
    # 'a' is now pinned; re-adding it should keep the pin and move to front.
    m.add("a")
    texts = [e.text for e in m.entries()]
    # only one 'a'
    assert texts.count("a") == 1
    a = next(e for e in m.entries() if e.text == "a")
    assert a.pinned is True


def test_capacity_eviction_keeps_pinned():
    m = ClipboardManager(capacity=3)
    for ch in "abcde":
        m.add(ch)
    # newest 3 unpinned survive: e, d, c
    assert [e.text for e in m.entries()] == ["e", "d", "c"]

    m2 = ClipboardManager(capacity=2)
    m2.add("keep")
    # pin "keep" by index in entries()
    m2.pin([e.text for e in m2.entries()].index("keep"), True)
    for ch in "xyz":
        m2.add(ch)
    texts = [e.text for e in m2.entries()]
    # pinned "keep" survives despite capacity=2 of unpinned (z, y)
    assert "keep" in texts
    unpinned = [e.text for e in m2.entries() if not e.pinned]
    assert unpinned == ["z", "y"]
    # pinned first
    assert m2.entries()[0].text == "keep"


def test_pin_remove():
    m = ClipboardManager()
    m.add("a")
    m.add("b")
    m.pin(0)  # pin "b" (front)
    assert m.entries()[0].pinned is True
    m.pin(0, False)
    assert m.entries()[0].pinned is False
    m.remove(0)
    assert [e.text for e in m.entries()] == ["a"]


def test_clear_keep_pinned_true():
    m = ClipboardManager()
    m.add("a")
    m.add("b")
    m.add("c")
    # pin "b"
    m.pin([e.text for e in m.entries()].index("b"))
    m.clear(keep_pinned=True)
    assert [e.text for e in m.entries()] == ["b"]


def test_clear_keep_pinned_false():
    m = ClipboardManager()
    m.add("a")
    m.add("b")
    m.pin(0)
    m.clear(keep_pinned=False)
    assert m.entries() == []


def test_get_index():
    m = ClipboardManager()
    m.add("a")
    m.add("b")
    assert m.get(0).text == "b"
    assert m.get(1).text == "a"
    assert m.get(5) is None
    assert m.get(-1) is None


def test_auto_label_simple():
    e = ClipEntry(text="hello world")
    assert e.label == "hello world"


def test_auto_label_first_nonempty_line():
    e = ClipEntry(text="\n\n   first line  \nsecond")
    assert e.label == "first line"


def test_auto_label_truncation_ellipsis():
    text = "x" * 50
    e = ClipEntry(text=text)
    assert e.label == "x" * 40 + "…"
    assert len(e.label) == 41


def test_explicit_label_preserved():
    e = ClipEntry(text="hello", label="my label")
    assert e.label == "my label"


def test_entry_round_trip():
    e = ClipEntry(text="hi", label="L", pinned=True)
    d = e.to_dict()
    assert d == {"text": "hi", "label": "L", "pinned": True}
    e2 = ClipEntry.from_dict(d)
    assert (e2.text, e2.label, e2.pinned) == ("hi", "L", True)


def test_manager_round_trip_with_pins():
    m = ClipboardManager(capacity=7)
    m.add("a")
    m.add("b")
    m.add("c")
    m.pin([e.text for e in m.entries()].index("b"))
    d = m.to_dict()
    m2 = ClipboardManager.from_dict(d)
    assert m2.capacity == 7
    assert [e.text for e in m2.entries()] == [e.text for e in m.entries()]
    b = next(e for e in m2.entries() if e.text == "b")
    assert b.pinned is True
    # round-trip preserves stored order/pins exactly
    assert m2.to_dict() == d


def test_copy_returns_status_string(monkeypatch):
    monkeypatch.setattr(clip, "os_copy", lambda text: True)
    assert clip.copy("hi") == "copied"


def test_copy_falls_back_to_osc52(monkeypatch):
    monkeypatch.setattr(clip, "os_copy", lambda text: False)
    buf = io.StringIO()
    monkeypatch.setattr(clip.sys, "stdout", buf)
    status = clip.copy("hello")
    assert status == "copied (OSC 52)"
    out = buf.getvalue()
    assert out  # OSC 52 sequence was written
    assert "\033]52;c;" in out


def test_osc52_runs_without_raising(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(clip.sys, "stdout", buf)
    clip.osc52("some text")  # must not raise
    assert "\033]52;c;" in buf.getvalue()


# --- the codec on the helper's pipes ---------------------------------------
#
# The clipboard bridge round-trips the user's own text, so it is the likeliest
# non-ASCII string in abax — and the right codec is a property of the *tool*,
# not of our locale. wl-copy/wl-paste speak Wayland's
# ``text/plain;charset=utf-8`` and xclip/xsel exchange ``UTF8_STRING``, so
# those pipes are UTF-8 under a latin-1 LC_ALL too; the Windows console tools
# and pbcopy/pbpaste follow the locale. One codec for all of them is wrong for
# one group or the other, whichever one is picked.


def _spy_on_subprocess(monkeypatch) -> dict:
    """Capture the kwargs of the next ``subprocess.run`` inside the bridge."""
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(clip.subprocess, "run", fake_run)
    return seen


@pytest.mark.parametrize("cmd", [
    ["wl-copy"],
    ["wl-paste", "-n"],
    ["xclip", "-selection", "clipboard"],
    ["xclip", "-selection", "clipboard", "-o"],
    ["xsel", "-b", "-i"],
    ["xsel", "-b", "-o"],
])
def test_wayland_and_x11_helpers_are_utf8_whatever_the_locale(monkeypatch, cmd):
    """These four are UTF-8 by protocol, so the parent's locale is not the answer."""
    seen = _spy_on_subprocess(monkeypatch)
    clip._run(cmd, "héllo Ω")
    assert seen["kwargs"]["encoding"] == "utf-8", (
        f"{cmd[0]} exchanges UTF-8 by protocol; got "
        f"{seen['kwargs']['encoding']!r}")
    assert seen["kwargs"]["errors"] == "replace"


@pytest.mark.parametrize("cmd", [
    ["clip"],
    ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
    ["pbcopy"],
    ["pbpaste"],
])
def test_console_and_locale_driven_helpers_use_the_shared_policy(monkeypatch, cmd):
    """Windows' console tools and pbcopy/pbpaste follow the locale/codepage.

    Pinned to ``console_encoding()`` rather than to a literal: hardcoding
    "utf-8" would be the same defect with a nicer-looking default, and
    hardcoding "oem" would be wrong off Windows.
    """
    seen = _spy_on_subprocess(monkeypatch)
    clip._run(cmd)
    assert seen["kwargs"]["encoding"] == console_encoding()
    assert seen["kwargs"]["errors"] == "replace"


def test_a_windows_exe_suffix_does_not_change_the_tool(monkeypatch):
    """``shutil.which`` can hand back ``wl-copy.exe`` (WSL/MSYS); still UTF-8."""
    seen = _spy_on_subprocess(monkeypatch)
    clip._run(["C:/msys64/usr/bin/wl-copy.EXE"], "x")
    assert seen["kwargs"]["encoding"] == "utf-8"
