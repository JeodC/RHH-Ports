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

source "$controlfolder"/control.txt
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls

# Variables
GAMEDIR="/$directory/ports/pokewilds"
BINARY=java
JAR_PACKAGE="${GAMEDIR}/bin/app/pokewilds.jar"

# Logging
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Permissions
$ESUDO chmod +x "$GAMEDIR/tools/7za"
$ESUDO chmod +x "$GAMEDIR/tools/splash"
$ESUDO chmod +x "$GAMEDIR/tools/zramctl"

# Exports
export LD_LIBRARY_PATH="$GAMEDIR/libs:$LD_LIBRARY_PATH"
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
export XDG_DATA_HOME="$GAMEDIR/bin"
export LANG=en_US.utf8
export TEXTINPUTINTERACTIVE="Y"

cd "$GAMEDIR"/bin || exit

# Check RAM requirements
if [[ "$DEVICE_RAM" -lt "2" ]]; then
    pm_message "Pokewilds will not work without at least 2GB of memory."
    sleep 5
    exit 1
elif [[ "$DEVICE_RAM" -lt "3" ]]; then
    pm_message "Pokewilds may crash due to low memory. Proceed with caution."
    sleep 5
    # Setup zram if none is present (knulli might setup one)
    zram_count=`$ESUDO "$GAMEDIR/tools/zramctl" -n | wc -l`
    if [[ $zram_count -eq 0 ]]; then
        zram_device=`$ESUDO "$GAMEDIR/tools/zramctl" -f` && \
		$ESUDO "$GAMEDIR/tools/zramctl" $zram_device --size 1024M && \
		$ESUDO mkswap $zram_device && \
		$ESUDO swapon --discard --priority 20000 $zram_device
	fi
fi

# Check for the jar
if [[ ! -f $JAR_PACKAGE ]]; then
    pm_message "Pokewilds jar package missing. Please follow the readme installation steps."
    sleep 2
    exit 1
else
    if [[ -d "$GAMEDIR/patch" ]]; then
        # Patch in the modified classes to disable gamepad
        "$GAMEDIR/tools/7za" u "${JAR_PACKAGE}" "$GAMEDIR"/patch/*
    fi
fi

# Display loading splash
[ "$CFW_NAME" == "muOS" ] && $ESUDO "$GAMEDIR/tools/splash" "$GAMEDIR/splash.png" 1
$ESUDO "$GAMEDIR/tools/splash" "$GAMEDIR/splash.png" 2000 & 

# Check if we need to use westonpack. If we have mainline OpenGL, we don't need to use it.
if glxinfo | grep -q "OpenGL version string"; then
    westonpack=0
else
    westonpack=1
fi

if [ "$westonpack" -eq 1 ]; then
    # Mount Weston
    weston_dir=/tmp/weston
    $ESUDO mkdir -p "${weston_dir}"
    weston_runtime="weston_pkg_0.2"
    if [ ! -f "$controlfolder/libs/${weston_runtime}.squashfs" ]; then
        if [ ! -f "$controlfolder/harbourmaster" ]; then
            pm_message "This port requires the latest PortMaster to run, please go to https://portmaster.games/ for more info."
            sleep 5
            exit 1
        fi
        $ESUDO "$controlfolder"/harbourmaster --quiet --no-check runtime_check "${weston_runtime}.squashfs"
    fi
    if [[ "$PM_CAN_MOUNT" != "N" ]]; then
        $ESUDO umount "${weston_dir}"
    fi
    $ESUDO mount "$controlfolder/libs/${weston_runtime}.squashfs" "${weston_dir}"
fi

# JRE load runtime
runtime="zulu17.54.21-ca-jre17.0.13-linux"
export JAVA_HOME="$HOME/zulu17.54.21-ca-jre17.0.13-linux.aarch64"
$ESUDO mkdir -p "${JAVA_HOME}"

if [ ! -f "$controlfolder/libs/${runtime}.squashfs" ]; then
  # Check for runtime if not downloaded via PM
  if [ ! -f "$controlfolder/harbourmaster" ]; then
    pm_message "This port requires the latest PortMaster to run, please go to https://portmaster.games/ for more info."
    sleep 5
    exit 1
  fi

  $ESUDO "$controlfolder"/harbourmaster --quiet --no-check runtime_check "${runtime}.squashfs"
fi

if [[ "$PM_CAN_MOUNT" != "N" ]]; then
    $ESUDO umount "${JAVA_HOME}"
fi

$ESUDO mount "$controlfolder/libs/${runtime}.squashfs" "${JAVA_HOME}"
export PATH="$JAVA_HOME/bin:$PATH"

# Zink is buggy, use freedreno
if [ "$MESA_LOADER_DRIVER_OVERRIDE" = "zink" ] && [ -f /usr/lib/dri/msm_dri.so ]; then
  export MESA_LOADER_DRIVER_OVERRIDE=msm
fi

if [ "$CFW_NAME" = "ROCKNIX" ]; then
  ( for i in $(seq 60); do sleep 1; swaymsg -q '[class="PokeWilds"] fullscreen enable' 2>/dev/null && break; done ) &
fi

# Run the game
$GPTOKEYB "$BINARY" -c "$GAMEDIR/pokewilds.gptk" &
pm_platform_helper "$JAVA_HOME/bin/java" >/dev/null
if [ "$westonpack" -eq 1 ]; then 
	$ESUDO env SDL_NO_SIGNAL_HANDLERS=1 WRAPPED_LIBRARY_PATH="$GAMEDIR/libs:$LD_LIBRARY_PATH" WESTON_HEADLESS_WIDTH="$DISPLAY_WIDTH" WESTON_HEADLESS_HEIGHT="$DISPLAY_HEIGHT" \
    "$weston_dir"/westonwrap.sh headless noop kiosk crusty_glx_gl4es \
    PATH="$PATH" JAVA_HOME="$JAVA_HOME" XDG_DATA_HOME="$GAMEDIR/bin" java -Xmx612M -jar "${JAR_PACKAGE}"
	$ESUDO "$weston_dir"/westonwrap.sh cleanup
else
	PATH="$PATH" JAVA_HOME="$JAVA_HOME" XDG_DATA_HOME="$GAMEDIR/bin" java -Xmx612M -jar "${JAR_PACKAGE}"
fi

# Cleanup
if [[ ! -z $zram_device ]]; then
  $ESUDO swapoff $zram_device
  $ESUDO "$GAMEDIR/tools/zramctl" -r $zram_device
fi
pm_finish