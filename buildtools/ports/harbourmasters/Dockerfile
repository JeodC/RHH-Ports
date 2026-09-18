FROM rhh-base

RUN printf 'Acquire::ForceIPv4 "true";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99force-ipv4

# Clang-18 toolchain via the upstream LLVM apt script — focal's clang lags
# upstream point releases, and pinning all HarbourMasters ports to clang-18 keeps the
# toolchain consistent across SoH / 2s2h / Starship / SpaghettiKart / etc.
RUN apt update && apt install -y --no-install-recommends \
        gnupg software-properties-common
RUN for attempt in 1 2 3 4 5; do \
        wget -4 https://apt.llvm.org/llvm.sh && break; \
        echo "llvm.sh fetch failed (attempt $attempt); retrying" >&2; sleep $((attempt * 5)); \
    done && \
    test -s llvm.sh && \
    chmod +x llvm.sh && \
    ./llvm.sh 18 && \
    rm llvm.sh

# Autotools (opusfile's build), explicit libstdc++ version pin.
RUN apt install -y --no-install-recommends \
        libstdc++-10-dev autoconf automake libtool

# Common dev libs across all HarbourMasters ports.
#   - libsdl2-dev / libsdl2-net-dev are intentionally absent — every port
#     builds modern SDL2 (and SDL2_net where needed) from source so the
#     binary links against newer headers; at runtime the device's system
#     SDL2 satisfies the SONAME.
#   - libopus-dev / libopusfile-dev are absent for the same reason — built
#     from source via build_opus / build_opusfile so the binary picks up
#     /usr/local copies.
#   - libssl-dev is required by opusfile's ./configure (HTTPS URL fetching).
RUN apt install -y --no-install-recommends \
        libpng-dev libzip-dev \
        libogg-dev libvorbis-dev \
        libssl-dev \
        libboost-dev libopengl-dev \
        nlohmann-json3-dev libtinyxml2-dev libspdlog-dev \
        zipcmp zipmerge ziptool

ENV CC=clang-18
ENV CXX=clang++-18
ENV LD=lld-18
