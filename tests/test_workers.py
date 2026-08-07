"""Background IOWorker / FuncWorker: the off-thread signal contract.

These two QObjects are the only things abax runs on a QThread, and their whole
contract is "never raise across the thread boundary — emit ``error`` instead"
(spec §7, §8). The tests below call ``run()`` directly to pin the exact signal
*sequence* on every success and failure path, then wire one of each through a
real ``QThread`` to prove the canonical ``finished`` → ``thread.quit`` wiring
terminates and that the payload reaches the main thread.

Deterministic by construction: the threaded tests join with ``QThread.wait``
(a bounded, explicit join) and never sleep to synchronise. Skips cleanly
without a Qt binding.
"""

from __future__ import annotations

import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.cellstore import WindowedCellStore  # noqa: E402
from abax.core.workbook import Workbook  # noqa: E402
from abax.engine.document import Document  # noqa: E402
from abax.gui._qtcompat import QApplication, QObject, QThread  # noqa: E402
from abax.workers import FuncWorker, IOWorker  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Log:
    """Records every signal a worker emits, in emission order.

    Connected before ``run()``; since the worker still lives in the calling
    thread the connections are direct, so the recorded order is the emission
    order with no event loop in the way.
    """

    def __init__(self, worker):
        self.events: list[tuple[str, object]] = []
        worker.progress.connect(lambda pct: self.events.append(("progress", pct)))
        worker.result.connect(lambda obj: self.events.append(("result", obj)))
        worker.error.connect(lambda msg: self.events.append(("error", msg)))
        worker.finished.connect(lambda: self.events.append(("finished", None)))

    @property
    def kinds(self) -> list[str]:
        return [k for k, _ in self.events]

    def payloads(self, kind: str) -> list:
        return [v for k, v in self.events if k == kind]

    def one(self, kind: str):
        vals = self.payloads(kind)
        assert len(vals) == 1, f"expected exactly one {kind!r}, got {vals!r}"
        return vals[0]


def _csv(tmp_path, name: str = "in.csv", text: str = "a,b\n1,2\n3,4\n"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def _native(tmp_path, name: str = "book.abax"):
    """A small native (.abax) file — the format that windows *during* load."""
    wb = Workbook()
    wb.sheet.set_cell(0, 0, "21")
    wb.sheet.set_cell(0, 1, "=A1*2")
    p = tmp_path / name
    wb.save_json(p)
    return p


# --- IOWorker: open ----------------------------------------------------------


def test_open_emits_progress_then_result_then_finished(tmp_path):
    worker = IOWorker("open", str(_csv(tmp_path)))
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "progress", "result", "finished"]
    assert log.payloads("progress") == [10, 90]


def test_open_delivers_a_loaded_document(tmp_path):
    p = _csv(tmp_path, text="a,b\n1,2\n")
    worker = IOWorker("open", str(p))
    log = _Log(worker)
    worker.run()
    doc = log.one("result")
    assert isinstance(doc, Document)
    assert doc.path == p
    assert doc.dirty is False
    assert doc.workbook.sheet.get_raw(1, 0) == "1"


def test_open_of_a_missing_file_errors_before_reaching_90(tmp_path):
    """The failure surfaces as ``error`` — and the progress bar never claims 90%."""
    worker = IOWorker("open", str(tmp_path / "nope.csv"))
    log = _Log(worker)
    worker.run()                                    # must not raise
    assert log.kinds == ["progress", "error", "finished"]
    assert log.payloads("progress") == [10]
    assert "nope.csv" in log.one("error")


def test_open_of_an_unsupported_extension_names_the_extension(tmp_path):
    p = tmp_path / "data.unknownext"
    p.write_text("whatever", encoding="utf-8")
    worker = IOWorker("open", str(p))
    log = _Log(worker)
    worker.run()
    assert log.payloads("result") == []
    assert "unsupported file type" in log.one("error")
    assert ".unknownext" in log.one("error")


def test_open_of_an_empty_path_is_an_error_not_a_crash():
    """An empty path has no suffix, so the loader rejects it — via ``error``."""
    worker = IOWorker("open", "")
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "error", "finished"]
    assert "unsupported file type" in log.one("error")


def test_windowed_capacity_is_applied_during_the_load(tmp_path):
    """The setting rides into ``Document.open`` so the sheet is windowed AT LOAD.

    Observable two ways: the policy is retained on the document (undo/redo
    re-apply it) and the sheet's store is the bounded one.
    """
    worker = IOWorker("open", str(_native(tmp_path)), windowed_capacity=4)
    log = _Log(worker)
    worker.run()
    doc = log.one("result")
    assert doc.windowed_capacity == 4
    store = doc.workbook.sheet._cells
    assert isinstance(store, WindowedCellStore) and store.capacity == 4
    assert doc.workbook.sheet.get_value(0, 1) == 42.0   # values survive windowing
    store.close()                                        # drop the spill file


def test_default_capacity_leaves_a_small_sheet_on_the_plain_store(tmp_path):
    worker = IOWorker("open", str(_native(tmp_path)))
    log = _Log(worker)
    worker.run()
    doc = log.one("result")
    assert doc.windowed_capacity == 0                    # the "auto" policy
    assert not isinstance(doc.workbook.sheet._cells, WindowedCellStore)


# --- IOWorker: save ----------------------------------------------------------


def test_save_writes_the_file_and_emits_the_same_document(tmp_path):
    doc = Document(Workbook())
    doc.workbook.sheet.set_cell(0, 0, "=2*21")
    out = tmp_path / "out.abax"
    worker = IOWorker("save", str(out), doc)
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "progress", "result", "finished"]
    assert log.one("result") is doc                      # identity, not a copy
    assert out.exists()
    assert Workbook.load_json(out).sheet.get_value(0, 0) == 42.0
    assert doc.path == out and doc.dirty is False


def test_save_without_a_document_errors_before_any_progress(tmp_path):
    """The guard fires ahead of ``progress(10)``, so the bar never even starts."""
    worker = IOWorker("save", str(tmp_path / "out.abax"))
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["error", "finished"]
    assert log.one("error") == "save requires a document"
    assert not (tmp_path / "out.abax").exists()


def test_failed_save_keeps_the_document_dirty(tmp_path):
    """A save that blows up must not fake success — dirty/path stay as they were."""
    doc = Document(Workbook())
    doc.mark_dirty()
    worker = IOWorker("save", str(tmp_path / "out.zzz"), doc)
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "error", "finished"]
    assert "unsupported file type" in log.one("error")
    assert doc.dirty is True and doc.path is None


def test_save_into_a_missing_directory_is_reported(tmp_path):
    doc = Document(Workbook())
    worker = IOWorker("save", str(tmp_path / "no" / "such" / "dir" / "out.abax"), doc)
    log = _Log(worker)
    worker.run()
    assert log.payloads("result") == []
    assert log.kinds[-1] == "finished"
    assert log.one("error")                              # a non-empty OS message


# --- IOWorker: op guard ------------------------------------------------------


def test_unknown_op_is_reported_not_raised(tmp_path):
    worker = IOWorker("frobnicate", str(_csv(tmp_path)))
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["error", "finished"]
    assert log.one("error") == "unknown op: frobnicate"


# --- FuncWorker --------------------------------------------------------------


def test_func_worker_emits_the_callables_return_value():
    worker = FuncWorker(lambda: {"rows": 3})
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "progress", "result", "finished"]
    assert log.one("result") == {"rows": 3}


def test_func_worker_is_not_run_at_construction():
    calls = []
    worker = FuncWorker(lambda: calls.append(1))
    assert calls == []                                   # constructing is inert
    worker.run()
    assert calls == [1]


def test_func_worker_emits_a_none_result_rather_than_skipping_it():
    """``result`` fires even for a callable that returns nothing, so the GUI's
    success callback (and therefore the busy-state teardown) always runs."""
    worker = FuncWorker(lambda: None)
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "progress", "result", "finished"]
    assert log.one("result") is None


def test_func_worker_converts_an_exception_into_an_error_signal():
    def boom():
        raise RuntimeError("streaming import failed")

    worker = FuncWorker(boom)
    log = _Log(worker)
    worker.run()                                         # must not raise
    assert log.kinds == ["progress", "error", "finished"]
    assert log.one("error") == "streaming import failed"


def test_func_worker_reports_an_exception_with_no_message_as_empty_text():
    """``str(exc)`` can be empty; the worker still signals *error*, not success —
    the caller must never mistake a blank message for a completed run."""
    def boom():
        raise RuntimeError()

    worker = FuncWorker(boom)
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "error", "finished"]
    assert log.one("error") == ""
    assert log.payloads("result") == []


def test_func_worker_with_a_non_callable_reports_it():
    worker = FuncWorker(None)
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "error", "finished"]
    assert "not callable" in log.one("error")


def test_only_exception_is_trapped_but_finished_still_fires():
    """``except Exception`` deliberately lets a BaseException through (a
    KeyboardInterrupt must still kill the process) — the ``finally`` guarantees
    ``finished`` fires anyway, so the GUI's busy state is always released."""
    def interrupted():
        raise KeyboardInterrupt

    worker = FuncWorker(interrupted)
    log = _Log(worker)
    with pytest.raises(KeyboardInterrupt):
        worker.run()
    assert log.kinds == ["progress", "finished"]


# --- the shared contract (MainWindow._run_io drives both) --------------------


@pytest.mark.parametrize("kind", ["io", "func"])
def test_both_workers_share_one_success_signal_shape(kind, tmp_path):
    worker = (IOWorker("open", str(_csv(tmp_path))) if kind == "io"
              else FuncWorker(lambda: "ok"))
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "progress", "result", "finished"]
    assert log.payloads("progress") == [10, 90]


@pytest.mark.parametrize("kind", ["io", "func"])
def test_both_workers_share_one_failure_signal_shape(kind, tmp_path):
    def boom():
        raise OSError("disk on fire")

    worker = (IOWorker("open", str(tmp_path / "gone.csv")) if kind == "io"
              else FuncWorker(boom))
    log = _Log(worker)
    worker.run()
    assert log.kinds == ["progress", "error", "finished"]
    assert log.payloads("result") == []
    assert isinstance(log.one("error"), str) and log.one("error")


# --- on a real QThread (the canonical wiring) --------------------------------


class _Sink(QObject):
    """Main-thread receiver: records payloads and the thread they arrived on."""

    def __init__(self):
        super().__init__()
        self.results: list = []
        self.errors: list[str] = []
        self.progress: list[int] = []
        self.idents: list[int] = []

    def on_result(self, obj):
        self.results.append(obj)
        self.idents.append(threading.get_ident())

    def on_error(self, msg):
        self.errors.append(msg)
        self.idents.append(threading.get_ident())

    def on_progress(self, pct):
        self.progress.append(pct)


def _run_on_thread(app, worker, sink, timeout_s: float = 10.0) -> None:
    """The spec §7 wiring: started→run, finished→quit, then an explicit join.

    Nothing here sleeps. ``done`` is set by a direct (in-worker-thread)
    connection, so waiting on it is a real blocking join on the worker's body;
    ``processEvents`` then runs the *queued* ``thread.quit`` (the QThread object
    lives on the main thread, so its slot is invoked here), ``QThread.wait``
    joins the OS thread, and a final ``processEvents`` drains the payload
    signals the worker queued back to us.
    """
    done = threading.Event()
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.finished.connect(done.set)
    worker.result.connect(sink.on_result)
    worker.error.connect(sink.on_error)
    worker.progress.connect(sink.on_progress)
    thread.start()
    assert done.wait(timeout_s), "worker never emitted finished"
    app.processEvents()
    assert thread.wait(int(timeout_s * 1000)), "worker thread did not exit"
    app.processEvents()
    assert thread.isFinished()


def test_func_worker_runs_off_the_calling_thread_and_reports_back(app):
    ran_on = {}

    def work():
        ran_on["ident"] = threading.get_ident()
        return "payload"

    worker = FuncWorker(work)
    sink = _Sink()
    _run_on_thread(app, worker, sink)
    assert ran_on["ident"] != threading.get_ident()      # genuinely off-thread
    assert sink.results == ["payload"]
    assert sink.idents == [threading.get_ident()]        # delivered on the main thread
    assert sink.progress == [10, 90]
    assert sink.errors == []


def test_io_worker_builds_a_document_off_thread(app, tmp_path):
    p = _csv(tmp_path, text="x,y\n5,6\n")
    worker = IOWorker("open", str(p))
    sink = _Sink()
    _run_on_thread(app, worker, sink)
    assert sink.errors == []
    doc, = sink.results
    assert doc.workbook.sheet.get_raw(1, 0) == "5"
    assert doc.path == p


def test_a_failing_worker_still_quits_its_thread(app, tmp_path):
    """``finished`` fires on the error path too, so ``finished``→``quit`` always
    stops the thread — a failed load can never strand it (``_run_io`` frees the
    busy state on ``thread.finished``)."""
    worker = IOWorker("save", str(tmp_path / "out.abax"))   # no document
    sink = _Sink()
    _run_on_thread(app, worker, sink)                       # asserts isFinished()
    assert sink.results == []
    assert sink.errors == ["save requires a document"]
