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
GAMEDIR="/$directory/ports/starship"

# Exports
export LD_LIBRARY_PATH="$GAMEDIR/libs:$LD_LIBRARY_PATH"
export SDL_GAMECONTROLLERCONFIG=$sdl_controllerconfig

# Set up logging
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Permissions
$ESUDO chmod +x "$GAMEDIR/Starship"
$ESUDO chmod +x "$GAMEDIR/tools/otrgen"

# Check imgui.ini and modify if needed
input_file="imgui.ini"
temp_file="imgui_temp.ini"
skip_section=0
# Loop through each line in the input file
while IFS= read -r line; do
    # Check if the line is a window header
    case "$line" in
        "[Window][Main Game]"*|"[Window][Main - Deck]"*)
            skip_section=1  # Set the flag to skip modifications for this section
            ;;
        "[Window]"*)
            skip_section=0  # Reset the flag for other windows
            ;;
    esac

    # Modify Pos and Size only if the current section is not skipped
    if [[ $skip_section -eq 0 ]]; then
        case "$line" in
            Pos=*) echo "Pos=30,30" >> "$temp_file" ;;
            Size=*) echo "Size=400,300" >> "$temp_file" ;;
            *) echo "$line" >> "$temp_file" ;;
        esac
    else
        # If skipping, write the line unchanged
        echo "$line" >> "$temp_file"
    fi
done < "$input_file"

# Replace the original file with the modified one
mv "$temp_file" "$input_file"

# Close the menu if open
sed -i 's/"Menu": *1/"Menu": 0/' starship.cfg.json

# Force controller navigation on
if grep -q '"gControlNav"' starship.cfg.json; then
    sed -i 's/"gControlNav":[[:space:]]*[0-9]*/"gControlNav": 1/' starship.cfg.json
else
    sed -i '/"CVars":[[:space:]]*{/a\"gControlNav": 1,' starship.cfg.json
fi

# Warn if sf64.o2r is older than Starship or starship.o2r
if [ -f "$GAMEDIR/sf64.o2r" ]; then
    if [ -f "$GAMEDIR/Starship" ] && [ "$GAMEDIR/Starship" -nt "$GAMEDIR/sf64.o2r" ] \
       || [ -f "$GAMEDIR/starship.o2r" ] && [ "$GAMEDIR/starship.o2r" -nt "$GAMEDIR/sf64.o2r" ]; then
        echo "Notice: sf64.o2r is older than Starship and/or starship.o2r. Forcing regeneration."
        rm -f "$GAMEDIR/sf64.o2r"
        REGEN=1
        export REGEN
    fi
fi

# Check if we need to generate any o2r files
if [ ! -f "$GAMEDIR/sf64.o2r" ]; then
    # Ensure we have a rom file before attempting to generate o2r
    if ls "$GAMEDIR/baseroms/"*.*64 1> /dev/null 2>&1; then
        if [ -f "$controlfolder/utils/patcher.txt" ]; then
            export PATCHER_FILE="$GAMEDIR/tools/otrgen"
            export PATCHER_GAME="$(basename "${0%.*}")"
            export PATCHER_TIME="5 to 10 minutes"
            export controlfolder
            source "$controlfolder/utils/patcher.txt"
            pid=$(pidof gptokeyb) && [ -n "$pid" ] && $ESUDO kill -9 $pid
        else
            pm_message "This port requires the latest version of PortMaster."
        fi
    else
        pm_message "Missing ROM files! Can't generate o2r!"
    fi
fi

# Check if O2R files were generated
if [ ! -f "$GAMEDIR/sf64.o2r" ]; then
    echo "No o2r found, can't run the game!"
    exit 1
fi

# Run the game
$GPTOKEYB "Starship" -c "starship.gptk" & 
pm_platform_helper "$GAMEDIR/Starship" > /dev/null
./Starship

# Cleanup
rm -rf logs
pm_finish
