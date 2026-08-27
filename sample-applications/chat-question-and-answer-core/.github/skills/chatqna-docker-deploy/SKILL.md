---
name: chatqna-docker-deploy
description: >
  Deploy Chat Question-and-Answer Core with Docker Compose (OpenVINO CPU, OpenVINO GPU, or Ollama CPU),
  including env setup, profile selection, startup verification, health checks, and teardown.
  Use this skill when the user says "deploy chatqna core", "start chatqna container", "run compose", "openvino gpu deploy", or "ollama deploy".
  Canonical deploy sources are docker/compose.yaml (services and image names) and scripts/setup_env.sh (runtime profile export); Makefile is not the source of truth.
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "chatqna deploy docker compose openvino ollama gpu cpu"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ChatQnA Docker Deploy

Deploy the Chat Question and Answer Core sample application as containers using
Docker Compose.

## Environment setup (run first)

This skill operates on real ChatQnA source files, so the ChatQnA application
must be present and commands must run from the app root. Do this before any
deploy workflow, whether or not source is already in your workspace.

Run the bundled bootstrap. It searches for an existing ChatQnA checkout by
walking up from the current directory and checking the enclosing git repo, then
reuses it without re-cloning. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/chat-question-and-answer-core` from `main`.

It prints the resolved app root on stdout:

```bash
# SKILL_DIR is this skill directory. In-repo it is:
# .github/skills/chatqna-docker-deploy
SKILL_DIR=".github/skills/chatqna-docker-deploy"
APP_ROOT="$(bash "$SKILL_DIR/scripts/chatqna-bootstrap.sh")"
cd "$APP_ROOT"
```

Every command below assumes the working directory is this `APP_ROOT`.

To use a fork/branch or a specific clone path, override these before running
the bootstrap script:

- `CHATQNA_REPO_URL`
- `CHATQNA_REPO_BRANCH`
- `CHATQNA_CLONE_DIR`
- `CHATQNA_FORCE_CLONE` (set to `1` to force clone)

Codebase root: `sample-applications/chat-question-and-answer-core/`

## What This Skill Produces

- A running ChatQnA Core deployment on one backend profile:
  - OpenVINO CPU (`OPENVINO`)
  - OpenVINO GPU (`OPENVINO-GPU`)
  - Ollama CPU (`OLLAMA`)
- A verified startup state using container status, logs, and health endpoint.
- A concise deployment report containing:
  - runtime profile selected
  - image source used (prebuilt tags or locally built)
  - whether pinned default tags or user-provided tags were used
  - access URL and API docs URL
  - any warnings (token/model/device constraints)

## When to Use

- "Deploy chat question and answer core"
- "Start chatqna containers"
- "Run docker compose for chatqna"
- "Deploy OpenVINO GPU profile"
- "Deploy ollama backend"

## Inputs To Confirm

Before running commands, confirm or infer these values:

1. Backend/runtime: `openvino` or `ollama`
2. Device: `cpu` or `gpu` (GPU valid only for OpenVINO)
3. Image source:
   - prebuilt registry images (`REGISTRY`, `BACKEND_TAG`, `UI_TAG`), or
   - local source builds (tags usually `latest`)
4. Optional model config path: `MODEL_CONFIG_PATH`
5. Optional Hugging Face token for private/gated models: `HUGGINGFACEHUB_API_TOKEN`

If runtime/device values are missing, default to `openvino` + `cpu`, proceed directly with OpenVINO CPU using `source scripts/setup_env.sh`.

If prebuilt images are used and tags are not specified by the user, default to
pinned release tags.

Use Docker Compose commands only for deployment actions in this skill.
Always use the repository compose file path `docker/compose.yaml`.
Do not substitute `docker-compose.yml` and do not use placeholders such as
`<compose-file>`.

### Defaulting Rule (Mandatory)

For prompts like "Deploy chatqna core with docker compose" where runtime or
device is omitted:

1. Assume backend=`openvino` and device=`cpu`.
2. Run the standard preflight checks.
3. Select profile with `source scripts/setup_env.sh`.
4. Start with `docker compose -f docker/compose.yaml up -d`.
5. Verify with `docker compose -f docker/compose.yaml ps`,
   `docker compose -f docker/compose.yaml logs --tail=150`, and health check
   on `/v1/chatqna/health`.

## Decision Logic

- If backend is `ollama`:
  - force CPU path
  - use `source scripts/setup_env.sh -b ollama`
- If backend is `openvino` and device is `gpu`:
  - use `source scripts/setup_env.sh -d gpu`
  - if `/dev/dri/render*` does not exist, warn and fall back to CPU path
- Else:
  - use `source scripts/setup_env.sh` (OpenVINO CPU)

## Deployment Workflow

Run from `sample-applications/chat-question-and-answer-core`.

### 1. Preflight

```bash
docker --version
docker compose version
```

If prebuilt images are requested and the user did not provide tags, use the following as defaults:

```bash
export REGISTRY="intel/"
export BACKEND_TAG="core_2026.2.0-rc2"      # or core_gpu_2026.2.0-rc2 / core_ollama_2026.2.0-rc2
export UI_TAG="core_2026.2.0-rc2"
```

These variable names must match `docker/compose.yaml` exactly:

- `REGISTRY`
- `BACKEND_TAG`
- `UI_TAG`

Do not use other variable names other than `REGISTRY`, `BACKEND_TAG`, and `UI_TAG` for this workflow.
Do not use a generic `TAG` variable for this workflow.
Do not default to `latest` when tags are omitted.

If the user explicitly provides different tags or registry, use those values
instead of the pinned defaults.

Optional model config override:

```bash
export MODEL_CONFIG_PATH="/absolute/path/to/config.yaml"
```

Optional gated/private model token:

```bash
export HUGGINGFACEHUB_API_TOKEN="<token>"
```

For gated/private models, use the variable name exactly as above. Do not
replace it with `HF_TOKEN` in this skill.

### 2. Select Profile and Export Environment

Choose exactly one:

```bash
# OpenVINO CPU (default)
source scripts/setup_env.sh

# OpenVINO GPU
source scripts/setup_env.sh -d gpu

# Ollama CPU
source scripts/setup_env.sh -b ollama
```

### 3. Start Containers

Default startup mode is detached:

```bash
docker compose -f docker/compose.yaml up -d
```

### 4. Verify Deployment

```bash
docker compose -f docker/compose.yaml ps
docker compose -f docker/compose.yaml logs --tail=150
curl -sf "http://${HOST_IP:-127.0.0.1}:8102/v1/chatqna/health"
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "http://${HOST_IP:-127.0.0.1}:8102/v1/chatqna/health"
```

When handling a deploy request, include raw command output in the response as
evidence:

- `docker compose -f docker/compose.yaml ps` output showing expected services
  as `Up`.
- Health check output and HTTP status from:
  `curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "http://${HOST_IP:-127.0.0.1}:8102/v1/chatqna/health"`

Expected readiness indicators:

- backend container is `running`
- UI container is `running`
- nginx container for selected profile is `running`
- health endpoint returns success

Access ChatQnA application:

- To access the ChatQnA UI: `http://<HOST_IP>:8102` or `http://localhost:8102`
- To access the ChatQnA API docs: `http://<HOST_IP>:8102/v1/chatqna/docs` or `http://localhost:8102/v1/chatqna/docs`

### 5. Stop or Reset

```bash
# Stop and remove service containers
docker compose -f docker/compose.yaml down

# Evidence: show running containers after shutdown
docker ps
```

When handling a stop request, include the exact `docker ps` output in the
response as evidence that containers are terminated.

Expected evidence for a fully stopped state:

```text
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

The deep cleanup command below (`down -v --remove-orphans`) exists only for
requests that explicitly ask for volume/orphan removal or a full
reset/teardown. For a plain stop request, leave it out of the response
entirely — do not run it, print it, or add a note explaining that it was
skipped; a plain stop only needs the `down` and `docker ps` commands above.

```bash
# Optional deep cleanup (only when explicitly requested)
docker compose -f docker/compose.yaml down -v --remove-orphans
```

## Failure Handling

- `setup_env.sh` returns unsupported backend/device:
  - restrict backend to one of: `openvino` or `ollama`
  - restrict device to one of: `cpu` or `gpu` (GPU valid only for OpenVINO)
  - continue with at least one corrected invocation:
    - `source scripts/setup_env.sh`
    - `source scripts/setup_env.sh -d gpu`
    - `source scripts/setup_env.sh -b ollama`
- GPU requested but no render node:
  - continue with OpenVINO CPU and report fallback
- container startup failure:
  - collect `docker compose -f docker/compose.yaml ps`
  - collect `docker compose -f docker/compose.yaml logs --tail=200`
  - identify and report the failing service name from compose status or logs
  - capture and report the first actionable error from logs
- health check fails after startup:
  - check backend container logs first, for example:
    `docker compose -f docker/compose.yaml logs --tail=200 chatqna-backend-server`
  - validate `HOST_IP` and selected runtime profile (`openvino` or `ollama`)
  - note that first startup can take longer due to model download or conversion
  - re-check health after stabilization:
    `curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "http://${HOST_IP:-127.0.0.1}:8102/v1/chatqna/health"`

## Scenario-Specific Must-Include Commands

- Deploy request with missing runtime/device:
  - `source scripts/setup_env.sh`
  - `docker compose -f docker/compose.yaml up -d`
  - `docker compose -f docker/compose.yaml ps`
  - `curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "http://${HOST_IP:-127.0.0.1}:8102/v1/chatqna/health"`
- OpenVINO GPU deploy request:
  - `source scripts/setup_env.sh -d gpu`
  - check `/dev/dri/render*`; if missing, fall back to `source scripts/setup_env.sh`
  - `docker compose -f docker/compose.yaml up -d`
- Ollama deploy request:
  - state Ollama path is CPU-only in this skill
  - `source scripts/setup_env.sh -b ollama`
  - `docker compose -f docker/compose.yaml up -d`
- Prebuilt image tags request without tags:
  - must use these exact variable names (`REGISTRY`, `BACKEND_TAG`, `UI_TAG`) to set pinned defaults, not alternate names:
    - `export REGISTRY="intel/"`
    - `export BACKEND_TAG="core_2026.2.0-rc2"` (or runtime-specific pinned backend tag)
    - `export UI_TAG="core_2026.2.0-rc2"`
  - do not use `latest` as the default when tags are omitted
  - use only `REGISTRY`, `BACKEND_TAG`, and `UI_TAG`; do not replace them with other variable names
  - if user provides registry/tags, they override these defaults
- Custom model config + token request:
  - `export MODEL_CONFIG_PATH="/absolute/path/to/config.yaml"`
  - `export HUGGINGFACEHUB_API_TOKEN="<token>"`
  - valid profile selection via `setup_env.sh`
  - `docker compose -f docker/compose.yaml up -d`
- Readiness evidence request:
  - include raw outputs for `ps`, `logs --tail=150`, and health with `HTTP_STATUS`
- Stop request:
  - `docker compose -f docker/compose.yaml down`
  - include raw `docker ps` output as termination evidence
  - do not mention, run, or reference `down -v --remove-orphans` unless the
    user explicitly asks for deep cleanup/volume removal

## Completion Criteria

1. Requested runtime profile is started successfully.
2. `docker compose ps` shows expected services running.
3. Health endpoint responds at `/v1/chatqna/health`.
4. User gets access URL, API docs URL, exact stop command, and the image tags used.
5. For deploy requests, response includes raw `docker compose ps` output and
  raw health-check output with `HTTP_STATUS:200` as readiness evidence.
6. For stop requests, response includes raw `docker ps` output as termination
	evidence, and a fully stopped state matches:
	`CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES`
