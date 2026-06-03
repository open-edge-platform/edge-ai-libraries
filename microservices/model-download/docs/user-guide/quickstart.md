# Quick Start

In this the microservice can be run as an ephemeral (one-shot) container that downloads or converts a model and exits automatically. This is useful for CI/CD pipelines, pre-provisioning model caches, or scripted workflows.

## Prerequisites

- Docker installed and running. Installation guide [here](https://docs.docker.com/engine/install/ubuntu/)
- `curl` and `python3` available on the host

---

## One-liner Setup

Download and run directly — no repo clone needed. The script starts a temporary Docker container, downloads the model to your local disk, and **automatically removes the container** once the operation completes.

```bash
curl -sSLO https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/release-2026.1.0/microservices/model-download/scripts/get_model.sh && source ./get_model.sh --model-name sentence-transformers/all-MiniLM-L6-v2 --hub huggingface --plugins huggingface
```

## Quick Examples

### Download a HuggingFace model

```bash
. ./get_model.sh \
  --model-name sentence-transformers/all-MiniLM-L6-v2 \
  --hub huggingface --plugins huggingface
```

### Download and convert to OpenVINO (OVMS-ready)

```bash
. ./get_model.sh \
  --model-name meta-llama/Llama-3.2-1B \
  --hub openvino \
  --type llm \
  --is-ovms \
  --precision int8 \
  --device CPU \
  --plugins huggingface,openvino
```

### Download an Ollama model

```bash
. ./get_model.sh \
  --model-name llama3.2 \
  --hub ollama \
  --plugins ollama
```

### Download an Ultralytics model

```bash
. ./get_model.sh \
  --model-name yolov8s \
  --hub ultralytics \
  --plugins ultralytics
```

---

## Advanced Options

### Model Parameters

| Argument | Description | Required |
|----------|-------------|----------|
| `--model-name <name>` | Model identifier (e.g. `meta-llama/Llama-3.2-1B`) | Yes |
| `--hub <hub>` | Source hub: `huggingface`, `ultralytics`, `ollama`, `openvino`, `geti`, `hls` | Yes |
| `--type <type>` | Model type: `llm`, `vlm`, `embeddings`, `rerank`, `vision`, `3d-pose`, `rppg`, `ai-ecg` | No |
| `--revision <rev>` | Branch, tag, or commit hash | No |
| `--is-ovms` | Convert to OpenVINO format after downloading | No |
| `--precision <prec>` | Weight precision: `int4`, `int8`, `fp16`, `fp32` (default: `int8`) | No |
| `--device <dev>` | Target device: `CPU`, `GPU`, `NPU` (default: `CPU`) | No |
| `--cache-size <gb>` | KV cache size in GB (for LLM/VLM conversion) | No |
| `--download-path <path>` | Sub-directory under models dir for downloads | No |

### Docker Options

| Argument | Description | Default |
|----------|-------------|---------|
| `--model-path <path>` | Host path for model storage | `./models` |
| `--image-tag <tag>` | Docker image tag | `2026.1.0-rc2` |
| `--plugins <list>` | Comma-separated plugins to enable | `all` |
| `--ovms-release-tag <tag>` | OVMS release tag | `v2025.4.1` |

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` | HuggingFace authentication for gated models |
| `GETI_HOST` | Geti server hostname |
| `GETI_TOKEN` | Geti authentication token |
| `GETI_WORKSPACE_ID` | Geti workspace ID |

---

## Troubleshooting

On failure, the script creates an error log at:

```
.model_download_logs/model_download_YYYYMMDD_HHMMSS.log
```

The log path is printed at the end of a failed run.

### Reading the error log

The log file contains structured sections:

```
===== Model Download Ephemeral Mode - Error Log =====
Timestamp: 2026-05-22T12:46:17+05:30
Command: source ./get_model.sh --model-name ... --hub ...
Image: model-download:2026.1.0-rc2
Model Path: /home/user/models
Plugins: huggingface,openvino

[2026-05-22T12:46:44+05:30] ERROR: Job xxx failed: <error message>

===== Job Failure: <job-id> =====
{ full JSON response from API }

===== Container Logs =====
<last 100 lines of container output>
```

### Common issues

**Plugin not activated**
```
Plugin 'openvino' was not activated during container startup. Active plugins: huggingface
```
Fix: Add the required plugin to `--plugins` (e.g., `--plugins huggingface,openvino`).

**Gated model access denied**
```
Access to Gated or private models is restricted. You must be authenticated.
```
Fix: Set `HF_TOKEN` with a token that has access to the model:
```bash
export HF_TOKEN="hf_..."
source ./get_model.sh --model-name meta-llama/Llama-2-7b-hf --hub huggingface
```

**Container failed to start**
```
ERROR: Failed to get mapped port for container.
```
Fix: Check that the Docker image exists (`docker images | grep model-download`) and rebuild if needed.

**Service health timeout**
```
ERROR: Service failed to start within 180s.
```
Fix: Check the container logs in the error log file. Common causes: missing dependencies, network issues during plugin setup.

### Cleanup stale containers

If the script was interrupted, you may need to remove the leftover container:

```bash
docker rm -f model-download-ephemeral
```
