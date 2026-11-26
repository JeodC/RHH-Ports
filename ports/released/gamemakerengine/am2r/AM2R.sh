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
GAMEDIR="/$directory/ports/am2r"
PATCH_VERSION_FILE="$GAMEDIR/.patch_version"
UPDATE_CHECK_FILE="$GAMEDIR/.update_check"
RELEASES_URL="https://api.github.com/repos/PatchDev-AM2ARM/AM2ARM/releases"

# CD and set logging
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Mount gmloadernext runtime
GMLOADER="$HOME/gmloadernext"
GMLOADER_RUNTIME="$controlfolder/libs/gmloadernext.squashfs"
if [ -f "$GMLOADER_RUNTIME" ]; then
    $ESUDO mkdir -p "$GMLOADER"
    $ESUDO umount "$GMLOADER" 2>/dev/null || true
    $ESUDO mount "$GMLOADER_RUNTIME" "$GMLOADER"
else
    pm_message "This port requires the gmloadernext runtime. Please download it."
    pm_finish
    exit 1
fi

# Dual screen needs the runtime from 2026-11-25 or later
if ! grep -q DualScreen_Begin "$GMLOADER/lib/libdualscreen.so" 2>/dev/null; then
    pm_message "This port requires the latest gmloadernext runtime. Please update it."
    $ESUDO umount "$GMLOADER" 2>/dev/null || true
    pm_finish
    exit 1
fi

# Honor the update-check toggle the user set in the patcher screen.
update_check_enabled=1
if [ -f "$UPDATE_CHECK_FILE" ] && [ "$(cat "$UPDATE_CHECK_FILE" 2>/dev/null)" = "0" ]; then
    update_check_enabled=0
fi

# Check if we need to patch the game
need_patch=0
if [ ! -f am2r.port ] || [ ! -f "$PATCH_VERSION_FILE" ]; then
    need_patch=1
fi

check_upstream() {
    if [ "$update_check_enabled" = "1" ] || [ "$need_patch" = "1" ]; then
        UPSTREAM_ZIP=$(curl -fsSL --max-time 5 "$RELEASES_URL" 2>/dev/null | \
            grep -oE '"browser_download_url": *"[^"]+/AM2ARM-gmloader-[^"/]+\.zip"' | head -n 1 | cut -d'"' -f4
        )
        [ -n "$UPSTREAM_ZIP" ] && UPSTREAM_TAG=$(basename "$(dirname "$UPSTREAM_ZIP")")
    fi
}

#check_upstream

# Check for update, fall through if no connection or toggle is off
if [ "$need_patch" = "0" ] && [ -n "$UPSTREAM_TAG" ]; then
    stored_tag=$(cat "$PATCH_VERSION_FILE" 2>/dev/null)
    if [ "$UPSTREAM_TAG" != "$stored_tag" ]; then
        echo "============================================================"
        echo "Upstream release update detected: $stored_tag -> $UPSTREAM_TAG"
        echo "============================================================"
        need_patch=1
    fi
fi

# Patch if the game doesn't exist yet or we detected an update
if [ "$need_patch" = "1" ]; then
    if [ -f "$controlfolder/utils/patcher.txt" ]; then
        export PATCHER_FILE="$GAMEDIR/tools/patchscript"
        #[ -f "$UPDATE_CHECK_FILE" ] || export PATCHER_QUESTIONS="$GAMEDIR/tools/questions.lua"
        export PATCHER_GAME="$(basename "${0%.*}")"
        export PATCHER_TIME="1 to 5 minutes"
        export controlfolder ESUDO DEVICE_ARCH UPSTREAM_ZIP UPSTREAM_TAG
        chmod +x "$PATCHER_FILE"
        source "$controlfolder/utils/patcher.txt"
        $ESUDO kill -9 $(pidof gptokeyb)
    else
        echo "This port requires the latest version of PortMaster."
    fi
fi

# An am2r.port without a patch version is from the old port
if [ ! -f am2r.port ] || [ ! -f "$PATCH_VERSION_FILE" ]; then
    $ESUDO umount "$GMLOADER" 2>/dev/null || true
    pm_finish
    exit 1
fi

# Nano defaults on for slow devices. Only set when the device changes
mkdir -p saves
if [ "$(cat saves/device.txt 2>/dev/null)" != "$DEVICE_NAME $DEVICE_CPU" ]; then
    case "$DEVICE_NAME $DEVICE_CPU" in
        # RK3326 devices PortMaster doesn't list report Cortex-A35
        *RK3326*|*Cortex-A35*|*"RG DS"*|*RGDS*|*RG-DS*) NANO=1 ;;
        *) NANO=0 ;;
    esac
    if grep -q "^Nano=" saves/config.ini 2>/dev/null; then
        sed -i "s/^Nano=.*/Nano=$NANO/" saves/config.ini
    elif grep -q "^\[Screen\]" saves/config.ini 2>/dev/null; then
        sed -i "s/^\[Screen\].*/[Screen]\nNano=$NANO/" saves/config.ini
    else
        printf '\n[Screen]\nNano=%s\n' "$NANO" >> saves/config.ini
    fi
    echo "$DEVICE_NAME $DEVICE_CPU" > saves/device.txt
fi

# Exports
export GMLOADER_LIB_PATH="$GMLOADER/lib"
export LD_LIBRARY_PATH="$GMLOADER/lib:$LD_LIBRARY_PATH"
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"

# Assign gptokeyb and load the game
$GPTOKEYB "gmloadernext.aarch64" -c "am2r.gptk" &
pm_platform_helper "$GMLOADER/gmloadernext.aarch64" >/dev/null
"$GMLOADER/gmloadernext.aarch64" -c gmloader.json

# Cleanup
# Unmount gmloadernext runtime
$ESUDO umount "$GMLOADER" 2>/dev/null || true

pm_finish
