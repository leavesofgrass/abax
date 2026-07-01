"""venv bootstrap launcher.

Creates a local .venv if missing, installs abax with the requested extras,
and re-execs the CLI inside it. The fast paths (--help/--version/--deps) short
out *before* any venv work, per the spec.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).parent
VENV = ROOT / ".venv"
FAST_PATHS = {"--help", "-h", "--version", "--deps"}


def _venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def main() -> int:
    args = sys.argv[1:]

    # Fast path: never create a venv just to print help/version/deps.
    if args and args[0] in FAST_PATHS:
        sys.path.insert(0, str(ROOT))
        from abax.app import main as abax_main

        return abax_main(args)

    py = _venv_python()
    if not py.exists():
        print("Creating .venv …", file=sys.stderr)
        venv.create(VENV, with_pip=True)
        subprocess.check_call([str(py), "-m", "pip", "install", "-e", ".[fast-io]"], cwd=ROOT)

    if Path(sys.executable).resolve() != py.resolve():
        os.execv(str(py), [str(py), "-m", "abax", *args])
    from abax.app import main as abax_main

    return abax_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
