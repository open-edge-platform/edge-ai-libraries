<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Source map — Multimodal DataPrep

## Application lifecycle

`src/main.py` creates the FastAPI app with `root_path="/v1/dataprep"`, CORS,
and a `DataPrepResponse` error envelope. Its lifespan:

1. starts the optional Metrics Manager publisher;
2. preloads `preload_embedding_client()` and `preload_object_detector()`;
3. serves requests;
4. stops the publisher and calls `get_vector_store().update_index()` during
   shutdown.

`GET /health` is implemented in `src/endpoints/health/check_health.py`. Its
declared response includes service status, embedding-client status/model/device,
OpenVINO state, and detection model/device.

## API routers

All paths below are relative to `/v1/dataprep`.

| Route | Handler |
|---|---|
| `GET /health` | `health/check_health.py` |
| `POST /summary` | `document_processing/process_text.py` |
| `POST /media/upload` and `/media/rtsp` | `video_processing/upload_and_process_video.py` |
| `POST /media/process` | `video_processing/process_minio_video.py` |
| `POST /media/ingest` and `/media/ingest/batch` | `video_processing/ingest_image.py` |
| `POST /media/upload/batch`, `/media/process/batch`, `/media/ingest-dir` | `video_processing/batch_ingest.py` |
| `GET /media/jobs/{job_id}` and `DELETE /media/jobs/{job_id}` | `video_processing/batch_ingest.py` |
| `GET /media` | `video_management/list_videos.py` |
| `GET /media/download` | `video_management/download_video.py` |
| `DELETE /media/{bucket_name}/{video_id}` | `video_management/delete_video.py` |
| `GET /telemetry` | `telemetry/telemetry.py` |

Request and response models live in `src/common/schema.py`, including typed
image sources and asynchronous batch job state/results.

## Embedding and ingestion pipeline

| Path | Responsibility |
|---|---|
| `src/core/embedding/embedding_orchestrator.py` | Async entry points for stored, uploaded, URI, image, and text inputs; metadata, telemetry, storage cleanup, and Metrics Manager notification |
| `src/core/embedding/embedding_helper.py` | In-process model/detector singletons, preload/warmup, threaded video pipeline, shared-memory frame handling, detection, embedding, storage workers, and runtime pipeline statistics |
| `src/core/embedding/client.py` | `EmbeddingClient`: loads the model handler from `multimodal-embedding-serving`, probes capabilities/dimensions, generates image/text vectors, and delegates persistence to the active vector store |
| `src/core/embedding/decoder.py` | File/bytes/RTSP decoding, frame batching, shared-memory pool, and `VideoFrameExtractor` |
| `src/core/image_ingest.py` | Base64/data-URL decoding, remote image fetching with limits, image validation, and filename resolution |
| `src/core/media.py` | Supported video/image extensions, kind detection, and MIME helpers |
| `src/core/dedup.py` | Content-hash registration and duplicate-upload policy |
| `src/core/jobs/` | In-memory asynchronous batch jobs and processors |

Embedding is always in process; follow only the current modules listed above.

## Pluggable persistence

### Vector stores

- `src/core/vectorstores/base.py` defines `BaseVectorStore`.
- `factory.py` lazily loads registered backends and returns a cached singleton
  selected by `MM_DATAPREP_VECTORDB_BACKEND`.
- `vdms_store.py` and `milvus_store.py` implement the current backends.
- `metadata.py` projects canonical metadata into backend-appropriate forms.

Endpoint and pipeline code must use `get_vector_store()`. Adding a backend
means implementing/registering a new store module and adding focused tests; do
not add backend branches throughout endpoints.

### Media storage

- `src/core/storage/base.py` defines `BaseStorage`.
- `factory.py` selects the cached backend from
  `MM_DATAPREP_STORAGE_BACKEND`.
- `minio_storage.py` and `local_storage.py` are the current implementations.
- `src/core/minio_client.py` is the lower-level MinIO adapter retained by the
  MinIO storage backend.

Use `get_storage()` (or the compatibility helper `get_minio_client()`, which
returns the active storage abstraction) rather than constructing MinIO in
endpoint code.

## Configuration and observability

| Path | Responsibility |
|---|---|
| `src/common/settings.py` | Pydantic settings with `MM_DATAPREP_` environment prefix |
| `src/config.yaml` | Frame extraction, detection, ROI, and runtime defaults |
| `src/core/validation.py` | Request/path validation and sanitization |
| `src/core/telemetry/` | Persistent JSONL ingestion records exposed by `/telemetry` |
| `src/core/metrics_manager.py` | Optional asynchronous publisher configured by `MM_DATAPREP_METRICS_MANAGER_URL` |
| `src/core/utils/metadata_utils.py` | Canonical metadata and download URL generation |

## Build and deployment

- `docker/Dockerfile` copies
  `visual-data-preparation-for-retrieval/multimodal-dataprep/` and the sibling
  `multimodal-embedding-serving/` from the `microservices/` build context.
- `build.sh` is the sanctioned image build and supports `--push`.
- `docker/compose.yaml` runs DataPrep with VDMS and MinIO.
- `docker/compose-milvus.yaml` runs DataPrep with Milvus and MinIO.
- `docker/compose.storage-local.yaml` switches media storage to the local
  filesystem when layered after the default compose file.
- `docker/compose.rtsp-test.yaml` provides an RTSP test publisher/server.
