<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Alert Agent Service — AI agents

## Canonical Instructions

This file is the canonical AI-agent instruction set for the Alert Agent Service.
Keep guidance here service-specific. Do not duplicate broader repository policy or
tool-specific policy into sibling agent files.

## What This Service Is

Alert Agent Service is a FastAPI-based microservice for alert action dispatching.
It receives alert events from upstream detection pipelines, reasons over alert
context using an LLM-powered agentic backend, and dispatches configurable tools
such as logging, webhook notifications, MQTT publishing, and snapshot saving.

The service supports both direct service logic and agentic workflows, with the
main HTTP entrypoint in `src/main.py` and the agent/tool orchestration split
across `src/agentic/`, `src/core/`, `src/schemas/`, and `src/tools/`.

## Repository Map

| Path | Purpose |
| --- | --- |
| `src/main.py` | FastAPI application entrypoint, lifespan setup, API routing, and service wiring |
| `src/agentic/` | LLM agent logic, tool discovery, MCP integration, and agent orchestration |
| `src/core/` | Core processing such as event handling, deduplication, subscriptions, and WebSocket management |
| `src/config.py` | Runtime settings and logging setup |
| `src/schemas/` | Pydantic request, response, and alert schema models |
| `src/tools/` | Action tool implementations such as logging, webhook, MQTT, and snapshot helpers |
| `tests/` | Pytest-based test suite |
| `docs/` | User-guide and API documentation |
| `docker/` | Container build and compose assets |
| `mosquitto/` | MQTT broker configuration used for local or reference deployments |
| `resources/` | Service resources and supporting data files |
| `pyproject.toml` / `uv.lock` | Python project metadata, dependencies, and locked uv environment |

## Tech Stack

- Python 3.12
- `uv` for environment and dependency management
- FastAPI + Uvicorn for the REST service
- Pydantic for schemas and validation
- Google ADK and LiteLLM for agentic / LLM-backed reasoning
- `paho-mqtt` for MQTT publishing
- Mosquitto configuration under `mosquitto/`
- Pytest for tests

## Conventions

- Prefer `uv` workflows for local commands and testing.
- Keep API-facing changes aligned with the FastAPI app and schemas in `src/main.py`
  and `src/schemas/`.
- Keep agent behavior, tool registration, and LLM integration inside `src/agentic/`
  unless a change clearly belongs in shared core logic.
- Keep delivery/action behavior in `src/tools/`; avoid mixing transport-specific logic
  into request schema or API layers.
- Preserve separation between configuration (`src/config.py`), orchestration
  (`src/agentic/`, `src/core/`), and tool execution (`src/tools/`).
- Use pytest for validation, normally through the existing `tests/` suite.
- Update `README.md` or `docs/` when API behavior, configuration, or operator-facing
  workflows change.
