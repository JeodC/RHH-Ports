#!/usr/bin/env python3
"""
Unpacks queued zips into the ports/windows tree and merges their gameinfo.
"""
from pathlib import Path
from contextlib import suppress
import io
import os
import tempfile
import zipfile
import shutil
import xml.etree.ElementTree as ET

# Basenames of the GameMaker data file inside a .port archive.
GAME_DATA_NAMES = ("game.droid", "data.win")

# DATA_DIR holds the autoinstall queue; INSTALL_DIR is the binary's dir. PORTS_DIR /
# WINDOWS_DIR derive from its siblings (PortMaster's ports/ and windows/ trees).
from config import DATA_DIR as _DATA_DIR_STR, INSTALL_DIR as _INSTALL_DIR_STR
DATA_DIR = Path(_DATA_DIR_STR)
AUTOINSTALL_DIR = DATA_DIR / "autoinstall"
INSTALL_DIR = Path(_INSTALL_DIR_STR)
PORTS_DIR = INSTALL_DIR.parent
WINDOWS_DIR = INSTALL_DIR.parent.parent / "windows"

class AutoInstaller:
    def __init__(self, autoinstall_dir: Path = AUTOINSTALL_DIR):
        self.autoinstall_dir = Path(autoinstall_dir)
        self.autoinstall_dir.mkdir(parents=True, exist_ok=True)

    def install_zip(self, zip_name: str) -> int:
        zip_path = self.autoinstall_dir / zip_name
        if not zip_path.is_file():
            print(f"[ERROR] {zip_path} not found")
            return 255

        print(f"[INSTALL] Installing {zip_name}...")
        try:
            result = self._extract_and_register(zip_path, zip_name)
        except zipfile.BadZipFile:
            print(f"[ERROR] {zip_name} is not a valid zip")
            result = 255
        except Exception as e:
            print(f"[ERROR] Failed to install {zip_name}: {e}")
            result = 255
        finally:
            # Always consume the zip, success or failure. A left-behind zip is
            # re-globbed every batch and, if corrupt, never clears. A real retry
            # re-downloads it anyway.
            zip_path.unlink(missing_ok=True)

        if result == 0:
            print(f"[OK] Installed {zip_name}")
        return result

    def _extract_and_register(self, zip_path: Path, zip_name: str) -> int:
        """Extract one autoinstall zip into the ports/windows tree and merge its
        gameinfo.xml into gamelist.xml. Returns 0, or 255 when the zip lacks
        port.json/bottle.json or a bottle can't install. May raise; install_zip maps that to 255."""
        with zipfile.ZipFile(zip_path, "r") as zf:
            print(f"[EXTRACT] Zip contents: {zf.namelist()}")
            target_json = None
            for file in zf.namelist():
                if file.endswith(("port.json", "bottle.json")):
                    target_json = file
                    break
            if not target_json:
                print(f"[ERROR] No port.json or bottle.json in {zip_name}")
                return 255

            is_port = target_json.endswith("port.json")
            base_dir = PORTS_DIR if is_port else WINDOWS_DIR
            gamelist_path = base_dir / "gamelist.xml"

            if not is_port and not WINDOWS_DIR.exists():
                print(f"[ERROR] {WINDOWS_DIR} system folder is missing. Aborting bottle install.")
                return 255

            base_dir.mkdir(parents=True, exist_ok=True)

            print(f"[EXTRACT] Extracting {zip_name} -> {base_dir}/ (flat)")
            self._extract_preserving_ports(zf, base_dir)
            self._join_split_payloads(zf, base_dir)

            # Clean macOS junk
            for junk in base_dir.rglob("__MACOSX"):
                if junk.is_dir():
                    shutil.rmtree(junk, ignore_errors=True)
            for junk in base_dir.rglob("*.DS_Store"):
                junk.unlink(missing_ok=True)

            gameinfo_file = None
            for file in zf.namelist():
                if file.endswith("gameinfo.xml"):
                    candidate = base_dir / file
                    if candidate.is_file():
                        gameinfo_file = candidate
                        break

            if gameinfo_file:
                print(f"[GAMELIST] Found {gameinfo_file}")
                self.gamelist_add(gameinfo_file, gamelist_path)
            else:
                print(f"[WARN] No gameinfo.xml found in {zip_name}")

        return 0

    def _extract_preserving_ports(self, zf: zipfile.ZipFile, base_dir: Path) -> None:
        """Like extractall(), but never blow away a user's GameMaker .port."""
        for member in zf.infolist():
            if member.filename.endswith(".port") and not member.is_dir():
                target = base_dir / member.filename
                if target.is_file() and self._merge_port(zf, member, target):
                    continue
            zf.extract(member, base_dir)

    def _join_split_payloads(self, zf: zipfile.ZipFile, base_dir: Path) -> None:
        groups: dict[str, list[tuple[int, str]]] = {}
        for name in zf.namelist():
            base, sep, index = name.rpartition(".part.")
            if sep and index.isdigit():
                groups.setdefault(base, []).append((int(index), name))

        for base, members in sorted(groups.items()):
            members.sort()
            if [i for i, _ in members] != list(range(1, len(members) + 1)):
                print(f"[SPLIT][ERROR] {base}: parts {[i for i, _ in members]} are not a "
                      f"complete run from 001; leaving them unjoined")
                continue

            paths = [base_dir / name for _, name in members]
            missing = [p for p in paths if not p.is_file()]
            if missing:
                print(f"[SPLIT][ERROR] {base}: {len(missing)} part(s) missing after extract; "
                      f"leaving them unjoined")
                continue

            target = base_dir / base
            tmp = target.with_name(target.name + ".joining")
            print(f"[SPLIT] Joining {len(paths)} parts -> {target}")
            try:
                with open(tmp, "wb") as out:
                    for part in paths:
                        with open(part, "rb") as f:
                            shutil.copyfileobj(f, out, 1024 * 1024)
                os.replace(tmp, target)
            except OSError as e:
                print(f"[SPLIT][ERROR] {base}: join failed ({e}); parts kept for retry")
                with suppress(OSError):
                    tmp.unlink()
                continue

            for part in paths:
                part.unlink(missing_ok=True)
            print(f"[SPLIT] Joined {target.name} ({target.stat().st_size} bytes)")

    def _merge_port(self, zf: zipfile.ZipFile, member: zipfile.ZipInfo, target: Path) -> bool:
        """Reconcile an incoming .port with the one on disk. Returns True if handled
        here (caller skips the normal extract), False to fall back to a plain overwrite."""
        try:
            incoming = zipfile.ZipFile(io.BytesIO(zf.read(member)))
            incoming_infos = incoming.infolist()
        except (zipfile.BadZipFile, OSError) as e:
            print(f"[PORT][WARN] {member.filename}: unreadable incoming .port ({e}); overwriting")
            return False

        # Ships a complete game -> overwrite to deliver updates. Carries no user
        # data (saves live in a separate save_dir).
        if any(os.path.basename(i.filename) in GAME_DATA_NAMES for i in incoming_infos):
            print(f"[PORT] {member.filename}: ships game data -> overwriting")
            return False

        # Runtime-only base: the on-device copy has the user's game packed in.
        try:
            existing = zipfile.ZipFile(target, "r")
        except (zipfile.BadZipFile, OSError) as e:
            print(f"[PORT][WARN] {target}: unreadable existing .port ({e}); overwriting")
            return False

        try:
            existing_infos = existing.infolist()
            existing_crc = {i.filename: i.CRC for i in existing_infos}
            runtime_changed = any(
                not i.is_dir() and existing_crc.get(i.filename) != i.CRC
                for i in incoming_infos
            )

            if not runtime_changed:
                return True

            # Runtime changed: splice new runtime libs into the user's .port,
            # preserving every entry the base doesn't provide (their game data).
            incoming_names = {i.filename for i in incoming_infos}
            fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".porttmp")
            os.close(fd)
            try:
                with zipfile.ZipFile(tmp, "w") as out:
                    for info in incoming_infos:
                        self._copy_entry(incoming, info, out)
                    for info in existing_infos:
                        if info.filename not in incoming_names:
                            self._copy_entry(existing, info, out)
                existing.close()
                os.replace(tmp, str(target))
            except Exception as e:
                with suppress(OSError):
                    os.remove(tmp)
                print(f"[ERROR] {member.filename}: splice failed ({e}); overwriting")
                return False
            return True
        finally:
            existing.close()

    @staticmethod
    def _copy_entry(src: zipfile.ZipFile, info: zipfile.ZipInfo, out: zipfile.ZipFile) -> None:
        """Stream one entry from src into out, preserving name and compression."""
        if info.is_dir():
            out.writestr(info, b"")
            return
        with src.open(info, "r") as sf, out.open(info, "w") as df:
            shutil.copyfileobj(sf, df, 1024 * 1024)

    def gamelist_add(self, gameinfo_file: Path, gamelist_path: Path) -> None:
        try:
            tree = ET.parse(gameinfo_file)
            root_gameinfo = tree.getroot()
        except ET.ParseError as e:
            print(f"[ERROR] Bad gameinfo.xml ({gameinfo_file.name}): {e}")
            return

        if gamelist_path.exists():
            try:
                tree = ET.parse(gamelist_path)
                root = tree.getroot()
                if root.tag.lower() != "gamelist":
                    root.tag = "gameList"
            except ET.ParseError:
                print(f"[WARN] Corrupted gamelist.xml - creating new")
                root = ET.Element("gameList")
                tree = ET.ElementTree(root)
        else:
            root = ET.Element("gameList")
            tree = ET.ElementTree(root)
            print(f"[CREATE] Creating {gamelist_path}")

        existing_games = {
            game.find("path").text: game
            for game in root.findall("game")
            if game.find("path") is not None
        }

        count_added = 0
        count_updated = 0

        for game in root_gameinfo.findall("game"):
            path_elem = game.find("path")
            if path_elem is not None:
                path = path_elem.text
                if path in existing_games:
                    existing_game = existing_games[path]
                    for elem in game:
                        existing = existing_game.find(elem.tag)
                        if existing is not None:
                            existing.text = elem.text
                        else:
                            existing_game.append(elem)
                    count_updated += 1
                else:
                    root.append(game)
                    existing_games[path] = game
                    count_added += 1

        if count_added > 0 or count_updated > 0:
            if hasattr(ET, "indent"):
                ET.indent(root, space="  ", level=0)
            gamelist_path.parent.mkdir(parents=True, exist_ok=True)
            tree.write(
                gamelist_path,
                encoding="utf-8",
                xml_declaration=True,
                short_empty_elements=False
            )
            print(f"[GAMELIST] Added {count_added} new game(s), updated {count_updated} existing game(s) -> {gamelist_path.name}")
        else:
            print(f"[INFO] No changes from {gameinfo_file.name}")