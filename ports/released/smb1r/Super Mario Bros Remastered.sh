#!/bin/bash

XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}

# Detect PortMaster control folder
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

# Paths
GAMEDIR="/$directory/ports/smb1r"
CONFDIR="$GAMEDIR/config"
GPTK="$GAMEDIR/tools/mario-kb.gptk"

# CD and set up log and permissions
cd "$GAMEDIR"
exec > "$GAMEDIR/log.txt" 2>&1
$ESUDO chmod +x "$GAMEDIR/SMB1R.arm64"
$ESUDO chmod +x "$GAMEDIR/tools/splash"
$ESUDO chmod +r "$GAMEDIR/tools/crc32.py"

# Exports
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
export GODOT_SILENCE_ROOT_WARNING=1

# -- Display splash --
display_splash() {
    $ESUDO "$GAMEDIR/tools/splash" "$GAMEDIR/tools/$SPLASH" 10000 &
}

# -- GL Test --
gl_test() {
    if command -v glxinfo >/dev/null 2>&1; then
        version=$(glxinfo 2>/dev/null | grep -Eo 'OpenGL version string: [0-9]+\.[0-9]+' | awk '{print $4}' | head -n1)
        if [ -n "$version" ]; then
            major=${version%%.*}
            minor=${version#*.}
            if [ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 3 ]; }; then
                export MESA_GL_VERSION_OVERRIDE=3.3
                export MESA_GLSL_VERSION_OVERRIDE=330
            fi
        fi
    else
        echo "glxinfo not found — assuming limited OpenGL (using 3.3 fallback)."
        export MESA_GL_VERSION_OVERRIDE=3.3
        export MESA_GLSL_VERSION_OVERRIDE=330
    fi
    export MESA_NO_ASYNC_COMPILE=1
}

# --- ROM detection & validation (CRC32) ---
find_and_copy_rom() {
	VALID_CRC32S="3337EC46 393A432F"
	NES_DIR="/$directory/nes"

	check_crc() {
		local rom_path="$1"
		local crc
		crc=$($GAMEDIR/tools/crc32.py "$rom_path" | awk '{print $1}')
		echo "$VALID_CRC32S" | grep -q -i "$crc"
	}

	# 1. Check if a valid ROM already exists in $GAMEDIR
	for rom in "$GAMEDIR"/*.nes; do
		[ -e "$rom" ] || continue
		if check_crc "$rom"; then
			echo "Valid ROM already exists in $GAMEDIR. Nothing to do."
			return
		fi
	done

	# 2. Search NES directory for a valid ROM to copy
	for dir in "$NES_DIR"; do
		[ -d "$dir" ] || continue
		echo "Searching in $dir..."

		# 2a. Plain .nes files
		for rom in "$dir"/*.nes; do
			[ -e "$rom" ] || continue
			if check_crc "$rom"; then
				echo "Valid ROM found: $rom"
				cp "$rom" "$GAMEDIR"
				return
			fi
		done

		# 2b. .nes files inside zip archives
		for zip in "$dir"/*.zip; do
			[ -e "$zip" ] || continue
			echo "Checking zip: $zip"
			tmpfile=$(mktemp)
			unzip -Z1 "$zip" | grep -i '\.nes$' > "$tmpfile"
			while read -r nes_file; do
				tmpnes=$(mktemp)
				unzip -p "$zip" "$nes_file" > "$tmpnes" 2>/dev/null
				if check_crc "$tmpnes"; then
					echo "Valid ROM found inside zip: $zip -> $nes_file"
					cp "$tmpnes" "$GAMEDIR/$(basename "$nes_file")"
					rm -f "$tmpnes"
					rm -f "$tmpfile"
					return
				fi
				rm -f "$tmpnes"
			done < "$tmpfile"
			rm -f "$tmpfile"
		done
	done

	echo "No valid ROM found in $NES_DIR!"
	exit 1
}

# --- PCK verification ---
verify_pck() {
    local file="$1"
    if [ ! -f "$file" ]; then
        echo "Missing PCK file: $file"
        return 1
    fi

    # Read first 4 bytes (should be "GDPC")
    local magic
    magic=$(head -c4 "$file" | od -An -t x1 | tr -d ' \n')

    if [ "$magic" != "47445043" ]; then
        echo "Invalid PCK: bad header (expected GDPC)."
        return 1
    fi
    return 0
}

# --- Check for PCK updates ---
update_check() {
    # URLs for latest files
    remote_pck_url="https://raw.githubusercontent.com/JeodC/RHH-Ports/main/ports/released/smb1r/smb1r/SMB1R.pck"
    remote_bin_url="https://raw.githubusercontent.com/JeodC/RHH-Ports/main/ports/released/smb1r/smb1r/SMB1R.arm64"

    local_pck="$GAMEDIR/SMB1R.pck"
    local_bin="$GAMEDIR/SMB1R.arm64"
    etag_pck_file="$GAMEDIR/.SMB1R.pck.etag"
    etag_bin_file="$GAMEDIR/.SMB1R.arm64.etag"
    SPLASH="splash.png"

    echo "Checking for updates..."

    # --- Helper function to check & download a file ---
    check_and_update_file() {
        local remote_url="$1"
        local local_file="$2"
        local etag_file="$3"

        remote_etag=$(curl -sI -L "$remote_url" | grep -i '^etag:' | cut -d'"' -f2)
        if [ -z "$remote_etag" ]; then
            echo "Could not get remote ETag for $local_file. Skipping."
            return
        fi

        download_needed=0
        if [ ! -f "$local_file" ]; then
            echo "$local_file is missing. Will download."
            download_needed=1
            SPLASH="update.png"
        elif [ ! -f "$etag_file" ] || [ "$remote_etag" != "$(cat "$etag_file")" ]; then
            echo "Newer version of $local_file found. Will update."
            download_needed=1
            SPLASH="update.png"
        else
            echo "$local_file is up-to-date."
        fi
        
        display_splash

        if [ $download_needed -eq 1 ]; then
            echo "Downloading $local_file..."
            if curl -L -C - --retry 5 --retry-delay 5 --max-time 600 --progress-bar -o "$local_file" "$remote_url"; then
                chmod +rx "$local_file"
                echo "$remote_etag" > "$etag_file"
                echo "$local_file downloaded and updated."
            else
                echo "Failed to download $local_file!"
                [ ! -f "$local_file" ] && exit 1
            fi
        fi
    }

    # Check PCK
    check_and_update_file "$remote_pck_url" "$local_pck" "$etag_pck_file"

    # Check ARM64 binary
    check_and_update_file "$remote_bin_url" "$local_bin" "$etag_bin_file"
}

# Run update check
update_check
if [ -f "$GAMEDIR/config/baserom.nes" ]; then
    for rom in "$GAMEDIR"/*.nes; do
        [ -e "$rom" ] && rm -f "$rom"
    done
else
    find_and_copy_rom
fi

# Run the GL test
gl_test

# Mount Weston runtime
weston_dir=/tmp/weston
$ESUDO mkdir -p "$weston_dir"
weston_runtime="weston_pkg_0.2"

if [ ! -f "$controlfolder/libs/${weston_runtime}.squashfs" ]; then
	if [ ! -f "$controlfolder/harbourmaster" ]; then
		pm_message "This port requires the latest PortMaster to run, please go to https://portmaster.games/ for more info."
		sleep 5
		exit 1
	fi

	# Try quiet install
	if ! $ESUDO "$controlfolder/harbourmaster" --quiet --no-check runtime_check "${weston_runtime}.squashfs"; then
		pm_message "Failed to install the runtime automatically. Please update PortMaster or install '${weston_runtime}' manually."
		sleep 5
		exit 1
	fi
fi

if [ "$PM_CAN_MOUNT" != "N" ]; then
	$ESUDO umount "$weston_dir"
fi

$ESUDO mount "$controlfolder/libs/${weston_runtime}.squashfs" "$weston_dir"

# Disable gamepad for Knulli
case "$CFW_NAME" in
    *Knulli*)
        export LD_PRELOAD="$GAMEDIR/libs/hacksdl.so"
        export HACKSDL_NO_GAMECONTROLLER=1
        export HACKSDL_VERBOSE=0
        GPTK="$GAMEDIR/tools/mario-kb.gptk"
        ;;
esac

# Launch game
$GPTOKEYB "SMB1R.arm64" -c "$GPTK" &
$ESUDO env CRUSTY_BLOCK_INPUT=1 $weston_dir/westonwrap.sh headless noop kiosk crusty_x11egl \
	./SMB1R.arm64 \
	--resolution ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT} -f \
	--main-pack SMB1R.pck

# Clean up
$ESUDO $weston_dir/westonwrap.sh cleanup
if [ "$PM_CAN_MOUNT" != "N" ]; then
	$ESUDO umount "$weston_dir"
fi
pm_finish
