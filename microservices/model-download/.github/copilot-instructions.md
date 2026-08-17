<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Model Download — AI agents

## Canonical Instructions

This is the canonical router for AI agents working in the Model Download
microservice. Read this file first, then load deeper workflow guidance from
`.github/skills/` as needed. Keep shared project policy in `AGENTS.md` and do
not duplicate it here.

## What This Service Is

Model Download is a centralized microservice for downloading AI/ML models from
multiple hubs, including HuggingFace, Ollama, Ultralytics, Geti, and Pipeline
Zoo, with optional OpenVINO IR conversion for deployment workflows.

## Repository Map

| Path | Purpose |
| --- | --- |
| `src/api/` | FastAPI app, request models, and REST endpoints |
| `src/core/` | `ModelManager`, job lifecycle, plugin registry, and core orchestration |
| `src/plugins/` | Hub-specific downloader and converter plugins |
| `src/mcp/` | MCP server integration |
| `src/utils/` | Shared helpers and utility code |
| `tests/` | Unit and integration tests run with `pytest` |
| `docker/` | Container build and runtime assets, including the Dockerfile |
| `chart/` | Helm chart for Kubernetes deployment |
| `docs/user-guide/` | User documentation, setup guides, and API docs |
| `.github/skills/` | Task-oriented agent skills for developer and user workflows |

## Tech Stack

- Python 3.11+
- `uv` for dependency and environment management
- FastAPI + Uvicorn for the service API
- `pytest` for tests
- Docker, Helm, and Makefile-based build and deployment workflows

## Conventions

- Run commands from the microservice root: `microservices/model-download/`.
- Prefer `uv sync` and `uv run ...` over ad hoc Python environment setup.
- Use the service's real interfaces when possible: REST API, scripts, Makefile,
  Docker, and Helm.
- Keep changes surgical and aligned with the existing plugin-based architecture.
- Add SPDX copyright and license headers to new source, documentation, and
  agent configuration files where applicable.
- Update `docs/user-guide/` when behavior, setup, API usage, or deployment
  guidance changes.
- Validate changes with the smallest relevant command, usually `uv run pytest`
  or a targeted `pytest` selection.

## Skills

Discover task-specific workflow guidance under `.github/skills/`. Current
Model Download skills include:

- `model-download-dev` — extend, test, debug, or integrate the microservice
  codebase
- `model-download-user` — set up the service and guide model download or
  conversion requests
