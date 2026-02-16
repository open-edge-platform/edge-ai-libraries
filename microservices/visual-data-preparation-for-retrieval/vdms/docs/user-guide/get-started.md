# Get Started

The **VDMS DataPrep microservice** builds and stores frame-level and text embeddings in VDMS while preserving the raw assets in MinIO. This guide explains how to launch the service, configure runtime options, and exercise the primary APIs.

## Configuration and Setup

VDMS DataPrep ships with Docker Compose manifests (`docker/compose*.yaml`) that provision MinIO, VDMS Vector DB, and the DataPrep container. Always `source` the accompanying setup scripts so the exported environment variables remain in your shell.

## Prerequisites

Before you begin, ensure the following:

- **System Requirements**: Verify that your system meets the [minimum requirements](./system-requirements.md).
- **Docker Installed**: Install Docker. For installation instructions, see [Get Docker](https://docs.docker.com/get-docker/).

This guide assumes basic familiarity with Docker commands and terminal usage. If you are new to Docker, see [Docker Documentation](https://docs.docker.com/) for an introduction.

## Environment Variables

The table below lists the core configuration knobs. `setup.sh` seeds defaults, but you can override them before sourcing the script.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | ✅ | _(none)_ | Credentials used to bootstrap MinIO and authenticate API calls from DataPrep. |
| `MINIO_ENDPOINT` | ✅ | `minio-server:9000` | Host:port string DataPrep uses to communicate with MinIO from inside the container. |
| `DEFAULT_BUCKET_NAME` | ✅ | `vdms-bucket` (via `setup.sh`) | Destination bucket for uploaded videos and generated manifests. Override with `PM_MINIO_BUCKET` when running alongside pipeline-manager. |
| `VDMS_VDB_HOST` / `VDMS_VDB_PORT` | ✅ | `vdms-vector-db` / `55555` | Connection information for VDMS Vector DB. |
| `DB_COLLECTION` | ✅ | `video-rag` | VDMS collection that stores embeddings and metadata. |
| `MULTIMODAL_EMBEDDING_MODEL_NAME` | ✅ | _(none)_ | Model identifier used by both SDK and API execution paths (for example `CLIP/clip-vit-b-32` for multimodal or `QwenText/qwen3-embedding-0.6b` for text-only embeddings). |
| `EMBEDDING_PROCESSING_MODE` | ✅ | `sdk` | Selects optimized in-process execution (`sdk`) or HTTP-based execution (`api`). |
| `SDK_USE_OPENVINO` | Optional | `true` | Enables OpenVINO acceleration in SDK mode. Set `false` to stay on PyTorch. |
| `VDMS_DATAPREP_DEVICE` | Optional | `CPU` | Processing device for embeddings, and object detection (`CPU` or `GPU`). |
| `FRAME_INTERVAL` | Optional | `15` | Extract every Nth frame during video processing. |
| `ENABLE_OBJECT_DETECTION` | Optional | `true` | Toggles YOLOX-based crop extraction. |
| `DETECTION_CONFIDENCE` | Optional | `0.85` | Minimum confidence threshold for detections. |
| `ROI_CONSOLIDATION_ENABLED` | Optional | `false` | Enables ROI consolidation (merging overlapping detections). |
| `ROI_CONSOLIDATION_IOU_THRESHOLD` | Optional | `0.2` | IoU threshold used to group overlapping boxes into a single ROI. |
| `ROI_CONSOLIDATION_CLASS_AWARE` | Optional | `false` | Merge only boxes of the same class when `true`. |
| `ROI_CONSOLIDATION_CONTEXT_SCALE` | Optional | `0.2` | Expands merged ROIs by this fraction of their width/height. |
| `OV_MODELS_DIR` | Optional | `/app/ov_models` | Persistent mount that caches OpenVINO-optimized models. |
| `ALLOW_ORIGINS`, `ALLOW_METHODS`, `ALLOW_HEADERS` | Optional | `*` | CORS configuration applied by FastAPI. |

### Advanced tuning

Additional environment variables are available for high-throughput scenarios:

- `ENABLE_PARALLEL_PIPELINE` (default `true`) — disable to force single-threaded embedding.
- `MAX_PARALLEL_WORKERS` — hard cap on SDK worker threads (auto-calculated when unset).
- `OV_PERFORMANCE_MODE`, `OV_PERFORMANCE_HINT_NUM_REQUESTS`, `OV_NUM_STREAMS` — forward performance hints to OpenVINO when running on CPU or GPU.

Export overrides before sourcing the setup script:

```bash
export MULTIMODAL_EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-16"
export MINIO_ROOT_USER="minioadmin"
export MINIO_ROOT_PASSWORD="minioadmin"
export EMBEDDING_PROCESSING_MODE="sdk"
source ./setup.sh --nosetup
```

> **Tip:** When you only need long-form text embeddings—such as the combined `--all` mode in the video search and summarization sample—set `EMBEDDING_MODEL_NAME="QwenText/qwen3-embedding-0.6b"` before sourcing `setup.sh`. The script forwards this value to the DataPrep container as `MULTIMODAL_EMBEDDING_MODEL_NAME`, enabling Qwen-backed text embeddings in SDK and API modes without any additional flags.

## ROI consolidation (optional)

ROI consolidation merges overlapping detections into a single crop and optionally expands that crop for more context. This can reduce duplicate crops and improve embedding coverage when multiple detections overlap the same object.

Enable it via environment variable (recommended for quick toggles):

```bash
export ROI_CONSOLIDATION_ENABLED=true
```

Or configure it in `src/config.yaml` under `object_detection.roi_consolidation`:

- `enabled`: Master switch for ROI consolidation logic.
- `iou_threshold`: IoU threshold used to cluster overlapping boxes. IoU is $\frac{\text{intersection area}}{\text{union area}}$ for two boxes; higher values mean only tighter overlaps merge, lower values merge more aggressively.
- `class_aware`: When `true`, only boxes of the same class can be merged. When `false`, overlapping boxes across classes can merge (useful for mixed-class clusters).
- `context_scale`: Expand merged ROI by this fraction of its size. Higher values include more surrounding context; lower values keep crops tighter to the merged box.

Use `source ./setup.sh --conf` to print the resolved Docker Compose configuration with your overrides applied.

## Supporting Resources

- [Overview](Overview.md)
- [Architecture Overview](./overview-architecture.md)
- [Video Ingestion Flow](./video-ingestion-flow.md) - Detailed flow diagrams of the video processing pipeline
- [API Reference](api-reference.md)
- [System Requirements](system-requirements.md)

## Quick Start with Docker

> **Important:** Do not run `docker build` directly against `docker/Dockerfile`. The build depends on a wheel generated from the multimodal embedding serving microservice. Always execute `./build.sh` in the `vdms` directory first so the wheel is created under `wheels/` before building the container image.

The user has an option to either [build the docker images](./how-to-build-from-source.md#steps-to-build) or use prebuilt images as documented below.

**Configure the registry**:
   The VDMS DataPrep microservice uses the registry URL and tag to pull the required image.

    ```bash
    export REGISTRY_URL=intel
    export TAG=latest
    ```

1. **Clone the repository and enter the project.**

   ```bash
   git clone https://github.com/open-edge-platform/edge-ai-libraries.git
   cd edge-ai-libraries/microservices/visual-data-preparation-for-retrieval/vdms
   ```

2. **Export required secrets and model selection.**

   ```bash
   export MINIO_ROOT_USER="minioadmin"
   export MINIO_ROOT_PASSWORD="minioadmin"
   export MULTIMODAL_EMBEDDING_MODEL_NAME="CLIP/clip-vit-b-32"
   ```

   For text-only scenarios replace the last line with:

   ```bash
   export MULTIMODAL_EMBEDDING_MODEL_NAME="QwenText/qwen3-embedding-0.6b"
   ```

3. **Choose your execution mode.**

   - **SDK mode (default):** No external embedding service required. Run `source ./setup.sh` to spin up MinIO, VDMS, and DataPrep using `docker/compose.yaml`.
   - **API mode:** Requires the multimodal embedding serving container. Set `export EMBEDDING_PROCESSING_MODE=api`, `source ./setup-with-embedding.sh`, then launch with `docker compose -f docker/compose-with-embedding.yaml up -d --build`.

4. **Confirm the stack is healthy.**

   ```bash
   docker ps --filter "name=vdms" --format "table {{.Names}}\t{{.Status}}"
   ```

5. **Open the interactive docs.** Navigate to `http://localhost:6007/docs` (adjust if you changed `VDMS_DATAPREP_HOST_PORT`) to view the OpenAPI schema.

6. **Shut everything down when finished.** Use `source ./setup.sh --down` (or `docker compose ... down` for the API stack) to stop services.

## Usage

The FastAPI application is mounted under `/v1/dataprep`.

### Health probe

```bash
curl http://localhost:6007/v1/dataprep/health
```

SDK mode responses include the preload status, model name, and device.

### Upload and process a new video

```bash
curl -X POST "http://localhost:6007/v1/dataprep/videos/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@/path/to/video.mp4" \
  -F "frame_interval=10" \
  -F "enable_object_detection=true" \
  -F "tags=intersection" -F "tags=night"
```

The service streams the asset to MinIO, extracts frames (and crops), generates embeddings, and persists metadata in VDMS. The JSON response reports the processing mode that was used.

### Process an existing video in MinIO

```bash
curl -X POST "http://localhost:6007/v1/dataprep/videos/minio" \
  -H "Content-Type: application/json" \
  -d '{
        "bucket_name": "vdms-bucket",
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
        "bucket_name": "vdms-bucket",
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
curl "http://localhost:6007/v1/dataprep/videos"

# Download a processed clip (stream or attachment)
curl -L "http://localhost:6007/v1/dataprep/videos/download?video_id=traffic_cam_2024_10_21&video_name=clip_0003.mp4" -o clip_0003.mp4

# Delete everything under a video_id (omit video_name to remove one file)
curl -X DELETE "http://localhost:6007/v1/dataprep/videos?video_id=traffic_cam_2024_10_21"
```

### Review processing telemetry

The telemetry endpoint captures per-request wall-clock timings, stage durations, throughput, and batch-level stats. Query the most recent entries directly from the DataPrep service (or via the pipeline-manager proxy) with:

```bash
curl --location 'http://localhost:6016/telemetry?limit=5'
```

See the [Telemetry Metrics](telemetry-metrics.md) reference for a complete breakdown of every field and how each value is calculated.

## Validate Services

1. Call `GET /v1/dataprep/health` – expect `status: ok`, the active embedding mode, and the OpenVINO flag when SDK mode is selected.
2. Upload a small MP4 via `/videos/upload` and confirm:
   - The response payload reports `success`.
   - `GET /v1/dataprep/videos` lists the generated `video_id` and manifests.
   - The MinIO console (`http://localhost:6011`) shows the raw asset, thumbnails, and crops.
3. Inspect VDMS (via `vdms_cli` or a custom client) to verify entries in the `video-rag` collection.

## Troubleshooting

- **Startup fails with “model name must be provided”:** Set `MULTIMODAL_EMBEDDING_MODEL_NAME` before launching Docker (required for both SDK and API modes).
- **Object detection disabled unexpectedly:** Check logs for YOLOX download failures. Ensure the `YOLOX_MODELS_VOLUME_NAME` volume exists and the host has outbound network access during first run.
- **API mode returns 502:** Verify the multimodal embedding service is healthy at `MULTIMODAL_EMBEDDING_ENDPOINT` (see `docker compose -f docker/compose-with-embedding.yaml ps`).
- **Uploads rejected:** Files larger than 500 MB are not accepted by the FastAPI upload endpoint. Stage the video directly in MinIO and use `/videos/minio` instead.
- **GPU acceleration inactive:** Confirm `/dev/dri/*` is mapped into the container, `VDMS_DATAPREP_DEVICE=GPU`, and `SDK_USE_OPENVINO=true`.