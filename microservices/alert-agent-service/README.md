# Alert Agent Microservice

**Alert Agent Microservice** is a FastAPI-based microservice for alert action dispatching.
It receives alert events from upstream detection pipelines, reasons over the alert context
using an LLM-powered agentic backend, and dispatches one or more configurable action tools —
such as logging, webhook notifications, MQTT publishing, and snapshot saving.

Below, you will find links to detailed documentation to help you get started,
configure, and deploy the microservice.

## Documentation

- Overview

  - [Overview](./docs/user-guide/index.md): A high-level introduction to the
    microservice and its capabilities.
  - [How It Works](./docs/user-guide/how-it-works.md): An explanation of the internal architecture,
    components, and processing flow.

- Getting Started

  - [Get Started](./docs/user-guide/get-started.md): Step-by-step entry point that walks
    you through your first run.
  - [System Requirements](./docs/user-guide/get-started/system-requirements.md): Hardware, OS, and
    runtime prerequisites.

- API Reference

  - [API Reference](./docs/user-guide/api-reference.md): Comprehensive reference for the
    available REST API endpoints.

- Release Notes

  - [Release Notes](./docs/user-guide/release-notes.md): Notable updates, improvements,
    and known limitations.
