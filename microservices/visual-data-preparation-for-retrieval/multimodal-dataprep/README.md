# Multimodal Data Preparation Microservice

The Multimodal DataPrep microservice efficiently ingests and manages multimodal data—videos, images, and text summaries—by converting them into embeddings and storing them with metadata in a vector database. The original media assets are stored in the configured object storage. Images can be supplied as a binary upload, inline base64, or a remote URL.

The microservice is **vector-database and storage agnostic**: the vector store
(`vdms`, `milvus`) and object storage (`minio`, `local`) are each selected at
startup behind a factory, using [VDMS](https://github.com/IntelLabs/vdms) and
Milvus LangChain integrations. See [Pluggable Backends](docs/user-guide/pluggable-backends.md).

> **Note:** Videos must be MP4. Supported image formats are JPG/JPEG, PNG, WEBP, BMP, and GIF.

Follow the links below to the detailed documentation to help you get started, configure, and deploy the microservice.

## Documentation

- **Overview**
  - [Overview](./docs/user-guide/index.md): A high-level introduction to the microservice.
  - [Architecture Overview](docs/user-guide/how-it-works-architecture.md): Detailed architecture.
  - [Pluggable Backends](docs/user-guide/pluggable-backends.md): Vector-database (VDMS/Milvus) and storage (MinIO/local) selection, configuration, and how to add a new backend.

- **Getting Started**
  - [Get Started](docs/user-guide/get-started.md): Step-by-step guide to getting started with the microservice.
  - [System Requirements](./docs/user-guide/get-started/system-requirements.md): Hardware and software requirements for running the microservice.

- **Deployment**
  - [Build from Source](./docs/user-guide/get-started/build-from-source.md): Instructions for building the microservice from source code.

- **API Reference**
  - [API Reference](docs/user-guide/api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](docs/user-guide/release-notes.md): Information on the latest updates, improvements, and bug fixes.
