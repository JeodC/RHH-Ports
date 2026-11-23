#!/usr/bin/env python3
"""
pharos-daemon - background update-checker for Pharos.

Event-driven: initial check on startup, then sleeps until SIGHUP (fired by
the ES game-end script). On wake, re-checks Pharos's manifest against each
repo's catalog and fires one ES notification for outdated ports.
Dedup state is in /tmp, so a reboot re-shows the toast.

Supported daemon hosts: the 'systemd' bucket (LibreELEC family - ROCKNIX,
AmberELEC, JELOS, EmuELEC, UnofficialOS) and 'userland' bucket (Batocera
family - Knulli, Batocera, REGLinux). MuOS is detected for logging but has
no notification backend (MuOS users invoke Pharos directly).

Usage (the Service installer handles this; direct invocation is for
diagnostics):
  pharos-daemon                   # daemon loop
  pharos-daemon --once            # single check + exit
  pharos-daemon --install-module  # restore the ES Tools entry + exit
  pharos-daemon --verbose         # echo logs to stderr
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import hashlib
import json
import os
import shutil
import signal
import socket
import sys
import time
import urllib.request
from http.client import HTTPException
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError

from cfw import detect_cfw, set_device_override
from sources import catalog_entries, catalog_urls, is_portmaster, read_sources

# Minimal CFWs (Knulli) lack CA certs in OpenSSL's default path, so HTTPS
# fails with CERTIFICATE_VERIFY_FAILED. Point ssl at our bundled certifi store.
import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# Ignore SIGHUP at import time: the default SIG_DFL would terminate the
# process if a game-end SIGHUP lands before daemon_loop installs its handler.
signal.signal(signal.SIGHUP, signal.SIG_IGN)

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
INSTALL_DIR = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
SOURCES_PATH = INSTALL_DIR / "sources.json"
SETTINGS_PATH = INSTALL_DIR / "settings.json"
MANIFEST_PATH = INSTALL_DIR / "resources" / "manifest.json"

PID_FILE = INSTALL_DIR / "resources" / "daemon.pid"
LOG_FILE = INSTALL_DIR / "logs" / "daemon.log"

PID_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Minimum gap between GitHub fetches; rate-limits SIGHUP storms (back-to-back
# game-end events) from hammering the API.
MIN_FETCH_INTERVAL_S = 300

RETRY_BACKOFF_INITIAL = 5
RETRY_BACKOFF_MAX = 60
GITHUB_HTTP_TIMEOUT = 10

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
_verbose = False

# Rotate daemon.log at this size, keeping a single .1 backup.
LOG_MAX_BYTES = 256 * 1024


def _rotate_log_if_needed() -> None:
    """Roll LOG_FILE -> LOG_FILE.1 once it exceeds LOG_MAX_BYTES. Size-based
    rotation (vs. truncate-on-every-start) keeps a restart storm visible instead
    of each respawn erasing the prior crash."""
    try:
        if LOG_FILE.stat().st_size < LOG_MAX_BYTES:
            return
    except OSError:
        return
    backup = LOG_FILE.with_name(LOG_FILE.name + ".1")
    try:
        os.replace(LOG_FILE, backup)
    except OSError:
        pass


def log(level: str, msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [{level}] {msg}\n"
    try:
        _rotate_log_if_needed()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
    if _verbose or level in ("ERROR", "WARN"):
        sys.stderr.write(line)


def _log_info(msg: str) -> None:
    log("INFO", msg)


# ----------------------------------------------------------------------
# Notification backends
# ----------------------------------------------------------------------
def notify_es_http(message: str) -> bool:
    """Both supported buckets share the batocera-ES HTTP /notify endpoint."""
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:1234/notify",
            data=message.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            return True
    except socket.timeout:
        log("INFO", "notify_es_http: server slow to ack; assuming delivered")
        return True
    except (HTTPError, URLError, OSError) as e:
        log("WARN", f"notify_es_http failed: {e}")
        return False


def notify(cfw: str, message: str) -> bool:
    if cfw in ("systemd", "userland"):
        return notify_es_http(message)
    log("WARN", f"unsupported CFW '{cfw}'; would have sent: {message}")
    return False


# If there's a modules dir (used for Tools menu in ES),
# add a Pharos launch script there if the daemon is in use.
MODULES_DIR = Path("/storage/.config/modules")
MODULE_SCRIPT = MODULES_DIR / "Start Pharos.sh"
MODULE_GAMELIST = MODULES_DIR / "gamelist.xml"
MODULE_IMAGE = MODULES_DIR / "images" / "pharos.svg"
MODULE_ICON_SOURCE = INSTALL_DIR / "pharos.svg"
_MODULE_SCRIPT_TEMPLATE = """#!/bin/bash
# Created by pharos-daemon: launches Pharos from the Tools menu.
source /etc/profile

for launcher in "{ports_dir}/Pharos"*.sh; do
    if [ -f "$launcher" ]; then
        exec /bin/bash "$launcher"
    fi
done
echo "Pharos launcher not found in {ports_dir}" >&2
exit 1
"""

_GAMELIST_ENTRY = """    <game>
        <path>./Start Pharos.sh</path>
        <name>Pharos</name>
        <desc>Pharos is a tool for downloading ports and wine bottles hosted on independent GitHub repositories.</desc>
        <developer>Jeod</developer>
        <publisher>Jeod</publisher>
        <rating>5.0</rating>
        <releasedate>2025</releasedate>
        <genre>Tool</genre>
        <players>1</players>
        <image>./images/pharos.svg</image>
    </game>
"""


def ensure_es_module() -> None:
    """Idempotently install 'Start Pharos.sh' + its gamelist.xml entry into
    the ES modules dir. No-op on CFWs without /storage/.config/modules."""
    if not MODULES_DIR.is_dir():
        return
    try:
        desired = _MODULE_SCRIPT_TEMPLATE.format(ports_dir=INSTALL_DIR.parent)
        try:
            current = MODULE_SCRIPT.read_text("utf-8")
        except OSError:
            current = None
        if current != desired:
            MODULE_SCRIPT.write_text(desired, encoding="utf-8")
            MODULE_SCRIPT.chmod(0o755)
            log("INFO", f"installed ES module {MODULE_SCRIPT}")

        if not MODULE_IMAGE.exists() and MODULE_ICON_SOURCE.exists():
            MODULE_IMAGE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(MODULE_ICON_SOURCE, MODULE_IMAGE)
            log("INFO", f"copied module icon -> {MODULE_IMAGE}")

        if MODULE_GAMELIST.exists():
            xml = MODULE_GAMELIST.read_text("utf-8")
        else:
            xml = '<?xml version="1.0"?>\n<gameList>\n</gameList>\n'
        if "Start Pharos.sh" not in xml and "</gameList>" in xml:
            xml = xml.replace("</gameList>", _GAMELIST_ENTRY + "</gameList>", 1)
            tmp = MODULE_GAMELIST.with_suffix(".tmp")
            tmp.write_text(xml, encoding="utf-8")
            os.replace(tmp, MODULE_GAMELIST)
            log("INFO", f"added Pharos entry to {MODULE_GAMELIST}")
    except OSError as e:
        log("WARN", f"ES module injection failed: {e}")


# ----------------------------------------------------------------------
# Update check
# ----------------------------------------------------------------------
# Transport-level failures (URLError/timeout/OSError) within one run_check
# pass. HTTPError isn't counted - the network worked, the server said no. Lets
# the caller distinguish "nothing changed" from "network was down".
_network_errors_this_pass = 0


def _http_get(url: str, timeout: int = GITHUB_HTTP_TIMEOUT) -> bytes | None:
    """Fetch a URL. 200 -> bytes; 404 -> silent None; other HTTP errors -> WARN
    + None. Transport failures also bump _network_errors_this_pass so
    daemon_loop schedules a retry."""
    global _network_errors_this_pass
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PharosDaemon/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except HTTPError as e:
        if e.code != 404:
            log("WARN", f"http GET {url} -> HTTP {e.code}")
        return None
    except (OSError, HTTPException) as e:
        _network_errors_this_pass += 1
        log("WARN", f"http GET {url} failed: {e}")
        return None


def load_local_manifest() -> tuple[dict[str, str], dict[str, str], dict[str, str], set[str]]:
    """Returns ({name: md5}, {name: title}, {name: repo}, {muted_names}) for
    Pharos-tracked ports. Names are extensionless; `repo` is empty for legacy
    entries; `muted` defaults False."""
    if not MANIFEST_PATH.exists():
        log("INFO", f"manifest not found at {MANIFEST_PATH}")
        return {}, {}, {}, set()
    try:
        data = json.loads(MANIFEST_PATH.read_text("utf-8"))
        md5s: dict[str, str] = {}
        titles: dict[str, str] = {}
        repos: dict[str, str] = {}
        muted: set[str] = set()
        # Bottles have no ports.json to check against
        for entry in data.get("ports") or []:
            name, md5 = (entry.get("name"), entry.get("md5")) if isinstance(entry, dict) else (None, None)
            if not (name and md5 and isinstance(name, str) and isinstance(md5, str)):
                log("INFO", f"manifest entry skipped (missing name/md5): {entry!r}")
                continue
            md5s[name] = md5
            titles[name] = entry.get("title") or name
            repos[name] = entry.get("repo") or ""
            muted_field = entry.get("muted")
            log(
                "INFO",
                f"manifest: name={name!r} md5={md5[:8]} muted={muted_field!r}",
            )
            if muted_field:
                muted.add(name)
        log(
            "INFO",
            f"manifest summary: {len(md5s)} tracked, {len(muted)} muted -> {sorted(muted)}",
        )
        return md5s, titles, repos, muted
    except (OSError, ValueError, AttributeError, TypeError) as e:
        log("WARN", f"manifest parse failed: {e}")
        return {}, {}, {}, set()


def parse_sources() -> list[str]:
    """Returns the repo slugs in sources.json."""
    try:
        return read_sources(SOURCES_PATH, warn=lambda msg: log("WARN", msg))
    except (OSError, ValueError) as e:
        log("WARN", f"Can't read sources.json: {e}")
        return []


def fetch_remote_md5s(slug: str) -> tuple[dict[str, str], dict[str, str]]:
    """Returns ({name: md5}, {name: title}) from a repo's catalog.
    Names stripped of .zip to match the local manifest. Wine bottle repos
    (winecask.json) are out of scope - Pharos handles those itself."""
    for url in catalog_urls(slug):
        raw = _http_get(url)
        if raw is None:
            continue
        try:
            entries = catalog_entries(raw)
        except ValueError as e:
            log("WARN", f"{url}: {e}")
            continue
        md5s: dict[str, str] = {}
        titles: dict[str, str] = {}
        for p in entries:
            md5 = p["source"].get("md5")
            if not (md5 and isinstance(md5, str)):
                continue
            name = os.path.splitext(p["name"])[0]
            md5s[name] = md5
            titles[name] = p["attr"].get("title") or name
        return md5s, titles
    log("INFO", f"no ports.json on {slug}; skipping")
    return {}, {}


def find_outdated(local: dict[str, str], local_repos: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Returns (sorted outdated names, remote-title fallback dict).

    Per-port:
      - local_repos[name] set (a slug): authoritative, only that repo's
        ports.json can mark it outdated.
      - empty (legacy entry): match-any across every sources.json repo but
        PortMaster's, which are newer than those entries; outdated only when no
        repo publishes the local md5.
    """
    repos_in_sources = parse_sources()
    fetched: dict[str, tuple[dict[str, str], dict[str, str]]] = {}

    def remote_for(slug: str) -> tuple[dict[str, str], dict[str, str]]:
        if slug not in fetched:
            fetched[slug] = fetch_remote_md5s(slug)
        return fetched[slug]

    outdated: list[str] = []
    remote_titles: dict[str, str] = {}

    for name, local_md5 in local.items():
        recorded = local_repos.get(name) or ""
        if recorded and "/" in recorded:
            md5s, titles = remote_for(recorded)
            remote_md5 = md5s.get(name)
            if remote_md5 and remote_md5 != local_md5:
                outdated.append(name)
            if titles.get(name):
                remote_titles.setdefault(name, titles[name])
        else:
            seen: set[str] = set()
            for slug in repos_in_sources:
                if is_portmaster(slug):
                    continue
                md5s, titles = remote_for(slug)
                if name in md5s:
                    seen.add(md5s[name])
                    if titles.get(name):
                        remote_titles.setdefault(name, titles[name])
            if seen and local_md5 not in seen:
                outdated.append(name)

    return sorted(outdated), remote_titles


def format_message(outdated: Iterable[str], titles: dict[str, str]) -> str:
    items = list(outdated)
    if len(items) == 1:
        return f"[PHAROS] Update available for {titles.get(items[0], items[0])}"
    return f"[PHAROS] {len(items)} updates available"


# ----------------------------------------------------------------------
# Notify-state dedup (tmpfs-backed: survives in-session restarts, cleared
# on reboot - so reboot re-shows the toast, mid-session respawns stay silent)
# ----------------------------------------------------------------------
def _outdated_hash(items: Iterable[str]) -> str:
    return hashlib.sha256(",".join(sorted(items)).encode("utf-8")).hexdigest()


STATE_FILE = Path("/tmp/pharos-daemon.state")


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, STATE_FILE)
    except OSError as e:
        log("WARN", f"state save failed: {e}")


_state_cache: dict = _load_state()

# ----------------------------------------------------------------------
# Memory trim
# ----------------------------------------------------------------------
# Resolve libc once; malloc_trim lets glibc hand freed arenas back to the OS.
# None on musl / anywhere libc.so.6 isn't loadable - trim degrades to gc only.
try:
    _libc = ctypes.CDLL("libc.so.6")
except OSError:
    _libc = None


def _trim_memory() -> None:
    """Return freed heap to the OS after a check. glibc holds run_check's
    ports.json high-water mark reserved across the long idle that follows, so
    gc.collect() drops the Python objects and malloc_trim releases the arenas."""
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except (AttributeError, OSError):
            pass


# ----------------------------------------------------------------------
# PortMaster's device info
# ----------------------------------------------------------------------
def ensure_device_override() -> None:
    # A PortMaster update rewrites its cache
    try:
        settings = json.loads(SETTINGS_PATH.read_text("utf-8-sig"))
        if settings["override_device_info"] is True:
            set_device_override(
                settings["controlfolder"], os.path.join(os.path.realpath(INSTALL_DIR), "device_override.txt")
            )
    except (FileNotFoundError, KeyError):
        pass  # never turned on
    except (OSError, ValueError, TypeError) as e:
        log("WARN", f"device override: {e}")


# ----------------------------------------------------------------------
# Main check
# ----------------------------------------------------------------------
def run_check() -> tuple[bool, bool]:
    """One check + notify pass. Returns (settled, network_failed).

    settled        - False on notify failure (caller may retry), else True.
    network_failed - True if any HTTP fetch hit a transport error. Independent
                     of settled - caller schedules a retry alarm so updates
                     aren't missed when the boot-time network was down.
    """
    global _network_errors_this_pass
    _network_errors_this_pass = 0

    ensure_es_module()
    ensure_device_override()

    local_md5s, local_titles, local_repos, muted = load_local_manifest()
    if not local_md5s:
        log("INFO", "manifest empty; nothing tracked")
        return True, False

    # Strip muted ports up front - invisible to the rest of the pipeline,
    # including dedup, so unmuting later genuinely re-fires.
    if muted:
        log("INFO", f"{len(muted)} port(s) muted: {sorted(muted)}")
        local_md5s = {n: m for n, m in local_md5s.items() if n not in muted}
        if not local_md5s:
            log("INFO", "all tracked ports muted")
            return True, False

    outdated, remote_titles = find_outdated(local_md5s, local_repos)
    network_failed = _network_errors_this_pass > 0
    if not outdated:
        log("INFO", "no updates" + (" (with network failures)" if network_failed else ""))
        return True, network_failed

    h = _outdated_hash(outdated)
    if _state_cache.get("last_outdated_hash") == h:
        log("INFO", f"{len(outdated)} outdated but state unchanged; skipping notify")
        return True, network_failed

    titles = {**remote_titles, **local_titles}
    cfw = detect_cfw(_log_info)
    msg = format_message(outdated, titles)
    log("INFO", f"notifying ({cfw}): {msg}")

    backoff = RETRY_BACKOFF_INITIAL
    for attempt in range(1, 7):
        if notify(cfw, msg):
            _state_cache["last_outdated_hash"] = h
            _save_state(_state_cache)
            return True, network_failed
        time.sleep(backoff)
        backoff = min(backoff * 2, RETRY_BACKOFF_MAX)
        log("INFO", f"notify retry attempt {attempt}")
    log("ERROR", "all notify retries exhausted")
    return False, network_failed


# ----------------------------------------------------------------------
# Daemon loop + signals
# ----------------------------------------------------------------------
_pending = False  # SIGHUP arrived inside rate-limit window; SIGALRM scheduled for window-end
_retrying = False  # last check hit network errors; SIGALRM scheduled for ~60s retry

# Network-retry interval. Shorter than MIN_FETCH_INTERVAL_S to recover quickly
# from a boot-time network race rather than wait the full rate-limit window.
NETWORK_RETRY_S = 60

# Which primitive backs _wait_for_wake. signal.sigsuspend is absent in
# python:3.11-slim-bullseye, the image the daemon is frozen in, so using it
# raised AttributeError on the first wait and crash-looped. sigwaitinfo /
# sigtimedwait are present and dequeue a blocked signal synchronously, with no
# handler race. If neither exists we degrade to a periodic poll.
_HAVE_SIGWAITINFO = hasattr(signal, "sigwaitinfo")
_HAVE_SIGTIMEDWAIT = hasattr(signal, "sigtimedwait")

# sigtimedwait re-wait quantum / poll-fallback interval.
_WAIT_POLL_S = 3600


def _on_wake(_signum, _frame) -> None:
    """No-op. Wake signals are blocked and consumed synchronously by
    _wait_for_wake, so this never runs. It exists only to give them a
    non-SIG_IGN disposition - a blocked signal set to 'ignore' is discarded
    rather than made pending, so the wait would never see it."""
    # Intentionally empty.


def _on_sigterm(_signum, _frame) -> None:
    log("INFO", "SIGTERM - shutting down")
    sys.exit(0)


def _wait_for_wake(wake_signals: set[int]) -> None:
    """Block until a wake signal (SIGHUP/SIGALRM) arrives, then consume it.

    Blocked in daemon_loop, wake signals queue as pending and are dequeued here
    without invoking a handler - closing the race where a signal lands between a
    'did we wake?' check and the wait. SIGTERM/SIGINT stay unblocked and
    interrupt this call (InterruptedError)."""
    try:
        if _HAVE_SIGWAITINFO:
            signal.sigwaitinfo(wake_signals)
        elif _HAVE_SIGTIMEDWAIT:
            # Re-wait on timeout (None) so this blocks until a real signal.
            while signal.sigtimedwait(wake_signals, _WAIT_POLL_S) is None:
                pass
        else:
            # No synchronous signal-wait on this build. SIGHUP won't wake us
            # promptly, but the loop's periodic re-check still catches updates.
            time.sleep(_WAIT_POLL_S)
    except InterruptedError:
        pass


def _is_our_daemon(pid: int) -> bool:
    """Cross-check that /proc/<pid> is actually a Pharos daemon, not an
    unrelated process the kernel reassigned our old PID to (PID reuse).
    Compares /proc/<pid>/comm against /proc/self/comm to cover renamed binaries
    and PyInstaller temp prefixes. Returns True if /proc isn't usable - keeps
    the conservative "don't start over a live PID" behavior."""
    comm_file = Path(f"/proc/{pid}/comm")
    if not comm_file.exists():
        return True
    try:
        their_comm = comm_file.read_text().strip()
    except OSError:
        return True
    try:
        our_comm = Path("/proc/self/comm").read_text().strip()
    except OSError:
        # Fall back to the literal binary name if /proc/self is unreadable.
        our_comm = "pharos-daemon"
    return their_comm == our_comm


def write_pidfile() -> None:
    if PID_FILE.exists():
        try:
            old = int(PID_FILE.read_text().strip())
            os.kill(old, 0)
            # Process exists; cross-check it's ours before refusing to start
            # (PID reuse could otherwise lock us out forever).
            if _is_our_daemon(old):
                log("ERROR", f"another instance running (pid {old}); exiting")
                sys.exit(1)
            log("INFO", f"pidfile points at pid {old} but /proc shows it's not our daemon; treating as stale")
        except (OSError, ValueError):
            pass  # process gone or pidfile garbage; take over
    PID_FILE.write_text(str(os.getpid()))


def remove_pidfile() -> None:
    try:
        PID_FILE.unlink()
    except OSError:
        pass


def _check() -> bool:
    """Returns network_failed"""
    try:
        return run_check()[1]
    except Exception as e:
        log("ERROR", f"check failed: {type(e).__name__}: {e}")
        return False


def daemon_loop() -> None:
    """Initial check on startup, then idle until a wake signal. Each wake
    re-runs the check, gated by MIN_FETCH_INTERVAL_S; _pending and _retrying
    defer a check that would otherwise be dropped."""
    global _pending, _retrying
    write_pidfile()
    try:
        # These handlers exist only so the wake signals aren't SIG_IGN (and can
        # go pending while blocked); they never run - _wait_for_wake dequeues.
        signal.signal(signal.SIGHUP, _on_wake)
        signal.signal(signal.SIGALRM, _on_wake)
        signal.signal(signal.SIGTERM, _on_sigterm)
        signal.signal(signal.SIGINT, _on_sigterm)

        # Block wake signals so _wait_for_wake can dequeue them synchronously.
        # SIGTERM/SIGINT stay unblocked so they always interrupt promptly.
        wake_signals = {signal.SIGHUP, signal.SIGALRM}
        signal.pthread_sigmask(signal.SIG_BLOCK, wake_signals)

        # Initial check: boot-time notification once ES is up. last_fetch stays
        # 0.0 so the first post-boot SIGHUP isn't rate-limited against it - that
        # SIGHUP is the user's first retry if the boot check ran pre-network.
        last_fetch = 0.0
        network_failed = _check()
        _trim_memory()
        if network_failed:
            log("INFO", f"boot check hit network errors; scheduling retry in {NETWORK_RETRY_S}s")
            signal.alarm(NETWORK_RETRY_S)
            _retrying = True

        while True:
            _wait_for_wake(wake_signals)

            now = time.time()
            since = now - last_fetch
            if since < MIN_FETCH_INTERVAL_S:
                remaining = MIN_FETCH_INTERVAL_S - since
                if not _pending:
                    _pending = True
                    # +1s slack so the alarm fires just past the window edge.
                    signal.alarm(int(remaining) + 1)
                    log("INFO", f"woken; rate-limited ({int(remaining)}s remaining); deferred")
                else:
                    log("INFO", f"woken; rate-limited ({int(remaining)}s remaining); already deferred")
                continue

            if _pending:
                log("INFO", "woken (deferred check after rate-limit window)")
            elif _retrying:
                log("INFO", "woken (network-failure retry)")
            else:
                log("INFO", "woken (SIGHUP)")
            _pending = False
            _retrying = False
            signal.alarm(0)

            network_failed = _check()
            _trim_memory()
            if network_failed:
                log("INFO", f"network failure during check; scheduling retry in {NETWORK_RETRY_S}s")
                signal.alarm(NETWORK_RETRY_S)
                _retrying = True
            else:
                last_fetch = time.time()
    finally:
        remove_pidfile()


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def main() -> int:
    global _verbose
    p = argparse.ArgumentParser(description="Pharos update-check daemon.")
    p.add_argument("--once", action="store_true", help="run one check and exit")
    p.add_argument(
        "--install-module",
        action="store_true",
        help="restore the ES Tools entry and exit (no network)",
    )
    p.add_argument("--verbose", action="store_true", help="echo logs to stderr")
    args = p.parse_args()
    _verbose = args.verbose

    # pharos-module.service runs this with ES ordered after it, so keep it to
    # local file writes - boot must never wait on the network here.
    if args.install_module:
        log("INFO", f"pharos-daemon --install-module (pid {os.getpid()})")
        ensure_es_module()
        return 0

    if args.once:
        log("INFO", f"pharos-daemon --once (pid {os.getpid()})")
        _, network_failed = run_check()
        if network_failed:
            log("WARN", "--once detected network failures; daemon mode would schedule a retry")
        return 0

    log("INFO", f"pharos-daemon start (pid {os.getpid()}, install_dir {INSTALL_DIR})")

    try:
        daemon_loop()
    except KeyboardInterrupt:
        log("INFO", "interrupted; shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
