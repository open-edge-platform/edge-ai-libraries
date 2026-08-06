# Release Notes: Multimodal Data Preparation for Retrieval

## Version 2026.2.0

**Release Date:** August 4, 2026

**New**

- **Multimodal ingestion:** the service now ingests **images** alongside video. Images are embedded directly (no frame extraction) into the same shared vector space as video frames and text summaries, discriminated by a `content_type` (`video`/`image`/`text`) metadata field, enabling cross-modal search.
- **Three image transports:** multipart binary (`POST /media/upload`), inline base64 and remote URL (`POST /media/ingest`, typed on a `type` discriminator; batch via `POST /media/ingest/batch`).
- **Async batch ingestion:** `POST /media/upload/batch`, `/media/ingest/batch`, `/media/process/batch`, and `/media/ingest-dir` return `202 Accepted` with a `job_id` polled at `GET /media/jobs/{job_id}` (cancellable via `DELETE`). Per-item error isolation keeps one bad item from failing the whole job.
- **Content deduplication:** optional content-hash (SHA-256) dedup gated by `MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS` (default `true`); byte-identical re-uploads are rejected `409 Conflict` across all transports.
- **HTTP Range / seek** support on `GET /media/download` (`206 Partial Content`).
- **Complete delete CRUD:** `DELETE /media/{bucket}/{video_id}` now removes both the stored object and its embeddings from the vector database.
- **Ingest by reference:** `store_copy=false` indexes media already present on a mounted path without copying bytes into object storage, using a canonical, path-traversal-safe metadata contract (`MM_DATAPREP_INGEST_DATA_ROOT` / `INGEST_DATA_ROOT_HOST`).
- **RTSP source support** in the embedding pipeline (`POST /media/rtsp`).
- **Metrics Manager integration:** ingestion throughput is published for live observability.
- Added expanded NPU device support in setup/runtime configuration for per-component execution (`MM_DATAPREP_EMBEDDING_DEVICE`, `MM_DATAPREP_DETECTION_DEVICE`).
- Added richer API/OpenAPI alignment updates for media processing and management endpoints.

**Improved**

- **Endpoints renamed `/videos/*` → `/media/*`** to reflect multimodal functionality (for example `/videos/upload` → `/media/upload`, `/videos/minio` → `/media/process`, `/videos/batch/{job_id}` → `/media/jobs/{job_id}`). Request/response field names (`video_id`, `video_name`, `video_url`) are unchanged for retriever compatibility.
- **Backend-agnostic:** vector database (`vdms`/`milvus`) and object storage (`minio`/`local`) are each selected at startup behind a factory via `MM_DATAPREP_VECTORDB_BACKEND` / `MM_DATAPREP_STORAGE_BACKEND` — no code changes to switch. See [Pluggable Backends](pluggable-backends.md).
- **Registry-based factories:** vector-store and storage backends self-register via a decorator, so adding a backend is a single self-contained module with no factory edits.
- **Microservice renamed** from `vdms-dataprep` to `multimodal-dataprep`, removing VDMS-specific naming from generic identifiers.
- **Environment variables normalized** under a single `MM_DATAPREP_` prefix, with fully independent per-component device selection.
- **Single in-process embedding pipeline:** the deprecated API embedding mode and the standalone multimodal-embedding-serving container were removed; embeddings are generated through the in-process Python SDK.
- Object detection now applies to both video frames and images via the shared `MM_DATAPREP_ENABLE_OBJECT_DETECTION` toggle.
- Hardened NPU runtime dependency installation in Docker images (including stricter Level Zero/driver setup validation).
- Simplified containerization flow by removing legacy dev/lint/report runtime paths and aligning setup scripts with a production-focused image flow.
- Updated compose/setup defaults and docs to reflect current accelerator-oriented configuration behavior.

**Fixed**

- Resolved a shared-memory pool deadlock: pool acquisition is now time-bounded and batch size is clamped to the pool capacity.
- Video processing is offloaded to a worker thread so long ingestions no longer block the event loop and stall `/health`.
- Duplicate-upload policy is now enforced per item for batch-processed media (`POST /media/process/batch`), matching the single-media path.
- Duplicate-upload conflicts no longer leave orphan tiles behind.
- DataPrep object bucket aligned with the video summary flow.
- Fixed an end-of-stream hang on the RTSP ingestion path.
- Fixed Milvus connection failures on existing collections, plus Milvus compose environment wiring and healthcheck.
- Fixed request-schema compatibility issue in upload processing parameters for newer FastAPI/Pydantic combinations.

**Upgrade Notes**

- Consumers of the old `/videos/*` paths must migrate to `/media/*`.
- Environment variables not already prefixed with `MM_DATAPREP_` must be renamed (for example `MM_EMBEDDING_DEVICE` → `MM_DATAPREP_EMBEDDING_DEVICE`).

## Version 2026.1.0

**June 17, 2026**

**New**

- Stage-separated embedding pipeline: decode → detect → embed → store stages run concurrently via bounded queues with back-pressure control.
- Shared memory Zero-copy frame metadata transport via POSIX shared memory pool between pipeline stages.
- Pipeline tracer that emits Chrome Tracing JSON for profiling decode/detect/embed/store stages; enabled via `MM_DATAPREP_ENABLE_TRACING=true`.
- Structured per-stream pipeline metrics: stage durations, throughput FPS, concurrency factor, and efficiency %. Runtime stats can be saved as JSON via `MM_DATAPREP_SAVE_RUNTIME_PIPELINE_STATS=true`.
- Configurable embedding pipeline via environment variables (seeded by `setup.sh`).

**Improved**

- Uploaded video bytes are processed directly from memory; no temp-file re-read after MinIO upload.
- Batch embedding generation supports `metrics_out=True` to return inference timing alongside results.
- Telemetry log now emits a structured pipeline summary (frames, detections, embeddings, FPS, stage durations) on completion.
- Container healthcheck, raised `nofile` ulimits and `ipc: host` added to Docker Compose.
- `get-started.md` updated with full environment variable reference and setup instructions.

**Upgrade Notes**

- Telemetry schema: `TelemetryRecord.stages` and `.throughput` replaced by `pipeline_stats`, `stage_duration`, and `stage_throughput` dicts. `batch_index` is now 0-based; `stream_id` field added to `TelemetryBatchDetail` and `TelemetryCounts`. Update downstream telemetry consumers.
- Docker / Kubernetes deployments must set `ipc: host` / `hostIPC: true` for the shared memory pipeline.

*Validated configuration*

- *Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU, Intel® Core™ Ultra Processors (Series 2 and 3)*
- *Vanilla Kubernetes Cluster*

## Releases 1.2.0, 1.2.1, 1.2.2, 1.2.3, 1.3.0 and 1.3.1

This microservice supports features based on the requirements of Video Search and Summarization sample application which is using this microservice. Refer to Video Search and Summarization [release notes](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/release-notes.html) for release details of this microservice.
