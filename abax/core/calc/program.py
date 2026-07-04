"""HP keystroke *program memory* for the RPN calculators (LBL/GTO/GSB/RTN).

The immediate-mode Voyager keypads (:mod:`abax.core.calc.voyager`,
:mod:`~abax.core.calc.rpn12`, :mod:`~abax.core.calc.rpn16`) treat the flow-control
keys — ``LBL``, ``GTO``, ``GSB``, ``RTN``, the ``x<=y`` / ``x=0`` test keys — as
inert (they sit in each module's ``_PROGRAM_KEYS`` and merely set a message).
This module adds the missing half: a :class:`Program` of recorded *steps* and a
runner that executes them against the existing RPN engine, exactly like the real
HP-15C's program memory.

Design
------
A program is an ordered list of :class:`Step`. A step is one of:

``key``   replay a physical keypad button (``keypad.press(number)``);
``feed``  feed a raw engine token (``"5"``, ``"+"``, ``"sqrt"`` …) — the
          keypad-independent equivalent of a keystroke, used when a program is
          built directly rather than recorded;
``lbl``   a label marker — a landing target for ``GTO`` / ``GSB`` (a no-op when
          reached in the normal flow);
``gto``   unconditional jump to a label;
``gsb``   *gosub* — push the return address, then jump to a label;
``rtn``   *return* — pop the return address; with an empty return stack the run
          halts (an HP ``RTN`` at the top level stops the program);
``test``  an HP conditional (``"x<=y"``, ``"x=0"`` …). HP's convention is
          **do-if-true**: when the test is true the next step runs; when false
          the next step is *skipped*. Guarded loops are built with a ``test``
          immediately before a ``GTO``.

Execution is a small program counter over that list with a bounded step budget
so an accidental infinite loop (``LBL a; GTO a``) terminates with a clear error
rather than hanging. Everything here is pure stdlib; the Qt run/step panel lives
in :mod:`abax.gui.calc.program_panel`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

__all__ = [
    "ProgramError",
    "Step",
    "Program",
    "ProgramRunner",
    "KeystrokeRecorder",
    "TESTS",
    "record_into",
]


class ProgramError(Exception):
    """Raised on a malformed program or a runtime fault (unknown label, loop cap)."""


# -- conditional tests -----------------------------------------------------
#
# Each test is evaluated against the engine's X (and, for the two-operand
# forms, Y) register. HP's convention is "do the next step if TRUE, skip it if
# FALSE"; the runner applies that. Kept as plain callables so the set is easy to
# audit and extend, and so it works against both the float and integer engines
# (the integer HP-16C stores X unsigned, so signed comparisons go through
# ``_signed`` below).

def _signed(engine, v):
    """The signed value of ``v`` for the integer engine; ``v`` itself otherwise."""
    conv = getattr(engine, "_signed_value", None)
    return conv(v) if conv is not None else v


def _x(engine) -> float:
    return _signed(engine, engine.stack[0])


def _y(engine) -> float:
    return _signed(engine, engine.stack[1])


TESTS: dict[str, Callable[[object], bool]] = {
    "x<=y": lambda e: _x(e) <= _y(e),
    "x<y": lambda e: _x(e) < _y(e),
    "x>y": lambda e: _x(e) > _y(e),
    "x>=y": lambda e: _x(e) >= _y(e),
    "x=y": lambda e: _x(e) == _y(e),
    "x==y": lambda e: _x(e) == _y(e),
    "x!=y": lambda e: _x(e) != _y(e),
    "x<=0": lambda e: _x(e) <= 0,
    "x<0": lambda e: _x(e) < 0,
    "x>0": lambda e: _x(e) > 0,
    "x>=0": lambda e: _x(e) >= 0,
    "x=0": lambda e: _x(e) == 0,
    "x==0": lambda e: _x(e) == 0,
    "x!=0": lambda e: _x(e) != 0,
}

# The step kinds a Program understands.
_KINDS = frozenset({"key", "feed", "lbl", "gto", "gsb", "rtn", "test"})


@dataclass(frozen=True)
class Step:
    """One recorded program step: a ``kind`` plus its operand.

    ``kind``       one of ``key`` / ``feed`` / ``lbl`` / ``gto`` / ``gsb`` /
                   ``rtn`` / ``test`` (see the module docstring).
    ``arg``        the button number (``key``), token/label/test name (others),
                   or ``None`` (``rtn``).
    """

    kind: str
    arg: object = None

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ProgramError(f"unknown step kind: {self.kind!r}")
        if self.kind == "key" and not isinstance(self.arg, int):
            raise ProgramError("a 'key' step needs an integer button number")
        if self.kind in ("lbl", "gto", "gsb") and not self.arg:
            raise ProgramError(f"a {self.kind!r} step needs a label name")
        if self.kind == "test" and self.arg not in TESTS:
            raise ProgramError(f"unknown test: {self.arg!r}")

    # -- convenience constructors -----------------------------------------

    @staticmethod
    def key(number: int) -> "Step":
        return Step("key", int(number))

    @staticmethod
    def feed(token: str) -> "Step":
        return Step("feed", str(token))

    @staticmethod
    def lbl(name: str) -> "Step":
        return Step("lbl", str(name))

    @staticmethod
    def gto(name: str) -> "Step":
        return Step("gto", str(name))

    @staticmethod
    def gsb(name: str) -> "Step":
        return Step("gsb", str(name))

    @staticmethod
    def rtn() -> "Step":
        return Step("rtn", None)

    @staticmethod
    def test(name: str) -> "Step":
        return Step("test", str(name))

    def text(self) -> str:
        """A short one-line listing of this step (for a program panel / SST)."""
        if self.kind == "key":
            return f"KEY {self.arg}"
        if self.kind == "feed":
            return str(self.arg)
        if self.kind == "rtn":
            return "RTN"
        return f"{self.kind.upper()} {self.arg}"


@dataclass
class Program:
    """An ordered list of recorded :class:`Step`s (HP program memory)."""

    steps: list[Step] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)

    def __getitem__(self, i):
        return self.steps[i]

    # -- editing -----------------------------------------------------------

    def append(self, step: Step) -> None:
        """Append a step (record it at the end of program memory)."""
        if not isinstance(step, Step):
            raise ProgramError("Program.append expects a Step")
        self.steps.append(step)

    def clear(self) -> None:
        """Erase all program memory (HP ``f CLEAR PRGM``)."""
        self.steps.clear()

    def delete(self, index: int) -> None:
        """Delete the step at ``index`` (HP program editing / backspace)."""
        del self.steps[index]

    # -- recording keystrokes ---------------------------------------------

    def record_key(self, number: int) -> Step:
        """Record a physical keypad button press; return the step recorded."""
        step = Step.key(number)
        self.steps.append(step)
        return step

    def record_feed(self, token: str) -> Step:
        """Record a raw engine token (a keypad-independent keystroke)."""
        step = Step.feed(token)
        self.steps.append(step)
        return step

    # -- labels ------------------------------------------------------------

    def labels(self) -> dict[str, int]:
        """Map every ``LBL`` name to its step index (last definition wins)."""
        out: dict[str, int] = {}
        for i, step in enumerate(self.steps):
            if step.kind == "lbl":
                out[str(step.arg)] = i
        return out

    def find_label(self, name: str) -> int:
        """Index of the ``LBL name`` step, or raise :class:`ProgramError`."""
        idx = self.labels().get(str(name))
        if idx is None:
            raise ProgramError(f"label not found: {name!r}")
        return idx

    def listing(self) -> list[str]:
        """A numbered listing (``001 …``) of the program, HP ``P/R`` style."""
        return [f"{i + 1:03d} {s.text()}" for i, s in enumerate(self.steps)]


# -- execution -------------------------------------------------------------


@dataclass
class RunResult:
    """The outcome of a run/step batch.

    ``steps``      program steps actually executed;
    ``halted``     True once the program has finished (RTN at top level / ran
                   off the end / stopped);
    ``pc``         the program counter where execution paused (or the length of
                   the program once halted);
    ``message``    a short human-readable status (empty on a clean run).
    """

    steps: int = 0
    halted: bool = False
    pc: int = 0
    message: str = ""


class ProgramRunner:
    """Executes a :class:`Program` against a keypad (or a bare RPN engine).

    The runner drives the *keypad* when one is supplied (so recorded button
    presses replay through the real keypad state machine, committing digit
    entry exactly as a user would) and falls back to the engine directly for
    ``feed`` steps. Pass a keypad **or** an engine; a keypad's ``.rpn`` is used
    as the engine automatically.
    """

    def __init__(
        self,
        program: Program,
        keypad=None,
        engine=None,
        step_cap: int = 10_000,
    ) -> None:
        if keypad is None and engine is None:
            raise ProgramError("ProgramRunner needs a keypad or an engine")
        self.program = program
        self.keypad = keypad
        self.engine = engine if engine is not None else keypad.rpn
        if step_cap <= 0:
            raise ProgramError("step_cap must be positive")
        self.step_cap = step_cap
        self.pc: int = 0
        self.return_stack: list[int] = []
        self.halted: bool = False
        self.message: str = ""

    # -- positioning -------------------------------------------------------

    def reset(self) -> None:
        """Rewind to the top of program memory (does not touch the stack)."""
        self.pc = 0
        self.return_stack = []
        self.halted = False
        self.message = ""

    def goto_label(self, name: str) -> None:
        """Position the program counter *after* ``LBL name`` (HP ``GTO``)."""
        self.pc = self.program.find_label(name) + 1
        self.halted = False
        self.message = ""

    # -- single step -------------------------------------------------------

    def step(self) -> bool:
        """Execute exactly one program step; return True if the program advanced.

        Returns False when the program has halted (nothing left to do). A
        ``test`` that must skip its guarded step consumes *two* positions but is
        still reported as a single advancing step.
        """
        if self.halted:
            return False
        if self.pc >= len(self.program):
            self.halted = True
            self.message = self.message or "end of program"
            return False
        step = self.program.steps[self.pc]
        self._exec(step)
        return True

    def _exec(self, step: Step) -> None:
        kind = step.kind
        if kind == "lbl":
            self.pc += 1
        elif kind == "key":
            self._press(step.arg)
            self.pc += 1
        elif kind == "feed":
            self.engine.feed(str(step.arg))
            self.pc += 1
        elif kind == "gto":
            self.pc = self.program.find_label(str(step.arg)) + 1
        elif kind == "gsb":
            # Push the address of the step *after* this GSB, then jump.
            self.return_stack.append(self.pc + 1)
            self.pc = self.program.find_label(str(step.arg)) + 1
        elif kind == "rtn":
            if self.return_stack:
                self.pc = self.return_stack.pop()
            else:
                # RTN with an empty return stack halts the program (top-level RTN).
                self.pc += 1
                self.halted = True
                self.message = "RTN"
        elif kind == "test":
            passed = TESTS[str(step.arg)](self.engine)
            # HP "do if true": true -> run the next step; false -> skip it.
            self.pc += 1 if passed else 2
        else:  # pragma: no cover - guarded by Step.__post_init__
            raise ProgramError(f"unhandled step kind: {kind!r}")

    def _press(self, number: int) -> None:
        if self.keypad is None:
            raise ProgramError(
                "a 'key' step needs a keypad (this runner has only an engine)")
        self.keypad.press(number)

    # -- bounded run -------------------------------------------------------

    def run(self, label: Optional[str] = None) -> RunResult:
        """Run from ``label`` (or the current PC) to RTN / end, bounded by the cap.

        The step budget (:attr:`step_cap`) bounds *every* run so a program with
        an unguarded loop terminates deterministically with a clear error
        instead of hanging. Returns a :class:`RunResult`; on hitting the cap the
        result is raised as a :class:`ProgramError` after leaving the runner at
        the offending PC so a panel can show where it stalled.
        """
        if label is not None:
            self.goto_label(label)
        else:
            self.halted = False
        executed = 0
        while not self.halted:
            if executed >= self.step_cap:
                self.message = f"step cap ({self.step_cap}) exceeded — possible infinite loop"
                raise ProgramError(self.message)
            if not self.step():
                break
            executed += 1
        return RunResult(
            steps=executed,
            halted=self.halted,
            pc=self.pc,
            message=self.message,
        )


# -- keystroke recording ---------------------------------------------------


class KeystrokeRecorder:
    """A non-invasive keystroke-record hook that captures presses into a Program.

    Wraps a keypad's ``press`` so every physical button press is *also* appended
    to a :class:`Program` while recording is armed — the record-mode half of HP
    program entry. It monkey-patches the bound method on the single keypad
    instance (never the class), so no engine/keypad source needs editing and
    :meth:`stop` fully restores the original behaviour. Usable as a context
    manager::

        with KeystrokeRecorder(keypad, program):
            keypad.press(17)     # recorded as Step.key(17)

    """

    def __init__(self, keypad, program: Optional[Program] = None) -> None:
        self.keypad = keypad
        self.program = program if program is not None else Program()
        self._original: Optional[Callable[[int], None]] = None
        self.recording = False

    def start(self) -> "KeystrokeRecorder":
        """Arm recording: subsequent ``keypad.press`` calls are captured."""
        if self.recording:
            return self
        original = self.keypad.press

        def _recording_press(number: int) -> None:
            original(number)
            self.program.record_key(number)

        self._original = original
        self.keypad.press = _recording_press  # type: ignore[assignment]
        self.recording = True
        return self

    def stop(self) -> Program:
        """Disarm recording and restore the keypad; return the recorded program."""
        if self.recording and self._original is not None:
            self.keypad.press = self._original  # type: ignore[assignment]
        self._original = None
        self.recording = False
        return self.program

    # -- context-manager sugar --------------------------------------------

    def __enter__(self) -> "KeystrokeRecorder":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()


def record_into(keypad, program: Optional[Program] = None) -> KeystrokeRecorder:
    """Convenience: build and *arm* a :class:`KeystrokeRecorder` on ``keypad``."""
    return KeystrokeRecorder(keypad, program).start()
