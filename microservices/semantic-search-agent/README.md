# Semantic Search Agent Microservice

This repository provides a FastAPI-based microservice for AI-powered item matching and validation. It accepts comparison requests via a REST API, runs them through a configurable multi-strategy matching pipeline (exact string, semantic VLM-based, or hybrid), and returns structured results with confidence scores and detailed match breakdowns. The service consolidates semantic matching logic from multiple edge-AI applications into a single extensible microservice.

Below, you'll find links to detailed documentation to help you get started, configure, and deploy the microservice.

## Documentation

- Overview

  - [Overview](./docs/user-guide/index.md): A high-level introduction to the
    microservice and its capabilities.
  - [How It Works](./docs/user-guide/how-it-works.md): Internal request flow and the main
    components of the service.

- Getting Started

  - [Get Started](./docs/user-guide/get-started.md): Step-by-step entry point that walks
    you through your first run.
  - [System Requirements](./docs/user-guide/get-started/system-requirements.md): Hardware, OS, and
    runtime prerequisites.
  - [Run in Docker](./docs/user-guide/get-started/run-container.md): Step-by-step guide to running
    the microservice in a container.
  - [Run on the Host](./docs/user-guide/get-started/run-standalone.md): Step-by-step guide to
    running the microservice directly on the host.

- Deployment

  - [Build From Source](./docs/user-guide/get-started/build-from-source.md): Instructions for
    building the microservice from source.
  - [Configuration](./docs/user-guide/get-started/configuration.md): Instructions for changing the
    microservice configuration.

- API Reference

  - [API Reference](./docs/user-guide/api-reference.md): Comprehensive reference for the
    available REST API endpoints and Prometheus metrics.

- Support

  - [Troubleshooting](./docs/user-guide/troubleshooting.md): Common issues and how to
    resolve them.

- Release Notes

  - [Release Notes](./docs/user-guide/release-notes.md): Notable updates, improvements,
    and known limitations.

## Notes

- Do not use this page as the run guide; use the linked docs above.
- When `DEFAULT_MATCHING_STRATEGY` is `semantic` or `hybrid`, a VLM backend must be configured (`OVMS_ENDPOINT`+`OVMS_MODEL_NAME`, `OPENVINO_MODEL_PATH`, or `OPENAI_API_KEY`); the service will log an error at startup if required variables are missing.
- For exact-only matching (`DEFAULT_MATCHING_STRATEGY=exact`), no VLM backend is required and the service starts with no external dependencies.
