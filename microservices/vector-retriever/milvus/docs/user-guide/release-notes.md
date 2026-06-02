# Release Notes: Vector Retriever - Milvus

## Version 2026.1.0

**June 17, 2026**

**Fixed**

- Docker base images for both the visual data preparation for retrieval and vector retriever Milvus services updated from the pinned `python:3.12.12-slim` to the rolling `python:3.12-slim`; the build now runs a full apt-get upgrade to apply all available OS-level security patches, and apt-get clean is performed to reduce image size.

- `astapi` upgraded from `0.121.1` to `0.121.3` and `pydantic` from `2.9.1` to `2.10.6` to resolve dependency scan findings.

## Version 2025.2.0

**10 Dec 2025**:

**New**

- Microservices Architecture:

  - Retriever Service: Retrieves data from Milvus based on text queries.
  - Multimodal Embedding Service: Generates embeddings for multimodal data.

- Milvus Integration: Seamless vector database support for high-performance retrieval.

- Model Support:

  - Configurable embedding models (e.g., CLIP/clip-vit-h-14).

*Validated configuration*:

- *Intel® Core™ processors (13th Gen, i7 recommended)*
- *Intel® Arc™ A-Series Graphics (Intel® Arc™ A770 recommended)*
