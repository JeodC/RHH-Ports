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

# Set variables — customize these four lines per port
GAMEDIR="/$directory/ports/portfolder"
GAME_BIN="GameName"            # the harbourmaster .elf or binary in $GAMEDIR
GAME_CFG="game.cfg.json"       # cvar file the engine reads
O2R_BASE="rom"                 # base ROM hash name — oot, mm, sf64, sm64, mk64, etc.
O2R_PORT="game.o2r"            # port-specific assets file shipped alongside the binary

# Exports
export LD_LIBRARY_PATH="$GAMEDIR/libs:$LD_LIBRARY_PATH"
export SDL_GAMECONTROLLERCONFIG=$sdl_controllerconfig

# Set up logging
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Permissions
$ESUDO chmod +x "$GAMEDIR/$GAME_BIN"
$ESUDO chmod +x "$GAMEDIR/tools/otrgen"

# Reset imgui windows so the menu doesn't open into a weird state.
# Skips the Main Game and Main - Deck windows (those need to stay full-size).
imgui_reset() {
    local input_file="imgui.ini"
    local temp_file="imgui_temp.ini"
    local skip_section=0
    while IFS= read -r line; do
        case "$line" in
            "[Window][Main Game]"*|"[Window][Main - Deck]"*) skip_section=1 ;;
            "[Window]"*) skip_section=0 ;;
        esac
        if [[ $skip_section -eq 0 ]]; then
            case "$line" in
                Pos=*) echo "Pos=30,30" >> "$temp_file" ;;
                Size=*) echo "Size=400,300" >> "$temp_file" ;;
                *) echo "$line" >> "$temp_file" ;;
            esac
        else
            echo "$line" >> "$temp_file"
        fi
    done < "$input_file"
    mv "$temp_file" "$input_file"
}

# Close the menu if open + force controller navigation on.
# Newer SoH-derived ports (Starship, Spaghettify, Ghostship, 2S2H) use
# "gControlNav" with a g-prefix. Original SoH uses bare "ControlNav".
if [ -f "$GAME_CFG" ]; then
    sed -i 's/"Menu": *1/"Menu": 0/' "$GAME_CFG"
    sed -i 's/"gOpenMenu": *1/"gOpenMenu": 0/' "$GAME_CFG"
    if grep -q '"gControlNav"' "$GAME_CFG"; then
        sed -i 's/"gControlNav":[[:space:]]*[0-9]*/"gControlNav": 1/' "$GAME_CFG"
    else
        sed -i '/"CVars":[[:space:]]*{/a\"gControlNav": 1,' "$GAME_CFG"
    fi
fi

# Force o2r regeneration if the binary or port-asset file is newer than the
# generated o2r — this keeps users on the right version after a port update.
if [ -f "$GAMEDIR/${O2R_BASE}.o2r" ]; then
    if { [ -f "$GAMEDIR/$GAME_BIN" ] && [ "$GAMEDIR/$GAME_BIN" -nt "$GAMEDIR/${O2R_BASE}.o2r" ]; } \
       || { [ -f "$GAMEDIR/$O2R_PORT" ] && [ "$GAMEDIR/$O2R_PORT" -nt "$GAMEDIR/${O2R_BASE}.o2r" ]; }; then
        echo "Notice: ${O2R_BASE}.o2r is older than $GAME_BIN and/or $O2R_PORT. Forcing regeneration."
        rm -f "$GAMEDIR/${O2R_BASE}.o2r"
        REGEN=1
        export REGEN
    fi
fi

# Generate o2r from the user's ROM if missing — uses PortMaster's patcher GUI
if [ ! -f "$GAMEDIR/${O2R_BASE}.o2r" ]; then
    if ls "$GAMEDIR/baseroms/"*.*64 1> /dev/null 2>&1; then
        if [ -f "$controlfolder/utils/patcher.txt" ]; then
            export PATCHER_FILE="$GAMEDIR/tools/otrgen"
            export PATCHER_GAME="$(basename "${0%.*}")"
            export PATCHER_TIME="5 to 10 minutes"
            export controlfolder
            export DEVICE_ARCH
            source "$controlfolder/utils/patcher.txt"
            pid=$(pidof gptokeyb) && [ -n "$pid" ] && $ESUDO kill -9 $pid
        else
            pm_message "This port requires the latest version of PortMaster."
        fi
    else
        pm_message "Missing ROM files in $GAMEDIR/baseroms! Can't generate o2r."
    fi
fi

# Bail if o2r still not present
if [ ! -f "$GAMEDIR/${O2R_BASE}.o2r" ]; then
    echo "No o2r found, can't run the game!"
    exit 1
fi

if [ -f "imgui.ini" ]; then
    imgui_reset
fi

# Run the game
$GPTOKEYB "$GAME_BIN" -c "game.gptk" &
pm_platform_helper "$GAMEDIR/$GAME_BIN" > /dev/null
./"$GAME_BIN"

# Cleanup
rm -rf "$GAMEDIR/logs"
pm_finish
