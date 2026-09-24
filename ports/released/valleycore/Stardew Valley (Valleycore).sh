#!/bin/bash

########################################
# PortMaster Preamble
########################################
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

########################################
# Local setup
########################################
GAMEDIR="/$directory/ports/valleycore"

# CD and set logging
cd $GAMEDIR
> "$GAMEDIR/log.txt" && exec > >(tee "$GAMEDIR/log.txt") 2>&1

# Setup permissions
for f in \
    "$GAMEDIR/gamedata/Stardew Valley" \
    "$GAMEDIR/gamedata/StardewModdingAPI" \
    "$GAMEDIR/gamedata/patch.sh"
do
    [ -f "$f" ] && $ESUDO chmod +xwr "$f"
done

[ -f "$GAMEDIR/tools/splash" ] && $ESUDO chmod +xr "$GAMEDIR/tools/splash"

# Exports
export SDL_GAMECONTROLLERCONFIG="$sdl_controllerconfig"
export XDG_CONFIG_HOME="$GAMEDIR"

########################################
# System Requirement Check
########################################
sys_requirements_check() {
    # Minimum resolution
    if [ "$DISPLAY_WIDTH" -lt 1280 ]; then
        echo "Valleycore requires a widescreen resolution."
        return 1
    fi

    # Minimum RAM
    if [ "$DEVICE_RAM" -le 1 ]; then
        echo "Valleycore requires at least 2GB of RAM to run."
        return 1
    fi

    # Graphics requirements
    if ! command -v glxinfo >/dev/null 2>&1; then
        echo "Valleycore requires a mainline-compatible OpenGL stack (glxinfo not found)."
        return 1
    fi

    if ! glxinfo | grep -q "OpenGL version string"; then
        echo "Valleycore does not support the libMali graphics driver. Switch to Panfrost to continue."
        return 1
    fi
    
    # Correct game assets
    file_info=$(file "$GAMEDIR/gamedata/Stardew Valley")

    if echo "$file_info" | grep -q "PE32"; then
        echo "Please use the Linux 64-bit version of the game. See the README for details."
        return 1
    elif ! echo "$file_info" | grep -Eq "ELF 64-bit.*(x86-64|aarch64)"; then
        echo "Please use the Linux 64-bit version of the game. See the README for details."
        return 1
    fi
}

########################################
# Check ValleyCore Update
########################################
check_valleycore_update() {
	repo="a9ix/ValleyCore"
	version_file="$GAMEDIR/.install"

	# Fetch latest release metadata
	release_json=$(curl -s -H "Accept: application/vnd.github.v3+json" \
		"https://api.github.com/repos/${repo}/releases/latest")
	if [ -z "$release_json" ]; then
		echo "Failed to fetch release info"
		return 1
	fi

	# Extract tag name
	latest_tag=$(echo "$release_json" | grep -Po '"tag_name":\s*"\K[^"]+')
	if [ -z "$latest_tag" ]; then
		echo "Could not find tag_name in JSON"
		return 1
	fi

	# Read current version if any
	current_tag=""
	[ -f "$version_file" ] && current_tag=$(<"$version_file")

	if [ "$latest_tag" = "$current_tag" ]; then
		echo "ValleyCore is already up-to-date: $latest_tag"
		return 0
	fi

	# Find download URL for ValleyCore.tar.gz
	download_url=$(echo "$release_json" \
		| grep -iPo '"browser_download_url":\s*"\K[^"]*ValleyCore-SMAPI\.tar\.gz(?=")')
	if [ -z "$download_url" ]; then
		echo "No ValleyCore-SMAPI.tar.gz asset found in latest release"
		return 1
	fi

	echo "New ValleyCore release detected: $latest_tag"
	# Call download function
	download_valleycore "$latest_tag" "$download_url"
	return $?
}

########################################
# Download
########################################
download_valleycore() {
  latest_tag="$1"
  download_url="$2"
  archive_file="$GAMEDIR/ValleyCore-SMAPI.tar.gz"
  tmpfile="$GAMEDIR/ValleyCore.tar.gz.tmp"
  version_file="$GAMEDIR/.install"

  echo "Downloading ValleyCore $latest_tag from $download_url"

  if ! curl -L -o "$tmpfile" "$download_url"; then
	echo "Download failed, removing partial file"
	rm -f "$tmpfile"
	return 1
  fi

  mv "$tmpfile" "$archive_file"
  echo "$latest_tag" > "$version_file"
  echo "Downloaded version $latest_tag"
  return 0
}

########################################
# Extraction
########################################
extract_valleycore() {
	SEVENZIP="$GAMEDIR/tools/7zzs.${DEVICE_ARCH}"

	archive="$1"
	[ -f "$archive" ] || return 1

	mkdir -p "$GAMEDIR/gamedata"
	echo "Extracting $archive..."

	if "$SEVENZIP" x -y -aoa "$archive" -o"$GAMEDIR/gamedata"; then
		# Handle nested .tar
		inner_tar="$(ls "$GAMEDIR"/gamedata/*.tar 2>/dev/null | head -n 1)"
		if [ -f "$inner_tar" ]; then
			echo "Extracting inner tar: $inner_tar"
			if "$SEVENZIP" x -y -aoa "$inner_tar" -o"$GAMEDIR/gamedata"; then
				rm -f "$inner_tar"
			else
				echo "Failed to extract inner tar"
				return 1
			fi
		fi
		rm -f "$archive"
	else
		echo "Extraction failed for $archive"
		return 1
	fi
}

########################################
# Run system checks
########################################
sys_requirements_check || exit

# Check for updates
check_valleycore_update

# Extract if archive exists
archive="$(ls "$GAMEDIR"/ValleyCore*.tar.gz 2>/dev/null | head -n 1)"
[ -n "$archive" ] && extract_valleycore "$archive"

########################################
# Patch
########################################
if [ -f "$GAMEDIR/gamedata/patch.sh" ]; then
	if [ -f "$controlfolder/utils/patcher.txt" ]; then
		export PATCHER_FILE="$GAMEDIR/gamedata/patch.sh"
		export PATCHER_GAME="$(basename "${0%.*}")"
		export PATCHER_TIME="2 to 5 minutes"
		source "$controlfolder/utils/patcher.txt"
		touch .install && rm -rf "$GAMEDIR/gamedata/patch.sh"
		$ESUDO kill -9 $(pidof gptokeyb)
	else
		echo "This port requires the latest version of PortMaster."
	fi
fi

if [ -d "$GAMEDIR/gamedata/Mods" ]; then
    find "$GAMEDIR/gamedata/Mods" -type f -name "*.dll" | while read -r filepath; do
        # Patch only if needed by checking bytes
        arch=$(od -A n -j 0x85 -N 1 -t x1 "$filepath" 2>/dev/null | tr -d ' ')
        if [ "$arch" = "86" ]; then
            printf "\xaa" | dd of="$filepath" bs=1 seek=$((0x85)) conv=notrunc 2>/dev/null
			echo "Patched mod DLL: $(basename "$filepath")"
        fi
    done
fi

########################################
# Splash
########################################
if [ -f .install ]; then
	[ "$CFW_NAME" == "muOS" ] && $ESUDO "$GAMEDIR/tools/splash" "$GAMEDIR/splash.png" 1
	$ESUDO "$GAMEDIR/tools/splash" "$GAMEDIR/splash.png" 8000 & 
fi

########################################
# Determine executable
########################################
if [ -f "$GAMEDIR/gamedata/StardewModdingAPI" ]; then
	EXEC="StardewModdingAPI"
else
	EXEC="Stardew Valley"
fi

########################################
# Launch
########################################
$GPTOKEYB "$EXEC" -c "valleycore.gptk" &
pm_platform_helper "$GAMEDIR/gamedata/$EXEC" >/dev/null
./gamedata/"$EXEC"

# Cleanup
pm_finish
