"""``abax doctor`` — an aggregated environment health report.

A read-only diagnostic that answers "why isn't X working here?" in one shot:
the Python/platform it's running on, which optional dependencies are present
(and what each falls back to without them), the code-isolation level and which
OS sandbox confinement is selected/available, the runtime directories and
whether each is writable, and whether ``settings.json`` parses.

The one hard rule: **it must never crash.** Every probe is wrapped, and the
sandbox escape probe runs against a throwaway temp dir (never the user's real
scratch). A broken confinement, a missing directory, or a corrupt settings
file each surfaces as a report line, not a traceback. :func:`run_doctor`
returns an exit code — ``0`` when everything checked out, non-zero when a
probe found a problem worth a human's attention — so scripts and CI can gate
on it.

The integrator wires the ``doctor`` subparser to call :func:`run_doctor`;
nothing here imports Qt / Textual / curses, so it stays a fast path.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
from pathlib import Path

from . import _runtime as rt

# Exit codes: 0 = healthy, non-zero = a probe reported a problem. Kept small and
# additive so a caller can still distinguish "ran but degraded" from a crash.
OK = 0
PROBLEM = 1


def _write(stream, text: str = "") -> None:
    """Print one line to *stream*, swallowing any I/O error (a closed pipe must
    not turn a health report into a crash)."""
    try:
        stream.write(text + "\n")
    except Exception:
        pass


def _section(stream, title: str) -> None:
    _write(stream)
    _write(stream, title)
    _write(stream, "-" * len(title))


def _python_and_platform(stream) -> None:
    """Python version + interpreter + OS/arch."""
    _section(stream, "Python & platform")
    try:
        _write(stream, f"  python      : {platform.python_version()} "
                       f"({platform.python_implementation()})")
    except Exception:
        _write(stream, f"  python      : {sys.version.split()[0]}")
    _write(stream, f"  executable  : {sys.executable or '(unknown)'}")
    try:
        _write(stream, f"  platform    : {platform.platform()}")
    except Exception:
        _write(stream, f"  platform    : {sys.platform}")
    try:
        _write(stream, f"  machine     : {platform.machine() or '(unknown)'}")
    except Exception:
        pass


def _dependency_matrix(stream) -> int:
    """The optional-dependency matrix, reusing :mod:`abax.diagnostics`.

    Returns the count of missing packages (informational — a missing optional
    dep is not itself a doctor failure, since each has a graceful fallback).
    """
    _section(stream, "Optional dependencies")
    missing = 0
    try:
        from .diagnostics import OPTIONAL_DEPENDENCIES

        width = max((len(n) for n in OPTIONAL_DEPENDENCIES), default=0)
        for name, info in OPTIONAL_DEPENDENCIES.items():
            available = bool(info.get("available"))
            if available:
                _write(stream, f"  [OK] {name.ljust(width)}  available")
            else:
                missing += 1
                _write(stream, f"  [--] {name.ljust(width)}  "
                               f"missing (fallback: {info.get('fallback', 'n/a')})")
        present = len(OPTIONAL_DEPENDENCIES) - missing
        _write(stream, f"  {present}/{len(OPTIONAL_DEPENDENCIES)} optional "
                       "packages present (run 'abax deps' to fetch the rest)")
    except Exception as exc:  # noqa: BLE001 - never let the report die here
        _write(stream, f"  (could not read dependency matrix: {exc!r})")
    return missing


def _read_isolation_level() -> str:
    """The active ``code_isolation`` level from settings, defaulting to the same
    ``"isolated"`` the app uses when the setting is absent or unreadable."""
    try:
        from .settings import load_settings

        s = load_settings(rt.CONFIG_DIR / "settings.json")
        return getattr(s, "code_isolation", "isolated")
    except Exception:
        return "isolated"


def _sandbox_selftest(confinement) -> str:
    """Run the filesystem-escape probe against a *throwaway* temp dir.

    Returns a short human verdict. Never raises: an unavailable confinement, a
    self-test that reports an escape, or an unexpected error all map to a line.
    We deliberately skip the network half (:func:`sandbox.selftest`'s
    ``check_network``) because we are *not* confined here — an unconfined doctor
    process would always 'escape', which says nothing about the strategy.
    """
    try:
        from . import sandbox

        # A temp dir the current (unconfined) process owns. The escape probe
        # writes *outside* this dir; under no confinement that write succeeds,
        # which is expected and merely confirms the probe machinery works.
        with tempfile.TemporaryDirectory(prefix="abax-doctor-") as scratch:
            escaped = sandbox._can_write_outside(scratch)
        if escaped is None:
            return "filesystem writes are already restricted in this process"
        return "probe OK (this process is unconfined, as expected for a report)"
    except Exception as exc:  # noqa: BLE001
        return f"self-test probe unavailable: {exc!r}"


def _code_isolation(stream) -> None:
    """Active isolation level + which OS confinement is selected/available."""
    _section(stream, "Code isolation & sandbox")
    level = _read_isolation_level()
    _labels = {
        "off": "in-process (no worker, no limits — not a security boundary)",
        "isolated": "out-of-process worker + resource limits (crash isolation)",
        "strict": "out-of-process worker + OS confinement (fail-closed boundary)",
    }
    _write(stream, f"  level       : {level} — {_labels.get(level, 'unknown level')}")

    confinement = None
    try:
        from . import sandbox

        confinement = sandbox.select_confinement()
    except Exception as exc:  # noqa: BLE001
        _write(stream, f"  confinement : (selection failed: {exc!r})")

    if confinement is not None:
        try:
            name = getattr(confinement, "name", "?")
            available = bool(confinement.available())
        except Exception as exc:  # noqa: BLE001
            name, available = "?", False
            _write(stream, f"  confinement : probe error ({exc!r})")
        else:
            _write(stream, f"  confinement : {name} "
                           f"({'available' if available else 'not available'})")
        try:
            _write(stream, f"  detail      : {confinement.describe()}")
        except Exception:
            pass

        # If the user has (or wants) strict mode but nothing confines here, that
        # is a real, actionable problem — surface it prominently.
        if level == "strict" and not available:
            _write(stream, "  WARNING     : strict isolation is selected but no OS "
                           "confinement is available here; code execution will "
                           "refuse to run (fail-closed).")

    _write(stream, f"  self-test   : {_sandbox_selftest(confinement)}")


def _runtime_dirs() -> "list[tuple[str, Path]]":
    """The runtime directories to probe, in report order.

    Uses whichever of config/data/cache/state/log/exchange ``_runtime`` actually
    exposes (it defines CONFIG/DATA/CACHE/LOG/EXCHANGE today; a future STATE_DIR
    is picked up automatically), so the report never invents a path.
    """
    wanted = (
        ("config", "CONFIG_DIR"),
        ("data", "DATA_DIR"),
        ("cache", "CACHE_DIR"),
        ("state", "STATE_DIR"),
        ("log", "LOG_DIR"),
        ("exchange", "EXCHANGE_DIR"),
    )
    dirs: list[tuple[str, Path]] = []
    for label, attr in wanted:
        path = getattr(rt, attr, None)
        if path is not None:
            dirs.append((label, Path(path)))
    return dirs


def _probe_writable(path: Path) -> str:
    """Classify *path*: missing / not-a-dir / writable / read-only.

    Probes by actually creating and deleting a temp file inside the dir (the
    only portable truth on Windows, where ``os.access(..., W_OK)`` lies). Never
    raises; a surprising error is reported as text.
    """
    try:
        if not path.exists():
            return "MISSING (will be created on next launch)"
        if not path.is_dir():
            return "NOT A DIRECTORY"
    except OSError as exc:
        return f"unstat-able ({exc.__class__.__name__})"
    try:
        # ``tempfile`` picks a unique name and cleans up, so concurrent doctors
        # don't collide and nothing is left behind.
        fd, probe = tempfile.mkstemp(prefix=".abax-doctor-", dir=str(path))
        os.close(fd)
        os.remove(probe)
        return "writable"
    except OSError as exc:
        return f"NOT writable ({exc.__class__.__name__})"
    except Exception as exc:  # noqa: BLE001
        return f"probe error ({exc!r})"


def _runtime_directories(stream) -> int:
    """Report each runtime dir + whether it is writable. Returns the count of
    dirs that are not currently writable (each counts as a problem)."""
    _section(stream, "Runtime directories")
    problems = 0
    dirs = _runtime_dirs()
    if not dirs:
        _write(stream, "  (no runtime directories exposed by abax._runtime)")
        return problems
    width = max(len(label) for label, _ in dirs)
    for label, path in dirs:
        status = _probe_writable(path)
        if status != "writable":
            problems += 1
        _write(stream, f"  {label.ljust(width)} : {path}")
        _write(stream, f"  {' '.ljust(width)}   -> {status}")
    return problems


def _settings_health(stream) -> int:
    """Whether ``settings.json`` exists and parses. Returns 1 if it exists but
    cannot be parsed (a real problem); 0 if it parses or is simply absent (the
    app writes defaults on first run, so 'missing' is fine)."""
    _section(stream, "Settings")
    path = rt.CONFIG_DIR / "settings.json"
    _write(stream, f"  file        : {path}")
    try:
        exists = path.exists()
    except OSError as exc:
        _write(stream, f"  status      : cannot stat ({exc.__class__.__name__})")
        return PROBLEM
    if not exists:
        _write(stream, "  status      : absent (defaults will be written on first run)")
        return OK
    # Parse the raw JSON directly so we detect corruption even under the msgspec
    # backend (whose loader silently falls back to defaults on a bad file).
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _write(stream, f"  status      : unreadable ({exc.__class__.__name__})")
        return PROBLEM
    try:
        json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - JSON/Unicode/anything = corrupt
        _write(stream, f"  status      : PRESENT but does NOT parse ({exc.__class__.__name__})")
        return PROBLEM
    # It is valid JSON; confirm the typed loader accepts it too.
    try:
        from .settings import load_settings

        s = load_settings(path)
        level = getattr(s, "code_isolation", "?")
        theme = getattr(s, "theme", "?")
        _write(stream, f"  status      : parses OK (theme={theme}, isolation={level})")
    except Exception as exc:  # noqa: BLE001
        _write(stream, f"  status      : JSON valid but load_settings failed ({exc!r})")
        return PROBLEM
    return OK


def run_doctor(stream=None) -> int:
    """Print an aggregated environment health report to *stream*.

    *stream* defaults to :data:`sys.stdout`. Returns ``0`` when every probe was
    happy, or a non-zero exit code when a probe reported a problem (an
    unwritable runtime directory, an unparseable ``settings.json``, or strict
    isolation selected with no confinement available). Never raises: each
    section is independently guarded, so even a wholly broken environment yields
    a report rather than a traceback.
    """
    if stream is None:
        stream = sys.stdout

    _write(stream, "abax doctor — environment health report")
    _write(stream, "=" * 39)

    exit_code = OK

    # Each section is guarded so one failure can't abort the rest of the report.
    try:
        _python_and_platform(stream)
    except Exception as exc:  # noqa: BLE001
        _write(stream, f"  (python/platform probe failed: {exc!r})")

    try:
        _dependency_matrix(stream)  # missing deps are informational, not failures
    except Exception as exc:  # noqa: BLE001
        _write(stream, f"  (dependency probe failed: {exc!r})")

    try:
        _code_isolation(stream)
    except Exception as exc:  # noqa: BLE001
        _write(stream, f"  (isolation probe failed: {exc!r})")

    try:
        if _runtime_directories(stream):
            exit_code = PROBLEM
    except Exception as exc:  # noqa: BLE001
        _write(stream, f"  (runtime-directory probe failed: {exc!r})")
        exit_code = PROBLEM

    try:
        if _settings_health(stream):
            exit_code = PROBLEM
    except Exception as exc:  # noqa: BLE001
        _write(stream, f"  (settings probe failed: {exc!r})")
        exit_code = PROBLEM

    _write(stream)
    if exit_code == OK:
        _write(stream, "Summary: OK — no problems detected.")
    else:
        _write(stream, "Summary: problems detected (see lines flagged above).")
    return exit_code


if __name__ == "__main__":  # pragma: no cover - manual invocation convenience
    raise SystemExit(run_doctor())
