# Plugins Guide

Per-plugin request bodies, accepted parameters, and ready-to-use curl examples.

**Base URL:** `http://localhost:8200/api/v1`

---

## Table of Contents

- [HuggingFace](#huggingface)
- [OpenVINO Converter](#openvino-converter)
- [Ollama](#ollama)
- [Ultralytics](#ultralytics)
- [Geti](#geti)
- [Pipeline Zoo Models](#pipeline-zoo-models)
- [HLS Healthcare](#hls-healthcare)

---

## HuggingFace

Downloads any public or gated model from HuggingFace Hub using `snapshot_download`.

### Request Body

```json
{
  "models": [
    {
      "name": "<org/model-name>",
      "hub": "huggingface",
      "revision": "<branch-or-commit>"
    }
  ]
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | HuggingFace model ID (e.g. `meta-llama/Llama-3.2-1B`) |
| `hub` | string | Yes | Must be `"huggingface"` |
| `revision` | string | No | Branch, tag, or commit hash (default: `main`) |

**Environment:** Set `HF_TOKEN` or `HUGGINGFACEHUB_API_TOKEN` for gated models.

### Output Path

Models are stored at: `<model-path>/huggingface/<org_model_name>/`
(slashes in model name replaced with underscores)

### Curl Example

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=hf-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "hub": "huggingface"
      }
    ]
  }'
```

---

## OpenVINO Converter

Converts HuggingFace models to OpenVINO IR format for deployment with OVMS.
This is a **converter** plugin — it downloads from HuggingFace first, then converts.

There are two ways to trigger conversion:

**Option A — Use `hub: "openvino"` (pure conversion flow):**
```json
{
  "models": [
    {
      "name": "<org/model-name>",
      "hub": "openvino",
      "type": "llm",
      "config": {
        "precision": "int4",
        "device": "CPU",
        "cache_size": 4
      }
    }
  ]
}
```

**Option B — Use `hub: "huggingface"` with `is_ovms: true` (download + convert):**
```json
{
  "models": [
    {
      "name": "<org/model-name>",
      "hub": "huggingface",
      "type": "llm",
      "is_ovms": true,
      "config": {
        "precision": "int8",
        "device": "CPU"
      }
    }
  ]
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | HuggingFace model ID |
| `hub` | string | Yes | `"openvino"` or `"huggingface"` |
| `type` | string | Yes | Model type — see table below |
| `is_ovms` | bool | No | `true` to trigger conversion (required with `hub: "huggingface"`) |
| `config.precision` | string | No | `int4`, `int8`, `fp16`, `fp32` (default: `int8`) |
| `config.device` | string | No | `CPU`, `GPU`, `NPU` (default: `CPU`) |
| `config.cache_size` | int | No | KV cache size in GB (LLM/VLM only) |
| `config.kv_cache_precision` | string | No | `u8` or model default |
| `config.enable_prefix_caching` | bool | No | Enable prefix caching for prompts |
| `config.pipeline_type` | string | No | `LM`, `LM_CB`, `VLM`, `VLM_CB`, `AUTO` |
| `config.overwrite_models` | bool | No | Overwrite if model already exists |
| `config.extra_quantization_params` | string | No | Advanced NNCF params (e.g. `"--sym --group-size -1"`) |

### Model Type → Export Type Mapping

| `type` value | Export type used | Typical models |
|--------------|-----------------|----------------|
| `llm` | `text_generation` | Llama, Mistral, Phi, Qwen |
| `vlm` | `text_generation` (VLM mode) | LLaVA, InternVL, Phi-3-Vision |
| `embeddings` | `embeddings_ov` | sentence-transformers, BGE |
| `rerank` | `rerank_ov` | cross-encoder rerankers |

**NPU constraint:** NPU device forces `int4` precision regardless of config.

### Output Path

`<model-path>/openvino_models/<DEVICE>/<precision>/`

### Curl Example — LLM INT4 for CPU

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=llm-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.2-1B",
        "hub": "openvino",
        "type": "llm",
        "config": {
          "precision": "int4",
          "device": "CPU",
          "cache_size": 4
        }
      }
    ]
  }'
```

### Curl Example — Embeddings for OVMS

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=embedding-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "hub": "openvino",
        "type": "embeddings",
        "config": {
          "precision": "int8",
          "device": "CPU"
        }
      }
    ]
  }'
```

---

## Ollama

Downloads Ollama models by starting a local Ollama server inside the container and running `ollama pull`.

> **Note:** Downloads are serialized — only one Ollama model downloads at a time even if multiple jobs are submitted.

### Request Body

```json
{
  "models": [
    {
      "name": "llama3.2",
      "hub": "ollama",
      "revision": "3b"
    }
  ]
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Ollama model name (e.g. `llama3.2`, `codellama`) |
| `hub` | string | Yes | Must be `"ollama"` |
| `revision` | string | No | Model tag (e.g. `3b`, `13b`, `latest`) — appended as `name:revision` |

### Output Path

`<model-path>/ollama/<model-name>/<revision>/`

### Curl Example

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=ollama-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "llama3.2",
        "hub": "ollama",
        "revision": "3b"
      }
    ]
  }'
```

---

## Ultralytics

Downloads YOLO/Ultralytics models with optional INT8 quantization.

### Request Body

```json
{
  "models": [
    {
      "name": "yolov8n",
      "hub": "ultralytics",
      "config": {
        "quantize": "coco128"
      }
    }
  ]
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Model name: `yolov8n`, `yolov8s`, `yolo_all`, `all`, or comma-separated list |
| `hub` | string | Yes | Must be `"ultralytics"` |
| `config.quantize` | string | No | Dataset name for INT8 quantization (e.g. `coco`, `coco128`) |

**Constraint:** INT8 quantization (`config.quantize`) requires a single model name — not `all`, `yolo_all`, or comma-separated.

### Model Name Values

| Value | Effect |
|-------|--------|
| `yolov8n` | Single model |
| `yolov8n,yolov8s` | Multiple models (no quantization) |
| `all` | All supported models |
| `yolo_all` | All YOLO variants |

### Output Path

`<model-path>/ultralytics/<model-name>/`

### Curl Example — With INT8 Quantization

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=yolo-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolov8n",
        "hub": "ultralytics",
        "config": {
          "quantize": "coco128"
        }
      }
    ]
  }'
```

---

## Geti

Downloads trained models from an Intel Geti server (base or optimized OpenVINO variants).

**Required environment variables before starting service:**
```bash
export GETI_HOST=https://geti.example.com
export GETI_TOKEN=<your-api-token>
export GETI_WORKSPACE_ID=<workspace-id>
```

### Request Body

```json
{
  "models": [
    {
      "name": "<project-name>",
      "hub": "geti",
      "config": {
        "export_type": "optimized",
        "model_group_id": "<model-group-id>",
        "optimized_model_id": "<optimized-model-id>",
        "model_only": true
      }
    }
  ]
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Geti project name |
| `hub` | string | Yes | Must be `"geti"` |
| `config.export_type` | string | No | `"base"` or `"optimized"` (default: `"optimized"`) |
| `config.model_group_id` | string | No | Model group ID from Geti |
| `config.optimized_model_id` | string | No | Specific optimized model ID |
| `config.model_only` | bool | No | Download model artifacts only (skip project data) |

### Output Path

`<model-path>/geti/<project-id>/<model-id>/`

---

## Pipeline Zoo Models

Downloads models from the [dlstreamer/pipeline-zoo-models](https://github.com/dlstreamer/pipeline-zoo-models) GitHub repository.

### Request Body

```json
{
  "models": [
    {
      "name": "person-vehicle-bike-detection-2004",
      "hub": "pipeline-zoo-models"
    }
  ]
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Model name, comma-separated list, or `"all"` |
| `hub` | string | Yes | `"pipeline-zoo-models"` |

### Common Pipeline Zoo Model Names

- `person-vehicle-bike-detection-2004`
- `vehicle-license-plate-detection-barrier-0106`
- `age-gender-recognition-retail-0013`
- `emotions-recognition-retail-0003`
- `face-detection-retail-0004`

### Output Path

`<model-path>/pipeline-zoo-models/<model-name>/`

### Curl Example

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=pipeline-zoo" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "person-vehicle-bike-detection-2004",
        "hub": "pipeline-zoo-models"
      }
    ]
  }'
```

---

## HLS Healthcare

Downloads pre-converted OpenVINO IR models for Intel Health & Life Sciences (HLS) demos.

### Supported Types

| `type` value | Model(s) | Description |
|-------------|----------|-------------|
| `3d-pose` | `human-pose-estimation-3d-0001` | 3D human pose estimation |
| `rppg` | `mtts_can` | Remote photoplethysmography (heart rate from video) |
| `ai-ecg` | `ecg_17920_ir10_fp16`, `ecg_8960_ir10_fp16` | ECG signal classification |

### Request Body

```json
{
  "models": [
    {
      "name": "hls-3d-pose",
      "hub": "hls",
      "type": "3d-pose"
    }
  ]
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Any string (used as job label) |
| `hub` | string | Yes | Must be `"hls"` |
| `type` | string | Yes | `"3d-pose"`, `"rppg"`, or `"ai-ecg"` |

### Output Path

`<model-path>/hls/<type>/`

### Curl Example — 3D Pose

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=hls-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "hls-3d-pose",
        "hub": "hls",
        "type": "3d-pose"
      }
    ]
  }'
```

---

## Batch Downloads

Submit multiple models in a single request — they download in parallel (except Ollama which serializes):

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=batch" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "hub": "huggingface"
      },
      {
        "name": "yolov8n",
        "hub": "ultralytics"
      }
    ]
  }'
```

Response includes one `job_id` per model:
```json
{"job_ids": ["<uuid-1>", "<uuid-2>"]}
```

---

## Checking Plugin Availability

Before submitting a job, verify which plugins are active:

```bash
curl -s http://localhost:8200/api/v1/plugins | python3 -m json.tool
```
