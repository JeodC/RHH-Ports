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

source "$controlfolder/control.txt"
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls

# Variables
GAMEDIR="/$directory/ports/zelda-ladxhd"
GAME="$GAMEDIR/data/LADXHD"
PATCH_VERSION_FILE="$GAMEDIR/data/.patch_version"
UPDATE_CHECK_FILE="$GAMEDIR/data/.update_check"
BACKUP_ZIP="$GAMEDIR/data/.backup/source.zip"
RELEASES_LATEST_URL="https://gitlab.com/api/v4/projects/bighead.0%2Fladxhd_updated/releases/permalink/latest"

# CD and set logging
cd "$GAMEDIR/data"
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Honor the update-check toggle the user set in the patcher screen.
update_check_enabled=1
if [ -f "$UPDATE_CHECK_FILE" ] && [ "$(cat "$UPDATE_CHECK_FILE" 2>/dev/null)" = "0" ]; then
    update_check_enabled=0
fi

# Discover upstream's latest stable release tag
# Skip the API call entirely when the toggle is off
# and if GAME is already patched
if [ "$update_check_enabled" = "1" ] || [ ! -f "$GAME" ]; then
    UPSTREAM_TAG=$(curl -fsSL --max-time 5 "$RELEASES_LATEST_URL" 2>/dev/null | \
        awk -F'"tag_name":"' '{if (NF>1) {split($2,a,"\""); print a[1]}}'
    )
fi

# Check for update, fall through if no connection or toggle is off
if [ "$update_check_enabled" = "1" ] && [ -f "$GAME" ] \
   && [ -f "$PATCH_VERSION_FILE" ] && [ -f "$BACKUP_ZIP" ]; then
    stored_tag=$(cat "$PATCH_VERSION_FILE" 2>/dev/null)
    if [ -n "$UPSTREAM_TAG" ] && [ -n "$stored_tag" ] && [ "$UPSTREAM_TAG" != "$stored_tag" ]; then
        echo "============================================================"
        echo "Upstream release update detected: $stored_tag -> $UPSTREAM_TAG"
        echo "Re-applying patches from preserved v1.0.0 base..."
        echo "============================================================"
        rm -f "$GAME"
    fi
fi

# Patch if game binary doesn't exist yet or we detected an update
if [ ! -f "$GAME" ]; then
    if [ -f "$controlfolder/utils/patcher.txt" ]; then
        export PATCHER_FILE="$GAMEDIR/tools/patchscript"
        [ -f "$UPDATE_CHECK_FILE" ] || export PATCHER_QUESTIONS="$GAMEDIR/tools/questions.lua"
        export PATCHER_GAME="$(basename "${0%.*}")" # This gets the current script filename without the extension
        export PATCHER_TIME="2 to 5 minutes"
        export controlfolder
        export ESUDO
        export DEVICE_ARCH
        export UPSTREAM_TAG
        source "$controlfolder/utils/patcher.txt"
        $ESUDO kill -9 $(pidof gptokeyb)
    else
        pm_message "This port requires the latest version of PortMaster."
    fi
fi

# Permissions
chmod +x "$GAME"

# Splash
if [ -f "$GAME" ]; then
	[ "$CFW_NAME" == "muOS" ] && $ESUDO "$GAMEDIR/tools/splash" "$GAMEDIR/splash.png" 1
	$ESUDO "$GAMEDIR/tools/splash" "$GAMEDIR/splash.png" 8000 & 
fi

# Request libGL
if [ -f "${controlfolder}/libgl_${CFW_NAME}.txt" ]; then
    source "${controlfolder}/libgl_${CFW_NAME}.txt"
else
    source "${controlfolder}/libgl_default.txt"
fi

if [ -n "$LIBGL_ES" ]; then
    export SDL_VIDEO_GL_DRIVER="${GAMEDIR}/gl4es/libGL.so.1"
    export SDL_VIDEO_EGL_DRIVER="${GAMEDIR}/gl4es/libEGL.so.1"
fi

# Exports
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
export LD_LIBRARY_PATH="$GAMEDIR/data:$LD_LIBRARY_PATH"
export XDG_DATA_HOME="$GAMEDIR"

swapabxy() {
    # Update SDL_GAMECONTROLLERCONFIG to swap a/b and x/y button

    if [ "$CFW_NAME" = "knulli" ] && [ -f "$SDL_GAMECONTROLLERCONFIG_FILE" ];then
        cat "$SDL_GAMECONTROLLERCONFIG_FILE" | swapabxy.py > "$GAMEDIR/gamecontrollerdb_swapped.txt"
	    export SDL_GAMECONTROLLERCONFIG_FILE="$GAMEDIR/gamecontrollerdb_swapped.txt"
    else
        export SDL_GAMECONTROLLERCONFIG="`echo "$SDL_GAMECONTROLLERCONFIG" | $GAMEDIR/tools/swapabxy.py`"
    fi
}

# Swap a/b and x/y button if needed
if [ -f "$GAMEDIR/swapabxy.txt" ]; then
    swapabxy
fi

# Run the game
$GPTOKEYB "LADXHD" -c "$GAMEDIR/zelda.gptk" &
pm_platform_helper "$GAME" >/dev/null

# OpenAL workaround: bundled libopenal.so requires GLIBC_2.34.
if [ -n "$CFW_GLIBC" ] && [ "$CFW_GLIBC" -lt 234 ] 2>/dev/null; then
    echo "[OpenAL] Checking system library..."

    SYSTEM_OPENAL=$(find /usr/lib /lib -name 'libopenal.so.1' -print -quit 2>/dev/null)

    if [ -n "$SYSTEM_OPENAL" ]; then
        echo "[OpenAL] Using $SYSTEM_OPENAL"
        DOTNET_CACHE="$HOME/.net/LADXHD"
        timeout 10 "$GAME" >/dev/null 2>&1
        find "$DOTNET_CACHE" -name 'libopenal.so' -exec sh -c '
            SYSTEM_OPENAL=$1
            shift
            for lib do
                rm -f "$lib"
                if ln -s "$SYSTEM_OPENAL" "$lib"; then
                    echo "[OpenAL] Replaced: $lib"
                else
                    echo "[OpenAL] ERROR: Failed: $lib"
                fi
            done
        ' sh "$SYSTEM_OPENAL" {} +
    else
        echo "[OpenAL] WARNING: No compatible libopenal.so.1 found."
    fi
fi

"$GAME"

# Cleanup
pm_finish
