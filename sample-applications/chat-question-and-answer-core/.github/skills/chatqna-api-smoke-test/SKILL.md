---
name: chatqna-api-smoke-test
description: >
  Validate ChatQnA Core REST APIs from docs/user-guide/api-reference.md using repeatable curl-based smoke tests,
  runtime-specific endpoint checks (OpenVINO or Ollama), and concise pass/fail evidence.
  Use this skill  when the user says "test APIs", "verify endpoint health", "check /chat", "validate docs endpoint", or "smoke test deployment".
license: Apache-2.0
metadata:
  version: "1.0.0"
  tags: "chatqna api smoke-test curl openapi health chat documents openvino ollama"
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# ChatQnA API Smoke Test

Run practical API checks for ChatQnA Core using the documented endpoints in
`docs/user-guide/api-reference.md`.

## Environment setup (run first)

This skill operates on real ChatQnA source files, so the ChatQnA application
must be present and commands must run from the app root. Do this before any
API validation workflow, whether or not source is already in your workspace.

Run the bundled bootstrap. It searches for an existing ChatQnA checkout by
walking up from the current directory and checking the enclosing git repo, then
reuses it without re-cloning. Only when no checkout is found does it do a
shallow, single-branch, sparse checkout of just
`sample-applications/chat-question-and-answer-core` from `main`.

It prints the resolved app root on stdout:

```bash
# SKILL_DIR is this skill directory. In-repo it is:
# .github/skills/chatqna-api-smoke-test
SKILL_DIR=".github/skills/chatqna-api-smoke-test"
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

- A runtime-aware API validation report for one scope:
  - Core health and metadata endpoints
  - Chat inference endpoint
  - Document ingestion lifecycle endpoints
  - Runtime-specific endpoints (OpenVINO device APIs or Ollama model APIs)
- Raw command evidence (`curl` output + HTTP status) for each check.
- A concise pass/fail summary with failing endpoint and first actionable next step.

## When to Use

- "Smoke test the API"
- "Validate /v1/chatqna endpoints"
- "Check chat endpoint response"
- "Verify Swagger/OpenAPI endpoints"
- "Test runtime-specific endpoints for OpenVINO or Ollama"

## Inputs To Confirm

Before running checks, confirm or infer:

1. Base host (`HOST_IP`, default `127.0.0.1`)
2. Port (default `8102`)
3. Runtime (`openvino` or `ollama`, optional but recommended)
4. Scope (`core`, `chat`, `documents`, `runtime`, or `all`; default `core`)

Base URL:

```text
http://<HOST_IP>:8102/v1/chatqna
```

## Decision Logic

- If scope is omitted, run `core` checks first (`/health`, `/model`, docs/openapi).
- If runtime is `openvino`, include `/devices` checks.
- If runtime is `ollama`, include `/ollama-models` and optional `/ollama-model` checks.
- If user asks for full validation, run `all` checks.
- If user asks for non-destructive tests only, avoid `POST /documents` and `DELETE /documents`.

## Smoke Test Workflow

Run from `sample-applications/chat-question-and-answer-core`.

### 1. Ensure Deployment Is Running

If ChatQnA is not already running, start containers before API checks:

```bash
# Select runtime profile (choose one)
source scripts/setup_env.sh            # OpenVINO CPU (default)
# source scripts/setup_env.sh -d gpu   # OpenVINO GPU
# source scripts/setup_env.sh -b ollama # Ollama CPU

# Start services
docker compose -f docker/compose.yaml up -d

# Quick readiness check before API probes
docker compose -f docker/compose.yaml ps
```

If deployment is already running, continue with API smoke tests.

### 2. Preflight and URL Setup

```bash
HOST_IP=${HOST_IP:-127.0.0.1}
BASE_URL="http://${HOST_IP}:8102/v1/chatqna"

echo "${BASE_URL}"
```

### 3. Core Availability

```bash
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/health"
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/model"
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "http://${HOST_IP}:8102/v1/chatqna/docs"
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "http://${HOST_IP}:8102/v1/chatqna/openapi.json"
```

### 4. Chat API Check

```bash
curl -sS -X POST "${BASE_URL}/chat" \
  -H "Content-Type: application/json" \
  -d '{"input":"What is Retrieval-Augmented Generation?","stream":false}' \
  -w "\nHTTP_STATUS:%{http_code}\n"
```

### 5. Runtime-Specific Checks

OpenVINO:

```bash
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/devices"
# Optional device detail probe
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/devices/CPU"
```

Ollama:

```bash
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/ollama-models"
# Optional named model probe
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/ollama-model?model_id=<model-id>"
```

### 6. Document API Checks (Optional)

Non-destructive listing:

```bash
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" "${BASE_URL}/documents"
```

Upload and cleanup (run only when user explicitly requests ingestion testing):

```bash
curl -sS -X POST "${BASE_URL}/documents" \
  -H "Content-Type: multipart/form-data" \
  -F "files=@./doc1.pdf" \
  -w "\nHTTP_STATUS:%{http_code}\n"

curl -sS -X DELETE "${BASE_URL}/documents?delete_all=true" \
  -w "\nHTTP_STATUS:%{http_code}\n"
```

## Failure Handling

- `HTTP_STATUS` is not 2xx:
  - report endpoint, status code, and response body snippet
- `/chat` fails:
  - verify request JSON includes non-empty `input`
- runtime endpoint mismatch (e.g., `/devices` on Ollama):
  - note runtime-specific availability from API reference
- docs/openapi unavailable:
  - verify gateway URL and service readiness via `/health`

## Completion Criteria

1. Requested scope is executed against the correct base URL.
2. Runtime-specific checks match selected runtime.
3. Response includes raw command evidence with HTTP statuses.
4. Final summary clearly marks pass/fail by endpoint.
5. For failures, provide one actionable next debugging step.
