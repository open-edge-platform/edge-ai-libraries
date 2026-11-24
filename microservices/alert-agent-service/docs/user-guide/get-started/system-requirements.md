<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# System Requirements

## Hardware Requirements

| Component | Minimum                                           | Recommended                    |
| --------- | ------------------------------------------------- | ------------------------------ |
| CPU       | 4 cores                                           | 8+ cores                       |
| RAM       | 8 GB                                              | 16 GB                          |
| Disk      | 10 GB free                                        | 20 GB free                     |
| GPU       | _(optional)_ Intel® Arc™ / Flex / Data Center GPU | Intel® Arc™ A770 or equivalent |
| NPU       | _(optional)_ Intel® NPU with a supported Linux driver | Host device available under `/dev/accel/` |

> [!NOTE]
> The OVMS text-generation deployment supports GPU, CPU, and NPU targets.
> Set `TARGET_DEVICE=CPU` for CPU-only inference. NPU compatibility depends on
> the selected model and platform.

### Intel NPU

The reference Docker Compose deployment supports Intel NPU inference through
OpenVINO™ Model Server. NPU deployment requires:

- a supported Intel NPU and host driver;
- an NPU device node, typically `/dev/accel/accel0`;
- permission to access the device through its host device group;
- `TARGET_DEVICE=NPU`;
- `ACCEL_MOUNT_PATH` set to the host NPU device node; and
- `RENDER_DEVICE_GID` set to the GID that owns the NPU device.

The pinned OVMS GPU image also contains the Intel NPU plugin. Compose maps only
the configured accelerator device and does not require privileged mode.

[OpenVINO Model Server documents NPU support](https://github.com/openvinotoolkit/model_server/tree/main/demos/vlm_npu)
on Ubuntu 24.04 for supported Intel platforms. Confirm support for the
selected model and platform before production deployment.

## Software Requirements

| Software       | Version       | Notes                                                     |
| -------------- | ------------- | --------------------------------------------------------- |
| Docker Engine  | 24.0 or later | [Install Docker](https://docs.docker.com/engine/install/) |
| Docker Compose | v2 plugin     | Bundled with Docker Desktop; install separately on Linux  |
| Python         | 3.12 or later | Required only for running tests locally                   |
| `uv`           | Latest        | Required only for local development; `pip install uv`     |

## Network Requirements

The following network ports are used by default:

| Port   | Service                       | Configurable via                 |
| ------ | ----------------------------- | -------------------------------- |
| `8000` | Alert Agent Service REST API  | `PORT` environment variable           |
| `9001` | OVMS LLM server (host-mapped) | `LLM_PORT` environment variable       |
| `1883` | MQTT broker (host-mapped)     | `MQTT_HOST_PORT` environment variable |

Within the Compose network, OVMS listens on port `9000` and the bundled MQTT broker listens on port `1883`. `LLM_PORT` and `MQTT_HOST_PORT` only control how those ports are published on the host. `MQTT_PORT` specifies the destination port used by the Alert Agent Service when connecting to an MQTT broker.

## Proxy Settings

If your environment requires an HTTP proxy, set the standard proxy environment variables before starting the service:

```bash
export http_proxy=http://proxy.example.com:8080
export https_proxy=http://proxy.example.com:8080
export no_proxy=localhost,127.0.0.1,ovms-llm
```

These are forwarded automatically to both containers in the Docker Compose setup.
