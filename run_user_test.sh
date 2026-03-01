#!/bin/bash
set -e

echo "=============================================="
echo "  QEMU Concurrency Bug Detection Framework"
echo "  (False Sharing + Deadlock Detection)"
echo "=============================================="
echo ""

# ── Helpers ───────────────────────────────────────
run_with_timeout() {
    local timeout_secs="$1"
    shift
    local pid
    local elapsed=0

    "$@" &
    pid=$!

    while kill -0 "$pid" 2>/dev/null; do
        if [ "$elapsed" -ge "$timeout_secs" ]; then
            kill -TERM "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            return 124
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    wait "$pid"
}

# ── Check Docker ──────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is required. Install Docker Desktop:"
    echo "  https://docs.docker.com/get-docker/"
    exit 1
fi

DOCKER_INFO_TIMEOUT=${DOCKER_INFO_TIMEOUT:-20}
if ! run_with_timeout "$DOCKER_INFO_TIMEOUT" docker info &> /dev/null; then
    echo "ERROR: Docker daemon is not running or is unresponsive (timeout ${DOCKER_INFO_TIMEOUT}s)."
    echo "  Start Docker Desktop and retry."
    echo "  Tip: increase timeout with DOCKER_INFO_TIMEOUT=60 if Docker is slow to start."
    exit 1
fi

# ── Configuration (override with env vars) ────────
BUFFER_SIZE=${BUFFER_SIZE:-64}
BENCHMARK=${BENCHMARK:-all}        # 'all' runs all three real-world apps
ITERATIONS=${ITERATIONS:-2000}
TIMEOUT=${TIMEOUT:-300}
DEADLOCK=${DEADLOCK:-1}
IMAGE_NAME="qemu-false-sharing"

# Docker Hub image (pre-built = instant, no compilation)
REMOTE_IMAGE="${DOCKER_HUB_IMAGE:-}"

detect_max_docker_mem() {
    local bytes
    local gib
    local reserve_gib=1

    # Prefer Docker's own memory total (reflects Docker Desktop limit).
    bytes="$(run_with_timeout "$DOCKER_INFO_TIMEOUT" docker info --format '{{.MemTotal}}' 2>/dev/null || true)"
    if [[ "$bytes" =~ ^[0-9]+$ ]] && [ "$bytes" -gt 0 ]; then
        gib=$((bytes / 1024 / 1024 / 1024))
        [ "$gib" -gt "$reserve_gib" ] && gib=$((gib - reserve_gib))
        [ "$gib" -lt 2 ] && gib=2
        echo "${gib}g"
        return
    fi

    # Fallback for macOS if docker info is unavailable during startup.
    if command -v sysctl >/dev/null 2>&1; then
        bytes="$(sysctl -n hw.memsize 2>/dev/null || true)"
        if [[ "$bytes" =~ ^[0-9]+$ ]] && [ "$bytes" -gt 0 ]; then
            gib=$((bytes / 1024 / 1024 / 1024))
            [ "$gib" -gt "$reserve_gib" ] && gib=$((gib - reserve_gib))
            [ "$gib" -lt 2 ] && gib=2
            echo "${gib}g"
            return
        fi
    fi

    # Conservative fallback.
    echo "4g"
}

if [ -z "${DOCKER_MEM:-}" ]; then
    DOCKER_MEM="$(detect_max_docker_mem)"
    echo "Auto-selected Docker memory cap: $DOCKER_MEM"
fi

echo "Config:"
echo "  benchmark=$BENCHMARK  iterations=$ITERATIONS  buffer=$BUFFER_SIZE"
echo "  timeout=${TIMEOUT}s  deadlock=$DEADLOCK  docker_mem=$DOCKER_MEM"
echo ""

# ── Step 1: Get Docker Image ─────────────────────
if [ -n "$REMOTE_IMAGE" ]; then
    echo "[1/3] Pulling pre-built image..."
    docker pull "$REMOTE_IMAGE"
    IMAGE_NAME="$REMOTE_IMAGE"
elif docker image inspect "$IMAGE_NAME" &> /dev/null; then
    echo "[1/3] Using cached image '$IMAGE_NAME'"
else
    echo "[1/3] Building Docker image (first run only, ~10 min)..."
    echo "      Tip: override with DOCKER_MEM=<N>g if you want a custom cap"
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

# ── Step 2: Run Benchmark(s) ─────────────────────
mkdir -p results

run_one() {
    local bench="$1"
    local label="$2"
    local iters="$3"

    echo "  --> $label (iterations=$iters)..."

    docker run --rm \
        --memory="$DOCKER_MEM" \
        -e ITERATIONS="$iters" \
        -v "$(pwd)/results:/output" \
        "$IMAGE_NAME" bash -c "
            cd /qemu
            EXIT_CODE=0

            timeout ${TIMEOUT}s ./build/qemu-riscv64 \\
                $QEMU_FLAGS \\
                benchmarks/${bench}.rv64 \${ITERATIONS} 2>/tmp/bench_stderr.txt || EXIT_CODE=\$?

            if [ \$EXIT_CODE -eq 124 ]; then
                echo 'WARNING: timed out after ${TIMEOUT}s' | tee -a /tmp/bench_stderr.txt
            fi

            cp instruction_log.txt /output/instruction_log_${bench}.txt 2>/dev/null || true
            cp /tmp/bench_stderr.txt /output/stderr_${bench}.txt 2>/dev/null || true

            if [ -f instruction_log.txt ]; then
                python3 detect_false_sharing.py instruction_log.txt \\
                    --binary benchmarks/${bench}.rv64 \\
                    --pc-hotspots \\
                    --read-write --write-write \\
                    2>&1 | tee /output/report_${bench}.txt
            else
                echo 'No instruction log produced.' | tee /output/report_${bench}.txt
            fi

            if [ -s /tmp/bench_stderr.txt ]; then
                echo '' >> /output/report_${bench}.txt
                echo '=== Deadlock / Runtime Warnings ===' >> /output/report_${bench}.txt
                cat /tmp/bench_stderr.txt >> /output/report_${bench}.txt
            fi

            rm -f instruction_log.txt instruction_log_stats.txt
        "
    echo "      Saved to results/report_${bench}.txt"
}

if [ "$BENCHMARK" = "all" ]; then
    echo "[2/3] Running all three real-world multithreaded apps..."
    echo ""
    # Each app uses its own iteration count — real apps do far more work per
    # iteration than the synthetic benchmark, so they need smaller values to
    # keep the instruction log at a manageable size.
    ITER_COMPRESS=${ITER_COMPRESS:-${ITERATIONS}}
    ITER_WORDCOUNT=${ITER_WORDCOUNT:-${ITERATIONS}}
    ITER_SORT=${ITER_SORT:-${ITERATIONS}}
    ITER_BASELINE=${ITER_BASELINE:-${ITERATIONS}}

    run_one "parallel_compress" "pigz-style parallel pipeline (pipeline false sharing)"         "$ITER_COMPRESS"
    run_one "word_count"        "Phoenix MapReduce word count (hash table + per-thread stats)"  "$ITER_WORDCOUNT"
    run_one "parallel_sort"     "Parallel merge sort (merge-state flag false sharing)"          "$ITER_SORT"

    # Also run the original false_sharing benchmark for comparison
    run_one "false_sharing"     "Synthetic false sharing (baseline)"                            "$ITER_BASELINE"

    # Run DuckDB TPC-H if the binary was built
    docker run --rm "$IMAGE_NAME" test -f benchmarks/duckdb.rv64 && HAS_DUCKDB=1 || HAS_DUCKDB=0
    if [ "$HAS_DUCKDB" = "1" ]; then
        echo "  --> DuckDB TPC-H micro-benchmark (real-world OLAP database)..."
        docker run --rm \
            --memory="$DOCKER_MEM" \
            -v "$(pwd)/results:/output" \
            "$IMAGE_NAME" bash -c "
                cd /qemu
                timeout ${TIMEOUT}s ./build/qemu-riscv64 \
                    $QEMU_FLAGS \
                    benchmarks/duckdb.rv64 \
                    -c 'INSTALL tpch; LOAD tpch; CALL dbgen(sf=0.01); SELECT count(*) FROM lineitem;' \
                    2>/tmp/duckdb_stderr.txt || true

                cp instruction_log.txt /output/instruction_log_duckdb.txt 2>/dev/null || true
                cp /tmp/duckdb_stderr.txt /output/stderr_duckdb.txt 2>/dev/null || true

                if [ -f instruction_log.txt ]; then
                    python3 detect_false_sharing.py instruction_log.txt \
                        --pc-hotspots --read-write --write-write \
                        2>&1 | tee /output/report_duckdb.txt
                fi
                rm -f instruction_log.txt instruction_log_stats.txt
            "
        echo "      Saved to results/report_duckdb.txt"
    else
        echo "  --> DuckDB: skipped (binary not available)"
    fi

    # Combine reports
    echo ""
    echo "=== Combined Report ===" > results/report.txt
    for bench in parallel_compress word_count parallel_sort false_sharing duckdb; do
        if [ -f "results/report_${bench}.txt" ]; then
            echo "" >> results/report.txt
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> results/report.txt
            echo "  APP: ${bench}" >> results/report.txt
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> results/report.txt
            cat "results/report_${bench}.txt" >> results/report.txt
        fi
    done

elif [ "$BENCHMARK" = "deadlock" ]; then
    echo "[2/3] Running deadlock detection..."
    run_one "deadlock" "ABBA deadlock" "$ITERATIONS"
    cp results/report_deadlock.txt results/report.txt 2>/dev/null || true
else
    echo "[2/3] Running '$BENCHMARK'..."
    run_one "$BENCHMARK" "$BENCHMARK" "$ITERATIONS"
    cp "results/report_${BENCHMARK}.txt" results/report.txt 2>/dev/null || true
fi

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
echo "Output files in results/:"
ls results/ 2>/dev/null | sed 's/^/  /'
echo "=============================================="
echo ""
echo "Examples:"
echo "  ./run_user_test.sh                               # run all 3 real apps (default)"
echo "  BENCHMARK=parallel_sort ./run_user_test.sh       # single app"
echo "  BENCHMARK=deadlock DEADLOCK=1 ./run_user_test.sh # deadlock detection"
echo "  BENCHMARK=false_sharing ./run_user_test.sh       # synthetic baseline"
echo "  ITERATIONS=5000 TIMEOUT=600 ./run_user_test.sh   # longer run"
