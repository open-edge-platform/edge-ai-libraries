# System Requirements

## Supported Platforms

**Operating Systems**

- Ubuntu 22.04 LTS or newer
- Debian 12 or newer
- RHEL 9 or newer
- Any Linux distribution with kernel 5.4+

The service uses Linux-specific paths (`/sys`, `/proc`, `/dev/dri`) mounted into the container. It cannot collect system metrics on Windows or macOS hosts, but the REST API and SSE streaming work on any platform.

**Hardware Platforms**

- Any x86-64 processor (Intel or AMD)
- Any ARM64 processor (with Docker installed)
- Intel Arc GPU (optional, for GPU metrics via qmassa)
- Intel NPU (MTL/ARL/LNL/PTL generations, optional, for NPU metrics)

## Minimum Requirements

| Component | Minimum | Recommended |
|-----------|---------|------------|
| Processor | 2 cores @ 1 GHz | 4 cores @ 2 GHz |
| Memory (RAM) | 512 MB | 2 GB |
| Disk Space | 2 GB (for build) | 10 GB (with headroom) |
| Docker | 24.0+ | 26.0+ |
| Docker Compose | 2.20+ | 2.25+ |

## Software Requirements

**Required Software**

- Docker 24.0 or newer (`docker --version`)
- Docker Compose 2.20 or newer (`docker compose version`)
- `git` for cloning the repository
- `curl` for testing endpoints (optional but recommended)

**Optional Software**

- `make` — for convenience commands (e.g., `make helm-lint`)
- `kubectl` — if deploying to Kubernetes
- `helm` 3.8+ — if using the Helm chart for Kubernetes deployment

## Hardware-Specific Notes

### Intel Arc GPU (Recommended for GPU metrics)

- Requires Intel Arc GPU to be installed on the system
- No additional drivers needed in the container (GPU metrics read from sysfs)
- The qmassa reader (`scripts/qmassa_reader.py`) automatically detects the GPU and publishes metrics

**Collected metrics:**
- Engine usage (compute, render, copy, video, video-enhance)
- GPU frequency
- GPU power consumption

If GPU is absent, qmassa logs `No DRM devices found` and exits gracefully. Other metrics continue normally.

### Intel NPU (Optional, for NPU telemetry)

- Supported on Meteor Lake (MTL), Arrow Lake (ARL/ARL-H/ARL-S), Lunar Lake (LNL), and Panther Lake (PTL)
- Requires Intel NPU driver (`intel_vpu`) to be loaded on the host
- Requires `/sys/class/intel_pmt/` to be accessible inside the container (provided by `privileged: true` and `/sys:/sys:ro` in `compose.yaml`)

**Collected metrics:**
- NPU power draw (watts)
- NPU frequency
- NPU temperature
- NPU utilization (%)
- NPU bandwidth
- Tile configuration
- Memory usage (MB) — reports `-1` on MTL/ARL (sysfs node doesn't exist)

If NPU is absent or driver is not loaded, the NPU reader logs a warning and enters idle mode. Other metrics continue normally.

## Validation Checklist

- [ ] Linux kernel 5.4+: `uname -r`
- [ ] Docker installed: `docker --version`
- [ ] Docker Compose installed: `docker compose version`
- [ ] At least 512 MB RAM available: `free -h`
- [ ] At least 2 GB disk space: `df -h /`
- [ ] (Optional) Intel GPU: `lspci | grep -i intel | grep -i graphics`
- [ ] (Optional) Intel NPU driver: `ls /sys/bus/pci/drivers/intel_vpu/`

If all checks pass, you're ready to proceed with the [Installation Guide](./installation.md) or [Get Started Guide](../get-started.md).

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
