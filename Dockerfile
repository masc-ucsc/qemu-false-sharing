FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install deps — g++-riscv64 for DuckDB, cmake/git for DuckDB clone
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential ninja-build pkg-config \
    libglib2.0-dev libpixman-1-dev \
    python3 python3-venv python3-tomli \
    gcc-riscv64-linux-gnu g++-riscv64-linux-gnu \
    binutils-riscv64-linux-gnu \
    libc6-dev-riscv64-cross libstdc++-12-dev-riscv64-cross \
    cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /qemu
COPY . /qemu/

# Build QEMU: user-mode only, -j4 for speed
RUN mkdir -p build && cd build && \
    ../configure \
        --target-list=riscv64-linux-user \
        --disable-system \
        --disable-docs \
        --disable-tools \
        --disable-guest-agent \
    && ninja -j4

# Cross-compile all C benchmarks as static RISC-V binaries
RUN riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/false_sharing.c     -o benchmarks/false_sharing.rv64     && \
    riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/true_sharing.c      -o benchmarks/true_sharing.rv64      && \
    riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/deadlock.c          -o benchmarks/deadlock.rv64          && \
    riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/parallel_compress.c -o benchmarks/parallel_compress.rv64 && \
    riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/word_count.c        -o benchmarks/word_count.rv64        && \
    riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/parallel_sort.c     -o benchmarks/parallel_sort.rv64

# Build DuckDB v1.2.1 for RISC-V (real-world multithreaded OLAP database).
# Uses a CMake toolchain file; skips jemalloc (uses x86 'pause' instruction).
RUN printf '%s\n' \
    'set(CMAKE_SYSTEM_NAME Linux)' \
    'set(CMAKE_SYSTEM_PROCESSOR riscv64)' \
    'set(CMAKE_C_COMPILER riscv64-linux-gnu-gcc)' \
    'set(CMAKE_CXX_COMPILER riscv64-linux-gnu-g++)' \
    'set(CMAKE_FIND_ROOT_PATH /usr/riscv64-linux-gnu)' \
    'set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)' \
    'set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)' \
    'set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)' \
    'set(CMAKE_EXE_LINKER_FLAGS "-static -pthread")' \
    > /tmp/riscv64-toolchain.cmake && \
    git clone --depth=1 --branch v1.2.1 https://github.com/duckdb/duckdb.git /tmp/duckdb && \
    cd /tmp/duckdb && mkdir build && cd build && \
    cmake .. -G Ninja \
        -DCMAKE_TOOLCHAIN_FILE=/tmp/riscv64-toolchain.cmake \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHELL=1 \
        -DBUILD_UNITTESTS=0 \
        -DBUILD_BENCHMARKS=0 \
        -DBUILD_PYTHON=0 \
        -DBUILD_EXTENSIONS='' \
        -DSKIP_EXTENSIONS='jemalloc' \
        -DENABLE_UBSAN=0 \
        -DENABLE_THREAD_SANITIZER=0 \
    && ninja -j4 duckdb \
    && cp duckdb /qemu/benchmarks/duckdb.rv64 \
    && rm -rf /tmp/duckdb /tmp/riscv64-toolchain.cmake \
    || { echo "WARN: DuckDB cross-compile failed (optional)"; rm -rf /tmp/duckdb; }

# addr2line for source-line resolution
RUN ln -sf /usr/bin/riscv64-linux-gnu-addr2line /usr/local/bin/addr2line

CMD ["bash"]
