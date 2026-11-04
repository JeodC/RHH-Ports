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
GAMEDIR="/$directory/ports/hollow_knight_silksong"
BOX="$HOME/box"
BOX64="$BOX/box64"
GAME="Hollow Knight Silksong"

# CD and set log
cd "$GAMEDIR/data"
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Permissions
chmod +x "$GAMEDIR/tools/gptokeyb"
chmod +x "$GAME"

# Pre-flight checks for X11 and OpenGL. This is a Unity game — the westonwrap
# crusty GL bridge aborts it during graphics init, so it runs on native X11/GL
# only (hence the opengl requirement in port.json).
if [ -z "$DISPLAY" ]; then
    echo "Error: Display manager not found. Hollow Knight: Silksong requires OpenGL and X11 to run."
    exit 1
fi

if ! command -v glxinfo >/dev/null 2>&1; then
    echo "Error: OpenGL not found. Hollow Knight requires OpenGL and X11 to run."
    exit 1
else
    # Extract the OpenGL version number (e.g., "4.6" or "3.3")
    version=$(glxinfo | grep -oP 'OpenGL version string: \K[0-9]+\.[0-9]+' | head -n 1)

    # Split into major and minor version
    major=${version%%.*}
    minor=${version#*.}

    # Check if it's at least 3.3
    if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 3 ]; }; then
        # Spoof the GL version so we can launch the game
        export MESA_GL_VERSION_OVERRIDE=3.3
        export MESA_GLSL_VERSION_OVERRIDE=330
        export MESA_NO_ASYNC_COMPILE=1
        # Warn the user in log
        echo "[WARNING] Overriding GL version to run the game; this may have unintended side effects or performance issues!"
    fi
fi

# Mount box runtime (box64 + Box32, shared across box ports)
BOX_RUNTIME="$controlfolder/libs/box.squashfs"
if [ -f "$BOX_RUNTIME" ]; then
    $ESUDO mkdir -p "$BOX"
    $ESUDO umount "$BOX" 2>/dev/null || true
    $ESUDO mount "$BOX_RUNTIME" "$BOX"
else
    pm_message "This port requires the box runtime. Please update PortMaster."
    pm_finish
    exit 1
fi

# Display loading splash (from the box runtime)
[ "$CFW_NAME" == "muOS" ] && $ESUDO "$BOX/splash" "$GAMEDIR/splash.png" 1
$ESUDO "$BOX/splash" "$GAMEDIR/splash.png" 30000 &

# Exports
export LD_LIBRARY_PATH="$GAMEDIR/libs.aarch64:$GAMEDIR/data:$LD_LIBRARY_PATH"
export BOX64_LD_LIBRARY_PATH="$BOX/box64-x86_64-linux-gnu:$BOX/box64-i386-linux-gnu:$GAMEDIR/data:$LD_LIBRARY_PATH"
export XDG_CONFIG_HOME="$GAMEDIR/saves" && mkdir -p "$GAMEDIR/saves"
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
export SDL_VIDEODRIVER="x11"

# Box64 optimizations -- see https://github.com/ptitSeb/box64/blob/main/docs/USAGE.md
export BOX64_NOBANNER=1                # Hide Box64 startup banner (cleaner logs)
export BOX64_DYNAREC=1                 # Enable the JIT dynarec for x86_64 to ARM
export BOX64_DYNAREC_SAFEFLAGS=0       # Skip extra flag-preservation checks for speed
export BOX64_DYNAREC_FASTROUND=0       # Use precise IEEE rounding (safer than fast mode)
export BOX64_DYNAREC_CALLRET=2         # Disable CALL/RET optimizations (more compatible)
export BOX64_DYNAREC_DIRTY=1           # https://github.com/ptitSeb/box64/blob/main/docs/USAGE.md#box64_dynarec_dirty
export BOX64_DYNAREC_BIGBLOCK=3        # Merge more instructions per block (moderate aggressiveness)
export BOX64_DYNAREC_FORWARD=1024      # Scan up to X bytes ahead to extend blocks -- weaker CPUs may want this value lowered or disabled entirely
export BOX64_RDTSC_1GHZ=1              # Emulate RDTSC at 1 GHz for predictable timing
export BOX64_VSYNC=0                   # Allow Unity engine to control vsync

# OpenGL/Mesa error suppression (minor perf gain)
export MESA_NO_ERROR=1                 # Don’t check Mesa GL errors

# Use custom gptokeyb to fix d-pad
export GPTOKEYB="$GAMEDIR/tools/gptokeyb $ESUDOKILL"

# Ignore input plumber — only expose the gptokeyb virtual pad to the game
export SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT=0x045e/0x028e

# Run it
$GPTOKEYB "$GAME" xbox360 &
pm_platform_helper $GAME > /dev/null
$BOX64 "$GAMEDIR/data/$GAME" -force-opengl -screen-fullscreen 1 -screen-width $DISPLAY_WIDTH -screen-height $DISPLAY_HEIGHT

# Clean up after ourselves
$ESUDO umount "$BOX" 2>/dev/null
pm_finish
