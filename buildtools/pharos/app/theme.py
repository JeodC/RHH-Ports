"""
Color themes
"""

import json
import re
from pathlib import Path
from types import SimpleNamespace

from config import BASE_PATH, DATA_DIR

BUILTIN_DIR = Path(BASE_PATH) / "resources" / "themes"
USER_DIR = Path(DATA_DIR) / "themes"
DEFAULT_THEME = "Pharos"
COLORS = {
    "background": "#000000",
    "text": "#ffffff",
    "label": "#c8c8c8",
    "header_bg": "#141414",
    "header_text": "#ffffff",
    "header_info": "#c8c8c8",
    "footer_bg": "#333333",
    "footer_text": "#ffffff",
    "row_bg": "#383838",
    "row_text": "#c8c8c8",
    "row_muted": "#2a2a2a",
    "row_selected": "#2f843e",
    "row_selected_text": "#ffffff",
    "row_highlight": "#d3b948",
    "row_highlight_text": "#141414",
    "popup_bg": "#141414",
    "popup_border": "#c8c8c8",
    "popup_text": "#ffffff",
    "progress_bar": "#00b400",
    "discount": "#beee11",
    "btn_a": "#2f843e",
    "btn_b": "#ad3c3c",
    "btn_x": "#3b80aa",
    "btn_y": "#d3b948",
    "btn_l1": "#383838",
    "btn_r1": "#383838",
    "btn_text": "#ffffff",
}

theme = SimpleNamespace(**COLORS)


def theme_names() -> list[str]:
    found = {path.stem for folder in (BUILTIN_DIR, USER_DIR) for path in folder.glob("[!.]*.json")}
    return [DEFAULT_THEME] + sorted(found - {DEFAULT_THEME}, key=str.lower)


def apply_theme(name: str) -> None:
    vars(theme).update({**COLORS, **_load(name)})


def _load(name: str) -> dict[str, str]:
    for path in (USER_DIR / f"{name}.json", BUILTIN_DIR / f"{name}.json"):
        try:
            data = json.loads(path.read_text("utf-8-sig"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError, RecursionError) as e:
            print(f"[THEME] {path}: {e}")
            return {}
        if not isinstance(data, dict):
            data = {}
        colors = {k: v for k, v in data.items() if k in COLORS and re.fullmatch(r"#[0-9a-fA-F]{6}", str(v))}
        if len(colors) < len(data):
            print(f"[THEME] {path}: ignored {', '.join(data.keys() - colors.keys())}")
        return colors
    return {}
