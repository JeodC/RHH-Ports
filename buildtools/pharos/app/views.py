"""
Pharos screens
"""
import queue
import time
from itertools import cycle
from typing import List

import sdl2

import images
import manifest
from autoinstall import WINDOWS_DIR
from config import Port, Repository
from ui import (
    color_menu_bg,
    color_row_text,
    color_text,
    c_row_muted,
    FOOTER_HEIGHT,
    BUTTON_AREA_HEIGHT,
    STORE_ROW_HEIGHT,
)

MAX_ROWS = 12
REPO_ROWS = 10
DECODE_DELAY = 0.1  # seconds on a port before its screenshot is loaded
FETCH_DELAY = 0.3  # seconds before one is downloaded
PROGRESS_STICKY_SECONDS = 2.0


class View:
    def __init__(self, app) -> None:
        self.app = app
        self.ui = app.ui
        self.input = app.input

    def draw(self) -> None:
        raise NotImplementedError

    def handle_input(self) -> None:
        raise NotImplementedError

    def _pressed(self, button: str) -> bool:
        return self.input.key(self.app.layout[button]["key"])

    def _draw_button_bar(self, buttons: List[tuple]) -> None:
        """buttons: (layout button, label) pairs"""
        x = 20
        for button, label in buttons:
            b = self.app.layout[button]
            # Small screens have no room for Page Up and Page Down
            if x + self.ui.get_text_width(label) + 20 > self.ui.screen_width:
                break
            end = self.ui.button_circle((x, self.ui.screen_height - 50), b["btn"], label, color=b["color"])
            x = int(end) + 22

    def _draw_row(self, text: str, y: int, selected: bool) -> None:
        self.ui.row_list(text, (20, y), self.ui.screen_width - 40, 28, selected,
                         color=color_text if selected else color_row_text)

    def _draw_rows(self, rows: List[str], idx: int, count: int) -> None:
        start = max(0, min(idx, len(rows) - 1) - count + 1)
        for i, text in enumerate(rows[start: start + count]):
            self._draw_row(text, 30 + i * 30, start + i == idx)


# ----------------------------------------------------------------------
# Repositories
# ----------------------------------------------------------------------
class RepoView(View):
    MENU = ("Settings", "Exit")

    def __init__(self, app) -> None:
        super().__init__(app)
        self.idx = 0
        self.selected = ""  # slug or menu label

        # Loading spinner (only used during repo fetch)
        self.spinner = cycle(["|", "/", "-", "\\"])
        self.spinner_speed = 0.12
        self.last_spinner = 0.0
        self.spinner_frame = ""

    def _spin(self) -> None:
        now = time.time()
        if now - self.last_spinner >= self.spinner_speed:
            self.last_spinner = now
            self.spinner_frame = next(self.spinner)

    def _repos(self) -> List[Repository]:
        # Sources that failed to load or hold nothing aren't listed
        repos = [r for r in self.app.repositories if not r.loaded or r.items]
        # Keep the selection when a row above it goes away
        rows = self._row_keys(repos)
        self.idx = rows.index(self.selected) if self.selected in rows else min(self.idx, len(repos))
        return repos

    def _row_keys(self, repos: List[Repository]) -> List[str]:
        return [r.slug for r in repos] + list(self.MENU)

    def draw(self) -> None:
        self.ui.draw_header("Select A Repository", color_text)
        repos = self._repos()

        loading = sum(not r.loaded for r in repos)
        if loading:
            self._spin()
            self.ui.draw_log(text=f"{self.spinner_frame} Loading {loading} repo(s)...")
        else:
            total_items = sum(len(r.items) for r in repos)
            self.ui.draw_log(text=self.app.sources_error or f"Loaded {total_items} items in {len(repos)} repositories")

        rows = [f"{r.slug} ({len(r.items)} items)" if r.loaded else f"{r.slug} (loading...)" for r in repos]
        self._draw_rows(rows, self.idx, REPO_ROWS)
        for i, label in enumerate(self.MENU):
            self._draw_row(label, 352 + i * 30, self.idx == len(rows) + i)

        btns = [
            ("a", "Select"),
            ("b", "Exit"),
            ("l1", "Page Up"),
            ("r1", "Page Down"),
        ]
        self._draw_button_bar(btns)

    def handle_input(self) -> None:
        repos = self._repos()
        rows = self._row_keys(repos)
        row = rows[self.idx]
        if self._pressed("a"):
            if row == "Settings":
                self.app.push(SettingsView(self.app))
            elif row == "Exit":
                self._exit()
            elif repos[self.idx].loaded:
                self.app.push(PortsView(self.app, repos[self.idx]))
        elif self._pressed("b"):
            self._exit()
        else:
            idx = self.input.handle_navigation(self.idx, 10, len(rows))
            if idx != self.idx:
                self.idx, self.selected = idx, rows[idx]

    def _exit(self) -> None:
        print("[USER] Exit requested")
        self.app.running = False


# ----------------------------------------------------------------------
# Ports
# ----------------------------------------------------------------------
class PortsView(View):
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

    def __init__(self, app, repo: Repository) -> None:
        super().__init__(app)
        self.repo = repo
        self.idx = 0
        self._items_cache: tuple = (None, [])
        self._selected_since: tuple = (None, 0.0)  # port name, time

        # 2-second sticky message handling
        self.last_progress_msg = None  # (dl, tot, txt, stage)
        self.last_progress_time = 0.0
        self.progress_percent = 0.0

        images.assign(repo)

    def _max_discount_for_port(self, port) -> int:
        """Deepest active discount % across all of a port's stores, or 0."""
        shops = self.app.discounts_by_appid.get(port.appid)
        if not shops:
            return 0
        return max((shops.get(s.get("name", ""), 0) for s in port.store), default=0)

    def items(self) -> List[Port]:
        """Apply the active view_mode's filter+sort to the repo's items."""
        mode = self.app.view_mode
        key = (mode, manifest.installed, self.app.discounts_by_appid)
        if self._items_cache[0] == key:
            return self._items_cache[1]
        old = self._items_cache[1][self.idx:self.idx + 1] if self.idx else []

        items = list(self.repo.items)
        if mode == "installed":
            items = [i for i in items if manifest.entry_for(i)]
        elif mode == "updated":
            items.sort(key=lambda p: p.date_updated or "", reverse=True)
        elif mode == "new":
            items.sort(key=lambda p: p.first_seen or "", reverse=True)
        elif mode == "discount":
            # Deepest discount first; alphabetical tiebreak keeps no-sale ports at bottom.
            items.sort(key=lambda p: (-self._max_discount_for_port(p), p.title.lower()))
        self._items_cache = (key, items)
        # Installing it from another repo drops it from the installed list
        self.idx = items.index(old[0]) if old and old[0] in items else max(0, min(self.idx, len(items) - 1))
        return items

    def _can_download(self) -> bool:
        return not self.repo.bottles or WINDOWS_DIR.exists()

    def _draw_selected_image(self, port: Port) -> None:
        if port.name != self._selected_since[0]:
            self._selected_since = (port.name, time.time())
        rested = time.time() - self._selected_since[1]
        if port.image_path:
            if rested >= DECODE_DELAY or self.ui.has_texture(port.image_path):
                if not self.ui.draw_port_image(port.image_path, max_h=280 - self.ui.desc_shift):
                    self.app.image_fetcher.reject(self.repo, port)
        elif port.image_url and rested >= FETCH_DELAY:
            self.app.image_fetcher.want(self.repo, port)

    def draw(self) -> None:
        repo, mode = self.repo, self.app.view_mode
        items = self.items()
        label = "installed" if mode == "installed" else "items"
        suffix = self._VIEW_MODE_HEADER_SUFFIX[mode]
        header_text = f"{len(items)} {label} in {repo.slug}{suffix}"
        self.ui.draw_header(header_text, color_text)

        can_download = self._can_download()

        start = max(0, self.idx - MAX_ROWS + 1)
        visible = items[start: start + MAX_ROWS]
        selected_item = items[self.idx] if items else None
        for i, item in enumerate(visible):
            y = 30 + i * 30
            sel = (start + i) == self.idx
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
            self._draw_selected_image(selected_item)
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
            shops = self.app.discounts_by_appid.get(selected_item.appid, {})
            self.ui.draw_port_stores(
                selected_item.store,
                discount_lookup=lambda name: shops.get(name, 0),
                center_x=(self.ui.screen_width * 3 // 4 - 20),
                max_width=self.ui.screen_width // 2,
                bottom_y=self.ui.screen_height - self.ui.footer_height - BUTTON_AREA_HEIGHT,
            )

        self._update_progress()

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
        elif mode == "installed":
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

        btns.append(("y", self._VIEW_MODE_BTN_LABEL[mode]))
        btns.append(("l1", "Page Up"))
        btns.append(("r1", "Page Down"))

        self._draw_button_bar(btns)

    def _update_progress(self) -> None:
        latest = None
        while True:
            try:
                item = self.app.progress_q.get_nowait()
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
            if elapsed >= PROGRESS_STICKY_SECONDS:
                self.last_progress_msg = None
                self.progress_percent = 0
        else:
            self.progress_percent = 0

    def handle_input(self) -> None:
        items = self.items()

        # B (back) and Y (cycle view mode) must work even when the filtered
        # list is empty, else the user gets stuck in an empty view.
        if self._pressed("b"):
            self.app.pop()
            self.app.downloader.clear_queue()
            return

        if self._pressed("y"):
            i = self.VIEW_MODES.index(self.app.view_mode)
            self.app.view_mode = self.VIEW_MODES[(i + 1) % len(self.VIEW_MODES)]
            self._items_cache = (None, [])
            self.idx = 0
            return

        if not items:
            return

        if self._pressed("a") and self._can_download():
            self.app.downloader.enqueue(items[self.idx], "bottle" if self.repo.bottles else "port")

        elif self._pressed("x"):
            # Toggle mute; only acts on ports with a manifest entry.
            if manifest.entry_for(items[self.idx]):
                manifest.toggle_muted(items[self.idx])

        else:
            self.idx = self.input.handle_navigation(self.idx, 10, len(items))


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
class SettingsView(View):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.idx = 0

    def _rows(self) -> List[tuple]:
        """(label, view) pairs"""
        return [
            (f"Pharos Service: {self.app.service.status_text()}", ServiceView),
        ]

    def draw(self) -> None:
        self.ui.draw_header("Settings", color_text)
        self._draw_rows([label for label, _ in self._rows()], self.idx, MAX_ROWS)
        self.ui.draw_log(text=f"Pharos v{self.app.updater.current_version}")
        self._draw_button_bar([("a", "Open"), ("b", "Back")])

    def handle_input(self) -> None:
        rows = self._rows()
        if self._pressed("a"):
            self.app.push(rows[self.idx][1](self.app))
        elif self._pressed("b"):
            self.app.pop()
        else:
            self.idx = self.input.handle_navigation(self.idx, 10, len(rows))


# ----------------------------------------------------------------------
# Pharos Service
# ----------------------------------------------------------------------
class ServiceView(View):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.service = app.service
        self.msg = ""  # last install/uninstall result, shown in log strip

    def draw(self) -> None:
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
        if self.msg:
            self.ui.draw_log(text=self.msg)
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

    def handle_input(self) -> None:
        if self._pressed("b"):
            self.app.pop()
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
            self.msg = ("[OK] " if ok else "[ERR] ") + msg
            self.input.begin_frame()  # drop presses made meanwhile


# ----------------------------------------------------------------------
# Self-update
# ----------------------------------------------------------------------
class UpdateView(View):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.updater = app.updater

    def draw(self) -> None:
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

    def handle_input(self) -> None:
        if self._pressed("a"):
            if self.updater.download():
                self.ui.draw_log(
                    text=f"Pharos v{self.updater.latest_version} downloaded - applying and re-launching..."
                )
                self.ui.render_to_screen()
                sdl2.SDL_Delay(2000)
                self.app.running = False
            else:
                self.ui.draw_log(
                    text="Update not ready (still publishing?) - try again in a few minutes."
                )
                self.ui.render_to_screen()
                sdl2.SDL_Delay(1500)
                self.app.pop()
                self.input.begin_frame()  # drop presses made meanwhile
        elif self._pressed("b"):
            self.app.pop()
