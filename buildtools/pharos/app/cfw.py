"""
CFW detection, shared by Pharos and the daemon
"""
import functools
import os
import shutil
from pathlib import Path

# CFW_NAME values (case-insensitive) PortMaster's device_info.txt may export,
# grouped by family: every member of a tuple shares one install code path.
_LIBREELEC_FAMILY = ("rocknix", "amberelec", "jelos", "emuelec", "unofficialos")
_BATOCERA_FAMILY = ("batocera", "knulli", "reglinux")
_KNOWN_UNSUPPORTED = (
    "muos", "arkos", "retrodeck", "trimui", "miyoo", "spruce", "thera", "retrooz",
)


# A command, then folders. install() creates the ES scripts folder.
_PREREQS = {
    "systemd": ("systemctl", "/storage/.config/system.d", "/storage/.config/emulationstation"),
    "userland": ("batocera-settings-set", "/userdata/system/services", "/userdata/system/configs/emulationstation"),
}


def _missing_prereqs(bucket: str) -> list[str]:
    """What the bucket needs that isn't on disk - env labels can be
    wrong, so confirm capability before trusting them."""
    command, *folders = _PREREQS[bucket]
    missing = [] if shutil.which(command) else [command]
    return missing + [f for f in folders if not Path(f).exists()]


@functools.lru_cache(maxsize=1)
def detect_cfw(log) -> str:
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
        log(f"CFW detect: env={env_name!r} (known unsupported)")
        return env_name

    if bucket is None:
        if Path("/run/muos").exists() or Path("/opt/muos").exists():
            log(f"CFW detect: env={env_name!r} fs=muos")
            return "muos"
        if Path("/userdata/system").exists():
            bucket = "userland"
        elif Path("/storage/.config/emulationstation").exists():
            bucket = "systemd"

    if bucket is None:
        log(f"CFW detect: env={env_name!r} fs=<no markers> -> unknown")
        return "unknown"

    missing = _missing_prereqs(bucket)
    if missing:
        log(
            f"CFW detect: env={env_name!r} bucket={bucket!r} "
            f"but missing {', '.join(missing)}; downgrading to 'unknown'"
        )
        return "unknown"

    log(f"CFW detect: env={env_name!r} bucket={bucket!r} verified")
    return bucket
