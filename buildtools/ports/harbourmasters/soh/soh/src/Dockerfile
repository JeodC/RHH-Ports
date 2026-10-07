FROM rhh-base

RUN printf 'Acquire::ForceIPv4 "true";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99force-ipv4

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

RUN add-apt-repository -y ppa:ubuntu-toolchain-r/test && apt update && \
    apt install -y --no-install-recommends \
        libstdc++-11-dev autoconf automake libtool

RUN apt install -y --no-install-recommends \
        zlib1g-dev libogg-dev libvorbis-dev \
        libssl-dev

ENV CC=clang-18
ENV CXX=clang++-18
ENV LD=lld-18
