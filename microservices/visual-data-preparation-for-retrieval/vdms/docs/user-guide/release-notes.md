# Release Notes: Visual Data Preparation for Retrieval (VDMS)

## Version 2026.1.0-rc1

**14 May 2026**

**New**

- Stage-separated SDK pipeline: decode → detect → embed → store stages run concurrently via bounded queues with back-pressure control.
- Shared memory Zero-copy frame metadata transport via POSIX shared memory pool between pipeline stages.
- Pipeline tracer that emits Chrome Tracing JSON for profiling decode/detect/embed/store stages; enabled via `SDK_ENABLE_TRACING=true`.
- Structured per-stream pipeline metrics: stage durations, throughput FPS, concurrency factor, and efficiency %. Runtime stats can be saved as JSON via `SAVE_RUNTIME_PIPELINE_STATS=true`.
- Configurable SDK pipeline via environment variables (seeded by `setup.sh` / `setup-with-embedding.sh`):


**Improvements**

- In SDK mode, uploaded video bytes are processed directly from memory; no temp-file re-read after MinIO upload.
- Batch embedding generation supports `metrics_out=True` to return inference timing alongside results.
- Telemetry log now emits a structured pipeline summary (frames, detections, embeddings, FPS, stage durations) on completion.
- Container healthcheck, raised `nofile` ulimits and `ipc: host` added to Docker Compose.
- `get-started.md` updated with full environment variable reference and setup instructions.

**Breaking Changes**

- Telemetry schema: `TelemetryRecord.stages` and `.throughput` replaced by `pipeline_stats`, `stage_duration`, and `stage_throughput` dicts. `batch_index` is now 0-based; `stream_id` field added to `TelemetryBatchDetail` and `TelemetryCounts`. Update downstream telemetry consumers.
- Docker / Kubernetes deployments must set `ipc: host` / `hostIPC: true` for the shared memory pipeline.

**Validated configuration**

- Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU, Intel® Core™ Ultra Processors (Series 2 and 3)
- Vanilla Kubernetes Cluster

## Releases 1.2.0, 1.2.1, 1.2.2, 1.2.3, 1.3.0 and 1.3.1

This microservice supports features based on the requirements of Video Search and Summarization sample application which is using this microservice. Refer to Video Search and Summarization [release notes](../../../../../sample-applications/video-search-and-summarization/docs/user-guide/release-notes.md) for release details of this microservice.
