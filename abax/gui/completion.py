"""Token-aware function autocomplete for the formula bar.

Wraps a ``QCompleter`` but drives it from :mod:`abax.core.completion` so the
popup completes the *current function token* (not the whole field) and includes
user-defined functions. The completion logic itself is the tested core; this is
the thin Qt adapter.
"""

from __future__ import annotations

from ._qtcompat import QCompleter, QStringListModel, Qt


class FormulaCompleter:
    """Token-aware formula autocomplete for a ``QLineEdit``.

    ``context`` is an optional zero-arg callable returning ``(names, sheets)`` —
    the workbook's defined names and sheet names — so completion offers those
    alongside function names.
    """

    def __init__(self, line_edit, context=None) -> None:
        self._le = line_edit
        self._context = context
        self._completer = QCompleter([], line_edit)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setWidget(line_edit)
        self._completer.activated.connect(self._insert)
        line_edit.textEdited.connect(self._on_edited)

    def _on_edited(self, text: str) -> None:
        from ..core.completion import complete, current_token

        cursor = self._le.cursorPosition()
        names, sheets = self._context() if self._context else ((), ())
        candidates = complete(text, cursor, names=names, sheets=sheets)
        if not candidates:
            self._completer.popup().hide()
            return
        token, _ = current_token(text, cursor)
        self._completer.setModel(QStringListModel(candidates, self._completer))
        self._completer.setCompletionPrefix(token)
        self._completer.complete()

    def _insert(self, name: str) -> None:
        from ..core.completion import apply_completion

        text = self._le.text()
        cursor = self._le.cursorPosition()
        new_text, new_cursor = apply_completion(text, cursor, name)
        self._le.setText(new_text)
        self._le.setCursorPosition(new_cursor)
