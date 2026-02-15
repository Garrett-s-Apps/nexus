#!/bin/bash
# QEMU VM Setup for Apple Silicon M1
# Creates a lightweight Linux VM with Docker support

set -e

QEMU_DIR="$HOME/.qemu-vms"
VM_NAME="nexus-linux"
VM_PATH="$QEMU_DIR/$VM_NAME"
DISK_SIZE="20G"
RAM="4G"
CPUS="2"

echo "🚀 QEMU VM Setup for M1 Mac"
echo "================================"

# Create VM directory
mkdir -p "$VM_DIR"
cd "$VM_DIR"

echo "📦 Downloading Ubuntu 24.04 LTS (ARM64)..."
# Using minimal cloud image for faster setup
UBUNTU_IMAGE="jammy-server-cloudimg-arm64.img"
UBUNTU_URL="https://cloud-images.ubuntu.com/jammy/current/$UBUNTU_IMAGE"

if [ ! -f "$UBUNTU_IMAGE" ]; then
  wget -q "$UBUNTU_URL" || {
    echo "❌ Failed to download Ubuntu image"
    echo "Alternative: Download manually from: $UBUNTU_URL"
    exit 1
  }
fi

echo "💾 Creating VM disk..."
qemu-img create -f qcow2 -b "$UBUNTU_IMAGE" "$VM_NAME-disk.qcow2" "$DISK_SIZE"

echo "📝 Creating cloud-init config..."
cat > user-data.txt << 'CLOUD_INIT'
#cloud-config
hostname: nexus-linux
users:
  - name: ubuntu
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    shell: /bin/bash
package_update: true
packages:
  - docker.io
  - curl
  - git
  - python3-pip
runcmd:
  - usermod -aG docker ubuntu
  - systemctl start docker
  - systemctl enable docker
CLOUD_INIT

echo "🔧 Creating meta-data..."
cat > meta-data.txt << 'META'
instance-id: nexus-1
local-hostname: nexus-linux
META

echo "📀 Creating ISO for cloud-init..."
mkisofs -output init.iso -volid cidata -joliet -rock user-data.txt meta-data.txt

echo ""
echo "✅ VM setup complete!"
echo ""
echo "🚀 To start the VM, run:"
echo ""
echo "qemu-system-aarch64 \\"
echo "  -machine virt,gic-version=3 \\"
echo "  -cpu host \\"
echo "  -m $RAM \\"
echo "  -smp $CPUS \\"
echo "  -drive file=$VM_NAME-disk.qcow2,if=virtio,cache=writethrough \\"
echo "  -drive file=init.iso,if=virtio,cache=writethrough \\"
echo "  -nographic \\"
echo "  -net nic,model=virtio \\"
echo "  -net user,hostfwd=tcp::2222-:22,hostfwd=tcp::8080-:80,hostfwd=tcp::8443-:443 \\"
echo "  -bios /opt/homebrew/share/qemu/edk2-aarch64-code.fd"
echo ""
echo "ℹ️  VM will be accessible at:"
echo "   SSH: ssh -p 2222 ubuntu@localhost"
echo "   Password: ubuntu (first login, change it!)"
echo ""
