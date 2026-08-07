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
