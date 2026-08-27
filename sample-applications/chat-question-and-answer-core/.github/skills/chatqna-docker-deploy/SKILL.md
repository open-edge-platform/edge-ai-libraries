---
name: chatqna-docker-deploy
description: >
  Deploy Chat Question-and-Answer Core with Docker Compose (OpenVINO CPU, OpenVINO GPU, or Ollama CPU),
  including env setup, profile selection, startup verification, health checks, and teardown.
  Use this skill when the user says "deploy chatqna core", "start chatqna container", "run compose", "openvino gpu deploy", or "ollama deploy".
metadata:
  version: "1.0.0"
  tags: "chatqna deploy docker compose openvino ollama gpu cpu"
argument-hint: >
  Describe runtime and image source, for example "deploy openvino cpu from prebuilt intel images" or "deploy ollama from local builds with custom model config".
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ChatQnA Docker Deploy

Deploy the Chat Question and Answer Core sample application as containers using
Docker Compose.

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

If runtime/device values are missing, default to `openvino` + `cpu`.

If prebuilt images are used and tags are not specified by the user, default to
pinned release tags.

Use Docker Compose commands only for deployment actions in this skill.

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

If prebuilt images are requested and the user did not provide tags, use pinned
defaults:

```bash
export REGISTRY="intel/"
export BACKEND_TAG="core_1.3.3"      # or core_gpu_1.3.3 / core_ollama_1.3.3
export UI_TAG="core_1.3.3"
```

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

Access URLs:

- UI: `http://<HOST_IP>:8102`
- API docs: `http://<HOST_IP>:8102/v1/chatqna/docs`

### 5. Stop or Reset

```bash
# Stop and remove service containers
docker compose -f docker/compose.yaml down

# Evidence: show running containers after shutdown
docker ps

# Optional deep cleanup (only when explicitly requested)
docker compose -f docker/compose.yaml down -v --remove-orphans
```

When handling a stop request, include the exact `docker ps` output in the
response as evidence that containers are terminated.

Expected evidence for a fully stopped state:

```text
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

## Failure Handling

- `setup_env.sh` returns unsupported backend/device:
	- correct to one of: `openvino` or `ollama`; device `cpu`/`gpu`
- GPU requested but no render node:
	- continue with OpenVINO CPU and report fallback
- container startup failure:
	- collect `docker compose ... logs --tail=200`
	- report failing service name and first actionable error
- health check fails after startup:
	- check backend logs and confirm `HOST_IP`, profile, and model download status
	- note that first startup can take longer due to model download/conversion

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
