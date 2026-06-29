# Service Setup Reference

This document covers starting the Model Download service, configuring environment
variables, and enabling the right plugins for your use case.

---

## Prerequisites

- Docker and Docker Compose installed
- Sufficient disk space for models (LLMs can be 5–50 GB)
- (Optional) HuggingFace API token for gated models or OpenVINO conversion

---

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/microservices/model-download

# 2. Set environment variables
export REGISTRY="intel/"
export TAG=latest
export HUGGINGFACEHUB_API_TOKEN=<your-hf-token>   # optional, needed for gated HF models

# 3. Start the service
source scripts/run_service.sh up --plugins all --model-path $PWD/models
```

The service starts on port **8200** and exposes its API at `http://localhost:8200/api/v1`.

---

## Environment Variables

### HuggingFace

| Variable | Required | Purpose |
|----------|----------|---------|
| `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` | Gated models / OpenVINO conversion | HuggingFace authentication |

### Geti

| Variable | Required | Purpose |
|----------|----------|---------|
| `GETI_HOST` | Yes | Geti server URL (e.g. `https://geti.example.com`) |
| `GETI_TOKEN` | Yes | Geti API access token |
| `GETI_WORKSPACE_ID` | Yes | Workspace ID from Geti UI |
| `GETI_SERVER_SSL_VERIFY` | No | Set `False` to disable SSL verification (default: `False`) |
| `GETI_SERVER_API_VERSION` | No | API version (default: `v1`) |

### Service

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODELS_DIR` | `/opt/models` | Internal container path for model storage |
| `MODEL_PATH` | `models` | Host path prefix shown in download_path responses |
| `MAX_UPLOAD_SIZE_MB` | `500` | Max size for custom model ZIP uploads |
| `OVMS_RELEASE_TAG` | `v2025.4.1` | OpenVINO Model Server release tag for export scripts |

---

## Plugin Flags

The `--plugins` flag controls which plugins are activated at container startup.
Only activated plugins can handle download requests.

```bash
# Activate specific plugins (comma-separated, no spaces)
source scripts/run_service.sh up --plugins huggingface,openvino --model-path $PWD/models

# Activate all plugins
source scripts/run_service.sh up --plugins all --model-path $PWD/models
```

| Plugin name | Use case |
|-------------|----------|
| `huggingface` | Download any HuggingFace model |
| `openvino` | Convert models to OpenVINO IR for OVMS |
| `ollama` | Pull Ollama models |
| `ultralytics` | Download YOLO/Ultralytics models |
| `geti` | Download from Intel Geti platform |
| `pipeline-zoo-models` | Download DL Streamer pipeline-zoo models |
| `hls` | Download healthcare AI models |

> **Note:** Enabling a plugin activates its virtual environment and dependencies
> inside the container. Unused plugins add startup time — only enable what you need.

---

## run_service.sh Options

```
Usage: source scripts/run_service.sh [options] [action]

Actions:
  up      Start the service (default)
  down    Stop the service

Options:
  --build                   Build Docker image before running
  --rebuild                 Rebuild from scratch (ignore cache)
  --model-path <path>       Host directory for model storage (default: ~/models)
  --plugins <list>          Comma-separated plugins or "all"
  --ovms-release-tag <tag>  OVMS tag for export scripts (default: v2025.4.1)
  --help                    Show help
```

---

## Health Check

After the service starts, verify it is ready:

```bash
curl http://localhost:8200/api/v1/health
# Expected: {"status": "ok"}
```

---

## Docker Compose Layout

The `docker/compose.yaml` defines:
- **model-download** service: the FastAPI application on port 8200
- **ovms** service: OpenVINO Model Server (activated when using `openvino` plugin)

Models are stored in the volume mounted at `MODEL_PATH` on the host.

---

## OpenAPI Documentation

The service exposes an OpenAPI spec accessible via the Swagger UI at:
```
http://localhost:8200/api/v1/docs
```

Or fetch the raw spec:
```bash
curl http://localhost:8200/api/v1/openapi.json
```
