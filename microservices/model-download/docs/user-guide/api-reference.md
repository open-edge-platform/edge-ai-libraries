# API Reference

**Version: 1.1.0**

This document describes all REST API endpoints, request/response formats, and examples.

---

## Health Check

```bash
curl http://localhost:8200/api/v1/health
```

```json
{
  "status": "ok"
}
```

---

## Models

### List Models from a Hub - `POST /api/v1/models/list`

Lists models available on a hub using hub-specific filters and pagination. Supported hubs: `huggingface`, `ultralytics`, `pipeline-zoo-models`, `geti`.

```bash
# List HuggingFace models by author
curl -X POST http://localhost:8200/api/v1/models/list \
  -H "Content-Type: application/json" \
  -d '{
    "hub": "huggingface",
    "filters": {"author": "microsoft", "search": "phi"},
    "limit": 10,
    "offset": 0
  }'
```

```bash
# List Ultralytics models
curl -X POST http://localhost:8200/api/v1/models/list \
  -H "Content-Type: application/json" \
  -d '{
    "hub": "ultralytics",
    "filters": {"search": "yolov8"},
    "limit": 10
  }'
```

```bash
# List Geti™ models
curl -X POST http://localhost:8200/api/v1/models/list \
  -H "Content-Type: application/json" \
  -d '{
    "hub": "geti",
    "filters": {"project_name": "detection", "precision": "FP16"},
    "limit": 10
  }'
```

**Request Fields:**

| Field                  | Type   | Required | Description                                                                 |
| ---------------------- | ------ | -------- | --------------------------------------------------------------------------- |
| `hub`                  | string | yes      | Hub to list models from (`huggingface`, `ultralytics`, `pipeline-zoo-models`, `geti`) |
| `filters`              | object | no       | Hub-specific listing filters (see below)                                    |
| `limit`                | int    | no       | Max items to return (1–200, default 50)                                     |
| `offset`               | int    | no       | Items to skip for pagination (default 0)                                    |
| `override_credentials` | object | no       | Base64-encoded per-request credential overrides                             |

**Supported Filters by Hub:**

| Hub                  | Filter Fields                                                                                    |
| -------------------- | ------------------------------------------------------------------------------------------------ |
| `huggingface`        | `author`, `search`, `tags`                                                                       |
| `ultralytics`        | `search`                                                                                         |
| `pipeline-zoo-models`| `search`                                                                                         |
| `geti`               | `project_id`, `project_name`, `model_group_id`, `model_group_name`, `model_name`, `export_type`, `precision`, `model_format` |

**Response:**

```json
{
  "hub": "huggingface",
  "items": [
    {
      "name": "microsoft/Phi-3.5-mini-instruct",
      "owner": "microsoft",
      "tags": ["text-generation"],
      "license": "mit",
      "gated": false,
      "requires_token": false
    }
  ],
  "total": 100,
  "limit": 10,
  "offset": 0
}
```

---

### Download Models - `POST /api/v1/models/download`

Downloads one or more models from supported hubs and optionally converts them to OpenVINO IR format. Requests are processed asynchronously; job IDs are returned immediately.

**Query Parameter:**

| Parameter       | Type   | Required | Description                                             |
| --------------- | ------ | -------- | ------------------------------------------------------- |
| `download_path` | string | yes      | Base path/subdirectory for model downloads (relative to `MODELS_DIR`) |

```bash
# Download a HuggingFace model
curl -X POST "http://localhost:8200/api/v1/models/download?download_path=my-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "microsoft/Phi-3.5-mini-instruct",
        "hub": "huggingface",
        "type": "llm",
        "is_ovms": false
      }
    ]
  }'
```

```bash
# Download and convert to OpenVINO
curl -X POST "http://localhost:8200/api/v1/models/download?download_path=my-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "microsoft/Phi-3.5-mini-instruct",
        "hub": "openvino",
        "type": "llm",
        "is_ovms": true,
        "config": {
          "precision": "int8",
          "device": "CPU",
          "cache_size": 10
        }
      }
    ]
  }'
```

```bash
# Download an Ollama model
curl -X POST "http://localhost:8200/api/v1/models/download?download_path=my-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [{"name": "deepseek-r1", "hub": "ollama"}]
  }'
```

```bash
# Download from a remote URL
curl -X POST "http://localhost:8200/api/v1/models/download?download_path=my-models" \
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

```bash
# Download multiple models in parallel
curl -X POST "http://localhost:8200/api/v1/models/download?download_path=my-models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {"name": "microsoft/Phi-3.5-mini-instruct", "hub": "huggingface", "type": "llm"},
      {"name": "deepseek-r1", "hub": "ollama"}
    ],
    "parallel_downloads": true
  }'
```

**Model Request Fields:**

| Field                   | Type    | Required | Description                                                                 |
| ----------------------- | ------- | -------- | --------------------------------------------------------------------------- |
| `name`                  | string  | yes      | Model name/ID (format is hub-specific)                                      |
| `hub`                   | string  | yes      | Source hub (see Supported Hubs below)                                       |
| `type`                  | string  | no       | Model type (determines conversion behavior)                                 |
| `is_ovms`               | boolean | no       | Convert to OpenVINO IR format (default `false`)                             |
| `revision`              | string  | no       | Specific model revision/version to download                                 |
| `config`                | object  | no       | Configuration for OpenVINO conversion (required if `is_ovms` is `true`)     |
| `override_credentials`  | object  | no       | Per-request credential overrides (takes precedence over env vars)           |
| `validate_credentials`  | boolean | no       | Validate credentials before starting (default `false`)                      |

**Supported Hubs:**

| Hub                  | Description                          |
| -------------------- | ------------------------------------ |
| `huggingface`        | HuggingFace model hub               |
| `ollama`             | Ollama model registry                |
| `ultralytics`        | Ultralytics YOLO models             |
| `pipeline-zoo-models`| Pipeline Zoo Models                  |
| `omz`                | Open Model Zoo                       |
| `openvino`           | OpenVINO model export                |
| `geti`               | Intel Geti™                          |
| `hls`                | HLS model source                     |
| `remote-url`         | Download from a remote URL           |

**Model Types:**

| Type               | Description                      |
| ------------------ | -------------------------------- |
| `llm`              | Large language model             |
| `vlm`              | Vision-language model            |
| `embeddings`       | Embedding model                  |
| `rerank`           | Reranking model                  |
| `image_generation` | Image generation model           |
| `text2speech`      | Text-to-speech model             |
| `speech2text`      | Speech-to-text model             |
| `vision`           | Vision model                     |
| `3d-pose`          | 3D pose estimation model         |
| `rppg`             | Remote photoplethysmography      |
| `ai-ecg`           | AI ECG model                     |

**Conversion Config Fields:**

| Field              | Type    | Required | Description                                                       |
| ------------------ | ------- | -------- | ----------------------------------------------------------------- |
| `precision`        | string  | no       | Weight precision: `int4`, `int8`, `fp16`, `fp32` (default `int8`) |
| `device`           | string  | no       | Target device: `CPU`, `GPU`, `NPU`, or `HETERO:GPU,CPU` (default `CPU`) |
| `cache_size`       | int     | no       | Cache size for model optimization                                 |
| `quantize`         | string  | no       | Ultralytics quantization dataset for INT8 export                  |
| `overwrite_models` | boolean | no       | Overwrite an existing exported model (OpenVINO)                   |
| `post_processing`  | object  | no       | Post-processing overrides for OMZ model-specific workflows        |

**`name` Format by Hub:**

- `huggingface`, `ollama`, `openvino`, `geti`, `hls`, `remote-url`: single model name
- `ultralytics`: single name, comma-separated names, or `all`
- `pipeline-zoo-models`: single name, comma-separated names, or `all`
- `omz`: single name or comma-separated names (`all` is not supported)

**Response:**

```json
{
  "message": "Started processing 1 model(s)",
  "job_ids": ["download_abc123", "convert_def456"],
  "status": "processing"
}
```

**Authentication Notes:**

- `HUGGINGFACEHUB_API_TOKEN` is optional for public HuggingFace models
- `HUGGINGFACEHUB_API_TOKEN` is required for gated/private HuggingFace models and for conversion
- No authentication needed for Ollama, Ultralytics, Pipeline Zoo Models, Geti™, or HLS models

---

### Upload Custom Model - `POST /api/v1/models/upload`

Upload a ZIP file containing `model.xml` and `model.bin` at the ZIP root.

```bash
curl -X POST http://localhost:8200/api/v1/models/upload \
  -F "file=@my_model.zip" \
  -F "model_name=my_custom_model" \
  -F "provider=geti" \
  -F "framework=openvino" \
  -F "precision=FP16"
```

**Form Fields:**

| Field        | Type   | Required | Description                                        |
| ------------ | ------ | -------- | -------------------------------------------------- |
| `file`       | binary | yes      | ZIP file containing `model.xml` and `model.bin`    |
| `model_name` | string | yes      | Model name (alphanumeric, `.`, `_`, `-`, spaces)   |
| `provider`   | string | no       | Provider segment in target path                    |
| `framework`  | string | no       | Framework segment in target path                   |
| `precision`  | string | no       | Precision folder (e.g., `FP16`, `FP32`, `INT8`)   |

**Validation:**

- `model_name` allows `A-Z a-z 0-9 . _ - <space>`. Spaces are replaced with underscores. Must not start/end with `.` or contain `..`
- File size limit enforced (default 500 MB via `MAX_UPLOAD_SIZE_MB`)
- Files are read in chunks (default 8 KB via `UPLOAD_CHUNK_SIZE_KB`)
- Returns `409` if the target model path already exists

**Response:**

```json
{
  "status": "success",
  "message": "Model 'my_custom_model' uploaded successfully.",
  "job_id": "upload_abc123",
  "model_name": "my_custom_model",
  "model_path": "/opt/models/custom_uploaded_models/geti/openvino/my_custom_model/FP16"
}
```

---

### Get Completed Model Results - `GET /api/v1/models/results`

Retrieve all completed model downloads and conversions.

```bash
curl http://localhost:8200/api/v1/models/results
```

```json
{
  "results": [
    {
      "job_id": "download_abc123",
      "model_name": "BAAI/bge-small-en-v1.5",
      "hub": "huggingface",
      "operation_type": "download",
      "status": "completed",
      "model_path": "/opt/models/preloaded/BAAI/bge-small-en-v1.5",
      "is_ovms": false,
      "completion_time": "2026-07-16T08:31:10.000000"
    }
  ]
}
```

---

### Get Jobs for a Model - `GET /api/v1/models/jobs`

Retrieve all jobs related to a specific model.

```bash
curl "http://localhost:8200/api/v1/models/jobs?model_name=microsoft/Phi-3.5-mini-instruct"
```

```json
{
  "jobs": [
    {
      "id": "5f0d4eba-c79c-4d02-97a6-43c3d0168ca0",
      "operation_type": "download",
      "model_name": "microsoft/Phi-3.5-mini-instruct",
      "hub": "huggingface",
      "status": "completed",
      "output_dir": "/opt/models/preloaded",
      "start_time": "2026-07-16T08:30:00.000000",
      "completion_time": "2026-07-16T08:31:10.000000"
    }
  ]
}
```

---

## Jobs

### List All Jobs - `GET /api/v1/jobs`

Retrieve all in-memory jobs.

```bash
curl http://localhost:8200/api/v1/jobs
```

```json
{
  "jobs": [
    {
      "id": "5f0d4eba-c79c-4d02-97a6-43c3d0168ca0",
      "operation_type": "download",
      "model_name": "BAAI/bge-small-en-v1.5",
      "hub": "huggingface",
      "output_dir": "/opt/models/preloaded",
      "status": "completed",
      "start_time": "2026-07-16T08:30:00.000000",
      "completion_time": "2026-07-16T08:31:10.000000",
      "plugin_name": "huggingface",
      "model_type": "embeddings"
    }
  ]
}
```

### Get Job Status - `GET /api/v1/jobs/{job_id}`

Retrieve the status and details of a specific job.

```bash
curl http://localhost:8200/api/v1/jobs/5f0d4eba-c79c-4d02-97a6-43c3d0168ca0
```

```json
{
  "id": "5f0d4eba-c79c-4d02-97a6-43c3d0168ca0",
  "operation_type": "download",
  "model_name": "BAAI/bge-small-en-v1.5",
  "hub": "huggingface",
  "output_dir": "/opt/models/preloaded",
  "status": "downloading",
  "start_time": "2026-07-16T08:30:00.000000",
  "plugin_name": "huggingface",
  "model_type": "embeddings"
}
```

### Cancel a Job - `POST /api/v1/jobs/{job_id}/cancel`

Cancel a job that is in a cancellable state (`queued`, `downloading`, or `converting`).

```bash
curl -X POST http://localhost:8200/api/v1/jobs/download_abc123/cancel
```

```json
{
  "message": "Job download_abc123 has been cancelled",
  "job_id": "download_abc123",
  "status": "canceled"
}
```

**Job Statuses:**

| Status        | Description                      |
| ------------- | -------------------------------- |
| `queued`      | Job is waiting to be processed   |
| `downloading` | Model download in progress       |
| `converting`  | Model conversion in progress     |
| `completed`   | Job finished successfully        |
| `failed`      | Job encountered an error         |
| `canceled`    | Job was cancelled by the user    |

---

## Plugins

### List Available Plugins - `GET /api/v1/plugins`

Retrieve information about all available plugins, their capabilities, and status.

```bash
curl http://localhost:8200/api/v1/plugins
```

```json
{
  "available_plugins": {
    "hub": [
      {
        "name": "huggingface",
        "type": "hub",
        "description": "Download models from HuggingFace",
        "capabilities": {
          "supports_parallel_downloads": true,
          "supports_listing": true,
          "listing_filter_fields": ["author", "search", "tags"]
        },
        "available": true
      }
    ]
  },
  "total_count": 8,
  "available_count": 6,
  "activation_instructions": "Enable/disable plugins via environment variables"
}
```

---

## Endpoint Summary

### Models (POST)

| Endpoint                              | Description                                    |
| ------------------------------------- | ---------------------------------------------- |
| `POST /api/v1/models/list`            | List models available on a hub                 |
| `POST /api/v1/models/download`        | Download and optionally convert models         |
| `POST /api/v1/models/upload`          | Upload a custom model ZIP file                 |

### Models (GET)

| Endpoint                              | Description                                    |
| ------------------------------------- | ---------------------------------------------- |
| `GET /api/v1/models/results`          | Get completed model operations                 |
| `GET /api/v1/models/jobs`             | Get jobs for a specific model                  |

### Jobs

| Endpoint                              | Description                                    |
| ------------------------------------- | ---------------------------------------------- |
| `GET /api/v1/jobs`                    | List all jobs                                  |
| `GET /api/v1/jobs/{job_id}`           | Get job status                                 |
| `POST /api/v1/jobs/{job_id}/cancel`   | Cancel a running or queued job                 |

### Other

| Endpoint                              | Description                                    |
| ------------------------------------- | ---------------------------------------------- |
| `GET /api/v1/health`                  | Health check                                   |
| `GET /api/v1/plugins`                 | List available plugins                         |

---

## Response Models

| Endpoint                            | Response Model          |
| ----------------------------------- | ----------------------- |
| `GET /api/v1/health`                | `HealthResponse`        |
| `POST /api/v1/models/list`          | `ModelListResponse`     |
| `POST /api/v1/models/download`      | `DownloadResponse`      |
| `POST /api/v1/models/upload`        | `UploadResponse`        |
| `GET /api/v1/models/results`        | `ModelResultsResponse`  |
| `GET /api/v1/models/jobs`           | `JobListResponse`       |
| `GET /api/v1/jobs`                  | `JobListResponse`       |
| `GET /api/v1/jobs/{job_id}`         | `Job`                   |
| `POST /api/v1/jobs/{job_id}/cancel` | `CancelJobResponse`     |
| `GET /api/v1/plugins`               | `PluginsResponse`       |

---

## HTTP Status Codes

| Code                       | Scenario                                                                    |
| -------------------------- | --------------------------------------------------------------------------- |
| `200 OK`                   | Request successful                                                          |
| `400 Bad Request`          | Invalid hub, missing dependencies, or plugin not available                   |
| `401 Unauthorized`         | Authentication failed for the hub                                           |
| `404 Not Found`            | Job or model not found                                                      |
| `409 Conflict`             | Model already exists (upload)                                               |
| `413 Content Too Large`    | Uploaded file exceeds configured size limit                                 |
| `422 Unprocessable Entity` | Validation error — malformed JSON, missing required fields                  |
| `429 Too Many Requests`    | Rate limit exceeded                                                         |
| `500 Internal Server Error`| Server error (unexpected exception)                                         |
| `501 Not Implemented`      | Hub does not support the requested operation (e.g., listing)                |
| `502 Bad Gateway`          | Upstream hub request failed                                                 |

---

## License

Copyright (C) 2025-2026 Intel Corporation

SPDX-License-Identifier: Apache-2.0
