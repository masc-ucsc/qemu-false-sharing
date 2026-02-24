#!/bin/bash
set -e

# Fedora 2020 Minimal Image (Known working with QEMU Virt)
BASE_URL="https://dl.fedoraproject.org/pub/alt/risc-v/archive/repo/virt-builder-images/images"
FW_FILENAME="Fedora-Minimal-Rawhide-20200108.n.0-fw_payload-uboot-qemu-virt-smode.elf"
DISK_FILENAME="Fedora-Minimal-Rawhide-20200108.n.0-sda.raw.xz"

echo "Downloading Fedora RISC-V Images..."

# Download Kernel/Firmware Payload
if [ ! -f "kernel_payload.elf" ]; then
    echo "Downloading Kernel Payload ($FW_FILENAME)..."
    curl -L -o kernel_payload.elf "$BASE_URL/$FW_FILENAME"
fi

# Download and Extract RootFS
if [ ! -f "rootfs.img" ]; then
    if [ ! -f "$DISK_FILENAME" ]; then
        echo "Downloading Disk Image ($DISK_FILENAME)..."
        curl -L -o "$DISK_FILENAME" "$BASE_URL/$DISK_FILENAME"
    fi
    echo "Extracting Disk Image..."
    xz -d -k "$DISK_FILENAME"
    mv "${DISK_FILENAME%.xz}" rootfs.img
fi

echo "Download Complete."
echo "Kernel: kernel_payload.elf"
echo "RootFS: rootfs.img"
