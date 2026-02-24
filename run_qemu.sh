#!/bin/bash
# Script to launch QEMU with False Sharing Detection enabled

QEMU_BIN="./build/qemu-system-riscv64-unsigned"
KERNEL="kernel_payload.elf"
DRIVE="rootfs.img"

# Check for files
if [ ! -f "$KERNEL" ] || [ ! -f "$DRIVE" ]; then
    echo "Files missing. Running download script..."
    ./download_images.sh
fi

echo "Starting QEMU..."
echo "Login: root (no password) or fedora / fedora"
echo "To exit QEMU: 'poweroff' inside guest, or Ctrl-A x"

$QEMU_BIN \
    -M virt -m 2G -nographic \
    -bios none \
    -kernel $KERNEL \
    -append "root=/dev/vda4 ro console=ttyS0" \
    -drive file=$DRIVE,format=raw,id=hd0,if=none \
    -device virtio-blk-device,drive=hd0 \
    -smp 4 \
    -cpu rv64,sb-limit=500,sb-false-sharing=on,sb-false-sharing-read=on,sb-false-sharing-write=on
