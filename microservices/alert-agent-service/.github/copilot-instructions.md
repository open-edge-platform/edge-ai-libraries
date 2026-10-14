<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Alert Agent Service — AI agents

## Canonical Instructions

Use this file as the canonical router for coding agents. Keep tool-specific
files such as `AGENTS.md`, `CLAUDE.md`, and
`.cursor/rules/alert-agent-service.mdc` as short pointers to this file.

## What This Service Is

Alert Agent Service is a FastAPI-based microservice for alert action
dispatching (FastAPI + Google ADK + LiteLLM). It receives alert events from
upstream detection pipelines, reasons over alert context using an LLM-powered
agentic backend, and dispatches configurable tools such as logging, webhook
notifications, MQTT publishing, and snapshot saving. Deeper user docs live
under [`docs/`](../docs/); this file is the agent-facing map.

## Run Interfaces

- Deploy: `docker compose -f docker/docker-compose.yml up -d`. Host port
  `PORT` (**8000**) maps to container 8000. LLM backend on port
  `LLM_PORT` (**9001**).
- The service depends on an LLM backend (OVMS) and an MQTT broker (Mosquitto);
  both are defined in the compose file.
- Probe readiness: `GET http://localhost:8000/api/v1/health`.

## API Surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/alerts` | Ingest alert payload from detection pipelines |
| POST | `/actions/execute` | Execute an action against an alert context |
| GET | `/events` | SSE stream of alert events |
| GET | `/tools` | List registered action tools |
| POST | `/tools/reload` | Hot-reload tool definitions |
| GET | `/mcp/status` | MCP integration status |
| GET | `/mcp/tools` | List MCP-discovered tools |
| POST | `/mcp/reload` | Reload MCP tool registry |
| POST | `/mcp/tools/{tool_name}/invoke` | Invoke a specific MCP tool |
| GET | `/subscriptions` | List active alert subscriptions |
| POST | `/subscriptions/reload` | Reload subscription configuration |
| GET | `/health` | 200 healthy / 500 unhealthy |

## Repository Map

| Path | Contents |
|---|---|
| `src/main.py` | FastAPI application entrypoint, lifespan setup, API routing, and service wiring. |
| `src/agentic/` | LLM agent logic, tool discovery, MCP integration, and agent orchestration. |
| `src/core/` | Core processing: event handling, deduplication, subscriptions, and WebSocket management. |
| `src/config.py` | Runtime settings and logging setup. |
| `src/schemas/` | Pydantic request, response, and alert schema models. |
| `src/tools/` | Action tool implementations: logging, webhook, MQTT, and snapshot helpers. |
| `tests/` | Pytest-based test suite. |
| `docs/` | User-guide and API documentation. |
| `docker/` | `docker-compose.yml` + `Dockerfile`. |
| `mosquitto/` | MQTT broker configuration used for local or reference deployments. |
| `resources/` | Service resources and supporting data files. |
| `pyproject.toml` / `uv.lock` | Python project metadata, dependencies, and locked uv environment. |

## Tech Stack

Python 3.12 with `uv` (lockfile-based), FastAPI + Uvicorn, Pydantic for
schemas and validation, Google ADK + LiteLLM for agentic/LLM-backed reasoning,
`paho-mqtt` for MQTT publishing, Mosquitto for local broker, Pytest for tests.

## Conventions

- Run commands from this microservice's root unless a skill says otherwise.
- Prefer `uv sync` and `uv run ...` over ad hoc Python environment setup.
- Every new source/config/doc file carries the repo SPDX header
  (`SPDX-FileCopyrightText: (C) 2026 Intel Corporation` / `Apache-2.0`).
- Probe `GET http://localhost:8000/api/v1/health` before any API workflow.
- Keep agent behavior, tool registration, and LLM integration inside
  `src/agentic/` unless a change clearly belongs in shared core logic.
- Keep delivery/action behavior in `src/tools/`; avoid mixing
  transport-specific logic into request schema or API layers.
- Preserve separation between configuration (`src/config.py`), orchestration
  (`src/agentic/`, `src/core/`), and tool execution (`src/tools/`).
- Update `README.md` or `docs/` when API behavior, configuration, or
  operator-facing workflows change.
- Validate with `uv run pytest` or a targeted pytest selection.

## Gotchas

- The service requires both an LLM backend and MQTT broker to be healthy
  before it can process alerts — ensure the full compose stack is up.
- Tool definitions are loaded at startup; use `/tools/reload` or
  `/mcp/reload` for hot-reload without a full restart.
- The `/alerts` endpoint triggers agentic reasoning which may be slow
  depending on LLM latency — callers should handle timeouts.
- MCP tools are discovered dynamically; if the MCP server is unavailable,
  `/mcp/tools` returns an empty list without error.
- Alert deduplication logic lives in `src/core/` — duplicate payloads within
  the configured window are silently dropped.

## Skills

No task-specific skills are defined yet for this microservice. When skills are
added, they will live under `.github/skills/` following the shared skill
catalog pattern.

## Skill Loading Rules

- Load only the skill needed for the current request.
- Open a skill's linked docs or `references/` files only when its `SKILL.md`
  points to them.
- Run commands yourself when the harness permits it and relay the result.

## Path Conventions

All paths in this file are relative to this microservice's root
(`microservices/alert-agent-service/`). Skills, when added, will live in
`.github/skills/` as the shared location for Codex, Copilot CLI, Claude Code,
Cursor, and local agent scripts.
