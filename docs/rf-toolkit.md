# RF / amateur-radio toolkit

abax ships a set of **radio-frequency engineering functions** — power/level
conversions, transmission-line and matching math, link-budget and propagation
formulas, antenna helpers, and the **Maidenhead grid locator** — so you can build a
link budget, antenna, or matching spreadsheet natively. They are backed by
[`abax/core/science/rf.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/rf.py) (pure standard library;
no third-party dependency).

See also: [formula reference](formula-reference.md) ·
[data analysis](data-analysis.md) · [index](index.md) ·
[contest log scoring example](examples/radio/contest-log-scoring/README.md).

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
The **RF toolkit dialog** and **Smith chart** (*Radio* menu) accept MHz / feet
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
| `QWMATCH(z1, z2)` | quarter-wave transformer impedance √(Z₁·Z₂) (Ω) |
| `SWRPWR(forward_w, reflected_w)` | SWR from forward / reflected power |

## Component & antenna design (radio math)

Resonant-circuit component values, loaded-Q / bandwidth, inductor design, and
antenna dimensions, backed by
[`abax/core/science/rf_math.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/rf_math.py). All SI units
(farads, henries, metres, hertz) except `TOROIDL`/`TOROIDN`, which take the
manufacturer's **AL** value in nH/turn².

| Function | Returns |
| --- | --- |
| `CFROMXC(xc_ohms, freq_hz)` | capacitance for a target reactance (F) |
| `LFROMXL(xl_ohms, freq_hz)` | inductance for a target reactance (H) |
| `RESONANTC(freq_hz, L_henry)` | C that resonates with L at f (F) |
| `RESONANTL(freq_hz, C_farad)` | L that resonates with C at f (H) |
| `QBW(center_hz, bandwidth_hz)` | loaded Q from centre frequency and bandwidth |
| `BWQ(center_hz, q)` | bandwidth from centre frequency and Q (Hz) |
| `AIRCOILL(diameter_m, length_m, turns)` | single-layer air-core inductance, Wheeler (H) |
| `AIRCOILN(inductance_h, diameter_m, length_m)` | turns for a target air-core inductance |
| `TOROIDL(al_nh, turns)` | toroid inductance from an AL value (H) |
| `TOROIDN(inductance_h, al_nh)` | turns for a target toroid inductance |
| `LOOPLEN(freq_hz)` | full-wave loop circumference (m) |
| `DISHGAIN(diameter_m, freq_hz, [eff=0.55])` | parabolic-dish gain (dBi) |
| `DISHBW(diameter_m, freq_hz)` | parabolic-dish half-power beamwidth (degrees) |
| `DOPPLER(freq_hz, velocity_mps)` | Doppler shift for a closing/opening velocity (Hz) |
| `ZINLINER(z_load_r, z_load_x, z0, elec_len_deg)` | real part of lossless-line input impedance Zin (Ω) |
| `ZINLINEX(z_load_r, z_load_x, z0, elec_len_deg)` | imaginary part of lossless-line input impedance Zin (Ω) |
| `LINELOSS(length_m, freq_hz, matched_loss_db_per_100m)` | matched line loss (dB) |

`ZINLINER`/`ZINLINEX` transform the load `ZL = z_load_r + j·z_load_x` through a
lossless line of characteristic impedance `z0` and electrical length
`elec_len_deg` (90° = quarter wave, 180° = half wave):
`Zin = Z0·(ZL + jZ0·tan βl)/(Z0 + jZL·tan βl)`. A quarter-wave line maps `ZL` to
`Z0²/ZL`; a half-wave line repeats the load. Return the real / imaginary parts
separately, mirroring `DIPOLER`/`DIPOLEX`.

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

## Amateur-radio reference data

| Function | Returns |
| --- | --- |
| `HAMBAND(freq_hz)` | US amateur band name for a frequency (e.g. `14.1e6` → `20m`), `#N/A` outside any band |
| `CTCSSTONE(n)` | the *n*-th standard EIA CTCSS tone (1–50), in Hz |
| `NEARESTCTCSS(freq_hz)` | the standard CTCSS tone nearest a measured frequency |
| `DXCC(callsign)` | DXCC entity for a callsign (`=DXCC("W1AW")` → `United States`); handles portable prefixes and operational suffixes |

`DXCC` is backed by a 378-prefix table (`abax/core/science/dxcc.py`); it strips
trailing operational suffixes (`/P`, `/M`, `/QRP`, …) and honours a leading
re-location prefix (`DL/W1AW` → `Germany`), matching on the longest prefix in the
table.

## ADIF logbook (.adi / .adif)

abax reads and writes **ADIF** (Amateur Data Interchange Format) logbooks, backed by
[`abax/core/io/adif_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/adif_io.py) (pure standard library):

- **Open** a `.adi`/`.adif` file (*File → Open*) and abax loads it into a sheet named
  **Log** — the header row is the union of ADIF field names (in first-seen order) and
  each QSO record becomes a row.
- **Save As** a `.adi`/`.adif` file (*File → Save As*) writes the sheet back out as a
  valid ADIF document (header row = field names, one `<…:len>value…<EOR>` record per
  data row).
- The parser skips an optional header (through `<EOH>`), is case-insensitive, and
  measures field lengths in **UTF-8 bytes** so values with non-ASCII characters survive
  a round-trip. `abax.core.io.adif_io` is also exposed in the Python console as `adif`
  (`parse_adif` / `to_adif` / `records_to_grid` / `grid_to_records`).

Combine it with `DXCC` in the grid — e.g. `=DXCC(A2)` in a column next to your logged
callsigns — to annotate the entities you've worked.

## POTA/SOTA & contest logging

abax has a small logging layer for **Parks/Summits On The Air** activations and
contest operating, backed by [`abax/core/science/hamlog.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/hamlog.py)
(pure standard library). It gives the grid two spreadsheet functions and a live
GUI logger, both built on the same dupe / scoring primitives.

| Function | Returns |
| --- | --- |
| `ISDUPE(call, band, mode, [log_range])` | `TRUE` if `(call, band, mode)` already appears in `log_range` |
| `QSOPOINTS(mode, [ruleset])` | point value of one QSO in `mode` under a named ruleset |

`log_range` is a range of prior QSOs laid out one per row as `call \| band \| mode`
(extra columns ignored); omit it and the log is treated as empty. `QSOPOINTS`
defaults to the `generic` ruleset (1 pt/QSO); under `fieldday` a CW/digital QSO
scores 2 and phone 1 (ARRL Field Day 7.3.1).

**Duplicate detection** works **per band per mode** with **callsign
normalisation** — a call is upper-cased and stripped of portable decorations
before comparison, so `W1AW`, `w1aw/p` and `VE3/W1AW` all collide, and modes are
folded onto a family (`USB`/`LSB` → `SSB`, `FT8`/`PSK31`/`RTTY` → data) so those
count together. The dupe key defaults to *call + band + mode* (the POTA/contest
"once per band per mode" convention); the **SOTA** preset collapses band and
mode so a summit counts once regardless.

**Point / multiplier tally.** Scoring walks a log in order, marks each QSO new or
dupe (a dupe earns 0 points), applies the ruleset's per-QSO point value, and
counts multipliers (the distinct non-blank multiplier tokens among credited
QSOs). The final score is credited points × multipliers (× 1 when a ruleset has
no multipliers). Built-in presets are `generic`, `pota`, `sota`, `fieldday`, and
`arrl-dx`.

### Activation log dialog

*Tools → Radio → Activation log (POTA/SOTA)* opens a keyboard-first logger
(`HamLogDialog`). Pick a ruleset, type a callsign, choose band/mode (time
defaults to now, UTC), and *Log QSO*: the contact is added to an in-memory log,
scored against the selected ruleset, and checked for dupes. **Dupe rows are
highlighted** and a **running tally** — valid QSOs / dupes / points / score —
updates on every entry. *Write to sheet* drops the whole scored log into a new
worksheet (with a summary block), where the ADIF logbook tools can export it.

## Satellite passes (SGP4)

abax predicts **satellite passes** from a two-line element set (TLE) and an
observer, backed by [`abax/engine/satellite.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/satellite.py).
Given a TLE plus an observer (latitude, longitude, altitude) it computes, for
each pass over a time window, the **rise**, **culmination** and **set** times,
the **azimuth** at each of those moments, and the **maximum elevation** at
culmination.

Orbit **propagation** uses the optional **`sgp4`** package (a pure-Python
implementation of the standard SGP4 model); everything after propagation —
converting the orbit position to the observer's topocentric frame for azimuth and
elevation — is pure standard library. Importing the module never fails:
`satellite.available()` reports whether the propagation path can run, and a
predictor call raises a descriptive "install sgp4" message when the package is
absent.

```python
from abax.engine import satellite

satellite.available()                 # True iff the 'sgp4' package is importable
passes = satellite.predict_passes(
    tle,                              # a TLE string (three-line or two-line) or parsed Tle
    (40.71, -74.01, 10.0),           # observer: lat°, lon°, altitude (m)
    start, hours=24,                  # window start (UTC) and length
    min_elevation_deg=10.0,           # only report passes above this elevation
)
```

Each returned pass carries the satellite name, `rise` / `culmination` / `set`
(timezone-aware UTC datetimes), `max_elevation`, the rise / max / set azimuths,
and the duration in seconds.

`sgp4` is an **optional dependency** shipped in the `satellite` extra:

```bash
pip install abax[satellite]      # or: pip install sgp4
```

### Satellite pass predictor dialog

*Tools → Radio → Satellite passes (SGP4)* opens the predictor (`SatelliteDialog`).
Paste a TLE (the name line is optional and a sample ISS element set is prefilled),
set the observer and the window (start time in UTC, length in hours, minimum
elevation), and **Predict** (or press F5). Passes appear in a table — rise,
culmination and set with their azimuths, the maximum elevation, and the duration
— and *Passes → new sheet* drops them into a fresh sheet. When `sgp4` is not
installed the dialog stays usable but Predict reports the "install sgp4" message
instead of computing.

## GUI tools (the *Radio* menu)

All of the RF/amateur-radio tools live under the **Tools → Radio** submenu (general
math tools stay under *Tools → Scientific*):

- **RF toolkit** — a mode-switching dialog for **link budget**, **coax line**,
  **antenna dimensions**, and **L-network matching**, showing results in both
  metric and imperial where it helps.
- **Smith chart** — plots a load impedance and its reflection coefficient, reports
  VSWR / return loss, and computes the two L-network matching solutions.
- **Antenna pattern** — a polar plot of the analytic dipole / array patterns with
  directivity (dBi) and half-power beamwidth. It re-plots live as you change N /
  spacing / phase, and **exports the pattern as SVG** or a **NEC `.nec`** deck.
- **Antenna modeler** — a Method-of-Moments dialog for a real **dipole** or
  **Yagi**, reporting gain / front-to-back / feed impedance and a radiation cut,
  with a **Ground** option for an over-ground take-off pattern (see *Antenna
  modeling* below).
- **Activation log (POTA/SOTA)** — the keyboard-first activation logger with live
  dupe highlighting and a running score (see *POTA/SOTA & contest logging*).
- **Satellite passes (SGP4)** — the TLE + observer pass predictor (see *Satellite
  passes*); needs the optional `sgp4` package.
- **RF reference** — a filterable view of the US amateur band plan (with width and
  mid-band wavelength) and the 50 EIA CTCSS tones; double-click (or *Send to cell*)
  writes a value into the grid, and *Bands → new sheet* drops the band plan in.
- **I/Q → SVG** — reads a two-column (I, Q) selection and exports the constellation
  as an SVG, reporting power in dBFS.
- **Solve NEC deck (PyNEC)** — see below.

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
  **Yagi** arrays), with a far-field pattern and front-to-back ratio. It also
  models **multi-wire junctions** and an **image-plane ground reflection** — see
  *Junctions & ground reflection* below.
- `nec` — read and write NEC2 `.nec` decks (`parse_nec` / `to_nec` / `solve`), so
  abax exchanges models with 4nec2 / EZNEC / xnec2c. The Antenna pattern viewer's
  *Export NEC* button writes a deck for the current geometry.

### Junctions & ground reflection

`wire_mom` is more than a straight dipole — two capabilities let it model real
installed antennas rather than an idealised element in free space:

- **Multi-wire junctions.** When several wires share an endpoint (to within a
  tiny node tolerance) they form a *junction*, and the solver enforces
  **Kirchhoff current continuity** there instead of pinning the shared point to
  zero current. At a junction of degree *d* it builds *d − 1* piecewise-sinusoidal
  bases (a reference arm carrying current into the node, each other arm carrying a
  share out), so the current the solution pushes into one arm equals the sum it
  draws out of the rest. This is what lets **verticals with radials**, **loops**,
  and **fed T-junctions** solve correctly. A single wire's ordinary interior node
  is just the *d = 2* case and reduces to the classic before/after pair, so the
  free-space single-wire path is unchanged.
- **Image-plane ground reflection.** `radiation_vector_ground` /
  `far_field_intensity_ground` superpose the structure (assumed at *z ≥ 0*) with
  its image in a horizontal ground plane at *z = 0*: each element gets a mirror
  image whose horizontal current is negated and vertical current kept, scaled by
  a reflection coefficient. That turns the free-space elevation cut — which is
  symmetric about the horizon — into a real **take-off pattern** for a given
  install **height** and ground, asymmetric about the horizon and zero below it.
  A perfect (PEC) ground uses Γ = −1 (horizontal) / +1 (vertical); a finite ground
  uses a **Fresnel** reflection coefficient from a relative permittivity and
  conductivity (`Ground("finite", …)`).

Both are surfaced in the **Antenna modeler** dialog (*Tools → Radio → Antenna
modeler*, backed by `wire_mom`). Its **Ground** chooser offers *Free space*
(the classic symmetric pattern), *Perfect ground* (structure on the plane), and
*Perfect ground + height* (which enables a **Height above ground (λ)** field and
lifts the geometry before folding in the image reflection). Choose an elevation
cut with a ground option and the plot becomes a genuine over-ground take-off
pattern; the dialog labels it *(over ground)* so it is never mistaken for the
free-space cut. Over-ground cuts always use the built-in image model even when
PyNEC is present, since PyNEC's free-space read-back cannot express the take-off
pattern.

### Optional PyNEC solver (reference-grade)

For reference-grade accuracy abax can hand a deck to **PyNEC** (the SWIG binding
to the classic NEC-2 engine) when it is installed — *Radio → Solve NEC deck
(PyNEC)*, backed by `engine/necpy.py`. It is a fully **optional** dependency
with a **graceful fallback**: if PyNEC is not importable, abax silently uses its
own built-in Method-of-Moments solver instead, so nothing breaks. `abax --deps`
reports whether PyNEC is present.

**Platform note (why it may be absent).** PyNEC is a compiled C++/SWIG
extension and does **not** publish wheels for every platform — notably there are
no Windows wheels. It is included in the `nec` extra and in `all` (so picking the
**All** feature preset *attempts* it), but on a machine
without a matching wheel that best-effort build can fail quietly; abax then just
keeps using the built-in solver. This is deliberate — PyNEC is a
nice-to-have accelerator, not a requirement.

To install it yourself:

```bash
pip install abax[nec]      # or: pip install PyNEC
```

On Windows (or any platform lacking a wheel) the build needs a C/C++ toolchain
and SWIG on `PATH` — e.g. MSVC Build Tools plus `swig`. If that is more than you
want, do nothing: the built-in `mom` / `wire_mom` / `nec` path above is the
supported default and matches NEC on the validation cases.

## Signal / DSP

RF signal work is served by the no-numpy DSP stack (*Tools → Signal / data tool*):
FFT / STFT / spectrogram, **Welch PSD** (real one-sided and complex **I/Q**
two-sided — a two-column selection is read as quadrature), interpolation,
Butterworth/FIR filters, and ODE solvers. See
[data-science.md](data-science.md) and the console modules `fft`, `spectral`,
`filters`, `signal`.
