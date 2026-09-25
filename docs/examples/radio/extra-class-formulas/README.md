# Work the Amateur Extra calculation questions

Every calculation question in the FCC **Amateur Extra (Element 4)** question
pool, worked as an abax formula and checked against the pool's answer key.
Use it to study, or as a template for your own station math.

**You'll need:** abax only.

**Which pool:** the 2024–2028 Extra Class pool from the NCVEC Question Pool
Committee, effective July 1, 2024 through June 30, 2028, as published with its
fourth errata (February 4, 2026). The script checks 45 questions; the pool's
other questions are conceptual or rules-based and need no arithmetic.

## Run it

```sh
cd docs/examples/radio/extra-class-formulas
python run.py
```

The script exits with status 1 if any result disagrees with the answer key,
so the docs test suite fails if a formula ever drifts.

## What you should see

```
ID               result  pool answer
E1A01        1.4347e+07  D: 3 kHz USB at 14.348 MHz extends past the band edge
E1A03       1.41472e+07  C: 14.1472 MHz
E1A04         3.603e+06  C: no — 3.601 MHz LSB extends below 3.600 MHz
E4C05          -173.975  B: -174 dBm is kTB in 1 Hz
E4C06           13.0103  D: 13 dB
E4D12                 8  C: +8 dB
E4D13               -51  A: -51 dBm
E4D14             1e-13  D: 0.1 pW (1e-13 W)
E5A02       3.55881e+06  C: 3.56 MHz
E5A10       7.11763e+06  A: 7.12 MHz
E5A11           47333.3  C: 47.3 kHz
E5A12           31355.9  C: 31.4 kHz
E5B01          0.632121  B: one time constant (63.2 %)
E5B04               220  D: 220 seconds
E5B07          -14.0362  C: 14.0°, voltage lagging current
E5B08          -63.4349  A: 63°, voltage lagging current
E5B11           26.5651  B: 27°, voltage leading current
E5C10  400-299.163426864j  B: Point 4 (400 - j300)
E5C11  300+396.40616103j  B: Point 3 (300 + j400)
E5C12  300-395.121507179j  A: Point 1 (300 - j400)
E5D11               100  B: 100 W
E7F05                 2  B: twice the highest frequency
E7F06                10  D: 10 bits
E7G07                47  C: 47
E7G09              -2.3  D: -2.3 V
E7G10           37.7778  C: 38
E7G11           14.2424  B: 14
E8A09               256  D: 256
E8B03                 3  A: 3
E8B04                 3  B: 3
E8B05           1.66667  D: 1.67
E8B06           2.14286  A: 2.14
E8C05                52  C: 52 Hz
E8C07             15360  A: 15.36 kHz
E9A02           285.819  D: 286 W
E9A06           316.979  A: 317 W
E9A07           251.785  B: 252 W
E9A12              3.85  A: 3.85 dBd
E9D01            6.0206  D: +6 dB when frequency doubles
E9E06           70.7107  C: 75 Ω coax (nearest to 70.7 Ω)
E9F04       6.12323e-15  B: shorted 1/2 λ: very low impedance
E9F06           10.6309  C: 10.6 m
E9F10                50  C: shorted 1/8 λ: inductive reactance
E9F11               -50  C: open 1/8 λ: capacitive reactance
E9F12       3.06162e-15  D: open 1/4 λ: very low impedance

45/45 match the answer key
```

The first column is the pool question ID. Results are in SI units (hertz,
watts, ohms, seconds). A phase angle is negative when the voltage lags the
current, and positive when it leads.

## How it works

- Each question is one formula. A few combine functions, for example:
  - `=TAURC(RPARALLEL(1e6,1e6),CPARALLEL(220e-6,220e-6))` for E5B04, where the
    two resistors and the two capacitors are each in parallel
  - `=LINKMARGIN(RXLEVEL(…),…)` for E4D12
- `ERPW` / `EIRPW` take the transmitter power, the antenna gain, then any
  number of losses as positive dB, in the order the question lists them.
- `ZSERIESRLC` returns an Excel-style complex impedance string (`400-299.16j`).
  `IMREAL`, `IMAGINARY` and `IMABS` read it back.
- `STUBX` gives a stub's input reactance: positive is inductive, negative is
  capacitive. A shorted quarter-wave stub (E9F09) has infinite reactance, so
  `=STUBX(50,90)` returns `#NUM!`. That is the "very high impedance" answer.

See the [RF toolkit guide](../../../rf-toolkit.md#circuit-fundamentals) for
every function used here.
