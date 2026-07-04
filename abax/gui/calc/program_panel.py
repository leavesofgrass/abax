"""A small keystroke-program run/step panel for the RPN calculators.

Sits beside a Voyager faceplate (any of the HP-12C/15C/16C keypads) and gives it
HP program memory: **record** captures every key you press into a
:class:`~abax.core.calc.program.Program`, **Run** executes it from the top
(bounded by a step cap so an infinite loop can't hang the UI), **Step** runs a
single instruction (HP ``SST``), and the listing mirrors the program back like
the real ``P/R`` display.

The panel is deliberately model-agnostic: it drives whatever keypad it is handed
(``faceplate.keypad``), so it works with every RPN faceplate unchanged. It is a
plain :class:`QWidget`, so the integrator can drop it into the calculator window
(a dock, a tab, or below the faceplate) however they like — this module wires no
menus itself.

Qt comes through the binding shim (:mod:`abax.gui._qtcompat`) like the rest of
the GUI, so it runs on PySide6 or PyQt6 unchanged.
"""

from __future__ import annotations

from .._qtcompat import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from ...core.calc.program import Program, ProgramError, ProgramRunner, Step


class ProgramPanel(QWidget):
    """Record / run / single-step a keystroke program on an RPN faceplate.

    Pass the faceplate (or anything exposing a ``keypad`` attribute) so the
    panel can record real button presses and replay them through the keypad's
    own state machine. The step cap bounds every run.
    """

    def __init__(self, faceplate=None, parent=None, step_cap: int = 10_000) -> None:
        super().__init__(parent)
        self._faceplate = faceplate
        self._program = Program()
        self._step_cap = step_cap
        self._recording = False
        self._orig_press = None
        self._runner: ProgramRunner | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        self._status = QLabel("Program memory — idle", self)
        self._status.setWordWrap(True)
        outer.addWidget(self._status)

        self._listing = QListWidget(self)
        self._listing.setAccessibleName("Program listing")
        self._listing.setToolTip("Recorded program steps (the highlighted row is the program counter)")
        outer.addWidget(self._listing, 1)

        row1 = QHBoxLayout()
        self._record_btn = QPushButton("● Record", self)
        self._record_btn.setToolTip("Capture the keys you press into program memory")
        self._record_btn.setCheckable(True)
        self._record_btn.clicked.connect(self._toggle_record)
        row1.addWidget(self._record_btn)
        clear_btn = QPushButton("Clear", self)
        clear_btn.setToolTip("Erase program memory (f CLEAR PRGM)")
        clear_btn.clicked.connect(self._clear)
        row1.addWidget(clear_btn)
        row1.addStretch(1)
        outer.addLayout(row1)

        row2 = QHBoxLayout()
        self._run_btn = QPushButton("▶ Run", self)
        self._run_btn.setToolTip("Execute the program from the top (R/S)")
        self._run_btn.clicked.connect(self._run)
        row2.addWidget(self._run_btn)
        self._step_btn = QPushButton("Step", self)
        self._step_btn.setToolTip("Execute a single instruction (SST)")
        self._step_btn.clicked.connect(self._single_step)
        row2.addWidget(self._step_btn)
        self._reset_btn = QPushButton("Reset PC", self)
        self._reset_btn.setToolTip("Rewind the program counter to the top")
        self._reset_btn.clicked.connect(self._reset)
        row2.addWidget(self._reset_btn)
        row2.addStretch(1)
        outer.addLayout(row2)

        self._refresh()

    # -- keypad plumbing ---------------------------------------------------

    def set_faceplate(self, faceplate) -> None:
        """Point the panel at a new faceplate (e.g. after a model switch)."""
        if self._recording:
            self._toggle_record(False)
        self._faceplate = faceplate
        self._runner = None
        self._refresh()

    def _keypad(self):
        """The keypad to drive, or None if the current faceplate has none."""
        fp = self._faceplate
        if fp is None:
            return None
        return getattr(fp, "keypad", None)

    def _refresh_lcd(self) -> None:
        """Repaint the faceplate LCD after the engine state changed."""
        fp = self._faceplate
        refresh = getattr(fp, "_refresh_lcd", None)
        if refresh is not None:
            refresh()
        update = getattr(fp, "update", None)
        if update is not None:
            update()

    # -- record ------------------------------------------------------------

    def _toggle_record(self, checked: bool | None = None) -> None:
        if checked is None:
            checked = not self._recording
        keypad = self._keypad()
        if keypad is None:
            self._recording = False
            self._record_btn.setChecked(False)
            self._set_status("No calculator to record from.")
            return
        if checked and not self._recording:
            # Arm: wrap the keypad's press so each press is also appended.
            original = keypad.press

            def _recording_press(number, _orig=original):
                _orig(number)
                self._program.record_key(number)
                self._refresh()

            self._orig_press = original
            keypad.press = _recording_press
            self._recording = True
            self._record_btn.setChecked(True)
            self._set_status("Recording — every key you press is captured.")
        elif not checked and self._recording:
            # Disarm: restore the original bound method.
            if self._orig_press is not None:
                keypad.press = self._orig_press
            self._orig_press = None
            self._recording = False
            self._record_btn.setChecked(False)
            self._set_status(f"Recorded {len(self._program)} step(s).")
        self._refresh()

    def _clear(self) -> None:
        self._program.clear()
        self._runner = None
        self._set_status("Program memory cleared.")
        self._refresh()

    # -- run / step --------------------------------------------------------

    def _ensure_runner(self) -> ProgramRunner | None:
        keypad = self._keypad()
        if keypad is None:
            self._set_status("No calculator to run against.")
            return None
        if self._runner is None or self._runner.keypad is not keypad:
            self._runner = ProgramRunner(
                self._program, keypad=keypad, step_cap=self._step_cap)
        return self._runner

    def _run(self) -> None:
        if not len(self._program):
            self._set_status("Program is empty — record some keys first.")
            return
        runner = self._ensure_runner()
        if runner is None:
            return
        runner.reset()
        try:
            result = runner.run()
        except ProgramError as exc:
            self._refresh_lcd()
            self._set_status(f"Stopped: {exc}")
            self._refresh(runner.pc)
            return
        self._refresh_lcd()
        self._set_status(f"Ran {result.steps} step(s) — {result.message or 'done'}.")
        self._refresh(runner.pc)

    def _single_step(self) -> None:
        if not len(self._program):
            self._set_status("Program is empty — record some keys first.")
            return
        runner = self._ensure_runner()
        if runner is None:
            return
        try:
            advanced = runner.step()
        except ProgramError as exc:
            self._refresh_lcd()
            self._set_status(f"Stopped: {exc}")
            self._refresh(runner.pc)
            return
        self._refresh_lcd()
        if advanced:
            self._set_status(f"Stepped to instruction {runner.pc + 1}.")
        else:
            self._set_status("End of program — press Reset PC to run again.")
        self._refresh(runner.pc)

    def _reset(self) -> None:
        runner = self._ensure_runner()
        if runner is not None:
            runner.reset()
        self._set_status("Program counter rewound to the top.")
        self._refresh(0)

    # -- view --------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status.setText(text)

    def _refresh(self, pc: int | None = None) -> None:
        self._listing.clear()
        for line in self._program.listing():
            self._listing.addItem(line)
        if not self._program.listing():
            self._listing.addItem("(empty — press Record)")
        if pc is not None and 0 <= pc < self._listing.count():
            self._listing.setCurrentRow(pc)
        # Enable/disable controls to match state.
        has_kp = self._keypad() is not None
        self._record_btn.setEnabled(has_kp)
        self._run_btn.setEnabled(has_kp)
        self._step_btn.setEnabled(has_kp)

    # -- programmatic API (for tests / the integrator) ---------------------

    @property
    def program(self) -> Program:
        return self._program

    def append_step(self, step: Step) -> None:
        """Append a control/keystroke step (used to insert LBL/GTO/GSB/RTN)."""
        self._program.append(step)
        self._refresh()
