"""
Pharos manifest: installed ports and bottles, runtimes and gmtoolkit
"""

import json
import os
import threading
from contextlib import contextmanager, suppress
from pathlib import Path

from config import DATA_DIR, Port, save_json
from sources import is_portmaster

MANIFEST_PATH = Path(DATA_DIR) / "resources" / "manifest.json"

_lock = threading.RLock()

# A port and a bottle can share a name. Never changed in place.
installed: dict[str, list[dict]] = {}


def _index(data: dict) -> None:
    global installed
    index: dict[str, list[dict]] = {}
    for e in data["ports"] + data["bottles"]:
        index.setdefault(e["name"], []).append(e)
    installed = index


def load() -> dict:
    with _lock:
        data = {}
        try:
            data = json.loads(MANIFEST_PATH.read_text("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except FileNotFoundError:
            pass
        except ValueError as e:
            # Kept aside, since the next save would overwrite it
            print(f"[MANIFEST] Unreadable ({e}); kept as {MANIFEST_PATH.name}.bad")
            with suppress(OSError):
                os.replace(MANIFEST_PATH, MANIFEST_PATH.with_suffix(".json.bad"))
            data = {}
        for key in ("ports", "bottles"):
            entries = data.get(key)
            data[key] = [
                e
                for e in (entries if isinstance(entries, list) else [])
                if isinstance(e, dict) and isinstance(e.get("name"), str)
            ]
        _index(data)
        return data


@contextmanager
def edit():
    with _lock:
        data = load()
        yield data
        save_json(MANIFEST_PATH, data)
        _index(data)


def entry_for(port: Port) -> dict | None:
    entries = installed.get(port.name, [])
    for entry in entries:
        if (entry.get("repo") or "").lower() == port.repo.lower():
            return entry
    # Older entries have no repo, and PortMaster wasn't a source back then
    if not is_portmaster(port.repo):
        return next((e for e in entries if not e.get("repo")), None)
    return None


def update_available(port: Port) -> bool:
    entry = entry_for(port)
    return bool(entry and entry.get("md5") and port.md5 and entry["md5"] != port.md5)


def is_muted(port: Port) -> bool:
    entry = entry_for(port)
    return bool(entry and entry.get("muted"))


# Per-port mute is a "muted" boolean on each manifest entry; the daemon reads
# the same manifest the Pharos UI mutates here.
def toggle_muted(port: Port) -> None:
    try:
        with edit():
            if entry := entry_for(port):
                entry["muted"] = not entry.get("muted")
    except OSError as e:
        print(f"[MANIFEST] Mute not saved: {e}")


def record(entry: dict, key: str) -> None:
    # Preserve user-set fields (currently `muted`) so a re-download doesn't wipe them.
    with edit() as data:
        kept = []
        for e in data[key]:
            if e["name"].lower() != entry["name"].lower():
                kept.append(e)
            elif "muted" in e:
                entry["muted"] = e["muted"]
        data[key] = kept + [entry]
