python := if os_family() == "windows" { "py" } else { "python3" }
pkg    := "abax"

default:
    @just --list

install:
    {{python}} -m pip install -e ".[dev,thin]"

test *args:
    {{python}} -m pytest {{args}}

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
