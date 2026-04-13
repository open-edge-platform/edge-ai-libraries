# Airgap (Offline) Deployment Guide

This guide explains how to deploy the VLM OpenVINO Serving microservice in an
airgapped environment — a network where the host has **no internet access**.

## Overview

By default the microservice downloads and converts models from Hugging Face Hub
at startup. In an airgapped deployment, the model must be **pre-converted** on
a machine with internet access and then transferred to the target host.

Setting the `AIRGAP_MODE` environment variable to `true` ensures:

* All Hugging Face Hub network calls are blocked (`HF_HUB_OFFLINE=1`).
* `AutoProcessor` / `AutoTokenizer` load exclusively from the local model
  directory with `local_files_only=True`.
* The startup script (`compress_model.sh`) and `convert_model()` fail fast
  with a clear error if the model directory is missing, rather than attempting
  a download.

## Prerequisites

### 1. Pre-convert the Model (Internet-Connected Machine)

On a machine **with** internet access, run the standard export:

```bash
# Using the container (recommended)
docker compose -f docker/compose.yaml run --rm vlm-openvino-serving \
  /app/scripts/compress_model.sh <MODEL_NAME> <WEIGHT_FORMAT> <HF_TOKEN>

# Or using optimum-cli directly
optimum-cli export openvino \
  --trust-remote-code \
  --model <MODEL_NAME> \
  --weight-format <WEIGHT_FORMAT> \
  <OUTPUT_DIR>
```

### 2. Verify the Model Directory

The output directory (`ov-model/<model-short-name>/<weight-format>/`) must
contain **at least** the following files:

| File | Purpose |
|------|---------|
| `openvino_model.xml` / `.bin` | OpenVINO IR model weights |
| `openvino_tokenizer.xml` | OpenVINO tokenizer |
| `tokenizer_config.json` | HF tokenizer configuration |
| `tokenizer.json` | HF fast-tokenizer data |
| `special_tokens_map.json` | Special token mappings |
| `preprocessor_config.json` | Processor configuration (images/video) |
| `config.json` | Model architecture config |

> **Tip:** The `save_preprocessors()` call during conversion already saves
> `preprocessor_config.json` and related files. Verify they are present.

### 3. Transfer to the Airgapped Host

Copy the entire model directory to the target host. Common methods:

* USB drive / removable media
* `scp` / `rsync` over an internal network
* Container image with the model baked in

## Configuration

### Docker Compose

Add `AIRGAP_MODE=true` to your `.env` file or pass it directly:

```bash
export AIRGAP_MODE=true
```

The variable is already wired through `docker/compose.yaml`.

### Volume Mounts

Ensure the `ov-models` Docker volume contains the pre-converted model
directory, or bind-mount the host path:

```yaml
volumes:
  - /path/to/local/ov-model:/app/ov-model
```

### Full Example `.env`

```env
VLM_MODEL_NAME=Qwen/Qwen2.5-VL-7B-Instruct
VLM_COMPRESSION_WEIGHT_FORMAT=int4
VLM_DEVICE=CPU
AIRGAP_MODE=true
HUGGINGFACE_TOKEN=none
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `AIRGAP_MODE is enabled but the converted model directory … does not exist` | Model not pre-converted or wrong volume mount | Verify the model directory is mounted at `ov-model/<name>/<weight>/` |
| `Cannot find … preprocessor_config.json` | Processor config missing from local dir | Re-run conversion; ensure `save_preprocessors` completed |
| `ConnectionError` / timeout during startup | `AIRGAP_MODE` not set or set to `false` | Set `AIRGAP_MODE=true` in your environment |
