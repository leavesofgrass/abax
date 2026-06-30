"""Layer-seam guard: ``qcell.core`` imports only the standard library at import
time.

Optional third-party deps (numpy, pandas, pyte, …) are imported lazily inside
functions or under ``if TYPE_CHECKING``; core never reaches up into
``qcell.engine`` / ``qcell.gui`` / ``qcell.tui`` (the dependency arrow points
downward). The one sanctioned cross-module dependency is ``qcell._runtime`` — the
paths/dirs helper, itself stdlib-only. A reorg is exactly when a stray import can
slip across the seam, so this test pins the invariant the architecture doc states.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import qcell

ROOT = pathlib.Path(qcell.__file__).parent
CORE = ROOT / "core"
STDLIB = set(sys.stdlib_module_names)
ALLOWED_QCELL = {"qcell", "qcell._runtime"}


def _is_type_checking(test) -> bool:
    return ((isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
            or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"))


def _runtime_imports(tree):
    """Yield import nodes that execute at import time — i.e. not inside a function
    and not under an ``if TYPE_CHECKING:`` block."""
    def walk(node, in_func):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield from walk(child, True)
            elif isinstance(child, ast.If) and _is_type_checking(child.test):
                continue  # type-only block; not executed at runtime
            else:
                if isinstance(child, (ast.Import, ast.ImportFrom)) and not in_func:
                    yield child
                yield from walk(child, in_func)
    yield from walk(tree, False)


def _abs_module(node: ast.ImportFrom, pkg_parts: list[str]) -> str | None:
    if node.level == 0:
        return node.module
    base = pkg_parts[: len(pkg_parts) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


def _allowed(mod: str) -> bool:
    root = mod.split(".")[0]
    return root in STDLIB or mod in ALLOWED_QCELL or mod.startswith("qcell.core")


def test_core_is_stdlib_only_at_import_time():
    offenders = []
    for path in sorted(CORE.rglob("*.py")):
        pkg = ["qcell", *path.relative_to(ROOT).parts[:-1]]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in _runtime_imports(tree):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import)
                    else [_abs_module(node, pkg)])
            for mod in mods:
                if mod and not _allowed(mod):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {mod!r}")
    assert not offenders, (
        "qcell.core must import only the standard library at import time "
        "(optional deps go in lazy/in-function imports):\n" + "\n".join(offenders))
