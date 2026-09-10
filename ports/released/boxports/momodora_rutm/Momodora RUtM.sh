#!/bin/bash

XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}

if [ -d "/opt/system/Tools/PortMaster/" ]; then
  controlfolder="/opt/system/Tools/PortMaster"
elif [ -d "/opt/tools/PortMaster/" ]; then
  controlfolder="/opt/tools/PortMaster"
elif [ -d "$XDG_DATA_HOME/PortMaster/" ]; then
  controlfolder="$XDG_DATA_HOME/PortMaster"
else
  controlfolder="/roms/ports/PortMaster"
fi

source "$controlfolder/control.txt"
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls

GAMEDIR="/$directory/ports/momodora_rutm"
GAME="$GAMEDIR/data/MomodoraRUtM"

# Variables
cd "$GAMEDIR"
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Exports
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"

# gl4es tuning
export LIBGL_FB=0
export LIBGL_X11=1
export LIBGL_GL=21
export LIBGL_ES=2
export LIBGL_SHRINK=0
export LIBGL_UPLOAD_OPTIMIZE=1
export LIBGL_NPOT=2

# Box64 dynarec tuning
export BOX64_NOBANNER=1
export BOX64_DYNAREC=1
export BOX64_DYNAREC_BIGBLOCK=1
export BOX64_DYNAREC_CALLRET=1
export BOX64_DYNAREC_FORWARD=128
export BOX64_DYNAREC_STRONGMEM=0
export BOX64_DYNAREC_FASTROUND=1
export BOX64_DYNAREC_FASTNAN=1
export BOX64_DYNAREC_SAFEFLAGS=1
export BOX64_DYNAREC_WAIT=1
export BOX64_RDTSC_1GHZ=1

# Bind saves dir
bind_directories ~/.config/MomodoraRUtM "$GAMEDIR/saves"

# Prepare game
find "$GAMEDIR/data" -type f \( \
    -name "*.sh" -o -name "*.so" -o -name "*.out" \
\) -exec rm -f {} \;

# Mount box runtime
BOX="$HOME/box"
BOX_RUNTIME="$controlfolder/libs/box.squashfs"
BOX64="$BOX/box64"
if [ -f "$BOX_RUNTIME" ]; then
    $ESUDO mkdir -p "$BOX"
    $ESUDO umount "$BOX" 2>/dev/null || true
    $ESUDO mount "$BOX_RUNTIME" "$BOX"
else
    pm_message "This port requires the box runtime. Please update PortMaster."
    pm_finish
    exit 1
fi

# Mount Weston runtime
weston_dir=/tmp/weston
$ESUDO mkdir -p "$weston_dir"
weston_runtime="weston_pkg_0.2"

if [ ! -f "$controlfolder/libs/${weston_runtime}.squashfs" ]; then
    if [ ! -f "$controlfolder/harbourmaster" ]; then
        pm_message "This port requires the latest PortMaster. Please visit https://portmaster.games/."
        sleep 5
        exit 1
    fi

    # Try quiet install
    if ! $ESUDO "$controlfolder/harbourmaster" --quiet --no-check runtime_check "${weston_runtime}.squashfs"; then
        pm_message "Failed to install runtime. Please update PortMaster or install '${weston_runtime}' manually."
        sleep 5
        exit 1
    fi
fi

if [ "$PM_CAN_MOUNT" != "N" ]; then
    $ESUDO umount "$weston_dir" 2>/dev/null
fi

$ESUDO mount "$controlfolder/libs/${weston_runtime}.squashfs" "$weston_dir"

# Library search path
game_libs="$BOX/box64-i386-linux-gnu:$BOX/box64-x86_64-linux-gnu:$weston_dir/lib_aarch64:$GAMEDIR/data"

# Mali's fbdev EGL won't allocate a surface whose width isn't 32-aligned
WESTON_W=${DISPLAY_WIDTH:-640}
WESTON_H=${DISPLAY_HEIGHT:-480}
if [ $(( WESTON_W % 32 )) -ne 0 ]; then
    WESTON_W=$(( (WESTON_W + 31) / 32 * 32 ))
    echo "[LOG]: Display width ${DISPLAY_WIDTH} is not 32-aligned; using ${WESTON_W} for the weston output."
fi

# Run it
cd "$GAMEDIR/data"
$GPTOKEYB "MomodoraRUtM" -c "$GAMEDIR/momodora.gptk" &
pm_platform_helper "$GAME" > /dev/null
$ESUDO env \
    WRAPPED_LIBRARY_PATH="$game_libs" \
    BOX64_LD_LIBRARY_PATH="$game_libs" \
    WESTON_HEADLESS_WIDTH="$WESTON_W" \
    WESTON_HEADLESS_HEIGHT="$WESTON_H" \
    $weston_dir/westonwrap.sh headless noop kiosk crusty_glx_gl4es \
    "$BOX64" "$GAME"

# Cleanup
$ESUDO "$weston_dir/westonwrap.sh" cleanup
if [ "$PM_CAN_MOUNT" != "N" ]; then
    $ESUDO umount "$weston_dir" 2>/dev/null
    $ESUDO umount "$BOX" 2>/dev/null
fi

pm_finish
