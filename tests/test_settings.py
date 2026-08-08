"""Settings persistence: defaults, save/load round-trip, lazy schema migration.

The module keeps two interchangeable back ends (msgspec Struct when installed, a
stdlib dataclass + ``json`` otherwise) and promises they behave the same. The
``stdlib_settings`` fixture below re-executes the module with msgspec forced off
so the fallback branch is exercised on a machine that *has* msgspec, and the
divergences that survive that promise are pinned explicitly.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

import abax
import abax._runtime as rt
from abax.settings import (
    SCHEMA_VERSION,
    Settings,
    _migrate_settings,
    load_settings,
    save_settings,
)

_SRC = Path(abax.__file__).parent / "settings.py"
# Which branch the imported abax.settings actually took (msgspec Structs carry
# __struct_fields__; the fallback is a plain dataclass).
_MSGSPEC_BACKEND = hasattr(Settings, "__struct_fields__")


@pytest.fixture()
def stdlib_settings(monkeypatch):
    """``abax.settings`` re-executed with msgspec forced off (dataclass branch).

    Loaded under its own name and never installed over ``abax.settings``, so the
    rest of the suite keeps the classes it imported at collection time. It does
    have to live in ``sys.modules`` while it executes — ``@dataclass`` resolves
    annotations through ``sys.modules[cls.__module__]``.
    """
    monkeypatch.setattr(rt, "_HAS_MSGSPEC", False)
    name = "abax._settings_stdlib_under_test"
    spec = importlib.util.spec_from_file_location(name, _SRC)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, mod)
    spec.loader.exec_module(mod)
    return mod


def _fields(cls):
    """Field names of either back end's Settings, in declaration order."""
    names = getattr(cls, "__struct_fields__", None)
    return tuple(names) if names is not None else tuple(cls.__dataclass_fields__)


def _bump(value):
    """Move a value off its default while keeping its JSON type."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 7
    if isinstance(value, float):
        return value + 0.25
    if isinstance(value, str):
        return value + "-x"
    if isinstance(value, list):
        return ["one", 2, {"three": True}]
    if isinstance(value, dict):
        return {"x": 10, "nested": {"y": [1, 2]}}
    return value


def _populated(cls):
    """A Settings with every data field moved off its default."""
    base = cls()
    kwargs = {
        name: _bump(getattr(base, name))
        for name in _fields(cls)
        if name != "schema_version"
    }
    return cls(**kwargs)


# --- defaults --------------------------------------------------------------


def test_defaults_are_the_safe_baseline():
    s = Settings()
    # Every capability that reaches out (code, plugins, network, other files)
    # is off until the user consents.
    assert s.code_consent is False
    assert s.plugins_enabled is False
    assert s.live_data_enabled is False
    assert s.external_refs_enabled is False
    assert s.code_isolation == "isolated"   # worker + limits, not in-process
    # Everyday defaults.
    assert s.theme == "galaxy" and s.tui_theme == "galaxy"
    assert s.vim_mode is True and s.show_toolbar is True
    assert s.zoom == 1.0
    assert s.autosave_enabled is True and s.autosave_interval == 30
    assert s.calc_iterative is False       # circular refs surface as #CIRC!
    assert s.windowed_store_capacity == 0  # AUTO
    assert s.chart_backend == "auto"
    assert s.schema_version == SCHEMA_VERSION


def test_mutable_defaults_are_not_shared_between_instances():
    a, b = Settings(), Settings()
    a.recent_files.append("book.abax")
    a.window_geometry["x"] = 10
    a.fm_buttons.append({"label": "Zip"})
    assert b.recent_files == [] and b.window_geometry == {} and b.fm_buttons == []
    assert Settings().recent_files == []


# --- save / load round-trip ------------------------------------------------


def test_every_field_survives_a_round_trip(tmp_path):
    # Derived from the defaults, so a field added later is covered automatically.
    s = _populated(Settings)
    path = tmp_path / "settings.json"
    save_settings(s, path)
    assert load_settings(path) == s


def test_round_trip_preserves_container_shape_and_numeric_types(tmp_path):
    s = Settings()
    s.recent_files = ["b.abax", "a.abax", "b.abax"]  # order and dupes are the user's
    s.window_geometry = {"main": {"x": 10, "y": 20}, "maximized": False}
    s.zoom = 1.25
    s.calc_max_change = 1e-9
    path = tmp_path / "settings.json"
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.recent_files == ["b.abax", "a.abax", "b.abax"]
    assert loaded.window_geometry == {"main": {"x": 10, "y": 20}, "maximized": False}
    assert loaded.zoom == 1.25 and loaded.calc_max_change == 1e-9


def test_saved_file_is_plain_json_at_the_current_schema(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings()
    s.theme = "nord"
    save_settings(s, path)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["theme"] == "nord"
    assert on_disk["schema_version"] == SCHEMA_VERSION
    # Nothing is elided: every field is written, so the file is self-describing.
    assert set(on_disk) == set(_fields(Settings))


def test_paths_may_be_plain_strings(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings()
    s.last_cell = "AA42"
    save_settings(s, str(path))
    assert load_settings(str(path)).last_cell == "AA42"


def test_save_replaces_the_previous_file_entirely(tmp_path):
    path = tmp_path / "settings.json"
    fat = Settings()
    fat.recent_files = [f"book{i}.abax" for i in range(50)]
    save_settings(fat, path)
    save_settings(Settings(), path)
    assert load_settings(path).recent_files == []
    json.loads(path.read_text(encoding="utf-8"))  # no trailing garbage


def test_non_ascii_values_survive_a_round_trip(tmp_path):
    # settings.json is written on whatever the platform's default encoding is,
    # so anything non-ASCII has to come back through escapes, not raw bytes.
    path = tmp_path / "settings.json"
    s = Settings()
    s.theme = "nørd"
    s.last_cell = "Ω1"
    s.recent_files = ["данные.abax", "図表.abax"]
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.theme == "nørd" and loaded.last_cell == "Ω1"
    assert loaded.recent_files == ["данные.abax", "図表.abax"]


def test_save_does_not_create_missing_parent_dirs(tmp_path):
    # Callers own the directory (abax creates CONFIG_DIR at import); saving into
    # a directory that does not exist must fail loudly rather than silently drop.
    with pytest.raises(OSError):
        save_settings(Settings(), tmp_path / "nope" / "settings.json")


# --- missing / malformed input ---------------------------------------------


def test_missing_file_yields_defaults(tmp_path):
    assert load_settings(tmp_path / "never-written.json") == Settings()


@pytest.mark.parametrize(
    "blob",
    [
        b"",                       # empty file (interrupted write)
        b"   \n",                  # whitespace only
        b"{ not json",             # truncated object
        b'{"theme": "nord"',       # unterminated
        b"null",                   # valid JSON, wrong shape
        b"[1, 2, 3]",              # valid JSON, wrong shape
        b'"nord"',                 # valid JSON, wrong shape
        b"\x00\x01\x02",           # binary garbage
    ],
    ids=["empty", "blank", "truncated", "unterminated", "null", "list", "str", "binary"],
)
def test_malformed_file_yields_defaults(tmp_path, blob):
    path = tmp_path / "settings.json"
    path.write_bytes(blob)
    assert load_settings(path) == Settings()


def test_unreadable_path_yields_defaults(tmp_path):
    # A directory where a file was expected: read fails, defaults stand in.
    assert load_settings(tmp_path) == Settings()


def test_partial_file_fills_the_rest_with_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "theme": "nord",
                                "autosave_interval": 5}), encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.theme == "nord" and loaded.autosave_interval == 5
    assert loaded.vim_mode is True and loaded.chart_backend == "auto"
    assert loaded.recent_files == []


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "theme": "nord",
                                "from_the_future": {"deep": [1]}, "column_width": 9}),
                    encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.theme == "nord"
    assert not hasattr(loaded, "from_the_future")


def test_newer_schema_version_is_left_alone(tmp_path):
    # Downgrading abax must not silently rewrite a file a newer build owns.
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION + 5, "theme": "obsidian"}),
                    encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.schema_version == SCHEMA_VERSION + 5
    assert loaded.theme == "obsidian"   # no v9->v10 remap above the current version


def test_non_numeric_schema_version_does_not_escape_load(tmp_path):
    # The migrator itself compares the version numerically...
    with pytest.raises(TypeError):
        _migrate_settings({"schema_version": "10"})
    # ...but load_settings is the guard: a hand-edited file never raises.
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": "10", "theme": "nord"}), encoding="utf-8")
    assert load_settings(path) == Settings()


# --- schema migration ------------------------------------------------------


@pytest.mark.parametrize("version", list(range(SCHEMA_VERSION + 1)))
def test_any_known_version_chains_to_current(version):
    assert _migrate_settings({"schema_version": version})["schema_version"] == SCHEMA_VERSION


def test_versionless_file_is_treated_as_v0():
    migrated = _migrate_settings({"color_scheme": "nord", "sandbox_strict": True})
    assert migrated["schema_version"] == SCHEMA_VERSION
    assert migrated["theme"] == "nord"            # v0 -> v1 rename ran
    assert migrated["code_isolation"] == "strict"  # v1 -> v2 rename ran
    assert "color_scheme" not in migrated and "sandbox_strict" not in migrated


def test_v0_theme_rename_does_not_clobber_an_existing_theme():
    migrated = _migrate_settings({"color_scheme": "nord", "theme": "galaxy"})
    assert migrated["theme"] == "galaxy"
    assert "color_scheme" in migrated  # left as a stray key; dropped on load


@pytest.mark.parametrize(
    "strict,expected", [(True, "strict"), (False, "isolated")],
)
def test_v1_sandbox_bool_becomes_tri_state_isolation(strict, expected):
    migrated = _migrate_settings({"schema_version": 1, "sandbox_strict": strict})
    assert migrated["code_isolation"] == expected
    assert "sandbox_strict" not in migrated   # always dropped, never re-saved


def test_v1_migration_defers_to_an_explicit_isolation_choice():
    migrated = _migrate_settings({"schema_version": 1, "sandbox_strict": True,
                                  "code_isolation": "off"})
    assert migrated["code_isolation"] == "off"
    assert "sandbox_strict" not in migrated


def test_v3_migration_strips_retired_fields():
    migrated = _migrate_settings({"schema_version": 3, "column_width": 80,
                                  "faceplate_repo": "https://example.invalid/repo",
                                  "theme": "nord"})
    assert "column_width" not in migrated and "faceplate_repo" not in migrated
    assert migrated["theme"] == "nord"


def test_v9_obsidian_theme_is_renamed_in_both_front_ends():
    migrated = _migrate_settings({"schema_version": 9, "theme": "obsidian",
                                  "tui_theme": "obsidian"})
    assert migrated["theme"] == "galaxy" and migrated["tui_theme"] == "galaxy"
    # Only that one name is remapped.
    kept = _migrate_settings({"schema_version": 9, "theme": "nord", "tui_theme": "light"})
    assert kept["theme"] == "nord" and kept["tui_theme"] == "light"


def test_migration_only_runs_steps_newer_than_the_file(tmp_path):
    # A v2 file that somehow still carries the v0 key does *not* get the rename
    # replayed — the key is stale and is simply dropped when the struct is built.
    migrated = _migrate_settings({"schema_version": 2, "color_scheme": "nord"})
    assert "theme" not in migrated
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": 2, "color_scheme": "nord"}),
                    encoding="utf-8")
    assert load_settings(path).theme == "galaxy"


def test_migration_is_idempotent():
    once = _migrate_settings({"color_scheme": "obsidian", "sandbox_strict": False,
                              "column_width": 80, "vim_mode": False})
    twice = _migrate_settings(dict(once))
    assert twice == once
    assert once["theme"] == "galaxy" and once["code_isolation"] == "isolated"
    assert once["vim_mode"] is False


def test_lazy_migration_writes_back_a_clean_current_file(tmp_path):
    # "migrate on read, write back so later reads are free": the read applies the
    # migration, and the caller's next save leaves a file at the current schema.
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"color_scheme": "obsidian", "sandbox_strict": True,
                                "column_width": 80, "faceplate_repo": "x",
                                "vim_mode": False}), encoding="utf-8")
    loaded = load_settings(path)
    assert loaded.theme == "galaxy"          # obsidian -> galaxy, via v0 rename
    assert loaded.code_isolation == "strict"
    assert loaded.vim_mode is False
    assert loaded.schema_version == SCHEMA_VERSION
    save_settings(loaded, path)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == SCHEMA_VERSION
    for retired in ("color_scheme", "sandbox_strict", "column_width", "faceplate_repo"):
        assert retired not in on_disk
    assert load_settings(path) == loaded     # second read is a no-op migration


# --- back-end parity (stdlib dataclass fallback) ---------------------------


def test_stdlib_backend_has_the_same_fields_and_defaults(stdlib_settings):
    assert _fields(stdlib_settings.Settings) == _fields(Settings)
    fallback, primary = stdlib_settings.Settings(), Settings()
    for name in _fields(Settings):
        assert getattr(fallback, name) == getattr(primary, name), name
    assert stdlib_settings.SCHEMA_VERSION == SCHEMA_VERSION


def test_stdlib_backend_round_trips_and_migrates(stdlib_settings, tmp_path):
    path = tmp_path / "settings.json"
    s = _populated(stdlib_settings.Settings)
    stdlib_settings.save_settings(s, path)
    assert stdlib_settings.load_settings(path) == s
    # ...and the cross-backend contract: what msgspec wrote, the fallback reads.
    other = tmp_path / "from_msgspec.json"
    primary = Settings()
    primary.theme = "nord"
    primary.recent_files = ["a.abax"]
    save_settings(primary, other)
    read_back = stdlib_settings.load_settings(other)
    assert read_back.theme == "nord" and read_back.recent_files == ["a.abax"]
    # Old files migrate identically under the fallback.
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"color_scheme": "obsidian", "sandbox_strict": True}),
                      encoding="utf-8")
    migrated = stdlib_settings.load_settings(legacy)
    assert migrated.theme == "galaxy" and migrated.code_isolation == "strict"
    assert migrated.schema_version == SCHEMA_VERSION


@pytest.mark.parametrize("blob", [b"", b"{ not json", b"null", b"[1, 2]"])
def test_stdlib_backend_tolerates_malformed_files(stdlib_settings, tmp_path, blob):
    path = tmp_path / "settings.json"
    path.write_bytes(blob)
    assert stdlib_settings.load_settings(path) == stdlib_settings.Settings()
    assert stdlib_settings.load_settings(tmp_path / "gone.json") == stdlib_settings.Settings()


def test_backends_diverge_on_type_invalid_values(stdlib_settings, tmp_path):
    """Pinned divergence: only the msgspec back end validates field types.

    A hand-edited ``"vim_mode": "yes"`` makes msgspec discard the whole file and
    fall back to defaults, while the dataclass branch stores the string as-is.
    Neither raises, which is the contract callers actually depend on.
    """
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION, "vim_mode": "yes",
                                "theme": "nord"}), encoding="utf-8")
    fallback = stdlib_settings.load_settings(path)
    assert fallback.vim_mode == "yes"      # dataclass: no validation at all
    assert fallback.theme == "nord"
    if _MSGSPEC_BACKEND:
        loaded = load_settings(path)       # msgspec: one bad field voids the file
        assert loaded.vim_mode is True and loaded.theme == "galaxy"


# --- cross-backend encoding contract ---------------------------------------
#
# The two back ends write the same file to the same path, and a user really does
# swap between them: ``abax[thin]``/``abax[all]`` pull in msgspec, while a bare
# ``pip install abax`` and the portable ``abax.pyz`` run the stdlib fallback. So
# the contract is not "each back end round-trips itself" — it is "what one back
# end writes, the other reads back *identically*", non-ASCII included.
#
# msgspec's JSON is always UTF-8 with non-ASCII left raw. Anything the stdlib
# branch does with the *platform* encoding silently mangles that on a non-UTF-8
# locale (cp1252 Windows): no exception, just wrong values that load_settings
# happily keeps.
#
# One script per hazard class, so this cannot pass by luck on some codepage:
#   ø     representable in cp1252/latin-1 — the classic "looks fine, is wrong"
#   Ω     outside cp1252 entirely
#   Й 図  Cyrillic + CJK, multi-byte in UTF-8, outside cp1252
#   𝄞     non-BMP: a surrogate *pair* once \u-escaped, 4 bytes in UTF-8

_NA_THEME = "nørd"
_NA_CELL = "Ω1"
_NA_FILES = [
    "C:/Users/José/Documents/budsjett-år.abax",   # accented path — the real case
    "D:/データ/図表.abax",
    "/home/Йван/score-𝄞.abax",
]


def _non_ascii(cls):
    """A Settings carrying non-ASCII in the fields a user actually fills."""
    s = cls()
    s.theme = _NA_THEME
    s.last_cell = _NA_CELL
    s.recent_files = list(_NA_FILES)
    return s


def _assert_non_ascii_intact(loaded):
    # Codepoints, not just equality: mojibake ("nÃ¸rd") is still a perfectly
    # ordinary str, and the ordinals say *how* it broke — [110, 195, 184, 114,
    # 100], five chars, where the UTF-8 pair for ø was read as two cp1252 ones.
    assert [ord(c) for c in loaded.theme] == [ord(c) for c in _NA_THEME]
    assert loaded.theme == _NA_THEME
    assert loaded.last_cell == _NA_CELL
    assert loaded.recent_files == _NA_FILES


def _write_msgspec_shaped(path, mapping):
    """The bytes msgspec's encoder produces: UTF-8, non-ASCII left raw.

    Spelled out with the stdlib so the expectation still holds on a machine
    with no msgspec at all — which is exactly where the fallback back end is
    the only reader a user has.
    """
    path.write_bytes(json.dumps(mapping, ensure_ascii=False).encode("utf-8"))


def test_persistence_never_relies_on_the_platform_default_encoding(
        stdlib_settings, tmp_path, monkeypatch):
    """The regression guard that still works where the default *is* UTF-8.

    Every other test in this group compares bytes against decoded text, so each
    one only goes red on a host whose default encoding is not UTF-8. CI is not
    such a host: ``.github/workflows/ci.yml`` sets ``PYTHONUTF8: "1"`` for every
    job, which puts Python in UTF-8 mode, so ``read_text()`` with no ``encoding=``
    returns the right string there whether or not the bug is present. Left at
    that, the whole group would pass on CI against a reverted fix — coverage
    that cannot fail is not coverage.

    So assert the contract instead of the symptom: every file operation on
    settings.json must NAME its encoding rather than inherit the ambient one.
    That is exactly what regressed, it fails on any platform and under any
    PYTHONUTF8 setting, and it needs no non-UTF-8 locale to detect.

    The spy has to sit on ``read_text``/``write_text``, not on ``Path.open``:
    ``read_text`` passes its argument through ``io.text_encoding()``, which
    *returns* ``"utf-8"`` when the interpreter is in UTF-8 mode, so by the time
    ``open`` is reached an omitted encoding is indistinguishable from an
    explicit one. (Confirmed the hard way — the first version of this test
    watched ``Path.open`` and was itself blind under ``PYTHONUTF8=1``.)
    """
    path = tmp_path / "settings.json"
    seen: list = []
    real_read, real_write = Path.read_text, Path.write_text

    def read_spy(self, encoding=None, *args, **kwargs):
        if self == path:
            seen.append(("read_text", encoding))
        return real_read(self, encoding, *args, **kwargs)

    def write_spy(self, data, encoding=None, *args, **kwargs):
        if self == path:
            seen.append(("write_text", encoding))
        return real_write(self, data, encoding, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_spy)
    monkeypatch.setattr(Path, "write_text", write_spy)
    stdlib_settings.save_settings(_non_ascii(stdlib_settings.Settings), path)
    stdlib_settings.load_settings(path)

    assert {op for op, _ in seen} == {"read_text", "write_text"}, (
        f"expected both a read and a write of settings.json, saw {seen}")
    assert all(enc is not None for _, enc in seen), (
        f"settings.json was accessed with encoding=None — that inherits the "
        f"platform default, which is the bug this guards: {seen}")
    # utf-8 either way; the reader additionally tolerates a BOM via -sig.
    assert all(enc.lower().replace("-", "").replace("_", "") in {"utf8", "utf8sig"}
               for _, enc in seen), seen


@pytest.mark.parametrize("bom", [True, False], ids=["with-bom", "no-bom"])
def test_a_utf8_bom_does_not_wipe_the_settings(stdlib_settings, tmp_path, bom):
    """An editor-added BOM must not silently reset the user's config.

    A UTF-8 BOM is not valid JSON, so before this both back ends fell into their
    ``except Exception`` guard and returned defaults — which the next save then
    wrote over the top of. VS Code's "UTF-8 with BOM" and PowerShell 5.1
    redirection both produce one, and neither is exotic on this platform.
    """
    path = tmp_path / "settings.json"
    body = json.dumps({"schema_version": SCHEMA_VERSION, "theme": _NA_THEME,
                       "last_cell": _NA_CELL, "recent_files": _NA_FILES},
                      ensure_ascii=False).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" + body) if bom else body)

    _assert_non_ascii_intact(stdlib_settings.load_settings(path))
    if _MSGSPEC_BACKEND:                       # both back ends read this file
        _assert_non_ascii_intact(load_settings(path))


def test_stdlib_backend_reads_raw_utf8_non_ascii(stdlib_settings, tmp_path):
    """A settings.json in msgspec's byte shape loads unmangled under the fallback.

    This is the whole bug: the file is UTF-8, the reader used the locale.
    """
    path = tmp_path / "settings.json"
    _write_msgspec_shaped(path, {"schema_version": SCHEMA_VERSION, "theme": _NA_THEME,
                                 "last_cell": _NA_CELL, "recent_files": _NA_FILES})
    assert b"n\xc3\xb8rd" in path.read_bytes()   # raw UTF-8 on disk, not \u00f8
    _assert_non_ascii_intact(stdlib_settings.load_settings(path))


@pytest.mark.skipif(not _MSGSPEC_BACKEND, reason="needs the msgspec back end installed")
def test_msgspec_written_settings_read_back_under_the_stdlib_backend(stdlib_settings, tmp_path):
    """msgspec saves -> the stdlib fallback loads. End to end, both real writers."""
    path = tmp_path / "settings.json"
    save_settings(_non_ascii(Settings), path)
    # Prove the file really does carry the hazard, or the assertion below is empty.
    assert b"n\xc3\xb8rd" in path.read_bytes()
    _assert_non_ascii_intact(stdlib_settings.load_settings(path))


@pytest.mark.skipif(not _MSGSPEC_BACKEND, reason="needs the msgspec back end installed")
def test_stdlib_written_settings_read_back_under_the_msgspec_backend(stdlib_settings, tmp_path):
    """...and back the other way: the fallback saves, msgspec loads."""
    path = tmp_path / "settings.json"
    stdlib_settings.save_settings(_non_ascii(stdlib_settings.Settings), path)
    _assert_non_ascii_intact(load_settings(path))


def test_stdlib_backend_round_trips_non_ascii_on_its_own(stdlib_settings, tmp_path):
    # The single-back-end round trip that masked the bug for so long; keep it
    # pinned so the write side stays correct too.
    path = tmp_path / "settings.json"
    stdlib_settings.save_settings(_non_ascii(stdlib_settings.Settings), path)
    _assert_non_ascii_intact(stdlib_settings.load_settings(path))


def test_stdlib_backend_writes_ascii_only_json(stdlib_settings, tmp_path):
    """Pinned, deliberate divergence: the fallback escapes, msgspec does not.

    Both files decode to the same values (the tests above), but the fallback's
    bytes stay pure ASCII — ``json.dumps``' ``ensure_ascii`` default. That is
    kept on purpose: an ASCII-only file is decoded correctly by *every* reader,
    including already-shipped abax builds whose stdlib loader still reads with
    the platform encoding. Byte-identity between the back ends is not on the
    table anyway — msgspec's encoder emits compact JSON, the fallback indents.
    """
    path = tmp_path / "settings.json"
    stdlib_settings.save_settings(_non_ascii(stdlib_settings.Settings), path)
    raw = path.read_bytes()
    raw.decode("ascii")                    # no raw multi-byte anywhere
    assert rb"n\u00f8rd" in raw            # ...because it escaped instead
    assert rb"\ud834\udd1e" in raw         # non-BMP as a surrogate pair


# --- backward compatibility of the fixed reader ----------------------------


def _legacy_stdlib_bytes(mapping):
    """The bytes the *old* stdlib writer produced: ``json.dumps`` defaults.

    ``ensure_ascii=True`` meant those files were pure ASCII, which is why they
    survived being read back through the locale — and why the fixed reader,
    which insists on UTF-8, must still read every one of them.
    """
    return json.dumps(mapping, indent=2).encode("ascii")


def test_legacy_ascii_escaped_file_still_loads(stdlib_settings, tmp_path):
    path = tmp_path / "settings.json"
    path.write_bytes(_legacy_stdlib_bytes({"schema_version": SCHEMA_VERSION,
                                           "theme": _NA_THEME, "last_cell": _NA_CELL,
                                           "recent_files": _NA_FILES}))
    _assert_non_ascii_intact(stdlib_settings.load_settings(path))
    if _MSGSPEC_BACKEND:
        _assert_non_ascii_intact(load_settings(path))


def test_old_file_still_migrates_when_it_carries_non_ascii(stdlib_settings, tmp_path):
    # SCHEMA_VERSION/_migrate_settings sit in the load path, so the encoding fix
    # has to leave lazy migration working — in both byte shapes an old file can
    # have on disk.
    legacy = {"color_scheme": "obsidian", "sandbox_strict": True, "column_width": 80,
              "last_cell": _NA_CELL, "recent_files": _NA_FILES}
    for name, blob in (("ascii.json", _legacy_stdlib_bytes(dict(legacy))),
                       ("utf8.json", json.dumps(legacy, ensure_ascii=False).encode("utf-8"))):
        path = tmp_path / name
        path.write_bytes(blob)
        for loader in ([stdlib_settings.load_settings, load_settings]
                       if _MSGSPEC_BACKEND else [stdlib_settings.load_settings]):
            loaded = loader(path)
            assert loaded.theme == "galaxy"              # v0 rename + v9 remap
            assert loaded.code_isolation == "strict"     # v1 -> v2 tri-state
            assert loaded.schema_version == SCHEMA_VERSION
            assert loaded.last_cell == _NA_CELL
            assert loaded.recent_files == _NA_FILES


@pytest.mark.parametrize(
    "blob",
    [
        b'{"theme": "n\xf8rd"}',      # cp1252-encoded ø: not valid UTF-8
        b'{"theme": "\x81\x8d\x90"}',  # undefined in cp1252 *and* invalid UTF-8
        b"\xff\xfe{\x00\x7d\x00",      # UTF-16LE with a BOM
    ],
    ids=["cp1252-bytes", "undecodable", "utf16"],
)
def test_undecodable_file_degrades_to_defaults(stdlib_settings, tmp_path, blob):
    """Garbage bytes still yield defaults rather than escaping load_settings.

    Insisting on UTF-8 turns a locale-decodable-but-wrong file into a decode
    error; the ``except Exception`` guard has to keep swallowing it. No released
    abax ever *wrote* these — the old fallback wrote pure ASCII — so this only
    covers hand-edited or corrupted files.
    """
    path = tmp_path / "settings.json"
    path.write_bytes(blob)
    assert stdlib_settings.load_settings(path) == stdlib_settings.Settings()
    if _MSGSPEC_BACKEND:
        assert load_settings(path) == Settings()


def test_config_dir_is_redirected_away_from_the_real_profile(abax_user_dirs):
    # The autouse conftest fixture is what keeps this whole module (and anything
    # it triggers) out of %APPDATA%/abax; persist through it the way abax does.
    path = abax_user_dirs["CONFIG_DIR"] / "settings.json"
    assert not path.exists()
    s = Settings()
    s.theme = "nord"
    save_settings(s, rt.CONFIG_DIR / "settings.json")
    assert path.exists()
    assert load_settings(rt.CONFIG_DIR / "settings.json").theme == "nord"
