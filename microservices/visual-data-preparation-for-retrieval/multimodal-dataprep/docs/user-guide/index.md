# Multimodal Data Preparation Microservice

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/visual-data-preparation-for-retrieval/multimodal-dataprep">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/visual-data-preparation-for-retrieval/multimodal-dataprep/README.md">
     Readme
  </a>
</div>
hide_directive-->

Multimodal DataPrep is the ingestion and embedding service that powers the [Video Search and Summarization (VSS)](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/index.html) and [Visual Search & Question-Answering (VSQA)](https://docs.openedgeplatform.intel.com/dev/edge-ai-suites/visual-search-question-and-answering/index.html) flows. It accepts raw media — **videos and images** — orchestrates enrichment (frame sampling for video, direct embedding for images, optional object detection for both), generates embeddings in-process, and stores both the derived embeddings and the original assets in a vector database and object storage. The service is **vector-database agnostic** (VDMS, Milvus) and **storage agnostic** (MinIO, local filesystem); backends are selected at startup with no code changes.

The FastAPI application is mounted under the `/v1/dataprep` root path and exposes endpoints to ingest videos and images (binary upload, base64, or remote URL), process existing stored content, ingest in batches, attach human-authored summaries, and manage stored media.

## Overview

The microservice handles multimodal ingestion with a unified media pipeline:

1. **Source ingestion:** Videos and images can be uploaded directly (multipart), referenced from storage, or — for images — supplied inline as base64 or as a remote URL that the service downloads. Batch variants run as asynchronous jobs.
2. **Frame extraction and detection (video):** Every Nth frame (configurable via `MM_DATAPREP_FRAME_INTERVAL`) is sampled. When object detection is enabled, the detector generates cropped regions of interest that are embedded separately from the full frame.
3. **Direct embedding (image):** Images skip frame extraction and are embedded as a whole; when object detection is enabled, each detected crop is embedded separately — mirroring the per-frame crop contract used for video.
4. **Embedding generation:** Embeddings are generated through the in-process pipeline, which is memory-first, multi-threaded, and OpenVINO-aware. CLIP-style models embed video frames, images, and text summaries into one shared space, enabling cross-modal search.
5. **Metadata enrichment:** Each record is annotated with a `content_type` (`video`/`image`/`text`), timestamps, download URLs (`/v1/dataprep/media/download`), detection confidences, and tags.
6. **Persistent storage:** Embeddings and metadata are stored in the selected vector database while the raw assets remain in the selected object storage for later retrieval.

## Key Benefits

- **Multimodal ingest:** Video frame-level sampling and image direct-embedding in one API, with optional YOLOX-based object detection for both.
- **Backend agnostic:** Swap the vector database (`MM_DATAPREP_VECTORDB_BACKEND`: `vdms`/`milvus`) or the object storage (`MM_DATAPREP_STORAGE_BACKEND`: `minio`/`local`) without code changes. See [Pluggable Backends](./pluggable-backends.md).
- **Flexible runtime:** Runtime toggles for OpenVINO acceleration and device offload (`MM_DATAPREP_EMBEDDING_DEVICE`, `MM_DATAPREP_DETECTION_DEVICE`) without code changes.
- **Content deduplication:** Optional content-hash dedup (`MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS`) rejects byte-identical re-uploads across all transports (multipart, base64, URL).
- **Consistent metadata model:** Each stored record always references the canonical download URL and includes timestamps, tag lists, `content_type`, and bucket identifiers for frictionless recall.
- **Operational efficiency:** Preloaded embedding client, parallel embedding pipelines, batched image inference, and range/seek-aware downloads reduce latency and I/O overhead.
- **End-to-end observability:** Structured logging, health reporting, and schema-validated requests provide clear insight during development and production operations.

## Feature Highlights

- **REST API surface mounted at `/v1/dataprep`** with endpoints for health, media ingest (`/media/upload`, `/media/ingest`, `/media/process`), batch ingest (`/media/upload/batch`, `/media/ingest/batch`, `/media/process/batch`, `/media/ingest-dir`) with async job polling (`/media/jobs/{job_id}`), metadata retrieval (`/media`), range-aware download (`/media/download`), deletion, RTSP ingest (`/media/rtsp`), and summary ingestion (`/summary`).
- **Three image transports** — multipart binary (`/media/upload`), inline base64 and remote URL (`/media/ingest`, typed on a `type` discriminator).
- **Object detection first-class support** for both video and images with per-request overrides (`enable_object_detection`, `detection_confidence`) and automatic fallback when a model is unavailable.
- **Tags and summaries** that link curated text back to the precise video segment, enabling multi-modal search.
- **Complete CRUD** — upload, list, range-aware download, and delete (which removes both the stored object and its vectors).
- **Containerized deployment** via Docker Compose with companion services for the chosen storage and vector-database backends.

## Example Use Cases

- **Semantic media search:** Populate the vector database with frame, image, and crop embeddings to power temporal aggregation and ranking in Search-MS / VSQA.
- **Operations review:** Store clips, images, and timestamped human summaries that can be replayed directly using generated download URLs.
- **Hybrid analytics:** Combine embeddings with detector metadata to filter results by objects, tags, `content_type`, or time ranges.
- **Content auditing:** Automatically surface media containing specific objects or scenes based on the detector-enhanced embeddings.

## Supporting Resources

- [Get Started Guide](./get-started.md)
  - [System Requirements](./get-started/system-requirements.md)
- [Pluggable Backends](./pluggable-backends.md)
- [API Reference](./api-reference.md)

<!--hide_directive
:::{toctree}
:hidden:

get-started.md
pluggable-backends.md
How It Works: Architecture <how-it-works-architecture.md>
How It Works: Ingestion Flow <how-it-works-ingestion-flow.md>
telemetry-metrics.md
api-reference.md
troubleshooting.md
release-notes.md

:::
hide_directive-->
