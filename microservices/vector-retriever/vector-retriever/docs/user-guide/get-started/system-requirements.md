# System Requirements

This page describes runtime and tooling requirements for the Vector Retriever microservice.

## Supported Platforms

- Linux (recommended for Docker-based deployment)

## Required Software

- Docker 24.x or newer
- Docker Compose (v2 plugin)
- Python 3.11 - 3.12 for local development and tests
- Poetry 1.8+ for dependency management

## Runtime Dependencies

- Reachable embedding endpoint (`EMBEDDINGS_ENDPOINT`, or `MULTIMODAL_EMBEDDING_ENDPOINT` via `setup.sh`)
- Embedding model name (`EMBEDDING_MODEL_NAME`)

Backend-specific dependencies:

- `vdms`: VDMS Vector DB endpoint
- `milvus`: Milvus endpoint (`MILVUS_URI`)
- `pgvector`: PostgreSQL with pgvector and psycopg3 connection string
- `faiss`: local in-process index (optional disk path for persisted index)

## Minimum Resource Guidance

For local validation:

- CPU: 4 cores
- Memory: 8 GB RAM
- Disk: 5 GB free for images and logs

For production, size resources based on query volume, embedding latency, and backend throughput.

## Network/Proxy Notes

If you are behind a proxy, configure:

- `http_proxy`
- `https_proxy`
- `no_proxy`

## Validation Checklist

- Docker and Compose are available in shell
- Embedding endpoint is reachable from retriever container
- Selected backend endpoint is reachable
- `GET /health` returns `ok`
- `GET /ready` returns `ready`

## Supporting Resources

- [Overview](Overview.md)
- [Overview and Architecture](overview-architecture.md)
- [Get Started](get-started.md)
- [API Reference](api-reference.md)
- [OpenAPI Specification](api-docs/openapi.yaml)
- [How to Build from Source](how-to-build-from-source.md)
- [Add New Retriever Backend](add-new-retriever-backend.md)
- [Release Notes](release-notes.md)
