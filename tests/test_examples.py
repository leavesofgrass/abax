"""Every runnable example under docs/examples ships tested — and stays tested.

Each ``docs/examples/<category>/<name>/run.py`` is executed in a subprocess
from a temporary working directory (so ``out/`` artifacts never land in the
repo), with the repo root on PYTHONPATH (the installed-package equivalent).
Exit code 0 is the contract: an example that needs an optional dependency must
degrade gracefully (print a pointer and exit 0), never traceback.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RUNNERS = sorted(REPO.glob("docs/examples/*/*/run.py"))


def _example_id(path: Path) -> str:
    return f"{path.parent.parent.name}/{path.parent.name}"


def test_examples_exist():
    assert RUNNERS, "no docs/examples/*/*/run.py found — was the tree moved?"


@pytest.mark.parametrize("runner", RUNNERS, ids=_example_id)
def test_example_runs_clean(runner: Path, tmp_path: Path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        [sys.executable, str(runner)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"{runner} exited {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
