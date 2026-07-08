<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Chat Question and Answer Core - AI agents

## Canonical Instructions

Use this file as the canonical router for coding agents working in this sample
application. Keep tool-specific files such as AGENTS.md or CLAUDE.md as short
pointers to this file.

## What This Repo Is

Chat Question and Answer Core is a foundational Retrieval-Augmented Generation
(RAG) sample application designed for resource-constrained edge deployments. This
sample packages the full RAG workflow into a single backend service with a
web UI, optimized for lower memory footprint.

## Runtime Modes

The application supports two backend runtimes and OpenVINO device selection.
Environment is configured by sourcing `scripts/setup_env.sh` before launching
containers.

| Runtime | Command | Notes |
|---|---|---|
| OpenVINO CPU (default) | `source scripts/setup_env.sh` | Uses profile `OPENVINO` |
| OpenVINO GPU | `source scripts/setup_env.sh -d gpu` | Uses profile `OPENVINO-GPU`; requires `/dev/dri` |
| Ollama CPU | `source scripts/setup_env.sh -b ollama` | Uses profile `OLLAMA`; GPU not supported |

Launch/stop:

- Start: `docker compose -f docker/compose.yaml up -d`
- Stop: `docker compose -f docker/compose.yaml down`

The helper Makefile also provides `make deploy`, `make deploy-build`, and
`make undeploy`.

## Architecture at a Glance

- `chatqna-core-*` backend container: FastAPI-based RAG service (internal port
	`8888`), profile-selected by runtime mode.
- `chatqna-core-ui`: Frontend UI.
- `chatqna-core-nginx`: Gateway and single entrypoint, exposed on host port
	`8102`.

All external traffic should target nginx at `http://<HOST_IP>:8102`.

- API base: `/v1/chatqna`
- Swagger UI: `/v1/chatqna/docs`
- OpenAPI JSON: `/v1/chatqna/openapi.json`

## Repository Map

| Path | Contents |
|---|---|
| `Makefile` | Build/test/deploy helper commands for CPU/GPU and OpenVINO/Ollama modes |
| `docker/compose.yaml` | Runtime composition and profile-specific services |
| `scripts/setup_env.sh` | Exports runtime env vars and compose profiles; generates nginx config |
| `nginx_config/` | Gateway template and generation scripts |
| `app/` | Backend application source |
| `ui/` | Frontend application source |
| `model_config/` | Model configuration templates and examples |
| `drivers/` | Runtime/backend adapter layer |
| `tests/` | API and component tests |
| `docs/user-guide/` | User/developer documentation and API reference |
| `chart/` | Helm deployment chart |

## Tech Stack

- Python backend (FastAPI/Uvicorn execution model)
- Frontend web UI
- Docker Compose for local deployment
- Helm chart for Kubernetes deployment
- OpenVINO and Ollama runtime options

## Conventions

- Run commands from the sample root directory unless documentation explicitly
    says otherwise.
- Source `scripts/setup_env.sh` (do not execute it) so exported environment
	variables are available to the current shell.
- Use gateway URL/port (`8102`) and API prefix (`/v1/chatqna`) for verification.
- Do not hardcode secrets or tokens in source, docs, or scripts.
- Ensure new source and documentation files include SPDX licensing headers per
	repository policy.

## Recommended Validation Flow

1. Configure runtime via `source scripts/setup_env.sh ...`.
2. Start stack: `docker compose -f docker/compose.yaml up -d`.
3. Health probe: `GET http://<HOST_IP>:8102/v1/chatqna/health`.
4. Verify docs endpoint: `http://<HOST_IP>:8102/v1/chatqna/docs`.
5. For document/chat workflows, test `/documents` and `/chat` endpoints.

## Skills

Shared skill files for this sample live under `.github/skills/`.

- Start with `chatqna-build` for image build, build-validation, and packaging
	workflows.
- If skill files and a skill catalog are present, use them as the first routing
	layer for task-specific workflows.
- If `.github/skills/` has only partial coverage, combine available skills with
	this file plus `README.md` and `docs/user-guide/`.

| User intent | Skill |
|---|---|
| Build images, run build validation, prepare packaging | `chatqna-build` |

## Skill Loading Rules

- Load only the minimum skill set needed for the active request.
- Prefer real repo interfaces (`scripts/setup_env.sh`, `docker compose`,
	`Makefile`, documented REST APIs) over ad-hoc wrappers.
- Run commands directly when environment access is available and report concrete
	results.
- Probe health endpoint before deeper API workflow validation.

## Path Conventions

All skill and instruction paths are repository-root relative. Skills
live in `.github/skills` as the shared location for Codex, Copilot CLI, Claude
Code, Cursor, and local agent scripts.
