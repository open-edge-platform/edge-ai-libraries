<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Model Download — AI agents

## Canonical Instructions

Use this file as the canonical router for coding agents. Keep tool-specific
files such as `AGENTS.md`, `CLAUDE.md`, and
`.cursor/rules/model-download.mdc` as short pointers to this file.

## What This Service Is

Model Download is a centralized microservice for downloading AI/ML models from
multiple hubs (HuggingFace, Ollama, Ultralytics, Geti, Pipeline Zoo) with
optional OpenVINO IR conversion for deployment workflows (FastAPI + plugin
architecture). Deeper user docs live under
[`docs/user-guide/`](../docs/user-guide/); this file is the agent-facing map.

## Run Interfaces

- Deploy: `make deploy` or
  `docker compose -f docker/compose.yaml up -d`. Host port **8200** maps to
  container 8000.
- Probe readiness: `GET http://localhost:8200/health`.
- Build image: `make build`.
- Run tests: `make test` or `uv run pytest`.

## API Surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/models/download` | Submit a model download/conversion job |
| POST | `/models/upload` | Upload a local model |
| GET | `/models/jobs` | List all download/conversion jobs |
| GET | `/models/results` | List completed model artifacts |
| GET | `/jobs` | List jobs (alias) |
| GET | `/jobs/{job_id}` | Get status of a specific job |
| POST | `/jobs/{job_id}/cancel` | Cancel a running job |
| GET | `/plugins` | List registered hub plugins |
| GET | `/health` | 200 healthy / 500 unhealthy |

## Repository Map

| Path | Contents |
|---|---|
| `src/api/` | FastAPI app, request models, and REST endpoints. |
| `src/core/` | `ModelManager`, job lifecycle, plugin registry, and core orchestration. |
| `src/plugins/` | Hub-specific downloader and converter plugins. |
| `src/mcp/` | MCP server integration. |
| `src/utils/` | Shared helpers and utility code. |
| `tests/` | Unit and integration tests run with `pytest`. |
| `docker/` | `compose.yaml` + `Dockerfile` + `entrypoint.sh`. |
| `chart/` | Helm chart for Kubernetes deployment. |
| `docs/user-guide/` | User documentation, setup guides, and API docs. |
| `.github/skills/` | Task-oriented agent skills for developer and user workflows. |

## Tech Stack

Python 3.11+ with `uv` (lockfile-based), FastAPI + Uvicorn for the service
API, plugin-based hub architecture, OpenVINO for model conversion, Pytest for
tests, Docker + Helm + Makefile for build and deployment workflows.

## Conventions

- Run commands from this microservice's root unless a skill says otherwise.
- Prefer `uv sync` and `uv run ...` over ad hoc Python environment setup.
- Every new source/config/doc file carries the repo SPDX header
  (`SPDX-FileCopyrightText: (C) 2026 Intel Corporation` / `Apache-2.0`).
- Probe `GET http://localhost:8200/health` before any API workflow.
- Keep changes surgical and aligned with the existing plugin-based
  architecture.
- Update `docs/user-guide/` when behavior, setup, API usage, or deployment
  guidance changes.
- Validate changes with the smallest relevant command, usually `uv run pytest`
  or a targeted `pytest` selection.

## Gotchas

- Download and conversion jobs are **asynchronous** — submit via
  `/models/download`, then poll `/jobs/{job_id}` for completion.
- The `entrypoint.sh` script downloads external OVMS export scripts at
  container startup; network access is required on first run.
- Plugin registration is automatic via the plugin directory; new plugins must
  follow the existing interface contract in `src/core/`.
- Model artifacts are stored on a volume mount; losing the volume loses
  downloaded models.

## Skills

Reusable workflow skills live under [`.github/skills/`](skills/). Pick the
relevant skill directory and read its `SKILL.md`.

| User intent | Skill |
|---|---|
| Set up the service and download or convert models | `model-download-user` |
| Extend, test, debug, or integrate the codebase | `model-download-dev` |

## Skill Loading Rules

- Load only the skill needed for the current request.
- Open a skill's linked docs or `references/` files only when its `SKILL.md`
  points to them.
- Run commands yourself when the harness permits it and relay the result.

## Path Conventions

All paths in the skill catalog are relative to this microservice's root
(`microservices/model-download/`). The skills live in `.github/skills` as the
shared location for Codex, Copilot CLI, Claude Code, Cursor, and local agent
scripts. Skills also work without a repo clone — the `-user` skill fetches the
same compose files and docs from GitHub and uses the prebuilt image.
