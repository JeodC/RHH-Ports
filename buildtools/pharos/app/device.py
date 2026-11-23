"""
Device info and port compatibility
"""

import ctypes
import os
import platform
import re
import shutil
import time
from math import gcd
from pathlib import Path
from typing import List

from autoinstall import PORTS_DIR
from config import Port
from strings import UI_REQS, UI_STRINGS

ARMHF_LOADER = "/lib/ld-linux-armhf.so.3"
DISK_REFRESH = 5  # seconds

# REQS_MAP in buildtools/generate_pm_catalog.py
REQ_ALIASES = {"!lowpower": "power"}
ASPECTS = {"1:1": 1, "4:3": 4 / 3, "3:2": 3 / 2, "16:9": 16 / 9}
SCREEN_CAPS = re.compile(r"\d+x\d+|\d+:\d+|hires|lowres|wide|square")

LOW_POWER_CPUS = ("rk3326", "px30")
NOT_ULTRA_CPUS = LOW_POWER_CPUS + ("h700", "a133", "a527", "sun50iw9", "sun50iw10")
# Older PortMaster versions don't report these
ASSUMED_CAPS = {"opengl", "vulkan", "touch", "rumble", "analog_triggers", "restore"}


def _portmaster(name: str) -> str:
    value = os.environ.get(name, "").strip()
    return "" if value.lower() in ("unknown", "none") else value


def _reported(name: str) -> str:
    # device_override.txt keeps the old value
    return os.environ.get(f"PM_{name}", "").strip() or _portmaster(name)


def _read(path: str) -> str:
    try:
        return Path(path).read_text("utf-8", "replace").strip("\0\n ")
    except OSError:
        return ""


def _libc_version() -> str:
    try:
        version = ctypes.CDLL(None).gnu_get_libc_version
    except (OSError, AttributeError, TypeError):
        return ""
    version.restype = ctypes.c_char_p
    return version().decode()


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text))


def _screen_caps(w: int, h: int) -> set[str]:
    caps = {f"{w}x{h}", _aspect(w, h)}
    caps.update(name for name, ratio in ASPECTS.items() if abs(w / h - ratio) < 0.02)
    if w >= 960 or h >= 720:
        caps.add("hires")
    elif w < 640 or h < 480:
        caps.add("lowres")
    if w / h >= 1.5:
        caps.add("wide")
    elif w / h <= 1.25:
        caps.add("square")
    return caps


def _aspect(w: int, h: int) -> str:
    return f"{w // gcd(w, h)}:{h // gcd(w, h)}"


class Device:
    def __init__(self) -> None:
        self.cfw = _portmaster("CFW_NAME")
        self.arch = _portmaster("DEVICE_ARCH") or platform.machine()
        self.armhf = os.path.exists(ARMHF_LOADER)
        self.cpu = _portmaster("DEVICE_CPU") or self._soc()
        self.glibc = _libc_version()
        self._glibc = _version(self.glibc)
        self.ram_gb = self._ram_gb()
        self.sticks = _portmaster("ANALOG_STICKS")
        self.size = (0, 0)
        self.refresh_rate = 0
        self.caps: frozenset[str] = frozenset()  # never changed in place
        self._disk = (None, 0.0)  # usage, time

    @staticmethod
    def _soc() -> str:
        compatible = _read("/proc/device-tree/compatible").split("\0")
        return compatible[min(1, len(compatible) - 1)].partition(",")[2]

    @staticmethod
    def _ram_gb() -> int:
        if _portmaster("DEVICE_RAM").isdigit():
            return int(_portmaster("DEVICE_RAM"))
        total = re.search(r"MemTotal:\s+(\d+)", _read("/proc/meminfo"))
        # MemTotal leaves out reserved memory
        return round(int(total.group(1)) / 1024**2 * 1.1) if total else 0

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------
    def set_display(self, w: int, h: int, refresh_rate: int) -> None:
        # Portrait panels are mounted sideways
        self.size = (max(w, h), min(w, h))
        self.refresh_rate = refresh_rate
        self.caps = frozenset(self._capabilities())
        self._log()

    def _capabilities(self) -> set[str]:
        reported = set(_portmaster("DEVICE_CAPABILITIES").lower().split())
        caps = {c for c in reported if not SCREEN_CAPS.fullmatch(c) and c != "armhf"} or self._fallback_caps()
        caps |= _screen_caps(*self.size)
        caps.add(self.arch)
        if self.armhf:
            caps.add("armhf")
        # For reqs like !trimui
        if self.cfw:
            caps |= {self.cfw.lower(), self.cfw.lower().split()[0]}
        return caps

    def _fallback_caps(self) -> set[str]:
        cpu = self.cpu.lower()
        caps = set(ASSUMED_CAPS)
        caps.update(f"{gb}gb" for gb in (1, 2, 4, 8, 16, 32) if self.ram_gb >= gb or not self.ram_gb)
        caps.update(f"analog_{n}" for n in range(int(self.sticks) + 1 if self.sticks.isdigit() else 3))
        if not any(c in cpu for c in LOW_POWER_CPUS):
            caps.add("power")
        if self.ram_gb >= 4 and not any(c in cpu for c in NOT_ULTRA_CPUS):
            caps.add("ultra")
        return caps

    def unmet(self, port: Port) -> List[str]:
        out = []
        if port.arch and not any(a.lower() in self.caps for a in port.arch):
            out.append(UI_STRINGS["OR"].join(port.arch))
        if self._glibc and _version(port.min_glibc) > self._glibc:
            out.append(UI_REQS["glibc"].format(version=port.min_glibc))
        for req in port.reqs:
            req = REQ_ALIASES.get(req.lower(), req.lower())
            names = [n for n in req.lstrip("!").split("|") if n]
            if names and any(n in self.caps for n in names) == req.startswith("!"):
                out.append(self._req_text(req))
        return out

    @staticmethod
    def _req_text(req: str) -> str:
        if re.fullmatch(r"\d+gb", req):
            return UI_REQS["ram"].format(gb=req[:-2])
        if req not in UI_REQS and req.startswith("!"):
            return UI_REQS["not"].format(name=req[1:])
        return UI_REQS.get(req) or req.replace("|", UI_STRINGS["OR"])

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------
    def _differences(self) -> dict[str, str]:
        reported = {
            "DEVICE_SCREEN": "x".join(filter(None, (_reported("DISPLAY_WIDTH"), _reported("DISPLAY_HEIGHT")))),
            "DEVICE_ARMHF": {"Y": UI_STRINGS["YES"], "N": UI_STRINGS["NO"]}.get(_reported("DEVICE_HAS_ARMHF"), ""),
            "DEVICE_GLIBC": re.sub(r"^(\d)(\d+)$", r"\1.\2", _portmaster("CFW_GLIBC")),
        }
        measured = {
            "DEVICE_SCREEN": "{}x{}".format(*self.size),
            "DEVICE_ARMHF": UI_STRINGS["YES" if self.armhf else "NO"],
            "DEVICE_GLIBC": self.glibc,
        }
        return {k: v for k, v in reported.items() if v and measured[k] and v != measured[k]}

    def _log(self) -> None:
        print(f"[DEVICE] {'; '.join(f'{key}: {value}' for key, value in self._values().items())}")
        print(f"[DEVICE] Capabilities: {' '.join(sorted(self.caps))}")
        for key, value in self._differences().items():
            print(f"[DEVICE] PortMaster has {key} {value}")

    def rows(self) -> List[tuple[str, str]]:
        return [(UI_STRINGS[key], value) for key, value in self._values().items()]

    def _values(self) -> dict[str, str]:
        differences = self._differences()
        values = {
            "DEVICE_CFW": f"{self.cfw} {_portmaster('CFW_VERSION')}",
            "DEVICE_NAME": _portmaster("DEVICE_NAME") or _read("/proc/device-tree/model"),
            "DEVICE_CPU": f"{self.cpu} ({self.arch})",
            "DEVICE_ARMHF": UI_STRINGS["YES" if self.armhf else "NO"],
            "DEVICE_RAM": UI_STRINGS["DEVICE_RAM_SIZE"].format(gb=self.ram_gb) if self.ram_gb else "",
            "DEVICE_GPU": f"{_portmaster('GPU_DRIVER')} {_portmaster('GPU_DRIVER_VERSION')}",
            "DEVICE_SCREEN": self._screen_text(),
            "DEVICE_STICKS": self.sticks,
            "DEVICE_STORAGE": self._storage_text(),
            "DEVICE_GLIBC": self.glibc,
            "DEVICE_KERNEL": platform.release(),
            "DEVICE_PORTMASTER": _portmaster("PM_VERSION"),
        }
        for key, portmaster in differences.items():
            values[key] = UI_STRINGS["DEVICE_DIFFERS"].format(value=values[key], portmaster=portmaster)
        return {key: value.strip() for key, value in values.items() if value.strip()}

    def _screen_text(self) -> str:
        w, h = self.size
        if not w or not h:
            return ""
        return UI_STRINGS["DEVICE_SCREEN_SIZE"].format(w=w, h=h, aspect=_aspect(w, h), rate=self.refresh_rate)

    def _disk_usage(self):
        usage, checked = self._disk
        if time.time() - checked >= DISK_REFRESH:
            try:
                usage = shutil.disk_usage(PORTS_DIR)
            except OSError:
                usage = None
            self._disk = (usage, time.time())
        return usage

    def _storage_text(self) -> str:
        usage = self._disk_usage()
        if not usage:
            return ""
        return UI_STRINGS["DEVICE_STORAGE_SIZE"].format(free=_size_text(usage.free), total=_size_text(usage.total))

    def summary(self) -> str:
        usage = self._disk_usage()
        free = UI_STRINGS["DEVICE_FREE"].format(free=_size_text(usage.free)) if usage else ""
        return " | ".join(filter(None, (self.cfw, free)))


def _size_text(size: int) -> str:
    mb = size / 1024**2
    return UI_STRINGS["SIZE_MB"].format(size=mb) if mb < 1024 else UI_STRINGS["SIZE_GB"].format(size=mb / 1024)
