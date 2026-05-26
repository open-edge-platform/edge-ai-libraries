# Release Notes

## Release 1.0.0

Highlights:

- Multi-backend retriever support (`vdms`, `milvus`, `pgvector`, `faiss`)
- Backend-centric folder structure under `src/retriever/backends/`
- Registry-based backend dispatch and filter translation
- Primary `where` filter grammar with compatibility aliases (`tags`, `time_filter`, `filters`)
- Filter capability discovery endpoint (`GET /capabilities/filters`)
- Batch query API with partial error handling
- Image query modality: send an image (base64 or URL) instead of text for visual similarity search, with mutually exclusive `query`/`image` fields
- Developer template and guide for adding new backends

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
