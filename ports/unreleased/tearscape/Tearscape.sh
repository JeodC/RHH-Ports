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

# Variables
GAMEDIR="/$directory/ports/tearscape"
GAME="$GAMEDIR/data/Tearscape.x86_64"
BOX64="$GAMEDIR/box64/box64"

# CD and set log
cd "$GAMEDIR/data"
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Permissions
chmod +x "$BOX64"

# Exports
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"

export LD_LIBRARY_PATH="$GAMEDIR/box64/x64:$GAMEDIR/data:$LD_LIBRARY_PATH"
export BOX64_LD_LIBRARY_PATH="$GAMEDIR/box64/x64:$GAMEDIR/data:$LD_LIBRARY_PATH"

# Bind config dir
bind_directories "$XDG_DATA_HOME/Tearscape" "$GAMEDIR/config"

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

# Box64 optimizations
export BOX64_NOBANNER=1
export BOX64_DYNAREC=1
export BOX64_DYNAREC_SAFEFLAGS=1
export BOX64_DYNAREC_FASTROUND=0
export BOX64_DYNAREC_BIGBLOCK=0
export BOX64_DYNAREC_CALLRET=0
export MESA_NO_ERROR=1

# Run it
$GPTOKEYB "$GAME" -c "$GAMEDIR/tearscape.gptk" &
pm_platform_helper "$GAME" > /dev/null
$ESUDO env \
    WRAPPED_LIBRARY_PATH="$LD_LIBRARY_PATH" \
    BOX64_LD_LIBRARY_PATH="$BOX64_LD_LIBRARY_PATH" \
    $weston_dir/westonwrap.sh headless noop kiosk crusty_glx_gl4es \
    "$BOX64" "$GAME"

# Cleanup
$ESUDO "$weston_dir/westonwrap.sh" cleanup
if [ "$PM_CAN_MOUNT" != "N" ]; then
    $ESUDO umount "$weston_dir" 2>/dev/null
fi

pm_finish