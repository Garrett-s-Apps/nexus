# QEMU on Apple Silicon M1 - Complete Setup Guide

## What is QEMU?
QEMU is a free, open-source hypervisor that works on **Mac, Windows, and Linux**. This makes it ideal for cross-platform VM management.

## Current Architecture

```
MacBook Air M1 (Bare Metal)
├─ macOS Virtualization Framework (built-in)
│  └─ Docker Desktop Linux VM (current setup)
│     └─ nexus-playground container
│
└─ QEMU (new option)
   └─ Ubuntu Linux VM (arm64)
      ├─ Docker Engine
      └─ Containers & services
```

## Installation

QEMU is already installed via Homebrew (v10.2.1).

Verify:
```bash
qemu-system-aarch64 --version
qemu-img --version
```

## Quick Start: Create & Run a Linux VM

### Step 1: Set up the VM (one-time)
```bash
./qemu-setup.sh
```

This will:
- Create `~/.qemu-vms/nexus-linux/` directory
- Download Ubuntu 24.04 LTS (ARM64)
- Create a 20GB QCOW2 disk
- Configure cloud-init for automatic setup

### Step 2: Start the VM
```bash
./qemu-start-vm.sh
```

The VM will boot with:
- 4GB RAM
- 2 CPU cores
- Docker pre-installed
- Port forwarding enabled:
  - SSH: `localhost:2222` → VM port 22
  - HTTP: `localhost:8080` → VM port 80
  - HTTPS: `localhost:8443` → VM port 443

### Step 3: Connect to the VM
```bash
ssh -p 2222 ubuntu@localhost
```

Default credentials: `ubuntu` / `ubuntu` (change on first login)

## Using Docker Inside QEMU VM

Once connected to the VM via SSH:

```bash
# Verify Docker is installed
docker --version

# Run nexus-playground
docker run -d \
  --name nexus-playground \
  --memory 2g \
  --cpus 2 \
  --network none \
  -v nexus-workspace:/workspace \
  nexus-playground

# Check status
docker ps
```

## Performance Considerations

| Layer | Speed | Overhead |
|-------|-------|----------|
| Current (macOS native) | ⚡⚡⚡ Fast | Minimal |
| QEMU on M1 | ⚡⚡ Moderate | 10-20% |
| QEMU nested VM | ⚡ Slow | 30-50% |

QEMU on Apple Silicon is well-optimized but slower than native macOS virtualization.

## Cross-Platform Advantage

The same VM image can run on:
- **Mac M1/M2** - Via QEMU
- **Windows** - Via QEMU (or WSL2)
- **Linux** - Via QEMU or native Docker

## Managing Multiple VMs

Create additional VMs:
```bash
./qemu-setup.sh  # Creates nexus-linux
mkdir ~/.qemu-vms/production
# ... repeat for other VMs
```

Start specific VM:
```bash
./qemu-start-vm.sh nexus-linux
./qemu-start-vm.sh production
```

## Advanced: Nested Virtualization

To run VMs inside the QEMU VM (triple nesting):

```bash
# Inside QEMU VM
sudo apt install -y qemu-system-arm64 libvirt-daemon
sudo systemctl start libvirtd

# Now you can run KVM/QEMU inside
```

⚠️ **Warning**: Triple nesting has significant performance overhead (30-50% slower).

## Stopping a VM

Inside the QEMU VM or from SSH:
```bash
sudo poweroff
```

Or from host (emergency):
- Press `Ctrl+A` then `X`

## Troubleshooting

### VM won't start
```bash
# Check QEMU version
qemu-system-aarch64 --version

# Verify disk exists
ls -lh ~/.qemu-vms/nexus-linux/nexus-linux-disk.qcow2
```

### Slow performance
- Reduce `-m` (RAM) or `-smp` (CPUs) to free host resources
- Use SSD for QEMU disk location
- Monitor host CPU: `top`

### Network issues
```bash
# Inside VM, test connectivity
curl https://www.google.com

# Check host forwarding
netstat -an | grep 2222
```

## Next Steps

1. **Lightweight approach** (recommended): Keep using Docker Desktop VM
2. **Cross-platform approach**: Use QEMU for workloads that need Windows/Linux parity
3. **Nested approach**: Use QEMU VM with Docker + internal KVM for testing

Choose based on your needs!
