<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# VLM OpenVINO Serving — AI agents

## Canonical Instructions

Use this file as the canonical router for coding agents. Keep tool-specific
files such as `AGENTS.md`, `CLAUDE.md`, and
`.cursor/rules/vlm-openvino-serving.mdc` as short pointers to this file.

## What This Service Is

VLM OpenVINO Serving is an **OpenAI-API-compatible** microservice (FastAPI +
OpenVINO GenAI) that serves Vision Language Models — image and video chat
completions — on Intel CPUs and GPUs. It targets VLMs not yet supported by
OpenVINO Model Server. A prebuilt image is published as
`intel/vlm-openvino-serving:latest` on Docker Hub. Deeper user docs live under
[`docs/user-guide/`](../docs/user-guide/); this file is the agent-facing map.

## Run Interfaces

- `setup.sh` must be **sourced**, never executed (it exports env vars and uses
  `return`). It requires `VLM_MODEL_NAME` to be exported first and creates the
  external Docker volume `ov-models`.
- Deploy: `export VLM_MODEL_NAME=... && source setup.sh && docker compose -f
  docker/compose.yaml up -d`. Host port `VLM_SERVICE_PORT` (default **9764**)
  maps to container port 8000.
- The first start downloads and converts the model (long); the `ov-models`
  volume caches both the HF download and the converted OpenVINO model.

## API Surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/chat/completions` | Chat completion (OpenAI-compatible; streaming; text/image/video content) |
| GET | `/v1/models` | The single configured model |
| GET | `/v1/telemetry?limit=N` | Recent inference telemetry |
| GET | `/v1/queue-status` | Active/queued request counts |
| GET | `/device`, `/device/{device}` | OpenVINO devices and properties |
| GET | `/health` | 200 healthy / 503 model not ready |

## Repository Map

| Path | Contents |
|---|---|
| `setup.sh` | Env export + `ov-models` volume creation (source it). |
| `docker/` | `compose.yaml` + `Dockerfile` (two-stage, non-root `appuser`). |
| `src/app.py` | All routes + model lifecycle (~1600 lines; model loads at import). |
| `src/utils/` | Settings, data models, telemetry, model conversion helpers. |
| `src/config/model_config.yaml` | Per-model pixel limits + video-capable model list. |
| `scripts/compress_model.sh` | `optimum-cli` export/compression at container start. |
| `tests/` | Four-module Pytest suite with model initialization mocked before import. |
| `docs/user-guide/` | get-started, environment-variables, api-reference (OpenAPI). |

## Tech Stack

Python 3.11+ with Poetry, FastAPI + Gunicorn/Uvicorn, OpenVINO GenAI /
optimum-intel, Docker Compose for deploy.

## Conventions

- Run commands from this microservice's root unless a skill says otherwise.
- `setup.sh` is **sourced**, never executed directly.
- Every new source/config/doc file carries the repo SPDX header
  (`SPDX-FileCopyrightText: (C) 2026 Intel Corporation` / `Apache-2.0`).
- Probe `GET http://localhost:9764/health` before any API workflow.
- Destructive operations (removing the `ov-models` volume, `docker compose
  down -v`) need explicit user confirmation.

## Gotchas

- Exact `VLM_DEVICE=GPU` forces `VLM_COMPRESSION_WEIGHT_FORMAT=int4` and
  `WORKERS=1`; qualified values such as `GPU.0` bypass that exact check.
- GPU OOM surfaces as `error code: -5`; the server self-restarts via
  `os.execv`.
- `video`/`video_url` content is only truly supported on Qwen models; SmolVLM
  reports no telemetry.
- Importing `src.app` triggers a full model download/convert — tests must mock
  `initialize_model`.

## Skills

Reusable workflow skills live under [`.github/skills/`](skills/). Use
[`skill-catalog.json`](skills/skill-catalog.json) to pick the relevant skill,
then read that skill's `SKILL.md`.

| User intent | Skill |
|---|---|
| Deploy, query, or troubleshoot the running service (consume it) | `vlm-openvino-serving-user` |
| Build from source, run tests, navigate/modify the code | `vlm-openvino-serving-dev` |

## Skill Loading Rules

- Load only the skill needed for the current request.
- Open a skill's linked docs or `references/` files only when its `SKILL.md`
  points to them.
- Run commands yourself when the harness permits it and relay the result.

## Path Conventions

All paths in the skill catalog are relative to this microservice's root
(`microservices/vlm-openvino-serving/`). The skills live in `.github/skills`
as the shared location for Codex, Copilot CLI, Claude Code, Cursor, and local
agent scripts. Skills also work without a repo clone — the `-user` skill
fetches the same `setup.sh`/compose files and docs from GitHub and uses the
prebuilt image.
