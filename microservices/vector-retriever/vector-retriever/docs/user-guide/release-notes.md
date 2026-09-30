# Release Notes: Vector Retriever

These release notes describe the Vector Retriever microservice. For sample-application
integration context, see the [Video Search and Summarization release notes](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/video-search-and-summarization/release-notes.html).

## Version 2026.2.0

**Release Date:** August 4, 2026

**New (initial release):**

- Multi-backend retriever support (`vdms`, `milvus`, `pgvector`, `faiss`)
- Backend-centric folder structure under `src/retriever/backends/`
- Registry-based backend dispatch and filter translation
- Primary `where` filter grammar with compatibility aliases (`tags`, `time_filter`, `filters`)
- Filter capability discovery endpoint (`GET /capabilities/filters`)
- Batch query API with partial error handling
- Image query modality: send an image (base64 or URL) instead of text for visual similarity search, with mutually exclusive `query`/`image` fields
- Developer template and guide for adding new backends
- Docker Compose overlays for running the retriever against a selected backend

**Improved:**

- Hardened the VDMS over-fetch floor so `fetch_k` is always greater than `k`, improving recall when filters discard candidates.
- Backend registry, middleware, and VDMS backend fixes with expanded test coverage.
- Refreshed the OpenAPI specification.
- Resolved a copyleft licensing issue in the service dependencies.
- Documentation fixes and corrections.
