# Building touchHLE

This folder holds the patches for the `touchHLE` binary in the Command & Conquer: Red Alert (iPad) port. The port carries only the built files; rebuild them from here. The build starts from [touchHLE](https://github.com/touchHLE/touchHLE) v0.3.0 and runs on Ubuntu 20.04, so the binary needs nothing newer than GLIBC 2.30.

The patches change touchHLE's MPL-2.0 source files, so they are under the Mozilla Public License 2.0 too. Apply them in order:

| Patch | Change |
|--|--|
| `01-autorotation-callbacks.patch` | Send launch rotation callbacks to the root view controller (`--autorotation-callbacks`) |
| `02-stretch.patch` | Fill the screen in fullscreen (`--stretch`) |
| `03-gles1-native-window.patch` | Ask for a GLES window when `--gles1=gles1_native` is set |
| `04-virtual-cursor.patch` | A relative virtual cursor with D-pad and arrow options |
| `05-cursor-drag-button.patch` | A second cursor button for drag-select (`--cursor-drag-button=`) |
| `06-stick-gestures.patch` | Stick panning, edge scrolling and trigger pinching |
| `07-map-noreserve.patch` | Map guest memory with `MAP_NORESERVE` on Linux |
| `08-openal-no-sndio.patch` | Leave out openal-soft's SndIO backend, which devices don't ship |

## Build

From the repository root, build the shared `rhh-base` image if you don't have it, then open a shell in it with this folder mounted:

```bash
docker build --platform linux/aarch64 -t rhh-base -f buildtools/Dockerfile.base buildtools
docker run --rm -it --platform linux/aarch64 -v "$PWD/buildtools/touchhle:/host" rhh-base bash
```

Inside the container:

```bash
apt update && apt install -y --no-install-recommends gnupg software-properties-common libstdc++-10-dev libboost-dev
wget https://apt.llvm.org/llvm.sh && bash llvm.sh 18
export CC=clang-18 CXX=clang++-18

git clone --depth 1 --branch release-2.32.10 https://github.com/libsdl-org/SDL.git /tmp/SDL2
cmake -S /tmp/SDL2 -B /tmp/SDL2/build -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DSDL_TEST=OFF
cmake --build /tmp/SDL2/build && cmake --install /tmp/SDL2/build && ldconfig

curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
. "$HOME/.cargo/env"

git clone --branch v0.3.0 https://github.com/touchHLE/touchHLE.git && cd touchHLE
git submodule update --init --recursive vendor/dynarmic vendor/openal-soft vendor/stb
for patch in /host/*.patch; do git apply --verbose "$patch"; done

CARGO_PROFILE_RELEASE_LTO=fat CARGO_PROFILE_RELEASE_CODEGEN_UNITS=1 \
    cargo build --release --no-default-features --features touchHLE_openal_soft_wrapper/static
strip --strip-unneeded target/release/touchHLE

mkdir -p /host/out/licenses
cp target/release/touchHLE /host/out/
cp -r touchHLE_dylibs touchHLE_fonts /host/out/
cp LICENSE /host/out/licenses/LICENSE_touchHLE.txt
cp dev-scripts/gpl-3.0.txt /host/out/licenses/GPL-3.txt
target/release/touchHLE --copyright 2>&1 | sed -n '/^The following authorship/,$p' > /host/out/licenses/LICENSE_touchHLE_dependencies.txt
```

Copy the contents of `out/` into the port's `candcra/` folder.

## Checks

- `readelf -d target/release/touchHLE | grep NEEDED` lists only `libSDL2-2.0.so.0`, `libstdc++.so.6`, `libgcc_s.so.1` and glibc's own libraries. openal-soft is linked in, and SDL2 comes from the device.
- `objdump -T target/release/touchHLE | grep -o 'GLIBC_[0-9.]*' | sort -uV | tail -n 1` prints `GLIBC_2.30` or lower.
- Under QEMU on an x86 PC, `cargo build` takes about 30 minutes.
