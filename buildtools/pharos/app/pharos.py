#!/usr/bin/env python3
"""
Pharos
"""
import os
import json
import queue
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from itertools import cycle
from typing import List
import sdl2
import sdl2.ext

# ----------------------------------------------------------------------
# Manifest MD5 cache. Manifest + image cache live in DATA_DIR (the install
# dir, set by the launchscript via XDG_DATA_HOME).
# ----------------------------------------------------------------------
from config import DATA_DIR
MANIFEST_PATH = os.path.join(DATA_DIR, "resources", "manifest.json")
local_md5s: dict[str, str] = {}
muted_ports: set[str] = set()
if os.path.exists(MANIFEST_PATH):
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
        for entry in manifest.get("ports", []) + manifest.get("bottles", []):
            name = entry.get("name")
            if not name:
                continue
            local_md5s[name] = entry.get("md5")
            if entry.get("muted"):
                muted_ports.add(name)

# ----------------------------------------------------------------------
# Local imports
# ----------------------------------------------------------------------
from autoinstall import WINDOWS_DIR
from config import get_controller_layout, Repository, Port
from input import Input
from ui import (
    UserInterface,
    color_menu_bg,
    color_text,
    c_row_muted,
    FOOTER_HEIGHT,
    BUTTON_AREA_HEIGHT,
    STORE_ROW_HEIGHT,
)
from download import Downloader
from update import Update
from service import Service, toggle_muted_port

# ----------------------------------------------------------------------
# Safe background task runner
# ----------------------------------------------------------------------
def _safe_bg(func, *args):
    def wrapper():
        thread_name = threading.current_thread().name
        try:
            func(*args)
        except Exception as e:
            import traceback
            print(f"[{thread_name}] CRASHED: {e}\n{traceback.format_exc()}")
    return wrapper

# ----------------------------------------------------------------------
# Pharos core
# ----------------------------------------------------------------------
class Pharos:
    def __init__(self) -> None:
        self.input = Input()
        self.ui = UserInterface()
        self.sources_path = os.path.join(DATA_DIR, ".sources")
        self.repositories: List[Repository] = []
        self.repo_idx = 0
        self.port_idx = 0
        self.dl_queue: queue.Queue = queue.Queue()
        self.progress_q: queue.Queue = queue.Queue()
        self.layout = get_controller_layout()

        # Loading spinner (only used during repo fetch)
        self.spinner = cycle(["|", "/", "-", "\\"])
        self.spinner_speed = 0.12
        self.last_spinner = 0.0
        self.spinner_frame = ""

        # 2-second sticky message handling
        self.last_progress_msg = None  # (dl, tot, txt, stage)
        self.last_progress_time = 0.0
        self.PROGRESS_STICKY_SECONDS = 2.0

        self.current_view = "repos"
        self.running = True
        self.download_active = False
        self.view_mode = "all"

        self.updater = Update(self.ui)
        self.self_update_available = False
        self.self_update_prompted = False

        # Pharos Service (background daemon) controller.
        self.service = Service()

        # Live discount data, populated by a background thread once repos load.
        # Shape: { steam_appid: { shop_name: cut_pct, ... }, ... }
        self.discounts_by_appid: dict = {}
        self._discounts_lock = threading.Lock()
        self.service_msg: str = ""  # last install/uninstall result, shown in log strip

        # Refresh + restart the service if the bundled daemon differs from the
        # on-disk copy (avoids manual reinstall after a self-update). Backgrounded
        # because systemctl restart can take a couple of seconds.
        threading.Thread(
            target=self._refresh_service_if_stale,
            name="ServiceRefresh",
            daemon=True,
        ).start()

        self._load_sources()
        threading.Thread(
            target=self._check_self_update,
            name="SelfUpdateCheck",
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self) -> None:
        self.running = False
        try:
            self.dl_queue.put(None)
        except Exception:
            pass

        deadline = time.time() + 5.0
        while time.time() < deadline:
            alive = any(
                t.is_alive() and t.name in ("DownloaderThread", "InputThread")
                for t in threading.enumerate()
                if t is not threading.main_thread()
            )
            if not alive:
                break
            time.sleep(0.05)

        for q in (self.dl_queue, self.progress_q):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

        for repo in self.repositories:
            for port in getattr(repo, "ports", []) or []:
                port.image_path = None
            for bottle in getattr(repo, "bottles", []) or []:
                bottle.image_path = None
        self.repositories.clear()

        try:
            if sdl2.SDL_WasInit(sdl2.SDL_INIT_VIDEO):
                sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_VIDEO)
            if sdl2.SDL_WasInit(sdl2.SDL_INIT_GAMECONTROLLER):
                sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_GAMECONTROLLER)
        except Exception as e:
            print(f"[CLEANUP] SDL error: {e}")
        print("[CLEANUP] Done.")

    # ------------------------------------------------------------------
    # Load .sources
    # ------------------------------------------------------------------
    def _load_sources(self) -> None:
        if len(sys.argv) > 1:
            self.sources_path = sys.argv[1]
            print(f"Using sources path: {self.sources_path}")
        if not os.path.exists(self.sources_path):
            self.ui.draw_log(text=f"Missing .sources file at {self.sources_path}", background=True)
            return
        with open(self.sources_path, "r", encoding="utf-8") as f:
            for line in f:
                url = line.strip()
                if not url or url.startswith("#"):
                    continue
                parsed = urllib.parse.urlparse(url)
                path = parsed.path.lstrip("/")
                if path.endswith(".git"):
                    path = path[:-4]
                if "/" not in path:
                    continue
                owner, name = path.split("/", 1)
                repo = Repository(
                    name=name,
                    url=f"https://github.com/{path}",
                    images_dir=os.path.join(DATA_DIR, "resources", f"{owner}-{name}-images"),
                    images_zip_url=f"https://github.com/{path}/releases/download/ports-latest/images.zip",
                )
                self.repositories.append(repo)
                threading.Thread(
                    target=_safe_bg(self._fetch_images, repo),
                    name=f"ImageFetcher-{repo.name}",
                    daemon=True
                ).start()
        self._fetch_all_ports_or_bottles()

    # ------------------------------------------------------------------
    # Fetch images
    # ------------------------------------------------------------------
    def _fetch_images(self, repo: Repository) -> None:
        worker = Downloader(queue.Queue(), queue.Queue())
        try:
            worker.fetch_repo_images(repo)
        except Exception as e:
            print(f"[ImageFetcher-{repo.name}] Failed: {e}")

    # ------------------------------------------------------------------
    # Fetch ports.json / winecask.json
    # ------------------------------------------------------------------
    def _fetch_ports_json(self, repo: Repository) -> None:
        gh = repo.url.replace("https://github.com/", "").rstrip("/")
        owner, repo_name = gh.split("/", 1)
        branch = "main"
        try:
            api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
            data = json.loads(self._gh_request(api_url))
            branch = data.get("default_branch", "main")
        except Exception:
            pass
        raw_base = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}"
        runtime_base = f"https://github.com/{owner}/{repo_name}/releases/download/runtimes-latest"
        for candidate in [f"{raw_base}/ports.json", f"{raw_base}/docs/ports.json"]:
            try:
                raw = self._gh_request(candidate)
                data = json.loads(raw)
                ports_raw = data.get("ports", data) if isinstance(data, dict) else data
                repo.ports = []
                for p in ports_raw:
                    src = p.get("source", {})
                    name = os.path.splitext(p.get("name", "Unnamed"))[0]
                    port = Port(
                        name=name,
                        title=p.get("attr", {}).get("title", p.get("name", "")),
                        desc=p.get("attr", {}).get("desc", "Missing description"),
                        download_url=src.get("download_url", ""),
                        size=src.get("size"),
                        date_updated=src.get("date_updated"),
                        first_seen=src.get("first_seen"),
                        runtime=[r for r in p.get("attr", {}).get("runtime", []) if r.endswith(".squashfs")],
                        runtime_base_url=runtime_base,
                        repo=f"{owner}/{repo_name}",
                        store=p.get("attr", {}).get("store", []) or [],
                    )
                    port.last_commit = src.get("last_commit", "")
                    port.md5 = src.get("md5")
                    local_md5 = local_md5s.get(port.name)
                    port.update_available = bool(local_md5 and port.md5 and local_md5 != port.md5)
                    repo.ports.append(port)
                return
            except Exception:
                continue

    def _fetch_winecask_json(self, repo: Repository) -> None:
        gh = repo.url.replace("https://github.com/", "").rstrip("/")
        owner, repo_name = gh.split("/", 1)
        branch = "main"
        try:
            api_url = f"https://api.github.com/repos/{owner}/{repo_name}"
            data = json.loads(self._gh_request(api_url))
            branch = data.get("default_branch", "main")
        except Exception:
            pass
        raw_base = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}"
        for candidate in [f"{raw_base}/winecask.json", f"{raw_base}/docs/winecask.json"]:
            try:
                raw = self._gh_request(candidate)
                data = json.loads(raw)
                bottles_raw = data.get("bottles", data) if isinstance(data, dict) else data
                repo.bottles = []
                for p in bottles_raw:
                    src = p.get("source", {})
                    name = os.path.splitext(p.get("name", "Unnamed"))[0]
                    bottle = Port(
                        name=name,
                        title=p.get("attr", {}).get("title", p.get("name", "")),
                        desc=p.get("attr", {}).get("desc", "Missing description"),
                        download_url=src.get("download_url", ""),
                        size=src.get("size"),
                        date_updated=src.get("date_updated"),
                        first_seen=src.get("first_seen"),
                        repo=f"{owner}/{repo_name}",
                    )
                    bottle.last_commit = src.get("last_commit", "")
                    bottle.md5 = src.get("md5")
                    local_md5 = local_md5s.get(bottle.name)
                    bottle.update_available = bool(local_md5 and bottle.md5 and local_md5 != bottle.md5)
                    repo.bottles.append(bottle)
                return
            except Exception:
                continue

    def _fetch_all_ports_or_bottles(self) -> None:
        for r in self.repositories:
            threading.Thread(target=_safe_bg(self._fetch_ports_json, r), name=f"PortsFetcher-{r.name}", daemon=True).start()
            threading.Thread(target=_safe_bg(self._fetch_winecask_json, r), name=f"WineCaskFetcher-{r.name}", daemon=True).start()
        threading.Thread(target=_safe_bg(self._fetch_discounts), name="DiscountFetcher", daemon=True).start()

    # Pulls ITAD-tracked discounts from the RHH-Ports Cloudflare Worker for every
    # Steam appid in the catalog into self.discounts_by_appid. Fails silently.
    def _fetch_discounts(self) -> None:
        WORKER = "https://rhh-ports-discounts.jeodc.workers.dev/"
        COUNTRY = "US"
        # Wait for ports.json to populate so we know which appids matter; retry up to ~15s.
        deadline = time.time() + 15
        appids = set()
        while time.time() < deadline:
            for r in self.repositories:
                for p in getattr(r, "ports", []) or []:
                    for s in getattr(p, "store", []) or []:
                        url = s.get("gameurl", "") if isinstance(s, dict) else ""
                        m = re.search(r"store\.steampowered\.com/app/(\d+)", url)
                        if m:
                            appids.add(m.group(1))
            if appids:
                break
            time.sleep(0.5)
        if not appids:
            return
        try:
            url = f"{WORKER}?appids={','.join(sorted(appids))}&country={COUNTRY}"
            raw = self._gh_request(url, timeout=20)
            data = json.loads(raw)
            if not isinstance(data, dict):
                return
            # Worker returns { appid: { shop: {cut, url} } }. Flatten to { appid: { shop: cut } }.
            flattened: dict = {}
            for appid, shops in data.items():
                if not isinstance(shops, dict):
                    continue
                per_shop = {}
                for shop_name, entry in shops.items():
                    if isinstance(entry, dict):
                        cut = entry.get("cut", 0) or 0
                    else:
                        cut = entry or 0
                    if cut > 0:
                        per_shop[shop_name] = cut
                if per_shop:
                    flattened[appid] = per_shop
            with self._discounts_lock:
                self.discounts_by_appid = flattened
        except Exception:
            pass

    def _gh_request(self, url: str, timeout: int = 12) -> bytes:
        hdr = {"User-Agent": "Pharos/1.0"}
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()

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
    def _draw_button_bar(self, buttons: List[dict]) -> None:
        x = 20
        for b in buttons:
            self.ui.button_circle((x, self.ui.screen_height - 50), b["key"], b["label"], color=b["color"])
            x += 50 + len(b["label"]) * 7

    def _map_port_images(self, repo: Repository) -> None:
        items = getattr(repo, "ports", None) or getattr(repo, "bottles", None)
        if not items or not repo.images_dir or not os.path.isdir(repo.images_dir):
            return
        for item in items:
            # images.zip names are PortMaster-cleaned ("tunics!" becomes
            # "tunics"), so try the cleaned form too.
            cleaned = re.sub(r"[ \.]+", ".", re.sub(r"[^a-zA-Z0-9 _\-\.]+", "", item.name.strip().lower()))
            item.image_path = None
            for name in dict.fromkeys((item.name, cleaned)):
                for ext in ("png", "jpg", "jpeg"):
                    path = os.path.join(repo.images_dir, f"{name}.screenshot.{ext}")
                    if os.path.exists(path):
                        item.image_path = path
                        break
                if item.image_path:
                    break

    # ------------------------------------------------------------------
    # Render Views
    # ------------------------------------------------------------------
    def _render_repos(self) -> None:
        self.ui.draw_header("Select A Repository", color_text)
        pending = [r for r in self.repositories if not (getattr(r, "ports", None) or getattr(r, "bottles", None))]
        if pending:
            self._spin()
            self.ui.draw_log(text=f"{self.spinner_frame} Loading {len(pending)} repo(s)...", background=True)
            self._draw_button_bar([])
            return

        total_items = sum(len(getattr(r, "ports", [])) + len(getattr(r, "bottles", [])) for r in self.repositories)
        total_repos = sum(1 for r in self.repositories if getattr(r, "ports", None) or getattr(r, "bottles", None))
        self.ui.draw_log(text=f"Loaded {total_items} items in {total_repos} repositories", background=True)

        max_vis = 12
        start = max(0, self.repo_idx - max_vis + 1)
        visible = self.repositories[start: start + max_vis]
        for i, repo in enumerate(visible):
            y = 30 + i * 30
            sel = (start + i) == self.repo_idx
            cnt = len(getattr(repo, "ports", []) or getattr(repo, "bottles", []))
            owner = repo.url.split("github.com/")[1].split("/")[0]
            txt = f"{owner}/{repo.name} ({cnt} items)"
            self.ui.row_list(txt, (20, y), self.ui.screen_width // 2, 28, sel, color=color_text if sel else color_menu_bg)

        btns = [
            {"key": self.layout["a"]["btn"], "label": "Open", "color": self.layout["a"]["color"]},
            {"key": self.layout["b"]["btn"], "label": "Exit", "color": self.layout["b"]["color"]},
            {"key": self.layout["x"]["btn"], "label": "Pharos Service", "color": self.layout["x"]["color"]},
            {"key": self.layout["l1"]["btn"], "label": "Page Up", "color": self.layout["l1"]["color"]},
            {"key": self.layout["r1"]["btn"], "label": "Page Down", "color": self.layout["r1"]["color"]},
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
        stores = getattr(port, "store", None) or []
        # Find the port's Steam appid (ITAD lookup key) from any Steam URL.
        appid = None
        for s in stores:
            if not isinstance(s, dict):
                continue
            m = re.search(r"store\.steampowered\.com/app/(\d+)", s.get("gameurl", ""))
            if m:
                appid = m.group(1)
                break
        if not appid:
            return 0
        with self._discounts_lock:
            shops = self.discounts_by_appid.get(appid)
        if not shops:
            return 0
        best = 0
        for s in stores:
            if not isinstance(s, dict):
                continue
            cut = shops.get(s.get("name", ""), 0) or 0
            if cut > best:
                best = cut
        return best

    def _items_for_current_view(self, all_items):
        """Apply the active view_mode's filter+sort to the repo's items."""
        if self.view_mode == "installed":
            items = [i for i in all_items if i.name in local_md5s]
        else:
            items = list(all_items)

        if self.view_mode == "updated":
            items.sort(key=lambda p: p.date_updated or "", reverse=True)
        elif self.view_mode == "new":
            items.sort(key=lambda p: (getattr(p, "first_seen", None) or ""), reverse=True)
        elif self.view_mode == "discount":
            # Deepest discount first; alphabetical tiebreak keeps no-sale ports at bottom.
            items.sort(key=lambda p: (-self._max_discount_for_port(p),
                                      (getattr(p, "title", "") or "").lower()))
        return items

    def _render_ports(self) -> None:
        repo = self.repositories[self.repo_idx]
        all_items = getattr(repo, "ports", None) or getattr(repo, "bottles", None) or []
        items = self._items_for_current_view(all_items)
        owner = repo.url.split("github.com/")[1].split("/")[0]
        label = "installed" if self.view_mode == "installed" else "items"
        suffix = self._VIEW_MODE_HEADER_SUFFIX[self.view_mode]
        header_text = f"{len(items)} {label} in {owner}/{repo.name}{suffix}"
        self.ui.draw_header(header_text, color_text)
        
        is_bottle_repo = bool(getattr(repo, "bottles", None))
        can_download = (not is_bottle_repo) or WINDOWS_DIR.exists()

        max_vis = 12
        start = max(0, self.port_idx - max_vis + 1)
        visible = items[start: start + max_vis] if items else []
        selected_item = None
        for i, item in enumerate(visible):
            y = 30 + i * 30
            sel = (start + i) == self.port_idx
            size = f" [{item.size / (1024*1024):.2f} MB]" if item.size else ""
            is_muted = item.name in muted_ports
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
                color=color_text if sel else color_menu_bg,
                highlight=item.update_available and not is_muted,
            )
            if sel:
                selected_item = item

        if selected_item and selected_item.image_path and os.path.exists(selected_item.image_path):
            try:
                self.ui.draw_port_image(selected_item)
            except Exception:
                pass  # image draw errors are non-fatal
        # Reserve space below the description for the store-icon row (only when
        # the port has stores, else the description gets the full vertical area).
        has_stores = bool(selected_item and getattr(selected_item, "store", None))
        store_reserve = STORE_ROW_HEIGHT if has_stores else 0
        if selected_item and selected_item.desc:
            self.ui.draw_wrapped_text_centered(
                selected_item.desc,
                center_x=(self.ui.screen_width * 3 // 4 - 20),
                start_y=400 - FOOTER_HEIGHT - BUTTON_AREA_HEIGHT - 5,
                max_width=self.ui.screen_width // 2,
                color=color_text,
                reserve_bottom=store_reserve,
            )
        if has_stores:
            # Map this port's Steam appid -> its per-shop discount entries so
            # the renderer can show "-NN%" beside relevant icons.
            shops = None
            for s in selected_item.store:
                url = s.get("gameurl", "") if isinstance(s, dict) else ""
                m = re.search(r"store\.steampowered\.com/app/(\d+)", url)
                if m:
                    with self._discounts_lock:
                        shops = self.discounts_by_appid.get(m.group(1))
                    break
            self.ui.draw_port_stores(
                selected_item.store,
                discount_lookup=(lambda name, sh=shops: (sh or {}).get(name, 0)),
                center_x=(self.ui.screen_width * 3 // 4 - 20),
                max_width=self.ui.screen_width // 2,
                bottom_y=self.ui.screen_height - FOOTER_HEIGHT - BUTTON_AREA_HEIGHT,
            )

        # ------------------------------------------------------------------
        # Progress Queue Handling
        # ------------------------------------------------------------------
        has_download = not self.dl_queue.empty() or not self.progress_q.empty()
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
        else:
            selected = items[self.port_idx] if items else None
            local_md5 = local_md5s.get(selected.name) if selected else None

            if not can_download:
                bottom_log = f"ERROR: {WINDOWS_DIR} not found!"
            elif selected and selected.md5 and local_md5 and selected.md5 != local_md5:
                bottom_log = f"{selected.title} - Update available!"
            elif selected:
                bottom_log = f"{selected.last_commit}"
            elif self.view_mode == "installed":
                bottom_log = "No installed ports in this repository."
            else:
                bottom_log = ""

        self.ui.draw_log(text=bottom_log, background=True)

        btns = []
        if can_download:
            btns.append({"key": self.layout["a"]["btn"], "label": "Download", "color": self.layout["a"]["color"]})

        btns.append({"key": self.layout["b"]["btn"], "label": "Back", "color": self.layout["b"]["color"]})

        # X toggles per-port mute - only meaningful for ports in the local
        # manifest (selected_item.name in local_md5s); nothing to mute otherwise.
        if selected_item is not None and selected_item.name in local_md5s:
            x_label = "Unmute" if selected_item.name in muted_ports else "Mute"
            btns.append({"key": self.layout["x"]["btn"], "label": x_label,
                         "color": self.layout["x"]["color"]})

        btns.append({"key": self.layout["y"]["btn"],
                     "label": self._VIEW_MODE_BTN_LABEL[self.view_mode],
                     "color": self.layout["y"]["color"]})
        btns.append({"key": self.layout["l1"]["btn"], "label": "Page Up", "color": self.layout["l1"]["color"]})
        btns.append({"key": self.layout["r1"]["btn"], "label": "Page Down", "color": self.layout["r1"]["color"]})

        self._draw_button_bar(btns)

    # ------------------------------------------------------------------
    # Input Handling
    # ------------------------------------------------------------------
    def _update_repos(self) -> None:
        if not self.repositories:
            return
        repo = self.repositories[self.repo_idx]
        if self.input.key(self.layout["a"]["key"]) and (getattr(repo, "ports", None) or getattr(repo, "bottles", None)):
            self.current_view = "ports"
            self.port_idx = 0
            if repo.images_dir and os.path.isdir(repo.images_dir):
                self._map_port_images(repo)
        elif self.input.key(self.layout["b"]["key"]):
            if self.current_view == "repos":
                print("[USER] Exit requested via B button")
                self.running = False
            else:
                self.current_view = "repos"
        elif self.input.key(self.layout["x"]["key"]):
            self.current_view = "service"
            self.service_msg = ""
        else:
            self.repo_idx = self.input.handle_navigation(self.repo_idx, 10, len(self.repositories))

    def _update_ports(self) -> None:
        repo = self.repositories[self.repo_idx]
        all_items = getattr(repo, "ports", None) or getattr(repo, "bottles", None) or []
        items = self._items_for_current_view(all_items)

        is_bottle_repo = bool(getattr(repo, "bottles", None))
        can_download = (not is_bottle_repo) or WINDOWS_DIR.exists()

        # B (back) and Y (cycle view mode) must work even when the filtered
        # list is empty, else the user gets stuck in an empty view.
        if self.input.key(self.layout["b"]["key"]):
            for item in all_items:
                item.image_path = None
            self.current_view = "repos"
            while not self.dl_queue.empty():
                try:
                    self.dl_queue.get_nowait()
                except queue.Empty:
                    break
            return

        if self.input.key(self.layout["y"]["key"]):
            i = self.VIEW_MODES.index(self.view_mode)
            self.view_mode = self.VIEW_MODES[(i + 1) % len(self.VIEW_MODES)]
            self.port_idx = 0
            return

        if not items:
            return

        if self.input.key(self.layout["a"]["key"]) and can_download:
            self.dl_queue.put((items[self.port_idx], "port" if not is_bottle_repo else "bottle"))
            self._ensure_worker()

        elif self.input.key(self.layout["x"]["key"]):
            # Toggle mute; only acts on ports with a manifest entry.
            sel_item = items[self.port_idx]
            if sel_item.name in local_md5s:
                new_state = toggle_muted_port(sel_item.name)
                if new_state is True:
                    muted_ports.add(sel_item.name)
                elif new_state is False:
                    muted_ports.discard(sel_item.name)

        else:
            self.port_idx = self.input.handle_navigation(self.port_idx, 10, len(items))

    # ------------------------------------------------------------------
    # Worker Management
    # ------------------------------------------------------------------
    def _ensure_worker(self) -> None:
        if self.download_active:
            return
        if any(t.name == "DownloaderThread" and t.is_alive() for t in threading.enumerate()):
            return
        self.download_active = True
        worker = Downloader(self.dl_queue, self.progress_q)
        t = threading.Thread(
            target=self._download_wrapper,
            args=(worker,),
            name="DownloaderThread",
            daemon=True,
        )
        t.start()

    def _download_wrapper(self, worker: Downloader) -> None:
        try:
            worker.run()
        except Exception:
            import traceback
            print(f"[DOWNLOAD FAILED]\n{traceback.format_exc()}")
        finally:
            self.download_active = False

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------
    def start(self) -> None:
        threading.Thread(target=self._monitor_input, name="InputThread", daemon=True).start()

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
            time.sleep(0.001)

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

        # Description block, manually wrapped to fit half-screen width.
        description = [
            "Pharos Service is a small background daemon that watches",
            "the repos in .sources for port updates without you having",
            "to open Pharos.",
            "",
            "It runs at boot, fires a notification if any installed",
            "ports are out of date, and re-checks whenever you exit a",
            "game. Notifications appear as an EmulationStation toast.",
        ]
        for i, line in enumerate(description):
            y = 50 + i * 22
            self.ui.draw_text((40, y), line, color_text)

        # Status line, centered.
        status_label = self.service.status_text()
        sw_text = self.ui.get_text_width(status_label)
        self.ui.draw_text(
            (max(20, sw // 2 - sw_text // 2), 240),
            status_label,
            color_text,
        )

        # Footer log: most-recent action result, if any.
        if self.service_msg:
            self.ui.draw_log(text=self.service_msg, background=True)
        elif not supported:
            self.ui.draw_log(text="This CFW isn't supported yet.", background=True)
        else:
            self.ui.draw_log(
                text=("Press A to install" if not installed else "Press A to uninstall"),
                background=True,
            )

        btns = [{"key": self.layout["b"]["btn"], "label": "Back",
                 "color": self.layout["b"]["color"]}]
        if supported:
            label = "Uninstall" if installed else "Install"
            btns.insert(0, {
                "key": self.layout["a"]["btn"], "label": label,
                "color": self.layout["a"]["color"],
            })
        self._draw_button_bar(btns)

    def _update_service(self) -> None:
        if self.input.key(self.layout["b"]["key"]):
            self.current_view = "repos"
            self.service_msg = ""
            return

        if not self.service.supported:
            return

        if self.input.key(self.layout["a"]["key"]):
            # install/uninstall blocks for a couple seconds (systemctl /
            # batocera-settings / filesystem); show a transient "Working..." hint.
            self.ui.draw_log(text="Working...", background=True)
            self.ui.render_to_screen()
            if self.service.installed:
                ok, msg = self.service.uninstall()
            else:
                ok, msg = self.service.install()
            self.service_msg = ("[OK] " if ok else "[ERR] ") + msg

    # ------------------------------------------------------------------
    # Self-update
    # ------------------------------------------------------------------
    def _refresh_service_if_stale(self) -> None:
        try:
            if self.service.refresh_if_stale():
                print("[Service] daemon binary refreshed and service restarted")
        except Exception as e:
            print(f"[ServiceRefresh] failed: {e}")

    def _check_self_update(self) -> None:
        try:
            if self.updater.check():
                print(
                    f"[Update] Pharos v{self.updater.latest_version} available "
                    f"(installed: v{self.updater.current_version})"
                )
                self.self_update_available = True
        except Exception as e:
            import traceback
            print(f"[SelfUpdateCheck] Failed: {e}\n{traceback.format_exc()}")

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
            text=f"Pharos update v{self.updater.latest_version} available.",
            background=True,
        )

        btns = [
            {"key": self.layout["a"]["btn"], "label": "Yes", "color": self.layout["a"]["color"]},
            {"key": self.layout["b"]["btn"], "label": "No",  "color": self.layout["b"]["color"]},
        ]
        self._draw_button_bar(btns)

    def _handle_self_update_input(self) -> None:
        if self.input.key(self.layout["a"]["key"]):
            self.self_update_prompted = True
            if self.updater.download():
                self.ui.draw_log(
                    text=f"Pharos v{self.updater.latest_version} downloaded - applying and re-launching...",
                    background=True,
                )
                self.ui.render_to_screen()
                sdl2.SDL_Delay(2000)
                self.running = False
            else:
                self.ui.draw_log(
                    text="Update not ready (still publishing?) - try again in a few minutes.",
                    background=True,
                )
                self.ui.render_to_screen()
                sdl2.SDL_Delay(1500)
                self.self_update_available = False
        elif self.input.key(self.layout["b"]["key"]):
            self.self_update_prompted = True
            self.self_update_available = False