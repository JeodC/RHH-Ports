#!/usr/bin/env python3
"""
Paths, user settings, button layouts and data containers
"""

import json
import os
import sys
from pathlib import Path
from typing import TypedDict

# ----------------------------------------------------------------------
# Runtime paths
#   BASE_PATH    sys._MEIPASS - where bundled resources (fonts/) extract.
#   DATA_DIR     XDG_DATA_HOME - writable state (manifest, logs, sources.json, settings.json,
#                .pending_update.zip) beside the binary.
#   INSTALL_DIR  where the binary lives; extract target for self-update.
# ----------------------------------------------------------------------
BASE_PATH = sys._MEIPASS
DATA_DIR = os.environ["XDG_DATA_HOME"]
INSTALL_DIR = os.path.dirname(os.path.abspath(sys.executable))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ----------------------------------------------------------------------
# User settings
# ----------------------------------------------------------------------
SETTINGS_PATH = Path(DATA_DIR) / "settings.json"


def _load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_PATH.read_text("utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        print(f"[SETTINGS] Unreadable ({e}); using the defaults")
        return {}
    return data if isinstance(data, dict) else {}


def get_setting(key: str, default):
    value = _load_settings().get(key, default)
    return value if isinstance(value, type(default)) else default


def put_setting(key: str, value) -> None:
    data = _load_settings()
    data[key] = value
    try:
        save_json(SETTINGS_PATH, data)
    except OSError as e:
        print(f"[SETTINGS] Not saved: {e}")


# ----------------------------------------------------------------------
# TypedDict definitions
# ----------------------------------------------------------------------
class Button(TypedDict):
    key: str  # SDL key name (e.g. "A")
    btn: str  # Label shown on-screen (e.g. "A")


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
        "a": {"key": "A", "btn": "A"},
        "b": {"key": "B", "btn": "B"},
        "x": {"key": "X", "btn": "X"},
        "y": {"key": "Y", "btn": "Y"},
        "l1": {"key": "L1", "btn": "L1"},
        "r1": {"key": "R1", "btn": "R1"},
    },
    "xbox": {
        "a": {"key": "B", "btn": "A"},
        "b": {"key": "A", "btn": "B"},
        "x": {"key": "Y", "btn": "X"},
        "y": {"key": "X", "btn": "Y"},
        "l1": {"key": "L1", "btn": "L1"},
        "r1": {"key": "R1", "btn": "R1"},
    },
}

# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
_XBOX_360_GUID = "030000005e0400008e02000014010000"


def _guid(mapping: str) -> str:
    guid = mapping.partition(",")[0]
    return guid[:4] + "0000" + guid[8:]  # SDL 2.26 puts a checksum of the name there


def _button(mapping: str, name: str) -> str:
    return next((p[2:] for p in mapping.split(",") if p.startswith(f"{name}:")), "")


def _database_row(path: str, guid: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return next((line for line in f if "platform:Linux" in line and _guid(line) == guid), "")
    except OSError:
        return ""


def _detect_layout_from_mapping(mapping: str) -> str:
    """nintendo when A and B match their labels, xbox when they're swapped"""
    # ROCKNIX names the layout it generated
    for line in os.getenv("SDL_GAMECONTROLLERCONFIG", "").splitlines():
        for layout in BUTTON_CONFIGS:
            if line.startswith(f"# {layout} layout"):
                return layout

    # B is where an Xbox pad has A, unless the database is swapped (spruce's Nintendo mode)
    if os.getenv("CFW_NAME", "").lower() in ("miyoo", "spruce", "trimui"):
        pad = _database_row(os.getenv("SDL_GAMECONTROLLERCONFIG_FILE", ""), _XBOX_360_GUID)
        return "nintendo" if _button(pad, "a") == "b1" else "xbox"

    # Raw button numbers differ per pad, so compare with PortMaster's copy of the
    # standard layout
    database = os.path.join(os.getenv("controlfolder", ""), ".Backup", "donottouch.txt")
    standard = _database_row(database, _guid(mapping))
    swapped = _button(mapping, "a") and _button(mapping, "a") == _button(standard, "b")
    return "xbox" if swapped else "nintendo"


def get_controller_layout(mapping: str) -> ButtonConfig:
    layout = _detect_layout_from_mapping(mapping)
    print(f"Controller layout: {layout} for {mapping}")
    return BUTTON_CONFIGS[layout]


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
    last_commit: str = ""
    image_url: str = ""
    appid: str = ""  # Steam
    arch: List[str] = field(default_factory=list)
    reqs: List[str] = field(default_factory=list)
    min_glibc: str = ""
    # Stores selling the underlying game (name/gameurl/developerurl from
    # port.json); display-only in the detail panel.
    store: List[dict] = field(default_factory=list)


@dataclass
class Repository:
    slug: str
    ports: List[Port] = field(default_factory=list)
    bottles: List[Port] = field(default_factory=list)
    loaded: bool = False

    @property
    def images_dir(self) -> str:
        return os.path.join(DATA_DIR, "resources", f"{self.slug.replace('/', '-')}-images")

    @property
    def items(self) -> List[Port]:
        return self.ports or self.bottles
