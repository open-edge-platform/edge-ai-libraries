# Text To Speech Microservice

This repository provides a FastAPI-based microservice for text-to-speech
generation with OpenVINO and PyTorch runtime support. It accepts text input,
synthesizes speech with the configured TTS model, and returns either raw WAV
audio or JSON metadata plus a base64-encoded WAV payload.

Below, you'll find links to detailed documentation to help you get started,
configure, and deploy the microservice.

## Documentation

- Overview

  - [Overview](docs/overview.md): A high-level introduction to the
    microservice and its capabilities.
  - [How It Works](docs/how-it-works.md): Internal request flow and the main
    components of the service.

- Getting Started

  - [Get Started](docs/get-started.md): Step-by-step entry point that walks
    you through your first run.
  - [System Requirements](docs/system-requirements.md): Hardware, OS, and
    runtime prerequisites.
  - [Run in Docker](docs/run-container.md): Step-by-step guide to running
    the microservice in a container.
  - [Run on the Host](docs/run-standalone.md): Step-by-step guide to
    running the microservice directly on the host.

- Deployment

  - [Build From Source](docs/build-from-source.md): Instructions for
    building the microservice from source.
  - [Configuration](docs/configuration.md): Instructions for changing the
    microservice configuration.

- API Reference

  - [API Reference](docs/api-reference.md): Comprehensive reference for the
    available REST API endpoints.

- Support

  - [Troubleshooting](docs/troubleshooting.md): Common issues and how to
    resolve them.

- Release Notes

  - [Release Notes](docs/release-notes.md): Notable updates, improvements,
    and known limitations.

## Notes

- Do not use this page as the run guide; use the linked docs above.
- The service currently supports English only; other languages return HTTP
  `400`.
- First startup can be slow because model download or conversion may happen
  during startup.
