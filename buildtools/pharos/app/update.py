#!/usr/bin/env python3
"""
Self-update mechanism. Adapted from rommapp/muos-app's RomM/update.py.

Flow: check() compares the bundled __version__ against __version__.py fetched
from PHAROS_REPO@main and reads the download URL + md5 from docs/ports.json.
download() streams the new zip to DATA_DIR/.pending_update.zip and verifies its
md5 against ports.json before accepting it. The Pharos App.sh wrapper applies it
(pre-launch if a prior run left one, or post-exit), extracting via 7zzs, copying
pharos/ to GAMEDIR, and re-exec'ing the new binary.
See ports/released/apps/pharos/Pharos App.sh::apply_pending_update.
"""
import hashlib
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import sdl2

import __version__
from config import DATA_DIR

# ----------------------------------------------------------------------
# Where Pharos publishes from. Hardcoded, unlike .sources for ports.
# ----------------------------------------------------------------------
PHAROS_REPO = "JeodC/RHH-Ports"
PHAROS_VERSION_RAW = (
    f"https://raw.githubusercontent.com/{PHAROS_REPO}/main/"
    "buildtools/pharos/app/__version__.py"
)
PHAROS_PORTS_JSON_RAW = (
    f"https://raw.githubusercontent.com/{PHAROS_REPO}/main/docs/ports.json"
)
PHAROS_PORT_NAME = "pharos.zip"

PENDING_ZIP = os.path.join(DATA_DIR, ".pending_update.zip")
VERSION_RE = re.compile(r"version\s*=\s*['\"]([^'\"]+)['\"]")


def _http_get(url: str, timeout: int = 5) -> bytes | None:
    try:
        req = Request(url, headers={"User-Agent": "Pharos/Updater"})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (HTTPError, URLError, TimeoutError) as e:
        print(f"[Update] {url} failed: {e}")
        return None


def _parse_version(text: str) -> str | None:
    m = VERSION_RE.search(text)
    return m.group(1) if m else None


def _version_tuple(v: str) -> tuple[int, ...]:
    """Semver-ish compare - three integer components, no pre-release/build metadata."""
    parts = re.findall(r"\d+", v)[:3]
    parts.extend(["0"] * (3 - len(parts)))
    return tuple(int(p) for p in parts)


class Update:
    def __init__(self, ui) -> None:
        self.ui = ui
        self.current_version = __version__.version
        self.latest_version: str | None = None
        self.download_url: str | None = None
        self.expected_md5: str | None = None
        self.expected_size: int | None = None
        self.download_percent = 0.0

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    def check(self) -> bool:
        """Populate latest_version + download_url. Returns True if a newer
        version is available."""
        raw_version = _http_get(PHAROS_VERSION_RAW)
        if raw_version is None:
            return False
        self.latest_version = _parse_version(raw_version.decode("utf-8", errors="replace"))
        if not self.latest_version:
            return False

        raw_ports = _http_get(PHAROS_PORTS_JSON_RAW)
        if raw_ports is not None:
            try:
                data = json.loads(raw_ports.decode("utf-8"))
                for entry in data:
                    if entry.get("name") == PHAROS_PORT_NAME:
                        src = entry.get("source", {}) or {}
                        self.download_url = src.get("download_url")
                        self.expected_md5 = src.get("md5")
                        size = src.get("size")
                        self.expected_size = int(size) if size else None
                        break
            except json.JSONDecodeError as e:
                print(f"[Update] ports.json parse failed: {e}")

        return _version_tuple(self.current_version) < _version_tuple(self.latest_version)

    def _edge_is_stale(self) -> bool:
        """True when the CDN is still serving the previous asset."""
        if not self.expected_size:
            return False
        try:
            req = Request(self.download_url,
                          headers={"User-Agent": "Pharos/Updater", "Range": "bytes=0-1023"})
            with urlopen(req, timeout=15) as resp:
                content_range = resp.getheader("Content-Range") or ""
                served_size = int(content_range.rpartition("/")[2] or 0)
                last_modified = resp.getheader("Last-Modified") or "unknown"
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as e:
            # Inconclusive, so let the full download + md5 check decide.
            print(f"[Update] size pre-check failed ({e}); downloading anyway.")
            return False

        if served_size and served_size != self.expected_size:
            print(f"[Update] CDN still has the previous asset "
                  f"({served_size} bytes, dated {last_modified}; expected {self.expected_size}).")
            return True
        return False

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def download(self) -> bool:
        """Stream the new zip into PENDING_ZIP with progress UI. Returns success."""
        if not self.download_url:
            print("[Update] No download URL; cannot download.")
            return False

        if self._edge_is_stale():
            return False

        # Drop any stale pending zip (e.g. canceled mid-extract) so we don't apply an old build.
        if os.path.exists(PENDING_ZIP):
            try:
                os.remove(PENDING_ZIP)
            except OSError:
                pass

        try:
            req = Request(self.download_url, headers={"User-Agent": "Pharos/Updater"})
            with urlopen(req) as resp:
                total = int(resp.getheader("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192
                md5 = hashlib.md5()

                with open(PENDING_ZIP, "wb") as out:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        out.write(chunk)
                        md5.update(chunk)
                        downloaded += len(chunk)
                        self.download_percent = min(100.0, downloaded / total * 100.0)

                        self.ui.draw_loader(self.download_percent)
                        self.ui.draw_log(
                            text=f"Downloading Pharos v{self.latest_version}... {self.download_percent:.1f}%",
                            background=True,
                        )
                        self.ui.render_to_screen()
                        sdl2.SDL_Delay(16)

            # GitHub's release CDN can serve a stale zip for a few minutes after a
            # new build publishes, so a version-only check would install the old
            # binary and re-prompt every launch. Reject the mismatch instead.
            got = md5.hexdigest()
            if self.expected_md5 and got != self.expected_md5:
                print(f"[Update] md5 mismatch: expected {self.expected_md5}, got {got}; "
                      "release still propagating - not applying.")
                if os.path.exists(PENDING_ZIP):
                    try:
                        os.remove(PENDING_ZIP)
                    except OSError:
                        pass
                return False

            print(f"[Update] Saved pending update to {PENDING_ZIP} "
                  f"({downloaded} bytes, md5 {got}).")
            return True
        except (HTTPError, URLError, OSError) as e:
            # OSError covers disk-full / permission mid-write failures that would
            # otherwise propagate up and crash the input handler.
            print(f"[Update] Download failed: {e}")
            if os.path.exists(PENDING_ZIP):
                try:
                    os.remove(PENDING_ZIP)
                except OSError:
                    pass
            return False
