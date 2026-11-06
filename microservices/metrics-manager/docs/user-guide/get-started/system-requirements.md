# System Requirements

## Supported Platforms

**Operating Systems**

- Ubuntu 22.04 LTS or newer
- Debian 12 or newer
- RHEL 9 or newer
- Any Linux distribution with kernel 5.4+

The shipped Docker build targets **Linux/amd64**.
Telemetry uses Linux-specific paths (`/sys`, `/proc`, `/dev/dri`). Running
Docker inside a VM on another operating system exposes the VM's environment,
not the physical host's Windows or macOS telemetry.

The capabilities endpoint (`GET /api/v1/capabilities`) is available wherever the service runs, but hardware-enriched values depend on Linux host visibility (`/sys`, `/proc`, and optionally `/dev/dri`).

**Hardware Platforms**

- Any x86-64 processor (Intel or AMD)
- ARM64 images/packages are not supplied by the current build: the Telegraf
  archive and Debian package target are amd64.
- Intel Arc GPU (optional, for GPU metrics via qmassa)
- Intel NPU (MTL/ARL/LNL/PTL generations, optional, for NPU metrics)

## Minimum Requirements

| Component      | Minimum          | Recommended           |
| -------------- | ---------------- | --------------------- |
| Processor      | 2 cores @ 1 GHz  | 4 cores @ 2 GHz       |
| Memory (RAM)   | 512 MB           | 2 GB                  |
| Disk Space     | 2 GB (for build) | 10 GB (with headroom) |
| Docker         | 24.0+            | 26.0+                 |
| Docker Compose | 2.20+            | 2.25+                 |

## Software Requirements

**Required Software**

- Docker 24.0 or newer (`docker --version`)
- Docker Compose 2.20 or newer (`docker compose version`)
- `git` for cloning the repository
- `curl` for testing endpoints (optional but recommended)

**Optional Software**

- `make` — for convenience commands (e.g., `make build`)

## Hardware-Specific Notes

### OpenVINO inference in the extended image

The extended image supplies OpenVINO plus Intel OpenCL/Level Zero GPU and NPU
userspace runtimes and compilers. The default image collects GPU/NPU telemetry
without these inference dependencies.

- GPU inference requires a supported Intel GPU, its host `i915`/`xe` driver,
  and access to `/dev/dri/renderD*`.
- NPU inference additionally requires compatible host `intel_vpu` and firmware,
  and access to `/dev/accel/accel*`. PMT telemetry alone does not prove inference
  access. The image does not install firmware or kernel modules.
- The shipped privileged Compose profile exposes the devices. A restricted
  deployment must explicitly grant the required device nodes and render-group
  permissions; do not change host security settings merely to pass a test.
- Official Intel vendor binaries target Ubuntu, but their pinned dependencies
  are resolved against Debian 13 without adding Ubuntu repositories or replacing
  the system C library. This is project-level compatibility validation, not an
  upstream support statement for Debian.
- Real CPU/GPU/NPU inference was validated on an Intel Core Ultra 5 225H with
  Arrow Lake graphics/NPU and Linux 7.0.0-42. Other device, firmware and kernel
  combinations require their own validation.

See the [hardware smoke test](./testing.md#openvino-accelerator-smoke-test).
Missing devices fail that test explicitly; it does not fall back to CPU.

### Intel Arc GPU (Recommended for GPU metrics)

- Requires Intel Arc GPU to be installed on the system
- Requires a compatible host kernel driver (`i915` or `xe`) and DRM access.
- qmassa collects device data; `mm-plugin-gpu` parses its FIFO stream into
  telemetry. Power and temperature can additionally require perf/MSR access.
- The optional extended image adds userspace OpenVINO/VAAPI components; it
  does not install or replace the host kernel driver.

**Collected metrics:**

- Engine usage (compute, render, copy, video, video-enhance)
- GPU frequency
- GPU power consumption

**Capabilities output note:**

- GPU entries are also exposed in capabilities JSON (`minimal` and `expanded` profiles).
- PCI branding/model naming uses `lspci` (`pciutils`) when available.
- `lspci` does not require `sudo` for read-only inventory.

If GPU is absent, qmassa logs `No DRM devices found` and exits gracefully. Other metrics continue normally.

### Intel NPU (Optional, for NPU telemetry)

- Supported on Meteor Lake (MTL), Arrow Lake (ARL/ARL-H/ARL-S), Lunar Lake (LNL), and Panther Lake (PTL)
- Requires Intel NPU driver (`intel_vpu`) to be loaded on the host
- Requires `/sys/class/intel_pmt/` to be accessible inside the container (provided by `privileged: true` and `/sys:/sys:ro` in `compose.yaml`)

**Collected metrics:**

- NPU power draw (watts)
- NPU frequency (Hz)
- NPU temperature (degrees Celsius)
- NPU utilization (%), when supported
- NPU bandwidth (bytes/second)
- Tile configuration
- Memory usage (bytes), when the required telemetry fields are present.
  Unsupported readings are omitted; measured zero remains zero. The native
  collector does not publish `-1` as a substitute for unavailable memory.

See the [native metric migration guide](./native-metric-migration.md) for
field names and display conversions.

If NPU is absent or driver is not loaded, the NPU reader logs a warning and enters idle mode. Other metrics continue normally.

## Capabilities API Quick Check

After deployment, verify platform/device capabilities with:

```bash
curl -s http://localhost:9090/api/v1/capabilities?profile=minimal | jq
curl -s http://localhost:9090/api/v1/capabilities?profile=expanded | jq
```

Use `minimal` for a compact platform/device summary and `expanded` for full technical inventory.

## Validation Checklist

- [ ] Linux kernel 5.4+: `uname -r`
- [ ] Docker installed: `docker --version`
- [ ] Docker Compose installed: `docker compose version`
- [ ] At least 512 MB RAM available: `free -h`
- [ ] At least 2 GB disk space: `df -h /`
- [ ] (Optional) Intel GPU: `lspci | grep -i intel | grep -i graphics`
- [ ] (Optional) Intel NPU driver: `ls /sys/bus/pci/drivers/intel_vpu/`

If all checks pass, you are ready to proceed with the [Get Started Guide](../get-started.md).

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
