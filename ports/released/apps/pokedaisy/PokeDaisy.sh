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
GAMEDIR="/$directory/ports/pokedaisy"
GAME="$GAMEDIR/pokedaisy-linux"
PATCH_VERSION_FILE="$GAMEDIR/.patch_version"
UPDATE_CHECK_FILE="$GAMEDIR/.update_check"
RELEASE_URL="https://codeberg.org/pokedaisy/pokedaisy/releases/latest/download/pokedaisy-portmaster-aarch64.zip"

# CD and set logging
cd "$GAMEDIR"
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Check if we need to install PokeDaisy
need_patch=0
if [ ! -f "$GAME" ] || [ ! -f "$PATCH_VERSION_FILE" ]; then
    need_patch=1
fi

# Check for update, fall through if no connection or the user turned it off in the patcher screen
if [ "$need_patch" = "0" ] && [ "$(cat "$UPDATE_CHECK_FILE" 2>/dev/null)" != "0" ]; then
    # The latest release's link redirects to its tag
    upstream_zip=$(curl -fsS --max-time 5 -o /dev/null -w '%{redirect_url}' "$RELEASE_URL" 2>/dev/null)
    upstream_tag=$(basename "$(dirname "$upstream_zip")")
    stored_tag=$(cat "$PATCH_VERSION_FILE")
    if [ -n "$upstream_zip" ] && [ "$upstream_tag" != "$stored_tag" ]; then
        echo "============================================================"
        echo "Upstream release update detected: $stored_tag -> $upstream_tag"
        echo "============================================================"
        need_patch=1
    fi
fi

# Install if PokeDaisy doesn't exist yet or we detected an update
if [ "$need_patch" = "1" ]; then
    if [ -f "$controlfolder/utils/patcher.txt" ]; then
        export PATCHER_FILE="$GAMEDIR/tools/patchscript"
        [ -f "$UPDATE_CHECK_FILE" ] || export PATCHER_QUESTIONS="$GAMEDIR/tools/questions.lua"
        export PATCHER_GAME="PokéDaisy"
        export PATCHER_TIME="about a minute"
        export controlfolder ESUDO DEVICE_ARCH RELEASE_URL
        $ESUDO chmod +x "$PATCHER_FILE"
        source "$controlfolder/utils/patcher.txt"
    else
        pm_message "This port requires the latest version of PortMaster."
    fi
fi

# A failed update leaves the installed version in place
if [ ! -f "$GAME" ]; then
    pm_finish
    exit 1
fi

# The game list shows Pokemon games from the firmware's rom folders too. gbh, gbch and gbah are romhacks
case "$CFW_NAME" in
    muOS)   romsdir="/$directory/ROMS" ;;
    TrimUI) romsdir="/mnt/SDCARD/Roms" ;;
    Miyoo)  romsdir="/mnt/sdcard/Roms" ;;
    *)      romsdir="/$directory" ;;
esac
export POCKET_ROM_DIRS=$(find -L "$romsdir" -maxdepth 1 -type d | grep -iE '/(gb[ac]?h?|nds|game boy( color| advance)?|nintendo ds)$' | tr '\n' ':')

# PokeDaisy reads the face buttons by position. These firmwares map them by label, ROCKNIX unless its layout is changed
case "$CFW_NAME" in
    *ArkOS*|TheRA|RetroOZ) layout="nintendo" ;;
    ROCKNIX) layout=$(source /etc/profile.d/001-functions >/dev/null 2>&1; get_setting controller_layout); layout=${layout:-nintendo} ;;
esac
[ "$layout" = "nintendo" ] && export POCKET_FACE_LABELS=1

# Exports
export POCKET_FULLSCREEN=1
export POCKET_MENU_COMBO=off # Start+Select is PortMaster's exit
# Guide opens the menu. PortMaster's mapping for RK3566 devices leaves out their F button
export SDL_GAMECONTROLLERCONFIG=$(echo "$sdl_controllerconfig" | sed '/^190000004b4800000111000000010000,/{/guide:/!s/start:/guide:b10,start:/;}')

# Permissions
$ESUDO chmod +x "$GAME"

# Run PokeDaisy
mkdir -p roms saves states
$GPTOKEYB "pokedaisy-linux" &
pm_platform_helper "$GAME" >/dev/null
"$GAME" --data "$GAMEDIR"

# Cleanup
pm_finish
