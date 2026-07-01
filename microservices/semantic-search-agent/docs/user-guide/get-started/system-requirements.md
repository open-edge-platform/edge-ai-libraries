# System Requirements

## Hardware Requirements

- **CPU**: x86_64 or compatible processor.
- **Memory**: 4 GB RAM minimum (8 GB recommended when running OpenVINO local inference).
- **Disk**: 2 GB free space for Docker image layers and log files. Additional space required for local VLM model files if using `openvino_local` backend.
- **GPU** (optional): Intel integrated or discrete GPU supported via OpenVINO for local inference.

| Device  | Minimum              | Recommended                             |
| ------- | -------------------- | --------------------------------------- |
| CPU     | x86_64               | Dual-core or higher                     |
| Memory  | 4 GB RAM             | 8 GB RAM (16 GB for local VLM)          |
| Disk    | 2 GB free            | 10 GB free (model files vary by size)   |
| GPU     | Not required         | Intel GPU for OpenVINO local inference  |

## Software Requirements

### Operating System

- Ubuntu 22.04 LTS (validated) or a compatible Linux distribution, Windows, or macOS.
- For container deployment: Docker Engine 24+ and Docker Compose v2.

### Host Packages (Standalone Run)

For local development or standalone execution, Python development tools are required:

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip
```

### Python

- Python 3.11 or newer.
- Dependencies installed from `requirements.txt`.

### VLM Backend (Optional)

Required only when `DEFAULT_MATCHING_STRATEGY` is set to `semantic` or `hybrid`.

| Backend          | Requirement                                                                 |
| ---------------- | --------------------------------------------------------------------------- |
| `ovms`           | Running OpenVINO Model Server instance with a vision-language model loaded. |
| `openvino_local` | OpenVINO IR model files on disk. `OPENVINO_MODEL_PATH` must point to them.  |
| `openai`         | Valid `OPENAI_API_KEY` with access to the configured model.                 |

## Network Requirements

- Inbound access to TCP port `8080` (default) for the REST API.
- Inbound access to TCP port `9090` (default) for the Prometheus metrics endpoint.
- Outbound access to the OVMS server host and port if using `VLM_BACKEND=ovms`.
- Outbound internet access to `api.openai.com` if using `VLM_BACKEND=openai`.
- Port `6379` access for Redis if using `CACHE_BACKEND=redis`.
