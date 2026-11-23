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
GAMEDIR="/$directory/ports/planetarian"
DEVICE_ARCH="${DEVICE_ARCH:-aarch64}"

# CD and set logging
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Setup RLVM
RLVM="$HOME/rlvm"
RLVM_RUNTIME="$controlfolder/libs/rlvm-sdl2.squashfs"
FONT="--font $RLVM/fonts/sazanami-gothic.ttf"
FONT2="--font $RLVM/fonts/DejaVuSans.ttf"
if [ -f "$RLVM_RUNTIME" ]; then
    $ESUDO mkdir -p "$RLVM"
    $ESUDO umount "$RLVM" 2>/dev/null || true
    $ESUDO mount "$RLVM_RUNTIME" "$RLVM"
else
    pm_message "This port requires the rlvm runtime. Please download it."
    pm_finish
    exit 1
fi

# Exports
export LD_LIBRARY_PATH="$RLVM/libs:$LD_LIBRARY_PATH"

# Request libGL
if [ -f "${controlfolder}/libgl_${CFW_NAME}.txt" ]; then
    source "${controlfolder}/libgl_${CFW_NAME}.txt"
else
    source "${controlfolder}/libgl_default.txt"
fi

# Create config dir, keeping a real one (it has saves)
mkdir -p "$HOME/.rlvm"
[ -L "$HOME/.rlvm/KEY_planetarian_ME" ] && rm -f "$HOME/.rlvm/KEY_planetarian_ME"
[ -d "$HOME/.rlvm/KEY_planetarian_ME" ] || ln -s "$GAMEDIR/saves" "$HOME/.rlvm/KEY_planetarian_ME"

# Setup controls
$GPTOKEYB "$RLVM/rlvm" -c "rlvm.gptk" &

# Run the game
pm_platform_helper "$RLVM/rlvm" > /dev/null
"$RLVM/rlvm" $FONT "$GAMEDIR/gamedata"

# Cleanup
pm_finish
