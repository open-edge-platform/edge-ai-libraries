# Behavioral Analysis Service

The Behavioral Analysis Service is an Intel-developed microservice that detects suspicious activity by analyzing sequences of video frames for tracked individuals.

It extracts skeletal pose keypoints using a YOLO26n-pose model optimized with OpenVINO Runtime, then evaluates the resulting pose sequences against behavioral patterns defined in YAML. No code changes are required to add or modify detection behaviors.

When a pose pattern matches, the service can optionally forward sampled key frames to a Visual Language Model (VLM) served by OpenVINO Model Server, adding a frame-level visual check on top of the geometric pose evidence.

The service operates as an event-driven MQTT consumer — it subscribes to a configurable request topic, processes each request, and publishes results to a configurable result topic. It expects frames to already be present in SeaweedFS; frame capture and storage are the responsibility of the upstream system.

**Key features and primary application areas:**

- **Pose extraction** — YOLO26n-pose inference via OpenVINO Runtime (no PyTorch); COCO 17-keypoint skeletal output per frame
- **Declarative pattern engine** — YAML-defined behavioral patterns with positional, angular, distance, and velocity conditions across ordered temporal phases; extensible without code changes
- **VLM confirmation** — optional visual verification using an OpenAI-compatible endpoint (Qwen2.5-VL-7B-Instruct via OVMS) with a built-in circuit breaker and concurrency limiter
- **Event-driven processing** — MQTT-based `request topic` → `result topic` pipeline with entity deduplication and configurable backpressure
- **Built-in loss-prevention pattern** — `shelf_to_waist` concealment detection targeting retail shrinkage scenarios
- **Container-ready** — based on `Intel Deep Learning Streamer (DL Streamer) `; fully configurable via environment variables and a volume-mounted YAML configuration file

Below, you'll find links to detailed documentation to help you get started,
configure, and deploy the microservice.

## Documentation

- Overview

  - [Overview](./docs/user-guide/index.md#1-overview): A high-level introduction to the
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
  deployment (MQTT broker + Seaweedfs) to produce meaningful output.
  
## License

Copyright (C) 2026 Intel Corporation. SPDX-License-Identifier: Apache-2.0
