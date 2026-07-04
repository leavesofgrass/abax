"""Keystroke program memory for the RPN calculators (abax.core.calc.program).

Covers LBL/GTO guarded loops, GSB/RTN subroutines, the step cap that bounds an
infinite loop, single-step / SST positioning, and the non-invasive keystroke
recorder. The float engine's stack/register semantics come from
:mod:`abax.core.calc.rpn` (Y-op-X binary ops, ``sto``/``rcl`` registers).
"""

from __future__ import annotations

import pytest

from abax.core.calc.program import (
    KeystrokeRecorder,
    Program,
    ProgramError,
    ProgramRunner,
    Step,
    record_into,
)
from abax.core.calc.rpn import RPN
from abax.core.calc.voyager import VoyagerKeypad

# --------------------------------------------------------------------------
# LBL / GTO — a guarded loop summing 1..N
# --------------------------------------------------------------------------


def _sum_program() -> Program:
    """A program that computes 1+2+...+N with N preloaded in R2, sum in R0.

    Registers: R0 = running sum, R1 = counter i, R2 = N (loaded by the caller).
    The loop increments i, adds it to the sum, then guards the branch-back with
    a ``test`` (HP "do next if true"): while N > i it takes the GTO, otherwise
    it falls through to RTN with the total in R0 (and on the X register).
    """
    p = Program()
    p.append(Step.feed("0"))
    p.append(Step.feed("sto0"))          # sum = 0
    p.append(Step.feed("0"))
    p.append(Step.feed("sto1"))          # i = 0
    p.append(Step.lbl("loop"))
    p.append(Step.feed("rcl1"))          # X = i
    p.append(Step.feed("1"))
    p.append(Step.feed("+"))
    p.append(Step.feed("sto1"))          # i = i + 1
    p.append(Step.feed("rcl0"))          # X = sum
    p.append(Step.feed("rcl1"))          # X = i, Y = sum
    p.append(Step.feed("+"))             # X = sum + i
    p.append(Step.feed("sto0"))          # sum = sum + i
    p.append(Step.feed("rcl1"))          # X = i
    p.append(Step.feed("rcl2"))          # X = N, Y = i
    p.append(Step.test("x>y"))           # N > i ?  true while i < N
    p.append(Step.gto("loop"))           # ... loop back (skipped when i == N)
    p.append(Step.feed("rcl0"))          # bring the total to X
    p.append(Step.rtn())
    return p


@pytest.mark.parametrize(
    "n, expected",
    # Oracle: closed form N(N+1)/2 (Gauss). 1..10 = 55, 1..5 = 15, 1..1 = 1,
    # 1..100 = 5050.
    [(1, 1.0), (5, 15.0), (10, 55.0), (100, 5050.0)],
)
def test_sum_loop_via_lbl_gto(n, expected):
    engine = RPN()
    engine.regs["R2"] = float(n)                 # N into R2
    runner = ProgramRunner(_sum_program(), engine=engine)
    result = runner.run()                        # run from the top
    assert engine.regs["R0"] == pytest.approx(expected)
    assert engine.x == pytest.approx(expected)   # total also left on X
    assert result.halted


def test_run_from_a_label():
    # GTO/run to a specific label: preload R0/R1/R2 and enter at ``loop`` so the
    # initialisation steps are skipped. Start sum=0, i=0, N=3 -> 6.
    engine = RPN()
    engine.regs.update({"R0": 0.0, "R1": 0.0, "R2": 3.0})
    runner = ProgramRunner(_sum_program(), engine=engine)
    runner.run("loop")
    assert engine.regs["R0"] == pytest.approx(6.0)   # 1+2+3


# --------------------------------------------------------------------------
# GSB / RTN — a subroutine
# --------------------------------------------------------------------------


def test_gsb_rtn_subroutine():
    # Main: 3, GSB sq (squares X -> 9), then + 1 -> 10. The subroutine LBL ``sq``
    # does x^2 and RTN back to the instruction after the GSB.
    p = Program()
    p.append(Step.feed("3"))
    p.append(Step.gsb("sq"))
    p.append(Step.feed("1"))
    p.append(Step.feed("+"))
    p.append(Step.rtn())          # top-level RTN halts
    p.append(Step.lbl("sq"))
    p.append(Step.feed("sq"))     # x^2  (rpn token)
    p.append(Step.rtn())          # returns to the step after GSB
    engine = RPN()
    runner = ProgramRunner(p, engine=engine)
    runner.run()
    assert engine.x == pytest.approx(10.0)   # 3^2 + 1


def test_nested_gsb_returns_in_order():
    # GSB a -> GSB b -> RTN -> RTN. The return stack must unwind LIFO so control
    # comes back through ``a`` to the top level. Each sub adds 1; start 0 -> 2.
    p = Program()
    p.append(Step.feed("0"))
    p.append(Step.gsb("a"))
    p.append(Step.rtn())          # top-level RTN
    p.append(Step.lbl("a"))
    p.append(Step.feed("1"))
    p.append(Step.feed("+"))
    p.append(Step.gsb("b"))
    p.append(Step.rtn())
    p.append(Step.lbl("b"))
    p.append(Step.feed("1"))
    p.append(Step.feed("+"))
    p.append(Step.rtn())
    engine = RPN()
    runner = ProgramRunner(p, engine=engine)
    result = runner.run()
    assert engine.x == pytest.approx(2.0)
    assert not runner.return_stack           # fully unwound
    assert result.halted


# --------------------------------------------------------------------------
# Step cap — bound an infinite loop
# --------------------------------------------------------------------------


def test_infinite_loop_hits_step_cap():
    # LBL a ; GTO a  — no guard, so it never halts. The cap must stop it.
    p = Program()
    p.append(Step.lbl("a"))
    p.append(Step.gto("a"))
    runner = ProgramRunner(p, engine=RPN(), step_cap=500)
    with pytest.raises(ProgramError) as exc:
        runner.run()
    assert "step cap" in str(exc.value)
    assert "500" in str(exc.value)


def test_step_cap_leaves_runner_positioned():
    # After hitting the cap the runner stays inside the loop (a panel can show
    # where it stalled) rather than resetting.
    p = Program()
    p.append(Step.lbl("a"))
    p.append(Step.feed("1"))
    p.append(Step.gto("a"))
    runner = ProgramRunner(p, engine=RPN(), step_cap=50)
    with pytest.raises(ProgramError):
        runner.run()
    assert 0 <= runner.pc < len(p)
    assert not runner.halted                 # it never reached an end


# --------------------------------------------------------------------------
# Single-step (SST) and label lookup
# --------------------------------------------------------------------------


def test_single_step_advances_one_at_a_time():
    p = Program()
    p.append(Step.feed("2"))
    p.append(Step.feed("3"))
    p.append(Step.feed("+"))
    p.append(Step.rtn())
    engine = RPN()
    runner = ProgramRunner(p, engine=engine)
    assert runner.step() and engine.x == pytest.approx(2.0)   # after "2"
    assert runner.step() and engine.x == pytest.approx(3.0)   # after "3"
    assert runner.step() and engine.x == pytest.approx(5.0)   # after "+"
    assert runner.step()                                       # RTN (halts)
    assert runner.halted
    assert runner.step() is False                              # nothing left


def test_test_skips_guarded_step_when_false():
    # X=1, Y=2 -> "x>y" is FALSE, so the guarded GTO is skipped and we reach the
    # marker feed. If the skip were wrong we'd loop or land elsewhere.
    p = Program()
    p.append(Step.feed("2"))       # Y
    p.append(Step.feed("1"))       # X  (X=1, Y=2)
    p.append(Step.test("x>y"))     # 1 > 2 -> False -> skip next
    p.append(Step.gto("never"))    # skipped
    p.append(Step.feed("7"))       # landing marker
    p.append(Step.rtn())
    p.append(Step.lbl("never"))
    p.append(Step.feed("99"))
    p.append(Step.rtn())
    engine = RPN()
    ProgramRunner(p, engine=engine).run()
    assert engine.x == pytest.approx(7.0)


def test_missing_label_raises():
    p = Program()
    p.append(Step.gto("nope"))
    with pytest.raises(ProgramError):
        ProgramRunner(p, engine=RPN()).run()


def test_bad_step_kinds_rejected():
    with pytest.raises(ProgramError):
        Step("bogus", 1)
    with pytest.raises(ProgramError):
        Step("key", "not-an-int")
    with pytest.raises(ProgramError):
        Step("test", "x<>y")          # not a known comparison test
    with pytest.raises(ProgramError):
        Step("gto", "")               # empty label


# --------------------------------------------------------------------------
# Keystroke recording (the non-invasive hook)
# --------------------------------------------------------------------------


def test_recorder_captures_presses_and_restores():
    kp = VoyagerKeypad()
    original = kp.press
    rec = KeystrokeRecorder(kp)
    with rec:
        # 7 ENTER 8 + -> the keypad still computes live (15 on X)...
        for b in (17, 36, 18, 40):        # button numbers: 7, ENTER, 8, +
            kp.press(b)
    assert kp.rpn.x == pytest.approx(15.0)
    # ...and the program captured exactly those four presses.
    assert [s.kind for s in rec.program] == ["key"] * 4
    assert [s.arg for s in rec.program] == [17, 36, 18, 40]
    # The keypad's press is fully restored after the context exits.
    assert kp.press == original


def test_recorded_program_replays_on_a_fresh_keypad():
    # Record on one keypad, then replay the recorded keys through a runner on a
    # fresh keypad — the classic HP "record once, run many" flow.
    src = VoyagerKeypad()
    prog = Program()
    rec = record_into(src, prog)
    for b in (17, 36, 18, 40):            # 7 ENTER 8 +
        src.press(b)
    rec.stop()

    fresh = VoyagerKeypad()
    runner = ProgramRunner(prog, keypad=fresh)
    runner.run()
    assert fresh.rpn.x == pytest.approx(15.0)


def test_runner_needs_keypad_for_key_steps():
    p = Program()
    p.append(Step.key(17))
    runner = ProgramRunner(p, engine=RPN())     # engine only, no keypad
    with pytest.raises(ProgramError):
        runner.run()


def test_program_editing_and_listing():
    p = Program()
    p.record_feed("5")
    p.append(Step.lbl("top"))
    p.record_key(40)
    assert len(p) == 3
    assert p.labels() == {"top": 1}
    listing = p.listing()
    assert listing[0] == "001 5"
    assert listing[1] == "002 LBL top"
    assert listing[2] == "003 KEY 40"
    p.delete(0)
    assert len(p) == 2
    p.clear()
    assert len(p) == 0
