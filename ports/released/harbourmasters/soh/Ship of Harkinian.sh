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

# Set variables
GAMEDIR="/$directory/ports/soh"
CONFIG="shipofharkinian.json"

# Exports
export LD_LIBRARY_PATH="$GAMEDIR/libs":$LD_LIBRARY_PATH
export SDL_GAMECONTROLLERCONFIG=$sdl_controllerconfig

export PLAYERNAME="Player"
export ROOMID="rhh-ports"

# CD and set log
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1
$ESUDO chmod +x "$GAMEDIR/soh.elf"

# -------------------- BEGIN FUNCTIONS --------------------

unzip_assets() {
    [ -f "$GAMEDIR/assets.zip" ] || return 0

    SEVENZIP="$controlfolder/7zzs.${DEVICE_ARCH}"
    if [ ! -x "$SEVENZIP" ]; then
        pm_message "This port requires the latest version of PortMaster."
        return 1
    fi

    echo "Unpacking extractor assets..."
    $ESUDO rm -rf "$GAMEDIR/assets"
    if $ESUDO "$SEVENZIP" x -y "$GAMEDIR/assets.zip" -o"$GAMEDIR" >/dev/null; then
        $ESUDO rm -f "$GAMEDIR/assets.zip"
    else
        pm_show_error "Unable to unpack assets.zip."
        return 1
    fi
}

# Bridge baseroms/ into the game directory.
STAGED_ROMS=()

stage_baseroms() {
    for rom in "$GAMEDIR/baseroms/"*.z64 "$GAMEDIR/baseroms/"*.n64 "$GAMEDIR/baseroms/"*.v64; do
        [ -f "$rom" ] || continue
        name=$(basename "$rom")
        [ -e "$GAMEDIR/$name" ] && continue
        if mv "$rom" "$GAMEDIR/$name"; then
            STAGED_ROMS+=("$name")
        fi
    done
}

unstage_baseroms() {
    for name in "${STAGED_ROMS[@]}"; do
        [ -f "$GAMEDIR/$name" ] && mv "$GAMEDIR/$name" "$GAMEDIR/baseroms/$name"
    done
}

edit_json() {
    [ -f "$CONFIG" ] || return 0

    # Close the menu if open
    sed -i 's/"Menu":[[:space:]]*1/"Menu": 0/' "$CONFIG"

    # Set player name and room id
    awk -v name="$PLAYERNAME" -v room="$ROOMID" '
        depth == 1 {
            sub(/"Name":[[:space:]]*"[^"]*"/, "\"Name\": \"" name "\"")
            sub(/"RoomId":[[:space:]]*"[^"]*"/, "\"RoomId\": \"" room "\"")
        }
        depth { depth += gsub(/[{]/, "{") - gsub(/[}]/, "}") }
        !depth && /"Anchor":[[:space:]]*[{]/ { depth = 1 }
        { print }
    ' "$CONFIG" > "$CONFIG.tmp" && mv "$CONFIG.tmp" "$CONFIG"

    # Force controller navigation on
    if grep -q '"ControlNav"' "$CONFIG"; then
        sed -i 's/"ControlNav":[[:space:]]*[0-9]*/"ControlNav": 1/' "$CONFIG"
    else
        sed -i '/"gSettings":[[:space:]]*{/a\"ControlNav": 1,' "$CONFIG"
    fi
}

# --------------------- END FUNCTIONS ---------------------

# Perform functions
unzip_assets || exit 1

# Make baseroms visible to Torch
stage_baseroms

# Edit json
edit_json

# Run the game
$GPTOKEYB "soh.elf" -c "soh.gptk" & 
pm_platform_helper "soh.elf" >/dev/null
./soh.elf

# Cleanup
unstage_baseroms
rm -rf "$GAMEDIR/logs/"
pm_finish
