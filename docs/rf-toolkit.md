# RF / ham-radio toolkit

abax ships a set of **radio-frequency engineering functions** — power/level
conversions, transmission-line and matching math, link-budget and propagation
formulas, antenna helpers, and the **Maidenhead grid locator** — so you can build a
link budget, antenna, or matching spreadsheet natively. They are backed by
[`abax/core/science/rf.py`](../abax/core/science/rf.py) (pure standard library;
no third-party dependency).

See also: [formula reference](formula-reference.md) ·
[data analysis](data-analysis.md) · [index](index.md).

## Units

The formula functions use **SI base units** so they stay unambiguous and
unit-neutral:

| Quantity | Unit |
| --- | --- |
| frequency | hertz (Hz) — e.g. `14.2e6` for 14.2 MHz |
| length / distance / wavelength | metre (m) |
| power | watt (W); levels in dBm / dBW / dB |
| inductance · capacitance | henry (H) · farad (F) |
| impedance | ohm (Ω) |

Put MHz/feet in your own cells and scale, or use `CONVERT` (see
[file formats / functions](formula-reference.md)) — e.g. `=CONVERT(A1,"ft","m")`.
A forthcoming **RF toolkit dialog** and **Smith chart** will accept MHz / feet
directly and show results in both metric and imperial.

## Power & levels

| Function | Returns |
| --- | --- |
| `DBM2W(dbm)` / `W2DBM(watts)` | dBm ↔ watts |
| `DBW2W(dbw)` / `W2DBW(watts)` | dBW ↔ watts |
| `DB2RATIO(db)` / `RATIO2DB(power_ratio)` | dB ↔ linear power ratio |
| `DBADD(db1, db2)` | combine two powers given in dB(m) |
| `DBUV2DBM(dbuv, [z=50])` | dBµV (across Z) → dBm |
| `SUNIT2DBM(s)` | HF S-meter reading → dBm (S9 = −73 dBm) |
| `NOISEFLOOR(bw_hz, [temp_k=290])` | thermal noise floor kTB (dBm) |
| `NF2NT(nf_db, [t0])` / `NT2NF(temp_k, [t0])` | noise figure ↔ noise temperature |

## Wavelength, resonance, reactance

| Function | Returns |
| --- | --- |
| `WAVELENGTH(freq_hz, [vf=1])` / `WL2FREQ(m, [vf=1])` | λ ↔ f (optional velocity factor) |
| `DIPOLELEN(freq_hz, [k=0.95])` | physical ½-wave dipole length (m) |
| `MONOPOLELEN(freq_hz, [k=0.95])` | physical ¼-wave monopole length (m) |
| `XL(freq_hz, L_henry)` / `XC(freq_hz, C_farad)` | inductive / capacitive reactance (Ω) |
| `RESFREQ(L_henry, C_farad)` | LC resonant frequency (Hz) |

## Transmission line & matching

| Function | Returns |
| --- | --- |
| `VSWR(z_load, [z0=50])` | VSWR from a (resistive) load |
| `VSWRG(gamma)` | VSWR from \|Γ\| |
| `REFLCOEF(z_load, [z0=50])` | reflection coefficient Γ |
| `RETURNLOSS(gamma)` / `MISMATCHLOSS(gamma)` | return loss / mismatch loss (dB) |
| `VSWR2GAMMA(vswr)` | \|Γ\| from VSWR |
| `Z0COAX(d_outer, d_inner, [eps_r=1])` | coax characteristic impedance (Ω) |
| `VELFACTOR(eps_r)` | velocity factor 1/√εr |

## Link budget & propagation

| Function | Returns |
| --- | --- |
| `FSPL(distance_m, freq_hz)` | free-space path loss (dB) |
| `FRIIS(ptx_dbm, gtx_dbi, grx_dbi, dist_m, freq_hz)` | received power (dBm) |
| `EIRP(ptx_dbm, gain_dbi, [loss_db=0])` | EIRP (dBm) |
| `FRESNEL(d1_m, d2_m, freq_hz, [zone=1])` | Fresnel-zone radius (m) |
| `RADIOHORIZON(h1_m, [h2_m=0])` | radio line-of-sight distance (km, 4/3 earth) |
| `SKINDEPTH(freq_hz, [sigma=5.8e7], [mu_r=1])` | skin depth (m); default copper |
| `DBI2DBD(dbi)` / `DBD2DBI(dbd)` | antenna gain reference conversion |

## Maidenhead grid locator

| Function | Returns |
| --- | --- |
| `GRIDSQUARE(lat, lon, [precision=6])` | locator string, e.g. `JN58td` |
| `GRIDLAT(grid)` / `GRIDLON(grid)` | cell-centre latitude / longitude |
| `GRIDDIST(grid_a, grid_b)` | great-circle distance (km) |
| `GRIDBEARING(grid_a, grid_b)` | initial bearing (degrees) |

## Worked examples

**2.4 GHz link at 1 km, 12 dBi antennas, 30 dBm TX:**

```
A1: =FSPL(1000, 2.4e9)              → 100.05   (dB)
A2: =FRIIS(30, 12, 12, 1000, 2.4e9) → -46.05   (dBm received)
```

**40 m dipole + feedline match check (75 Ω load on 50 Ω line):**

```
B1: =DIPOLELEN(7.1e6)   → 20.05    (m, half-wave with k=0.95)
B2: =VSWR(75, 50)       → 1.5
B3: =RETURNLOSS(VSWR2GAMMA(B2)) → 13.98  (dB)
```

**Grid-square distance/bearing (Munich → London):**

```
C1: =GRIDDIST("JN58td", "IO91wm")    → ~920    (km)
C2: =GRIDBEARING("JN58td", "IO91wm") → ~300    (degrees, WNW)
```

## Ham reference data

| Function | Returns |
| --- | --- |
| `HAMBAND(freq_hz)` | US amateur band name for a frequency (e.g. `14.1e6` → `20m`), `#N/A` outside any band |
| `CTCSSTONE(n)` | the *n*-th standard EIA CTCSS tone (1–50), in Hz |
| `NEARESTCTCSS(freq_hz)` | the standard CTCSS tone nearest a measured frequency |

## GUI tools (*Tools → Scientific*)

- **RF toolkit** — a mode-switching dialog for **link budget**, **coax line**,
  **antenna dimensions**, and **L-network matching**, showing results in both
  metric and imperial where it helps.
- **Smith chart** — plots a load impedance and its reflection coefficient, reports
  VSWR / return loss, and computes the two L-network matching solutions.
- **Antenna pattern** — a polar plot of the analytic dipole / array patterns with
  directivity (dBi) and half-power beamwidth. It re-plots live as you change N /
  spacing / phase, and **exports the pattern as SVG** or a **NEC `.nec`** deck.

## Antenna impedance

Closed-form dipole input impedance by the induced-EMF method (validated against the
textbook 73.1 + j42.5 Ω half-wave result):

| Function | Returns |
| --- | --- |
| `DIPOLER(length_wl, [radius_wl])` | input resistance (Ω) |
| `DIPOLEX(length_wl, [radius_wl])` | input reactance (Ω) |
| `RADRESIST(length_wl)` | radiation resistance (Ω) |
| `RESONANTLEN([radius_wl])` | resonant length (wavelengths), just under 0.5 λ |

## Antenna modeling — Method of Moments & NEC

For real wire-antenna analysis, abax has a thin-wire **Method of Moments** solver
(pure stdlib), available in the Python console:

```python
from abax.core.science import mom, wire_mom, nec

mom.dipole_input_impedance(0.5, 1e-3)          # a straight dipole
wire_mom.yagi(0.47, [(0.5, -0.25), (0.45, 0.15)], spacing_wl=0.2)  # a Yagi
```

- `mom` — a straight center-fed dipole. A single basis reproduces the induced-EMF
  impedance to 5 significant figures; the converged multi-segment result matches NEC.
- `wire_mom` — arbitrary 3-D wire structures (bent wires, V antennas, parasitic
  **Yagi** arrays), with a far-field pattern and front-to-back ratio.
- `nec` — read and write NEC2 `.nec` decks (`parse_nec` / `to_nec` / `solve`), so
  abax exchanges models with 4nec2 / EZNEC / xnec2c. The Antenna pattern viewer's
  *Export NEC* button writes a deck for the current geometry.

A live PyNEC adapter (for reference-grade accuracy) remains a future option; the
built-in solver is the working path.

## Signal / DSP

RF signal work is served by the no-numpy DSP stack (*Tools → Signal / data tool*):
FFT / STFT / spectrogram, **Welch PSD** (real one-sided and complex **I/Q**
two-sided — a two-column selection is read as quadrature), interpolation,
Butterworth/FIR filters, and ODE solvers. See
[data-science.md](data-science.md) and the console modules `fft`, `spectral`,
`filters`, `signal`.
