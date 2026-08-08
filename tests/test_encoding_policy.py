"""The text-encoding policy: nothing in :mod:`abax` may leave an encoding implicit.

abax has now been bitten twice by the same defect. Issue #1 was
:mod:`abax.settings` reading a UTF-8 ``settings.json`` back as the platform
locale and silently mojibaking the user's config. Issue #5 is
``abax.sandbox_windows._icacls`` decoding ``icacls`` output as strict UTF-8 —
``icacls`` writes the console OEM codepage, and ``ci.yml`` sets ``PYTHONUTF8=1``
for every job, so one non-ASCII byte in an ACL principal name (localised Windows
installs have them as a matter of course: *Administratoren*, *Utilisateurs*,
*Администраторы*) raises ``UnicodeDecodeError``. That escapes ``_icacls``'s
``except (OSError, subprocess.SubprocessError)`` as an unexpected type, and on
the *revoke* path a teardown that raises rather than returning ``False`` leaks
the machine-wide ALL-APPLICATION-PACKAGES grant the sandbox exists to clean up.

Two different defects hide under one description, and they do not take the same
fix — see :mod:`abax._runtime`'s "text encoding policy" section. This module
covers both, plus a sweep that stops the eighth occurrence:

* ``test_state_*`` — the file half. abax writes the state journal and reads it
  back, so it is a contract between abax and itself: UTF-8 on both sides.
* ``test_icacls_*`` — the subprocess half, and issue #5 specifically.
* ``test_console_pipe_*`` / ``test_pandoc_pipe_*`` — the subprocess half at
  every *other* site. These judge the **value**, which is the whole content of
  the fix: ``encoding="utf-8"`` in ``shell.run`` would satisfy "an encoding is
  named" and still be the exact bug issue #5 was.
* ``test_no_implicit_encoding_in_what_this_repo_ships`` — the class, not the
  instance. A new call site that forgets fails here.

**Why the state tests run in child processes.** Under ``PYTHONUTF8=1``
``read_text()`` defaults to UTF-8 *anyway*, so a test that merely round-trips a
file through the current interpreter passes on CI whether or not the bug is
present — that is precisely the trap the issue #1 fix fell into. Two independent
mechanisms are used so the tests can go red in **both** environments:

1. ``-X warn_default_encoding`` (PEP 597). The interpreter reports every
   ``open``/``read_text``/``write_text`` that omitted ``encoding=``, and it does
   so *regardless* of UTF-8 mode — verified: a ``PYTHONUTF8=1`` child still
   emits ``EncodingWarning``. This is the environment-independent guarantee.
2. A child with ``PYTHONUTF8=0``/``PYTHONCOERCECLOCALE=0``/``LC_ALL=C``, which
   forces a non-UTF-8 platform default (cp1252 on Windows, ascii under the C
   locale elsewhere). This is the *semantic* test: real non-ASCII content, real
   silent data loss. Where the platform refuses to give us a non-UTF-8 default
   the check cannot be expressed at all and reports that rather than passing
   quietly; mechanism 1 still covers those machines.
"""

from __future__ import annotations

import ast
import codecs
import json
import locale
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

import abax
from abax import sandbox_windows as sw
from abax.core import clipboard, fmbuttons, latexmath, shell
from abax.engine import convert

_PKG_ROOT = Path(abax.__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parent


# --------------------------------------------------------------------------- #
# child-process helpers
# --------------------------------------------------------------------------- #


def _run_child(script: str, *, flags: "list[str]" = (), env_overrides: dict | None = None):
    """Run *script* in a fresh interpreter and return the CompletedProcess.

    The script is written to a real file rather than passed with ``-c``: Python
    source is decoded as UTF-8 by language definition (PEP 3120), whereas a
    command line is decoded with the platform default — which is exactly the
    variable these tests are manipulating.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    for k, v in (env_overrides or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    d = tempfile.mkdtemp(prefix="abax-enc-")
    path = Path(d) / "child.py"
    path.write_bytes(textwrap.dedent(script).encode("utf-8"))
    return subprocess.run(
        [sys.executable, *flags, str(path)],
        capture_output=True, encoding="utf-8", errors="replace", timeout=180,
        env=env, cwd=d,
    )


def _child_json(proc) -> dict:
    assert proc.returncode == 0, (
        f"child exited {proc.returncode}\n--- stdout ---\n{proc.stdout}"
        f"\n--- stderr ---\n{proc.stderr}"
    )
    line = proc.stdout.strip().splitlines()[-1]
    return json.loads(line)


# --------------------------------------------------------------------------- #
# the file half: abax.state's write-ahead journal
# --------------------------------------------------------------------------- #


_STATE_WARN_CHILD = """
    import json, sys, tempfile, warnings
    from pathlib import Path

    # Import first, then arm the filter: a third-party import that forgets an
    # encoding is not what this test is about.
    from abax.state import StateManager

    root = Path(tempfile.mkdtemp())
    p = root / "state.json"
    # Both files must already exist: EncodingWarning is emitted when the text
    # wrapper is built, which is *after* the open fails on a missing file.
    p.write_bytes(json.dumps({"seen": 1}).encode("utf-8"))
    (root / "state.journal").write_bytes(
        json.dumps({"key": "seen", "value": 2}).encode("utf-8"))

    offenders = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mgr = StateManager.load(p)      # read_text x2 (journal replay + state)
        mgr.set("last_file", "x")       # write_text  (journal)
        mgr.flush()                     # write_text  (state)
    for w in caught:
        if issubclass(w.category, EncodingWarning):
            offenders.append({"file": str(w.filename), "line": w.lineno,
                              "msg": str(w.message)})

    sys.stdout.write(json.dumps({
        "warn_default_encoding": bool(sys.flags.warn_default_encoding),
        "utf8_mode": sys.flags.utf8_mode,
        "offenders": offenders,
    }, ensure_ascii=True) + "\\n")
"""


@pytest.mark.parametrize("utf8_mode", ["0", "1"])
def test_state_journal_never_uses_the_platform_default_encoding(utf8_mode):
    """Every read/write in :mod:`abax.state` names its encoding — in both modes.

    ``PYTHONUTF8`` is parameterised deliberately. CI sets it to 1 workflow-wide,
    which makes the default *happen* to be UTF-8 and hides the defect from any
    round-trip assertion; PEP 597's warning fires either way, so this is the one
    check that is red on every machine abax runs on.
    """
    proc = _run_child(_STATE_WARN_CHILD, flags=["-X", "warn_default_encoding"],
                      env_overrides={"PYTHONUTF8": utf8_mode})
    report = _child_json(proc)
    assert report["warn_default_encoding"], "child did not enable -X warn_default_encoding"
    assert report["offenders"] == [], (
        "abax.state read/wrote text without naming an encoding:\n"
        + "\n".join(f"  {o['file']}:{o['line']}  {o['msg']}" for o in report["offenders"])
    )


_STATE_ROUNDTRIP_CHILD = """
    import json, locale, sys, tempfile
    from pathlib import Path

    from abax.state import StateManager

    default = getattr(locale, "getencoding", None)
    default = default() if default else locale.getpreferredencoding(False)

    # A non-ASCII path, the way the state file actually carries one (the
    # last-opened workbook). U+0301 is deliberate: its UTF-8 encoding contains
    # 0x81, which is *undefined* in cp1252 and out of range for ascii, so a
    # mis-decode raises rather than silently mojibaking - either way the value
    # is lost, because StateManager.load swallows the exception.
    value = "D:/\u00dcnterlagen/r\u00e9sum\u00e9\u0301.abax"

    root = Path(tempfile.mkdtemp())
    p = root / "state.json"
    p.write_bytes(json.dumps({"last_file": value}, ensure_ascii=False).encode("utf-8"))
    loaded = StateManager.load(p).get("last_file")

    # ...and the same through the crash-replay path. No main state file here,
    # deliberately: StateManager.load replays the journal into _state and then
    # assigns _state = json.loads(<main file>), so a readable main file discards
    # the replayed entry outright. That clobber is a real defect but it is not
    # an *encoding* defect - it reproduces with a pure-ASCII value - so this
    # test stays inside the scenario where replay is observable rather than
    # asserting behaviour the journal has never had.
    p2 = root / "s2.json"
    (root / "s2.journal").write_bytes(
        json.dumps({"key": "last_file", "value": value},
                   ensure_ascii=False).encode("utf-8"))
    replayed = StateManager.load(p2).get("last_file")

    sys.stdout.write(json.dumps({
        "default_encoding": default,
        "utf8_mode": sys.flags.utf8_mode,
        "state_ok": loaded == value,
        "journal_ok": replayed == value,
        "loaded": loaded,
        "replayed": replayed,
    }, ensure_ascii=True) + "\\n")
"""


def test_state_round_trips_a_non_ascii_path_under_a_non_utf8_default():
    """A non-ASCII value survives the journal even when the platform default is not UTF-8.

    This is the consequence test for the file half: ``StateManager.load``
    swallows every exception, so a mis-decode does not surface as an error — the
    user's last-opened file just silently disappears from the state.
    """
    proc = _run_child(_STATE_ROUNDTRIP_CHILD, env_overrides={
        "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C", "LANG": "C",
    })
    report = _child_json(proc)
    codec = report["default_encoding"].lower().replace("-", "").replace("_", "")
    if report["utf8_mode"] or codec in ("utf8", "cp65001"):
        pytest.skip(
            "this platform gives a UTF-8 default even with PYTHONUTF8=0/LC_ALL=C "
            f"(got {report['default_encoding']!r}), so the mis-decode cannot be "
            "expressed here; test_state_journal_never_uses_the_platform_default_"
            "encoding covers this machine instead"
        )
    assert report["state_ok"], (
        f"state file lost its non-ASCII value under default encoding "
        f"{report['default_encoding']!r}: got {report['loaded']!r}"
    )
    assert report["journal_ok"], (
        f"journal replay lost its non-ASCII value under default encoding "
        f"{report['default_encoding']!r}: got {report['replayed']!r}"
    )


# --------------------------------------------------------------------------- #
# the file half, part two: files written *before* the contract was pinned
#
# Naming UTF-8 on both sides fixes every file abax writes from now on and
# breaks every file it already wrote. The old writer used the platform default,
# so a state.json from a cp1252 Windows box is cp1252 on disk, and a strict
# UTF-8 read of it raises on the first accented character. ``load`` swallows
# that — losing the whole dict, not the one key — and ``flush`` then writes the
# empty dict back. Upgrading abax would have deleted the file it could not
# read. Hence the one-shot locale fallback in ``abax.state._read_text``.
# --------------------------------------------------------------------------- #


_LEGACY_STATE = {
    "last_file": "C:/Users/José/Documents/budsjett-år.abax",
    "last_sheet": 3,
    "window": {"w": 1280, "h": 800},
}


def _write_legacy_cp1252(path: Path, mapping: dict) -> None:
    """Write *mapping* the way pre-fix abax wrote it on a cp1252 machine.

    ``Path.write_text`` with no ``encoding=`` — literally what ``StateManager``
    used to call — encodes with the platform default, so on a Western-European
    Windows install the bytes on disk are cp1252. Spelled out as bytes rather
    than produced by an unencoded ``write_text`` so the file is cp1252 on every
    host running this suite, CI's ``PYTHONUTF8=1`` included.
    """
    path.write_bytes(json.dumps(mapping, ensure_ascii=False).encode("cp1252"))


@pytest.fixture()
def cp1252_default(monkeypatch):
    """Make the legacy fallback resolve to cp1252 regardless of the host.

    The fallback asks ``locale.getpreferredencoding(False)``, which answers for
    *this* interpreter: under ``PYTHONUTF8=1`` (every CI job) it says UTF-8, and
    a cp1252 file would be undecodable by both codecs. Naming the codec here is
    what lets these tests assert the migration on a Linux runner and a Windows
    box alike — the file on disk is real cp1252 either way, and the code under
    test is unmodified.
    """
    import abax.state as state_mod

    monkeypatch.setattr(state_mod.locale, "getpreferredencoding",
                        lambda do_setlocale=True: "cp1252")
    return state_mod


def test_a_legacy_locale_encoded_state_file_still_loads(tmp_path, cp1252_default):
    """Every key of a pre-fix state.json survives the upgrade.

    The blast radius is what makes this worth a test of its own: it is not the
    accented value that goes missing, it is ``last_sheet`` and ``window`` and
    everything else in the file, because ``load`` assigns the whole dict at
    once and its ``except`` covers the entire read-and-parse.
    """
    from abax._runtime import read_text_utf8
    from abax.state import StateManager

    p = tmp_path / "state.json"
    _write_legacy_cp1252(p, _LEGACY_STATE)
    assert b"Jos\xe9" in p.read_bytes()          # cp1252 on disk, not UTF-8
    with pytest.raises(UnicodeDecodeError):      # ...and strict UTF-8 refuses it
        read_text_utf8(p)

    mgr = StateManager.load(p)
    assert mgr.get("last_file") == _LEGACY_STATE["last_file"]
    assert mgr.get("last_sheet") == 3
    assert mgr.get("window") == {"w": 1280, "h": 800}


def test_a_legacy_state_file_heals_itself_on_the_next_flush(tmp_path, cp1252_default):
    """One save migrates the file, so the fallback is taken exactly once.

    This is why the fallback is a fallback and not a second supported encoding:
    ``flush`` always writes UTF-8, so the legacy shape cannot outlive the first
    save and nothing has to keep guessing at it.
    """
    from abax._runtime import read_text_utf8
    from abax.state import StateManager

    p = tmp_path / "state.json"
    _write_legacy_cp1252(p, _LEGACY_STATE)
    StateManager.load(p).flush()

    # Strict UTF-8 now suffices — there is no legacy byte left to fall back on.
    # (``json.dumps`` escapes non-ASCII by default, so what ``flush`` wrote is
    # pure ASCII; that is UTF-8 by construction, and it is what makes the
    # migration one-way.)
    assert json.loads(read_text_utf8(p)) == _LEGACY_STATE
    assert b"Jos\xe9" not in p.read_bytes()      # the cp1252 byte is gone
    assert not p.read_bytes().startswith(b"\xef\xbb\xbf")   # and no BOM
    assert StateManager.load(p).get("last_file") == _LEGACY_STATE["last_file"]


def test_a_legacy_journal_replays_instead_of_being_dropped(tmp_path, cp1252_default):
    """The journal is the same contract, and the same legacy files exist for it.

    No main state file here, deliberately: ``load`` replays the journal into
    ``_state`` and then assigns over it, so replay is only observable when the
    main file is absent.
    """
    from abax.state import StateManager

    p = tmp_path / "state.json"
    _write_legacy_cp1252(p.with_suffix(".journal"),
                         {"key": "last_file", "value": _LEGACY_STATE["last_file"]})

    assert StateManager.load(p).get("last_file") == _LEGACY_STATE["last_file"]


def test_utf8_wins_over_the_legacy_fallback(tmp_path, cp1252_default):
    """A decodable UTF-8 file never reaches the fallback — order matters.

    Try the locale first and today's files mojibake instead: ``José`` read as
    cp1252 is a perfectly valid ``JosÃ©`` that nothing downstream can flag.
    """
    from abax.state import StateManager

    p = tmp_path / "state.json"
    p.write_bytes(json.dumps(_LEGACY_STATE, ensure_ascii=False).encode("utf-8"))
    assert StateManager.load(p).get("last_file") == _LEGACY_STATE["last_file"]


_LEGACY_MIGRATION_CHILD = """
    import json, locale, sys, tempfile
    from pathlib import Path

    from abax.state import StateManager

    default = getattr(locale, "getencoding", None)
    default = default() if default else locale.getpreferredencoding(False)

    state = {"last_file": "C:/Users/Jos\u00e9/Documents/budsjett-\u00e5r.abax",
             "last_sheet": 3}
    root = Path(tempfile.mkdtemp())
    p = root / "state.json"

    # The pre-fix writer, verbatim: write_text with no encoding=. Where the
    # platform default cannot hold the value this raises - which means abax
    # could never have written such a file on this host either, so there is
    # nothing here to migrate and the test says so rather than passing quietly.
    wrote = True
    try:
        p.write_text(json.dumps(state, ensure_ascii=False))
    except UnicodeEncodeError:
        wrote = False

    loaded = healed = None
    if wrote:
        mgr = StateManager.load(p)
        loaded = {"last_file": mgr.get("last_file"), "last_sheet": mgr.get("last_sheet")}
        mgr.flush()
        healed = json.loads(p.read_bytes().decode("utf-8"))   # strict: UTF-8 now

    sys.stdout.write(json.dumps({
        "default_encoding": default,
        "utf8_mode": sys.flags.utf8_mode,
        "wrote": wrote,
        "expected": state,
        "loaded": loaded,
        "healed": healed,
    }, ensure_ascii=True) + "\\n")
"""


def test_a_legacy_state_file_migrates_under_a_real_non_utf8_locale():
    """The same migration with nothing patched: real locale, real legacy writer.

    The in-process tests above name the codec themselves so they can run on any
    host. This one takes the platform's word for it — a child with
    ``PYTHONUTF8=0``/``LC_ALL=C`` writes the file the way abax used to, then a
    fresh ``StateManager`` reads it — which is the only version of this that
    also proves ``locale.getpreferredencoding`` is the right question to ask.
    """
    proc = _run_child(_LEGACY_MIGRATION_CHILD, env_overrides={
        "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0", "LC_ALL": "C", "LANG": "C",
    })
    report = _child_json(proc)
    codec = report["default_encoding"].lower().replace("-", "").replace("_", "")
    if report["utf8_mode"] or codec in ("utf8", "cp65001"):
        pytest.skip(
            "this platform gives a UTF-8 default even with PYTHONUTF8=0/LC_ALL=C "
            f"(got {report['default_encoding']!r}), so it has no legacy files to "
            "migrate; the cp1252 tests above cover the fallback here"
        )
    if not report["wrote"]:
        pytest.skip(
            f"the pre-fix writer could not encode a non-ASCII state file under "
            f"{report['default_encoding']!r} either (UnicodeEncodeError, swallowed "
            "by flush), so no such file exists on this host to migrate"
        )
    assert report["loaded"] == report["expected"], (
        f"a state file written under {report['default_encoding']!r} lost keys on "
        f"load: {report['loaded']}"
    )
    assert report["healed"] == report["expected"], (
        f"flush did not rewrite the migrated file as UTF-8: {report['healed']}"
    )


# --------------------------------------------------------------------------- #
# the subprocess half: issue #5, abax.sandbox_windows._icacls
# --------------------------------------------------------------------------- #


def _undecodable(*_a, **_kw):
    """What ``subprocess.run(text=True)`` raises on an OEM byte under strict UTF-8."""
    raise UnicodeDecodeError("utf-8", b"Administratoren\xfc", 15, 16, "invalid start byte")


def test_icacls_returns_false_when_the_child_output_cannot_be_decoded(monkeypatch):
    """Issue #5: a non-ASCII ACL principal must not escape ``_icacls`` as an exception.

    Every other ``_icacls`` failure mode degrades to ``False``. A decode failure
    must too, or ``_revoke_container_access`` aborts partway and leaves the
    ALL-APPLICATION-PACKAGES grant on the interpreter prefix with nothing left
    to revert it.
    """
    monkeypatch.setattr(sw.subprocess, "run", _undecodable)
    assert sw._icacls("C:/some/path", "/remove", sw.ALL_APP_PACKAGES) is False


def test_revoke_container_access_never_raises_on_undecodable_output(monkeypatch):
    """The teardown path must complete every revoke even if one cannot be decoded.

    This is the leak: ``_revoke_container_access`` is what reverts a
    machine-wide ACL grant, and it is called from ``cleanup_process`` and from
    the failure handler in ``custom_spawn``. It has no second chance.
    """
    monkeypatch.setattr(sw.subprocess, "run", _undecodable)
    sw._revoke_container_access(["C:/a", "C:/b", "C:/c"])  # must not raise


def test_icacls_decodes_the_console_codepage_and_never_strictly(monkeypatch):
    """``_icacls`` names a console encoding and replaces undecodable bytes.

    Widening the ``except`` alone would turn issue #5 from a crash into "every
    ACL operation silently fails on a localised Windows install", which is the
    same leak by a quieter route. The grant/revoke must actually *work* there,
    so the decode must not be able to fail in the first place.

    ``tests/test_sandbox_windows.py::_ace_lines`` already reads ``icacls`` with
    ``encoding="oem", errors="replace"`` (147eb6f); this pins the shipping code
    to the same choice so the two cannot drift apart.
    """
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(sw.subprocess, "run", fake_run)
    assert sw._icacls("C:/some/path", "/grant", "*S-1-15-2-1:(OI)(CI)(RX)") is True

    kwargs = seen["kwargs"]
    assert kwargs.get("errors") == "replace", (
        "icacls output is only ever compared or discarded; an odd byte must not "
        f"be able to fail the call (errors={kwargs.get('errors')!r})"
    )
    enc = kwargs.get("encoding")
    assert enc, "no encoding= given, so the decode is the platform default"
    # Pinned to the shared policy rather than to a literal: hardcoding "utf-8"
    # here would be the same bug with a nicer-looking default, and hardcoding
    # "oem" would be wrong off Windows (where console_encoding() correctly
    # returns the locale's codec, which on a modern POSIX box *is* UTF-8).
    assert enc == sw.console_encoding(), (
        f"_icacls picks its own codec ({enc!r}) instead of the shared "
        f"console_encoding() policy ({sw.console_encoding()!r})"
    )
    if sys.platform == "win32":
        assert str(enc).lower() == "oem", (
            "must agree with tests/test_sandbox_windows.py::_ace_lines, which "
            f"reads the same command as OEM (got {enc!r})"
        )


@pytest.mark.skipif(sys.platform != "win32", reason="icacls is Windows-only")
def test_icacls_still_succeeds_against_a_real_path(tmp_path):
    """The chosen codec must not break the ordinary path: real ``icacls``, real ACL."""
    assert sw._icacls(str(tmp_path)) is True


# --------------------------------------------------------------------------- #
# every other pipe: the codec's *value*, per site
# --------------------------------------------------------------------------- #
#
# ``_icacls`` above is one of seven call sites the encoding fix touched, and it
# was the only one with a test. The AST sweep at the bottom of this file is not
# a substitute: it asserts that an ``encoding=`` keyword exists and never looks
# at what it says, so swapping ``console_encoding()`` for ``"utf-8"`` in
# ``shell.run`` — reintroducing issue #5 verbatim — leaves it green. These pin
# the value at each site, the way ``test_icacls_decodes_the_console_codepage``
# does: no real child is ever spawned, so they run everywhere.
#
# The discriminator is a *sentinel* codec injected into the module under test
# rather than a comparison against the real ``console_encoding()``. Comparing
# against the real value is nearly vacuous off Windows, where the policy
# legitimately answers "utf-8" and so a hardcoded ``"utf-8"`` would agree with
# it; patching proves the site asks the shared policy at call time, which is
# the property that actually keeps the sites from drifting apart.

_SENTINEL_CODEC = "cp1252"      # a real codec, and never what any site hardcodes


class _Recorder:
    """A ``subprocess.run`` stand-in: records the call, reports success."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode
        self.cmd = None
        self.kwargs = None

    def __call__(self, cmd, **kwargs):
        self.cmd, self.kwargs = cmd, kwargs
        return subprocess.CompletedProcess(cmd, self.returncode,
                                           self.stdout, self.stderr)


def _only_windows_clipboard_tools(m):
    """Pin the clipboard bridge to its Windows branch on any host.

    ``os_copy``/``os_paste`` probe PATH and take the first tool they find, so
    which branch runs would otherwise depend on the test machine \u2014 and the
    branches do not share a codec. ``clip``/``Get-Clipboard`` are the console
    programs this policy is about; the POSIX helpers are not console programs
    at all (wl-copy/wl-paste offer ``text/plain;charset=utf-8``, xclip/xsel
    exchange ``UTF8_STRING``), so their pipes are UTF-8 whatever the locale and
    ``console_encoding()`` would be the wrong answer for them. That half is
    pinned in ``tests/test_clipboard.py``.
    """
    m.setattr(clipboard.os, "name", "nt")
    m.setattr(clipboard.shutil, "which",
              lambda name: f"C:/Windows/System32/{name}.exe"
              if name in ("clip", "powershell") else None)


def _invoke_clipboard(m):
    _only_windows_clipboard_tools(m)
    clipboard.os_copy("R\u00e9sum\u00e9")


def _invoke_clipboard_paste(m):
    _only_windows_clipboard_tools(m)
    clipboard.os_paste()


def _invoke_shell(m):
    shell.run("echo hi")


def _invoke_fmbuttons(m):
    fmbuttons.run_button(
        fmbuttons.Button("Git status", "git status -s"),
        fmbuttons.Context(directory=tempfile.gettempdir()),
    )


def _invoke_icacls(m):
    sw._icacls("C:/some/path", "/grant", "*S-1-15-2-1:(OI)(CI)(RX)")


_CONSOLE_SITES = [
    pytest.param(clipboard, _invoke_clipboard, id="clipboard.os_copy"),
    pytest.param(clipboard, _invoke_clipboard_paste, id="clipboard.os_paste"),
    pytest.param(shell, _invoke_shell, id="shell.run"),
    pytest.param(fmbuttons, _invoke_fmbuttons, id="fmbuttons.run_button"),
    pytest.param(sw, _invoke_icacls, id="sandbox_windows._icacls"),
]


@pytest.mark.parametrize("mod,invoke", _CONSOLE_SITES)
def test_console_pipe_decodes_with_the_shared_console_policy(mod, invoke, monkeypatch):
    """Each console child's pipes are decoded with ``console_encoding()``, replacing.

    The children here — ``clip``/``Get-Clipboard``, ``cmd /s /c ...``, a file
    manager button's arbitrary command, ``icacls`` — write the console codepage.
    Two things must hold at every one of them and neither is visible to a static
    sweep: the codec comes from the shared policy (so Windows gets OEM, not the
    UTF-8 that CI's ``PYTHONUTF8=1`` would otherwise impose), and the decode is
    non-strict (so an undecodable byte costs one U+FFFD, not the feature).
    """
    with monkeypatch.context() as m:
        rec = _Recorder()
        m.setattr(mod.subprocess, "run", rec)
        m.setattr(mod, "console_encoding", lambda: _SENTINEL_CODEC)
        invoke(m)

    assert rec.kwargs is not None, (
        f"{mod.__name__} never reached subprocess.run - the test invokes the "
        "wrong path and would pass however the encoding is spelled"
    )
    assert rec.kwargs.get("encoding") == _SENTINEL_CODEC, (
        f"{mod.__name__} does not decode its console pipe with the shared "
        f"console_encoding() policy (got encoding="
        f"{rec.kwargs.get('encoding')!r}); a literal codec here is issue #5 "
        "again - it is UTF-8 under PYTHONUTF8=1 that broke icacls"
    )
    assert rec.kwargs.get("errors") == "replace", (
        f"{mod.__name__} decodes strictly (errors="
        f"{rec.kwargs.get('errors')!r}); one byte the console codepage cannot "
        "map then raises instead of degrading to U+FFFD"
    )

    # ...and the unpatched call really does carry the policy's live answer,
    # which on Windows is the OEM codepage the console actually writes.
    with monkeypatch.context() as m:
        real = _Recorder()
        m.setattr(mod.subprocess, "run", real)
        invoke(m)
    assert real.kwargs.get("encoding") == mod.console_encoding()
    if sys.platform == "win32":
        assert str(real.kwargs.get("encoding")).lower() == "oem"


def _invoke_latexmath(m):
    m.setattr(latexmath, "pandoc_available", lambda: True)
    m.setattr(latexmath, "_pandoc_binary", lambda: "pandoc")
    latexmath.to_mathml("x^2")


def _invoke_convert(m):
    m.setattr(convert.pandoc, "pandoc_path", lambda: "pandoc")
    convert.pandoc_convert("in.md", "out.docx")


_PANDOC_SITES = [
    pytest.param(latexmath, _invoke_latexmath, id="latexmath.to_mathml"),
    pytest.param(convert, _invoke_convert, id="convert.pandoc_convert"),
]


@pytest.mark.parametrize("mod,invoke", _PANDOC_SITES)
def test_pandoc_pipe_is_utf8_whatever_the_locale_says(mod, invoke, monkeypatch):
    """pandoc's pipes are UTF-8 by protocol — the one place a literal is correct.

    pandoc reads and writes UTF-8 regardless of locale, so these two sites are
    deliberately *not* on ``console_encoding()``: following the console codepage
    here would be the same class of bug approached from the other side, and on
    Windows it would decode pandoc's UTF-8 output as OEM. The platform default
    is forced to a non-UTF-8 codec for the duration, so that mistake — and a
    plain omission — is red on every platform rather than only on Windows.
    """
    with monkeypatch.context() as m:
        rec = _Recorder(stdout="<math xmlns='http://www.w3.org/1998/Math/MathML'>"
                               "<mi>x</mi></math>")
        m.setattr(mod.subprocess, "run", rec)
        m.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "cp1252")
        invoke(m)

    assert rec.kwargs is not None, (
        f"{mod.__name__} never reached subprocess.run - the test invokes the "
        "wrong path and would pass however the encoding is spelled"
    )
    enc = rec.kwargs.get("encoding")
    assert enc is not None, (
        f"{mod.__name__} leaves pandoc's pipes to the platform default; under "
        "PYTHONUTF8=1 that is strict UTF-8 (issue #5) and under a legacy "
        "locale it mojibakes pandoc's UTF-8 output"
    )
    assert codecs.lookup(enc).name == "utf-8", (
        f"{mod.__name__} decodes pandoc as {enc!r}; pandoc speaks UTF-8 by "
        "protocol, so this must be the literal codec and not the console one"
    )
    assert rec.kwargs.get("errors") == "replace", (
        f"{mod.__name__} decodes strictly (errors={rec.kwargs.get('errors')!r}); "
        "both of these paths exist to produce a fallback or an error message, "
        "and neither may become a UnicodeDecodeError on the way there"
    )


def test_shell_decodes_partial_timeout_output_with_the_console_codepage(monkeypatch):
    """The timeout path decodes the same way the success path does.

    ``TimeoutExpired`` carries whatever the child managed to write, as *bytes*.
    A bare ``.decode()`` there defaults to UTF-8 and mojibakes exactly the
    output the non-timeout branch two lines up gets right — a split-brain that
    only shows up on the slow, already-unhappy path.
    """
    def timing_out(*_a, **_kw):
        raise subprocess.TimeoutExpired(
            cmd="x", timeout=0.1, output=b"caf\xe9\r\n", stderr=b"erreur \xe9chec")

    with monkeypatch.context() as m:
        m.setattr(shell.subprocess, "run", timing_out)
        m.setattr(shell, "console_encoding", lambda: _SENTINEL_CODEC)
        result = shell.run("x", timeout=0.1)

    assert result.returncode == 124
    assert result.stdout == "caf\u00e9\r\n", (
        f"timed-out stdout was not decoded with console_encoding() "
        f"(got {result.stdout!r}; UTF-8 would give 'caf\\ufffd')"
    )
    assert "erreur \u00e9chec" in result.stderr, (
        f"timed-out stderr was not decoded with console_encoding() "
        f"(got {result.stderr!r})"
    )
    assert "timed out after 0.1s" in result.stderr


# --------------------------------------------------------------------------- #
# the class: no eighth occurrence
# --------------------------------------------------------------------------- #


_SUBPROCESS_CALLS = {"run", "Popen", "check_output", "check_call", "call"}


def _keyword(call: ast.Call, name: str):
    for kw in call.keywords:
        if kw.arg == name:
            return kw
    return None


def _is_true(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _mode_literal(call: ast.Call) -> "str | None":
    """The literal ``mode`` of an ``open``-like call; ``None`` when not a literal.

    An omitted mode is ``"r"`` — text — so it returns ``""``.
    """
    node = None
    if len(call.args) >= 2:
        node = call.args[1]
    else:
        kw = _keyword(call, "mode")
        if kw is not None:
            node = kw.value
        else:
            return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _scan_source(path: Path) -> "list[str]":
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name, attribute = func.attr, True
        elif isinstance(func, ast.Name):
            name, attribute = func.id, False
        else:
            continue
        has_encoding = _keyword(node, "encoding") is not None
        if attribute and name in _SUBPROCESS_CALLS:
            text = _keyword(node, "text")
            legacy = _keyword(node, "universal_newlines")
            in_text_mode = ((text is not None and _is_true(text.value))
                            or (legacy is not None and _is_true(legacy.value)))
            if in_text_mode and not has_encoding:
                found.append(f"{path}:{node.lineno}: subprocess.{name}(text=True) "
                             "without encoding=")
        elif name in ("read_text", "write_text") and attribute and not has_encoding:
            found.append(f"{path}:{node.lineno}: .{name}() without encoding=")
        elif name == "open" and not has_encoding:
            mode = _mode_literal(node)
            if mode is None:
                continue                      # computed mode - can't judge statically
            if attribute and mode == "":
                continue                      # e.g. tarfile.open / Document.open
            if "b" not in mode:
                found.append(f"{path}:{node.lineno}: open(mode={mode!r}) "
                             "without encoding=")
    return found


# The scripts that *build* and *launch* what ships. Scoping the sweep to the
# `abax` package alone is what let make_pyz.py sit on `read_text()` — it parsed
# pyz_main.py, Python source, with the platform default, so the build of
# abax.pyz died with UnicodeDecodeError under an ASCII default (`LC_ALL=C`, i.e.
# a clean container) over the em dash in that file's docstring. Code that runs
# on a user's machine or produces the artifact that does belongs in the class.
#
# Still out: tests/, conftest.py, scripts/, benchmarks/ and macros/ — dev-only
# helpers whose failure never reaches a user, and `build/`, `_stage/`, `dist/`
# and `site/`, which are stale generated copies of the source that must never be
# scanned at all. (All four dev trees were swept by hand when this widened and
# were clean; none of them is load-bearing enough to gate the suite on.)
_SHIPPED_SCRIPTS = ("make_pyz.py", "launcher.py", "pyz_main.py")
_SHIPPED_DIRS = ("packaging",)


def _policy_paths() -> "list[Path]":
    """Every ``.py`` file the no-implicit-encoding policy governs."""
    paths = [p for p in _PKG_ROOT.rglob("*.py") if "__pycache__" not in p.parts]
    paths += [_REPO_ROOT / name for name in _SHIPPED_SCRIPTS]
    for name in _SHIPPED_DIRS:
        paths += [p for p in (_REPO_ROOT / name).rglob("*.py")
                  if "__pycache__" not in p.parts]
    return sorted(p for p in paths if p.is_file())


def test_no_implicit_encoding_in_what_this_repo_ships():
    """No shipping module may leave a text encoding to the platform default.

    Two encoding incidents came from exactly one omission each, in a codebase
    where ~40 other call sites spell it out by hand. Grepping caught them only
    after they shipped; this catches the next one at review time.

    A site that genuinely wants the platform default may say so explicitly —
    ``encoding=locale.getpreferredencoding(False)`` satisfies this and documents
    the intent, which is the whole point.
    """
    paths = _policy_paths()
    offenders: list[str] = []
    for path in paths:
        offenders.extend(_scan_source(path))
    assert len(paths) > 200, f"scanned only {len(paths)} files - wrong root {_PKG_ROOT}?"
    assert offenders == [], (
        f"{len(offenders)} site(s) leave the text encoding implicit:\n"
        + "\n".join("  " + o for o in offenders)
    )


def test_the_sweep_covers_the_build_and_entry_scripts():
    """The widened root stays widened.

    ``make_pyz.py`` was missed for exactly one reason: nothing outside the
    ``abax`` package was ever scanned. A silent regression to package-only scope
    would re-open that hole while the sweep above still passed, so name the
    files rather than trusting the glob.
    """
    scanned = {p.name for p in _policy_paths()}
    for name in _SHIPPED_SCRIPTS:
        assert name in scanned, f"{name} dropped out of the encoding sweep"
    assert {"launch_abax.py", "launch_worker.py"} <= scanned, (
        "packaging/ launchers dropped out of the encoding sweep"
    )


_MAKE_PYZ_WARN_CHILD = """
    import json, sys, warnings

    # Import first, then arm the filter - as in the state child, an import that
    # forgets an encoding is not what this test is about.
    import make_pyz

    offenders = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        make_pyz.verify_bootstrap_stdlib_only()     # reads pyz_main.py
    for w in caught:
        if issubclass(w.category, EncodingWarning):
            offenders.append({"file": str(w.filename), "line": w.lineno,
                              "msg": str(w.message)})

    sys.stdout.write(json.dumps({
        "warn_default_encoding": bool(sys.flags.warn_default_encoding),
        "offenders": offenders,
    }, ensure_ascii=True) + "\\n")
"""


def test_the_pyz_build_reads_python_source_without_a_platform_default():
    """``make_pyz`` must not decode ``pyz_main.py`` with the platform's codec.

    Python source is UTF-8 by language definition (PEP 3120), and
    ``pyz_main.py`` proves it: its docstring carries a U+2014 EM DASH, so the
    file is not ASCII-decodable. Reading it with the platform default made the
    build of the shipped ``abax.pyz`` die with ``UnicodeDecodeError`` wherever
    that default is ASCII — a container under ``LC_ALL=C`` — and mojibake in
    silence on cp1252.

    PEP 597 rather than a round-trip, for the reason the module docstring gives:
    a round-trip cannot fail on a machine whose default happens to decode the
    bytes (every Windows box, and every box under ``PYTHONUTF8=1``), which is
    most of them. This is red on all of them.
    """
    proc = _run_child(_MAKE_PYZ_WARN_CHILD, flags=["-X", "warn_default_encoding"])
    report = _child_json(proc)
    assert report["warn_default_encoding"], "child did not enable -X warn_default_encoding"
    assert report["offenders"] == [], (
        "make_pyz read text without naming an encoding:\n"
        + "\n".join(f"  {o['file']}:{o['line']}  {o['msg']}" for o in report["offenders"])
    )


def test_the_encoding_sweep_can_actually_detect_an_offender(tmp_path):
    """The sweep above is only worth having if it fails on a real offender."""
    bad = tmp_path / "bad.py"
    bad.write_text(textwrap.dedent("""
        import subprocess
        from pathlib import Path

        def f(p):
            Path(p).write_text("x")
            subprocess.run(["icacls", p], capture_output=True, text=True)
            with open(p, "w") as fh:
                fh.write("x")
    """), encoding="utf-8")
    found = _scan_source(bad)
    assert len(found) == 3, found

    good = tmp_path / "good.py"
    good.write_text(textwrap.dedent("""
        import subprocess
        import tarfile
        from pathlib import Path

        def f(p):
            Path(p).write_text("x", encoding="utf-8")
            subprocess.run(["icacls", p], capture_output=True, text=True,
                           encoding="oem", errors="replace")
            subprocess.run(["x"], capture_output=True)      # bytes: fine
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("x")
            with open(p, "wb") as fh:
                fh.write(b"x")
            with tarfile.open(p) as tf:
                tf.getnames()
    """), encoding="utf-8")
    assert _scan_source(good) == []
