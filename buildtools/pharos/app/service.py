"""
Pharos Service - install/uninstall the background update-checker daemon.

Each supported bucket gets its own autostart hook (systemd unit / userland
service script) plus an ES game-end script that SIGHUPs the daemon so users
see fresh notifications when ES regains the foreground.

MuOS is detected but unsupported: it has no ES game-end hook dir, and
patching launch.sh is fragile across MuOS updates. MuOS users run Pharos's
UI directly.

The daemon is a separate PyInstaller --onefile binary embedded in the Pharos
binary via --add-binary; at runtime it lives in BASE_PATH (sys._MEIPASS).
install() copies it out to INSTALL_DIR as a persistent executable - so the
port zip ships only the Pharos binary, no loose scripts.

refresh_if_stale() runs once on Pharos startup: if the bundled daemon hash
differs from the extracted on-disk copy (i.e. a Pharos self-update brought
new daemon code), it swaps the file and restarts the service - so the daemon
follows Pharos updates automatically.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from config import BASE_PATH, INSTALL_DIR

DAEMON_NAME = "pharos-daemon"

# Shared "unsupported CFW" wording, used by status_text() and install/uninstall.
UNSUPPORTED_MSG = "CFW '{cfw}' not supported"

# Bundled binary (read-only, inside _MEIPASS) and on-disk location after install.
DAEMON_BUNDLED_PATH = Path(BASE_PATH) / DAEMON_NAME
DAEMON_EXTRACTED_PATH = Path(INSTALL_DIR) / DAEMON_NAME

# Per-port mute is a "muted" boolean on each manifest entry; the daemon reads
# the same manifest the Pharos UI mutates here.
MANIFEST_PATH = Path(INSTALL_DIR) / "resources" / "manifest.json"


def toggle_muted_port(name: str) -> bool | None:
    """Flip the "muted" flag on the manifest entry matching `name`. Returns
    the new state, or None if no matching entry exists. Atomic write via
    tmp + rename so a partial save can't corrupt the manifest."""
    if not MANIFEST_PATH.exists():
        return None
    try:
        data = json.loads(MANIFEST_PATH.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    new_state: bool | None = None
    for key in ("ports", "bottles"):
        for entry in data.get(key, []) or []:
            if entry.get("name") == name:
                new_state = not bool(entry.get("muted"))
                entry["muted"] = new_state
                break
        if new_state is not None:
            break

    if new_state is None:
        return None

    tmp = MANIFEST_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, MANIFEST_PATH)
    return new_state

# Per-CFW autostart artifact paths.
SYSTEMD_UNIT_PATH = Path("/storage/.config/system.d/pharos-daemon.service")
SYSTEMD_MODULE_UNIT_PATH = Path("/storage/.config/system.d/pharos-module.service")
USERLAND_SERVICE_PATH = Path("/userdata/system/services/pharos-daemon")

# ES event-script paths (ROCKNIX + Batocera-family).
SYSTEMD_ES_SCRIPT = Path("/storage/.config/emulationstation/scripts/game-end/pharos-check")
USERLAND_ES_SCRIPT = Path("/userdata/system/configs/emulationstation/scripts/game-end/pharos-check")

DAEMON_PID_FILE = Path(INSTALL_DIR) / "resources" / "daemon.pid"


# ----------------------------------------------------------------------
# CFW detection
# ----------------------------------------------------------------------
# CFW_NAME values (case-insensitive) PortMaster's device_info.txt may export,
# grouped by family: every member of a tuple shares one install code path.
_LIBREELEC_FAMILY = ("rocknix", "amberelec", "jelos", "emuelec", "unofficialos")
_BATOCERA_FAMILY = ("batocera", "knulli", "reglinux")
_KNOWN_UNSUPPORTED = (
    "muos", "arkos", "retrodeck", "trimui", "miyoo", "thera", "retrooz",
)


def _verify_systemd_capable() -> bool:
    """Verify the 'systemd' bucket's prereqs on disk (systemctl, the
    /storage user-systemd dir, the ES scripts dir) - env labels can be
    wrong, so confirm capability before trusting them."""
    return (
        shutil.which("systemctl") is not None
        and Path("/storage/.config/system.d").exists()
        and Path("/storage/.config/emulationstation/scripts").exists()
    )


def _verify_userland_capable() -> bool:
    """Verify the 'userland' bucket's prereqs: batocera-settings-set,
    the /userdata services dir, and the ES scripts dir."""
    return (
        shutil.which("batocera-settings-set") is not None
        and Path("/userdata/system/services").exists()
        and Path("/userdata/system/configs/emulationstation/scripts").exists()
    )


@functools.lru_cache(maxsize=1)
def detect_cfw() -> str:
    """Returns 'systemd' / 'userland' / 'muos' / 'unknown' (or a
    known-but-unsupported lowercase CFW name, so the 'not supported'
    message names what we saw rather than just 'unknown').

    Buckets name the install mechanism, not a CFW: 'systemd' = the
    LibreELEC family (ROCKNIX, AmberELEC, JELOS, EmuELEC, UnofficialOS),
    'userland' = the Batocera family (Knulli, Batocera, REGLinux).

    $CFW_NAME first, then filesystem markers for the init-launched daemon
    that inherits no env, then a capability check that downgrades a bucket
    whose prereqs aren't on disk."""
    env_name = (os.environ.get("CFW_NAME") or "").lower()
    bucket: str | None = None

    if env_name in _LIBREELEC_FAMILY:
        bucket = "systemd"
    elif env_name in _BATOCERA_FAMILY:
        bucket = "userland"
    elif env_name in _KNOWN_UNSUPPORTED:
        print(f"[Service] CFW detect: env={env_name!r} (known unsupported)")
        return env_name

    if bucket is None:
        if Path("/run/muos").exists() or Path("/opt/muos").exists():
            print(f"[Service] CFW detect: env={env_name!r} fs=muos")
            return "muos"
        if Path("/userdata/system").exists():
            bucket = "userland"
        elif Path("/storage/.config/emulationstation").exists():
            bucket = "systemd"

    if bucket is None:
        print(f"[Service] CFW detect: env={env_name!r} fs=<no markers> -> unknown")
        return "unknown"

    verifier = _verify_systemd_capable if bucket == "systemd" else _verify_userland_capable
    if not verifier():
        print(
            f"[Service] CFW detect: env={env_name!r} bucket={bucket!r} "
            "but capability check failed; downgrading to 'unknown'"
        )
        return "unknown"

    print(f"[Service] CFW detect: env={env_name!r} bucket={bucket!r} verified")
    return bucket


# ----------------------------------------------------------------------
# Templates
# ----------------------------------------------------------------------
def _systemd_unit(daemon_path: Path) -> str:
    # TMPDIR points PyInstaller's --onefile extraction at disk, not /tmp: /tmp
    # is tmpfs (RAM) on these CFWs, so the ~15 MB extraction would stay pinned
    # in memory. ExecStartPre recreates the dir (cleanup/uninstall wipes it).
    # After= the ES units since ES serves the :1234 endpoint notify posts to.
    # essway on current ROCKNIX, emustation on older; naming a dead unit is a no-op.
    tmpdir = daemon_path.parent / "tmp"
    return f"""[Unit]
Description=Pharos update checker daemon
After=essway.service emustation.service
Wants=network-online.target

[Service]
Type=simple
Environment=TMPDIR={tmpdir}
ExecStartPre=/bin/sh -c 'mkdir -p "{tmpdir}"'
ExecStart={daemon_path}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""


def _systemd_module_unit(daemon_path: Path) -> str:
    """The ES Tools entry, as its own unit."""
    # Split from the daemon since the ordering is reversed: ROCKNIX's autostart
    # rsyncs --delete over /storage/.config/modules each boot, ES reads the
    # gamelist once, and this has to land between them. oneshot so Before= waits.
    tmpdir = daemon_path.parent / "tmp"
    return f"""[Unit]
Description=Pharos ES Tools entry
After=rocknix-autostart.service jelos-autostart.service autostart.service
Before=essway.service emustation.service

[Service]
Type=oneshot
RemainAfterExit=yes
Environment=TMPDIR={tmpdir}
ExecStartPre=/bin/sh -c 'mkdir -p "{tmpdir}"'
ExecStart={daemon_path} --install-module
TimeoutStartSec=30

[Install]
WantedBy=default.target
"""


def _userland_service(daemon_path: Path) -> str:
    # Extraction to disk, not tmpfs - see _systemd_unit for the TMPDIR rationale.
    tmpdir = daemon_path.parent / "tmp"
    return f"""#!/bin/sh
# Pharos update checker daemon - Batocera-style user service.
# Batocera's S99userservices runs this with start/stop arg.
#
# Includes a supervisor loop so a daemon crash respawns automatically (the
# systemd bucket gets this for free via Restart=on-failure; the userland
# bucket has to do it itself). The supervisor traps SIGTERM and forwards
# it to the daemon child so 'service stop' kills both cleanly.
PIDFILE=/var/run/pharos-daemon.pid
export TMPDIR="{tmpdir}"
mkdir -p "{tmpdir}" 2>/dev/null

case "$1" in
    start)
        if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
            exit 0
        fi
        # Backgrounded subshell = supervisor. trap kills the daemon child
        # before exiting so 'stop' doesn't orphan it. 5s sleep between
        # respawns keeps a crash loop from burning CPU.
        (
            trap 'kill $child 2>/dev/null; exit 0' TERM INT
            while true; do
                {daemon_path} >>/var/log/pharos-daemon.log 2>&1 &
                child=$!
                wait $child
                sleep 5
            done
        ) &
        echo $! > "$PIDFILE"
        ;;
    stop)
        [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null
        rm -f "$PIDFILE"
        ;;
    *)
        echo "usage: $0 start|stop" >&2
        exit 1
        ;;
esac
"""


def _es_event_script() -> str:
    pid_file = DAEMON_PID_FILE
    return f"""#!/bin/sh
# Pharos: nudge the daemon to re-check whenever ES regains the foreground.
PID_FILE={pid_file}
[ -f "$PID_FILE" ] && kill -HUP "$(cat "$PID_FILE")" 2>/dev/null
exit 0
"""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _safe_run(cmd: list[str]) -> tuple[int, str]:
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, check=False
        )
        return out.returncode, (out.stdout + out.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def _kill_pid_file(pid_file: Path) -> None:
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    try:
        pid_file.unlink()
    except OSError:
        pass


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(64 * 1024), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _daemon_alive(pid_file: Path, timeout: float = 5.0) -> bool:
    """Poll the pidfile for up to `timeout`s and verify the recorded pid is
    alive - used after a restart to confirm the new daemon came up. Tolerates
    the window where the old daemon's SIGTERM cleanup has removed the pidfile
    before the new one writes its own."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # liveness probe
            return True
        except (OSError, ValueError, FileNotFoundError):
            time.sleep(0.2)
    return False


def _cleanup_runtime_files() -> None:
    """Remove pid / state / log files left by the daemon, so an uninstall
    after a wedged or already-dead daemon leaves no trace."""
    for f in (
        Path(INSTALL_DIR) / "resources" / "daemon.pid",
        Path(INSTALL_DIR) / "resources" / "daemon.state.json",
        Path(INSTALL_DIR) / "logs" / "daemon.log",
        Path(INSTALL_DIR) / "logs" / "daemon.log.1",
    ):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass
    shutil.rmtree(Path(INSTALL_DIR) / "tmp", ignore_errors=True)


# ----------------------------------------------------------------------
# Service class
# ----------------------------------------------------------------------
class Service:
    def __init__(self) -> None:
        self.cfw = detect_cfw()
        # Persistent path - survives Pharos exit, _MEIPASS cleanup, and reboots.
        self.daemon_path = DAEMON_EXTRACTED_PATH

    def _extract_daemon(self) -> bool:
        """Copy the bundled daemon out of _MEIPASS to a persistent location.
        Idempotent on hash, not just existence - a truncated, corrupted, or
        stale-version extraction is detected and replaced. Returns True on
        success (fresh copy, replacement, or hash-matching no-op)."""
        if not DAEMON_BUNDLED_PATH.exists():
            print(f"[Service] ERROR: bundled daemon missing at {DAEMON_BUNDLED_PATH}")
            return False
        if (
            DAEMON_EXTRACTED_PATH.exists()
            and _hash_file(DAEMON_EXTRACTED_PATH) == _hash_file(DAEMON_BUNDLED_PATH)
        ):
            print(f"[Service] daemon already at {DAEMON_EXTRACTED_PATH} (hash matches); skipping extract")
            return True
        try:
            shutil.copy2(DAEMON_BUNDLED_PATH, DAEMON_EXTRACTED_PATH)
            DAEMON_EXTRACTED_PATH.chmod(0o755)
            print(f"[Service] extracted daemon: {DAEMON_BUNDLED_PATH} -> {DAEMON_EXTRACTED_PATH}")
            return True
        except OSError as e:
            print(f"[Service] ERROR: extract failed: {e}")
            return False

    @property
    def supported(self) -> bool:
        return self.cfw in ("systemd", "userland")

    @property
    def installed(self) -> bool:
        """Detect by the presence of the per-CFW autostart artifact."""
        if self.cfw == "systemd":
            return SYSTEMD_UNIT_PATH.exists()
        if self.cfw == "userland":
            return USERLAND_SERVICE_PATH.exists()
        return False

    def status_text(self) -> str:
        if not self.supported:
            return UNSUPPORTED_MSG.format(cfw=self._cfw_display_name())
        return "Installed" if self.installed else "Not installed"

    def _unsupported_result(self) -> tuple[bool, str]:
        return False, UNSUPPORTED_MSG.format(cfw=self._cfw_display_name())

    def _cfw_display_name(self) -> str:
        """Friendly CFW name for user-facing strings: $CFW_NAME preserves
        casing ('AmberELEC', 'muOS'); falls back to the lowercase dispatch
        key when env is unset (daemon path, Pharos outside PortMaster)."""
        return os.environ.get("CFW_NAME") or self.cfw

    # ------------------------------------------------------------------
    # Auto-refresh on Pharos update
    # ------------------------------------------------------------------
    def _restart_service(self) -> None:
        """Bucket-specific service restart, centralized for refresh_if_stale."""
        if self.cfw == "systemd":
            _safe_run(["systemctl", "restart", "pharos-daemon.service"])
        elif self.cfw == "userland":
            _safe_run([str(USERLAND_SERVICE_PATH), "stop"])
            _safe_run([str(USERLAND_SERVICE_PATH), "start"])

    def _refresh_launch_config(self) -> None:
        """Re-emit the per-CFW autostart artifact so template changes reach
        existing installs, not just the swapped binary."""
        (self.daemon_path.parent / "tmp").mkdir(parents=True, exist_ok=True)
        if self.cfw == "systemd":
            _write_executable(SYSTEMD_UNIT_PATH, _systemd_unit(self.daemon_path))
            _write_executable(
                SYSTEMD_MODULE_UNIT_PATH, _systemd_module_unit(self.daemon_path)
            )
            _safe_run(["systemctl", "daemon-reload"])
            # Pre-1.2.1 installs have no module unit; enable it on refresh so
            # updaters get the Tools fix without a manual reinstall.
            _safe_run(["systemctl", "enable", "pharos-module.service"])
        elif self.cfw == "userland":
            _write_executable(USERLAND_SERVICE_PATH, _userland_service(self.daemon_path))

    def refresh_if_stale(self) -> bool:
        """If the bundled daemon differs from the extracted on-disk copy,
        swap it in and restart the service, verifying the new daemon starts
        and rolling back to the previous binary if it doesn't. Returns True if
        a refresh happened (including a successful rollback). Called once on
        Pharos startup so a Pharos self-update brings the daemon with it."""
        if not self.installed:
            return False
        if not DAEMON_BUNDLED_PATH.exists() or not DAEMON_EXTRACTED_PATH.exists():
            return False
        if _hash_file(DAEMON_BUNDLED_PATH) == _hash_file(DAEMON_EXTRACTED_PATH):
            return False

        # .new = staged candidate; .bak = old binary held for rollback.
        new_path = DAEMON_EXTRACTED_PATH.with_suffix(".new")
        bak_path = DAEMON_EXTRACTED_PATH.with_suffix(".bak")
        try:
            shutil.copy2(DAEMON_BUNDLED_PATH, new_path)
            new_path.chmod(0o755)
        except OSError as e:
            print(f"[Service] refresh: staging failed: {e}")
            new_path.unlink(missing_ok=True)
            return False

        # Swap: move old aside, move new into place. A failed second rename
        # still leaves .bak as a recovery anchor.
        try:
            os.replace(DAEMON_EXTRACTED_PATH, bak_path)
            os.replace(new_path, DAEMON_EXTRACTED_PATH)
        except OSError as e:
            print(f"[Service] refresh: swap failed: {e}; attempting to restore")
            # If the first replace succeeded, restore .bak; else original stands.
            if bak_path.exists() and not DAEMON_EXTRACTED_PATH.exists():
                try:
                    os.replace(bak_path, DAEMON_EXTRACTED_PATH)
                except OSError:
                    pass
            new_path.unlink(missing_ok=True)
            bak_path.unlink(missing_ok=True)
            return False

        print(f"[Service] refresh: extracted -> {DAEMON_EXTRACTED_PATH} (old saved at {bak_path})")
        # Update the launch config too, so the restart adopts template changes.
        self._refresh_launch_config()
        self._restart_service()

        # Verify the new daemon starts; roll back if not.
        if _daemon_alive(DAEMON_PID_FILE, timeout=5.0):
            bak_path.unlink(missing_ok=True)
            print("[Service] refresh: new daemon verified alive; backup discarded")
            return True

        print("[Service] refresh: new daemon failed to start; rolling back to previous binary")
        try:
            os.replace(bak_path, DAEMON_EXTRACTED_PATH)
        except OSError as e:
            print(f"[Service] refresh: rollback move failed: {e}; daemon offline until next install")
            return False

        self._restart_service()
        if _daemon_alive(DAEMON_PID_FILE, timeout=5.0):
            print("[Service] refresh: rollback successful; running on previous binary")
        else:
            print("[Service] refresh: rollback restart did not bring daemon back; manual intervention needed")
        return True

    # ------------------------------------------------------------------
    # Install / uninstall - per-CFW dispatch
    # ------------------------------------------------------------------
    def install(self) -> tuple[bool, str]:
        if not self.supported:
            return self._unsupported_result()
        if not self._extract_daemon():
            return False, f"could not extract daemon to {self.daemon_path}"
        try:
            if self.cfw == "systemd":
                return self._install_systemd()
            if self.cfw == "userland":
                return self._install_userland()
        except OSError as e:
            return False, f"install failed: {e}"
        return self._unsupported_result()

    def uninstall(self) -> tuple[bool, str]:
        if not self.supported:
            return self._unsupported_result()
        try:
            if self.cfw == "systemd":
                return self._uninstall_systemd()
            if self.cfw == "userland":
                return self._uninstall_userland()
        except OSError as e:
            return False, f"uninstall failed: {e}"
        return self._unsupported_result()

    # ---- systemd bucket (LibreELEC family) --------------------------
    def _install_systemd(self) -> tuple[bool, str]:
        # Kill any stale daemon + state files whose pidfile would block the new
        # one from starting (e.g. a manual Pharos update left the old daemon up).
        rc, msg = _safe_run(["systemctl", "stop", "pharos-daemon.service"])
        print(f"[Service] pre-install stop (rc={rc}) {msg}")
        _cleanup_runtime_files()
        print("[Service] cleaned stale runtime files")

        print(f"[Service] writing systemd unit -> {SYSTEMD_UNIT_PATH}")
        _write_executable(SYSTEMD_UNIT_PATH, _systemd_unit(self.daemon_path))
        print(f"[Service] writing module unit -> {SYSTEMD_MODULE_UNIT_PATH}")
        _write_executable(
            SYSTEMD_MODULE_UNIT_PATH, _systemd_module_unit(self.daemon_path)
        )
        rc, msg = _safe_run(["systemctl", "daemon-reload"])
        print(f"[Service] systemctl daemon-reload (rc={rc}) {msg}")
        rc, msg = _safe_run(["systemctl", "enable", "pharos-daemon.service"])
        print(f"[Service] systemctl enable (rc={rc}) {msg}")
        rc, msg = _safe_run(["systemctl", "enable", "pharos-module.service"])
        print(f"[Service] systemctl enable module (rc={rc}) {msg}")
        # Run it now so the Tools entry appears without waiting for a reboot.
        rc, msg = _safe_run(["systemctl", "start", "pharos-module.service"])
        print(f"[Service] systemctl start module (rc={rc}) {msg}")
        rc, msg = _safe_run(["systemctl", "start", "pharos-daemon.service"])
        print(f"[Service] systemctl start (rc={rc}) {msg}")
        if rc != 0:
            return False, f"systemctl start failed: {msg}"
        print(f"[Service] writing ES event script -> {SYSTEMD_ES_SCRIPT}")
        _write_executable(SYSTEMD_ES_SCRIPT, _es_event_script())
        return True, "Installed (systemd unit enabled + ES hook)"

    def _uninstall_systemd(self) -> tuple[bool, str]:
        for unit in ("pharos-daemon.service", "pharos-module.service"):
            rc, msg = _safe_run(["systemctl", "stop", unit])
            print(f"[Service] systemctl stop {unit} (rc={rc}) {msg}")
            rc, msg = _safe_run(["systemctl", "disable", unit])
            print(f"[Service] systemctl disable {unit} (rc={rc}) {msg}")
        for path in (SYSTEMD_UNIT_PATH, SYSTEMD_MODULE_UNIT_PATH):
            existed = path.exists()
            path.unlink(missing_ok=True)
            print(f"[Service] removed unit file {path} (existed={existed})")
        existed = SYSTEMD_ES_SCRIPT.exists()
        SYSTEMD_ES_SCRIPT.unlink(missing_ok=True)
        print(f"[Service] removed ES script {SYSTEMD_ES_SCRIPT} (existed={existed})")
        _safe_run(["systemctl", "daemon-reload"])
        existed = DAEMON_EXTRACTED_PATH.exists()
        DAEMON_EXTRACTED_PATH.unlink(missing_ok=True)
        print(f"[Service] removed daemon binary {DAEMON_EXTRACTED_PATH} (existed={existed})")
        _cleanup_runtime_files()
        print("[Service] cleaned up runtime files (pid/state/log)")
        return True, "Uninstalled"

    # ---- userland bucket (Batocera-family user-service) -------------
    def _install_userland(self) -> tuple[bool, str]:
        # Stop any stale daemon + clear pid/state files first.
        if USERLAND_SERVICE_PATH.exists():
            _safe_run([str(USERLAND_SERVICE_PATH), "stop"])
        _kill_pid_file(Path("/var/run/pharos-daemon.pid"))
        _cleanup_runtime_files()
        print("[Service] cleaned stale runtime files")

        _write_executable(USERLAND_SERVICE_PATH, _userland_service(self.daemon_path))
        _safe_run([
            "batocera-settings-set", "system.services.pharos-daemon", "enabled"
        ])
        # Start it now too, so the user doesn't have to reboot.
        _safe_run([str(USERLAND_SERVICE_PATH), "start"])
        _write_executable(USERLAND_ES_SCRIPT, _es_event_script())
        return True, "Installed (Batocera service registered + ES hook)"

    def _uninstall_userland(self) -> tuple[bool, str]:
        if USERLAND_SERVICE_PATH.exists():
            _safe_run([str(USERLAND_SERVICE_PATH), "stop"])
        _safe_run([
            "batocera-settings-set", "system.services.pharos-daemon", "disabled"
        ])
        USERLAND_SERVICE_PATH.unlink(missing_ok=True)
        USERLAND_ES_SCRIPT.unlink(missing_ok=True)
        _kill_pid_file(Path("/var/run/pharos-daemon.pid"))
        DAEMON_EXTRACTED_PATH.unlink(missing_ok=True)
        _cleanup_runtime_files()
        return True, "Uninstalled"

