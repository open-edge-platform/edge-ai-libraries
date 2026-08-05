# Get Started

The Model Download is a microservice that downloads models from multiple hubs as follows: Hugging Face, Ollama, Geti™ software, Ultralytics, Pipeline Zoo Models, Open Model Zoo (OMZ), remote URL, and HLS. It supports conversion to OpenVINO™ model server format for Hugging Face models, supports uploading custom model ZIP artifacts, and exposes a RESTful API for managing model downloads, uploads, and conversions.

> **Note:** Model Download replaces Model Registry, which will be deprecated soon. See [Migrate from Model Registry to Model Download](./get-started/migration.md) for the migration guidelines.

## Features

- Downloads models from Hugging Face, Ollama, Geti software, Ultralytics, Pipeline Zoo Models, Open Model Zoo (OMZ), remote URL, and HLS hubs
- Lists available models from supported hubs before download
- Converts Hugging Face models to OpenVINO model server format
- Supports multiple model precisions (INT4, INT8, FP16, and FP32)
- Supports various device targets (CPU, GPU, and NPU), including heterogeneous execution via `HETERO:<dev>[,<dev>...]` (e.g. `HETERO:GPU,CPU`)
- OpenVINO plugin supports NPU model conversion exclusively in INT4 precision.
- Models supported for health AI suites(AI-ECG, rPPG and 3D Pose) with HLS plugin.
- Supports parallel download
- Supports configurable model caching
- Optionally schedules configured model downloads when the service starts
- Supports custom model upload through `POST /models/upload`
- Supports per-request credential overrides via `override_credentials`
- Supports pre-download credential validation via `validate_credentials`
- Supports job cancellation for queued, downloading, or converting jobs
- Exposes a REST API with OpenAPI documentation

## Prerequisites

- (Optional) Hugging Face API token, required for gated Hugging Face models or conversion.
- Sufficient disk space for model storage.
- See [System Requirements](./get-started/system-requirements.md)

## Start with Setup Script

### 1. Clone the repository

```bash
# Clone the latest on the mainline
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries
# Alternatively, clone a specific release branch
git clone https://github.com/open-edge-platform/edge-ai-libraries.git edge-ai-libraries -b <release-tag>
```

### 2. Navigate to the directory

```bash
cd edge-ai-libraries/microservices/model-download
```

### 3. Configure the environment variables

```bash
export REGISTRY="intel/"
export TAG=latest
export HUGGINGFACEHUB_API_TOKEN=<your-huggingface-token>
```

To use the Geti™ plugin, set these variables:

```bash
export GETI_WORKSPACE_ID=<YOUR_GETI_WORKSPACE_ID>
export GETI_HOST=<GETI_HOST_ADDRESS>
export GETI_TOKEN=<GETI_ACCESS_TOKEN>
export GETI_SERVER_API_VERSION=v1
export GETI_SERVER_SSL_VERIFY=False  # Default is FALSE
```

> **Note:** For Geti™ software setup instructions, see the documentation [here](https://github.com/open-edge-platform/geti).

To customize the `remote-url` hub allowlist (optional), set:

```bash
export EXTERNAL_SOURCES_URL_ALLOWLIST=<comma-separated host/path prefixes> # optional; when unset, the default allowlist in src/plugins/external_sources/sources.yaml is used
```

### 4. Launch the service and enable the plugins

```bash
source scripts/run_service.sh up --plugins all --model-path <host path>
```

> **Note:** For public models, no token is needed. Set the Hugging Face token via the `HUGGINGFACEHUB_API_TOKEN` environment variable to download GATED models and for conversion to OpenVINO IR format.

> **Note:** Ensure the host path does not require privileged access for directory creation. Intel recommends using `$PWD/host_path` or a similar location within your work directory.

The `run_service.sh` script is a Docker Compose wrapper that builds and manages the model download service container with configurable plugins, model paths, and deployment options.

Options available with the script:

```bash
source scripts/run_service.sh [options] [action]
```

**Actions**:

```text
up                     Start the services (default)
down                   Stop the services
```

**Options**:

| Option                   | Description                                                                                                                                   |
|--------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `--build`                | Builds the Docker image before running                                                                                                        |
| `--rebuild`              | This flag instructs to ignore any existing cached images, and rebuild them from scratch using the Dockerfile definitions                      |
| `--model-path <path>`    | Sets the custom model path (default: `$HOME/models/`)                                                                                         |
| `--plugins <list>`       | Comma-separated list of plugins to enable (e.g., `huggingface,ollama,openvino,ultralytics,pipeline-zoo-models,remote-url,omz,geti,hls`) or `all` to enable all available plugins |
| `--ovms-release-tag <tag>` | Set OVMS release tag (e.g., `v2025.4.1`) (default: `v2025.4.1`)                                                                             |
| `--help`                 | Shows this help message                                                                                                                       |

**Examples**:

   - Start the service with default settings: `source scripts/run_service.sh up`
   - Stop the service: `source scripts/run_service.sh down`
   - Enable specific plugins: `source scripts/run_service.sh up --plugins huggingface`
   - Enable multiple plugins: `source scripts/run_service.sh up --plugins huggingface,ollama,ultralytics,pipeline-zoo-models,remote-url,omz,geti`
   - Use a custom model storage: `source scripts/run_service.sh up --model-path /data/my-models`
   - Production deployment with all plugins: `source scripts/run_service.sh up --plugins all --model-path tmp/models`
   - Display usage information: `source scripts/run_service.sh --help`

### 5. Access the service

- The service will be available at `http://<host-ip>:8200/api/v1/docs`, where you can view the
  Swagger documentation for the available APIs.

## Download Models at Startup

The service can schedule model downloads and conversions automatically from a configuration file

See [Download Models at Startup](./get-started/startup-models.md) for the full configuration
schema.

## Verification

- Ensure that the application is running by checking the Docker container status:

  ```bash
  docker ps
  ```

- Access the application dashboard and verify that it is functioning as expected.

## Sample usage with CURL Command

**List models available on a hub:**

Use `POST /api/v1/models/list` to discover model names before calling `POST /api/v1/models/download`. Specify the target hub with the `hub` field in the request body. Listing is currently supported for `huggingface`, `ultralytics`, `pipeline-zoo-models`, and `geti`. Hubs that do not expose a catalog return `501`.

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/list" \
  -H "Content-Type: application/json" \
  -d '{
    "hub": "huggingface",
    "filters": {
      "author": "microsoft",
      "search": "phi"
    },
    "limit": 10,
    "offset": 0
  }'
```

For Ultralytics or Pipeline Zoo Models, use the `search` filter:

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/list" \
  -H "Content-Type: application/json" \
  -d '{
    "hub": "ultralytics",
    "filters": {
      "search": "yolov8"
    },
    "limit": 10,
    "offset": 0
  }'
```

For Geti™ software, listing discovers the latest model of every model group across the projects in the configured workspace. Each item's `model_type` is the Geti task type (for example, `DETECTION` or `CLASSIFICATION`) resolved from the model group's task, and `metadata` includes `project_id`, `project_name`, `model_group_id`, `model_group_name`, `model_id`, and `optimized_model_ids`. Requires `GETI_HOST`, `GETI_TOKEN`, and `GETI_WORKSPACE_ID` to be set.

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/list" \
  -H "Content-Type: application/json" \
  -d '{
    "hub": "geti",
    "filters": {
      "project_name": "detection",
      "precision": "FP16"
    },
    "limit": 10,
    "offset": 0
  }'
```

Call `GET /api/v1/plugins` to see which plugins support listing and which `listing_filter_fields` each plugin accepts. Hugging Face supports `author`, `search`, and `tags`. The `author` filter is the repository namespace and accepts a user, owner, or organization name (for example, `microsoft` or `meta-llama`); `tags` filters by Hugging Face tags (library, language, task, license, and so on). Each returned Hugging Face item also includes `license`, `gated` (`false`, `"auto"`, or `"manual"`), and `requires_token` (true when the model is gated and needs an HF token to download). Ultralytics and Pipeline Zoo Models support `search`. Geti™ supports `project_id`, `project_name`, `model_group_id`, `model_group_name`, `model_name`, `export_type`, `precision`, and `model_format`.

> **Name format by hub (`models[].name`):**
> `huggingface`, `ollama`, `openvino`, `geti`, `hls`, `remote-url`: single model name.
> `ultralytics`: single name, comma-separated names, or `all`.
> `pipeline-zoo-models`: single name, comma-separated names, or `all`.
> `omz`: single name or comma-separated names (`all` is not supported).

**Download a Hugging Face model:**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=hf_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "microsoft/Phi-3.5-mini-instruct",
        "hub": "huggingface",
        "type": "llm"
      }
    ],
    "parallel_downloads": false
  }'
```

**Download an Ollama model:**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=ollama_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "tinyllama",
        "hub": "ollama",
        "type": "llm"
      }
    ],
    "parallel_downloads": false
  }'
```

**Download a YOLO vision model from Ultralytics:**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=yolo_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolov8s",
        "hub": "ultralytics",
        "type": "vision"
      }
    ],
    "parallel_downloads": true
  }'
```

> **Note:** YOLO vision models from Ultralytics model hub will be downloaded and converted to
> the OpenVINO IR format with FP32 and FP16 precision by default.
> **Note:** Ultralytics supports a single model name, comma-separated model names, or `"name": "all"`.

**Download an Ultralytics model with INT8 quantization:**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=yolo_int8" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolov8n",
        "hub": "ultralytics",
        "type": "vision",
        "config": {
          "quantize": "coco128"
        }
      }
    ],
    "parallel_downloads": false
  }'
```

> **Note: INT8 behavior for Ultralytics requests:**
>
> - Set `config.quantize` to request INT8 export.
> - INT8 requests only support a single model name per request. Requests using comma-separated model names, `all`, or `yolo_all` with `quantize` are rejected.
> - If INT8 is requested but no INT8 artifact is produced, the request fails and partial artifacts are cleaned up.
> - Due to a limitation in the DL Streamer public model download script, requesting INT8 also downloads other supported precision artifacts for the model if present like FP32, FP16.
> - Currently available datasets are coco, coco8 and coco128.

**NOTE:** coco is a very large dataset of over 20GB and containing more than a 100,000 images. Quantization on this dataset can take a very long time. For development purposes, it is recommended to use coco128 or coco8 instead, which is much lighter.

**Download a Hugging Face model and convert it to OpenVINO IR format:**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=ovms_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "BAAI/bge-reranker-base",
        "hub": "openvino",
        "type": "rerank",
        "is_ovms": true,
        "config": {
          "precision": "fp32",
          "device": "CPU",
          "cache_size": 10
        }
      }
    ],
    "parallel_downloads": false
  }'
```

**Example: Optimum CLI-aligned nested config**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=ovms_model" \
  -H "Content-Type: application/json" \
  -d '{
  "models": [
    {
      "name": "Alibaba-NLP/gte-large-en-v1.5",
      "hub":"openvino",
      "type": "embeddings",
      "is_ovms": true,
      "config": {
        "precision": "int8",
        "device": "CPU",
        "cache_size": 2,
        "extra_quantization_params":"--library sentence_transformers"
      }
    }
  ],
  "parallel_downloads": false
}'
```

> **Note:**
>
> - Need additional OpenVINO export knobs? Review the parameter matrix in the [OpenVINO Model Server export guide](https://github.com/openvinotoolkit/model_server/blob/main/demos/common/export_models/README.md#quick-start) and pass the corresponding fields through `config`.
> - Visual-language models automatically set `pipeline_type` to `VLM` for type 'VLM'.
> - Unknown parameters keep their original spelling (underscores included) and are forwarded as `--<param_name>`, so options such as `reasoning_parser`, `tool_parser` etc.
> - Boolean flags are emitted only when they evaluate to true. Leave them unset or false to skip the corresponding CLI switch.
> - Hugging Face authentication is still required for OVMS exports; provide `HUGGINGFACEHUB_API_TOKEN` (or pass the token via the API) before invoking these parameters.

**Download models from Geti™ software, which are optimized through OpenVINO toolkit's optimization tool:**

```bash
curl -X POST 'http://<host-ip>:8200/api/v1/models/download?download_path=geti_folder' \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
        {
            "name": "yolox-tiny",
            "hub": "geti",
            "revision": "1",
            "config":{
                "precision": "fp32"
            }
        }
    ],
    "parallel_downloads": true
  }'
```

> **Note:** The default precision is FP16.

**Download a Pipeline Zoo model:**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=pipeline_zoo_models" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "dbnet",
        "hub": "pipeline-zoo-models"
      }
    ],
    "parallel_downloads": false
  }'
```

> **Note:** Pipeline Zoo supports a single model name, comma-separated model names (for example, `"name": "dbnet,yolov5m-320"`), or `"name": "all"` to download all available models from the `storage` directory.

**Download a tarball model at runtime from a remote URL (`remote-url` hub):**

Provide the archive URL in `config.url`. An optional `{name}` placeholder
is replaced with the model's `name` field before download. The URL is validated against an
allowlist (`host + path` prefixes) before fetching — scheme must be `https`.

The allowlist defaults to `allowed_prefixes` in `sources.yaml`. It can optionally be
overridden per deployment with `EXTERNAL_SOURCES_URL_ALLOWLIST` (comma-separated;
when set it **replaces** the YAML list). An empty allowlist rejects all runtime
URLs.

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=udf_timeseries" \
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
    ],
    "parallel_downloads": false
  }'
```

> **Note:** The URL must point to a tar archive (ex: `.tar`, `.tar.gz`) containing a single model's files, and `name` must be a single value (comma-separated names and `all` are not supported for `remote-url`).

> **Note:** Pass hub names (`pipeline-zoo-models`, `remote-url`) directly to `--plugins`. The internal plugin implementation is shared but not user-visible.

**Download an Open Model Zoo (OMZ) model:**

The model is fetched with `omz_downloader`, converted to OpenVINO IR with
`omz_converter`, and any model-specific post-processing (model-proc JSON, label
injection) declared in `omz_rules.yaml` is applied automatically.

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=omz_model" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "mobilenet-v2-pytorch",
        "hub": "omz"
      }
    ],
    "parallel_downloads": false
  }'
```

> **Note:** Models without a matching entry in `omz_rules.yaml` are downloaded and
> converted, but no post-processing is applied.
> **Note:** OMZ supports a single model name or comma-separated model names (for example, `"name": "mobilenet-v2-pytorch,face-detection-retail-0004"`). `"name": "all"` is not supported for OMZ because each model requires both download and conversion, and processing the full catalog can be very time-consuming and resource-intensive.

**Download fixed HLS models (3D pose, rPPG, AI-ECG):**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=hls_assets" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "human-pose-estimation-3d-0001",
        "hub": "hls",
        "type": "3d-pose"
      }
    ],
    "parallel_downloads": false
  }'
```

> **Notes:** Valid HLS types are `3d-pose`, `rppg`, and `ai-ecg`.
  The service downloads model artifacts only; demo videos must be fetched separately if needed.

**Query Parameter:**

- `download_path` (string): Specify a local filesystem path for saving the downloaded model.
  If not provided, the model will be saved to the default location.

**Response:**
**Sample Response (when a download request is started):**

```json
{
  "message": "Started processing 1 model(s)",
  "job_ids": ["5f0d4eba-c79c-4d02-97a6-43c3d0168ca0"],
  "status": "processing"
}
```

Each model-download request returns a `job_id`. To check the status of a download:

```bash
curl -X GET "http://<host-ip>:8200/api/v1/jobs/<job_id>"
```

**Sample Response (when the job is completed):**

```json
{
  "id": "5f0d4eba-c79c-4d02-97a6-43c3d0168ca0",
  "operation_type": "download",
  "model_name": "yolov8s",
  "hub": "ultralytics",
  "output_dir": "/opt/models/ultra_folder",
  "status": "completed",
  "start_time": "2025-10-27T08:24:23.510870",
  "model_type": "vision",
  "completion_time": "2025-10-27T08:30:14.443898",
  "result": {
    "model_name": "yolov8s",
    "source": "ultralytics",
    "download_path": "model/download/path",
    "return_code": 0
  }
}
```

**Download with Override Credentials:**

When using `override_credentials`, the service relies on Base64 encoding to
obfuscate credential values in the request body and on log redaction to prevent
credentials from appearing in service logs. Credentials are request-scoped
(in-memory only) and never persisted. For deployments where the API is exposed
beyond the local device or Docker network, place the service behind a
TLS-terminating reverse proxy to encrypt credentials in transit.

The `override_credentials` field lets you pass per-request credentials without
changing environment variables. All values must be Base64-encoded, regardless of
whether the key is marked as sensitive. The `sensitive` flag only controls
whether the value is redacted in service logs — Base64 encoding is required for
every key. Use `GET /api/v1/plugins` to discover the keys each plugin accepts.

**Encode credentials:**

```bash
echo -n 'my-secret-token' | base64
# Output: bXktc2VjcmV0LXRva2Vu
```

**Download a gated Hugging Face model with per-request token override (`HF_TOKEN`):**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=hf_gated" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "meta-llama/Llama-3.1-8B-Instruct",
        "hub": "huggingface",
        "type": "llm",
        "override_credentials": {
          "HF_TOKEN": "<base64_HF_token>"
        }
      }
    ],
    "parallel_downloads": false
  }'
```

**Download a Geti™ model with per-request credentials override (`GETI_HOST`, `GETI_TOKEN`, `GETI_WORKSPACE_ID`):**

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=geti_override" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "yolox-tiny",
        "hub": "geti",
        "revision": "1",
        "override_credentials": {
          "GETI_HOST": "<base64_GETI_HOST>",
          "GETI_TOKEN": "<base64_GETI_TOKEN>",
          "GETI_WORKSPACE_ID": "<base64_GETI_WORKSPACE_ID>"
        },
        "config": {
          "precision": "fp16"
        }
      }
    ],
    "parallel_downloads": false
  }'
```

> **Note:** When overriding a grouped set of keys (for example the `geti` group), all required keys in that group must be provided together. Use `GET /api/v1/plugins` to see which keys belong to each group.

**Download a remote-url model with per-request allowlist override (`EXTERNAL_SOURCES_URL_ALLOWLIST`):**

```bash
# Base64-encode the full comma-separated allowlist as a single value
echo -n 'github.com/open-edge-platform/edge-ai-resources/raw/main,example.com/models' | base64
# Output: Z2l0aHViLmNvbS9vcGVuLWVkZ2UtcGxhdGZvcm0vZWRnZS1haS1yZXNvdXJjZXMvcmF3L21haW4sZXhhbXBsZS5jb20vbW9kZWxz
```

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/download?download_path=remote_override" \
  -H "Content-Type: application/json" \
  -d '{
    "models": [
      {
        "name": "wind-turbine-anomaly-detection",
        "hub": "remote-url",
        "override_credentials": {
          "EXTERNAL_SOURCES_URL_ALLOWLIST": "<base64_comma_separated_prefixes>"
        },
        "config": {
          "url": "https://github.com/open-edge-platform/edge-ai-resources/raw/main/timeseries-udf-deployment-packages/{name}.tar"
        }
      }
    ],
    "parallel_downloads": false
  }'
```

> **Note:** The response format for downloads with `override_credentials` is the same as shown in the response section above for the corresponding hub plugin.

**Pre-validate credentials before download:**

Add `"validate_credentials": true` to any model in the request to perform a fast credential check before the download or conversion begins. If `override_credentials` is present, those values are validated; otherwise the service's environment credentials are checked. This is especially useful for `is_ovms` conversions where invalid credentials would otherwise surface only after minutes of processing.

```json
{
  "models": [{
    "name": "meta-llama/Llama-3.1-8B",
    "hub": "openvino",
    "is_ovms": true,
    "validate_credentials": true,
    "override_credentials": { "HF_TOKEN": "<base64-token>" }
  }]
}
```

If the credentials are invalid, the request returns `400` immediately without starting the job.


**Cancel a running or queued job:**

Use `POST /api/v1/jobs/<job_id>/cancel` to cancel a job that is still in a cancellable state (`queued`, `downloading`, or `converting`). If the job is already in a terminal state (`completed`, `failed`, or `canceled`), the endpoint returns `409`.

```bash
curl -X POST "http://<host-ip>:8200/api/v1/jobs/<job_id>/cancel"
```

**Sample Response (when the job is cancelled):**

```json
{
  "message": "Job 5f0d4eba-c79c-4d02-97a6-43c3d0168ca0 has been cancelled",
  "job_id": "5f0d4eba-c79c-4d02-97a6-43c3d0168ca0",
  "status": "canceled"
}
```

> **Note:** For hubs that do not support immediate interruption (`huggingface`, `geti`, `openvino`), the response includes an additional `warning` field. The transfer may continue briefly in the background; partial files are cleaned up automatically.

**Upload a custom model ZIP:**

Use this endpoint when user (or another client app) needs to upload a local model directly to model-download.
The ZIP must contain at least one `.xml` and one `.bin` file.

**Naming rules:**

- `model_name` allows letters, numbers, periods, underscores, hyphens, and spaces. Spaces are converted to underscores. Names must not start or end with a period or contain consecutive periods (`..`).
- `provider`, `framework`, and `precision` allow only letters, numbers, underscores, and hyphens, and must start with a letter or digit.

```bash
curl -X POST "http://<host-ip>:8200/api/v1/models/upload" \
  -F "file=@/path/to/my_model.zip" \
  -F "model_name=my_custom_model" \
  -F "provider=geti" \
  -F "framework=openvino" \
  -F "precision=FP16"
```

Upload storage path format:

```text
/opt/models/custom_uploaded_models/{provider}/{framework}/{model_name}/[{precision}/]
```

On successful upload, the model is registered as a completed operation and is visible in:

```bash
curl -X GET "http://<host-ip>:8200/api/v1/models/results"
```

**Sample Response (when the upload is completed):**

```json
{
  "status": "success",
  "message": "Model 'my_custom_model' uploaded successfully.",
  "job_id": "a1b2c3d4-1234-5678-9abc-def012345678",
  "model_name": "my_custom_model",
  "model_path": "/opt/models/custom_uploaded_models/geti/openvino/my_custom_model/FP16"
}
```

- For details, see the [API reference](./api-reference.md).

## Configuration

You can configure the service through environment variables and Docker volumes:

Environment Variables:

- `HF_HUB_ENABLE_HF_TRANSFER`: Enable Hugging Face transfer (default: 1)
- `HUGGINGFACEHUB_API_TOKEN`: Hugging Face token (only required for gated models or conversion)
- `MAX_UPLOAD_SIZE_MB`: Maximum allowed upload ZIP size in MB (default: 500)
- `UPLOAD_CHUNK_SIZE_KB`: Chunk size for streaming file uploads in KB (default: 8). Larger values improve throughput, smaller values reduce memory usage for concurrent uploads

Volumes:

- `~/models:/app/models`: Persist downloaded models

## Troubleshooting

- If you encounter any issues during the build or run process, check the Docker logs for errors:

  ```bash
  docker logs <container-id>
  ```

## Run Unit Tests

To validate changes locally before deploying:

1. **Set up virtual environment**:

   ```bash
   pip install uv
   uv venv
   source .venv/bin/activate
   ```

2. **Install all optional dependencies**:

   ```bash
   uv sync --all-extras
   ```

3. **Execute unit tests**:

   ```bash
   uv run pytest tests/unit -v
   ```

Use `pytest tests/ --cov=src --cov-report=term` if you also need coverage metrics. See
[docs/user-guide/running-tests.md](./running-tests.md) for advanced filtering options and troubleshooting tips.

## Model Storage Path Layout

When a download completes, the `result.download_path` field in the job response contains the absolute host-mapped path to the model directory. The path is deterministic — downloading the same model with the same parameters always produces the same path.

All hubs follow a common base pattern:

```text
<download_path>/<hub>/<model_name>/[<hub_specific_folder>/]
```

Where `<download_path>` is the `download_path` query parameter passed to `POST /api/v1/models/download`, resolved relative to the configured model storage root.

Hubs that support multiple precisions append a `<precision>/` subdirectory. Hubs that do not support precision store files directly under `<model_name>/`:

| Hub | Path layout | Example |
|-----|------------|---------|
| `huggingface` | `<download_path>/<hub>/<model_name>` | `models/huggingface/microsoft_Phi-3.5-mini-instruct` |
| `ollama` | `<download_path>/<hub>/<model_name>` | `models/ollama/tinyllama` |
| `ultralytics` | `<download_path>/<hub>/<model_name>/<precision>/` | `models/ultralytics/yolov8s/FP16/` |
| `openvino` | `<download_path>/<hub>/<model_name>/<precision>/` | `models/openvino/BAAI-bge-reranker-base/fp32/` |
| `geti` | `<download_path>/<hub>/<model_name>/<precision>/` | `models/geti/yolox-tiny/FP32/` |
| `pipeline-zoo-models` | `<download_path>/<hub>/<model_name>/` | `models/pipeline-zoo-models/dbnet/` |
| `omz` | `<download_path>/<hub>/<model_name>/` | `models/omz/mobilenet-v2-pytorch/` |
| `remote-url` | `<download_path>/<hub>/<model_name>/` | `models/remote-url/wind-turbine-anomaly-detection/` |
| `hls` | `<download_path>/<hub>/<model_name>/` | `models/hls/human-pose-estimation-3d-0001/` |

> **Note:** For model names containing `/` (for example, `microsoft/Phi-3.5-mini-instruct`), the slash is replaced with `_` in the directory name.

## Best Practices

1. Use parallel downloads with caution because they can consume significant resources.
2. Configure cache sizes based on available memory.
3. Select model precision according to your performance requirements.
4. Use appropriate model types and configurations for OpenVINO model server conversion.
5. For Ultralytics INT8 exports, submit one model per request and verify `config.quantize` is provided only when INT8 is intended.

## Run in Kubernetes Cluster

See [Deploy with Helm Chart](./get-started/deploy-with-helm-chart.md) for details. Address the prerequisites mentioned on this page before deploying with Helm chart.

## Learn More

For alternative ways to set up the sample application, see:

- [Download Models at Startup](./get-started/startup-models.md)
- [Quick start](./get-started/quickstart.md)
- [How to Build from Source](./get-started/build-from-source.md)

<!--hide_directive
:::{toctree}
:hidden:

Migrate from Model Registry <./get-started/migration.md>
./get-started/system-requirements
Startup<./get-started/startup-models.md>
Ephemeral Container <./get-started/quickstart.md>
./get-started/build-from-source
./get-started/deploy-with-helm-chart

:::
hide_directive-->
