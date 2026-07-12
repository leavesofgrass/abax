"""Score an amateur-radio contest log: dupes, points, running totals.

The same engine behind the ISDUPE / QSOPOINTS formula functions and the
POTA/SOTA activation dialog, driven from Python.
"""

from abax.core.science.hamlog import score_log

log = [
    {"CALL": "K7ABC",  "BAND": "20m", "MODE": "CW"},
    {"CALL": "N0XYZ",  "BAND": "20m", "MODE": "SSB"},
    {"CALL": "K7ABC",  "BAND": "40m", "MODE": "CW"},   # new band — counts
    {"CALL": "K7ABC",  "BAND": "20m", "MODE": "CW"},   # dupe!
    {"CALL": "W1AW",   "BAND": "15m", "MODE": "CW"},
    {"CALL": "N0XYZ",  "BAND": "20m", "MODE": "SSB"},  # dupe!
    {"CALL": "VE3DEF", "BAND": "20m", "MODE": "FT8"},
]

result = score_log(log, "generic")

for row in result.rows:
    flag = "DUPE" if row.is_dupe else f"{row.points} pt"
    print(f"{row.call:<7} {row.band:<4} {row.mode:<4} {flag:>5}"
          f"   running: {row.running_qsos} QSOs / {row.running_points} pts")

print(f"\n{result.qso_count} QSOs, {result.dupe_count} dupes, "
      f"{result.point_total} points -> score {result.score}")
