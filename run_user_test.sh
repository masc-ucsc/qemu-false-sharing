#!/bin/bash
set -e

echo "=============================================="
echo "  QEMU Concurrency Bug Detection Framework"
echo "  (False Sharing + Deadlock Detection)"
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
ITERATIONS=${ITERATIONS:-2000}
TIMEOUT=${TIMEOUT:-300}
DOCKER_MEM=${DOCKER_MEM:-4g}
DEADLOCK=${DEADLOCK:-1}
IMAGE_NAME="qemu-false-sharing"

# Docker Hub image (pre-built = instant, no compilation)
REMOTE_IMAGE="${DOCKER_HUB_IMAGE:-}"

echo "Config:"
echo "  benchmark=$BENCHMARK  iterations=$ITERATIONS  buffer=$BUFFER_SIZE"
echo "  timeout=${TIMEOUT}s  deadlock=$DEADLOCK  docker_mem=$DOCKER_MEM"
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
        -t "$IMAGE_NAME" . 2>&1 | tail -5
fi
echo "      Done"
echo ""

# ── Build QEMU flags ─────────────────────────────
# Default: logging-only mode (intercept every load/store, log to CSV).
# USE_BUFFER=1 enables store buffer simulation (experimental).
QEMU_FLAGS="-false-sharing-read -false-sharing-write"
if [ "${USE_BUFFER:-0}" = "1" ]; then
    QEMU_FLAGS="-buffer-size $BUFFER_SIZE $QEMU_FLAGS"
fi
if [ "$DEADLOCK" = "1" ]; then
    QEMU_FLAGS="$QEMU_FLAGS -deadlock-detector"
fi

# ── Step 2: Run Benchmark ─────────────────────────
echo "[2/3] Running '$BENCHMARK' (iterations=$ITERATIONS, timeout=${TIMEOUT}s)..."
mkdir -p results

docker run --rm \
    --memory="$DOCKER_MEM" \
    -e ITERATIONS="$ITERATIONS" \
    -v "$(pwd)/results:/output" \
    "$IMAGE_NAME" bash -c "
        cd /qemu
        EXIT_CODE=0

        # Run benchmark under qemu-riscv64 with timeout
        timeout ${TIMEOUT}s ./build/qemu-riscv64 \\
            $QEMU_FLAGS \\
            benchmarks/${BENCHMARK}.rv64 \${ITERATIONS} 2>/output/stderr.txt || EXIT_CODE=\$?

        if [ \$EXIT_CODE -eq 124 ]; then
            echo 'WARNING: Benchmark timed out after ${TIMEOUT}s (try fewer ITERATIONS)' | tee -a /output/stderr.txt
        fi

        # Copy log out
        cp instruction_log.txt /output/ 2>/dev/null || true
        cp instruction_log_stats.txt /output/ 2>/dev/null || true

        # Analyze false sharing
        if [ -f instruction_log.txt ]; then
            python3 detect_false_sharing.py instruction_log.txt \\
                --binary benchmarks/${BENCHMARK}.rv64 \\
                --pc-hotspots \\
                --read-write --write-write \\
                2>&1 | tee /output/report.txt
        else
            echo 'No instruction log produced.' | tee /output/report.txt
        fi

        # Show deadlock warnings (they go to stderr)
        if [ -s /output/stderr.txt ]; then
            echo '' >> /output/report.txt
            echo '=== Deadlock / Runtime Warnings ===' >> /output/report.txt
            cat /output/stderr.txt >> /output/report.txt
        fi
    "

echo "      Done"
echo ""

# ── Step 3: Results ───────────────────────────────
echo "[3/3] Results"
echo "=============================================="
if [ -f results/report.txt ]; then
    cat results/report.txt
else
    echo "  (no report -- check Docker output above)"
fi
echo ""
echo "  Log:    results/instruction_log.txt"
echo "  Report: results/report.txt"
echo "  Stderr: results/stderr.txt"
echo "=============================================="
echo ""
echo "Examples:"
echo "  ./run_user_test.sh                                    # default (false sharing, 500 iters)"
echo "  ITERATIONS=1000 BUFFER_SIZE=128 ./run_user_test.sh    # more iterations, bigger buffer"
echo "  BENCHMARK=true_sharing ./run_user_test.sh             # control test (no false sharing)"
echo "  BENCHMARK=deadlock DEADLOCK=1 ./run_user_test.sh      # deadlock detection demo"
echo "  TIMEOUT=300 ITERATIONS=5000 ./run_user_test.sh        # longer run"
