#!/bin/bash
# Pharos PyInstaller build.

set -e

PYTHON_MIN=3.11
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR/app"
DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"

# ---- Python version gate ---------------------------------------------------
PYTHON_BIN=""
for cand in python3.13 python3.12 python3.11 python3; do
    bin=$(command -v "$cand" || true)
    [ -z "$bin" ] && continue
    ver_major=$("$bin" -c 'import sys; print(sys.version_info.major)')
    ver_minor=$("$bin" -c 'import sys; print(sys.version_info.minor)')
    if [ "$ver_major" -ge 3 ] && [ "$ver_minor" -ge 11 ]; then
        PYTHON_BIN="$bin"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "No Python $PYTHON_MIN+ found." >&2
    echo "On Ubuntu/Debian: sudo apt install python3.11 python3.11-venv" >&2
    echo "If unavailable in apt: add the deadsnakes PPA first:" >&2
    echo "  sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt update" >&2
    exit 1
fi
PYTHON_VER=$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Using Python $PYTHON_VER at $PYTHON_BIN"

# ---- System build deps -----------------------------------------------------
# PyInstaller calls objdump on Linux; bullseye-slim doesn't ship binutils.
if command -v apt-get >/dev/null 2>&1 && ! command -v objdump >/dev/null 2>&1; then
    sudoer=""
    if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
        sudoer="sudo"
    fi
    echo "Installing binutils (needed by PyInstaller for objdump)"
    $sudoer apt-get update -qq
    $sudoer env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq binutils >/dev/null
fi

# ---- Python deps -----------------------------------------------------------
$PYTHON_BIN -m pip install --upgrade pip
$PYTHON_BIN -m pip install --upgrade -r "$SCRIPT_DIR/requirements.txt"

# ---- Build -----------------------------------------------------------------
rm -rf "$DIST_DIR" "$BUILD_DIR"
cd "$SCRIPT_DIR"

# Build the daemon as its own --onefile binary first. No SDL2, since it is
# headless. The --name is what the systemd unit and init.d hook reference.
pyinstaller \
    --onefile \
    --clean \
    --noconfirm \
    --name pharos-daemon \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR/daemon" \
    --specpath "$BUILD_DIR/daemon" \
    "$SOURCE_DIR/daemon.py"

# Build Pharos, embedding the daemon binary as a bundled resource. The
# Service module copies it out to INSTALL_DIR on user opt-in. SDL2 itself
# is provided by the target CFW at /usr/lib (set by the launchscript via
# PYSDL2_DLL_PATH) - we don't bundle it.
pyinstaller \
    --onefile \
    --clean \
    --noconfirm \
    --name Pharos \
    --collect-all sdl2 \
    --add-data "$SOURCE_DIR/fonts:fonts" \
    --add-data "$SOURCE_DIR/resources:resources" \
    --add-binary "$DIST_DIR/pharos-daemon:." \
    --paths "$SOURCE_DIR" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR/pharos" \
    --specpath "$BUILD_DIR/pharos" \
    "$SOURCE_DIR/main.py"

# The standalone daemon binary in dist/ has now been embedded in Pharos -
# remove it so only the single Pharos binary is published as the artifact.
rm -f "$DIST_DIR/pharos-daemon"

echo
echo "Build complete: $DIST_DIR/Pharos"
ls -lh "$DIST_DIR/Pharos"
