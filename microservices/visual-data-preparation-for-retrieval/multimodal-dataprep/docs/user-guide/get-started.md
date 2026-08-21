# Get Started

The **Multimodal DataPrep microservice** builds and stores frame-level, image, and text embeddings in the configured vector database — VDMS by default, or Milvus — while preserving the raw assets in the configured object storage — MinIO by default, or the local filesystem. This guide explains how to launch the service, configure runtime options, and exercise the primary APIs. Backend selection is covered in [Pluggable Backends](./pluggable-backends.md); this walkthrough uses the default VDMS + MinIO stack.

## Configuration and Setup

Multimodal DataPrep ships with Docker Compose manifests (`docker/compose*.yaml`) for different backends — for example `docker/compose.yaml` provisions the default MinIO + VDMS Vector DB + DataPrep stack, while `docker/compose-milvus.yaml` runs against Milvus. Always `source` the accompanying `setup.sh` script so the exported environment variables remain in your shell.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./get-started/system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Environment Variables

The table below lists the core configuration knobs. `setup.sh` seeds defaults, but you can override them before sourcing the script. The defaults below assume the **VDMS + MinIO** backends; to run against **Milvus** or **local filesystem** storage, set the backend selectors below and see [Pluggable Backends](./pluggable-backends.md) for the full backend-specific reference.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `MM_DATAPREP_VECTORDB_BACKEND` | Optional | `vdms` | Active vector-database backend: `vdms` or `milvus`. |
| `MM_DATAPREP_STORAGE_BACKEND` | Optional | `minio` | Active object-storage backend: `minio` or `local`. |
| `MM_DATAPREP_MILVUS_URI` | Optional | _(none)_ | Full Milvus URI (e.g. `http://milvus:19530`). Overrides `MILVUS_HOST`/`MILVUS_PORT`. Used only when `VECTORDB_BACKEND=milvus`. |
| `MM_DATAPREP_MILVUS_HOST` / `MM_DATAPREP_MILVUS_PORT` | Optional | _(none)_ / `19530` | Milvus host and port when `MILVUS_URI` is not set. Used only when `VECTORDB_BACKEND=milvus`. |
| `MM_DATAPREP_VDB_METRIC_TYPE` | Optional | `IP` | Vector similarity metric applied to both VDMS and Milvus (e.g. `IP`, `L2`). |
| `MM_DATAPREP_VDB_INDEX_TYPE` | Optional | `FLAT` | Vector index type for backends that require it (e.g. Milvus `FLAT`). |
| `MM_DATAPREP_LOCAL_STORAGE_PATH` | Optional | `/tmp/dataprep/storage` | Root directory for the `local` storage backend; each bucket maps to a subdirectory. Used only when `STORAGE_BACKEND=local`. |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | ✅ | _(none)_ | Credentials used to bootstrap MinIO. Required only when `STORAGE_BACKEND=minio`. |
| `MM_DATAPREP_MINIO_ENDPOINT` | ✅ | `minio-server:9000` | Host:port string DataPrep uses to communicate with MinIO from inside the container. Required only when `STORAGE_BACKEND=minio`. |
| `MM_DATAPREP_DEFAULT_BUCKET_NAME` | ✅ | `video-summary` (via `setup.sh`) | Destination bucket for uploaded media and generated manifests. Override with `MM_DATAPREP_PM_MINIO_BUCKET` when running alongside pipeline-manager. |
| `MM_DATAPREP_VDMS_VDB_HOST` / `MM_DATAPREP_VDMS_VDB_PORT` | ✅ | `vdms-vector-db` / `55555` | Connection information for VDMS Vector DB. Used only when `VECTORDB_BACKEND=vdms`. |
| `MM_DATAPREP_DB_COLLECTION` | ✅ | `video-rag-test` | Vector-database collection/index that stores embeddings and metadata (applies to both VDMS and Milvus). |
| `MM_DATAPREP_EMBEDDING_MODEL_NAME` | ✅ | _(none)_ | Model identifier used by the in-process embedding pipeline (for example `CLIP/clip-vit-b-32` for multimodal or `QwenText/qwen3-embedding-0.6b` for text-only embeddings). |
| `MM_DATAPREP_USE_OPENVINO` | Optional | `true` | Enables OpenVINO acceleration for embedding generation. Set `false` to stay on PyTorch. |
| `MM_DATAPREP_EMBEDDING_DEVICE` | Optional | `CPU` | Device for the in-process embedding pipeline (`CPU`, `GPU`, or `NPU`). |
| `MM_DATAPREP_DETECTION_DEVICE` | Optional | `CPU` | Device override for object detection execution (`CPU`, `GPU`, or `NPU`). |
| `MM_DATAPREP_EMBEDDING_BATCH_SIZE` | Optional | `32` | Number of items sent per embedding batch. |
| `MM_DATAPREP_MAX_PARALLEL_WORKERS` | Optional | _(auto)_ | Hard cap for parallel workers when auto-scaling is too aggressive for the host. |
| `MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS` | Optional | `true` | When `false`, an upload whose byte content is identical to an already-ingested video is rejected with `409 Conflict`. Detection is content-based (SHA-256) and applies to `/media/upload`, `/media/upload/batch`, `/media/ingest-dir`, `/media/process`, and `/media/process/batch` (per item, reported in the job status). |
| `MM_DATAPREP_FRAME_INTERVAL` | Optional | `15` | Extract every Nth frame during video processing. |
| `MM_DATAPREP_ENABLE_OBJECT_DETECTION` | Optional | `true` | Toggles YOLOX-based crop extraction. |
| `MM_DATAPREP_DETECTION_CONFIDENCE` | Optional | `0.85` | Minimum confidence threshold for detections. |
| `MM_DATAPREP_ROI_CONSOLIDATION_ENABLED` | Optional | `false` | Enables ROI consolidation (merging overlapping detections). |
| `MM_DATAPREP_ROI_CONSOLIDATION_IOU_THRESHOLD` | Optional | `0.2` | IoU threshold used to group overlapping boxes into a single ROI. |
| `MM_DATAPREP_ROI_CONSOLIDATION_CLASS_AWARE` | Optional | `false` | Merge only boxes of the same class when `true`. |
| `MM_DATAPREP_ROI_CONSOLIDATION_CONTEXT_SCALE` | Optional | `0.2` | Expands merged ROIs by this fraction of their width/height. |
| `MM_DATAPREP_VIDEO_SHM_MAX_BLOCKS` | Optional | `512` | Shared memory block count for the video decode and embedding pipeline. |
| `MM_DATAPREP_VIDEO_SHM_BLOCK_SIZE` | Optional | `6220800` | Per-block shared memory size in bytes (default sized for 1080p RGB frames). |
| `MM_DATAPREP_VIDEO_EXTRACTION_BATCH_SIZE` | Optional | `256` | Decoder-side batch size used when extracting frames for processing. |
| `MM_DATAPREP_PIPELINE_QUEUE_MAXSIZE` | Optional | `16` | Queue capacity for inter-stage pipeline buffers. |
| `MM_DATAPREP_PIPELINE_COMPLETION_QUEUE_MAXSIZE` | Optional | `1` | Queue capacity for completion/result handoff stage. |
| `MM_DATAPREP_DETECTION_WORKER_THREADS` | Optional | `2` | Local thread count used by object-detection worker stage. |
| `MM_DATAPREP_EMBED_WORKER_THREADS` | Optional | `2` | Local thread count used by embedding worker stage. |
| `MM_DATAPREP_PIPELINE_QUEUE_GET_TIMEOUT_S` | Optional | `1.0` | Timeout in seconds for pipeline queue reads before retry loops. |
| `MM_DATAPREP_SAVE_RUNTIME_PIPELINE_STATS` | Optional | `false` | Persist batch/stream runtime stats JSON artifacts for debugging and profiling. |
| `MM_DATAPREP_ENABLE_TRACING` | Optional | `false` | Enables trace emission for decode/detect/embed/store stages. |
| `MM_DATAPREP_VIDEO_FRAME_DECODER_WORKERS` | Optional | `2` | Number of decoder workers used in frame extraction utilities. |
| `MM_DATAPREP_VIDEO_FRAME_LOG_LEVEL` | Optional | `INFO` | Log level for decoder internals (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `MM_DATAPREP_OV_MODELS_DIR` | Optional | `/app/ov_models` | Persistent mount that caches OpenVINO-optimized models. |
| `MM_DATAPREP_METRICS_MANAGER_URL` | Optional | _(empty / disabled)_ | Metrics Manager base URL. When set, each completed video pipeline publishes `dataprep_embeddings_per_second` to `/api/v1/metrics/simple`. |
| `MM_DATAPREP_METRICS_MANAGER_TIMEOUT_SECONDS` | Optional | `2.0` | Timeout for one Metrics Manager publish attempt. Publishing is asynchronous and never delays ingestion. |
| `MM_DATAPREP_ALLOW_ORIGINS`, `MM_DATAPREP_ALLOW_METHODS`, `MM_DATAPREP_ALLOW_HEADERS` | Optional | `*` | CORS configuration applied by FastAPI. |

### Device selection (`MM_DATAPREP_EMBEDDING_DEVICE`, `MM_DATAPREP_DETECTION_DEVICE`)

DataPrep configures its two compute stages independently — there is no baseline
device. Each variable defaults to `CPU` when unset:

- `MM_DATAPREP_EMBEDDING_DEVICE` — device for the in-process embedding pipeline.
- `MM_DATAPREP_DETECTION_DEVICE` — device for object detection.

> **Important:** These variables are read directly by the DataPrep container. You
> can `source` a setup script (which exports the `CPU` defaults) or set them
> explicitly before running `docker compose up`.

Examples (run before sourcing the setup script):

```bash
# Offload detection to NPU and embedding to GPU (independent per-component devices)
export MM_DATAPREP_DETECTION_DEVICE=NPU
export MM_DATAPREP_EMBEDDING_DEVICE=GPU

# Run both stages on GPU
export MM_DATAPREP_EMBEDDING_DEVICE=GPU
export MM_DATAPREP_DETECTION_DEVICE=GPU

# Embedding on GPU, but keep detection on CPU
export MM_DATAPREP_EMBEDDING_DEVICE=GPU
export MM_DATAPREP_DETECTION_DEVICE=CPU
```

When targeting `NPU`, confirm the selected model supports NPU inference via the
[OpenVINO Supported Models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html) page.

> **Running everything on NPU:** Setting both embedding and detection to `NPU`
> (via `MM_DATAPREP_EMBEDDING_DEVICE=NPU` and `MM_DATAPREP_DETECTION_DEVICE=NPU`) is
> functionally supported — both stages run on NPU through OpenVINO. However, the
> host has a single NPU, so the embedding and detection stages contend for the
> same accelerator. It works, but it is not optimal for throughput. For best
> performance, split the load across accelerators (for example, keep embedding on
> `NPU` and detection on `GPU`/`CPU`, or vice versa).

### Advanced tuning

Additional environment variables are available for high-throughput scenarios:

- `MM_DATAPREP_ENABLE_PARALLEL_PIPELINE` (default `true`) — disable to force single-threaded embedding.
- `MM_DATAPREP_MAX_PARALLEL_WORKERS` — hard cap on worker threads (auto-calculated when unset).
- `MM_DATAPREP_OV_PERFORMANCE_MODE`, `OV_PERFORMANCE_HINT_NUM_REQUESTS`, `OV_NUM_STREAMS` — forward performance hints to OpenVINO when running on CPU or GPU.
- `MM_DATAPREP_VIDEO_SHM_MAX_BLOCKS`, `MM_DATAPREP_VIDEO_SHM_BLOCK_SIZE` — tune shared-memory capacity for frame transport.
- `MM_DATAPREP_VIDEO_EXTRACTION_BATCH_SIZE`, `MM_DATAPREP_PIPELINE_QUEUE_MAXSIZE`, `MM_DATAPREP_PIPELINE_QUEUE_GET_TIMEOUT_S` — tune decode and queue backpressure behavior.
- `MM_DATAPREP_DETECTION_WORKER_THREADS`, `MM_DATAPREP_EMBED_WORKER_THREADS` — tune stage-local worker counts.
- `MM_DATAPREP_SAVE_RUNTIME_PIPELINE_STATS`, `MM_DATAPREP_ENABLE_TRACING`, `MM_DATAPREP_VIDEO_FRAME_LOG_LEVEL` — enable diagnostics and control verbosity.

Export overrides before sourcing the setup script:

```bash
export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-16"
export MINIO_ROOT_USER="minioadmin"
export MINIO_ROOT_PASSWORD="minioadmin"
export MM_DATAPREP_EMBEDDING_DEVICE="CPU"
export MM_DATAPREP_DETECTION_DEVICE="CPU"
source ./setup.sh --nosetup
```

> **Tip:** When you only need long-form text embeddings—such as the combined `--all` mode in the video search and summarization sample—set `EMBEDDING_MODEL_NAME="QwenText/qwen3-embedding-0.6b"` before sourcing `setup.sh`. The script forwards this value to the DataPrep container as `MM_DATAPREP_EMBEDDING_MODEL_NAME`, enabling Qwen-backed text embeddings without any additional flags.

## ROI consolidation (optional)

ROI consolidation merges overlapping detections into a single crop and optionally expands that crop for more context. This can reduce duplicate crops and improve embedding coverage when multiple detections overlap the same object.

Enable it via environment variable (recommended for quick toggles):

```bash
export MM_DATAPREP_ROI_CONSOLIDATION_ENABLED=true
```

Or configure it in `src/config.yaml` under `object_detection.roi_consolidation`:

- `enabled`: Master switch for ROI consolidation logic.
- `iou_threshold`: IoU threshold used to cluster overlapping boxes. IoU is $\frac{\text{intersection area}}{\text{union area}}$ for two boxes; higher values mean only tighter overlaps merge, lower values merge more aggressively.
- `class_aware`: When `true`, only boxes of the same class can be merged. When `false`, overlapping boxes across classes can merge (useful for mixed-class clusters).
- `context_scale`: Expand merged ROI by this fraction of its size. Higher values include more surrounding context; lower values keep crops tighter to the merged box.

Use `source ./setup.sh --conf` to print the resolved Docker Compose configuration with your overrides applied.

## Quick Start with Docker

> **Important:** Do not run `docker build` directly against `docker/Dockerfile` from the `multimodal-dataprep` directory. Always execute `./build.sh` so the build uses the `microservices/` context and includes the local `multimodal-embedding-serving` source dependency.

The user has an option to either [build the docker images](./get-started/build-from-source.md#steps-to-build) or use prebuilt images as documented below.

**Configure the registry**:
The Multimodal DataPrep microservice uses the registry URL and tag to pull the required image.

```bash
export REGISTRY_URL=intel
export TAG=latest
```

1. **Clone the repository and enter the project.**

   ```bash
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git -b main
   cd edge-ai-libraries/microservices/visual-data-preparation-for-retrieval/multimodal-dataprep
   ```

2. **Export required secrets and model selection.**

   ```bash
   export MINIO_ROOT_USER="minioadmin"
   export MINIO_ROOT_PASSWORD="minioadmin"
   export EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32"
   ```

   For text-only scenarios replace the last line with:

   ```bash
   export EMBEDDING_MODEL_NAME="QwenText/qwen3-embedding-0.6b"
   ```

3. **Start the stack.**

   Run `source ./setup.sh` to export the environment variables, then start the default stack (MinIO, VDMS, and DataPrep) with `docker compose -f docker/compose.yaml up -d --build`. To run against Milvus instead, use `docker compose -f docker/compose-milvus.yaml up -d --build`.

4. **Confirm the stack is healthy.**

   ```bash
   docker ps --format "table {{.Names}}\t{{.Status}}"
   ```

5. **Open the interactive docs.** Navigate to `http://localhost:6007/docs` (adjust if you changed `MM_DATAPREP_HOST_PORT`) to view the OpenAPI schema.

6. **Shut everything down when finished.** Use `source ./setup.sh --down` (or `docker compose -f docker/compose.yaml down`) to stop services.

## Usage

The FastAPI application is mounted under `/v1/dataprep`.

### Health probe

```bash
curl http://localhost:6007/v1/dataprep/health
```

Health responses include the embedding client preload status, model name, and device.

### Upload and process a new video

```bash
curl -X POST "http://localhost:6007/v1/dataprep/media/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/video.mp4" \
  -F "frame_interval=10" \
  -F "enable_object_detection=true" \
  -F "tags=intersection" -F "tags=night"
```

The service streams the asset to the configured object storage, extracts frames (and crops), generates embeddings, and persists metadata in the configured vector database.

### Upload and process an image

The same endpoint accepts images (`.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`,
`.gif`). Images are embedded directly (full image plus optional detected-object
crops) into the same vector collection as video frames, enabling cross-modal
search.

```bash
# Multipart file upload
curl -X POST "http://localhost:6007/v1/dataprep/media/upload?enable_object_detection=true" \
  -F "file=@/path/to/image.jpg" -F "tags=cat"

# Inline base64 (data URL accepted) via the JSON typed-source endpoint
curl -X POST "http://localhost:6007/v1/dataprep/media/ingest" \
  -H "Content-Type: application/json" \
  -d '{"type": "image_base64", "image_base64": "data:image/png;base64,iVBORw0KGgo..."}'

# Remote URL (server downloads, size-capped at 50 MB)
curl -X POST "http://localhost:6007/v1/dataprep/media/ingest" \
  -H "Content-Type: application/json" \
  -d '{"type": "image_url", "image_url": "https://example.com/cat.jpg"}'
```

### Process an existing video in MinIO

```bash
curl -X POST "http://localhost:6007/v1/dataprep/media/process" \
  -H "Content-Type: application/json" \
  -d '{
        "bucket_name": "video-summary",
        "video_id": "traffic_cam_2024_10_21",
        "frame_interval": 12,
        "enable_object_detection": true,
        "tags": ["traffic", "daytime"]
      }'
```

### Attach a human-authored summary

To attach a human-authored summary to a video, use this command:

```bash
curl -X POST "http://localhost:6007/v1/dataprep/summary" \
  -H "Content-Type: application/json" \
  -d '{
        "bucket_name": "video-summary",
        "video_id": "traffic_cam_2024_10_21",
        "video_summary": "Vehicle stopped at intersection for 45 seconds",
        "video_start_time": 12.5,
        "video_end_time": 57.0,
        "tags": ["summary", "manual"]
      }'
```

### Discover, download, and delete content

You can use the following commands to discover, download, and delete content:

```bash
# List processed videos (video_id + filenames)
curl "http://localhost:6007/v1/dataprep/media"

# Download a processed clip (stream or attachment)
curl -L "http://localhost:6007/v1/dataprep/media/download?video_id=traffic_cam_2024_10_21" -o clip.mp4

# Delete a video (removes its storage object(s) + vector embeddings)
curl -X DELETE "http://localhost:6007/v1/dataprep/media/my-bucket/traffic_cam_2024_10_21"
```

### Review processing telemetry

The telemetry endpoint captures per-request wall-clock timings, stage durations, throughput, and batch-level stats. Query the most recent entries directly from the DataPrep service (or via the pipeline-manager proxy) with:

```bash
curl --location 'http://localhost:6016/telemetry?limit=5'
```

See the [Telemetry Metrics](telemetry-metrics.md) reference for a complete breakdown of every field and how each value is calculated.

## Validate Services

1. Call `GET /v1/dataprep/health` – expect `status: ok`, the embedding client status, model name, device, and OpenVINO flag.
2. Upload a small MP4 via `/media/upload` and confirm:
   - The response payload reports `success`.
   - `GET /v1/dataprep/media` lists the generated `video_id` and manifests.
   - The MinIO console (`http://localhost:6011`) shows the raw asset, thumbnails, and crops.
3. Inspect the vector database to verify entries in the `video-rag-test` collection (for the default VDMS backend, use `vdms_cli` or a custom client; for Milvus, use a Milvus client such as `pymilvus` or Attu).

## Troubleshooting

- **Startup fails with “model name must be provided”:** Set `EMBEDDING_MODEL_NAME` before sourcing `setup.sh` or set `MM_DATAPREP_EMBEDDING_MODEL_NAME` in the container environment before launching Docker.
- **Object detection disabled unexpectedly:** Check logs for YOLOX download failures. Ensure the `YOLOX_MODELS_VOLUME_NAME` volume exists and the host has outbound network access during first run.
- **Uploads rejected:** Files larger than 500 MB are not accepted by the FastAPI upload endpoint. Stage the video directly in MinIO and use `/media/process` instead.
- **GPU acceleration inactive:** Confirm `/dev/dri/*` is mapped into the container, set the relevant device variable (`MM_DATAPREP_EMBEDDING_DEVICE` or `MM_DATAPREP_DETECTION_DEVICE`) to `GPU`, and keep `MM_DATAPREP_USE_OPENVINO=true`.
- **NPU acceleration inactive:** Confirm `/dev/accel/accel0` is available on the host and mapped into the container, set the relevant device variable (`MM_DATAPREP_EMBEDDING_DEVICE` or `MM_DATAPREP_DETECTION_DEVICE`) to `NPU`, and keep `MM_DATAPREP_USE_OPENVINO=true`. Verify the selected model supports NPU inference via the [OpenVINO Supported Models](https://docs.openvino.ai/2026/documentation/compatibility-and-support/supported-models.html) page.
- **First NPU run is slow (one-time model compilation):** The first time a model runs on NPU, OpenVINO compiles it to an NPU-specific blob, which takes noticeably longer than CPU/GPU startup. This is expected and happens once per model/configuration. The compiled blob is cached on the `MM_DATAPREP_OV_MODELS_DIR` mount (default `/app/ov_models`), so subsequent runs reuse it and start quickly — persist this volume to retain the cache across container restarts.

## Supporting Resources

- [Overview](index.md)
- [System Requirements](./get-started/system-requirements.md)
- [Architecture Overview](./how-it-works-architecture.md)
- [Media Ingestion Flow](./how-it-works-ingestion-flow.md) - Detailed flow diagrams of the video and image processing pipelines
- [API Reference](./api-reference.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started/system-requirements.md
./get-started/build-from-source.md

:::
hide_directive-->
