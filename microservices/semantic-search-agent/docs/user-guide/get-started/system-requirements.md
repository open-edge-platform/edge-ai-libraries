# System Requirements

## Hardware Requirements

- **CPU**: x86_64 or compatible processor.
- **Memory**: 4-GB RAM minimum (Intel recommends 8-GB RAM when running OpenVINO local inference).
- **Disk**: 2-GB free space for Docker image layers and log files. You will need an additional space for local VLM model files if using the `openvino_local` backend.
- **GPU** (optional): Intel's integrated or discrete GPU supported via OpenVINO runtime for local inference.

| Device  | Minimum              | Recommended                             |
| ------- | -------------------- | --------------------------------------- |
| CPU     | x86_64               | Dual-core or higher                     |
| Memory  | 4-GB RAM             | 8-GB RAM (16-GB RAM for local VLM)      |
| Disk    | 2-GB free space      | 10-GB free (model files vary by size)   |
| GPU     | Not required         | Intel® GPU for OpenVINO local inference |

## Software Requirements

### Operating System

- Ubuntu OS version 22.04 LTS (validated) or a compatible Linux distribution, Windows OS, or macOS OS.
- For container deployment: Docker Engine version 24 or higher, and Docker Compose tool v2.

### Host Packages (Standalone Run)

For local development or standalone execution, you need Python development tools:

```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip
```

### Python

- Python programming language version 3.11 or newer.
- Dependencies installed from `requirements.txt`.

### VLM Backend (Optional)

Required only when you set `DEFAULT_MATCHING_STRATEGY` to `semantic` or `hybrid`.

| Backend          | Requirement                                                                    |
| ---------------- | ---------------------------------------------------------------------------    |
| `ovms`           | Running OpenVINO model server instance with a vision-language model loaded.    |
| `openvino_local` | OpenVINO IR^1^ model files on disk. `OPENVINO_MODEL_PATH` must point to them.  |
| `openai`         | Valid `OPENAI_API_KEY` with access to the configured model.                    |

> **Note**: 1. OpenVINO Intermediate Representation (IR).

## Network Requirements

- Inbound access to TCP port `8080` (default) for the REST API.
- Inbound access to TCP port `9090` (default) for the Prometheus metrics endpoint.
- Outbound access to the OpenVINO model server host and port if using `VLM_BACKEND=ovms`.
- Outbound internet access to `api.openai.com` if using `VLM_BACKEND=openai`.
- Port `6379` access for the Redis cache if using `CACHE_BACKEND=redis`.
