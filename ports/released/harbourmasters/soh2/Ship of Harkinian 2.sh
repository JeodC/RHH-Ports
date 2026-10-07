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
GAMEDIR="/$directory/ports/soh2"

# Exports
export LD_LIBRARY_PATH="$GAMEDIR/libs:$LD_LIBRARY_PATH"
export SDL_GAMECONTROLLERCONFIG=$sdl_controllerconfig
export TU_DEBUG=nolrz

# CD and set permissions
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1
$ESUDO chmod +x "$GAMEDIR/2s2h.elf"

# -------------------- BEGIN FUNCTIONS --------------------

unzip_assets() {
    [ -f "$GAMEDIR/assets/extractor.zip" ] || return 0

    SEVENZIP="$controlfolder/7zzs.${DEVICE_ARCH}"
    if [ ! -x "$SEVENZIP" ]; then
        pm_message "This port requires the latest version of PortMaster."
        return 1
    fi

    echo "Unpacking extractor assets..."
    if $ESUDO "$SEVENZIP" x -y "$GAMEDIR/assets/extractor.zip" -o"$GAMEDIR/assets" >/dev/null; then
        rm -f "$GAMEDIR/assets/extractor.zip"
    else
        pm_show_error "Unable to unpack assets/extractor.zip."
        return 1
    fi
}

rom_check() {
    [ -f "$GAMEDIR/mm.o2r" ] && return 0
    if ! ls "$GAMEDIR/"*.z64 "$GAMEDIR/"*.n64 "$GAMEDIR/"*.v64 >/dev/null 2>&1; then
        rom=$(find "$GAMEDIR" -type f \( -iname "*.z64" -o -iname "*.n64" -o -iname "*.v64" \) -print -quit)
        if [ -z "$rom" ]; then
            echo "No rom found in $GAMEDIR! Can't generate mm.o2r!"
            pm_message "No rom found. Place your Majora's Mask rom in ports/soh2, then relaunch."
            return 1
        fi
        name=$(basename "$rom")
        echo "Moving $name into $GAMEDIR"
        mv "$rom" "$GAMEDIR/${name%.*}.$(echo "${name##*.}" | tr '[:upper:]' '[:lower:]')"
    fi
}

# --------------------- END FUNCTIONS ---------------------

# Perform functions
unzip_assets || exit 1
rom_check || exit 1

# Close the menu if open
sed -i 's/"Menu": *1/"Menu": 0/' 2ship2harkinian.json

# Force controller navigation on
if grep -q '"ControlNav"' 2ship2harkinian.json; then
    sed -i 's/"ControlNav":[[:space:]]*[0-9]*/"ControlNav": 1/' 2ship2harkinian.json
else
    sed -i '/"gSettings":[[:space:]]*{/a\"ControlNav": 1,' 2ship2harkinian.json
fi

# Run the game
$GPTOKEYB "2s2h.elf" -c "soh2.gptk" & 
pm_platform_helper "2s2h.elf" >/dev/null
./2s2h.elf

# Cleanup
rm -rf "$GAMEDIR/logs"
pm_finish
