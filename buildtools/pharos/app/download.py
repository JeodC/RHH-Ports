#!/usr/bin/env python3
"""
Pharos download worker
"""
import os
import errno
import json
import queue
import hashlib
import threading
import urllib.request
import zipfile
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from contextlib import suppress

import manifest
from config import DATA_DIR, Port
from autoinstall import AutoInstaller
from sources import runtime_catalog_urls

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
BASE_DIR = Path(DATA_DIR)
AUTOINSTALL_DIR = BASE_DIR / "autoinstall"
AUTOINSTALL_DIR.mkdir(parents=True, exist_ok=True)

# Runtime environment
controlfolder = os.environ.get("controlfolder", "")
LIBS_DIR = Path(controlfolder) / "libs" if controlfolder else None
DEVICE_ARCH = os.environ.get("DEVICE_ARCH", "")

# CLI binary every GameMaker port needs at patch time. /releases/latest/download
# auto-redirects to the newest non-prerelease asset, so this URL never needs bumping.
GMTOOLKIT_RELEASE_URL = "https://github.com/JeodC/gmtoolkit/releases/latest/download"

PROGRESS_INTERVAL = 0.1  # seconds

# ----------------------------------------------------------------------
# Requests
# ----------------------------------------------------------------------
def progress_text(prefix: str, downloaded: int, total: int, speed: float) -> str:
    """A percentage when the server sent a size, transferred bytes when it did not."""
    if total:
        return f"{prefix} ({downloaded / total * 100:.1f}%) - {speed:.2f} MB/s"
    return f"{prefix} ({downloaded / (1024 * 1024):.1f} MB) - {speed:.2f} MB/s"


def _check_free_space(dest_dir: Path, needed: int) -> None:
    if not needed:
        return
    free = shutil.disk_usage(dest_dir).free
    if free >= needed:
        return
    mount = dest_dir
    while not os.path.ismount(mount) and mount.parent != mount:
        mount = mount.parent
    raise OSError(
        errno.ENOSPC,
        f"No space on {mount} (need {needed / (1024 * 1024):.0f} MB, {free / (1024 * 1024):.0f} MB free)",
    )


def _error_text(e: Exception, fallback: str) -> str:
    if isinstance(e, ConnectionError):
        return str(e)
    return e.strerror if getattr(e, "errno", None) == errno.ENOSPC else fallback


def md5_file(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "md5").hexdigest()


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Pharos/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def stream(url: str, dest: Path, on_progress=None, known_etag: str = "", space: int = 1,
           timeout: int = 60) -> str | None:
    """Returns the ETag, or None if it's still known_etag"""
    req = urllib.request.Request(url, headers={"User-Agent": "Pharos/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        etag = resp.headers.get("ETag") or ""
        if known_etag and etag == known_etag:
            return None
        total = int(resp.headers.get("Content-Length") or 0)
        _check_free_space(dest.parent, total * space)
        downloaded = 0
        start = last = time.time()
        with open(dest, "wb") as f:
            while data := resp.read(64 * 1024):
                f.write(data)
                downloaded += len(data)
                now = time.time()
                if on_progress and now - last >= PROGRESS_INTERVAL:
                    last = now
                    on_progress(downloaded, total, downloaded / (1024 * 1024) / (now - start))
        # A dropped connection ends read() early instead of raising
        if total and downloaded != total:
            raise ConnectionError(f"Connection dropped at {downloaded / total * 100:.0f}%")
        return etag

# ----------------------------------------------------------------------
# Downloader
# ----------------------------------------------------------------------
class Downloader:
    def __init__(self, progress_q: queue.Queue):
        self.dl_queue: queue.Queue = queue.Queue()
        self.progress_q = progress_q
        self.autoinstall_dir = AUTOINSTALL_DIR
        self.installer = AutoInstaller(self.autoinstall_dir)
        self.installing = False
        self._runtime_url_cache: dict = {}
        self._gmtoolkit_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._queued: set[str] = set()
        self._downloaded: dict[str, tuple[dict, str]] = {}  # zip name -> (manifest entry, manifest key)

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------
    def enqueue(self, port: Port, kind: str) -> None:
        if port.name in self._queued:
            return
        self._queued.add(port.name)
        self.dl_queue.put((port, kind))
        if not (self._thread and self._thread.is_alive()):
            self._thread = threading.Thread(target=self.run, name="DownloaderThread", daemon=True)
            self._thread.start()

    def clear_queue(self) -> None:
        with suppress(queue.Empty):
            while True:
                port, _ = self.dl_queue.get_nowait()
                self._queued.discard(port.name)

    def stop(self, timeout: float = 5.0) -> None:
        self.clear_queue()
        self.dl_queue.put(None)
        deadline = time.time() + timeout
        while self._thread and self._thread.is_alive() and (self.installing or time.time() < deadline):
            time.sleep(0.05)

    # ------------------------------------------------------------------
    # Runtime URL resolution
    # ------------------------------------------------------------------
    def _runtime_urls(self, repo_slug: str) -> dict:
        """Runtime name -> URL from the repo's PortMaster catalog: 'utils' for
        repo-hosted runtimes, 'official_runtimes' for PortMaster's own."""
        if repo_slug in self._runtime_url_cache:
            return self._runtime_url_cache[repo_slug]
        urls = {}
        try:
            for url in runtime_catalog_urls(repo_slug):
                catalog = json.loads(fetch(url))
                for section in ("utils", "official_runtimes"):
                    for name, info in catalog.get(section, {}).items():
                        if name.endswith(".squashfs") and info.get("url"):
                            urls.setdefault(name, info["url"])
            self._runtime_url_cache[repo_slug] = urls
        except Exception as e:
            print(f"[RUNTIME] Catalog lookup failed for {repo_slug}: {e}")
        return urls

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        self._sweep_stale_partials()
        while (item := self.dl_queue.get()) is not None:
            port, kind = item
            try:
                self._download_runtimes(port)
                self._ensure_gmtoolkit_binary(port)
                self._download_port(port, kind)
                self._run_autoinstall()
            except Exception as e:
                print(f"[DOWNLOAD ERROR] {port.name}: {type(e).__name__}: {e}")
                self._fail(port, f"{type(e).__name__}: {e}")
            self._queued.discard(port.name)

    def _sweep_stale_partials(self) -> None:
        for part in self.autoinstall_dir.glob("*.part"):
            with suppress(OSError):
                part.unlink()

    # ------------------------------------------------------------------
    # Autoinstall phase
    # ------------------------------------------------------------------
    def _run_autoinstall(self) -> None:
        zip_files = sorted(self.autoinstall_dir.glob("*.zip"))
        if not zip_files:
            return

        failed = []
        self.installing = True
        try:
            for zip_file in zip_files:
                name = zip_file.name
                self.progress_q.put((0, 1, f"Installing {name}", "install"))
                entry = self._downloaded.pop(name, None)
                if self.installer.install_zip(name) != 0:
                    failed.append(name)
                elif entry:
                    try:
                        manifest.record(*entry)
                    except OSError as e:
                        print(f"[ERROR] Manifest update failed: {e}")
        finally:
            self.installing = False
        status = f"[ERROR] Install failed: {', '.join(failed)}" if failed else "Installation complete"
        self.progress_q.put((0, 1, status, "install"))

    # ------------------------------------------------------------------
    # Runtime downloads
    # ------------------------------------------------------------------
    def _download_runtimes(self, port: Port) -> None:
        if not port.runtime or not port.runtime_base_url:
            return
        if DEVICE_ARCH != "aarch64":
            print(f"[RUNTIME] Skipping (arch={DEVICE_ARCH!r}, need aarch64)")
            return
        if not LIBS_DIR:
            print("[RUNTIME] Skipping (controlfolder not set)")
            return

        LIBS_DIR.mkdir(parents=True, exist_ok=True)
        known = manifest.load().get("runtimes", {})

        for rt_name in port.runtime:
            rt_path = LIBS_DIR / rt_name

            if rt_path.exists():
                if known.get(rt_name, {}).get("md5"):
                    print(f"[RUNTIME] {rt_name} present, skipping")
                    continue
                # On disk but not in manifest - record its md5 so we skip next time
                print(f"[RUNTIME] {rt_name} found on disk, recording md5")
                self._record_runtime(rt_name, rt_path)
                continue

            url = self._runtime_urls(port.repo).get(rt_name) or f"{port.runtime_base_url}/{rt_name}"
            print(f"[RUNTIME] Downloading {rt_name} from {url}")
            self.progress_q.put((0, 1, f"Runtime: {rt_name}", "download"))
            tmp_path = rt_path.with_name(rt_name + ".tmp")

            try:
                stream(url, tmp_path, self._progress(f"Runtime: {rt_name}"))
                os.replace(tmp_path, rt_path)
                self._record_runtime(rt_name, rt_path)
                self.progress_q.put((1, 1, f"Runtime installed: {rt_name}", "download"))
                print(f"[RUNTIME] Installed {rt_name}")
            except Exception as e:
                print(f"[RUNTIME ERROR] {rt_name}: {type(e).__name__}: {e}")
                self.progress_q.put((0, 1, _error_text(e, f"Runtime failed: {rt_name}"), "download"))
                with suppress(OSError):
                    tmp_path.unlink()

    def _record_runtime(self, rt_name: str, rt_path: Path) -> None:
        md5 = md5_file(rt_path)
        try:
            with manifest.edit() as data:
                data.setdefault("runtimes", {})[rt_name] = {"md5": md5}
        except OSError as e:
            print(f"[ERROR] Manifest update failed: {e}")

    # ------------------------------------------------------------------
    # gmtoolkit binary check
    # ------------------------------------------------------------------
    def _ensure_gmtoolkit_binary(self, port: Port) -> None:
        if not port.runtime or "gmloadernext.squashfs" not in port.runtime:
            return
        with self._gmtoolkit_lock:
            self._sync_gmtoolkit_binary()

    def refresh_gmtoolkit_if_installed(self) -> None:
        """Update a gmtoolkit that is already on disk."""
        if not controlfolder:
            return
        if not (Path(controlfolder) / f"gmtoolkit.{DEVICE_ARCH}").exists():
            return
        with self._gmtoolkit_lock:
            self._sync_gmtoolkit_binary()

    def _sync_gmtoolkit_binary(self) -> None:
        if DEVICE_ARCH != "aarch64":
            return
        if not controlfolder:
            return

        dest = Path(controlfolder) / f"gmtoolkit.{DEVICE_ARCH}"
        zip_name = f"gmtoolkit-{DEVICE_ARCH}.zip"
        zip_tmp = Path(controlfolder) / f"{zip_name}.tmp"
        etag = manifest.load().get("gmtoolkit", {}).get("etag", "") if dest.exists() else ""
        try:
            etag = stream(
                f"{GMTOOLKIT_RELEASE_URL}/{zip_name}", zip_tmp, self._progress("gmtoolkit"),
                known_etag=etag, space=2,
            )
            if etag is None:
                print("[GMTOOLKIT] Present and up to date")
                return

            # Extract binary + license bundle into $controlfolder.
            with zipfile.ZipFile(zip_tmp) as zf:
                zf.extractall(controlfolder)
            with suppress(OSError):
                os.chmod(dest, 0o755)
            # Record installed version so future runs detect staleness.
            with manifest.edit() as data:
                data["gmtoolkit"] = {"etag": etag}
            self.progress_q.put((1, 1, "gmtoolkit installed", "download"))
            print(f"[GMTOOLKIT] Installed {dest}")
        except Exception as e:
            print(f"[GMTOOLKIT ERROR] {type(e).__name__}: {e}")
            # An older copy still works
            if not dest.exists():
                self.progress_q.put((0, 1, _error_text(e, "gmtoolkit failed"), "download"))
        finally:
            with suppress(OSError):
                zip_tmp.unlink()

    # ------------------------------------------------------------------
    # Single-port download (streaming)
    # ------------------------------------------------------------------
    def _download_port(self, port: Port, kind: str) -> None:
        print(f"[DOWNLOAD] Starting: {port.name} from {port.download_url!r}")
        zip_path = self.autoinstall_dir / f"{port.name}.zip"
        tmp_path = zip_path.with_name(zip_path.name + ".part")
        try:
            stream(port.download_url, tmp_path, self._progress(port.title))
            os.replace(tmp_path, zip_path)
            size = zip_path.stat().st_size
            self.progress_q.put((size, size, f"Downloaded: {port.title}", "download"))

            entry = asdict(port)
            entry.update(md5=md5_file(zip_path), size=size)
            self._downloaded[zip_path.name] = (entry, "ports" if kind == "port" else "bottles")
            print(f"[DOWNLOAD] Complete: {zip_path} ({size} bytes)")

        except Exception as e:
            print(f"[DOWNLOAD ERROR] {port.name}: {type(e).__name__}: {e}")
            self._fail(port, _error_text(e, f"{type(e).__name__}: {e}"))
            with suppress(OSError):
                tmp_path.unlink()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _progress(self, label: str):
        def report(downloaded: int, total: int, speed: float) -> None:
            self.progress_q.put((downloaded, total, progress_text(label, downloaded, total, speed), "download"))
        return report

    def _fail(self, port: Port, message: str) -> None:
        self.progress_q.put((0, 1, f"Failed {port.name}.zip: {message}", "download"))
        print(f"[ERROR] {message}")
