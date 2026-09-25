"""Work the calculation questions of the Amateur Extra (Element 4) pool in abax.

Every calculation question in the 2024–2028 pool (effective July 1, 2024 –
June 30, 2028) is evaluated here as a spreadsheet formula and checked against
the pool's answer key. The script exits non-zero if any answer disagrees, so
the docs example suite (tests/test_examples.py) keeps it honest.
"""

import sys

from abax.core.workbook import Workbook

# (question ID, formula, what the pool's correct answer says, check)
# ``check`` takes the formula's value and returns True when it matches.
CASES = [
    # --- E1 band edges & sidebands -----------------------------------------
    ("E1A01", "=USBMAXFREQ(14.350e6,3000)",
     "D: 3 kHz USB at 14.348 MHz extends past the band edge", lambda v: v < 14.348e6),
    ("E1A03", "=USBMAXFREQ(14.150e6,2800)", "C: 14.1472 MHz", lambda v: v == 14.1472e6),
    ("E1A04", "=LSBMINFREQ(3.600e6,3000)",
     "C: no — 3.601 MHz LSB extends below 3.600 MHz", lambda v: v > 3.601e6),
    # --- E4 receivers & link budgets -----------------------------------------
    ("E4C05", "=NOISEFLOOR(1)", "B: -174 dBm is kTB in 1 Hz", lambda v: round(v) == -174),
    ("E4C06", "=BWNOISEDB(50,1000)", "D: 13 dB", lambda v: round(v) == 13),
    ("E4D12", "=LINKMARGIN(RXLEVEL(40,10,0,136,3),-103,6)", "C: +8 dB",
     lambda v: round(v) == 8),
    ("E4D13", "=RXLEVEL(40,6,3,100)", "A: -51 dBm", lambda v: round(v) == -51),
    ("E4D14", "=DBM2W(-100)", "D: 0.1 pW (1e-13 W)", lambda v: abs(v - 1e-13) < 1e-16),
    # --- E5 circuits -----------------------------------------------------------
    ("E5A02", "=RESFREQ(50e-6,40e-12)", "C: 3.56 MHz", lambda v: round(v / 1e6, 2) == 3.56),
    ("E5A10", "=RESFREQ(50e-6,10e-12)", "A: 7.12 MHz", lambda v: round(v / 1e6, 2) == 7.12),
    ("E5A11", "=BWQ(7.1e6,150)", "C: 47.3 kHz", lambda v: round(v / 1e3, 1) == 47.3),
    ("E5A12", "=BWQ(3.7e6,118)", "C: 31.4 kHz", lambda v: round(v / 1e3, 1) == 31.4),
    ("E5B01", "=TCCHARGE(1,1)", "B: one time constant (63.2 %)",
     lambda v: round(v, 3) == 0.632),
    ("E5B04", "=TAURC(RPARALLEL(1e6,1e6),CPARALLEL(220e-6,220e-6))", "D: 220 seconds",
     lambda v: round(v) == 220),
    ("E5B07", "=PHASEANGLE(1000,250-500)", "C: 14.0°, voltage lagging current",
     lambda v: round(v, 1) == -14.0),
    ("E5B08", "=PHASEANGLE(100,100-300)", "A: 63°, voltage lagging current",
     lambda v: round(v) == -63),
    ("E5B11", "=PHASEANGLE(100,75-25)", "B: 27°, voltage leading current",
     lambda v: round(v) == 27),
    ("E5C10", "=ZSERIESRLC(14e6,400,0,38e-12)", "B: Point 4 (400 - j300)",
     lambda v: v.startswith("400-299.")),
    ("E5C11", "=ZSERIESRLC(3.505e6,300,18e-6,0)", "B: Point 3 (300 + j400)",
     lambda v: v.startswith("300+396.")),
    ("E5C12", "=ZSERIESRLC(21.2e6,300,0,19e-12)", "A: Point 1 (300 - j400)",
     lambda v: v.startswith("300-395.")),
    ("E5D11", "=POWERIR(1,100)", "B: 100 W", lambda v: v == 100),
    # --- E7 op-amps & sampling -------------------------------------------------
    ("E7F05", "=NYQUIST(1)", "B: twice the highest frequency", lambda v: v == 2),
    ("E7F06", "=ADCBITS(1,0.001)", "D: 10 bits", lambda v: v == 10),
    ("E7G07", "=ABS(OPAMPINV(470,10))", "C: 47", lambda v: round(v) == 47),
    ("E7G09", "=OPAMPINV(10000,1000)*0.23", "D: -2.3 V", lambda v: round(v, 2) == -2.3),
    ("E7G10", "=ABS(OPAMPINV(68000,1800))", "C: 38", lambda v: round(v) == 38),
    ("E7G11", "=ABS(OPAMPINV(47000,3300))", "B: 14", lambda v: round(v) == 14),
    # --- E8 modulation & bandwidth ---------------------------------------------
    ("E8A09", "=ADCLEVELS(8)", "D: 256", lambda v: v == 256),
    ("E8B03", "=MODINDEX(3000,1000)", "A: 3", lambda v: v == 3),
    ("E8B04", "=MODINDEX(6000,2000)", "B: 3", lambda v: v == 3),
    ("E8B05", "=DEVRATIO(5000,3000)", "D: 1.67", lambda v: round(v, 2) == 1.67),
    ("E8B06", "=DEVRATIO(7500,3500)", "A: 2.14", lambda v: round(v, 2) == 2.14),
    ("E8C05", "=CWBW(13)", "C: 52 Hz", lambda v: round(v) == 52),
    ("E8C07", "=FSKBW(4800,9600)", "A: 15.36 kHz", lambda v: round(v) == 15360),
    # --- E9 antennas & feed lines ----------------------------------------------
    ("E9A02", "=ERPW(150,7,2,2.2)", "D: 286 W", lambda v: round(v) == 286),
    ("E9A06", "=ERPW(200,10,4,3.2,0.8)", "A: 317 W", lambda v: round(v) == 317),
    ("E9A07", "=EIRPW(200,7,2,2.8,1.2)", "B: 252 W", lambda v: round(v) == 252),
    ("E9A12", "=DBI2DBD(6)", "A: 3.85 dBd", lambda v: round(v, 2) == 3.85),
    ("E9D01", "=DISHGAIN(3,2e9)-DISHGAIN(3,1e9)", "D: +6 dB when frequency doubles",
     lambda v: round(v) == 6),
    ("E9E06", "=QWMATCH(100,50)", "C: 75 Ω coax (nearest to 70.7 Ω)",
     lambda v: round(v, 1) == 70.7),
    ("E9F04", "=ABS(STUBX(50,180))", "B: shorted 1/2 λ: very low impedance",
     lambda v: v < 1e-6),
    ("E9F06", "=LINELEN(14.10e6,0.5,1)", "C: 10.6 m", lambda v: round(v, 1) == 10.6),
    ("E9F10", "=STUBX(50,45)", "C: shorted 1/8 λ: inductive reactance", lambda v: v > 0),
    ("E9F11", "=STUBX(50,45,TRUE)", "C: open 1/8 λ: capacitive reactance", lambda v: v < 0),
    ("E9F12", "=ABS(STUBX(50,90,TRUE))", "D: open 1/4 λ: very low impedance",
     lambda v: v < 1e-6),
]


def main() -> int:
    wb = Workbook()
    sheet = wb.sheets[0]
    failures = 0
    print(f"{'ID':<6} {'result':>16}  pool answer")
    for i, (qid, formula, answer, check) in enumerate(CASES, start=1):
        sheet.set(f"A{i}", formula)
        value = sheet.get(f"A{i}")
        try:
            ok = check(value)
        except Exception:  # noqa: BLE001 — a CellError or wrong type is a failure
            ok = False
        failures += not ok
        shown = f"{value:.6g}" if isinstance(value, float) else str(value)
        print(f"{qid:<6} {shown:>16}  {answer}{'' if ok else '   <-- MISMATCH'}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} match the answer key")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
