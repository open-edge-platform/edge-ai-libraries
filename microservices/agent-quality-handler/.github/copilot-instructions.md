<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Agent Quality Handler — AI agents

## Canonical Instructions

Use this file as the canonical router for coding agents. Keep tool-specific
files such as `AGENTS.md`, `CLAUDE.md`, and
`.cursor/rules/agent-quality-handler.mdc` as short pointers to this file.

## What This Service Is

Agent Quality Handler is a LangGraph multi-agent orchestration service for
agentic predictive maintenance (FastAPI + LangGraph + OpenAI). It consumes
batch-complete events over MQTT, runs policy/analysis/evidence/ticketing
agents, and returns persisted reasoning results for bounded detection ranges.
Deeper user docs live under [`docs/user-guide/`](../docs/user-guide/); this
file is the agent-facing map.

## Run Interfaces

- Deploy: `docker compose -f docker/compose.yaml up -d`. Host port
  `AGENT_PORT` (**5002**) maps to container 5002.
- The service depends on an LLM backend (OVMS, port 8010) and an MQTT broker;
  both are defined in the compose file.
- Probe readiness: `GET http://localhost:5002/health`.

## API Surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/agents/run` | Trigger a full multi-agent orchestration run |
| GET | `/agents/status/{run_id}` | Poll run status |
| GET | `/agents/results/{run_id}` | Retrieve completed run results |
| GET | `/agents/runs` | List all known runs |
| GET | `/agents/outputs/{agent}` | Latest outputs for a specific agent |
| GET | `/agents/outputs/{agent}/{run_id}` | Agent outputs for a specific run |
| GET | `/health` | 200 healthy / 500 unhealthy |
| GET | `/metrics` | Prometheus-compatible metrics |

## Repository Map

| Path | Contents |
|---|---|
| `src/main.py` | FastAPI entrypoint, run queue, lifecycle hooks, and HTTP endpoints. |
| `src/meta_agent.py` | Top-level LangGraph pipeline orchestration. |
| `src/agents/` | Policy, analysis, evidence, and ticketing agent definitions. |
| `src/batch_event_subscriber.py` | MQTT subscription, batch-event parsing, and delivery hooks. |
| `src/utility/` | Config, runtime settings, LLM, storage, prompt, and output-store helpers. |
| `defaults/` | Default agent config, prompts, and fallback policy assets. |
| `config/` | Runtime configs for local broker, nginx, and Prometheus setups. |
| `tests/` | Pytest coverage for API behavior, graph outcomes, subscriber flow, and storage/output helpers. |
| `docs/user-guide/` | User-facing documentation, API reference, build, troubleshooting, and release notes. |
| `docker/` | `compose.yaml` + `Dockerfile`. |
| `pyproject.toml` / `uv.lock` | Python package metadata and locked dependency workflow. |

## Tech Stack

Python >=3.12,<3.13 with `uv` (lockfile-based), FastAPI + Uvicorn, LangGraph
for multi-agent orchestration, OpenAI client for LLM-backed execution,
`paho-mqtt` for event intake, Pydantic + PyYAML for typed config and data
handling, Pytest for tests.

## Conventions

- Run commands from this microservice's root unless a skill says otherwise.
- Prefer `uv sync` and `uv run ...` over ad hoc Python environment setup.
- Every new source/config/doc file carries the repo SPDX header
  (`SPDX-FileCopyrightText: (C) 2026 Intel Corporation` / `Apache-2.0`).
- Probe `GET http://localhost:5002/health` before any API workflow.
- Keep orchestration changes aligned with the current flow: storage-backed
  input, bounded runs, per-agent outputs, and explicit terminal statuses.
- Keep prompts and agent configuration under `defaults/` unless the task
  requires new runtime configuration behavior.
- When changing APIs, runtime settings, or deployment behavior, update the
  matching docs in `docs/user-guide/`.
- Validate with the smallest relevant `uv run pytest ...` command when behavior
  changes.

## Gotchas

- The service requires an active MQTT broker and LLM backend before it can
  process runs — ensure both are healthy in the compose stack.
- Run results are persisted to local storage; losing the container volume loses
  historical outputs.
- `defaults/` assets are loaded at startup; changes require a service restart.
- The `/agents/run` endpoint enqueues work — poll `/agents/status/{run_id}`
  for completion.

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
(`microservices/agent-quality-handler/`). Skills, when added, will live in
`.github/skills/` as the shared location for Codex, Copilot CLI, Claude Code,
Cursor, and local agent scripts.
