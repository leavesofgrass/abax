"""Background workers (QObject-based, moveToThread pattern).

Only imported on the GUI path, so importing Qt here is acceptable. Workers
never touch widgets and never raise across the thread boundary — they emit an
``error`` signal instead (spec §7, §8).
"""

from __future__ import annotations

from .gui._qtcompat import QObject, pyqtSignal


class IOWorker(QObject):
    """Loads or saves a document off the main thread.

    Wire ``finished`` to ``thread.quit`` and ``deleteLater`` in the window
    (see spec §7 for the canonical wiring).
    """

    progress = pyqtSignal(int)
    result = pyqtSignal(object)  # emits a Document or Workbook
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, op: str, path: str, document=None) -> None:
        super().__init__()
        self._op = op  # "open" | "save"
        self._path = path
        self._document = document

    def run(self) -> None:
        try:
            from .engine.document import Document

            if self._op == "open":
                self.progress.emit(10)
                doc = Document.open(self._path)
                self.progress.emit(90)
                self.result.emit(doc)
            elif self._op == "save":
                if self._document is None:
                    raise ValueError("save requires a document")
                self.progress.emit(10)
                self._document.save(self._path)
                self.progress.emit(90)
                self.result.emit(self._document)
            else:  # pragma: no cover - guarded by callers
                raise ValueError(f"unknown op: {self._op}")
        except Exception as exc:  # never raise across the thread boundary
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class FuncWorker(QObject):
    """Runs an arbitrary zero-arg callable off the main thread.

    Same signal contract as :class:`IOWorker` (so the GUI's ``_run_io`` lifecycle
    handles both). Used for work that isn't a plain Document open/save — e.g. the
    streaming CSV import. The callable must touch no Qt widgets and return a
    plain value (it is emitted via ``result``).
    """

    progress = pyqtSignal(int)
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.progress.emit(10)
            res = self._fn()
            self.progress.emit(90)
            self.result.emit(res)
        except Exception as exc:  # never raise across the thread boundary
            self.error.emit(str(exc))
        finally:
            self.finished.emit()
