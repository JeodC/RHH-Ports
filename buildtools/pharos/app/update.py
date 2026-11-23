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

import re
from http.client import HTTPException
from pathlib import Path
from urllib.request import Request, urlopen

import __version__
from config import DATA_DIR
from download import fetch, md5_file, progress_text, stream
from sources import catalog_entries

# ----------------------------------------------------------------------
# Where Pharos publishes from. Hardcoded, unlike sources.json for ports.
# ----------------------------------------------------------------------
PHAROS_REPO = "JeodC/RHH-Ports"
PHAROS_VERSION_RAW = f"https://raw.githubusercontent.com/{PHAROS_REPO}/main/buildtools/pharos/app/__version__.py"
PHAROS_PORTS_JSON_RAW = f"https://raw.githubusercontent.com/{PHAROS_REPO}/main/docs/ports.json"
PHAROS_PORT_NAME = "pharos.zip"

PENDING_ZIP = Path(DATA_DIR) / ".pending_update.zip"
VERSION_RE = re.compile(r"version\s*=\s*['\"]([^'\"]+)['\"]")


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

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    def check(self) -> bool:
        """Populate latest_version + download_url. Returns True if a newer
        version is available."""
        try:
            self.latest_version = _parse_version(fetch(PHAROS_VERSION_RAW, timeout=5).decode("utf-8", errors="replace"))
            if not self.latest_version:
                return False
            for entry in catalog_entries(fetch(PHAROS_PORTS_JSON_RAW, timeout=5)):
                if entry["name"] == PHAROS_PORT_NAME:
                    src = entry["source"]
                    self.download_url = src.get("download_url")
                    self.expected_md5 = src.get("md5")
                    size = src.get("size")
                    self.expected_size = int(size) if size else None
                    break
        except (OSError, ValueError, HTTPException) as e:
            print(f"[Update] check failed: {e}")
            return False

        return _version_tuple(self.current_version) < _version_tuple(self.latest_version)

    def _edge_is_stale(self) -> bool:
        """True when the CDN is still serving the previous asset."""
        if not self.expected_size:
            return False
        try:
            req = Request(self.download_url, headers={"User-Agent": "Pharos/Updater", "Range": "bytes=0-1023"})
            with urlopen(req, timeout=15) as resp:
                content_range = resp.getheader("Content-Range") or ""
                served_size = int(content_range.rpartition("/")[2] or 0)
                last_modified = resp.getheader("Last-Modified") or "unknown"
        except (OSError, ValueError, HTTPException) as e:
            # Inconclusive, so let the full download + md5 check decide.
            print(f"[Update] size pre-check failed ({e}); downloading anyway.")
            return False

        if served_size and served_size != self.expected_size:
            print(
                f"[Update] CDN still has the previous asset "
                f"({served_size} bytes, dated {last_modified}; expected {self.expected_size})."
            )
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

        try:
            stream(self.download_url, PENDING_ZIP, self._show_progress, timeout=30)
            # GitHub's release CDN can serve a stale zip for a few minutes after a
            # new build publishes, so a version-only check would install the old
            # binary and re-prompt every launch. Reject the mismatch instead.
            got = md5_file(PENDING_ZIP)
            if self.expected_md5 and got != self.expected_md5:
                raise ValueError(
                    f"md5 mismatch: expected {self.expected_md5}, got {got}; release still propagating - not applying."
                )
        except (OSError, ValueError, HTTPException) as e:
            # OSError covers disk-full / permission mid-write failures that would
            # otherwise propagate up and crash the input handler.
            print(f"[Update] Download failed: {e}")
            # The launcher applies whatever is left here
            PENDING_ZIP.unlink(missing_ok=True)
            return False
        print(f"[Update] Saved pending update to {PENDING_ZIP} (md5 {got}).")
        return True

    def _show_progress(self, downloaded: int, total: int, speed: float) -> None:
        if total:
            self.ui.draw_loader(downloaded / total * 100)
        self.ui.draw_log(text=progress_text(f"Downloading Pharos v{self.latest_version}...", downloaded, total, speed))
        self.ui.render_to_screen()
