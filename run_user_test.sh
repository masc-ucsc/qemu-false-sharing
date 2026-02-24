#!/bin/bash
set -e

echo "=============================================="
echo "  QEMU False Sharing End-to-End Test"
echo "=============================================="

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is required but not found."
    echo "QEMU linux-user mode requires a Linux host."
    echo "Install Docker Desktop and retry."
    exit 1
fi

# Build the Docker image (includes QEMU + cross-compiled benchmarks)
echo ""
echo "[1/4] Building Docker image (QEMU + benchmarks)..."
echo "      This may take 5-10 minutes on first run."
docker build -t qemu-fs-test . 2>&1 | tail -5

# Run the false_sharing benchmark inside Docker
echo ""
echo "[2/4] Running false_sharing benchmark under QEMU user mode..."
docker run --rm -v "$(pwd)/results:/results" qemu-fs-test bash -c '
    # Run benchmark
    echo "Starting qemu-riscv64 with false sharing detection..."
    ./build/qemu-riscv64 \
        -false-sharing-read -false-sharing-write \
        -buffer-size 64 \
        -deadlock-detector \
        benchmarks/false_sharing.rv64 2>&1 || true

    # Copy results out
    cp instruction_log.txt /results/ 2>/dev/null || echo "No log generated"
    
    # Run analysis inside container (has addr2line)
    echo ""
    echo "[3/4] Analyzing results..."
    python3 detect_false_sharing.py instruction_log.txt \
        --binary benchmarks/false_sharing.rv64 \
        --pc-hotspots --read-write --write-write | tee /results/analysis_report.txt
'

# Show results on host
echo ""
echo "[4/4] Results saved to ./results/"
echo "=============================================="
if [ -f results/analysis_report.txt ]; then
    echo ""
    cat results/analysis_report.txt
fi
echo ""
echo "Raw log: results/instruction_log.txt"
echo "Report:  results/analysis_report.txt"
echo "=============================================="
