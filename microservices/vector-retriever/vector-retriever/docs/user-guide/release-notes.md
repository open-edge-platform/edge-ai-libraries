# Release Notes: Vector Retriever

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

For sample-application integration context, see the Video Search and Summarization release notes in the corresponding sample application documentation.

## Supporting Resources

- [Overview](Overview.md)
- [Overview and Architecture](overview-architecture.md)
- [Get Started](get-started.md)
- [API Reference](api-reference.md)
- [OpenAPI Specification](api-docs/openapi.yaml)
- [How to Build from Source](how-to-build-from-source.md)
- [System Requirements](system-requirements.md)
- [Add New Retriever Backend](add-new-retriever-backend.md)
