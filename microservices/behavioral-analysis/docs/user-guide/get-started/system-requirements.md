# System Requirements

## Software Requirements

- Ubuntu 24.04 LTS (recommended and validated).
- Other recent 64-bit Linux distributions may work, but are not fully
  validated.
- Python 3.12
- Docker Engine | 24.0 or later recommended |
- Docker Compose | v2.x (`docker compose` command, not `docker-compose`)
- git for cloning the repository
---

## Hardware Requirements

- **CPU:**
  - 8 physical cores (16 threads) or more recommended.
  - x86_64 architecture with support for AVX2.

- **System Memory (RAM):**
  - Minimum: 16 GB.
  - Recommended: 32 GB or more for smoother multi-service operation and
    headroom for the VLM.

- **Storage:**
  - Minimum free disk space: 30 GB.
  - Recommended: 60 GB+ to accommodate Docker images, OpenVINO™ models, the
    VLM weights (Qwen2.5-VL is several GB) and frame storage.

- **Graphics / Accelerators:**
  - Required: Intel CPU.
  - Optional (recommended for full experience):
    - Intel integrated or discrete GPU supported by Intel® Graphics Compute
      Runtime — VLM inference `Qwen2.5-VL-7B-Instruct (GPU-backed recommended)`
    - Intel NPU supported by the `linux-npu-driver` stack — recommended for
      VLM inference (see [Release Notes](../release-notes.md) for a known
      issue on systems without NPU).

  - The host must expose GPU and NPU devices to Docker, for example:
    - `/dev/dri` (GPU)
    - `/dev/accel/accel0` (NPU)

---
## Required Ports

The service communicates via MQTT messaging; no external ports are typically required. Port exposure depends on the deployment environment (e.g., container-to-container networking within Docker Compose).

---

## External Services Required

The following services must be running and accessible for the behavioral-analysis service to operate:

| Service | Purpose | Default Address |
|---|---|---|
| SeaweedFS | Frame storage (S3-compatible object store) | `http://seaweedfs:8333` |
| MQTT Broker | Event messaging (`ba/requests` / `ba/results`) | `broker.scenescape.intel.com:1883` |
| OpenVINO Model Server (OVMS) | VLM inference (Qwen2.5-VL-7B-Instruct) | `http://ovms-vlm:8001` |

> OVMS is only required when `VLM_ENABLED=true` (the default). The service starts and functions for pose-only detection if VLM is disabled.

---

## YOLO-Pose Model

The service requires a YOLO26n-pose model in OpenVINO IR format (`.xml` + `.bin`):

| Item | Details |
|---|---|
| Model format | OpenVINO IR (`.xml` + `.bin`) |
| Expected path | `/models/yolo_models/yolo26n-pose/yolo26n-pose.xml` (inside container) |
| Host mount | `${DOWNLOADED_MODEL_PATH:-./models}:/models:ro` |

---

## Inference Device

| Environment Variable | Default | Options |
|---|---|---|
| `GST_INFERENCE_DEVICE` | `CPU` | `CPU`, `GPU`, `NPU` (any device supported by the installed OpenVINO Runtime) |

---

## Network Requirements

- The container must be able to reach SeaweedFS, the MQTT broker, and OVMS by hostname.
- In Docker Compose, all services share the `ba-network` network by default.
- No inbound internet access is required at runtime.
- `http_proxy`, `https_proxy`, and `no_proxy` environment variables are forwarded to the container for environments behind a corporate proxy.

## Related Documentation

- [Overview](./docs/user-guide/index.md#1-overview): A high-level introduction to the
    microservice and its capabilities.
- [Get Started](./get-started.md) — Step-by-step run instructions
- [API Reference](./api-reference.md) — HTTP and MQTT endpoint schemas
- [Configuration](./get-started/configuration.md) — Full environment variable reference
- [Troubleshooting](./troubleshooting.md) — Common issues and resolution
