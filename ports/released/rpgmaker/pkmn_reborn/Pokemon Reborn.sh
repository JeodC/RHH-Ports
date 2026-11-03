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
GAMEDIR="/$directory/ports/pkmn_reborn"
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
if [ ! -f "$GAMEDIR/Game.ini" ]; then
    pm_message "Game data missing. Copy your Pokemon Reborn install (19.16/19.17) into $GAMEDIR."
    sleep 5
    $ESUDO umount "$GAMEDIR/stdlib" 2>/dev/null || true
    $ESUDO umount "$MKXPZ" 2>/dev/null || true
    pm_finish
    exit 1
fi

# Restore handheld-tuned mkxp.json from the port-shipped preset
if [ -d "$GAMEDIR/mkxp" ]; then
    rm -f "$GAMEDIR/mkxp.json"
    mv "$GAMEDIR/mkxp/mkxp.json" "$GAMEDIR/mkxp.json"
    rmdir "$GAMEDIR/mkxp" 2>/dev/null || true
fi

# Force onscreen keyboard (replaces broken SDL text-input path with character grid)
TE_FILE="$GAMEDIR/Scripts/PokemonTextEntry.rb"
[ -f "$TE_FILE" ] && sed -i 's/^\(\s*USEKEYBOARD\s*=\s*\).*/\1false/' "$TE_FILE"

# Default screen size to Full (4) instead of the engine default of M (1)
SETTINGS_FILE="$GAMEDIR/Scripts/Reborn/Settings.rb"
[ -f "$SETTINGS_FILE" ] && sed -i 's/^\(\s*DEFAULTSCREENZOOM\s*=\s*\).*/\14.0/' "$SETTINGS_FILE"

# Gptk — launched with stock LD path so its hotkey/kill logic isn't
# broken by our runtime libs
$GPTOKEYB "mkxp-z.aarch64" -c "$GAMEDIR/reborn.gptk" &
pm_platform_helper "$MKXPZ/mkxp-z.aarch64" >/dev/null

# Now wire the runtime libs in for mkxp-z and run it.
export LD_LIBRARY_PATH="$MKXPZ/libs:$LD_LIBRARY_PATH"
export SRCDIR="$GAMEDIR"
"$MKXPZ/mkxp-z.aarch64"

# Cleanup — unmount bind first, then the runtime
$ESUDO umount "$GAMEDIR/stdlib" 2>/dev/null || true
$ESUDO umount "$MKXPZ" 2>/dev/null || true
pm_finish
