<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Agent Quality Handler — AI agents

## Canonical Instructions

- Treat this file as the canonical agent guidance for this microservice.
- Keep changes scoped to `agent-quality-handler`; do not add monorepo-wide policy here.
- Prefer the service's real interfaces: FastAPI endpoints, LangGraph orchestration flow, configured MQTT events, and file-backed defaults.
- Preserve existing API contracts and runtime behavior unless the task explicitly changes them.
- Keep edits minimal, typed, and testable; update nearby docs when APIs, config, or workflows change.
- Use the existing Python and `uv` workflow (`uv sync`, `uv run pytest`, `uv run uvicorn ...`) instead of ad hoc tooling.

## What This Service Is

Agent Quality Handler is a LangGraph multi-agent orchestration service for
agentic predictive maintenance. It exposes a FastAPI service, consumes
batch-complete events over MQTT, runs policy/analysis/evidence/ticketing
agents, and returns persisted reasoning results for bounded detection ranges.

## Repository Map

| Path | Purpose |
| --- | --- |
| `src/main.py` | FastAPI entrypoint, run queue, lifecycle hooks, and HTTP endpoints |
| `src/meta_agent.py` | Top-level LangGraph pipeline orchestration |
| `src/agents/` | Policy, analysis, evidence, and ticketing agent definitions |
| `src/batch_event_subscriber.py` | MQTT subscription, batch-event parsing, and delivery hooks |
| `src/utility/` | Config, runtime settings, LLM, storage, prompt, and output-store helpers |
| `defaults/` | Default agent config, prompts, and fallback policy assets |
| `config/` | Runtime configs for local broker, nginx, and Prometheus setups |
| `tests/` | Pytest coverage for API behavior, graph outcomes, subscriber flow, and storage/output helpers |
| `docs/user-guide/` | User-facing documentation, API reference, build, troubleshooting, and release notes |
| `docker/` | Dockerfile and Compose-based local deployment assets |
| `pyproject.toml` / `uv.lock` | Python package metadata and locked dependency workflow |

## Tech Stack

- Python `>=3.12,<3.13`
- `uv` for dependency management and execution
- FastAPI + Uvicorn for the REST service
- LangGraph for multi-agent orchestration
- OpenAI client integration for LLM-backed execution
- `paho-mqtt` for event intake
- `pydantic` and `PyYAML` for typed config and data handling
- `pytest` for tests

## Conventions

- Keep orchestration changes aligned with the current flow: storage-backed input,
  bounded runs, per-agent outputs, and explicit terminal statuses.
- Prefer typed request/response models and small utility helpers over inline,
  duplicated logic.
- Keep prompts and agent configuration under `defaults/` unless the task
  requires new runtime configuration behavior.
- When changing APIs, runtime settings, or deployment behavior, update the
  matching docs in `docs/user-guide/`.
- Validate with the smallest relevant `uv run pytest ...` command when behavior
  changes.
