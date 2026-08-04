# Release Notes: Video Search and Summarization Sample Application

## Version 2026.2.0

**Release Date:** August 4, 2026

**New:**

- **Backend-agnostic vector search:** Select the vector database with `VECTORDB_BACKEND` (`vdms` default, `milvus`). All vector similarity search is delegated to the standalone `vector-retriever` microservice; `video-search` keeps query orchestration and frame-to-video aggregation, so results are identical in shape across backends.
- **Multimodal DataPrep:** Replaced the legacy VDMS DataPrep with the `multimodal-dataprep` microservice across Docker Compose, Helm, and documentation.
- **Metrics Manager integration:** Replaced the legacy telemetry collector; the search UI now shows live multi-GPU telemetry (`ENABLE_METRICS_MANAGER=true`).
- **Batch video upload and embedding:** Multi-select upload in the UI uploads all files and submits a single asynchronous batch embeddings job, with new `search-embeddings-batch` and `search-embeddings-jobs` Pipeline Manager endpoints and job-status polling. Single-file upload keeps the synchronous path.
- **Directory watcher batch processing:** The directory watcher service now batches video uploads and embedding creation.
- **Duplicate-content upload policy:** New `MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS` setting (Docker Compose and Helm `global.env`) rejects content-identical re-uploads with HTTP `409`. Enforced per item for batch-processed media, so a duplicate fails only its own item.
- **Model download support:** Models are now fetched by a dedicated model-download step in `setup.sh`, including generic YOLO ids from the ultralytics hub for object detection.
- **Search score transparency:** Search results show the query-normalized relevance score alongside the underlying raw segment score and peak frame similarity, with a per-stage scoring breakdown popover and a weak-match indicator.
- **Makefile, functional test suite, and CI security scans** for the Video Search and Summarization sample application.
- **AI agent skills:** Added VSS agent skills (deploy, build, troubleshoot, summarize, search, and more) for AI coding assistants.

**Improved:**

- **Search orchestration alignment for accelerator usage:** Updated setup and compose behavior for Video Search so NPU device selections are preserved and propagated consistently for DataPrep and multimodal embedding services.
- **Simplified per-component device model (Compose):** Retired the redundant `VDMS_DATAPREP_DEVICE` baseline knob. Device selection is now purely per-component — `DATAPREP_EMBEDDING_DEVICE`, `DATAPREP_DETECTION_DEVICE`, and `MME_EMBEDDING_DEVICE` (each defaults to `CPU`) — matching the Helm chart model. `ENABLE_EMBEDDING_GPU` is now a mode-aware embedding shortcut (`sdk`→DataPrep embedding GPU, `api`→MME embedding GPU).
- **Helm accelerator support for search stack:** Updated VSS Helm subcharts for `multimodal-embedding-ms` and `multimodal-dataprep` to support NPU as an accelerator path (device-key validation, resource requests/limits, and `/dev/accel` mounts).
- **Helm accelerator device permissions:** Added `global.accelGroupIds` so the host gids owning `/dev/dri` (GPU) and `/dev/accel` (NPU) are injected into the pod `supplementalGroups`, letting the non-root container open the accelerator device (mirrors the Compose `group_add` render/video groups). Fixes NPU/GPU device initialization falling back to CPU-only.
- **Helm OpenVINO™ model cache:** Added a persistent OpenVINO™ cache (`ovCacheDir`, default `/app/ov_models/ov_cache`) for `multimodal-embedding-ms` and `multimodal-dataprep`, plus a longer DataPrep `startupProbe` budget, so GPU/NPU model compilation completes once and is reused across pod restarts instead of recompiling (avoids startup crash loops).
- **Helm single-source image override:** `global.registry`, `global.tag`, and `global.pullPolicy` now apply across all VSS service images (pipeline-manager, video-ingestion, video-search, vss-ui, multimodal-dataprep, multimodal-embedding-serving) from one place, with independent per-service PVCs for model/cache data.
- **Helm value override precedence:** Subchart defaults no longer shadow `global.env` overrides for `MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS` and `SDK_USE_OPENVINO`, so `--set global.env.<KEY>` now takes effect.
- **Clearer embedding error reporting:** The video embedding flow now surfaces the real upstream DataPrep error instead of a misleading "Request timed out" message; only genuine timeouts (`408`/`504`/connection aborts) are reported as timeouts.
- **Graceful OVMS cache fallback:** `setup.sh` now degrades cleanly when GPU drivers are absent instead of failing model cache setup.
- **Original filenames in embedding metadata:** The uploaded video name is threaded end-to-end into stored embedding metadata, so search results show the original filename.
- **Service health and startup dependencies** hardened across the stack, with retries for transient batch job polling failures.
- **Search deployment documentation refresh:** Added a dedicated **Deployment Options for Video Search** matrix (SDK/API with CPU/GPU/NPU combinations), including explicit `DATAPREP_EMBEDDING_DEVICE`, `MME_EMBEDDING_DEVICE`, and `DATAPREP_DETECTION_DEVICE` examples for accelerator-specific routing.
- **Helm user-guide clarifications:** Updated Helm guidance to include NPU device/key combinations and matching-device recommendations for shared PVC scheduling.
- **Documentation:** Aligned user and agent documentation with the multi-backend architecture, refreshed the DataPrep, retriever, and VSS OpenAPI specs, added 4K/8K video ingestion troubleshooting guidance, and split 2025 release notes into a separate document.
- **Maintenance:** Refreshed dependency version constraints and lock files, pinned Dockerfiles to release versions, aligned the DataPrep bucket with the video summary bucket, updated the VSS health check with a manual CI workflow trigger, and removed the `profile_dataprep` script and the vestigial `EMBEDDING_PROCESSING_MODE` chart value.

**Fixed:**

- Duplicate-upload conflicts no longer leave orphaned video tiles in the UI.
- Search result tiles no longer render as black thumbnails.
- Assorted `search-ms` and video embedding flow defects.

## Version 2026.1.0

**Release Date:** June 17, 2026

**New:**

- **EXPERIMENTAL - vLLM Intel® Arc™ Pro B-series GPU Support:** Added initial experimental support for running vLLM on Intel® Arc™ Pro B-series GPUs (XPUs) via new `ENABLE_VLLM_GPU` environment variable and `docker/compose.vllm.xpu.yaml` Docker Compose overlay. This feature enables GPU-accelerated VLM captioning and LLM summarization on Intel® Arc™ Pro B-series hardware (e.g., B60, B65, B70).
  > **Note:** This is an experimental feature in early stages and may require additional tuning and optimization. Performance characteristics are still being evaluated. Not recommended for production use.
- Added a a new Dual UI mode with a new `--summary --search` CLI argument for `setup.sh` that allows running both the summary and the search applications simultaneously at **/summary** and **/search** URI endpoints respectively.
- Added Dual UI support for Helm chart installations by allowing a values override file to be provided for summary and search modes simultaneously.

**Improved:**

- Updated setup script and nginx configuration files to allow flexible UI routing for each existing mode of deployment (summary mode, search mode, Unified UI Mode) and the new Dual UI mode.
- Refactored Helm chart to use a reusable `vssui` subchart with multi-mode nginx and consolidated embedding model config under `global.embeddingModelName`.
- Updated DLStreamer base image to `2026.1.0-ubuntu24-rc1` for Video Ingestion Microservice.
- **Setup Script:** Updated the environment variable to setup embedding models. New `MULTIMODAL_EMBEDDING_MODEL` and the existing `TEXT_EMBEDDING_MODEL` are used to provide embedding models in relevant modes.
- **Docker Compose:** Replaced `curl` with Python `urllib` package in the container `healthcheck` command for a lighter runtime footprint for Audio Analyzer.
- **Docker Compose:** Replaced environment variables with hard-coded mount paths. This helps in stopping containers without looking for preset variables.
- **Build Script:** Removed Audio-Analyzer from the dependency build pipeline. A frozen version 1.3.3 will be used for the Audio Analyzer microservice for the current and all subsequent releases.
- **Setup Script:** Removed unused environment variables and several environment variables being used as mount directories in Docker Compose files.

## Version 1.3.3-rc1

**Release Date:** 05 May 2026

**Features:**

- **Configurable final video summary**: Added `PM_PRODUCE_FINAL_SUMMARY` feature flag to make the final LLM map-reduce video summary optional. When disabled, chunk-wise summaries are displayed chronologically instead. A per-video UI override checkbox is available in both upload flows. Audio transcript summarization is automatically skipped when the final summary is turned off.
- **Audio transcript summarization**: Added audio transcript summarization support and improved audio transcription accuracy.
- **OVMS-first architecture**: Replaced the standalone `vlm-openvino-serving` microservice with OpenVINO™ Model Server (OVMS) as the unified inference backend for both VLM captioning and LLM summarization. This is a **breaking change**; the `vlm-inference` subchart and container have been removed.
- **Performance Optimizations (MME & VDMS-Data-Prep)**:
  - Refactored pre-processing and inference with `AsyncInferQueue` based OpenVINO™ inference and static shape model compilation for iGPU.
  - Added ThreadPool for parallel open_clip image pre-processing with support for input tensor batching and padding for optimal OpenVINO™ inference paths.
  - Introduced PyAV-based video decode abstraction supporting keyframes and uniform sampled frames extraction with producer-consumer pattern for parallel decode and frame translation to PIL.
  - Enabled multiple/parallel decoder instances for file, RTSP stream, and bytes input sources.
  - Implemented frame batching for pipelined pre-processing and inference with integrated PyAV decoder in VDMS data-prep.
- **Search Timeout and Resource Management**: Added `SEARCH_DATAPREP_TIMEOUT_MS` configuration to prevent VSS-UI timing out during embedding creation. Added ulimit constraints with soft and hard limits to enable shared memory creation and define memory block allocation boundaries.

**HW used for validation:**

- Intel® Xeon® 5 + Intel® Arc™ B580 GPU
- Vanilla Kubernetes Cluster

**Known Issues/Limitations:**

- This release includes only limited testing on EMT‑S and EMT‑D, some behaviors may not yet be fully validated across all scenarios.
- HW sizing of the Video Search or Video Summarization pipeline is in progress. Optimization of the pipelines will follow HW sizing.
- Known issues are internally tracked. Reference not provided here.
- `how-to-performance` document is not updated yet. HW sizing details will be added to this section shortly.
- NPU support with OVMS is added as experimental feature and may not work for all models or configurations.

## Version 1.3.2

**Release Date:** 17 Feb 2026

**Features:**

- In VSS search mode, users can now filter results by time range via:
- Query parsing to infer time ranges (e.g., "person seen in last 5 minutes").
- Direct time range input from the UI.
- Added live system and DataPrep performance metrics in the search UI (enable with `export ENABLE_METRICS_MANAGER=true`).
- Fixed the build script of the `vdms-dataprep` microservice.
- Added telemetry collection of the application metrics for VDMS-dataprep microservice and VLM microservice at `/telemetry` endpoint.

**HW used for validation:**

- Intel® Xeon® 5 + Intel® Arc™ B580 GPU
- Vanilla Kubernetes Cluster

## Previous Releases

- [Release Notes 2025](./release-notes/release-notes-2025.md)

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2025 <release-notes/release-notes-2025.md>

:::
hide_directive-->
