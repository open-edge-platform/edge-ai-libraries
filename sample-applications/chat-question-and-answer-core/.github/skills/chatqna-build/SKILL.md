---
name: chatqna-build
description: Build Chat Question and Answer Core Docker images from source using direct Docker or Docker Compose build commands (backend CPU, backend GPU, backend Ollama, and UI). Use when the user says "build chatqna", "rebuild images", "build from source", or "prepare images for deployment". Dockerfiles and docker/compose.yaml are the source of truth for builds, not the Makefile.
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "chatqna build development docker compose"
argument-hint: Describe what images to build and for which runtime (for example "build openvino cpu + ui" or "build ollama backend and ui with tag dev").
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ChatQnA Build

Build Chat Question and Answer Core container images directly with Docker and
Docker Compose.

Codebase root: `sample-applications/chat-question-and-answer-core/`

## Build Sources of Truth

| File | Purpose |
|---|---|
| `docker/Dockerfile` | OpenVINO backend image (CPU by default; GPU via `USE_GPU=true`) |
| `docker/Dockerfile.ollama` | Ollama backend image |
| `ui/Dockerfile` | Frontend UI image |
| `docker/compose.yaml` | Canonical image names, build contexts, and build args |

## When to Use

- Build backend and UI images from source
- Rebuild one runtime variant (OpenVINO CPU, OpenVINO GPU, or Ollama)
- Build images with explicit tags before local deploy/publish

## Build Controls

Set tags and optional registry prefix in shell before building:

| Var | Effect | Default |
|---|---|---|
| `BACKEND_TAG` | tag for backend image `${REGISTRY}chatqna:${BACKEND_TAG}` | `latest` |
| `UI_TAG` | tag for UI image `${REGISTRY}chatqna-ui:${UI_TAG}` | `latest` |
| `REGISTRY` | image prefix (for example `intel/`) | empty |
| `http_proxy` / `https_proxy` / `no_proxy` | forwarded into builds | inherited |

Final image names match compose:

- Backend OpenVINO/Ollama: `${REGISTRY}chatqna:${BACKEND_TAG}`
- UI: `${REGISTRY}chatqna-ui:${UI_TAG}`

## Typical Build Flows

```bash
# 0) From sample root
cd sample-applications/chat-question-and-answer-core

# 1) Optional tags/prefix
export REGISTRY=""
export BACKEND_TAG="latest"
export UI_TAG="latest"

# 2) Build OpenVINO CPU backend image
docker build -t ${REGISTRY}chatqna:${BACKEND_TAG} -f docker/Dockerfile .

# 3) Build OpenVINO GPU backend image (same image name/tag, GPU variant)
docker build --build-arg USE_GPU=true -t ${REGISTRY}chatqna:${BACKEND_TAG} -f docker/Dockerfile .

# 4) Build Ollama backend image
docker build -t ${REGISTRY}chatqna:${BACKEND_TAG} -f docker/Dockerfile.ollama .

# 5) Build UI image
docker build -t ${REGISTRY}chatqna-ui:${UI_TAG} -f ui/Dockerfile ui/
```

Compose-driven alternative (build only, no start):

```bash
# Build only active profile services
source scripts/setup_env.sh            # or: -d gpu / -b ollama
docker compose -f docker/compose.yaml build
```

## Prerequisites and Gotchas

- Docker engine and Docker Compose plugin must be available.
- OpenVINO GPU builds require hosts and runtimes that support `/dev/dri` for later runtime.
- `source scripts/setup_env.sh` is recommended before compose builds so profile/env values are aligned.
- If reusing the same `${BACKEND_TAG}` across variants, the latest build will overwrite that local tag.

## Verify

```bash
docker images | grep -E 'chatqna|chatqna-ui'
docker compose -f docker/compose.yaml config --services
```

## Completion Criteria

1. Requested runtime/backend images are built successfully.
2. Resulting local image tags match requested `REGISTRY` and tags.
3. Build output and next action (deploy or push) are clearly reported.
