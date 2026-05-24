import os
from pathlib import Path

FONT_DIR = Path(__file__).parent / "fonts"

_font_cache: dict[str, str] | None = None


def _display_name(filename: str) -> str:
    return Path(filename).stem.replace("-", " ").replace("_", " ")


def _load_fonts() -> dict[str, str]:
    global _font_cache
    if _font_cache is not None:
        return _font_cache

    _font_cache = {}
    for f in sorted(FONT_DIR.iterdir()):
        if f.suffix == ".otf":
            _font_cache[_display_name(f.name)] = str(f.resolve())

    return _font_cache


def get_available_fonts() -> dict[str, str]:
    return dict(_load_fonts())


def get_font_path(font_name: str) -> str | None:
    return _load_fonts().get(font_name)
