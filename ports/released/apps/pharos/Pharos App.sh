#!/bin/bash

XDG_DATA_HOME=${XDG_DATA_HOME:-${HOME}/.local/share}

if [ -d "/opt/system/Tools/PortMaster/" ]; then
    controlfolder="/opt/system/Tools/PortMaster"
elif [ -d "/opt/tools/PortMaster/" ]; then
    controlfolder="/opt/tools/PortMaster"
elif [ -d "${XDG_DATA_HOME}/PortMaster/" ]; then
    controlfolder="${XDG_DATA_HOME}/PortMaster"
else
    controlfolder="/roms/ports/PortMaster"
fi

source "${controlfolder}/control.txt"
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls

# Variables
GAMEDIR="/${directory}/ports/pharos"
GAMEPARENT="${GAMEDIR%/*}"
PENDING_ZIP="${GAMEDIR}/.pending_update.zip"
LOG_DIR="${GAMEDIR}/logs"
RUN_LOG="${LOG_DIR}/$(date +'%Y-%m-%d').log"

# Find the launcher path
SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null)"
[ -z "${SCRIPT_PATH}" ] && SCRIPT_PATH="$0"
SCRIPT_DIR="$(dirname "${SCRIPT_PATH}")"
SCRIPT_NAME="$(basename "${SCRIPT_PATH}")"

cd "${GAMEDIR}" || exit 1

mkdir -p "${LOG_DIR}"

# Exports
export XDG_DATA_HOME="${GAMEDIR}"
export LOG_FILE="${RUN_LOG}"
export SDL_GAMECONTROLLERCONFIG="${sdl_controllerconfig}"
export PYSDL2_DLL_PATH="/usr/lib"
export LD_LIBRARY_PATH="${GAMEDIR}/libs:${LD_LIBRARY_PATH}"
export controlfolder
export DEVICE_ARCH
export TMPDIR="${GAMEDIR}/tmp"
mkdir -p "${TMPDIR}"

notify() {
    if command -v pm_message >/dev/null 2>&1; then
        pm_message "$1"
    fi
    echo "[Pharos.sh] $(date '+%H:%M:%S') $1" >> "${RUN_LOG}"
}

# PortMaster closes the pm_message dialog from an EXIT trap, and `exec` does not
# run EXIT traps, so the re-exec below has to close it here or pugwash is orphaned.
notify_end() {
    if command -v pm_message_end >/dev/null 2>&1; then
        pm_message_end
    fi
}

apply_pending_update() {
    seven_zip="${controlfolder}/7zzs.${DEVICE_ARCH}"
    tmpdir=""

    if [ ! -x "${seven_zip}" ]; then
        notify "Update apply: 7zzs not found at ${seven_zip}."
        rm -f "${PENDING_ZIP}"
        return 1
    fi

    if ! "${seven_zip}" t "${PENDING_ZIP}" >>"${RUN_LOG}" 2>&1; then
        notify "Update apply: pending zip is corrupt; deleted."
        rm -f "${PENDING_ZIP}"
        return 1
    fi

    tmpdir="$(mktemp -d 2>/dev/null)"
    [ -z "${tmpdir}" ] && tmpdir="${LOG_DIR}/.update_tmp.$$"
    mkdir -p "${tmpdir}" 2>/dev/null

    notify "Applying Pharos update..."
    if ! "${seven_zip}" x -y "${PENDING_ZIP}" -o"${tmpdir}" >>"${RUN_LOG}" 2>&1; then
        notify "Update apply: extraction failed; see ${RUN_LOG}."
        rm -rf "${tmpdir}"
        rm -f "${PENDING_ZIP}"
        return 1
    fi

    # --- Data dir ---
    if [ ! -d "${tmpdir}/pharos" ]; then
        notify "Update apply: zip is missing pharos/ directory; aborting."
        rm -rf "${tmpdir}"
        rm -f "${PENDING_ZIP}"
        return 1
    fi
    if ! cp -rf "${tmpdir}/pharos/." "${GAMEDIR}/" >>"${RUN_LOG}" 2>&1; then
        notify "Update apply: data copy failed; see ${RUN_LOG}."
        rm -rf "${tmpdir}"
        rm -f "${PENDING_ZIP}"
        return 1
    fi

    # --- Launcher ---
    launcher_in_zip="$(ls "${tmpdir}"/*.sh 2>/dev/null | head -n1)"
    launcher_name="${SCRIPT_NAME}"
    if [ -n "${launcher_in_zip}" ] && [ -f "${launcher_in_zip}" ]; then
        launcher_name="$(basename "${launcher_in_zip}")"
        # Stage to a sibling .new then rename - atomic on the same FS,
        # so the in-flight `exec` below never sees a half-written script.
        if cp -f "${launcher_in_zip}" "${SCRIPT_DIR}/${launcher_name}.new" >>"${RUN_LOG}" 2>&1 \
           && chmod +x "${SCRIPT_DIR}/${launcher_name}.new" >>"${RUN_LOG}" 2>&1 \
           && mv -f "${SCRIPT_DIR}/${launcher_name}.new" "${SCRIPT_DIR}/${launcher_name}" >>"${RUN_LOG}" 2>&1; then
            :
        else
            notify "Update apply: launcher swap failed at ${SCRIPT_DIR}; old launcher kept."
            rm -f "${SCRIPT_DIR}/${launcher_name}.new"
            launcher_name="${SCRIPT_NAME}"
        fi
        # If the launcher was renamed across versions, drop the old one.
        if [ "${launcher_name}" != "${SCRIPT_NAME}" ] && [ -f "${SCRIPT_DIR}/${SCRIPT_NAME}" ]; then
            rm -f "${SCRIPT_DIR}/${SCRIPT_NAME}"
        fi
        # Mirror into ${GAMEPARENT} too if that's a separate location
        # and a launcher already exists there.
        if [ "${SCRIPT_DIR}" != "${GAMEPARENT}" ] && [ -f "${GAMEPARENT}/${launcher_name}" ]; then
            cp -f "${SCRIPT_DIR}/${launcher_name}" "${GAMEPARENT}/${launcher_name}" >>"${RUN_LOG}" 2>&1
            chmod +x "${GAMEPARENT}/${launcher_name}" >>"${RUN_LOG}" 2>&1
        fi
    fi

    rm -rf "${tmpdir}"
    rm -f "${PENDING_ZIP}"
    chmod +x "${GAMEDIR}/Pharos" 2>>"${RUN_LOG}"
    export _PHAROS_UPDATE_APPLIED=1
    notify_end
    exec "${SCRIPT_DIR}/${launcher_name}" "$@"
}

# Pre-launch apply: catches the path where the user came back to the menu
# and re-launched manually after a previous download.
if [ -f "${PENDING_ZIP}" ] && [ -z "${_PHAROS_UPDATE_APPLIED}" ]; then
    apply_pending_update "$@"
fi

# Defensive +x on the binary.
chmod +x "${GAMEDIR}/Pharos"

# Run
pm_platform_helper "${GAMEDIR}/Pharos" > /dev/null
"${GAMEDIR}/Pharos" "${GAMEDIR}/.sources" >>"${RUN_LOG}" 2>&1

# Post-exit apply
if [ -f "${PENDING_ZIP}" ]; then
    apply_pending_update "$@"
fi

# Cleanup
rm -rf "${tmpdir}"
pm_finish
