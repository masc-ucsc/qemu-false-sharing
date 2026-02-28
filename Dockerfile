FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install deps in single layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential ninja-build pkg-config \
    libglib2.0-dev libpixman-1-dev \
    python3 python3-venv python3-tomli \
    gcc-riscv64-linux-gnu binutils-riscv64-linux-gnu \
    libc6-dev-riscv64-cross \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /qemu
COPY . /qemu/

# Build: user-mode only, skip docs/tests/tools, limit parallelism
RUN mkdir -p build && cd build && \
    ../configure \
        --target-list=riscv64-linux-user \
        --disable-system \
        --disable-docs \
        --disable-tools \
        --disable-guest-agent \
    && ninja -j2

# Cross-compile all benchmarks
RUN riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/false_sharing.c -o benchmarks/false_sharing.rv64 && \
    riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/true_sharing.c -o benchmarks/true_sharing.rv64 && \
    riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/deadlock.c -o benchmarks/deadlock.rv64

# addr2line for source-line resolution (riscv64 cross version)
# Already available as riscv64-linux-gnu-addr2line from binutils pkg.
# Symlink so the Python script can find plain "addr2line":
RUN ln -sf /usr/bin/riscv64-linux-gnu-addr2line /usr/local/bin/addr2line

CMD ["bash"]
