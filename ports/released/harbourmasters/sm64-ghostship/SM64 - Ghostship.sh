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
GAMEDIR="/$directory/ports/sm64-ghostship"
CONFIG="ghostship.cfg.json"

# Exports
export LD_LIBRARY_PATH="$GAMEDIR/libs:$LD_LIBRARY_PATH"
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"

# Set up logging
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Permissions
$ESUDO chmod +x "$GAMEDIR/Ghostship"

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
    for rom in "$GAMEDIR/baseroms/"*.*64; do
        [ -f "$rom" ] || continue
        name=$(basename "$rom")
        # Never clobber a rom the user already put in the game directory.
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

# Check imgui.ini and modify if needed
imgui_reset() {
    input_file="imgui.ini"
    temp_file="imgui_temp.ini"
    skip_section=0
    # Loop through each line in the input file
    while IFS= read -r line; do
        # Check if the line is a window header
        if [[ "$line" =~ ^\[Window\]\[Main\ Game\] || "$line" =~ ^\[Window\]\[Main\ -\ Deck\] ]]; then
            skip_section=1  # Set the flag to skip modifications for this section
        elif [[ "$line" =~ ^\[Window\] ]]; then
            skip_section=0  # Reset the flag for other windows
        fi

        # Modify Pos and Size only if the current section is not skipped
        if [[ $skip_section -eq 0 ]]; then
            if [[ "$line" =~ ^Pos=.* ]]; then
                echo "Pos=30,30" >> "$temp_file"
            elif [[ "$line" =~ ^Size=.* ]]; then
                echo "Size=400,300" >> "$temp_file"
            else
                echo "$line" >> "$temp_file"
            fi
        else
            # If skipping, write the line unchanged
            echo "$line" >> "$temp_file"
        fi
    done < "$input_file"

    # Replace the original file with the modified one
    mv "$temp_file" "$input_file"
}

edit_json() {
    [ -f "$CONFIG" ] || return 0

    # Close the menu, force controller navigation, and correct the window
    # backend (3.0.0 renumbered the enum: Id 1 is now DX11, OpenGL moved to 2)
    sed -i -e 's/"Menu":[[:space:]]*1/"Menu": 0/' \
           -e 's/"gControlNav":[[:space:]]*[0-9]*/"gControlNav": 1/' \
           -e 's/"Id":[[:space:]]*1,/"Id": 2,/' \
           "$CONFIG"
}

# --------------------- END FUNCTIONS ---------------------

# Unpack shipped assets
unzip_assets || exit 1

# Edit json
edit_json

# Edit imgui
if [ -f "imgui.ini" ]; then
    imgui_reset
fi

# Make baseroms visible to the extractor if we still need to generate sm64.o2r
if [ ! -f "$GAMEDIR/sm64.o2r" ]; then
    stage_baseroms
fi

# Run the game
$GPTOKEYB "Ghostship" -c "ghostship.gptk" &
pm_platform_helper "$GAMEDIR/Ghostship" > /dev/null
./Ghostship

# Cleanup
unstage_baseroms
rm -rf "$GAMEDIR/logs/"
pm_finish
