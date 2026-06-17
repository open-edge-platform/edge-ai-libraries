<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Video Search and Summarization — AI agents

## Canonical Instructions

Use this file as the canonical router for coding agents. Keep tool-specific
files such as `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules/vss.mdc` as short
pointers to this file.

## What This Repo Is

Video Search and Summarization (VSS) is a foundational Intel sample application
that summarizes and natural-language-searches video using VLMs, multimodal
embeddings, and audio analysis, designed to run **locally** on Intel hardware.
It ships as a multi-service Docker Compose stack fronted by an nginx gateway,
with a NestJS **Pipeline Manager** as the central orchestrator/API. Deeper
user docs live under [`docs/`](../../docs/); this file is the agent-facing map.

## Deployment Modes

VSS deploys in four modes via `source setup.sh <mode>` (it must be **sourced**,
not executed, because it exports env vars into the shell):

| Mode | Command | What runs |
|---|---|---|
| Summary | `source setup.sh --summary` | Summarization pipeline + summary UI |
| Search | `source setup.sh --search` | Embedding/index/search + search UI |
| Dual UI | `source setup.sh --summary --search` (`--dual`) | Both, with separate UIs |
| Unified UI | `source setup.sh --summary-and-search` (`--unified`) | Search over summary text in one UI |

Other `setup.sh` verbs: `config` (render config without starting), `--stop`
(`--down`), `--clean-data`, `--help`. Use the `vss-up` skill to drive these.

## Architecture at a Glance

All external traffic enters through **nginx** on host port `APP_HOST_PORT`
(default **`12345`**). The Pipeline Manager API is reachable under the
`/manager/...` prefix (e.g. `GET /manager/health`); UIs are served from the same
gateway. Core services (see `docker/compose.*.yaml`):

- **nginx** — gateway/reverse proxy; the only port agents should target.
- **pipeline-manager** — NestJS orchestrator; owns the `/manager` REST API.
- **search-ms** — Python "video-search" microservice (embeddings + query).
- **video-ingestion** — frame extraction / ingestion pipeline.
- **audio-analyzer** — audio transcription/analysis (summary path).
- **vllm-cpu-service** / **ovms-service** — model serving (vLLM or OpenVINO
  Model Server) for VLM/LLM inference.
- **postgres-service**, **minio-service**, **rabbitmq-service** — metadata DB,
  object storage, and the work queue.

## Repository Map

| Path | Contents |
|---|---|
| `setup.sh` | Deploy/stop/clean entrypoint; composes `docker/compose.*.yaml` by mode. |
| `build.sh` | Build/push images from source (true source build; see `vss-build`). |
| `docker/` | Per-concern Compose files (`compose.base`, `.summary`, `.search`, `.vllm`, `.ui`, `.telemetry`, `.gpu_ovms`). |
| `config/` | Runtime config; `config/nginx/` holds gateway routing (`nginx.conf`, `dual_ui.conf`, `singleton_ui.conf`). |
| `pipeline-manager/` | NestJS/TypeScript orchestrator + `/manager` API. |
| `search-ms/` | Python (Poetry, `^3.11`) video-search microservice. |
| `video-ingestion/` | Python ingestion service. |
| `mcp/` | MCP server exposing VSS Search to AI agents. |
| `cli/` | Go (`go 1.23`) summarizer CLI. |
| `ui/react/` | React front-end(s). |
| `chart/` | Helm chart for Kubernetes deployment. |
| `docs/` | User/developer documentation. |
| `ov_models/`, `data/`, `scripts/` | Model assets, sample/runtime data, helper scripts. |

## Tech Stack

NestJS + TypeScript (pipeline-manager), Python 3.11 + Poetry (search-ms,
video-ingestion, mcp), Go 1.23 (cli), React (ui), Docker Compose for local
deploy and Helm for Kubernetes. Inference via vLLM or OpenVINO Model Server.

## Conventions

- Run repo-local commands from the **repository root** unless a skill says
  otherwise.
- Every new source/config/doc file carries the SPDX header used across the repo
  (`SPDX-FileCopyrightText: (C) 2026 Intel Corporation` / `Apache-2.0`).
- `setup.sh` is **sourced**, never executed directly.
- Target the nginx gateway port (`12345`) and the `/manager/...` prefix; do not
  hit internal service ports directly.

## Skills

Reusable VSS workflow skills live under [`.github/skills/`](skills/). Use
[`.github/skills/skill-catalog.json`](skills/skill-catalog.json) to pick the
relevant skill, then read that skill's `SKILL.md`.

| User intent | Skill |
|---|---|
| Deploy, start, stop, dry-run, or clean VSS | `vss-up` |
| Check health, detect running mode, or debug containers | `vss-doctor` |
| Build or push VSS Docker images | `vss-build` |
| Summarize videos through Pipeline Manager | `vss-summarize` |
| Upload, index, or search videos | `vss-search` |

## Skill Loading Rules

- Load only the skill needed for the current request.
- Use a skill's `references/` files only when its `SKILL.md` points to them.
- Prefer the repo's real interfaces: `setup.sh`, `build.sh`, Docker Compose,
  and the Pipeline Manager API at `/manager/...`.
- Run commands yourself when the harness permits it and relay the result.
- Probe `GET /manager/health` before API workflows. If the backend is not
  healthy, use `vss-doctor` or `vss-up`.

## Path Conventions

All paths in the skill catalog are relative to the repository root. The skills
live in `.github/skills` as the shared location for Codex, Copilot CLI, Claude
Code, Cursor, and local agent scripts.
