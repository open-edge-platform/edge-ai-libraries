# System Requirements

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16 GB |
| Disk | 10 GB free | 20 GB free |
| GPU | _(optional)_ Intel® Arc™ / Flex / Data Center GPU | Intel® Arc™ A770 or equivalent |

> **Note:** The default LLM (`Phi-4-mini-instruct-int4-ov`) can run on either GPU or CPU. Set `TARGET_DEVICE=CPU` in your environment to use CPU-only inference. GPU provides significantly lower latency and is recommended for production workloads with high alert frequency.

## Software Requirements

| Software | Version | Notes |
|----------|---------|-------|
| Docker Engine | 24.0 or later | [Install Docker](https://docs.docker.com/engine/install/) |
| Docker Compose | v2 plugin | Bundled with Docker Desktop; install separately on Linux |
| Python | 3.12 or later | Required only for running tests locally |
| `uv` | Latest | Required only for local development; `pip install uv` |

## Kubernetes Requirements (Helm Deployment)

| Tool | Version | Notes |
|------|---------|-------|
| Kubernetes | 1.27 or later | Cluster must support dynamic Persistent Volume provisioning |
| kubectl | Latest | [Install kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/) |
| Helm | 3.x | [Install Helm](https://helm.sh/docs/intro/install/) |

## Network Requirements

The following network ports are used by default:

| Port | Service | Configurable via |
|------|---------|-----------------|
| `9001` | Alert Agent Service REST API | `PORT` environment variable |
| `8001` | OVMS LLM server (host-mapped) | `LLM_PORT` environment variable |
| `1883` | MQTT broker (if used) | `MQTT_PORT` environment variable |

## Proxy Settings

If your environment requires an HTTP proxy, set the standard proxy environment variables before starting the service:

```bash
export http_proxy=http://proxy.example.com:8080
export https_proxy=http://proxy.example.com:8080
export no_proxy=localhost,127.0.0.1,ovms-llm
```

These are forwarded automatically to both containers in the Docker Compose setup.
