#!/bin/bash
# One-Command Install for QEMU Concurrency Bug Detection Framework
#
# Usage:
#   curl -LsSf https://raw.githubusercontent.com/<user>/qemu/main/scripts/install.sh | sh
#   # or:
#   ./scripts/install.sh [install_dir]
#
# This script:
#   1. Checks/installs Docker (required dependency)
#   2. Clones the repo (if not already present)
#   3. Builds the Docker image (QEMU + cross-compiled benchmarks)
#   4. Verifies the pipeline works with a quick smoke test
#   5. Prints PATH instructions
#
set -e

# ── Configuration ──────────────────────────────────
REPO_URL="${REPO_URL:-https://github.com/vijayarvind/qemu.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
INSTALL_DIR="${1:-$HOME/work/qemu-concurrency}"
IMAGE_NAME="qemu-false-sharing"
DOCKER_MEM="${DOCKER_MEM:-4g}"

# ── Colors ─────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[x]${NC} $*"; exit 1; }

echo ""
echo "=============================================="
echo "  QEMU Concurrency Bug Detection Framework"
echo "  One-Command Installer"
echo "=============================================="
echo ""

# ── Step 1: Check Docker ──────────────────────────
info "Checking Docker..."
if ! command -v docker &>/dev/null; then
    fail "Docker is not installed. Please install Docker Desktop first:
    https://docs.docker.com/get-docker/
Then re-run this script."
fi

if ! docker info &>/dev/null 2>&1; then
    fail "Docker daemon is not running. Start Docker Desktop and re-run."
fi
info "Docker OK"

# ── Step 2: Clone repo ────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Repository already exists at $INSTALL_DIR, pulling latest..."
    cd "$INSTALL_DIR"
    git pull --ff-only origin "$REPO_BRANCH" 2>/dev/null || true
else
    info "Cloning repository to $INSTALL_DIR..."
    git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi
info "Source ready at $INSTALL_DIR"

# ── Step 3: Build Docker image ────────────────────
info "Building Docker image (this takes ~10 min on first run)..."
docker build \
    --memory="$DOCKER_MEM" \
    --platform linux/amd64 \
    -t "$IMAGE_NAME" . 2>&1 | tail -3
info "Docker image '$IMAGE_NAME' ready"

# ── Step 4: Smoke test ────────────────────────────
info "Running smoke test (false sharing, 100 iterations)..."
mkdir -p results

docker run --rm \
    --memory="$DOCKER_MEM" \
    --platform linux/amd64 \
    -v "$(pwd)/results:/output" \
    "$IMAGE_NAME" bash -c "
        cd /qemu
        timeout 60s ./build/qemu-riscv64 \
            -false-sharing-read -false-sharing-write \
            -buffer-size 64 \
            benchmarks/false_sharing.rv64 100 2>/dev/null || true
        if [ -f instruction_log.txt ]; then
            python3 detect_false_sharing.py instruction_log.txt \
                --binary benchmarks/false_sharing.rv64 \
                --pc-hotspots --read-write --write-write \
                2>&1 | tee /output/report.txt
            cp instruction_log.txt /output/ 2>/dev/null || true
        fi
    "

if [ -f results/report.txt ] && grep -q "conflicts" results/report.txt; then
    info "Smoke test PASSED -- false sharing detected!"
else
    warn "Smoke test produced no conflicts (may need more iterations)."
    warn "Try: ITERATIONS=500 ./run_user_test.sh"
fi

# ── Step 5: Done ──────────────────────────────────
echo ""
echo "=============================================="
echo -e "  ${GREEN}Installation complete!${NC}"
echo "=============================================="
echo ""
echo "  Location: $INSTALL_DIR"
echo ""
echo "  Quick start:"
echo "    cd $INSTALL_DIR"
echo "    ./run_user_test.sh                                     # false sharing"
echo "    BENCHMARK=deadlock DEADLOCK=1 ./run_user_test.sh       # deadlock"
echo "    BENCHMARK=true_sharing ./run_user_test.sh              # control test"
echo ""
echo "  Results will be in: $INSTALL_DIR/results/"
echo ""
echo "  Optional: add to PATH for convenience:"
echo "    echo 'export PATH=\"$INSTALL_DIR:\$PATH\"' >> ~/.bashrc"
echo "    source ~/.bashrc"
echo ""
