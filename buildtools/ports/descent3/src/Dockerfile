FROM rhh-base

RUN apt install -y --no-install-recommends zlib1g-dev

# SDL 3.2 to link against. At runtime the shim below stands in for it.
ARG SDL3_TAG=release-3.2.30
RUN git clone --depth 1 --branch "$SDL3_TAG" https://github.com/libsdl-org/SDL.git /tmp/SDL3 \
 && cmake -S /tmp/SDL3 -B /tmp/SDL3/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TEST_LIBRARY=OFF -DSDL_TESTS=OFF \
 && cmake --build /tmp/SDL3/build \
 && cmake --install /tmp/SDL3/build \
 && rm -rf /tmp/SDL3

ARG SHIM_COMMIT=6057d79
COPY sdl3-sdl2-backend-fixes.patch /tmp/
RUN git clone https://github.com/bmdhacks/SDL.git -b sdl2-backend /tmp/shim \
 && cd /tmp/shim && git checkout "$SHIM_COMMIT" && git submodule update --init --recursive \
 && git apply /tmp/sdl3-sdl2-backend-fixes.patch \
 && cmake -S /tmp/shim -B /tmp/shim/build -G Ninja -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_FLAGS="-march=armv8-a" \
        -DSDL_SDL2_BACKEND=ON \
        -DSDL_X11=OFF -DSDL_WAYLAND=OFF -DSDL_KMSDRM=OFF \
        -DSDL_PIPEWIRE=OFF -DSDL_PULSEAUDIO=OFF -DSDL_ALSA=OFF \
        -DSDL_SNDIO=OFF -DSDL_OSS=OFF -DSDL_JACK=OFF \
        -DSDL_OFFSCREEN=OFF -DSDL_DUMMYVIDEO=OFF \
        -DSDL_DUMMYAUDIO=OFF -DSDL_DISKAUDIO=OFF \
        -DSDL_VULKAN=OFF -DSDL_GPU=OFF -DSDL_RENDER_GPU=OFF \
        -DSDL_UNIX_CONSOLE_BUILD=ON -DSDL_STATIC=OFF -DSDL_TEST_LIBRARY=OFF -DSDL_TESTS=OFF \
 && cmake --build /tmp/shim/build \
 && mkdir -p /opt/sdl3-shim && cp -L /tmp/shim/build/libSDL3.so.0 /opt/sdl3-shim/ \
 && rm -rf /tmp/shim

ARG PLOG_TAG=1.1.10
ARG GLM_TAG=1.0.1
# httplib's non-blocking DNS needs libanl before glibc 2.34, which its CMake package doesn't link
ARG HTTPLIB_TAG=v0.23.1
RUN git clone --depth 1 --branch "$PLOG_TAG" https://github.com/SergiusTheBest/plog.git /tmp/plog \
 && cmake -S /tmp/plog -B /tmp/plog/build -DPLOG_BUILD_SAMPLES=OFF \
 && cmake --install /tmp/plog/build \
 && git clone --depth 1 --branch "$GLM_TAG" https://github.com/g-truc/glm.git /tmp/glm \
 && cmake -S /tmp/glm -B /tmp/glm/build -DGLM_BUILD_TESTS=OFF -DGLM_BUILD_LIBRARY=OFF \
 && cmake --install /tmp/glm/build \
 && git clone --depth 1 --branch "$HTTPLIB_TAG" https://github.com/yhirose/cpp-httplib.git /tmp/httplib \
 && cmake -S /tmp/httplib -B /tmp/httplib/build \
        -DHTTPLIB_REQUIRE_OPENSSL=OFF -DHTTPLIB_USE_OPENSSL_IF_AVAILABLE=OFF \
        -DHTTPLIB_USE_ZLIB_IF_AVAILABLE=OFF -DHTTPLIB_USE_BROTLI_IF_AVAILABLE=OFF \
        -DHTTPLIB_USE_ZSTD_IF_AVAILABLE=OFF -DHTTPLIB_USE_NON_BLOCKING_GETADDRINFO=OFF \
 && cmake --install /tmp/httplib/build \
 && rm -rf /tmp/plog /tmp/glm /tmp/httplib
