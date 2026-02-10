#!/bin/bash

# Configuration
QEMU_BIN="./build/qemu-system-riscv64"
FW_BIN="opensbi-riscv64-generic-fw_dynamic.bin"
KERNEL="Image"
DRIVE="rootfs.ext2"

# 1. Provide Instructions
echo "=========================================================="
echo "    Running PostgreSQL with False Sharing Detection"
echo "=========================================================="
echo "To detect false sharing in Postgres, start QEMU with:"
echo ""
echo "$QEMU_BIN \\"
echo "    -M virt -nographic \\"
echo "    -bios $FW_BIN \\"
echo "    -kernel $KERNEL \\"
echo "    -append \"root=/dev/vda ro console=ttyS0\" \\"
echo "    -drive file=$DRIVE,format=raw,id=hd0 \\"
echo "    -device virtio-blk-device,drive=hd0 \\"
echo "    -cpu rv64,sb-limit=10,sb-false-sharing=on,sb-false-sharing-read=on,sb-false-sharing-write=on"
echo ""
echo "Note: The '-cpu' line is critical. It enables the detection logic."
echo "Once inside guest, run 'pgbench'!"
echo "After shutdown, 'instruction_log.txt' will be created."
echo "=========================================================="

# 2. Check if Log exists and Analyze
if [ -f "instruction_log.txt" ]; then
    echo "Found 'instruction_log.txt'. Analyzing..."
    python3 detect_false_sharing.py instruction_log.txt --read-write --write-write
else
    echo "No log found. Please run QEMU first."
fi
