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
from itertools import cycle
from typing import List
from urllib.parse import quote
import sdl2
import sdl2.ext

# ----------------------------------------------------------------------
# Local imports
# ----------------------------------------------------------------------
import images
import manifest
from autoinstall import WINDOWS_DIR
from config import DATA_DIR, get_controller_layout, Repository, Port
from input import Input
from ui import (
    UserInterface,
    color_menu_bg,
    color_row_text,
    color_text,
    c_row_muted,
    FOOTER_HEIGHT,
    BUTTON_AREA_HEIGHT,
    STORE_ROW_HEIGHT,
)
from download import DEVICE_ARCH, Downloader, fetch
from update import PHAROS_PORT_NAME, PHAROS_REPO, Update
from service import Service
from sources import catalog_entries, catalog_urls, is_portmaster, read_sources, release_url

STEAM_APPID = re.compile(r"store\.steampowered\.com/app/(\d+)")
MAX_ROWS = 12
DECODE_DELAY = 0.1  # seconds on a port before its screenshot is loaded
FETCH_DELAY = 0.3  # seconds before one is downloaded
DISCOUNTS_PER_REQUEST = 100

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
        self.repo_idx = 0
        self.port_idx = 0
        self.progress_q: queue.Queue = queue.Queue()
        self.downloader = Downloader(self.progress_q)
        self.image_fetcher = images.Fetcher()
        manifest.load()
        self.layout = get_controller_layout(self.input.controller_mapping())

        # Loading spinner (only used during repo fetch)
        self.spinner = cycle(["|", "/", "-", "\\"])
        self.spinner_speed = 0.12
        self.last_spinner = 0.0
        self.spinner_frame = ""

        # 2-second sticky message handling
        self.last_progress_msg = None  # (dl, tot, txt, stage)
        self.last_progress_time = 0.0
        self.PROGRESS_STICKY_SECONDS = 2.0
        self.progress_percent = 0.0

        self.current_view = "repos"
        self.running = True
        self.input_thread: threading.Thread | None = None
        self.view_mode = "all"
        self._view_cache: tuple = (None, [])
        self._selected_since: tuple = (None, 0.0)  # (repo, port), time

        self.updater = Update(self.ui)
        self.self_update_available = False
        self.self_update_prompted = False

        # Pharos Service (background daemon) controller.
        self.service = Service()

        # Live discount data, populated by a background thread once repos load.
        # Shape: { steam_appid: { shop_name: cut_pct, ... }, ... }, replaced whole.
        self.discounts_by_appid: dict = {}
        self.service_msg: str = ""  # last install/uninstall result, shown in log strip

        # Refresh + restart the service if the bundled daemon differs from the
        # on-disk copy (avoids manual reinstall after a self-update). Backgrounded
        # because systemctl restart can take a couple of seconds.
        _spawn("ServiceRefresh", self._refresh_service_if_stale)
        _spawn("GmtoolkitRefresh", self.downloader.refresh_gmtoolkit_if_installed)

        self._load_sources()
        _spawn("SelfUpdateCheck", self._check_self_update)

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
        _spawn("DiscountFetcher", self._fetch_discounts)

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
            return [self._parse_port(repo, p) for p in entries if self._runs_here(p) and not self._is_pharos(repo, p)]
        return []

    @staticmethod
    def _is_pharos(repo: Repository, entry: dict) -> bool:
        # A running binary can't be overwritten; self-update covers it
        return repo.slug.lower() == PHAROS_REPO.lower() and entry["name"] == PHAROS_PORT_NAME

    @staticmethod
    def _runs_here(entry: dict) -> bool:
        arch = entry["attr"].get("arch")
        if not isinstance(arch, list) or not arch or not DEVICE_ARCH or DEVICE_ARCH in arch:
            return True
        return "armhf" in arch and os.environ.get("DEVICE_HAS_ARMHF") == "Y"

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
            runtime=[r.removesuffix(".squashfs") + ".squashfs" for r in _list(runtime)
                     if isinstance(r, str) and r and "/" not in r],
            runtime_base_url=release_url(repo.slug, "runtimes-latest"),
            repo=repo.slug,
            store=store,
            last_commit=_text(src.get("last_commit")),
            image_url=quote(image_url, safe="%/:?=&"),
            appid=appid,
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

    # Pulls ITAD-tracked discounts from the RHH-Ports Cloudflare Worker for every
    # Steam appid in the catalog into self.discounts_by_appid. Fails silently.
    def _fetch_discounts(self) -> None:
        WORKER = "https://rhh-ports-discounts.jeodc.workers.dev/"
        COUNTRY = "US"
        repos = list(self.repositories)
        while not all(r.loaded for r in repos):
            time.sleep(0.5)
        appids = sorted({p.appid for r in repos for p in r.ports if p.appid})
        # Worker returns { appid: { shop: {cut, url} } }. Flatten to { appid: { shop: cut } }.
        flattened: dict = {}
        for i in range(0, len(appids), DISCOUNTS_PER_REQUEST):
            try:
                url = f"{WORKER}?appids={','.join(appids[i:i + DISCOUNTS_PER_REQUEST])}&country={COUNTRY}"
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
        self.discounts_by_appid = flattened

    # ------------------------------------------------------------------
    # Spinner
    # ------------------------------------------------------------------
    def _spin(self) -> None:
        now = time.time()
        if now - self.last_spinner >= self.spinner_speed:
            self.last_spinner = now
            self.spinner_frame = next(self.spinner)

    # ------------------------------------------------------------------
    # UI Helpers
    # ------------------------------------------------------------------
    def _pressed(self, button: str) -> bool:
        return self.input.key(self.layout[button]["key"])

    def _draw_button_bar(self, buttons: List[tuple]) -> None:
        """buttons: (layout button, label) pairs"""
        x = 20
        for button, label in buttons:
            b = self.layout[button]
            # Small screens have no room for Page Up and Page Down
            if x + self.ui.get_text_width(label) + 20 > self.ui.screen_width:
                break
            end = self.ui.button_circle((x, self.ui.screen_height - 50), b["btn"], label, color=b["color"])
            x = int(end) + 22

    def _draw_selected_image(self, repo: Repository, port: Port) -> None:
        key = (repo.slug, port.name)
        if key != self._selected_since[0]:
            self._selected_since = (key, time.time())
        rested = time.time() - self._selected_since[1]
        if port.image_path:
            if rested >= DECODE_DELAY or self.ui.has_texture(port.image_path):
                if not self.ui.draw_port_image(port.image_path, max_h=280 - self.ui.desc_shift):
                    self.image_fetcher.reject(repo, port)
        elif port.image_url and rested >= FETCH_DELAY:
            self.image_fetcher.want(repo, port)

    # ------------------------------------------------------------------
    # Render Views
    # ------------------------------------------------------------------
    def _render_repos(self) -> None:
        self.ui.draw_header("Select A Repository", color_text)
        pending = [r for r in self.repositories if not r.loaded]
        if pending:
            self._spin()
            self.ui.draw_log(text=f"{self.spinner_frame} Loading {len(pending)} repo(s)...")
            self._draw_button_bar([])
            return

        # Sources that failed to load or hold nothing aren't listed
        self.repositories = [r for r in self.repositories if r.items]
        self.repo_idx = max(0, min(self.repo_idx, len(self.repositories) - 1))

        total_items = sum(len(r.items) for r in self.repositories)
        self.ui.draw_log(text=self.sources_error or f"Loaded {total_items} items in {len(self.repositories)} repositories")

        start = max(0, self.repo_idx - MAX_ROWS + 1)
        visible = self.repositories[start: start + MAX_ROWS]
        for i, repo in enumerate(visible):
            y = 30 + i * 30
            sel = (start + i) == self.repo_idx
            txt = f"{repo.slug} ({len(repo.items)} items)"
            self.ui.row_list(txt, (20, y), self.ui.screen_width - 40, 28, sel, color=color_text if sel else color_row_text)

        btns = [
            ("a", "Open"),
            ("b", "Exit"),
            ("x", "Pharos Service"),
            ("l1", "Page Up"),
            ("r1", "Page Down"),
        ]
        self._draw_button_bar(btns)

    VIEW_MODES = ("all", "updated", "new", "discount", "installed")
    _VIEW_MODE_BTN_LABEL = {
        "all": "All",
        "updated": "Updated",
        "new": "New",
        "discount": "On Sale",
        "installed": "Installed",
    }
    _VIEW_MODE_HEADER_SUFFIX = {
        "all": "",
        "updated": " - by last update",
        "new": " - newest first",
        "discount": " - biggest discount first",
        "installed": "",
    }

    def _max_discount_for_port(self, port) -> int:
        """Deepest active discount % across all of a port's stores, or 0."""
        shops = self.discounts_by_appid.get(port.appid)
        if not shops:
            return 0
        return max((shops.get(s.get("name", ""), 0) for s in port.store), default=0)

    def _view_items(self, repo: Repository) -> List[Port]:
        """Apply the active view_mode's filter+sort to the repo's items."""
        key = (repo.slug, self.view_mode, manifest.installed, self.discounts_by_appid)
        if self._view_cache[0] == key:
            return self._view_cache[1]

        items = list(repo.items)
        if self.view_mode == "installed":
            items = [i for i in items if manifest.entry_for(i)]
        elif self.view_mode == "updated":
            items.sort(key=lambda p: p.date_updated or "", reverse=True)
        elif self.view_mode == "new":
            items.sort(key=lambda p: p.first_seen or "", reverse=True)
        elif self.view_mode == "discount":
            # Deepest discount first; alphabetical tiebreak keeps no-sale ports at bottom.
            items.sort(key=lambda p: (-self._max_discount_for_port(p), p.title.lower()))
        self._view_cache = (key, items)
        # The same port from another repo leaves this one's installed view
        self.port_idx = max(0, min(self.port_idx, len(items) - 1))
        return items

    def _can_download(self, repo: Repository) -> bool:
        return not repo.bottles or WINDOWS_DIR.exists()

    def _render_ports(self) -> None:
        repo = self.repositories[self.repo_idx]
        items = self._view_items(repo)
        label = "installed" if self.view_mode == "installed" else "items"
        suffix = self._VIEW_MODE_HEADER_SUFFIX[self.view_mode]
        header_text = f"{len(items)} {label} in {repo.slug}{suffix}"
        self.ui.draw_header(header_text, color_text)

        can_download = self._can_download(repo)

        start = max(0, self.port_idx - MAX_ROWS + 1)
        visible = items[start: start + MAX_ROWS]
        selected_item = items[self.port_idx] if items else None
        for i, item in enumerate(visible):
            y = 30 + i * 30
            sel = (start + i) == self.port_idx
            size = f" [{item.size / (1024*1024):.2f} MB]" if item.size else ""
            is_muted = manifest.is_muted(item)
            highlight = manifest.update_available(item) and not is_muted
            self.ui.row_list(
                f"{item.title}{size}",
                (20, y),
                self.ui.screen_width // 3,
                28,
                sel,
                # Muted ports get a darker background and lose the "update
                # available" highlight - consistent with the daemon, which
                # filters muted ports out before notifying.
                fill=c_row_muted if (is_muted and not sel) else None,
                color=color_text if sel else color_menu_bg if highlight else color_row_text,
                highlight=highlight,
            )

        if selected_item:
            self._draw_selected_image(repo, selected_item)
        # Reserve space below the description for the store-icon row (only when
        # the port has stores, else the description gets the full vertical area).
        has_stores = bool(selected_item and selected_item.store)
        store_reserve = STORE_ROW_HEIGHT if has_stores else 0
        if selected_item and selected_item.desc:
            self.ui.draw_wrapped_text_centered(
                selected_item.desc,
                center_x=(self.ui.screen_width * 3 // 4 - 20),
                start_y=400 - FOOTER_HEIGHT - BUTTON_AREA_HEIGHT - 5 - self.ui.desc_shift,
                max_width=self.ui.screen_width // 2,
                color=color_text,
                reserve_bottom=store_reserve,
            )
        if has_stores:
            shops = self.discounts_by_appid.get(selected_item.appid, {})
            self.ui.draw_port_stores(
                selected_item.store,
                discount_lookup=lambda name: shops.get(name, 0),
                center_x=(self.ui.screen_width * 3 // 4 - 20),
                max_width=self.ui.screen_width // 2,
                bottom_y=self.ui.screen_height - self.ui.footer_height - BUTTON_AREA_HEIGHT,
            )

        # ------------------------------------------------------------------
        # Progress Queue Handling
        # ------------------------------------------------------------------
        latest = None
        while True:
            try:
                item = self.progress_q.get_nowait()
                if isinstance(item, tuple) and len(item) == 4:
                    latest = item
            except queue.Empty:
                break

        if latest is not None:
            self.last_progress_msg = latest
            self.last_progress_time = time.time()
            dl, tot, txt, stage = latest
            if stage == "download":
                self.progress_percent = (dl / tot) * 100 if tot else -1
        elif self.last_progress_msg is not None:
            elapsed = time.time() - self.last_progress_time
            if elapsed >= self.PROGRESS_STICKY_SECONDS:
                self.last_progress_msg = None
                self.progress_percent = 0
        else:
            self.progress_percent = 0

        # ------------------------------------------------------------------
        # Bottom Log
        # ------------------------------------------------------------------
        if self.last_progress_msg:
            _, _, txt, stage = self.last_progress_msg
            bottom_log = txt
            if stage == "download":
                self.ui.draw_loader(self.progress_percent)
        elif not can_download:
            bottom_log = f"ERROR: {WINDOWS_DIR} not found!"
        elif selected_item and manifest.update_available(selected_item):
            bottom_log = f"{selected_item.title} - Update available!"
        elif selected_item:
            bottom_log = selected_item.last_commit
        elif self.view_mode == "installed":
            bottom_log = "No installed ports in this repository."
        else:
            bottom_log = ""

        self.ui.draw_log(text=bottom_log)

        btns = []
        if can_download:
            btns.append(("a", "Download"))

        btns.append(("b", "Back"))

        # X toggles per-port mute - only meaningful for ports in the local
        # manifest; nothing to mute otherwise.
        if selected_item and manifest.entry_for(selected_item):
            x_label = "Unmute" if manifest.is_muted(selected_item) else "Mute"
            btns.append(("x", x_label))

        btns.append(("y", self._VIEW_MODE_BTN_LABEL[self.view_mode]))
        btns.append(("l1", "Page Up"))
        btns.append(("r1", "Page Down"))

        self._draw_button_bar(btns)

    # ------------------------------------------------------------------
    # Input Handling
    # ------------------------------------------------------------------
    def _update_repos(self) -> None:
        if not self.repositories:
            if self._pressed("b"):
                self.running = False
            elif self._pressed("x"):
                self.current_view = "service"
                self.service_msg = ""
            return
        repo = self.repositories[self.repo_idx]
        if self._pressed("a") and repo.items:
            self.current_view = "ports"
            self.port_idx = 0
            images.assign(repo)
        elif self._pressed("b"):
            print("[USER] Exit requested via B button")
            self.running = False
        elif self._pressed("x"):
            self.current_view = "service"
            self.service_msg = ""
        else:
            self.repo_idx = self.input.handle_navigation(self.repo_idx, 10, len(self.repositories))

    def _update_ports(self) -> None:
        repo = self.repositories[self.repo_idx]
        items = self._view_items(repo)

        # B (back) and Y (cycle view mode) must work even when the filtered
        # list is empty, else the user gets stuck in an empty view.
        if self._pressed("b"):
            self.current_view = "repos"
            self.downloader.clear_queue()
            return

        if self._pressed("y"):
            i = self.VIEW_MODES.index(self.view_mode)
            self.view_mode = self.VIEW_MODES[(i + 1) % len(self.VIEW_MODES)]
            self.port_idx = 0
            return

        if not items:
            return

        if self._pressed("a") and self._can_download(repo):
            self.downloader.enqueue(items[self.port_idx], "bottle" if repo.bottles else "port")

        elif self._pressed("x"):
            # Toggle mute; only acts on ports with a manifest entry.
            if manifest.entry_for(items[self.port_idx]):
                manifest.toggle_muted(items[self.port_idx])

        else:
            self.port_idx = self.input.handle_navigation(self.port_idx, 10, len(items))

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
        if self.self_update_available and not self.self_update_prompted:
            self._render_self_update_prompt()
            self._handle_self_update_input()
            return
        if self.current_view == "service":
            self._render_service()
            self._update_service()
        elif self.current_view == "repos":
            self._render_repos()
            self._update_repos()
        else:
            self._render_ports()
            self._update_ports()

    # ------------------------------------------------------------------
    # Pharos Service view
    # ------------------------------------------------------------------
    def _render_service(self) -> None:
        sw = self.ui.screen_width
        self.ui.draw_header("Pharos Service", color_text)

        installed = self.service.installed
        supported = self.service.supported

        description = (
            "Pharos Service is a small background daemon that watches the repos in sources.json "
            "for port updates without you having to open Pharos.",
            "It runs at boot, fires a notification if any installed ports are out of date, "
            "and re-checks whenever you exit a game. Notifications appear as an EmulationStation toast.",
        )
        y = 50
        for paragraph in description:
            for line in self.ui.wrap_text(paragraph, min(sw - 80, 460)):
                self.ui.draw_text((40, y), line, color_text)
                y += self.ui.font_size + 10
            y += self.ui.font_size

        # Status line, centered.
        status_label = self.service.status_text()
        sw_text = self.ui.get_text_width(status_label)
        self.ui.draw_text(
            (max(20, sw // 2 - sw_text // 2), max(240, y + 8)),
            status_label,
            color_text,
        )

        # Footer log: most-recent action result, if any.
        if self.service_msg:
            self.ui.draw_log(text=self.service_msg)
        elif not supported:
            self.ui.draw_log(text="This CFW isn't supported yet.")
        else:
            self.ui.draw_log(
                text=("Press A to install" if not installed else "Press A to uninstall")
            )

        btns = [("b", "Back")]
        if supported:
            label = "Uninstall" if installed else "Install"
            btns.insert(0, ("a", label))
        self._draw_button_bar(btns)

    def _update_service(self) -> None:
        if self._pressed("b"):
            self.current_view = "repos"
            self.service_msg = ""
            return

        if not self.service.supported:
            return

        if self._pressed("a"):
            # install/uninstall blocks for a couple seconds (systemctl /
            # batocera-settings / filesystem); show a transient "Working..." hint.
            self.ui.draw_log(text="Working...")
            self.ui.render_to_screen()
            if self.service.installed:
                ok, msg = self.service.uninstall()
            else:
                ok, msg = self.service.install()
            self.service_msg = ("[OK] " if ok else "[ERR] ") + msg
            self.input.begin_frame()  # drops what was pressed meanwhile

    # ------------------------------------------------------------------
    # Self-update
    # ------------------------------------------------------------------
    def _refresh_service_if_stale(self) -> None:
        if self.service.refresh_if_stale():
            print("[Service] daemon binary refreshed and service restarted")

    def _check_self_update(self) -> None:
        if self.updater.check():
            print(
                f"[Update] Pharos v{self.updater.latest_version} available "
                f"(installed: v{self.updater.current_version})"
            )
            self.self_update_available = True

    def _render_self_update_prompt(self) -> None:
        sw, sh = self.ui.screen_width, self.ui.screen_height
        self.ui.draw_header("Pharos Update Available", color_text)

        line1 = f"v{self.updater.current_version}  ->  v{self.updater.latest_version}"
        line2 = "Download and install the new version?"
        for i, line in enumerate((line1, line2)):
            w = self.ui.get_text_width(line)
            x = max(20, sw // 2 - w // 2)
            y = sh // 2 - 30 + i * 24
            self.ui.draw_text((x, y), line, color_text)

        self.ui.draw_log(
            text=f"Pharos update v{self.updater.latest_version} available."
        )

        btns = [
            ("a", "Yes"),
            ("b", "No"),
        ]
        self._draw_button_bar(btns)

    def _handle_self_update_input(self) -> None:
        if self._pressed("a"):
            self.self_update_prompted = True
            if self.updater.download():
                self.ui.draw_log(
                    text=f"Pharos v{self.updater.latest_version} downloaded - applying and re-launching..."
                )
                self.ui.render_to_screen()
                sdl2.SDL_Delay(2000)
                self.running = False
            else:
                self.ui.draw_log(
                    text="Update not ready (still publishing?) - try again in a few minutes."
                )
                self.ui.render_to_screen()
                sdl2.SDL_Delay(1500)
                self.self_update_available = False
                self.input.begin_frame()  # drops what was pressed meanwhile
        elif self._pressed("b"):
            self.self_update_prompted = True
            self.self_update_available = False