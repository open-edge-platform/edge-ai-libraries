# Release Notes

## Current Release

**Version**: 2026.1.0 \
**Release Date**: 29 May 2026

**Features**:

- Embedding Backend:

  - In-process SDK mode (default, `USE_SDK_EMBEDDING=true`) loads the `multimodal_embedding_serving` model in dataprep and batches raw image frames through a single `encode_image` call, removing the previous per-image base64 HTTP round-trips to MME.
  - Remote HTTP mode is preserved behind `USE_SDK_EMBEDDING=false` for environments that prefer a separate embedding container.
  - OpenVINO GPU acceleration via `EMBEDDING_USE_OV=true` and `EMBEDDING_DEVICE=GPU`; configurable batch size through `EMBEDDING_BATCH_SIZE` (default 32).

- Build & Packaging:

  - New `build.sh` orchestrates the multi-stage docker build, rebuilds and bundles the local `multimodal_embedding_serving` wheel, and honours `REGISTRY` / `TAG` / `IMAGE_NAME` env vars.
  - Multi-stage Dockerfile keeps build-time toolchain out of the runtime image (~3.4 GB final).
  - Shared `ov-models` volume with the embedding service caches Hugging Face weights, OpenVINO IR files, and the YOLOX detection model across container restarts.

**HW used for validation**:

- Intel® Core™ processors (13th Gen, i7 recommended)
- Intel® Arc™ A-Series Graphics (Intel® Arc™ A770 recommended)

## Previous Releases

### 2025.2.0

**Release Date**: 10 Dec 2025

**Features**:

- Data Ingestion:

  - Supports directories or single files for ingestion.
  - Handles image and video formats: jpg, png, mp4.

- Preprocessing Options:

  - Frame extraction from videos with configurable intervals.
  - Optional object detection and cropping.

- Milvus Integration:

  - Stores embeddings and metadata for efficient retrieval.

**HW used for validation**:

- Intel® Core™ processors (13th Gen, i7 recommended)
- Intel® Arc™ A-Series Graphics (Intel® Arc™ A770 recommended)
