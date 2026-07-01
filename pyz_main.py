"""Stdlib-only .pyz bootstrapper.

This file MUST import only the Python standard library — verified by an AST
walk in make_pyz.py and tests/test_pyz.py. It locates the bundled package on
sys.path and hands control to abax.app.main.
"""

import os
import sys
import zipfile  # noqa: F401  (kept to assert stdlib-only surface)


def bootstrap():
    # When run as a zipapp, this file's directory is the archive root, which is
    # already on sys.path. Just dispatch to the real entry point.
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from abax.app import main

    return main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(bootstrap())
