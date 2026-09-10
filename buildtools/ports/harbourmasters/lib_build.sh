# Shared dependency-build helpers for HarbourMasters ports.
#
# Sourced by each port's src/build.txt at /root/buildtools/harbourmasters/lib_build.sh
# (the RHH-Ports repo root is bind-mounted at /root inside the build container).
#
# Provides:
#   project_clone               — clone the port repo, optionally with submodules,
#                                 honoring REPO_URL/REF/FORCE_HEAD
#   strip_upstream_cpu_option   — drop upstream's set(CPU_OPTION ...) so -DCPU_OPTION wins
#   project_configure_and_build — cmake configure + asset-generation target + main build
#   build_<dep>                 — clone, configure, build, and install a common dep into /usr/local
#   stage_libs                  — copy host libs into $PROJECT_BUILD_DIR/libs and verify NEEDED
#   fetch_gamecontrollerdb      — download a current SDL_GameControllerDB into the build dir
#
# Environment knobs:
#   PROJECT_URL  (optional) — fork URL to clone; default: caller-provided
#   REF          (optional) — branch/tag/SHA to check out
#   FORCE_HEAD   (optional) — "true" to skip latest-tag fallback and stay on HEAD
#   PROJECT_DIR=/root/build-port/project
#   DEPS_DIR=/root/build-port/deps
#   PROJECT_BUILD_DIR=$PROJECT_DIR/build
#
# Local-iteration knobs (see buildtools/Build-HMPort.ps1). These are all no-ops
# in CI, where every build gets a fresh container, so the same build.txt drives
# both paths:
#   RHH_LOCAL=1           — $PROJECT_DIR is a bind-mounted working copy: never
#                           clone, never move HEAD, build exactly what's there
#   RHH_SKIP_SUBMODULES=1 — don't touch submodules of that working copy
#   RHH_FORCE_DEPS=1      — rebuild deps even if a marker says they're installed

set -euo pipefail

PROJECT_DIR=${PROJECT_DIR:-/root/build-port/project}
DEPS_DIR=${DEPS_DIR:-/root/build-port/deps}
PROJECT_BUILD_DIR=${PROJECT_BUILD_DIR:-$PROJECT_DIR/build}

# Markers recording which deps are already installed into the prefix. Lives
# under /usr/local on purpose: a local run mounts a persistent volume there, so
# the markers survive exactly as long as the installed artifacts they describe.
RHH_DEP_MARKER_DIR=${RHH_DEP_MARKER_DIR:-/usr/local/.rhh-deps}

mkdir -p "$DEPS_DIR"

# _dep_marker <name> <identity...>
#   Marker path for <name>, keyed on everything that would change the build
#   (url, pinned ref, cmake args). Bump any of them and the old marker no
#   longer matches, so the dep rebuilds instead of silently going stale.
_dep_marker() {
    local name=$1
    shift
    local key
    key=$(printf '%s\0' "$@" | md5sum | cut -d' ' -f1)
    echo "$RHH_DEP_MARKER_DIR/$name-$key"
}

# _dep_cached <marker> — true if this exact dep/config is already installed.
_dep_cached() {
    [[ "${RHH_FORCE_DEPS:-0}" != "1" && -f "$1" ]]
}

_dep_mark_built() {
    mkdir -p "$RHH_DEP_MARKER_DIR"
    : > "$1"
}

# GitHub occasionally returns transient HTTP 500s during git clone. Retry with
# backoff so single failures don't abort the whole build.
git_clone_retry() {
    local attempt
    for attempt in 1 2 3 4 5; do
        if git clone "$@"; then
            return 0
        fi
        local delay=$((attempt * 5))
        echo "git clone failed (attempt $attempt); retrying in ${delay}s..." >&2
        sleep "$delay"
    done
    echo "git clone failed after 5 attempts" >&2
    return 1
}

# submodule_update_retry <git-submodule-update-flags...>
# Submodule init hits the same transient HTTP 500s as clone.
submodule_update_retry() {
    local attempt
    for attempt in 1 2 3 4 5; do
        if git -C "$PROJECT_DIR" submodule update "$@"; then
            return 0
        fi
        local delay=$((attempt * 5))
        echo "submodule update failed (attempt $attempt); retrying in ${delay}s..." >&2
        sleep "$delay"
    done
    echo "submodule update failed after 5 attempts" >&2
    return 1
}

# project_clone <default-url> [--recursive]
project_clone() {
    local default_url=$1
    local clone_flags=()
    local sm_flags=(--init)

    if [[ "${2:-}" == "--recursive" ]]; then
        clone_flags+=(--recursive)
        sm_flags+=(--recursive)
    fi

    # Local iteration: $PROJECT_DIR is your own working copy. Build what's
    # checked out — don't clone over it and don't move HEAD to a release tag.
    if [[ "${RHH_LOCAL:-0}" == "1" ]]; then
        if [[ ! -d "$PROJECT_DIR" ]]; then
            echo "project_clone: ERROR: RHH_LOCAL=1 but $PROJECT_DIR does not exist" >&2
            return 1
        fi
        echo ">>> project_clone: RHH_LOCAL=1, building working copy $PROJECT_DIR"
        git -C "$PROJECT_DIR" describe --always --dirty 2>/dev/null || true
        if [[ "${RHH_SKIP_SUBMODULES:-0}" == "1" ]]; then
            echo ">>> project_clone: RHH_SKIP_SUBMODULES=1, leaving submodules alone"
        else
            submodule_update_retry "${sm_flags[@]}"
        fi
        return 0
    fi

    if [[ -d "$PROJECT_DIR/.git" ]]; then
        echo ">>> project_clone: using existing checkout $PROJECT_DIR"
        submodule_update_retry "${sm_flags[@]}"
        return 0
    fi

    local url=${REPO_URL:-$default_url}
    echo ">>> project_clone: $url -> $PROJECT_DIR"
    git_clone_retry "${clone_flags[@]}" "$url" "$PROJECT_DIR"

    # Non-fatal: a tagless or tag-fetch-flaky remote shouldn't kill the build,
    # the latest-tag lookup below degrades to HEAD on its own.
    git -C "$PROJECT_DIR" fetch --tags ||
        echo ">>> project_clone: WARNING: fetch --tags failed, continuing" >&2

    if [[ -n "${REF:-}" ]]; then
        echo ">>> project_clone: checking out explicit ref $REF"
        git -C "$PROJECT_DIR" checkout "$REF"
    elif [[ "${FORCE_HEAD:-false}" == "true" ]]; then
        echo ">>> project_clone: FORCE_HEAD=true, staying on default branch HEAD"
    else
        local newest_tagged latest_tag=""
        newest_tagged=$(git -C "$PROJECT_DIR" rev-list --tags --max-count=1 || true)
        if [[ -n "$newest_tagged" ]]; then
            latest_tag=$(git -C "$PROJECT_DIR" describe --tags "$newest_tagged" || true)
        fi
        if [[ -n "$latest_tag" ]]; then
            echo ">>> project_clone: checking out latest tag $latest_tag"
            git -C "$PROJECT_DIR" checkout "$latest_tag"
        else
            echo ">>> project_clone: no tags found, staying on default branch HEAD" >&2
        fi
    fi

    submodule_update_retry "${sm_flags[@]}"
}

strip_upstream_cpu_option() {
    local cml="$PROJECT_DIR/CMakeLists.txt"
    local pattern='^[[:space:]]*set\(CPU_OPTION ' hits

    if [[ ! -f "$cml" ]]; then
        echo "strip_upstream_cpu_option: ERROR: $cml not found" >&2
        return 1
    fi

    hits=$(grep -cE "$pattern" "$cml" || true)
    if (( hits == 0 )); then
        if grep -qF '${CPU_OPTION}' "$cml"; then
            echo ">>> strip_upstream_cpu_option: already stripped"
            return 0
        fi
        echo "strip_upstream_cpu_option: ERROR: no CPU_OPTION at all in $cml" >&2
        echo "  Upstream changed how the CPU flag is chosen. Confirm -DCPU_OPTION still" >&2
        echo "  reaches target_compile_options before dropping this call." >&2
        return 1
    fi

    sed -i -E "/$pattern/d" "$cml"
    echo ">>> strip_upstream_cpu_option: removed $hits assignment(s)"
}

disable_upstream_scripting() {
    local cml="$PROJECT_DIR/CMakeLists.txt"
    local on='set(ENABLE_SCRIPTING ON CACHE' hits

    if [[ ! -f "$cml" ]]; then
        echo "disable_upstream_scripting: ERROR: $cml not found" >&2
        return 1
    fi

    hits=$(grep -cF "$on" "$cml" || true)
    if (( hits == 0 )); then
        if grep -qF 'set(ENABLE_SCRIPTING OFF CACHE' "$cml"; then
            echo ">>> disable_upstream_scripting: already off"
            return 0
        fi
        echo "disable_upstream_scripting: ERROR: no ENABLE_SCRIPTING assignment in $cml" >&2
        echo "  Upstream changed how scripting is enabled. Confirm TCC is still off" >&2
        echo "  before dropping this call, or the port regains the .tcc runtime." >&2
        return 1
    fi

    sed -i "s/$on/set(ENABLE_SCRIPTING OFF CACHE/" "$cml"
    if grep -qF "$on" "$cml"; then
        echo "disable_upstream_scripting: ERROR: patch did not take" >&2
        return 1
    fi
    echo ">>> disable_upstream_scripting: flipped $hits assignment(s) to OFF"
}

fix_upstream_ucustom_precision() {
    local dir="$PROJECT_DIR/libultraship/src/fast/shaders/opengl"
    local from='uniform vec4 uCustom[32];'
    local to='uniform highp vec4 uCustom[32];'
    local pat='uniform vec4 uCustom\[32\];'
    local f hits

    for f in "$dir/default.shader.glsl" "$dir/include/fast3d_vs.glsli"; do
        if [[ ! -f "$f" ]]; then
            echo "fix_upstream_ucustom_precision: ERROR: $f not found" >&2
            return 1
        fi

        hits=$(grep -cF "$from" "$f" || true)
        if (( hits == 0 )); then
            if grep -qF "$to" "$f"; then
                echo ">>> fix_upstream_ucustom_precision: ${f##*/} already highp"
                continue
            fi
            echo "fix_upstream_ucustom_precision: ERROR: no uCustom declaration in $f" >&2
            echo "  Upstream changed the uniform shared between VS and FS. Confirm both" >&2
            echo "  stages agree on precision before dropping this call, or Mesa refuses" >&2
            echo "  to link every program on GLES and the port renders black." >&2
            return 1
        fi
        if (( hits != 1 )); then
            echo "fix_upstream_ucustom_precision: ERROR: expected 1 declaration in $f, found $hits" >&2
            return 1
        fi

        sed -i "s/$pat/$to/" "$f"
        if grep -qF "$from" "$f" || ! grep -qF "$to" "$f"; then
            echo "fix_upstream_ucustom_precision: ERROR: patch did not take in $f" >&2
            return 1
        fi
        echo ">>> fix_upstream_ucustom_precision: ${f##*/} -> highp"
    done
}

# project_configure_and_build <generate-target> [extra cmake -D args...]
#   <generate-target>  — name of the asset-generation target (e.g. GenerateSohOtr,
#                        GeneratePortO2R), or "" to skip
project_configure_and_build() {
    local gen_target=$1
    shift
    local cmake_args=("$@")

    if command -v clang-18 >/dev/null 2>&1; then
        export CC=clang-18
        export CXX=clang++-18
    else
        export CC=clang
        export CXX=clang++
    fi

    echo ">>> project_configure_and_build: configuring"
    cmake -S "$PROJECT_DIR" -B "$PROJECT_BUILD_DIR" -GNinja "${cmake_args[@]}"

    if [[ -n "$gen_target" ]]; then
        echo ">>> project_configure_and_build: building asset target $gen_target"
        cmake --build "$PROJECT_BUILD_DIR" --target "$gen_target" -j"$(nproc)" -- -k 0
    fi

    echo ">>> project_configure_and_build: building main"
    cmake --build "$PROJECT_BUILD_DIR" -j"$(nproc)" -- -k 0
}

# _build_dep <name> <git-url> <ref> [extra cmake -D args...]
#   Clones into $DEPS_DIR/<name>, checks out <ref>, configures into <name>/build,
#   builds, installs into /usr/local.
_build_dep() {
    local name=$1 url=$2 ref=$3
    shift 3
    local extra_args=("$@")

    local src="$DEPS_DIR/$name"
    local build="$src/build"

    local marker
    marker=$(_dep_marker "$name" "$url" "$ref" "${extra_args[@]}")
    if _dep_cached "$marker"; then
        echo ">>> _build_dep $name: already installed at this ref/config, skipping"
        return 0
    fi

    if [[ -d "$src/.git" ]]; then
        echo ">>> _build_dep $name: already cloned, skipping fetch"
    else
        echo ">>> _build_dep $name: cloning $url"
        git_clone_retry "$url" "$src"
    fi

    # A cached $src may predate a bumped pin, in which case the ref isn't in
    # the local object store yet — fetch and retry before giving up.
    echo ">>> _build_dep $name: checking out $ref"
    if ! git -C "$src" checkout "$ref"; then
        echo ">>> _build_dep $name: $ref not present locally, fetching"
        git -C "$src" fetch --tags --force origin
        git -C "$src" checkout "$ref"
    fi

    echo ">>> _build_dep $name: configuring"
    cmake -S "$src" -B "$build" \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DBUILD_TESTING=OFF \
        "${extra_args[@]}"

    echo ">>> _build_dep $name: building"
    cmake --build "$build" -j"$(nproc)"

    echo ">>> _build_dep $name: installing"
    cmake --install "$build"

    _dep_mark_built "$marker"
}

build_sdl2() {
    _build_dep SDL https://github.com/libsdl-org/SDL.git release-2.32.0 \
        -DBUILD_SHARED_LIBS=ON \
        -DSDL_TEST=OFF \
        "$@"
}

build_sdl2_net() {
    _build_dep SDL_net https://github.com/libsdl-org/SDL_net.git release-2.2.0 \
        -DBUILD_SHARED_LIBS=ON "$@"
}

build_libzip() {
    _build_dep libzip https://github.com/nih-at/libzip.git \
        0581df510597b46c28509e9d4b5998cf5fecb636 \
        -DBUILD_TOOLS=OFF \
        -DBUILD_REGRESS=OFF \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_DOC=OFF \
        -DENABLE_OPENSSL=OFF \
        -DENABLE_GNUTLS=OFF \
        -DENABLE_MBEDTLS=OFF \
        -DENABLE_COMMONCRYPTO=OFF \
        -DENABLE_WINDOWS_CRYPTO=OFF \
        "$@"
}

build_json() {
    _build_dep json https://github.com/nlohmann/json.git \
        f3dc4684b40a124cabc8554967c2cd8db54f15dd \
        -DJSON_BuildTests=OFF \
        "$@"
}

build_bzip2() {
    _build_dep bzip2 https://github.com/libarchive/bzip2.git \
        1ea1ac188ad4b9cb662e3f8314673c63df95a589 "$@"
}

# tinyxml2: the installed cmake config conflicts with libultraship's own
# find_package mechanism; rename it post-install so downstream falls through
# to libultraship's path. Matches the original hm64-builder behavior.
build_tinyxml2() {
    local cfg="$DEPS_DIR/tinyxml2/cmake/tinyxml2-config.cmake"
    if [[ -f "$cfg.disabled" && ! -f "$cfg" ]]; then
        mv "$cfg.disabled" "$cfg"
    fi
    _build_dep tinyxml2 https://github.com/leethomason/tinyxml2.git \
        57ec94127bda7979282315b7d4b0059eeb6f3b5d \
        -DBUILD_SHARED_LIBS=ON "$@"
    if [[ -f "$cfg" ]]; then
        mv "$cfg" "$cfg.disabled"
    fi
}

build_opus() {
    _build_dep opus https://github.com/xiph/opus.git v1.5.2 \
        -DBUILD_SHARED_LIBS=ON \
        -DOPUS_BUILD_TESTING=OFF \
        "$@"
}

# opusfile uses autotools, not cmake — keep an inline helper so callers
# can still write `build_opusfile`.
build_opusfile() {
    local src="$DEPS_DIR/opusfile"
    local marker
    marker=$(_dep_marker opusfile https://github.com/xiph/opusfile.git master)
    if _dep_cached "$marker"; then
        echo ">>> build_opusfile: already installed, skipping"
        return 0
    fi
    if [[ ! -d "$src/.git" ]]; then
        echo ">>> build_opusfile: cloning"
        git_clone_retry https://github.com/xiph/opusfile.git "$src"
    fi
    # Subshell so a mid-build failure can't leave the caller in $src.
    (
        cd "$src"
        ./autogen.sh
        env -u LD PKG_CONFIG_PATH=/usr/local/lib/pkgconfig \
            ./configure --prefix=/usr/local \
                --disable-examples \
                --enable-shared --disable-static
        env -u LD make -j"$(nproc)"
        env -u LD make install
    )
    _dep_mark_built "$marker"
}

# openssl uses its own Perl Configure, not cmake — custom helper like opusfile.
# Built from source (3.5 LTS) rather than using focal's EOL 1.1.1 so we ship a
# current, patchable, known-provenance TLS stack. Installed shared into
# /usr/local; pass -DOPENSSL_ROOT_DIR=/usr/local to the project configure so
# downstream find_package(OpenSSL) (ixwebsocket's TLS) picks this over the
# system 1.1.1. no-docs/no-tests keeps the build lean.
build_openssl() {
    local src="$DEPS_DIR/openssl"
    local marker
    marker=$(_dep_marker openssl https://github.com/openssl/openssl.git openssl-3.5.6)
    if _dep_cached "$marker"; then
        echo ">>> build_openssl: already installed, skipping"
        return 0
    fi
    if [[ ! -d "$src/.git" ]]; then
        echo ">>> build_openssl: cloning"
        git_clone_retry --branch openssl-3.5.6 --depth 1 \
            https://github.com/openssl/openssl.git "$src"
    fi
    (
        cd "$src"
        # Explicit target (don't rely on ./config auto-detect); --libdir=lib so
        # it lands in /usr/local/lib, not lib64, matching our staging + find
        # paths.
        env -u LD ./Configure linux-aarch64 shared \
            --prefix=/usr/local \
            --openssldir=/usr/local/ssl \
            --libdir=lib \
            no-docs no-tests
        env -u LD make -j"$(nproc)"
        env -u LD make install_sw
    )
    _dep_mark_built "$marker"
}

build_fmt() {
    _build_dep fmt https://github.com/fmtlib/fmt.git 10.1.1 \
        -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
        -DFMT_TEST=OFF \
        -DFMT_DOC=OFF \
        "$@"
}

build_spdlog() {
    _build_dep spdlog https://github.com/gabime/spdlog.git \
        3335c380a08c5e0f5117a66622df6afdb3d74959 \
        -DSPDLOG_BUILD_TESTS=OFF \
        -DSPDLOG_BUILD_EXAMPLE=OFF \
        "$@"
}

build_gsl() {
    _build_dep GSL https://github.com/microsoft/GSL.git \
        2828399820ef4928cc89b65605dca5dc68efca6e \
        -DBUILD_SHARED_LIBS=ON \
        -DGSL_TEST=OFF \
        "$@"
}

HM_DEVICE_PROVIDED_LIBS="libSDL2-2.0.so.0 \
    libGL.so.1 libGLESv2.so.2 libGLESv1_CM.so.1 libEGL.so.1 \
    libOpenGL.so.0 libGLdispatch.so.0 libGLX.so.0 \
    libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1 libresolv.so.2 \
    ld-linux-aarch64.so.1 \
    libstdc++.so.6 libgcc_s.so.1 \
    libasound.so.2 libpulse.so.0 libpulse-simple.so.0 libjack.so.0"

# _hm_is_device_lib <soname>
_hm_is_device_lib() {
    [[ " $HM_DEVICE_PROVIDED_LIBS " == *" $1 "* ]]
}

# _hm_needed_of <elf-file>
#   Prints one DT_NEEDED soname per line. Errors if the file isn't a readable
#   ELF object — a silent empty result here would ship a port with no libs/.
_hm_needed_of() {
    if ! readelf -h "$1" >/dev/null 2>&1; then
        echo "stage_libs: ERROR: not a readable ELF object: $1" >&2
        return 1
    fi
    readelf -d "$1" | awk -F'[][]' '/NEEDED/ {print $2}'
}

# _hm_stage_needed <elf-file>
#   Recursive worker for stage_libs. Reads $_hm_libs_dir and the $_hm_seen map
#   from its caller's scope (bash dynamic scoping) — do not call directly.
_hm_stage_needed() {
    local needed lib src
    needed=$(_hm_needed_of "$1")

    while read -r lib; do
        [[ -z "$lib" ]] && continue

        # Already provided by the target device — don't ship, don't recurse.
        if _hm_is_device_lib "$lib"; then
            continue
        fi

        # Already staged (${x+_} form so an unset key is safe under `set -u`).
        if [[ -n "${_hm_seen[$lib]+_}" ]]; then
            continue
        fi

        if [[ -f "/usr/local/lib/$lib" ]]; then
            src="/usr/local/lib/$lib"
        elif [[ -f "/usr/lib/aarch64-linux-gnu/$lib" ]]; then
            src="/usr/lib/aarch64-linux-gnu/$lib"
        else
            echo "stage_libs: ERROR: cannot locate $lib" >&2
            return 1
        fi

        echo "Staging $lib"
        cp -L "$src" "$_hm_libs_dir/$lib"
        _hm_seen[$lib]=1

        # Recurse into this library's own dependencies.
        _hm_stage_needed "$_hm_libs_dir/$lib"
    done <<< "$needed"
}

stage_libs() {
    local binary_rel=$1
    local _hm_libs_dir="$PROJECT_BUILD_DIR/libs"
    local binary="$PROJECT_BUILD_DIR/$binary_rel"

    if [[ ! -f "$binary" ]]; then
        echo "stage_libs: ERROR: binary not found at $binary" >&2
        return 1
    fi

    # Start clean: a cached build dir must not leak stale sonames into the zip.
    rm -rf "$_hm_libs_dir"
    mkdir -p "$_hm_libs_dir"

    local -A _hm_seen=()

    _hm_stage_needed "$binary"

    # Closure check. Every DT_NEEDED of the binary and of everything we staged
    # must resolve to either a device-provided lib or a file in libs/. Without
    # this a miss only surfaces as a failed exec on the handheld.
    local missing=0 file lib
    for file in "$binary" "$_hm_libs_dir"/*; do
        # Skips the literal pattern when libs/ came out empty.
        [[ -f "$file" ]] || continue
        while read -r lib; do
            [[ -z "$lib" ]] && continue
            if _hm_is_device_lib "$lib"; then
                continue
            fi
            if [[ ! -f "$_hm_libs_dir/$lib" ]]; then
                echo "stage_libs: ERROR: $lib is NEEDED by ${file##*/} but not staged" >&2
                missing=1
            fi
        done <<< "$(_hm_needed_of "$file")"
    done

    if (( missing )); then
        return 1
    fi

    echo
    echo "Staged libraries:"
    ls -1 "$_hm_libs_dir"
}

# fetch_gamecontrollerdb
#   Pull a fresh SDL_GameControllerDB into the build dir so the shipped mapping
#   database tracks upstream instead of aging in the port payload.
#
#   Most HarbourMasters CMakeLists download this themselves, but some only do it
#   on a subset of platforms (Lighthouse: Darwin only), which leaves the Linux
#   build with nothing for retrieve-products to pick up. Calling this is safe
#   either way — it just overwrites whatever cmake did or didn't produce.
fetch_gamecontrollerdb() {
    local url=${1:-https://raw.githubusercontent.com/mdqinc/SDL_GameControllerDB/master/gamecontrollerdb.txt}
    local dest="$PROJECT_BUILD_DIR/gamecontrollerdb.txt"
    local tmp="$dest.tmp"

    mkdir -p "$PROJECT_BUILD_DIR"

    echo ">>> fetch_gamecontrollerdb: $url"
    # Checking the file as well as the exit code: not every curl build reports a
    # 404 as a failure, so an unwritten/empty output is the reliable tell.
    if ! curl -fsSL --retry 3 --retry-delay 2 -o "$tmp" "$url" || [[ ! -s "$tmp" ]]; then
        echo "fetch_gamecontrollerdb: ERROR: download failed" >&2
        rm -f "$tmp"
        return 1
    fi

    # A truncated or error-page response would ship a broken mapping db, so
    # sanity-check that we got something that actually looks like the database.
    if ! grep -q "platform:Linux" "$tmp"; then
        echo "fetch_gamecontrollerdb: ERROR: downloaded file has no Linux mappings" >&2
        rm -f "$tmp"
        return 1
    fi

    mv "$tmp" "$dest"
    echo ">>> fetch_gamecontrollerdb: $(wc -l < "$dest") lines"
}
