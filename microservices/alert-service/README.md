# Alert Service Microservice

This repository provides a FastAPI-based microservice for ingesting, deduplicating, and routing alerts to multiple delivery targets in real time. It accepts any JSON alert payload via a REST API, applies configurable field-hash deduplication strategies to suppress duplicate events within sliding time windows, and fans out alerts to pluggable delivery handlers (Webhook, MQTT, Log, and WebSockets) with automatic isolated retries on failure.

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
    available REST API and WebSocket endpoints.

- Support

  - [Troubleshooting](./docs/user-guide/troubleshooting.md): Common issues and how to
    resolve them.

- Release Notes

  - [Release Notes](./docs/user-guide/release-notes.md): Notable updates, improvements,
    and known limitations.

## Notes

- Do not use this page as the run guide; use the linked docs above.
- Ingestion is case-sensitive: alert types sent by API clients must match the subscriptions in `config/config.yaml` exactly.
