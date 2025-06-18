# Visual Data Management System (VDMS) based Data Preparation Microservice

[VDMS](https://github.com/IntelLabs/vdms) based DataPrep microservice uses VDMS LangChain integration to efficiently ingest and manage multimodal data—such as images, text, and audio—by converting them into embeddings and storing them with metadata in VDMS. The microservice stores the source video files directly in Minio object storage.

_Note_: Only MP4 video file format is supported for creating embeddings currently.

Below, you'll find links to detailed documentation to help you get started, configure, and deploy the microservice.

## Documentation

- **Overview**
  - [Overview](docs/user-guide/Overview.md): A high-level introduction to the microservice.
  - [Overview Architecture](docs/user-guide/overview-architecture.md): Detailed architecture.

- **Getting Started**
  - [Get Started](docs/user-guide/get-started.md): Step-by-step guide to getting started with the microservice.
  - [System Requirements](docs/user-guide/system-requirements.md): Hardware and software requirements for running the microservice.

- **Deployment**
  - [How to Build from Source](docs/user-guide/how-to-build-from-source.md): Instructions for building the microservice from source code.

- **API Reference**
  - [API Reference](docs/user-guide/api-reference.md): Comprehensive reference for the available REST API endpoints.

- **Release Notes**
  - [Release Notes](docs/user-guide/release-notes.md): Information on the latest updates, improvements, and bug fixes.


