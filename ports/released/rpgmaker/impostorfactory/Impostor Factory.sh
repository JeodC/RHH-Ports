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
GAMEDIR="/$directory/ports/impostorfactory"
MKXPZ_RUNTIME="$controlfolder/libs/mkxp-z.squashfs"
MKXPZ="$HOME/mkxp-z"

# CD and set logging
cd "$GAMEDIR" || exit 1
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Mount the mkxp-z runtime
if [ -f "$MKXPZ_RUNTIME" ]; then
    $ESUDO mkdir -p "$MKXPZ"
    $ESUDO umount "$MKXPZ" 2>/dev/null || true
    $ESUDO mount "$MKXPZ_RUNTIME" "$MKXPZ"
else
    pm_message "mkxp-z runtime missing. Install it via PortMaster."
    sleep 5
    pm_finish
    exit 1
fi

# Make config dir for saves
mkdir -p "$GAMEDIR/config"

# stdlib lives inside the runtime. Drop any pre-runtime extracted copy
# first so the bind mount lands cleanly, then bind into $GAMEDIR.
[ -e "$GAMEDIR/stdlib" ] && [ ! -L "$GAMEDIR/stdlib" ] && rm -rf "$GAMEDIR/stdlib"
bind_directories "$GAMEDIR/stdlib" "$MKXPZ/stdlib"

# Exports — LD_LIBRARY_PATH deferred until just before mkxp-z runs
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
export XDG_DATA_HOME="$GAMEDIR/config"
export LC_ALL=C
export LANG=C

# Sanity check — game data must be copied in by the user
if [ ! -f "$GAMEDIR/Game.rgssad" ]; then
    pm_message "Game data missing. Copy your Steam install of Impostor Factory into $GAMEDIR."
    sleep 5
    $ESUDO umount "$MKXPZ" 2>/dev/null || true
    pm_finish
    exit 1
fi

# Strip Windows-only artifacts copied from the Steam install
rm -f "$GAMEDIR"/*.exe "$GAMEDIR"/*.dll "$GAMEDIR/mkxp.conf"

# Restore handheld-tuned mkxp.json
[ -f "$GAMEDIR/config/mkxp.json" ] && cp -f "$GAMEDIR/config/mkxp.json" "$GAMEDIR/mkxp.json"

# Drop our compat preloads into the game's preload/ dir
if [ -d "$GAMEDIR/config/preload" ]; then
    mkdir -p "$GAMEDIR/preload"
    cp -rf "$GAMEDIR/config/preload/." "$GAMEDIR/preload/"
fi

# Gptk — launched with stock LD path so its hotkey/kill logic isn't
# broken by our runtime libs
$GPTOKEYB "mkxp-z.aarch64" -c "$GAMEDIR/impostorfactory.gptk" &
pm_platform_helper "$MKXPZ/mkxp-z.aarch64" >/dev/null

# Now wire the runtime libs in for mkxp-z and run it.
export LD_LIBRARY_PATH="$MKXPZ/libs:$LD_LIBRARY_PATH"
export SRCDIR="$GAMEDIR"
"$MKXPZ/mkxp-z.aarch64"

# Cleanup
$ESUDO umount "$GAMEDIR/stdlib" 2>/dev/null || true
$ESUDO umount "$MKXPZ" 2>/dev/null || true
pm_finish
