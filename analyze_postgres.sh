#!/bin/bash

# Configuration
QEMU_BIN="./build/qemu-system-riscv64-unsigned"
# Using downloaded Fedora images
KERNEL="kernel_payload.elf"
DRIVE="rootfs.img"

# 0. Check for Images
if [ ! -f "$KERNEL" ] || [ ! -f "$DRIVE" ]; then
    echo "Files '$KERNEL' or '$DRIVE' missing."
    echo "Running download script..."
    chmod +x download_images.sh
    ./download_images.sh
fi

# 1. Provide Instructions
echo "=========================================================="
echo "    Running PostgreSQL with False Sharing Detection"
echo "=========================================================="
echo "To detect false sharing in Postgres, start QEMU with:"
echo ""
echo "$QEMU_BIN \\"
echo "    -M virt -m 2G -nographic \\"
echo "    -bios none \\"
echo "    -kernel $KERNEL \\"
echo "    -append \"root=/dev/vda4 ro console=ttyS0\" \\"
echo "    -drive file=$DRIVE,format=raw,id=hd0,if=none \\"
echo "    -device virtio-blk-device,drive=hd0 \\"
echo "    -smp 4 \\"
echo "    -cpu rv64,sb-limit=500,sb-false-sharing=on,sb-false-sharing-read=on,sb-false-sharing-write=on"
echo ""
echo "Note: The '-cpu' line is critical. It enables the detection logic."
echo "Once inside the Fedora Guest (root, no password or 'fedora'):"
echo "  # dnf install -y postgresql-server postgresql-contrib"
echo "  # postgresql-setup --initdb"
echo "  # systemctl start postgresql"
echo "  # sudo -u postgres createdb pgbench"
echo "  # sudo -u postgres pgbench -i pgbench"
echo "  # sudo -u postgres pgbench -c 4 -T 10 pgbench"
echo ""
echo "After shutdown, 'instruction_log.txt' will be created."
echo "=========================================================="

# 2. Check if Log exists and Analyze
if [ -f "instruction_log.txt" ]; then
    # Check if log is stale (older than 10 minutes)
    if [ -n "$(find "instruction_log.txt" -mmin +10 -print)" ]; then
        echo "WARNING: 'instruction_log.txt' is old (>10 mins)."
        echo "You should probably run QEMU again to generate a fresh log."
        read -p "Analyze standard log anyway? [y/N] " confirm
        if [[ $confirm != [yY] && $confirm != [yY][eE][sS] ]]; then
            exit 0
        fi
    fi
    echo "Found 'instruction_log.txt'. Analyzing..."
    python3 detect_false_sharing.py instruction_log.txt --read-write --write-write
else
    echo "No log found. Please run QEMU first."
fi
