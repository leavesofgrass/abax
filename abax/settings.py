"""Settings struct + JSON persistence (msgspec when available, stdlib fallback).

Behaves identically with either backend, per the spec. Schema versioning uses
lazy migration: migrate on read, write back so later reads are free.
"""

from __future__ import annotations

from pathlib import Path

from ._runtime import _HAS_MSGSPEC

SCHEMA_VERSION = 8


def _migrate_settings(data: dict) -> dict:
    v = data.get("schema_version", 0)
    if v < 1:
        # v0 -> v1: renamed 'color_scheme' to 'theme'
        if "color_scheme" in data and "theme" not in data:
            data["theme"] = data.pop("color_scheme")
        data["schema_version"] = 1
    if v < 2:
        # v1 -> v2: the boolean 'sandbox_strict' became the tri-state
        # 'code_isolation' (off / isolated / strict).
        if "sandbox_strict" in data and "code_isolation" not in data:
            data["code_isolation"] = "strict" if data.get("sandbox_strict") else "isolated"
        data.pop("sandbox_strict", None)
        data["schema_version"] = 2
    if v < 3:
        # v2 -> v3: the autosave timer became configurable
        # ('autosave_enabled' + 'autosave_interval' seconds). Older files simply
        # take the defaults (on, 30s).
        data["schema_version"] = 3
    if v < 4:
        # v3 -> v4: dropped two never-read fields ('column_width' and the
        # obsolete 'faceplate_repo'). Strip them so they don't linger on re-save.
        data.pop("column_width", None)
        data.pop("faceplate_repo", None)
        data["schema_version"] = 4
    if v < 5:
        # v4 -> v5: new defaulted fields for iterative calc (calc_iterative /
        # calc_max_iterations / calc_max_change), accessibility (high_contrast /
        # speak_on_move / tui_screen_reader), and plugin consent (plugins_enabled).
        # All default off/safe, so older files simply take the defaults.
        data["schema_version"] = 5
    if v < 6:
        # v5 -> v6: new consent field 'live_data_enabled' gating the network
        # live-data formulas (REST/WEBSOCKET). Defaults off, so a workbook loaded
        # from disk never opens a connection until the user opts in.
        data["schema_version"] = 6
    if v < 7:
        # v6 -> v7: new consent field 'external_refs_enabled' gating the
        # closed-workbook external references (=[Book.abax]Sheet1!A1). Defaults
        # off, so an opened workbook never reads other files on its own.
        data["schema_version"] = 7
    if v < 8:
        # v7 -> v8: new 'windowed_store_capacity' (0 = off). Bounds resident
        # cells per sheet by spilling the rest to a temp file — for very large
        # data imports. Additive/default-off, so nothing changes for existing users.
        data["schema_version"] = 8
    return data


if _HAS_MSGSPEC:
    import msgspec

    class Settings(msgspec.Struct, kw_only=True):
        theme: str = "obsidian"
        vim_mode: bool = True
        tui_theme: str = "obsidian"
        zoom: float = 1.0
        dyslexic_font: bool = False
        calc_model: str = ""
        calc_style: str = "image"
        calc_degrees: bool = False
        last_sheet: int = 0
        last_cell: str = ""
        code_consent: bool = False
        # How code execution (console / scripts / macros) is isolated:
        # "off" = in-process, no worker, no limits (fastest, full access, no
        # crash isolation); "isolated" = out-of-process worker + resource limits
        # (default); "strict" = also OS-confine filesystem + network (Phase 3).
        code_isolation: str = "isolated"
        faceplate_assets_dir: str = ""
        show_toolbar: bool = True
        # Periodic autosave of settings.json: whether it runs, and how often.
        autosave_enabled: bool = True
        autosave_interval: int = 30  # seconds
        recent_files: list = []
        window_geometry: dict = {}
        fm_buttons: list = []
        auto_install: bool = True
        deps_prompted: bool = False
        # Iterative calculation: resolve circular references by capped fixed-point
        # iteration instead of surfacing #CIRC! (off by default, like Excel).
        calc_iterative: bool = False
        calc_max_iterations: int = 100
        calc_max_change: float = 0.001
        # Accessibility.
        high_contrast: bool = False
        speak_on_move: bool = False       # TTS the active cell on cursor move (GUI/TUI)
        tui_screen_reader: bool = False    # single-line, reader-friendly TUI rendering
        # Whether third-party UDF/format plugins (entry_points) may load (consent).
        plugins_enabled: bool = False
        # Whether network live-data formulas (REST/WEBSOCKET) may open connections
        # (consent). Off by default so a loaded workbook cannot phone home on open.
        live_data_enabled: bool = False
        # Whether closed-workbook external references (=[Book.abax]Sheet1!A1) may
        # read other workbook files (consent). Off by default so an opened file
        # cannot pull in other files on its own.
        external_refs_enabled: bool = False
        # Windowed cell store: keep at most this many cells resident per sheet and
        # spill the rest to a private temp file (0 = off, the default — every cell
        # stays in RAM). A memory/latency trade-off worth enabling ONLY for very
        # large *data* imports (lots of literal cells); formula-heavy sheets see
        # little benefit. See docs/configuration.md.
        windowed_store_capacity: int = 0
        schema_version: int = SCHEMA_VERSION

    _encoder = msgspec.json.Encoder()
    _decoder = msgspec.json.Decoder(Settings)

    def load_settings(path: Path) -> Settings:
        try:
            return _decoder.decode(Path(path).read_bytes())
        except Exception:
            return Settings()

    def save_settings(s: "Settings", path: Path) -> None:
        Path(path).write_bytes(_encoder.encode(s))

else:
    import json
    from dataclasses import asdict, dataclass, field

    @dataclass
    class Settings:  # type: ignore[no-redef]
        theme: str = "obsidian"
        vim_mode: bool = True
        tui_theme: str = "obsidian"
        zoom: float = 1.0
        dyslexic_font: bool = False
        calc_model: str = ""
        calc_style: str = "image"
        calc_degrees: bool = False
        last_sheet: int = 0
        last_cell: str = ""
        code_consent: bool = False
        # See the msgspec branch above for the meaning of code_isolation.
        code_isolation: str = "isolated"
        faceplate_assets_dir: str = ""
        show_toolbar: bool = True
        # Periodic autosave of settings.json: whether it runs, and how often.
        autosave_enabled: bool = True
        autosave_interval: int = 30  # seconds
        recent_files: list = field(default_factory=list)
        window_geometry: dict = field(default_factory=dict)
        fm_buttons: list = field(default_factory=list)
        auto_install: bool = True
        deps_prompted: bool = False
        # Iterative calculation: resolve circular references by capped fixed-point
        # iteration instead of surfacing #CIRC! (off by default, like Excel).
        calc_iterative: bool = False
        calc_max_iterations: int = 100
        calc_max_change: float = 0.001
        # Accessibility.
        high_contrast: bool = False
        speak_on_move: bool = False       # TTS the active cell on cursor move (GUI/TUI)
        tui_screen_reader: bool = False    # single-line, reader-friendly TUI rendering
        # Whether third-party UDF/format plugins (entry_points) may load (consent).
        plugins_enabled: bool = False
        # Whether network live-data formulas (REST/WEBSOCKET) may open connections
        # (consent). Off by default so a loaded workbook cannot phone home on open.
        live_data_enabled: bool = False
        # Whether closed-workbook external references (=[Book.abax]Sheet1!A1) may
        # read other workbook files (consent). Off by default so an opened file
        # cannot pull in other files on its own.
        external_refs_enabled: bool = False
        # Windowed cell store: keep at most this many cells resident per sheet and
        # spill the rest to a private temp file (0 = off, the default — every cell
        # stays in RAM). A memory/latency trade-off worth enabling ONLY for very
        # large *data* imports (lots of literal cells); formula-heavy sheets see
        # little benefit. See docs/configuration.md.
        windowed_store_capacity: int = 0
        schema_version: int = SCHEMA_VERSION

    def load_settings(path: Path) -> "Settings":
        try:
            data = json.loads(Path(path).read_text())
            data = _migrate_settings(data)
            return Settings(
                **{k: v for k, v in data.items() if k in Settings.__dataclass_fields__}
            )
        except Exception:
            return Settings()

    def save_settings(s: "Settings", path: Path) -> None:
        Path(path).write_text(json.dumps(asdict(s), indent=2))
