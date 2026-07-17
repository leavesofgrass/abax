"""Token-aware function autocomplete for the formula bar.

Wraps a ``QCompleter`` but drives it from :mod:`abax.core.completion` so the
popup completes the *current function token* (not the whole field) and includes
user-defined functions. The completion logic itself is the tested core; this is
the thin Qt adapter.

**Tab accepts.** While the popup is open, Tab (and Enter, via QCompleter's own
handling) inserts the highlighted candidate — an event filter on both the line
edit and the popup catches Tab before it moves focus.
"""

from __future__ import annotations

from ._qtcompat import QCompleter, QEvent, QObject, QStringListModel, Qt


class FormulaCompleter(QObject):
    """Token-aware formula autocomplete for a ``QLineEdit``.

    ``context`` is an optional zero-arg callable returning ``(names, sheets)`` —
    the workbook's defined names and sheet names — so completion offers those
    alongside function names.
    """

    def __init__(self, line_edit, context=None) -> None:
        super().__init__(line_edit)
        self._le = line_edit
        self._context = context
        self._completer = QCompleter([], line_edit)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setWidget(line_edit)
        self._completer.activated.connect(self._insert)
        line_edit.textEdited.connect(self._on_edited)
        # Tab must accept the highlighted candidate instead of moving focus —
        # filter it on both the field and the popup (whichever holds the event).
        # The popup itself is created LAZILY on the first completion: calling
        # QCompleter.popup() constructs a parentless top-level QListView, and
        # creating one per window at construction is exactly the stray window
        # that armed the test fixture's teardown double-free (see conftest.py's
        # _dispose_leaked_qt_windows). Until a completion pops, there is no
        # popup — and nothing to filter.
        line_edit.installEventFilter(self)
        self._popup_wired = False

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt override)
        if (event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab)
                and self._popup_wired
                and self._completer.popup().isVisible()):
            popup = self._completer.popup()
            index = popup.currentIndex()
            name = (index.data() if index.isValid()
                    else self._completer.currentCompletion())
            popup.hide()
            if name:
                self._insert(name)
            return True                      # consume: no focus change
        return super().eventFilter(obj, event)

    def _on_edited(self, text: str) -> None:
        from ..core.completion import complete, current_token

        cursor = self._le.cursorPosition()
        names, sheets = self._context() if self._context else ((), ())
        candidates = complete(text, cursor, names=names, sheets=sheets)
        if not candidates:
            if self._popup_wired:            # never create the popup just to hide it
                self._completer.popup().hide()
            return
        token, _ = current_token(text, cursor)
        self._completer.setModel(QStringListModel(candidates, self._completer))
        self._completer.setCompletionPrefix(token)
        if not self._popup_wired:
            # First completion for this field: the popup now has to exist —
            # create it once and give it the Tab-accept filter.
            self._completer.popup().installEventFilter(self)
            self._popup_wired = True
        self._completer.complete()

    def _insert(self, name: str) -> None:
        from ..core.completion import apply_completion

        text = self._le.text()
        cursor = self._le.cursorPosition()
        new_text, new_cursor = apply_completion(text, cursor, name)
        self._le.setText(new_text)
        self._le.setCursorPosition(new_cursor)
