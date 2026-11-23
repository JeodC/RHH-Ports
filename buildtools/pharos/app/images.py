"""
Port screenshots from PortMaster's images or a download cache
"""

import os
import re
import shutil
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import List
from urllib.error import HTTPError

from config import DATA_DIR, Port, Repository
from download import controlfolder, stream

RESOURCES_DIR = Path(DATA_DIR) / "resources"
CACHE_MAX_BYTES = 32 * 1024 * 1024
TRIM_EVERY = 25  # downloads
BACKOFF_FIRST = 5  # seconds
BACKOFF_MAX = 300
EXTENSIONS = (".png", ".jpg", ".jpeg")


def _portmaster_dirs() -> dict[str, Path]:
    """Lowercase slug -> PortMaster's images folder for it"""
    if not controlfolder:
        return {}
    config_dir = Path(controlfolder) / "config"
    dirs = {}
    for source in config_dir.glob("*.source.json"):
        with suppress(OSError):
            with open(source, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(1024)  # the catalog that follows is megabytes
            prefix = re.search(r'"prefix":\s*"(\w+)"', head)
            slug = re.search(r'"url":\s*"https://github\.com/([^/"]+/[^/"]+)/', head)
            if prefix and slug:
                dirs[slug.group(1).lower()] = config_dir / f"images_{prefix.group(1)}"
    return dirs


def _listing(folder: Path) -> dict[str, str]:
    with suppress(OSError):
        return {name: str(folder / name) for name in os.listdir(folder)}
    return {}


def assign(repo: Repository) -> None:
    files = _listing(Path(repo.images_dir))
    portmaster = _portmaster_dirs().get(repo.slug.lower())
    if portmaster:
        files.update(_listing(portmaster))
    for item in repo.items:
        # PortMaster cleans names ("tunics!" becomes "tunics"), so try the
        # cleaned form too.
        cleaned = re.sub(r"[ \.]+", ".", re.sub(r"[^a-zA-Z0-9 _\-\.]+", "", item.name.strip().lower()))
        item.image_path = next(
            (
                files[f]
                for name in dict.fromkeys((item.name, cleaned))
                for ext in EXTENSIONS
                if (f := f"{name}.screenshot{ext}") in files
            ),
            None,
        )


def prune(repos: List[Repository]) -> None:
    portmaster = _portmaster_dirs()
    keep = {Path(r.images_dir).name: r for r in repos}
    for folder in RESOURCES_DIR.glob("*-images"):
        repo = keep.get(folder.name)
        if not repo:
            shutil.rmtree(folder, ignore_errors=True)
            continue
        theirs = _listing(portmaster.get(repo.slug.lower(), folder / "none"))
        for name, path in _listing(folder).items():
            if name in theirs or not name.endswith(EXTENSIONS):
                with suppress(OSError):
                    os.remove(path)
    _trim()


def _trim() -> None:
    cached = []
    for path in RESOURCES_DIR.glob("*-images/*"):
        with suppress(OSError):
            info = path.stat()
            cached.append((info.st_mtime, info.st_size, path))
    total = sum(size for _, size, _ in cached)
    for _, size, path in sorted(cached):
        if total <= CACHE_MAX_BYTES:
            break
        with suppress(OSError):
            path.unlink()
            total -= size


class Fetcher:
    def __init__(self) -> None:
        self._wanted: tuple | None = None
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._failed: set[tuple[str, str]] = set()
        self._retry_at = 0.0
        self._backoff = BACKOFF_FIRST
        self._fetched = 0

    def want(self, repo: Repository, port: Port) -> None:
        if (repo.slug, port.name) in self._failed or time.time() < self._retry_at:
            return
        self._wanted = (repo, port)
        self._wake.set()
        if not self._thread:
            self._thread = threading.Thread(target=self._run, name="ImageFetcher", daemon=True)
            self._thread.start()

    def reject(self, repo: Repository, port: Port) -> None:
        """The port's screenshot on disk couldn't be shown"""
        path, port.image_path = port.image_path, None
        # Never PortMaster's files
        if path and os.path.dirname(path) == os.path.normpath(repo.images_dir) and os.path.exists(path):
            self._failed.add((repo.slug, port.name))
            with suppress(OSError):
                os.remove(path)

    def _run(self) -> None:
        while True:
            self._wake.wait()
            self._wake.clear()
            if self._wanted:
                (repo, port), self._wanted = self._wanted, None
                # Asked for again while it was downloading
                if not port.image_path and time.time() >= self._retry_at:
                    self._fetch(repo, port)

    def _fetch(self, repo: Repository, port: Port) -> None:
        ext = os.path.splitext(port.image_url)[1].lower()
        dest = Path(repo.images_dir) / f"{port.name}.screenshot{ext if ext in EXTENSIONS else '.png'}"
        tmp = dest.with_name(dest.name + ".part")
        try:
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                stream(port.image_url, tmp, timeout=15)
                os.replace(tmp, dest)
                self._fetched += 1
                if self._fetched % TRIM_EVERY == 0:
                    _trim()
            port.image_path = str(dest)
            self._backoff = BACKOFF_FIRST
        except Exception as e:
            print(f"[IMAGES] {repo.slug} {port.name}: {e}")
            with suppress(OSError):
                tmp.unlink()
            retry_after = (e.headers.get("Retry-After") or "") if isinstance(e, HTTPError) else ""
            refused = isinstance(e, HTTPError) and 400 <= e.code < 500 and e.code not in (408, 429) and not retry_after
            if refused or isinstance(e, ValueError):
                self._failed.add((repo.slug, port.name))
                return
            wait = min(int(retry_after), BACKOFF_MAX) if retry_after.isdigit() else self._backoff
            self._retry_at = time.time() + wait
            self._backoff = min(self._backoff * 2, BACKOFF_MAX)
