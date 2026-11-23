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
GAMEDIR="/$directory/ports/tomoyo_after"
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

# Create config dirs, keeping a real one (it has saves)
mkdir -p "$HOME/.rlvm"
SAVEDIRS="KEY\智代アフター KEY_智代アフター_EN_ALL"
for DIR in $SAVEDIRS; do
    [ -L "$HOME/.rlvm/$DIR" ] && rm -f "$HOME/.rlvm/$DIR"
    [ -d "$HOME/.rlvm/$DIR" ] || ln -s "$GAMEDIR/saves" "$HOME/.rlvm/$DIR"
done

# Check and modify Gameexe.ini
INI="$GAMEDIR/gamedata/Gameexe.ini"
if grep -q '#REGNAME = "KEY\智代アフター_EN_ALL"' $INI; then
    sed -i 's/#WAKU.001.TYPE=0/#WAKU.001.TYPE=5/' $INI
    sed -i 's/#WAKU.001.000.NAME="s_mw00d_convertible"/#WAKU.001.000.NAME="s_mw00d"/' $INI
    sed -i 's/#WAKU.001.000.BACK="s_mw00e_convertible"/#WAKU.001.000.BACK="s_mw00e"/' $INI
fi

# Setup controls
$GPTOKEYB "$RLVM/rlvm" -c "rlvm.gptk" &

# Run the game
pm_platform_helper "$RLVM/rlvm" > /dev/null
"$RLVM/rlvm" $FONT "$GAMEDIR/gamedata"

# Cleanup
pm_finish
