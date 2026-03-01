FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install deps in single layer — includes ccache for faster rebuilds,
# g++-riscv64 for DuckDB (C++), and cmake/git for DuckDB build.
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

# ccache speeds up rebuilds dramatically (~30x on warm cache)
ENV CCACHE_DIR=/root/.cache/ccache
ENV CC="ccache gcc" CXX="ccache g++"
RUN ccache --set-config=max_size=2G

WORKDIR /qemu

# ── Stage 1: Copy QEMU source (excluding benchmarks/scripts/results) ──
# Editing benchmarks or scripts does NOT invalidate the expensive QEMU build.
COPY --exclude=benchmarks/ \
     --exclude=scripts/ \
     --exclude=results/ \
     --exclude=paper/ \
     --exclude=detect_false_sharing.py \
     --exclude=run_user_test.sh \
     . /qemu/

# Build QEMU: user-mode only, -j4 instead of -j2 for 2x faster compile
RUN mkdir -p build && cd build && \
    CC=gcc CXX=g++ ../configure \
        --target-list=riscv64-linux-user \
        --disable-system \
        --disable-docs \
        --disable-tools \
        --disable-guest-agent \
    && ninja -j4

# ── Stage 2: Copy frequently-changing files ──
COPY benchmarks/             /qemu/benchmarks/
COPY detect_false_sharing.py /qemu/
COPY run_user_test.sh        /qemu/

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

# ── Stage 3: Build DuckDB (real-world multithreaded database) ──
# Minimal build: only TPC-H extension + benchmark runner.
# Uses riscv64 cross-compiler for static RISC-V binary.
RUN git clone --depth=1 https://github.com/duckdb/duckdb.git /duckdb && \
    cd /duckdb && \
    BUILD_BENCHMARK=1 \
    BUILD_EXTENSIONS='tpch' \
    BUILD_PYTHON=0 \
    BUILD_SHELL=0 \
    BUILD_JDBC=0 \
    BUILD_ODBC=0 \
    DISABLE_SANITIZER=1 \
    GEN=ninja \
    CC='riscv64-linux-gnu-gcc' \
    CXX='riscv64-linux-gnu-g++' \
    CMAKE_VARS='-DCMAKE_EXE_LINKER_FLAGS=-static -DCMAKE_FIND_ROOT_PATH=/usr/riscv64-linux-gnu' \
    make release -j4 || echo "WARN: DuckDB build failed (optional)"  && \
    cp /duckdb/build/release/duckdb /qemu/benchmarks/duckdb.rv64 2>/dev/null || true && \
    cp /duckdb/build/release/benchmark/benchmark_runner /qemu/benchmarks/duckdb_bench.rv64 2>/dev/null || true && \
    rm -rf /duckdb

# addr2line for source-line resolution (riscv64 cross version)
RUN ln -sf /usr/bin/riscv64-linux-gnu-addr2line /usr/local/bin/addr2line

CMD ["bash"]
