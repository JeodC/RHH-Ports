#!/usr/bin/env python3
"""
Controller layout -> button mapping
"""
import os
import sys
from typing import TypedDict

# ----------------------------------------------------------------------
# Runtime paths
#   BASE_PATH    sys._MEIPASS - where bundled resources (fonts/) extract.
#   DATA_DIR     XDG_DATA_HOME - writable state (manifest, logs, .sources,
#                .pending_update.zip) beside the binary.
#   INSTALL_DIR  where the binary lives; extract target for self-update.
# ----------------------------------------------------------------------
BASE_PATH = sys._MEIPASS
DATA_DIR = os.environ["XDG_DATA_HOME"]
INSTALL_DIR = os.path.dirname(os.path.abspath(sys.executable))

# ----------------------------------------------------------------------
# Button colors
# ----------------------------------------------------------------------
color_btn_a = "#2f843e"
color_btn_b = "#ad3c3c"
color_btn_x = "#3b80aa"
color_btn_y = "#d3b948"
color_btn_shoulder = "#383838"

# ----------------------------------------------------------------------
# TypedDict definitions
# ----------------------------------------------------------------------
class Button(TypedDict):
    key: str          # SDL key name (e.g. "A")
    btn: str          # Label shown on-screen (e.g. "A")
    color: str        # Hex color

class ButtonConfig(TypedDict):
    a: Button
    b: Button
    x: Button
    y: Button
    l1: Button
    r1: Button

# ----------------------------------------------------------------------
# Hard-coded layouts
# ----------------------------------------------------------------------
BUTTON_CONFIGS: dict[str, ButtonConfig] = {
    "nintendo": {
        "a": {"key": "A", "btn": "A", "color": color_btn_a},
        "b": {"key": "B", "btn": "B", "color": color_btn_b},
        "x": {"key": "X", "btn": "X", "color": color_btn_x},
        "y": {"key": "Y", "btn": "Y", "color": color_btn_y},
        "l1": {"key": "L1", "btn": "L1", "color": color_btn_shoulder},
        "r1": {"key": "R1", "btn": "R1", "color": color_btn_shoulder},
    },
    "xbox": {
        "a": {"key": "B", "btn": "A", "color": color_btn_a},
        "b": {"key": "A", "btn": "B", "color": color_btn_b},
        "x": {"key": "Y", "btn": "X", "color": color_btn_x},
        "y": {"key": "X", "btn": "Y", "color": color_btn_y},
        "l1": {"key": "L1", "btn": "L1", "color": color_btn_shoulder},
        "r1": {"key": "R1", "btn": "R1", "color": color_btn_shoulder},
    },
}

# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def _detect_layout_from_mapping() -> str:
    """Pick layout from SDL_GAMECONTROLLERCONFIG. The `a:bN`/`b:bN` segments
    reveal which SDL button raw joystick button 0 is bound to."""
    mapping = os.getenv("SDL_GAMECONTROLLERCONFIG", "")
    first_line = mapping.splitlines()[0] if mapping else ""
    for part in first_line.split(","):
        k, _, v = part.partition(":")
        if v.strip() == "b0" and k.strip() in ("a", "b"):
            return "nintendo" if k.strip() == "b" else "xbox"
    return "nintendo"


def get_controller_layout() -> ButtonConfig:
    return BUTTON_CONFIGS[_detect_layout_from_mapping()]

# ----------------------------------------------------------------------
# Data containers
# ----------------------------------------------------------------------
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Port:
    name: str
    title: str
    desc: str = "Missing description"
    download_url: str = ""
    image_path: Optional[str] = None
    date_updated: Optional[str] = None
    first_seen: Optional[str] = None
    size: Optional[int] = None
    md5: Optional[str] = None
    runtime: List[str] = field(default_factory=list)
    runtime_base_url: str = ""
    repo: str = ""
    muted: bool = False
    # Stores selling the underlying game (name/gameurl/developerurl from
    # port.json); display-only in the detail panel.
    store: List[dict] = field(default_factory=list)

@dataclass
class Repository:
    name: str
    url: str
    images_dir: Optional[str] = None
    images_zip_url: Optional[str] = None
    ports: List[Port] = field(default_factory=list)
    bottles: List[Port] = field(default_factory=list)