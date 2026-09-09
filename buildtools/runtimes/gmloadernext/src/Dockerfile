FROM debian:bullseye

ENV DEBIAN_FRONTEND=noninteractive

RUN SNAP=http://snapshot.debian.org/archive; STAMP=20260801T000000Z; \
    { echo "deb $SNAP/debian/$STAMP bullseye main"; \
      echo "deb $SNAP/debian/$STAMP bullseye-updates main"; \
      echo "deb $SNAP/debian-security/$STAMP bullseye-security main"; } > /etc/apt/sources.list && \
    dpkg --add-architecture arm64 && \
    apt-get -o Acquire::Check-Valid-Until=false -o Acquire::Retries=5 update && \
    apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
        ca-certificates curl wget git \
        build-essential pkg-config make cmake \
        binutils-aarch64-linux-gnu \
        gcc-aarch64-linux-gnu g++-aarch64-linux-gnu \
        libstdc++-10-dev-arm64-cross linux-libc-dev-arm64-cross \
        libzip-dev:arm64 libass-dev:arm64 \
        libasound2-dev:arm64 libpulse-dev:arm64 libudev-dev:arm64 \
        libdrm-dev:arm64 libgbm-dev:arm64 libgles2-mesa-dev:arm64 \
        libegl1-mesa-dev:arm64 libdbus-1-dev:arm64 libwayland-dev:arm64 \
        libxkbcommon-dev:arm64 \
        libx11-dev:arm64 libxext-dev:arm64 libxrandr-dev:arm64 \
        libxcursor-dev:arm64 libxfixes-dev:arm64 libxi-dev:arm64 libxss-dev:arm64 \
        libibus-1.0-dev:arm64 \
        python3 python3-clang \
        yasm nasm \
        squashfs-tools \
    && rm -rf /var/lib/apt/lists/*

# Build SDL2 from source.
ENV SDL2_VERSION=release-2.30.11
RUN cd /tmp && \
    git clone --depth 1 --branch ${SDL2_VERSION} https://github.com/libsdl-org/SDL.git && \
    cd SDL && mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_INSTALL_PREFIX=/usr \
          -DCMAKE_INSTALL_LIBDIR=lib/aarch64-linux-gnu \
          -DCMAKE_SYSTEM_NAME=Linux \
          -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
          -DCMAKE_C_COMPILER=aarch64-linux-gnu-gcc \
          -DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++ \
          -DSDL_SHARED=ON -DSDL_STATIC=OFF -DSDL_TEST=OFF \
          .. && \
    make -j"$(nproc)" && make install && \
    cd / && rm -rf /tmp/SDL

WORKDIR /root
CMD ["bash"]
