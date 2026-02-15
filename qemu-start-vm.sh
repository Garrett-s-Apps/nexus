#!/bin/bash
# Quick start QEMU Linux VM on M1 Mac
# Requires: QEMU installed (brew install qemu)

VM_NAME="${1:-nexus-linux}"
VM_DIR="$HOME/.qemu-vms/$VM_NAME"

if [ ! -d "$VM_DIR" ]; then
  echo "❌ VM directory not found: $VM_DIR"
  echo "Run ./qemu-setup.sh first to create a VM"
  exit 1
fi

cd "$VM_DIR"

echo "🚀 Starting QEMU VM: $VM_NAME"
echo "Network forwarding:"
echo "  SSH:  localhost:2222 → VM:22"
echo "  HTTP: localhost:8080 → VM:80"
echo "  HTTPS: localhost:8443 → VM:443"
echo ""
echo "To SSH into the VM: ssh -p 2222 ubuntu@localhost"
echo "To stop: Press Ctrl+A, then X"
echo ""

qemu-system-aarch64 \
  -machine virt,gic-version=3 \
  -cpu host \
  -m 4G \
  -smp 2 \
  -drive file=$VM_NAME-disk.qcow2,if=virtio,cache=writethrough \
  -nographic \
  -net nic,model=virtio \
  -net user,hostfwd=tcp::2222-:22,hostfwd=tcp::8080-:80,hostfwd=tcp::8443-:443 \
  -bios /opt/homebrew/share/qemu/edk2-aarch64-code.fd
