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
GAMEDIR="/$directory/ports/pkmn_tectonic"
SEVEN_ZIP="$controlfolder/7zzs.${DEVICE_ARCH}"
MKXPZ_RUNTIME="$controlfolder/libs/mkxp-z.squashfs"
MKXPZ="$HOME/mkxp-z"

# CD and set logging
cd "$GAMEDIR" || exit 1
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Mount the mkxp-z runtime (squashfs ships mkxp-z + libs + stdlib)
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

# Make directories
mkdir -p "$GAMEDIR/config"

# stdlib lives inside the runtime. Drop any pre-runtime extracted copy
# first so the bind mount lands cleanly, then bind into $GAMEDIR.
[ -e "$GAMEDIR/stdlib" ] && [ ! -L "$GAMEDIR/stdlib" ] && rm -rf "$GAMEDIR/stdlib"
bind_directories "$GAMEDIR/stdlib" "$MKXPZ/stdlib"

# Exports — LD_LIBRARY_PATH is deferred until just before mkxp-z runs.
# Backgrounded gptokeyb inherits its env at fork time, and runtime libs
# in its LD path confuse gptokeyb's dependency chain.
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
export XDG_DATA_HOME="$GAMEDIR/config"
export LC_ALL=C
export LANG=C

unzip_data() {
    pm_message "Unzipping game data. This could take a while..."
    local zipfile ini_path gdir entry name

    zipfile=$(find "$GAMEDIR" -maxdepth 1 -type f -name "*.zip" | head -n1)
    [ -n "$zipfile" ] || return 0

    "$SEVEN_ZIP" x -y -bso0 -bsp0 "$zipfile" -o"$GAMEDIR" || return 1

    ini_path=$(find "$GAMEDIR" -mindepth 2 -type f -iname "Project Chasm.ini" -print -quit)
    [ -z "$ini_path" ] && \
        ini_path=$(find "$GAMEDIR" -maxdepth 1 -type f -iname "Project Chasm.ini" -print -quit)

    if [ -z "$ini_path" ]; then
        echo "Error: Project Chasm.ini not found inside the zip structure."
        return 1
    fi

    gdir=$(dirname "$ini_path")
    if [ "$gdir" != "$GAMEDIR" ]; then
        echo "Lifting game files from $gdir to $GAMEDIR..."
        find "$gdir" -mindepth 1 -maxdepth 1 -print0 | \
            while IFS= read -r -d '' entry; do
                name="${entry##*/}"
                if [ -d "$entry" ] && [ -d "$GAMEDIR/$name" ]; then
                    cp -rfp "$entry/." "$GAMEDIR/$name/" && rm -rf "$entry"
                else
                    mv -f "$entry" "$GAMEDIR/$name"
                fi
            done
        rmdir "$gdir" 2>/dev/null || true
    fi

    rm -f "$zipfile"
    return 0
}

# Run only if a zip exists
if ls "$GAMEDIR"/*.zip 1> /dev/null 2>&1; then
    unzip_data || exit 1
    # Remove files we don't need
    rm -rf "$GAMEDIR/Debug Game With PBS Compile.bat"
    rm -rf "$GAMEDIR/Debug Game.bat"
    rm -rf "$GAMEDIR/Essentials Docs Wiki.URL"
    rm -rf "$GAMEDIR/extendtext.exe"
    rm -rf "$GAMEDIR/extendtext.txt"
    rm -rf "$GAMEDIR/Game Linux.x86_64"
    rm -rf "$GAMEDIR/Game.exe"
    rm -rf "$GAMEDIR/GitIgnored Files for Project Chasm.zip"
    rm -rf "$GAMEDIR/Tectonic Updater.jar"
    rm -rf "$GAMEDIR/townmapgen.html"
fi

if [ -d "$GAMEDIR/mkxp" ]; then
    rm -rf "$GAMEDIR/mkxp.json"
    mv "$GAMEDIR/mkxp/mkxp.json" "$GAMEDIR/mkxp.json"
    rmdir "$GAMEDIR/mkxp"
fi

# Force onscreen keyboard (replaces broken SDL text-input path with character grid)
TE_FILE="$GAMEDIR/Plugins/Tectonic Graphics and UI/Objects and windows/Text Entry/PokemonEntryScene.rb"
[ -f "$TE_FILE" ] && sed -i 's/^\(\s*USEKEYBOARD\s*=\s*\).*/\1false/' "$TE_FILE"

# Disable Screen Size resize (SDL window resize crashes under fullscreen mkxp-z)
SCENE_FILE="$GAMEDIR/Plugins/Tectonic Graphics and UI/Menus/Options/OptionScenes.rb"
[ -f "$SCENE_FILE" ] && sed -i 's|pbSetResizeFactor(\$Options\.screensize)|nil|' "$SCENE_FILE"

# Hide Controls menu entry (System.show_settings crashes under fullscreen mkxp-z)
MENU_FILE="$GAMEDIR/Plugins/Tectonic Graphics and UI/Menus/Options/PokemonOptionsMenu.rb"
[ -f "$MENU_FILE" ] && sed -i '/optionsCommands\[cmdControlsMapping = optionsCommands\.length\]/d' "$MENU_FILE"

# Close the pm_message dialog before launching.
if [ -e "$PM_PIPE" ] && command -v PortMasterDialogExit >/dev/null 2>&1; then
    PortMasterDialogExit
fi

# Gptk — launched with stock LD path so its hotkey/kill logic isn't
# broken by our runtime libs
$GPTOKEYB "mkxp-z.aarch64" -c "$GAMEDIR/tectonic.gptk" &
pm_platform_helper "$MKXPZ/mkxp-z.aarch64" >/dev/null

# Now wire the runtime libs in for mkxp-z and run it.
export LD_LIBRARY_PATH="$MKXPZ/libs:$LD_LIBRARY_PATH"
export SRCDIR="$GAMEDIR"
"$MKXPZ/mkxp-z.aarch64"

# Cleanup
$ESUDO umount "$GAMEDIR/stdlib" 2>/dev/null || true
$ESUDO umount "$MKXPZ" 2>/dev/null || true
pm_finish
