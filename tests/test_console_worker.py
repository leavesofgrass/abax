"""Out-of-process console worker — `Worker.handle` is pure (no subprocess needed)."""

from __future__ import annotations

from abax.console_worker import Worker
from abax.core.workbook import Workbook


def _env():
    return Workbook().to_envelope()


def test_workbook_round_trips():
    w = Worker()
    r = w.handle("put('A1', '5')", _env())
    assert Workbook.from_envelope(r["envelope"]).sheet.get("A1") == 5


def test_variables_persist_across_commands():
    w = Worker()
    r1 = w.handle("x = 21", _env())
    r2 = w.handle("print(x * 2)", r1["envelope"])
    assert r2["output"].strip() == "42"


def test_error_is_captured_not_fatal():
    w = Worker()
    r = w.handle("1 / 0", _env())
    assert "ZeroDivisionError" in r["output"]
    r2 = w.handle("print('still alive')", r["envelope"])   # worker survives
    assert "still alive" in r2["output"]


def test_exit_is_ignored():
    w = Worker()
    r = w.handle("exit()", _env())
    assert "ignored" in r["output"].lower()


# --- op=script (sandbox Phase 1: the script runner's path) --------------------


def test_script_runs_and_round_trips():
    w = Worker()
    r = w.handle_script("put('A1', '5')\nprint('done', cell('A1'))", "s.py", _env())
    assert r["error"] is None
    assert "done 5" in r["output"]
    assert Workbook.from_envelope(r["envelope"]).sheet.get("A1") == 5


def test_script_gets_fresh_namespace_and_file():
    w = Worker()
    w.handle("leak = 1", _env())                       # console variable
    r = w.handle_script("print(__name__, __file__)\nprint('leak' in dir())",
                        "myscript.py", _env())
    assert "abax_script myscript.py" in r["output"]
    assert "False" in r["output"]                       # console vars don't leak in


def test_script_error_is_reported_not_fatal():
    w = Worker()
    r = w.handle_script("boom()", "s.py", _env())
    assert r["error"] is not None and "NameError" in r["error"]
    r2 = w.handle_script("print('alive')", "s.py", _env())
    assert "alive" in r2["output"]


# --- op=macro (sandbox Phase 1: the macro runner's path) ----------------------


def _macro_file(tmp_path, body):
    f = tmp_path / "m.py"
    f.write_text(body, encoding="utf-8")
    return str(f)


def test_macro_loads_runs_and_logs(tmp_path):
    f = _macro_file(tmp_path, (
        "@macro\n"
        "def double(ctx):\n"
        "    ctx.set('A1', 21)\n"
        "    ctx.set('A2', '=A1*2')\n"
        "    ctx.log('doubled')\n"
    ))
    w = Worker()
    r = w.handle_macro("double", [f], None, _env())
    assert r["error"] is None
    assert "doubled" in r["output"]
    wb = Workbook.from_envelope(r["envelope"])
    assert wb.sheet.get("A2") == 42


def test_macro_cursor_reaches_context(tmp_path):
    f = _macro_file(tmp_path, (
        "@macro\n"
        "def where(ctx):\n"
        "    ctx.log(f'at {ctx.cursor}')\n"
    ))
    w = Worker()
    r = w.handle_macro("where", [f], [2, 3], _env())
    assert "at (2, 3)" in r["output"]


def test_macro_missing_is_an_error_not_a_crash(tmp_path):
    f = _macro_file(tmp_path, "@macro\ndef real(ctx):\n    pass\n")
    w = Worker()
    r = w.handle_macro("nope", [f], None, _env())
    assert r["error"] is not None and "no such macro" in r["error"]


def test_dispatch_routes_ops(tmp_path):
    w = Worker()
    assert "42" in w.dispatch({"op": "exec", "code": "print(42)",
                               "envelope": _env()})["output"]
    assert "43" in w.dispatch({"op": "script", "code": "print(43)", "path": "s.py",
                               "envelope": _env()})["output"]
    f = _macro_file(tmp_path, "@macro\ndef hi(ctx):\n    ctx.log('44')\n")
    assert "44" in w.dispatch({"op": "macro", "macro": "hi", "files": [f],
                               "cursor": None, "envelope": _env()})["output"]
    # No op defaults to the console path (wire-compat with old parents).
    assert "45" in w.dispatch({"code": "print(45)", "envelope": _env()})["output"]


# --- startup: the stray-print sink ------------------------------------------
#
# The worker reserves the real stdout pipe for framing and sends stray prints
# (from imports, say) to a sink, so they cannot corrupt the frame stream.
# `open(os.devnull, "w")` is the usual way and works everywhere except the one
# place this worker most needs it: inside a Windows AppContainer, opening `nul`
# is denied, so the confined worker died at startup with PermissionError before
# serving a frame. The parent saw only "no frame came back" (#6).


def test_discarding_stdout_prefers_a_real_file():
    """The unconfined path keeps a genuine file object, so anything reaching
    for sys.stdout.fileno() still gets one."""
    from abax.console_worker import _discarding_stdout

    sink = _discarding_stdout()
    try:
        assert sink.fileno() >= 0
    finally:
        sink.close()


def test_discarding_stdout_survives_a_denied_devnull(monkeypatch):
    """The AppContainer case, simulated: opening the device is refused."""
    import abax.console_worker as cw

    def _denied(*args, **kwargs):
        raise PermissionError(13, "Permission denied", "nul")

    monkeypatch.setattr(cw, "open", _denied, raising=False)
    sink = cw._discarding_stdout()          # must not raise
    assert sink.write("swallowed") == len("swallowed")
    assert sink.writable() is True


def test_the_sink_really_discards(capsys):
    """A print into it neither raises nor reaches real stdout.

    That second half is the point: the whole reason for the sink is that a
    stray print must not reach the pipe the frame protocol owns.
    """
    import contextlib

    from abax.console_worker import _NullWriter

    sink = _NullWriter()
    with contextlib.redirect_stdout(sink):
        print("this must vanish")
    assert capsys.readouterr().out == ""
    # Write-only by design; a reader would imply it was buffering somewhere.
    assert sink.readable() is False
