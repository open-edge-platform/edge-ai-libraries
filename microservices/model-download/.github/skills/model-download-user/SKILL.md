---
name: model-download-user
description: >
  Download and convert AI models using the Model Download microservice.
  Use this skill whenever a user wants to: download a model from HuggingFace,
  Ollama, Ultralytics, Geti, or Pipeline Zoo; convert a model to OpenVINO IR
  format for OVMS; download healthcare AI models (3D Pose, rPPG, AI-ECG) via
  the HLS plugin; set up the model download service; submit a download or
  conversion job via the REST API; or ask "how do I get model X working with
  OVMS?". Also trigger on phrases like "pull model", "download weights",
  "convert to int4", "OVMS-ready model", "prepare model for inference".
argument-hint: >
  Describe the model you want (e.g. "download Llama-3.2-1B from HuggingFace
  and convert to OpenVINO INT4 for CPU with OVMS")
---

# Model Download Agent

Set up the Model Download microservice and walk the user through downloading
or converting any supported model using the REST API.

> **Preview:** This skill is in preview — share feedback to help improve it.

## When to Use

- User wants to download a model from HuggingFace, Ollama, Ultralytics, Geti, Pipeline Zoo, or HLS
- User wants to convert a HuggingFace model to OpenVINO IR format for OVMS deployment
- User asks about model precision conversion (INT4/INT8/FP16/FP32)
- User needs to target a specific device (CPU, GPU, NPU)
- User wants to download healthcare AI models (3D Pose, rPPG, AI-ECG)
- User is integrating model downloads into a Docker Compose workflow

## Supported Hubs at a Glance

| Hub | `hub` value | What it does | Required env vars |
|-----|-------------|--------------|-------------------|
| HuggingFace | `huggingface` | Downloads any public or gated HF model | `HF_TOKEN` (gated only) |
| Ollama | `ollama` | Downloads Ollama models, runs local Ollama server | — |
| Ultralytics | `ultralytics` | Downloads YOLO models, optional INT8 quantization | — |
| OpenVINO | `openvino` | Converts HF models → OpenVINO IR for OVMS | `HF_TOKEN` (usually needed) |
| Geti | `geti` | Downloads trained models from Intel Geti platform | `GETI_HOST`, `GETI_TOKEN`, `GETI_WORKSPACE_ID` |
| Pipeline Zoo | `pipeline-zoo-models` | Downloads DL Streamer pipeline-zoo models | — |
| HLS | `hls` | Downloads healthcare AI models (3d-pose, rppg, ai-ecg) | — |

## Ollama Quick-Reference

> **Always use these exact field names for Ollama requests — the API differs from what
> generic model-download documentation implies.**

```json
{
  "models": [
    {
      "hub": "ollama",
      "name": "<model-family>",
      "revision": "<tag>"
    }
  ]
}
```

- **`hub`** must be `"ollama"` (not `model_hub`, not `type`)
- **`name`** is the base model family: `"llama3.2"`, `"mistral"`, `"gemma2"` (no tag suffix)
- **`revision`** is the tag: `"3b"`, `"7b"`, `"latest"` (separate field, not `model_name`)
- **Port is always `8200`** (not 8080, not 8000)
- **Plugin flag**: `source scripts/run_service.sh up --plugins ollama`

Example — download llama3.2:3b:
```bash
curl -s -X POST "http://localhost:8200/api/v1/models/download?download_path=ollama-models" \
  -H "Content-Type: application/json" \
  -d '{"models": [{"hub": "ollama", "name": "llama3.2", "revision": "3b"}]}'
```

## Common Mistakes to Avoid

| Mistake | Correct |
|---------|---------|
| Port `8080` or `8000` | Port **`8200`** always |
| `"model_hub": "ollama"` | `"hub": "ollama"` |
| `"model_name": "llama3.2:3b"` | `"name": "llama3.2", "revision": "3b"` |
| `docker compose up -d` | `source scripts/run_service.sh up --plugins <list>` |
| Starting without `--plugins <hub>` | Always activate the plugin for your hub |
| Polling `/api/v1/jobs` without job ID | Use the `job_ids[0]` from the download response |

---

## Reference Lookup

Read a reference file only when you need the detail it contains:

| Reference | When to read |
|-----------|-------------|
| [service-setup.md](./references/service-setup.md) | Starting the service, Docker Compose, plugin flags, env vars |
| [plugins-guide.md](./references/plugins-guide.md) | Per-plugin request bodies, parameters, and curl examples |
| [troubleshooting.md](./references/troubleshooting.md) | Auth errors, stuck jobs, plugin not activated, venv failures |

## Example Scenarios

Read these only if the user's request matches:

| File | Covers |
|------|--------|
| [examples/huggingface.md](./examples/huggingface.md) | Downloading public and gated HF models |
| [examples/openvino-llm.md](./examples/openvino-llm.md) | LLM → OpenVINO conversion (INT4/INT8) |
| [examples/openvino-vlm.md](./examples/openvino-vlm.md) | VLM → OpenVINO conversion |
| [examples/openvino-embeddings.md](./examples/openvino-embeddings.md) | Embedding model → OpenVINO for OVMS |
| [examples/ollama.md](./examples/ollama.md) | Pulling Ollama models |
| [examples/ultralytics-quantized.md](./examples/ultralytics-quantized.md) | YOLO models + INT8 quantization |
| [examples/geti.md](./examples/geti.md) | Downloading from Intel Geti |
| [examples/hls-healthcare.md](./examples/hls-healthcare.md) | 3D Pose, rPPG, AI-ECG healthcare models |
| [examples/pipeline-zoo.md](./examples/pipeline-zoo.md) | DL Streamer pipeline-zoo models |

---

## Procedure

### Execution Overview

After Step 0 (gather requirements), start the service setup in parallel with composing the API call.

```
Step 0 (gather requirements — interactive)
  │
  ├──► Step 1 (service setup — may require user action)
  └──► Step 2 (compose API call body — reasoning)
         │
         ├──► Step 3 (submit job + poll status)
         └──► Step 4 (verify result + next steps)
```

---

### Step 0 — Gather Requirements

Extract the following from the user's prompt. If anything is missing, ask before proceeding.

| Required | What to look for | Default if absent |
|----------|-----------------|-------------------|
| **Model name** | Exact model identifier (e.g. `meta-llama/Llama-3.2-1B`) | Must ask |
| **Hub** | One of: `huggingface`, `ollama`, `ultralytics`, `openvino`, `geti`, `pipeline-zoo-models`, `hls` | Must ask |
| **Conversion needed?** | User says "OVMS", "OpenVINO format", "convert", "is_ovms" | `false` |
| **Device** | CPU / GPU / NPU | `CPU` |
| **Precision** | int4 / int8 / fp16 / fp32 | `int8` for LLMs; `fp16` for others |
| **Model type** | llm / vlm / embeddings / rerank / vision / 3d-pose / rppg / ai-ecg | Infer from context |

**OpenVINO-specific rules (ask only if hub is `openvino` or `is_ovms: true`):**
- NPU forces `int4` regardless of other settings
- LLM/VLM conversions support `cache_size` (KV cache in GB) — ask if user mentioned memory constraints
- Embeddings and reranker conversions use `text_generation`/`embeddings_ov`/`rerank_ov` export types internally — these are resolved automatically from `type`

**If the user's prompt explicitly names a model AND hub**, go straight to Step 1. Otherwise ask.

---

### Step 1 — Service Setup

Read [service-setup.md](./references/service-setup.md) for full details.

Show the user the service startup command, using only the plugins their request requires:

```bash
# Clone (if not already done)
git clone https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries/microservices/model-download

# Set env vars
export HUGGINGFACEHUB_API_TOKEN=<your-hf-token>   # if using HF or OpenVINO
export REGISTRY="intel/"
export TAG=latest

# Start service (adjust --plugins to match what you need)
source scripts/run_service.sh up --plugins <comma-separated-list> --model-path $PWD/models
```

Plugin list recommendations:
- HuggingFace only → `--plugins huggingface`
- HuggingFace + OpenVINO conversion → `--plugins huggingface,openvino`
- Ollama → `--plugins ollama`
- Ultralytics → `--plugins ultralytics`
- All → `--plugins all`

Confirm the service is healthy before proceeding:
```bash
curl http://localhost:8200/api/v1/health
# Expected: {"status": "ok"}
```

---

### Step 2 — Compose the API Request

Read [plugins-guide.md](./references/plugins-guide.md) for the exact request body for each plugin.

The general request shape for `POST /api/v1/models/download?download_path=<subdir>` is:

```json
{
  "models": [
    {
      "name": "<model-identifier>",
      "hub": "<hub-value>",
      "type": "<model-type-or-omit>",
      "is_ovms": false,
      "config": {}
    }
  ]
}
```

Key rules:
- `is_ovms: true` triggers OpenVINO conversion after HuggingFace download
- `hub: "openvino"` triggers pure conversion (model already implicitly from HuggingFace)
- `config` holds precision, device, cache_size, and plugin-specific params
- `download_path` query param sets the subdirectory under the model store

---

### Step 3 — Submit Job and Poll Status

```bash
# 1. Submit download job
JOB_RESPONSE=$(curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=my-models" \
  -H "Content-Type: application/json" \
  -d '<your-request-body>')

echo "$JOB_RESPONSE"
# Response: {"job_ids": ["<uuid>"]}

# 2. Extract job ID
JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_ids'][0])")

# 3. Poll until completed or failed
watch -n 5 "curl -s http://localhost:8200/api/v1/jobs/$JOB_ID | python3 -m json.tool"
```

Job status values: `queued` → `downloading` / `converting` → `completed` / `failed`

If status is `failed`, read the `error` field and check [troubleshooting.md](./references/troubleshooting.md).

---

### Step 4 — Verify and Next Steps

```bash
# List all completed downloads
curl -s http://localhost:8200/api/v1/models/results | python3 -m json.tool

# Check a specific model's jobs
curl -s "http://localhost:8200/api/v1/models/jobs?model_name=<model-name>" | python3 -m json.tool
```

After confirming success, tell the user:
- The host path where the model was saved (shown in the job result's `download_path`)
- For OVMS conversions: how to mount the model directory into OVMS and which model name to use
- For Ollama: the model is stored inside the container's model store volume

**Quick alternative:** For one-shot, ephemeral container use (CI/CD, scripted workflows), show the `get_model.sh` one-liner from [scripts/get_model.sh](../../../microservices/model-download/scripts/get_model.sh):
```bash
curl -sSLO https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/model-download/scripts/get_model.sh
source ./get_model.sh --model-name <model> --hub <hub> --plugins <plugins>
```
