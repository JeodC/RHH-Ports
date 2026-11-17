#!/usr/bin/env python3
"""Build the PortMasterV3 ports.json + images.zip for the ports-latest release
so stock PortMaster can browse this repo (via docs/010_rhh.source.json)."""

import argparse
import hashlib
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO_SLUG = "JeodC/RHH-Ports"
PORTS_RELEASE_URL = f"https://github.com/{REPO_SLUG}/releases/download/ports-latest"
RUNTIMES_RELEASE_URL = f"https://github.com/{REPO_SLUG}/releases/download/runtimes-latest"

PM_OFFICIAL_CATALOG_URL = (
    "https://github.com/PortsMaster/PortMaster-New/releases/latest/download/ports.json"
)


def fetch_official_runtimes():
    """Official aarch64 runtimes ({runtime_name: info}) from the catalog stock
    PortMaster consumes. Fetch failure aborts; the published catalog stays live."""
    try:
        req = urllib.request.Request(
            PM_OFFICIAL_CATALOG_URL, headers={"User-Agent": "RHH-Ports catalog generator"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception as exc:
        sys.exit(f"ERROR: could not fetch official PortMaster catalog: {exc}")

    runtimes = {}
    for key, asset in data.get("utils", {}).items():
        if not key.endswith(".squashfs"):
            continue
        if asset.get("runtime_arch", "aarch64") != "aarch64":
            continue
        name = asset.get("runtime_name", key)
        runtimes[name] = {
            "name": asset.get("name", name),
            "runtime_name": name,
            "runtime_arch": "aarch64",
            "md5": asset["md5"],
            "size": asset["size"],
            "url": asset["url"],
        }

    if not runtimes:
        sys.exit("ERROR: official PortMaster catalog listed no runtimes")
    print(f"Discovered {len(runtimes)} official runtimes from PortMaster catalog")
    return runtimes

# Display names for repo-hosted runtimes (the set itself comes from
# runtimes/*.squashfs); a missing entry just shows the filename instead.
RUNTIME_DISPLAY_NAMES = {
    "gmloadernext.squashfs": "GMLoader-Next",
    "mkxp-z.squashfs": "MKXP-Z",
    "rlvm-sdl2.squashfs": "RLVM (SDL2)",
}

# PortMaster drops genres outside its fixed HM_GENRES list; map site-only
# tags to the closest match so genre filtering still finds these ports.
GENRE_MAP = {
    "visual-novel": "visual novel",
    "app": "other",
    "shooter": "fps",
}

# Unknown reqs make PortMaster hide a port on every device. Map site-only
# flags to the closest capability devices report (harbourmaster/hardware.py).
REQS_MAP = {
    "vulkan": "ultra",
    "!lowpower": "power",
}

ZIP_EPOCH = (2020, 1, 1, 0, 0, 0)  # arbitrary; real mtimes would change the zip md5 every run
ASSET_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def name_cleaner(text):
    # Same transform harbourmaster's name_cleaner does -- names have to match
    # what the app computes on its end.
    temp = re.sub(r"[^a-zA-Z0-9 _\-\.]+", "", text.strip().lower())
    return re.sub(r"[ \.]+", ".", temp)


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def convert_port(entry):
    attr = dict(entry.get("attr", {}))

    genres = []
    for genre in attr.get("genres") or []:
        genre = GENRE_MAP.get(genre, genre)
        if genre not in genres:
            genres.append(genre)
    attr["genres"] = genres

    if attr.get("image") is None:
        attr["image"] = {}
    if attr.get("min_glibc") is None:
        attr["min_glibc"] = ""

    attr["reqs"] = [REQS_MAP.get(req.lower(), req.lower()) for req in attr.get("reqs") or []]

    runtime = attr.get("runtime") or []
    if isinstance(runtime, str):
        runtime = [runtime]
    attr["runtime"] = runtime

    src = entry["source"]
    date_updated = (src.get("date_updated") or "")[:10]
    date_added = (src.get("first_seen") or date_updated)[:10]

    return {
        "version": entry.get("version", 4),
        "name": entry["name"],
        "items": entry.get("items") or [],
        "items_opt": entry.get("items_opt") or None,
        "attr": attr,
        "source": {
            "date_added": date_added,
            "date_updated": date_updated,
            "md5": src["md5"],
            "size": src["size"],
            "url": src["download_url"],
            # PortMaster's "total downloads" sort reads this
            "downloads": src.get("lifetime_downloads", 0),
        },
    }


def build_images_zip(ports, out_path):
    """Pack every port's screenshot into images.zip. Entries are sorted and
    timestamps fixed so identical screenshots always produce identical bytes."""
    entries = []
    missing = []
    by_name = {}
    for port_json in (REPO_ROOT / "ports" / "released").rglob("port.json"):
        try:
            data = json.loads(port_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("name"):
            by_name[data["name"]] = port_json.parent

    for port_name in ports:
        port_dir = by_name.get(port_name)
        screenshot = None
        if port_dir is not None:
            for candidate in sorted(port_dir.iterdir()):
                if candidate.is_file() and re.match(
                    r"screenshot.*\.(png|jpg|jpeg)$", candidate.name, re.IGNORECASE
                ):
                    screenshot = candidate
                    break
        if screenshot is None:
            missing.append(port_name)
            continue

        ext = screenshot.suffix.lower()
        if ext == ".jpeg":
            ext = ".jpg"  # PortMaster ignores .jpeg files, so store as .jpg
        stem = name_cleaner(port_name)
        if stem.endswith(".zip"):
            stem = stem[: -len(".zip")]
        entries.append((f"{stem}.screenshot{ext}", screenshot))

    entries.sort(key=lambda pair: pair[0])
    with zipfile.ZipFile(out_path, "w") as zf:
        for arcname, path in entries:
            info = zipfile.ZipInfo(arcname, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes(), compresslevel=9)

    if missing:
        print(f"WARNING: no screenshot found for: {', '.join(sorted(missing))}")
    return len(entries)


def build_utils(declared_runtimes, official_runtimes, images_zip_path):
    utils = {}

    # Anything in runtimes/ named like an official runtime is a mirror for
    # older Pharos builds -- skip it to avoid shadowing PortMaster's entry.
    own_runtimes = {
        path.name
        for path in (REPO_ROOT / "runtimes").glob("*.squashfs")
        if path.name not in official_runtimes
    }

    unresolvable = declared_runtimes - official_runtimes - own_runtimes
    if unresolvable:
        sys.exit(
            "ERROR: ports declare runtimes that neither official PortMaster nor "
            f"runtimes/ provides: {', '.join(sorted(unresolvable))}\n"
            "Add the squashfs to runtimes/ or fix the port.json."
        )

    for fname in sorted(own_runtimes & declared_runtimes):
        local = REPO_ROOT / "runtimes" / fname
        utils[fname] = {
            "name": RUNTIME_DISPLAY_NAMES.get(fname, fname[: -len(".squashfs")]),
            "runtime_name": fname,
            "runtime_arch": "aarch64",
            "md5": md5_file(local),
            "size": local.stat().st_size,
            "url": f"{RUNTIMES_RELEASE_URL}/{fname}",
        }

    utils["images.zip"] = {
        "name": "images.zip",
        "md5": md5_file(images_zip_path),
        "size": images_zip_path.stat().st_size,
        "url": f"{PORTS_RELEASE_URL}/images.zip",
    }
    return utils


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output", default="temp_pm", help="output directory (default: temp_pm)"
    )
    parser.add_argument(
        "--catalog",
        default=str(REPO_ROOT / "docs" / "ports.json"),
        help="input site catalog (default: docs/ports.json)",
    )
    args = parser.parse_args()

    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    ports = {}
    declared_runtimes = set()
    for entry in catalog:
        name = entry.get("name", "")
        if not ASSET_NAME_RE.match(name):
            print(
                f"WARNING: skipping port {name!r} - its name has characters GitHub "
                "strips from release-asset names, so its download URL would 404 "
                '(#67). Rename the port\'s "name" to a clean slug.',
                file=sys.stderr,
            )
            continue
        port = convert_port(entry)
        ports[port["name"]] = port
        declared_runtimes.update(port["attr"]["runtime"])

    images_zip = out_dir / "images.zip"
    image_count = build_images_zip(list(ports), images_zip)

    official = fetch_official_runtimes()

    pm_catalog = {
        "ports": {name: ports[name] for name in sorted(ports)},
        "utils": build_utils(declared_runtimes, set(official), images_zip),
        # PortMaster ignores extra top-level keys; Pharos reads this to fetch
        # official runtimes from PortMaster's hosting instead of a mirror.
        "official_runtimes": {
            name: official[name] for name in sorted(declared_runtimes & set(official))
        },
    }

    ports_json = out_dir / "ports.json"
    with open(ports_json, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(pm_catalog, fh, indent=2, sort_keys=False)
        fh.write("\n")

    print(
        f"Wrote {ports_json} ({len(ports)} ports, "
        f"{len(pm_catalog['utils'])} utils) and {images_zip} ({image_count} images)"
    )


if __name__ == "__main__":
    main()
