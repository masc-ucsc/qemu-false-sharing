FROM ubuntu:22.04

RUN mkdir -p /tmp/apt-archives/partial && \
    apt-get update && \
    apt-get -o dir::cache::archives=/tmp/apt-archives install -y --no-install-recommends \
    build-essential \
    ninja-build \
    pkg-config \
    libglib2.0-dev \
    libpixman-1-dev \
    python3 \
    python3-pip \
    python3-venv \
    python3-tomli \
    gcc-riscv64-linux-gnu \
    g++-riscv64-linux-gnu \
    binutils-riscv64-linux-gnu \
    git \
    && rm -rf /var/lib/apt/lists/* /tmp/apt-archives

WORKDIR /qemu

# Copy source
COPY . /qemu/

# Configure for linux-user mode only (fast build)
RUN mkdir -p build && cd build && \
    ../configure --target-list=riscv64-linux-user --disable-system && \
    ninja

# Cross-compile benchmarks
RUN riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/false_sharing.c -o benchmarks/false_sharing.rv64 && \
    riscv64-linux-gnu-gcc -g -O0 -static -pthread \
    benchmarks/true_sharing.c -o benchmarks/true_sharing.rv64

# Default: run the end-to-end test
CMD ["bash", "run_user_test.sh"]
