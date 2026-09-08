# System Requirements

## Hardware Requirements

| Component | Minimum                                           | Recommended                    |
| --------- | ------------------------------------------------- | ------------------------------ |
| CPU       | 4 cores                                           | 8+ cores                       |
| RAM       | 8 GB                                              | 16 GB                          |
| Disk      | 10 GB free                                        | 20 GB free                     |
| GPU       | _(optional)_ Intel® Arc™ / Flex / Data Center GPU | Intel® Arc™ A770 or equivalent |

> **Note:** The default LLM (`Phi-4-mini-instruct-int4-ov`) can run on either GPU or CPU. Set
> `TARGET_DEVICE=CPU` in your environment to use CPU-only inference. GPU provides significantly
> lower latency and is recommended for production workloads with high alert frequency.

## Software Requirements

| Software       | Version       | Notes                                                     |
| -------------- | ------------- | --------------------------------------------------------- |
| Docker Engine  | 24.0 or later | [Install Docker](https://docs.docker.com/engine/install/) |
| Docker Compose | v2 plugin     | Bundled with Docker Desktop; install separately on Linux  |
| Python         | 3.12 or later | Required only for running tests locally                   |
| `uv`           | 0.12.9        | Required only for local development; `pip install uv`     |

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
