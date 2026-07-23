# Overview and Architecture

VDMS DataPrep turns raw video content and associated summaries into searchable embeddings that conform to the requirements of the VSS Search microservice. The architecture is intentionally modular so that each stage can scale independently or be swapped out without changing the API surface.

## Architecture Overview

### High-Level Architecture Diagram
![Architecture Diagram](images/VDMS_DataPrep.png)
*Figure 1: High-level system view demonstrating the microservice.*

### Core Components

- **VDMS DataPrep (this service)** – A FastAPI application mounted at `/v1/dataprep`. It orchestrates frame extraction, object detection, in-process embedding generation, manifest storage, and metadata management.
- **Multimodal Embedding package** – The local package dependency (`multimodal-embedding-serving`) is imported directly so models are loaded in-process by DataPrep.
- **VDMS Vector DB** – Central vector store that persists frame, crop, and summary embeddings along with metadata (`video_url`, tags, timestamps). The collection name defaults to `video-rag` and can be overridden via `MM_DATAPREP_DB_COLLECTION`.
- **MinIO Object Store** – Persistent storage for the raw video assets and temporary frame caches when the shared-volume strategy is unavailable. Buckets are validated/created on demand through the integrated MinIO client helper.

### Inputs

- **Direct uploads** through `POST /v1/dataprep/media/upload` where the service streams the bytes into MinIO and keeps them in memory for processing.
- **MinIO references** through `POST /v1/dataprep/media/process` for content already present in MinIO. The request only needs the bucket name, directory (`video_id`), and optionally a specific filename.
- **Video summaries** through `POST /v1/dataprep/summary`. These requests reference an existing video and enrich it with timestamp-aligned text metadata and tags.

### Processing Pipeline

1. **Request validation & sanitation** – All payloads are validated using the Pydantic models in `src/common/schema.py`. Optional request overrides (`frame_interval`, `enable_object_detection`, `detection_confidence`, `tags`) are normalized at this stage.
2. **Frame extraction** – `src/core/utils/video_utils.py` reads the video via decord, sampling every Nth frame and saving crops when object detection is enabled. Extraction strategies and fallbacks (shared volume ➝ object storage ➝ base64 transfer) are configured in `src/config.yaml`.
3. **Object detection** – YOLOX models are loaded once per worker and reused using `create_detector_instance`. Detection can be toggled per request or globally via `MM_DATAPREP_ENABLE_OBJECT_DETECTION`.
4. **Embedding generation** – The service runs the in-process embedding pipeline, fans out work across multiple threads (`MM_DATAPREP_MAX_PARALLEL_WORKERS`), and stores embeddings in bulk. All embeddings are stamped with download URLs, timestamps, and detector metadata.
5. **Metadata persistence** – `metadata_utils` writes frames manifests and per-frame metadata, then hands them to the embedding client (`EmbeddingClient`) for storage.

### Outputs

- **Embeddings & metadata** persisted in VDMS with references back to the originating video, frame numbers, crop details, and optional tags.
- **Raw media** stored in MinIO under `{video_id}/{filename}` with download links exposed via `GET /v1/dataprep/media/download`.
- **Operational responses** that report the number of embeddings stored and success/error status for clients.

## Supporting Resources

- [Get Started Guide](get-started.md)
- [Video Ingestion Flow](./video-ingestion-flow.md) - Detailed flow diagrams of the video processing pipeline
- [API Reference](api-reference.md)
- [System Requirements](system-requirements.md)
