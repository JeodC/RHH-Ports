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

source $controlfolder/control.txt
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls

# Variables
GAMEDIR="/$directory/ports/elementallis"
GAME="$GAMEDIR/data/Elementallis.x86_64"
BOX="$HOME/box"
BOX64="$BOX/box64"

# CD and set log
cd "$GAMEDIR/data"
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Permissions
chmod +x "$GAME"

# Pre-flight checks for X11 and OpenGL. This is a Unity game — the westonwrap
# crusty GL bridge aborts it during graphics init, so it runs on native X11/GL
# only (hence the opengl requirement in port.json).
if [ -z "$DISPLAY" ]; then
    echo "Error: Display manager not found. This game requires OpenGL and X11 to run."
    exit 1
fi

if ! command -v glxinfo >/dev/null 2>&1; then
    echo "Error: OpenGL not found. This game requires OpenGL and X11 to run."
    exit 1
fi

# Mount box runtime (box64 + Box32, shared across box ports)
BOX_RUNTIME="$controlfolder/libs/box.squashfs"
if [ -f "$BOX_RUNTIME" ]; then
    $ESUDO mkdir -p "$BOX"
    $ESUDO umount "$BOX" 2>/dev/null || true
    $ESUDO mount "$BOX_RUNTIME" "$BOX"
else
    pm_message "This port requires the box runtime. Please update PortMaster."
    pm_finish
    exit 1
fi

# Display loading splash (from the box runtime)
[ "$CFW_NAME" == "muOS" ] && $ESUDO "$BOX/splash" "$GAMEDIR/splash.png" 1
$ESUDO "$BOX/splash" "$GAMEDIR/splash.png" 30000 &

# Exports
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
export LD_LIBRARY_PATH="$GAMEDIR/libs.aarch64:$GAMEDIR/data:$LD_LIBRARY_PATH"
export BOX64_LD_LIBRARY_PATH="$BOX/box64-x86_64-linux-gnu:$BOX/box64-i386-linux-gnu:$GAMEDIR/data:$LD_LIBRARY_PATH"
export XDG_CONFIG_HOME="$GAMEDIR/saves" && mkdir -p "$GAMEDIR/saves"
export SDL_VIDEODRIVER=x11

# Box64 settings
export BOX64_NOBANNER=1
export BOX64_DYNAREC=1
export BOX64_DYNAREC_SAFEFLAGS=0
export BOX64_DYNAREC_FASTROUND=1
export BOX64_DYNAREC_BIGBLOCK=1
export BOX64_DYNAREC_CALLRET=1
export BOX64_DYNAREC_DIRTY=1
export BOX64_DYNAREC_FORWARD=128
export BOX64_RDTSC_1GHZ=1

export BOX64_DYNAREC_STRONGMEM=0
export BOX64_DYNAREC_WAIT=1
export BOX64_DYNAREC_X87DOUBLE=0
export BOX64_DYNAREC_FASTNAN=1
export BOX64_PREFER_WRAPPED=1
export BOX64_PREFER_EMULATED=0
export BOX64_NOSIGSEGV=1

# Face-button layout — swap a/b and x/y when swapabxy.txt is present
if [ -f "$GAMEDIR/swapabxy.txt" ]; then
    chmod +x "$GAMEDIR/tools/swapabxy.py"
    if [ -n "$SDL_GAMECONTROLLERCONFIG_FILE" ] && [ -f "$SDL_GAMECONTROLLERCONFIG_FILE" ]; then
        cat "$SDL_GAMECONTROLLERCONFIG_FILE" | "$GAMEDIR/tools/swapabxy.py" > "$GAMEDIR/gamecontrollerdb_swapped.txt"
        export SDL_GAMECONTROLLERCONFIG_FILE="$GAMEDIR/gamecontrollerdb_swapped.txt"
    fi
    if [ -n "$SDL_GAMECONTROLLERCONFIG" ]; then
        export SDL_GAMECONTROLLERCONFIG="`echo "$SDL_GAMECONTROLLERCONFIG" | "$GAMEDIR/tools/swapabxy.py"`"
    fi
fi

# Run it
$GPTOKEYB "$GAME" xbox360 &
pm_platform_helper "$GAME" > /dev/null
$BOX64 "$GAME"

# Clean up after ourselves
$ESUDO umount "$BOX" 2>/dev/null
pm_finish
