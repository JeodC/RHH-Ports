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
GAMEDIR="/$directory/ports/candcra"

# CD and set permissions
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1
$ESUDO chmod +x "$GAMEDIR/touchHLE"

# Check for game data
APP=$(find "$GAMEDIR/gamedata" -maxdepth 1 \( -iname "*.ipa" -o -iname "*.app" \) | head -n 1)
if [ -z "$APP" ]; then
  pm_message "Copy your Red Alert for iPad .ipa into candcra/gamedata. See the README."
  sleep 5
  pm_finish
  exit 1
fi

# Request libGL
if [ -f "${controlfolder}/libgl_${CFW_NAME}.txt" ]; then
  source "${controlfolder}/libgl_${CFW_NAME}.txt"
else
  source "${controlfolder}/libgl_default.txt"
fi
GLES1=""
[ -n "$LIBGL_ES" ] && GLES1="--gles1=gles1_native"

# Zink is buggy, use freedreno
if [ "$MESA_LOADER_DRIVER_OVERRIDE" = "zink" ] && [ -f /usr/lib/dri/msm_dri.so ]; then
  export MESA_LOADER_DRIVER_OVERRIDE=msm
fi

# Sensitivity from controls.json
CONTROLS=()
if [ -f "$GAMEDIR/controls.json" ]; then
  while IFS=: read -r key value; do
    key=$(echo "$key" | tr -d '"[:space:]')
    value=$(echo "$value" | tr -d '[:space:]')
    case "$value" in ''|*[!0-9.]*) continue ;; esac
    if [ "$key" != deadzone ] && awk -v v="$value" 'BEGIN { exit v + 0 != 0 }'; then
      continue
    fi
    case "$key" in
      cursor_speed) CONTROLS+=("--virtual-cursor-relative=$value") ;;
      scroll_speed) CONTROLS+=("--stick-to-pan=$value") ;;
      edge_scroll_speed) CONTROLS+=("--edge-scroll=$value") ;;
      zoom_speed) CONTROLS+=("--triggers-to-pinch=$value") ;;
      deadzone) CONTROLS+=("--deadzone=$value") ;;
    esac
  done < <(grep -o '"[a-z_]*"[[:space:]]*:[[:space:]]*[0-9.]*' "$GAMEDIR/controls.json")
fi

# Run the game
$GPTOKEYB "touchHLE" -c "$GAMEDIR/candcra.gptk" &
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
pm_platform_helper "$GAMEDIR/touchHLE"

"$GAMEDIR/touchHLE" "$APP" --fullscreen --no-error-popup $GLES1 "${CONTROLS[@]}"

# Cleanup
pm_finish
