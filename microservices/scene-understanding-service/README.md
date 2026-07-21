# Scene Understanding Service Microservice

This repository provides a generic, FastAPI-based microservice for multi-scene
behavioral analysis. It subscribes to
[SceneScape](https://github.com/open-edge-platform/scenescape) MQTT topics to
consume scene events and track objects across configured scenes and zones,
applies a declarative rule engine to interpret those events, and routes the
resulting alerts to a downstream alert service. Because all behavior is defined
through configuration rather than code, the service is not tied to any single
use case: detecting suspicious activity (loitering, checkout bypass,
concealment, restricted-zone violations) is just one example of what it can do,
and the same engine can power other scene-understanding scenarios. It is driven
entirely by two YAML config files, so it can be dropped into any SceneScape
deployment without code changes.

Below, you'll find links to detailed documentation to help you get started,
configure, and deploy the microservice.

## Documentation

- Overview

  - [Overview](./docs/user-guide/index.md): A high-level introduction to the
    microservice and its capabilities.
  - [How It Works](./docs/user-guide/how-it-works.md): Internal event flow and the main
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
    available REST API endpoints.

- Support

  - [Troubleshooting](./docs/user-guide/troubleshooting.md): Common issues and how to
    resolve them.

- Release Notes

  - [Release Notes](./docs/user-guide/release-notes.md): Notable updates, improvements,
    and known limitations.

## Notes

- Do not use this page as the run guide; use the linked docs above.
- The service is an event consumer/producer; it requires a reachable SceneScape
  deployment (MQTT broker + REST API) to produce meaningful output.
- All runtime behavior is driven by `configs/scene-config.yaml` and
  `configs/rules.yaml`; the image ships with samples, and a consuming
  application overrides them via a read-only volume mount.

## License

Copyright (C) 2026 Intel Corporation. SPDX-License-Identifier: Apache-2.0
