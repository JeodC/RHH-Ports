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

ARMHF_LOADER = "/lib/ld-linux-armhf.so.3"
DISK_REFRESH = 5  # seconds

# REQS_MAP in buildtools/generate_pm_catalog.py
REQ_ALIASES = {"!lowpower": "power"}
REQ_TEXT = {
    "power": "a faster CPU",
    "ultra": "a high-end device",
    "hires": "a larger screen",
    "wide": "a wide screen",
    "!lowres": "a 640x480 screen",
    "opengl": "OpenGL",
    "vulkan": "Vulkan",
    "analog_1": "an analog stick",
    "analog_1|analog_2": "an analog stick",
    "analog_2": "two analog sticks",
}
ASPECTS = {"1:1": 1, "4:3": 4 / 3, "3:2": 3 / 2, "16:9": 16 / 9}
SCREEN_CAPS = re.compile(r"\d+x\d+|\d+:\d+|hires|lowres|wide|square")

LOW_POWER_CPUS = ("rk3326", "px30")
NOT_ULTRA_CPUS = LOW_POWER_CPUS + ("h700", "a133", "a527", "sun50iw9", "sun50iw10")
# Older PortMaster versions don't report these
ASSUMED_CAPS = {"opengl", "vulkan", "touch", "rumble", "analog_triggers", "restore"}


def _portmaster(name: str) -> str:
    value = os.environ.get(name, "").strip()
    return "" if value.lower() in ("unknown", "none") else value


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
        return round(int(total.group(1)) / 1024 ** 2 * 1.1) if total else 0

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
            out.append(" or ".join(port.arch))
        if self._glibc and _version(port.min_glibc) > self._glibc:
            out.append(f"glibc {port.min_glibc}")
        for req in port.reqs:
            req = REQ_ALIASES.get(req.lower(), req.lower())
            names = [n for n in req.lstrip("!").split("|") if n]
            if names and any(n in self.caps for n in names) == req.startswith("!"):
                out.append(self._req_text(req))
        return out

    @staticmethod
    def _req_text(req: str) -> str:
        if re.fullmatch(r"\d+gb", req):
            return f"{req[:-2]} GB RAM"
        return REQ_TEXT.get(req) or (f"a device other than {req[1:]}" if req.startswith("!") else req.replace("|", " or "))

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------
    def _differences(self) -> dict[str, str]:
        reported = {
            "Screen": "x".join(filter(None, (_portmaster("DISPLAY_WIDTH"), _portmaster("DISPLAY_HEIGHT")))),
            "32-bit": {"Y": "yes", "N": "no"}.get(_portmaster("DEVICE_HAS_ARMHF"), ""),
            "glibc": re.sub(r"^(\d)(\d+)$", r"\1.\2", _portmaster("CFW_GLIBC")),
        }
        measured = {
            "Screen": "{}x{}".format(*self.size),
            "32-bit": "yes" if self.armhf else "no",
            "glibc": self.glibc,
        }
        return {k: v for k, v in reported.items() if v and measured[k] and v != measured[k]}

    def _log(self) -> None:
        print(f"[DEVICE] {'; '.join(f'{label}: {value}' for label, value in self.rows())}")
        print(f"[DEVICE] Capabilities: {' '.join(sorted(self.caps))}")
        for label, value in self._differences().items():
            print(f"[DEVICE] PortMaster has {label} {value}")

    def rows(self) -> List[tuple[str, str]]:
        w, h = self.size
        differences = self._differences()
        values = {
            "CFW": f"{self.cfw} {_portmaster('CFW_VERSION')}",
            "Device": _portmaster("DEVICE_NAME") or _read("/proc/device-tree/model"),
            "CPU": f"{self.cpu} ({self.arch})",
            "32-bit": "yes" if self.armhf else "no",
            "RAM": f"{self.ram_gb} GB" if self.ram_gb else "",
            "GPU": f"{_portmaster('GPU_DRIVER')} {_portmaster('GPU_DRIVER_VERSION')}",
            "Screen": f"{w}x{h} ({_aspect(w, h)}), {self.refresh_rate} Hz" if w and h else "",
            "Analog sticks": self.sticks,
            "Storage": self._storage_text(),
            "glibc": self.glibc,
            "Kernel": platform.release(),
            "PortMaster": _portmaster("PM_VERSION"),
        }
        return [
            (label, value.strip() + (f" [PM: {differences[label]}]" if label in differences else ""))
            for label, value in values.items() if value.strip()
        ]

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
        return f"{_size_text(usage.free)} free of {_size_text(usage.total)}" if usage else ""

    def summary(self) -> str:
        usage = self._disk_usage()
        return " | ".join(filter(None, (self.cfw, f"{_size_text(usage.free)} free" if usage else "")))


def _size_text(size: int) -> str:
    mb = size / 1024 ** 2
    return f"{mb:.0f} MB" if mb < 1024 else f"{mb / 1024:.1f} GB"
