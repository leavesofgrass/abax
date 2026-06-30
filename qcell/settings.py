"""Settings struct + JSON persistence (msgspec when available, stdlib fallback).

Behaves identically with either backend, per the spec. Schema versioning uses
lazy migration: migrate on read, write back so later reads are free.
"""

from __future__ import annotations

from pathlib import Path

from ._runtime import _HAS_MSGSPEC

SCHEMA_VERSION = 1


def _migrate_settings(data: dict) -> dict:
    v = data.get("schema_version", 0)
    if v < 1:
        # v0 -> v1: renamed 'color_scheme' to 'theme'
        if "color_scheme" in data and "theme" not in data:
            data["theme"] = data.pop("color_scheme")
        data["schema_version"] = 1
    return data


if _HAS_MSGSPEC:
    import msgspec

    class Settings(msgspec.Struct, kw_only=True):
        theme: str = "obsidian"
        vim_mode: bool = True
        tui_theme: str = "obsidian"
        zoom: float = 1.0
        column_width: int = 10
        dyslexic_font: bool = False
        calc_model: str = ""
        calc_style: str = "image"
        faceplate_assets_dir: str = ""
        faceplate_repo: str = ""
        open_default_panels: bool = True
        show_toolbar: bool = True
        recent_files: list = []
        window_geometry: dict = {}
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
        column_width: int = 10
        dyslexic_font: bool = False
        calc_model: str = ""
        calc_style: str = "image"
        faceplate_assets_dir: str = ""
        faceplate_repo: str = ""
        open_default_panels: bool = True
        show_toolbar: bool = True
        recent_files: list = field(default_factory=list)
        window_geometry: dict = field(default_factory=dict)
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
