"""PyInstaller entry point for abax.exe / abaxw.exe.

Same behavior as the installed `abax` script: no arguments opens the GUI, and
the whole CLI surface (view / convert / get / tui / doctor / ...) works. The
--run-console-worker escape hatch lives inside abax.app.main.
"""
import multiprocessing
import sys

# Frozen apps must call this first: a re-exec'd child (multiprocessing spawn,
# joblib/loky) would otherwise run the app instead of the worker bootstrap.
multiprocessing.freeze_support()

from abax.app import main  # noqa: E402

sys.exit(main())
