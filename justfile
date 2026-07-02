# Interpreter: the `py` launcher locally on Windows, `python3` elsewhere. CI sets
# JUST_PYTHON=python so `just` uses the exact setup-python interpreter (the `py`
# launcher on a runner can otherwise pick a newer Python that lacks the deps).
python := env_var_or_default("JUST_PYTHON", if os_family() == "windows" { "py" } else { "python3" })
pkg    := "abax"

default:
    @just --list

install:
    {{python}} -m pip install -e ".[dev,thin]"

test *args:
    {{python}} -m pytest {{args}}

# Parallel run across all cores (pytest-xdist, in the dev extra). The GUI tests
# now dispose their windows (conftest + per-fixture teardown), so nothing
# accumulates and the whole suite is safe under -n auto — the ~40-min
# single-threaded suite finishes in a few minutes.
test-fast *args:
    {{python}} -m pytest -n auto {{args}}

lint:
    {{python}} -m ruff check {{pkg}}/

# Formatting is opt-in: the repo hand-aligns some literal tables that the
# formatter would reflow. Run `just fmt` to apply, `just fmt-check` to verify.
fmt:
    {{python}} -m ruff format {{pkg}}/

fmt-check:
    {{python}} -m ruff format --check {{pkg}}/

pyz:
    {{python}} make_pyz.py

pyz-smoke: pyz
    {{python}} abax.pyz --help
    {{python}} abax.pyz --version
    {{python}} abax.pyz --deps

wheel:
    {{python}} -m build --wheel

archive:
    {{python}} -m build --sdist

deps:
    {{python}} -m {{pkg}} --deps

check: lint test pyz pyz-smoke
    @echo "All checks passed."

clean:
    rm -rf dist/ build/ *.pyz *.egg-info __pycache__ .pytest_cache _stage/
