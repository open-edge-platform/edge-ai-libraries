
# Visual Data Management System (VDMS) based Data Preparation Microservice
VDMS DataPrep is the ingestion and embedding service that powers the Video Search and Summarization (VSS) flow. It accepts raw media, orchestrates frame-level enrichment (including object detection), and stores both the derived embeddings and the original assets in VDMS Vector DB and MinIO respectively. The service can operate in two different execution paths:

- **SDK mode (`EMBEDDING_PROCESSING_MODE=sdk`)** – the default, latency-optimized path that calls the multimodal embedding models in-process, keeps video bytes in memory, and optionally enables OpenVINO™ acceleration.
- **API mode (`EMBEDDING_PROCESSING_MODE=api`)** – a compatibility path that keeps parity with earlier deployments by invoking the multimodal embedding serving microservice over HTTP.

The FastAPI application is mounted under the `/v1/dataprep` root path and exposes endpoints to ingest videos, process existing MinIO content, attach human-authored summaries, and manage stored media.

## Overview

The microservice focuses on video-first pipelines while still supporting downstream text enrichment:

1. **Source ingestion:** Videos can be uploaded directly or referenced from MinIO buckets that the service has access to.
2. **Frame extraction and detection:** Every Nth frame (configurable via `FRAME_INTERVAL`) is sampled. When object detection is enabled, the detector generates cropped regions of interest that are embedded separately from the full frame.
3. **Embedding generation:** Depending on the processing mode, embeddings are generated either through the SDK pipeline (memory-first, multi-threaded, OpenVINO-aware) or through the multimodal embedding HTTP endpoint.
4. **Metadata enrichment:** Each frame or crop is annotated with timestamps, download URLs (`/v1/dataprep/videos/download`), detection confidences, and tags.
5. **Persistent storage:** Embeddings and metadata are stored in VDMS while the raw assets remain in MinIO for later retrieval.

## Key Benefits

- **Video-aware ingest:** Frame-level sampling, optional YOLOX-based object detection, and manifest-based storage tailored for downstream aggregation in Search-MS.
- **Flexible runtime:** Runtime toggles for SDK/API processing, OpenVINO acceleration, and GPU offload (`VDMS_DATAPREP_DEVICE=GPU`) without code changes.
- **Consistent metadata model:** Each stored record always references the canonical download URL and includes timestamps, tag lists, and bucket identifiers for frictionless recall.
- **Operational efficiency:** Cached SDK clients, preloading at startup, parallel embedding pipelines, and MinIO-aware utilities reduce cold-start latency and I/O overhead.
- **End-to-end observability:** Structured logging, health reporting, and schema-validated requests provide clear insight during development and production operations.

## Feature Highlights

- **REST API surface mounted at `/v1/dataprep`** with endpoints for health, media ingest (`/videos/upload`, `/videos/minio`), metadata retrieval (`/videos`), bulk download, deletion, and summary ingestion (`/summary`).
- **Object detection first-class support** with per-request overrides (`enable_object_detection`, `detection_confidence`) and automatic fallback when a model is unavailable.
- **Tags and summaries** that link curated text back to the precise video segment, enabling multi-modal search.
- **Configuration-driven behavior** through `config.yaml` and environment overrides for frame strategies, fallback transports, and detector settings.
- **Containerized deployment** via Docker Compose with companion services for MinIO, VDMS Vector DB, and optional multimodal embedding serving.

## Example Use Cases

- **Semantic video search:** Populate VDMS with frame and crop embeddings to power temporal aggregation and ranking in Search-MS.
- **Operations review:** Store clips and timestamped human summaries that can be replayed directly using generated download URLs.
- **Hybrid analytics:** Combine frame embeddings with detector metadata to filter results by objects, tags, or time ranges.
- **Content auditing:** Automatically surface clips containing specific objects or scenes based on the detector-enhanced embeddings.

## Supporting Resources

- [Get Started Guide](get-started.md)
- [API Reference](api-reference.md)
- [System Requirements](system-requirements.md)
