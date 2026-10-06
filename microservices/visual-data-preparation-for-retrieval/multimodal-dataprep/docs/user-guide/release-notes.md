# Release Notes: Multimodal Data Preparation for Retrieval

## Version 2026.3.0

**Release Date**: TBD

**New**:

- **Live (RTSP) stream ingestion as a managed resource:** the new `/media/streams` CRUD surface registers a camera and ingests it continuously on a background worker — create (single and batch), list with `state`/`tags` filters, inspect stats, pause/resume and reconfigure via `PATCH`, and delete (single and batch) with optional `purge_embeddings` / `purge_media`. Registrations are persisted and restored on restart, dropped sources reconnect with a bounded budget, and live embeddings are addressable through the existing media endpoints (`bucket_name` = `MM_DATAPREP_LIVE_STREAM_BUCKET`, `video_id` = `stream_id`).
- **Playback media for live streams:** each stream records N-second MP4 segments (`MM_DATAPREP_LIVE_SEGMENT_DURATION_SECONDS`, default 10), and every live embedding points at the segment covering its frame — so a retrieval hit on a live camera is playable.
- **Live retention:** `MM_DATAPREP_LIVE_RETENTION_HOURS` (default `0` = keep forever) prunes live embeddings and media past the window; requires the new vector-store `delete_embeddings_before()` operation, implemented for both VDMS and Milvus.
- **Live telemetry and health:** live sessions are recorded by `GET /telemetry`, and `GET /health` reports live-stream counts per state.
- **External media correlation contract:** every live embedding now records `sensor_id` (stable identity of the physical source, settable at registration and defaulting to the `stream_id`), `capture_time` with an explicit `capture_time_source`, and `media_owner`. These let media stored by another service be matched back to an embedding without changing the decode or embedding path. See [Stream Manager Integration Readiness](../integration/stream-manager-readiness.md).
- **Camera-clock capture timestamps for live streams:** `capture_time` is derived from each frame's PTS anchored to the best available clock, rather than from the ingest instant. This removes per-frame pipeline jitter and lets an independent consumer of the same RTSP feed resolve the same frame. The source degrades through `rtcp_sender_report` → `stream_anchored` → `ingest_estimated`, reported in `capture_time_source`; implausible camera clocks are rejected rather than trusted. Segment bucketing is unchanged and still uses ingest time. **In practice expect `stream_anchored`:** validation against a Hikvision DS-2CD1023G0E-I found the camera emits no RTCP at all — a raw probe saw 4316 RTP packets and 0 RTCP packets over 45 s on TCP, and none on UDP — so no client can recover an NTP mapping. Always branch on `capture_time_source` rather than assuming camera-clock accuracy.
- **Camera clock-skew warning:** starting a live stream probes the device's HTTP `Date` header and logs a warning when its clock disagrees with the host by more than `MM_DATAPREP_LIVE_CLOCK_SKEW_WARN_SECONDS` (default 2). The check is vendor-neutral, sends no credentials, runs off the ingestion path, and never alters a stored timestamp — it surfaces the otherwise-invisible condition that makes a camera unusable as a shared time reference when correlating with an external recorder. It distinguishes genuine drift from embedded web servers that stamp local time but label it `GMT`. Disable with `MM_DATAPREP_LIVE_CLOCK_CHECK_ENABLED=false`.

**Fixed**:

- **Live streams now produce embeddings promptly.** Batches were only flushed once `MM_DATAPREP_VIDEO_EXTRACTION_BATCH_SIZE` sampled frames had accumulated, and the "drain whatever is left" path only runs at end-of-stream — which an RTSP source never reaches. A camera at 12.5 fps with `frame_interval=15` therefore produced nothing for roughly five minutes while pinning shared-memory blocks. Partially filled batches from live sources are now flushed once the oldest frame reaches `MM_DATAPREP_LIVE_BATCH_MAX_AGE_SECONDS` (default 20).
- **Live stream statistics no longer stay at zero.** `frames_processed` and `embeddings_created` were only updated after the ingestion pipeline returned, which for a continuous stream never happens. Progress is now reported per stored batch, so `GET /media/streams/{stream_id}` reflects ingestion while it runs.
- **Recorded live media is now downloadable.** `GET /media` lists live objects under `<stream_id>/segments/...`, but `GET /media/download` rejected the `/` in those paths and a bare `video_id` returned an arbitrary object — so a retrieval hit on a live camera could not be played back. The endpoint accepts a new `media_path` query parameter resolved strictly within the stream's own prefix.
- **External correlation fields now reach the vector database.** `sensor_id`, `capture_time`, `capture_time_source`, and `media_owner` were computed per frame but were not part of the enforced canonical metadata contract, so they were stripped before storage and never appeared in retrieval results.
- **Live sessions now appear in `GET /telemetry`.** Records were built with a `-1` "unknown" stream index that failed the non-negative schema constraint, so every live record was silently discarded; the counts were also reported as zero because the live pipeline does not surface totals at the top level of its result.
- **Camera credentials no longer reach the service logs.** The decoder recorded the raw RTSP URL as the stream's source in the metadata it logs verbatim, disclosing any embedded `user:pass@`. That value is now redacted with the same helper used for API responses and vector metadata.
- Live ingestion no longer stores embeddings under a placeholder identity (`RTSP_BUCKET` / `video_id=-1`), which made them impossible to list, filter, or delete.
- **Ingestion no longer hangs when a decoder thread dies.** A frame larger than the shared-memory block size (for example 4K portrait video against the 1920x1080 default) killed the producer thread without signalling completion, leaving the request spinning forever and never returning. Decoder failures are now forwarded to the consumer and raised, and the request is rejected with `400 Bad Request` naming `MM_DATAPREP_VIDEO_SHM_BLOCK_SIZE` and the required byte count instead of an opaque `500`. The failure path also shuts down the shared-memory pools, which previously leaked on every failed request.
- **Concurrent embedding requests no longer abort the worker.** Two overlapping inference calls could overwrite each other's async completion callback, writing a result into a wrong-sized buffer and terminating the process with SIGABRT. Inference submission is now serialized per model instance and callback exceptions are re-raised in the submitting thread.

**Upgrade Notes**:

- **Breaking:** `POST /media/rtsp` has been removed. Register the source with
  `POST /media/streams` instead; the call returns immediately with a `stream_id`
  rather than holding the request open for the life of the stream, and
  `DELETE /media/streams/{stream_id}` replaces client-disconnect as the stop
  signal.
- Live-stream registrations are stored in a SQLite file on the existing
  `data-prep` volume (`MM_DATAPREP_LIVE_STREAM_STATE_PATH`). Deployments that do
  not persist that volume will lose registrations across restarts.
- Live ingestion grows the vector index indefinitely unless
  `MM_DATAPREP_LIVE_RETENTION_HOURS` is set.

## Version 2026.2.0

**Release Date**: September 9, 2026

**New**:

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

**Improved**:

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

**Fixed**:

- Resolved a shared-memory pool deadlock: pool acquisition is now time-bounded and batch size is clamped to the pool capacity.
- Fixed file-descriptor exhaustion (`[Errno 24] Too many open files`) in the shared-memory pool: each block held two open descriptors, so the frame and detected-crop pools together needed roughly 3000 and failed under a 1024-descriptor limit. Blocks now release their descriptor after allocation.
- Fixed shared-memory segments leaking into `/dev/shm` when pool teardown hit an already-unlinked block; blocks are now unlinked independently.
- Video processing is offloaded to a worker thread so long ingestions no longer block the event loop and stall `/health`.
- Duplicate-upload policy is now enforced per item for batch-processed media (`POST /media/process/batch`), matching the single-media path.
- Duplicate-upload conflicts no longer leave orphan tiles behind.
- DataPrep object bucket aligned with the video summary flow.
- Fixed an end-of-stream hang on the RTSP ingestion path.
- Fixed Milvus connection failures on existing collections, plus Milvus compose environment wiring and healthcheck.
- Fixed request-schema compatibility issue in upload processing parameters for newer FastAPI/Pydantic combinations.

**Upgrade Notes**:

- Consumers of the old `/videos/*` paths must migrate to `/media/*`.
- Environment variables not already prefixed with `MM_DATAPREP_` must be renamed (for example `MM_EMBEDDING_DEVICE` → `MM_DATAPREP_EMBEDDING_DEVICE`).

## Version 2026.1.0

**Release Date:** June 17, 2026

**New**:

- Stage-separated embedding pipeline: decode → detect → embed → store stages run concurrently via bounded queues with back-pressure control.
- Shared memory Zero-copy frame metadata transport via POSIX shared memory pool between pipeline stages.
- Pipeline tracer that emits Chrome Tracing JSON for profiling decode/detect/embed/store stages; enabled via `MM_DATAPREP_ENABLE_TRACING=true`.
- Structured per-stream pipeline metrics: stage durations, throughput FPS, concurrency factor, and efficiency %. Runtime stats can be saved as JSON via `MM_DATAPREP_SAVE_RUNTIME_PIPELINE_STATS=true`.
- Configurable embedding pipeline via environment variables (seeded by `setup.sh`).

**Improved**:

- Uploaded video bytes are processed directly from memory; no temp-file re-read after MinIO upload.
- Batch embedding generation supports `metrics_out=True` to return inference timing alongside results.
- Telemetry log now emits a structured pipeline summary (frames, detections, embeddings, FPS, stage durations) on completion.
- Container healthcheck, raised `nofile` ulimits and `ipc: host` added to Docker Compose.
- `get-started.md` updated with full environment variable reference and setup instructions.

**Upgrade Notes**:

- Telemetry schema: `TelemetryRecord.stages` and `.throughput` replaced by `pipeline_stats`, `stage_duration`, and `stage_throughput` dicts. `batch_index` is now 0-based; `stream_id` field added to `TelemetryBatchDetail` and `TelemetryCounts`. Update downstream telemetry consumers.
- Docker / Kubernetes deployments must set `ipc: host` / `hostIPC: true` for the shared memory pipeline.

*Validated configuration*:

- *Intel® Xeon® 5 + Intel® Arc&trade; B580 GPU, Intel® Core™ Ultra Processors (Series 2 and 3)*
- *Vanilla Kubernetes Cluster*

## Releases 1.2.0, 1.2.1, 1.2.2, 1.2.3, 1.3.0 and 1.3.1

This microservice supports features based on the requirements of Video Search and Summarization sample application which is using this microservice. Refer to Video Search and Summarization [release notes](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/release-notes.html) for release details of this microservice.
