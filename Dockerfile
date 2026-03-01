FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install deps — ccache for faster rebuilds, g++ for DuckDB
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential ninja-build pkg-config ccache \
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

# Build DuckDB benchmark (optional — best-effort)
RUN git clone --depth=1 --branch v1.2.1 https://github.com/duckdb/duckdb.git /tmp/duckdb && \
    cd /tmp/duckdb && mkdir build && cd build && \
    cmake .. -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_C_COMPILER=riscv64-linux-gnu-gcc \
        -DCMAKE_CXX_COMPILER=riscv64-linux-gnu-g++ \
        -DCMAKE_EXE_LINKER_FLAGS="-static" \
        -DBUILD_SHELL=1 \
        -DBUILD_BENCHMARKS=1 \
        -DDISABLE_SANITIZER=1 \
        -DBUILD_EXTENSIONS='tpch' \
    && ninja -j4 duckdb 2>&1 | tail -5 \
    && cp duckdb /qemu/benchmarks/duckdb.rv64 \
    || echo "WARN: DuckDB cross-compile failed (optional)" && \
    rm -rf /tmp/duckdb

# addr2line for source-line resolution
RUN ln -sf /usr/bin/riscv64-linux-gnu-addr2line /usr/local/bin/addr2line

CMD ["bash"]
