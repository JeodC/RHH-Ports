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
GAMEDIR="/$directory/ports/oracles-randomizer-ng"

# CD and set logging
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Setup permissions
$ESUDO chmod +x oracles-randomizer-ng
$ESUDO chmod +x love

# Exports
export OUTPUT="/$directory/gbc/randomized-${GAME}.gbc"
export LD_LIBRARY_PATH="$GAMEDIR/libs/lovelibs:$LD_LIBRARY_PATH"
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"

# Check for randomizer.zip
if [ -f "$GAMEDIR/randomizer.zip" ]; then
    echo "Extracting randomizer.zip..."
    if unzip randomizer.zip; then
        rm -f randomizer.zip
    fi
fi

# Check for roms
if [ ! -f "$GAMEDIR/randomizer/seasons.gbc" ] || [ ! -f "$GAMEDIR/randomizer/ages.gbc" ]; then
    export directory ESUDO
    source ./search
fi

# Run launcher
if [ -f "$GAMEDIR/randomizer/seasons.gbc" ] && [ -f "$GAMEDIR/randomizer/ages.gbc" ]; then
    $GPTOKEYB "love" &
    ./love .
fi

parse_options() {
    INI_FILE="options.ini"
    SECTION=""
    ARGS=""
    while IFS= read -r LINE; do
        # Strip comments and whitespace
        LINE="$(echo "$LINE" | cut -d'#' -f1 | tr -d '\r\n')"
        [ -z "$LINE" ] && continue

        case "$LINE" in
            \[*\])
                SECTION="$(echo "$LINE" | cut -d'[' -f2 | cut -d']' -f1)"
                continue
                ;;
        esac

        KEY="$(echo "$LINE" | cut -d'=' -f1)"
        VALUE="$(echo "$LINE" | cut -d'=' -f2- | sed 's/^"//;s/"$//')"

        case "$SECTION" in
            rom)
                [ "$KEY" = "1" ] && GAME="$VALUE"
                ;;
            flags)
                case "$KEY" in
                    hard)
                        [ "$VALUE" = "1" ] && ARGS="$ARGS -hard"
                        ;;
                    dungeons)
                        [ "$VALUE" = "1" ] && ARGS="$ARGS -dungeons"
                        ;;
                    keysanity)
                        [ "$VALUE" = "1" ] && ARGS="$ARGS -keysanity"
                        ;;
                    crossitems)
                        [ "$VALUE" = "1" ] && ARGS="$ARGS -crossitems"
                        ;;
                    portals)
                        [ "$VALUE" = "1" ] && ARGS="$ARGS -portals"
                        ;;
                    music)
                        # music can be "off", "on", or "all"
                        ARGS="$ARGS -music $VALUE"
                        ;;
                esac
                ;;
        esac
    done < "$INI_FILE"
    echo "[LOG]: Generated randomizer arguments: " $ARGS
}

# Cleanup launcher
if [ -f options.ini ]; then
    parse_options
    rm -f options.ini
    pm_finish
else
    exit
fi

# If Exit chosen from launcher, quit
if [ "$GAME" = "Exit" ]; then
    exit
fi

# Run the randomizer
./oracles-randomizer-ng $ARGS randomizer/"$GAME".gbc "$OUTPUT"

# Cleanup
pm_finish