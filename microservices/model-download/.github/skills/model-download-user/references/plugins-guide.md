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
- [Open Model Zoo (OMZ)](#open-model-zoo-omz)
- [Remote URL](#remote-url)
- [Custom Model Upload](#custom-model-upload)

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

**Environment:** For compose-based startup, set `HUGGINGFACEHUB_API_TOKEN` on the host. Docker maps it into the container as `HF_TOKEN`. This value is used **as-is (plain text, not base64)** — it's injected directly into the container environment.

### Output Path

Models are stored at: `<model-path>/<download_path>/huggingface/<org_model_name>/`
(`<download_path>` is the `download_path` query parameter from the request URL)
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

### Gated Models — Per-Request Token Override

For gated repos (e.g. `meta-llama/Llama-3.1-8B-Instruct`), accept the model's
license on the HF model page first. Instead of restarting the service with a
new `HUGGINGFACEHUB_API_TOKEN`, pass the token per-request via a top-level
`override_credentials.HF_TOKEN` field on the model entry (a sibling of
`name`/`hub`/`config`, **not** nested inside `config`). **This value must be
base64-encoded** — unlike the host env var above, the API/MCP request field
always expects base64, regardless of the `sensitive` flag:

```bash
# Encode the token first
echo -n 'hf_xxx' | base64
# e.g. aGZfeHh4

curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=hf-gated" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.1-8B-Instruct",
        "hub": "huggingface",
        "override_credentials": {
          "HF_TOKEN": "<base64_HF_token>"
        }
      }
    ]
  }'
```

When calling this through the MCP `download_model` tool, pass the same
base64-encoded value as the tool's top-level `override_credentials.HF_TOKEN`
argument — do not send the raw token, and do not nest it under `config`.

---

## OpenVINO Converter

Converts HuggingFace models to OpenVINO IR format for deployment with OVMS.
This is a **converter** plugin — it downloads from HuggingFace first, then converts.

Use `hub: "openvino"` (pure conversion flow):**
```json
{
  "models": [
    {
      "name": "<org/model-name>",
      "hub": "openvino",
      "type": "llm",
      "is_ovms": true,
      "config": {
        "precision": "int4",
        "device": "CPU",
        "cache_size": 4
      }
    }
  ]
}
```


### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | HuggingFace model ID |
| `hub` | string | Yes | Use `"openvino"` for the current REST conversion flow |
| `type` | string | Yes | Model type — see table below |
| `is_ovms` | bool | Yes for conversion | Set to `true` to trigger OpenVINO conversion |
| `config.precision` | string | No | `int4`, `int8`, `fp16`, `fp32` (default: `int8`) |
| `config.device` | string | No | `CPU`, `GPU`, `NPU`, or `HETERO:<dev>[,<dev>...]` e.g. `HETERO:GPU,CPU` (default: `CPU`) |
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
| `vlm` | `text_generation` (VLM mode) | LLaVA, InternVL, Phi-3-Vision, Gemma-4 |
| `embeddings` | `embeddings_ov` | sentence-transformers, BGE, GTE |
| `rerank` | `rerank_ov` | cross-encoder rerankers |
| `text2speech` | `text2speech` | SpeechT5, Kokoro |
| `speech2text` | `speech2text` | Whisper |
| `image_generation` | `image_generation` | Stable Diffusion, Dreamlike |

**NPU constraint:** NPU device forces `int4` precision regardless of config. This applies only to the exact `NPU` device — HETERO combinations (e.g. `HETERO:NPU,CPU`) keep the requested precision.

### Output Path

`<model-path>/<download_path>/openvino_models/<device>/<precision>/`
(the device segment is lowercased in the actual path, e.g. `cpu`, `hetero_gpu_cpu`)

The device segment is a lowercase filesystem-safe slug: `HETERO:GPU,CPU` becomes `hetero_gpu_cpu`.

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
        "is_ovms":true,
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
        "is_ovms": true,
        "config": {
          "precision": "int8",
          "device": "CPU"
        }
      }
    ]
  }'
```

### Gated Models — Conversion Requires the Same Token Rules as HuggingFace

The `openvino` hub downloads the source weights from HuggingFace before
converting, so gated/private models (e.g. `meta-llama/Llama-3.2-1B`) need the
same authentication as the HuggingFace plugin — and the **same two paths with
different encodings** apply:

- Service/compose startup or `get_model.sh` CLI: set `HUGGINGFACEHUB_API_TOKEN`
  on the host as the **raw** token (plain text, not base64).
- Per-request override: add a top-level `override_credentials.HF_TOKEN` field
  (sibling of `name`/`hub`/`config`) with the token **base64-encoded**.

```bash
echo -n 'hf_xxx' | base64

curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=llm-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.2-1B",
        "hub": "openvino",
        "type": "llm",
        "is_ovms": true,
        "config": {
          "precision": "int4",
          "device": "CPU",
          "cache_size": 4
        },
        "override_credentials": {
          "HF_TOKEN": "<base64_HF_token>"
        },
        "validate_credentials": true
      }
    ]
  }'
```

**Tip:** Set `validate_credentials: true` for conversion jobs. It runs a quick
credential pre-check before the (often multi-minute) conversion starts, so a
bad or wrongly-encoded token surfaces immediately instead of after the job has
been running for several minutes.

---

## Ollama

Downloads Ollama models by starting a local Ollama server inside the container and running `ollama pull`.

> [!NOTE]
> Downloads are serialized — only one Ollama model downloads at a time even if multiple jobs are submitted.

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

`<model-path>/<download_path>/ollama/<model-name>/<revision>/`

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

`<model-path>/<download_path>/ultralytics/<model-name>/`

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

`<model-path>/<download_path>/geti/<project-id>/<model-id>/`

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

`<model-path>/<download_path>/pipeline-zoo-models/<model-name>/`

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

`<model-path>/<download_path>/hls/<type>/`

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

## Open Model Zoo (OMZ)

Downloads and converts models from the [Open Model Zoo](https://github.com/openvinotoolkit/open_model_zoo) using `omz_downloader` + `omz_converter` (requires the OMZ tool venv to be available in the image).

### Request Body

```json
{
  "models": [
    {
      "name": "<omz-model-name>",
      "hub": "omz"
    }
  ]
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | OMZ model name, or a comma-separated list (`"all"` is **not** supported for `omz`) |
| `hub` | string | Yes | Must be `"omz"` |
| `config.post_processing` | object | No | Optional post-processing overrides applied after conversion for models with model-specific rules |

### Output Path

`<model-path>/<download_path>/omz/<model-name>/`

### Curl Example

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=omz-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "human-pose-estimation-0001",
        "hub": "omz"
      }
    ]
  }'
```

---

## Remote URL

Downloads a model packaged as a tarball archive from an arbitrary URL supplied per-request. The resolved URL is validated against a host/path allowlist (`EXTERNAL_SOURCES_URL_ALLOWLIST` env var, or the plugin's built-in defaults) before any request is made — secure by default.

### Request Body

```json
{
  "models": [
    {
      "name": "<model-name>",
      "hub": "remote-url",
      "config": {
        "url": "https://github.com/<org>/<repo>/raw/main/{name}.tar"
      }
    }
  ]
}
```

### Parameters

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Model name — substituted for `{name}` in `config.url` if present |
| `hub` | string | Yes | Must be `"remote-url"` |
| `config.url` | string | Yes | Archive URL (tarball); must match the configured allowlist or the request is rejected |

### Output Path

`<model-path>/<download_path>/remote-url/<model-name>/`

### Curl Example

```bash
curl -s -X POST \
  "http://localhost:8200/api/v1/models/download?download_path=remote-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "wind-turbine-anomaly-detection",
        "hub": "remote-url",
        "config": {
          "url": "https://github.com/open-edge-platform/edge-ai-resources/raw/main/timeseries-udf-deployment-packages/{name}.tar"
        }
      }
    ]
  }'
```

---

## Custom Model Upload

Separate from the download flow — uploads a ZIP file (`model.xml` + `model.bin` at the ZIP root) directly via `POST /api/v1/models/upload` (multipart form, not the JSON `models` request body used by the other hubs).

```bash
curl -X POST http://localhost:8200/api/v1/models/upload \
  -F "file=@my_model.zip" \
  -F "model_name=my_custom_model" \
  -F "provider=geti" \
  -F "framework=openvino" \
  -F "precision=FP16"
```

| Field | Required | Description |
|-------|----------|--------------|
| `file` | Yes | ZIP file containing `model.xml` and `model.bin` |
| `model_name` | Yes | Alphanumeric, `.`, `_`, `-`, spaces (spaces become underscores) |
| `provider` | No | Provider segment in the target path |
| `framework` | No | Framework segment in the target path |
| `precision` | No | Precision folder, e.g. `FP16`, `FP32`, `INT8` |

Returns `409 Conflict` if the target model path already exists; default upload size limit is 500 MB (`MAX_UPLOAD_SIZE_MB`).

---

## Batch Downloads

Submit multiple models in a single request. Set the top-level `parallel_downloads: true` flag
to download them concurrently (except Ollama, which always serializes); omit it, or set it to
`false`, and models are processed sequentially — this is the default:

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
    ],
    "parallel_downloads": true
  }'
```

Response includes one `job_id` per model:
```json
{"message": "Started processing 2 model(s)", "job_ids": ["<uuid-1>", "<uuid-2>"], "status": "processing"}
```

---

## Checking Plugin Availability

Before submitting a job, verify which plugins are active:

```bash
curl -s http://localhost:8200/api/v1/plugins | jq .
```
