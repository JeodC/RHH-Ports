"""
Languages, shared by Pharos and the daemon
"""

import json
from pathlib import Path
from string import Formatter

from strings import UI_BUTTONS, UI_REQS, UI_STRINGS

DEFAULT_LANGUAGE = "English"
TEMPLATE = "template"
ENGLISH = {
    "UI_STRINGS": dict(UI_STRINGS),
    "UI_BUTTONS": {name: button["label"] for name, button in UI_BUTTONS.items()},
    "UI_REQS": dict(UI_REQS),
}


def languages(folder: Path) -> dict[str, str]:
    """{file name: name in the language}"""
    paths = [path for path in sorted(folder.glob("[!.]*.json")) if path.stem != TEMPLATE]
    found = {path.stem: _own_name(_load(path, print)) or path.stem for path in paths}
    return {DEFAULT_LANGUAGE: DEFAULT_LANGUAGE, **found}


def _own_name(data: dict) -> str:
    strings = data.get("UI_STRINGS")
    name = strings.get("LANGUAGE_NAME") if isinstance(strings, dict) else None
    return name if isinstance(name, str) else ""


def apply_language(folder: Path, name: str, warn=print) -> None:
    path = folder / f"{name}.json"
    data = _load(path, warn)
    texts = {}
    for table, english in ENGLISH.items():
        translated = data.get(table)
        if not isinstance(translated, dict):
            translated = {}
        bad = [key for key in translated if key not in english or not _fits(translated[key], english[key])]
        if bad:
            warn(f"[LANGUAGE] {path}: ignored {', '.join(bad)}")
        texts[table] = {key: text if key in bad else translated.get(key, text) for key, text in english.items()}
    UI_STRINGS.update(texts["UI_STRINGS"])
    if data:
        UI_STRINGS["LANGUAGE_NAME"] = _own_name(data) or name
    UI_REQS.update(texts["UI_REQS"])
    for key, label in texts["UI_BUTTONS"].items():
        UI_BUTTONS[key]["label"] = label


def _load(path: Path, warn) -> dict:
    try:
        data = json.loads(path.read_text("utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, RecursionError) as e:
        warn(f"[LANGUAGE] {path}: {e}")
        return {}
    return data if isinstance(data, dict) else {}


def _fits(text, english: str) -> bool:
    # format() raises on a placeholder it isn't given
    try:
        return _placeholders(text) <= _placeholders(english)
    except (TypeError, ValueError):
        return False


def _placeholders(text: str) -> set[tuple]:
    return {(name, spec, conversion) for _, name, spec, conversion in Formatter().parse(text) if name is not None}
