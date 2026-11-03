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
GAMEDIR="/$directory/ports/descent3"

# CD and set permissions
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1
$ESUDO chmod +x "$GAMEDIR/game"

# Prepare game
bind_directories "$XDG_DATA_HOME/Outrage Entertainment/Descent 3" "$GAMEDIR/gamedata"
rm -rf "$GAMEDIR/gamedata/custom/cache/"
mkdir -p "$GAMEDIR/gamedata/custom/cache/"

# SDL3 shim
export LD_LIBRARY_PATH="$GAMEDIR/libs:$LD_LIBRARY_PATH"
if [ -n "$SDL_VIDEODRIVER" ]; then
  export SDL3SHIM_SDL2_VIDEODRIVER="$SDL_VIDEODRIVER"
  export SDL_VIDEODRIVER=sdl2
fi
if [ -n "$SDL_AUDIODRIVER" ]; then
  export SDL3SHIM_SDL2_AUDIODRIVER="$SDL_AUDIODRIVER"
  export SDL_AUDIODRIVER=sdl2
fi

# Run the game
$GPTOKEYB "game" -c "joy.gptk" &
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
pm_platform_helper "$GAMEDIR/game"

"$GAMEDIR/game" \
${DISPLAY_WIDTH:+-Width $DISPLAY_WIDTH -Height $DISPLAY_HEIGHT} \
-pilot Player \
-nooutragelogo \
-nomotionblur \
-logfile

# Cleanup
pm_finish