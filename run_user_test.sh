#!/bin/bash
set -e

echo "=============================================="
echo "  QEMU False Sharing Detection Framework"
echo "=============================================="
echo ""

# ── Check Docker ──────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is required. Install Docker Desktop:"
    echo "  https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "ERROR: Docker daemon is not running."
    echo "  Start Docker Desktop and retry."
    exit 1
fi

# ── Configuration (override with env vars) ────────
BUFFER_SIZE=${BUFFER_SIZE:-64}
BENCHMARK=${BENCHMARK:-false_sharing}
DOCKER_MEM=${DOCKER_MEM:-4g}
IMAGE_NAME="qemu-false-sharing"

# Docker Hub image (pre-built = instant, no compilation)
REMOTE_IMAGE="${DOCKER_HUB_IMAGE:-}"

echo "Config: benchmark=$BENCHMARK  buffer=$BUFFER_SIZE  docker_mem=$DOCKER_MEM"
echo ""

# ── Step 1: Get Docker Image ─────────────────────
if [ -n "$REMOTE_IMAGE" ]; then
    # Fast path: pull pre-built image
    echo "[1/3] Pulling pre-built image..."
    docker pull "$REMOTE_IMAGE"
    IMAGE_NAME="$REMOTE_IMAGE"
elif docker image inspect "$IMAGE_NAME" &> /dev/null; then
    echo "[1/3] Using cached image '$IMAGE_NAME'"
else
    echo "[1/3] Building Docker image (first run only, ~10 min)..."
    echo "      Tip: set DOCKER_MEM=8g if you get OOM errors"
    docker build \
        --memory="$DOCKER_MEM" \
        --platform linux/amd64 \
        -t "$IMAGE_NAME" . 2>&1 | tail -5
fi
echo "      ✓ Ready"
echo ""

# ── Step 2: Run Benchmark ─────────────────────────
echo "[2/3] Running '$BENCHMARK' with buffer_size=$BUFFER_SIZE ..."
mkdir -p results

docker run --rm \
    --memory="$DOCKER_MEM" \
    --platform linux/amd64 \
    -v "$(pwd)/results:/output" \
    "$IMAGE_NAME" bash -c "
        cd /qemu

        # Run benchmark under qemu-riscv64
        ./build/qemu-riscv64 \\
            -false-sharing-read \\
            -false-sharing-write \\
            -buffer-size $BUFFER_SIZE \\
            benchmarks/${BENCHMARK}.rv64 2>&1 || true

        # Copy log out
        cp instruction_log.txt /output/ 2>/dev/null || true

        # Analyze
        python3 detect_false_sharing.py instruction_log.txt \\
            --binary benchmarks/${BENCHMARK}.rv64 \\
            --pc-hotspots \\
            --read-write --write-write \\
            2>&1 | tee /output/report.txt
    "

echo "      ✓ Done"
echo ""

# ── Step 3: Results ───────────────────────────────
echo "[3/3] Results"
echo "=============================================="
if [ -f results/report.txt ]; then
    cat results/report.txt
else
    echo "  (no report — check Docker output above)"
fi
echo ""
echo "  Log:    results/instruction_log.txt"
echo "  Report: results/report.txt"
echo "=============================================="
echo ""
echo "Try different configs:"
echo "  BUFFER_SIZE=128 ./run_user_test.sh"
echo "  BENCHMARK=true_sharing ./run_user_test.sh"
