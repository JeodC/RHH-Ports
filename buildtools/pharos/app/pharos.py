#!/usr/bin/env python3
"""
Pharos
"""

import os
import json
import queue
import re
import threading
import time
from typing import List
from urllib.parse import quote
import sdl2
import sdl2.ext

# ----------------------------------------------------------------------
# Local imports
# ----------------------------------------------------------------------
import images
import manifest
from cfw import set_device_override
from config import DATA_DIR, INSTALL_DIR, get_controller_layout, get_setting, put_setting, Repository, Port
from device import Device
from input import Input
from theme import DEFAULT_THEME, apply_theme
from ui import UserInterface
from download import Downloader, controlfolder, fetch
from update import PHAROS_PORT_NAME, PHAROS_REPO, Update
from service import Service
from sources import catalog_entries, catalog_urls, is_portmaster, read_sources, release_url
from views import RepoView, UpdateView, View

STEAM_APPID = re.compile(r"store\.steampowered\.com/app/(\d+)")
DISCOUNTS_PER_REQUEST = 100
DEFAULT_DETAILS = ["size", "owner", "count"]


# ----------------------------------------------------------------------
# Background tasks
# ----------------------------------------------------------------------
def _spawn(name: str, func, *args) -> threading.Thread:
    def run():
        try:
            func(*args)
        except Exception as e:
            import traceback

            print(f"[{name}] CRASHED: {e}\n{traceback.format_exc()}")

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread


# ----------------------------------------------------------------------
# Catalog fields can hold anything
# ----------------------------------------------------------------------
def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _list(value) -> list:
    return value if isinstance(value, list) else []


# ----------------------------------------------------------------------
# Pharos core
# ----------------------------------------------------------------------
class Pharos:
    def __init__(self) -> None:
        self.input = Input()
        self.ui = UserInterface()
        self.repositories: List[Repository] = []
        self.sources_error = ""
        self.progress_q: queue.Queue = queue.Queue()
        self.downloader = Downloader(self.progress_q)
        self.image_fetcher = images.Fetcher()
        manifest.load()
        self.layout = get_controller_layout(self.input.controller_mapping())

        self.running = True
        self.input_thread: threading.Thread | None = None
        self.view_mode = "all"

        self.updater = Update(self.ui)
        self.self_update_available = False

        # Pharos Service (background daemon) controller.
        self.service = Service()

        # Live discount data, populated by a background thread once repos load.
        # Shape: { steam_appid: { shop_name: cut_pct, ... }, ... }, replaced whole.
        self.discounts_by_appid: dict = {}
        self._discount_appids: set[str] = set()
        self._discount_lock = threading.Lock()

        self.theme = get_setting("theme", DEFAULT_THEME)
        apply_theme(self.theme)
        self.device = Device()
        self._window_size = (0, 0)
        self.hide_incompatible = get_setting("hide_incompatible", False)
        self._visible: dict = {}
        self.details = get_setting("list_details", DEFAULT_DETAILS)
        self.override_device_info = get_setting("override_device_info", False)
        self._apply_device_override()
        self._views: List[View] = [RepoView(self)]

        # Refresh + restart the service if the bundled daemon differs from the
        # on-disk copy (avoids manual reinstall after a self-update). Backgrounded
        # because systemctl restart can take a couple of seconds.
        _spawn("ServiceRefresh", self._refresh_service_if_stale)
        _spawn("GmtoolkitRefresh", self.downloader.refresh_gmtoolkit_if_installed)

        self._load_sources()
        _spawn("SelfUpdateCheck", self._check_self_update)

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def set_theme(self, name: str) -> None:
        self.theme = name
        put_setting("theme", name)

    # ------------------------------------------------------------------
    # List details
    # ------------------------------------------------------------------
    def toggle_detail(self, key: str) -> None:
        self.details = [d for d in self.details if d != key] if key in self.details else self.details + [key]
        put_setting("list_details", self.details)

    # ------------------------------------------------------------------
    # PortMaster's device info
    # ------------------------------------------------------------------
    def toggle_override_device_info(self) -> str:
        """Returns an error message or an empty string"""
        self.override_device_info = not self.override_device_info
        error = self._apply_device_override()
        if error:
            self.override_device_info = not self.override_device_info
        put_setting("override_device_info", self.override_device_info)
        return error

    def _apply_device_override(self) -> str:
        # /roms and /storage/roms can be the same folder
        script = os.path.join(os.path.realpath(INSTALL_DIR), "device_override.txt")
        try:
            found = set_device_override(controlfolder, script if self.override_device_info else "")
        except OSError as e:
            print(f"[DEVICE] Can't change the device info cache: {e}")
            return f"Can't change the device info cache: {e.strerror}"
        if self.override_device_info and get_setting("controlfolder", "") != controlfolder:
            put_setting("controlfolder", controlfolder)  # for the daemon
        if self.override_device_info and not found:
            return "No device info cache found."
        return ""

    # ------------------------------------------------------------------
    # Compatibility filter
    # ------------------------------------------------------------------
    def toggle_hide_incompatible(self) -> None:
        self.hide_incompatible = not self.hide_incompatible
        put_setting("hide_incompatible", self.hide_incompatible)

    def visible(self, repo: Repository) -> List[Port]:
        if not self.hide_incompatible:
            return repo.items
        depends = (repo.items, self.device.caps, manifest.installed)
        cached = self._visible.get(repo.slug)
        if not cached or any(a is not b for a, b in zip(cached[0], depends)):
            # Installed ports stay, to update or mute them
            items = [p for p in repo.items if not self.device.unmet(p) or manifest.entry_for(p)]
            cached = self._visible[repo.slug] = (depends, items)
        return cached[1]

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def push(self, view: View) -> None:
        self._views.append(view)

    def pop(self) -> None:
        self._views.pop()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self) -> None:
        self.running = False
        self.downloader.stop()
        # It's still pumping SDL events
        if self.input_thread:
            self.input_thread.join(timeout=1)
        print("[CLEANUP] Done.")

    # ------------------------------------------------------------------
    # Load sources.json
    # ------------------------------------------------------------------
    def _load_sources(self) -> None:
        try:
            slugs = read_sources(os.path.join(DATA_DIR, "sources.json"), warn=lambda msg: print(f"[Sources] {msg}"))
        except (OSError, ValueError) as e:
            self.sources_error = f"Can't read sources.json: {e}"
            print(f"[Sources] {self.sources_error}")
            return
        self.repositories = [Repository(slug) for slug in slugs]
        images.prune(self.repositories)
        for repo in self.repositories:
            _spawn(f"PortsFetcher-{repo.slug}", self._fetch_repo, repo)

    # ------------------------------------------------------------------
    # Fetch ports.json / winecask.json
    # ------------------------------------------------------------------
    def _fetch_catalog(self, repo: Repository, filename: str, key: str) -> List[Port]:
        for url in catalog_urls(repo.slug, filename):
            try:
                entries = catalog_entries(fetch(url), key)
            except Exception as e:
                print(f"[Sources] {url}: {e}")
                continue
            return [self._parse_port(repo, p) for p in entries if not self._is_pharos(repo, p)]
        return []

    @staticmethod
    def _is_pharos(repo: Repository, entry: dict) -> bool:
        # A running binary can't be overwritten; self-update covers it
        return repo.slug.lower() == PHAROS_REPO.lower() and entry["name"] == PHAROS_PORT_NAME

    @staticmethod
    def _parse_port(repo: Repository, entry: dict) -> Port:
        src, attr = entry["source"], entry["attr"]
        name = os.path.splitext(entry["name"])[0]
        runtime = attr.get("runtime")
        if isinstance(runtime, str):
            runtime = [runtime]
        store = [s for s in _list(attr.get("store")) if isinstance(s, dict) and _text(s.get("name"))]
        # Find the port's Steam appid (ITAD lookup key) from any Steam URL.
        appid = next((m.group(1) for s in store if (m := STEAM_APPID.search(_text(s.get("gameurl"))))), "")
        image_url = _text(src.get("screenshot_url"))
        image = attr.get("image")
        if is_portmaster(repo.slug) and isinstance(image, dict) and image.get("screenshot"):
            image_url = f"https://raw.githubusercontent.com/{repo.slug}/HEAD/ports/{name}/{image['screenshot']}"
        return Port(
            name=name,
            title=_text(attr.get("title")) or name,
            desc=_text(attr.get("desc")) or "Missing description",
            download_url=_text(src.get("download_url")) or _text(src.get("url")),
            size=src["size"] if isinstance(src.get("size"), int) else None,
            md5=_text(src.get("md5")),
            date_updated=_text(src.get("date_updated")),
            first_seen=_text(src.get("first_seen")) or _text(src.get("date_added")),
            # PortMaster names some without the extension
            runtime=[
                r.removesuffix(".squashfs") + ".squashfs"
                for r in _list(runtime)
                if isinstance(r, str) and r and "/" not in r
            ],
            runtime_base_url=release_url(repo.slug, "runtimes-latest"),
            repo=repo.slug,
            store=store,
            last_commit=_text(src.get("last_commit")),
            image_url=quote(image_url, safe="%/:?=&"),
            appid=appid,
            arch=[a for a in _list(attr.get("arch")) if isinstance(a, str)],
            reqs=[r for r in _list(attr.get("reqs")) if isinstance(r, str)],
            min_glibc=_text(attr.get("min_glibc")),
        )

    def _fetch_repo(self, repo: Repository) -> None:
        try:
            repo.ports = self._fetch_catalog(repo, "ports.json", "ports")
            if not repo.ports:
                repo.bottles = self._fetch_catalog(repo, "winecask.json", "bottles")
        finally:
            repo.loaded = True
            if not repo.items:
                print(f"[Sources] No ports found in {repo.slug}")
        self._fetch_discounts(repo)

    # Pulls ITAD-tracked discounts from the RHH-Ports Cloudflare Worker for every
    # Steam appid in the repo into self.discounts_by_appid. Fails silently.
    def _fetch_discounts(self, repo: Repository) -> None:
        WORKER = "https://rhh-ports-discounts.jeodc.workers.dev/"
        COUNTRY = "US"
        with self._discount_lock:
            appids = sorted({p.appid for p in repo.ports if p.appid} - self._discount_appids)
            self._discount_appids.update(appids)
        # Worker returns { appid: { shop: {cut, url} } }. Flatten to { appid: { shop: cut } }.
        flattened: dict = {}
        for i in range(0, len(appids), DISCOUNTS_PER_REQUEST):
            try:
                url = f"{WORKER}?appids={','.join(appids[i : i + DISCOUNTS_PER_REQUEST])}&country={COUNTRY}"
                for appid, shops in json.loads(fetch(url, timeout=20)).items():
                    per_shop = {}
                    for shop_name, entry in shops.items():
                        cut = (entry.get("cut") if isinstance(entry, dict) else entry) or 0
                        if cut > 0:
                            per_shop[shop_name] = cut
                    if per_shop:
                        flattened[appid] = per_shop
            except Exception:
                pass
        with self._discount_lock:
            if flattened:
                self.discounts_by_appid = {**self.discounts_by_appid, **flattened}

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------
    def start(self) -> None:
        self.input_thread = _spawn("InputThread", self._monitor_input)

    def _monitor_input(self) -> None:
        while self.running:
            try:
                for ev in sdl2.ext.get_events():
                    self.input.check_event(ev)
                    if ev.type == sdl2.SDL_QUIT:
                        self.running = False
            except Exception as e:
                print(f"[INPUT THREAD ERROR] {e}")
                self.running = False
            time.sleep(0.005)

    def update(self) -> None:
        if self.self_update_available:
            self.self_update_available = False
            self.push(UpdateView(self))
        size = self.ui.window_size()
        if size != self._window_size and all(size):
            self._window_size = size
            self.device.set_display(*size, self.ui.refresh_rate())
        view = self._views[-1]
        view.draw()
        view.handle_input()

    # ------------------------------------------------------------------
    # Self-update
    # ------------------------------------------------------------------
    def _refresh_service_if_stale(self) -> None:
        if self.service.refresh_if_stale():
            print("[Service] daemon binary refreshed and service restarted")

    def _check_self_update(self) -> None:
        if self.updater.check():
            print(
                f"[Update] Pharos v{self.updater.latest_version} available (installed: v{self.updater.current_version})"
            )
            self.self_update_available = True
